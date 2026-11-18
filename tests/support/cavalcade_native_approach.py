"""Finite operator continuation of the complete native mirror, never an AI policy.

All paths are submitted through the ordinary viewer facade. Rejected attempts stay
in the history; a revised recipe is an explicitly selected subsequent experiment.
The existing collected native prefix workload and its measured source stay intact.
"""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Literal, cast

from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.support.cavalcade_native_prefix import (
    RANGED_ID,
    SCREEN_ID,
    SHADOW_LORD_SOURCE_ID,
    THREAT_ID,
    complete_native_prefix,
)
from tests.support.cavalcade_v995 import deployment_fixture, mirror_router, strict_mirror_session

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunBoundary, RunLimits
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload

NativeRecipe = Literal["original-v1", "revised-v3", "revised-v4", "revised-v5", "revised-v6"]
NativeAlternative = Literal["preserve", "screen"]
Translation = tuple[float, float, float]


def approach_moves(
    *, battle_round: int, player_id: str, recipe: NativeRecipe
) -> dict[str, Translation]:
    """Frozen translations; v3 retains the rejected v1 attempt in its input history."""
    assert recipe in ("original-v1", "revised-v3", "revised-v4", "revised-v5", "revised-v6")
    moves: dict[tuple[int, str], dict[str, Translation]] = {
        (1, "player-b"): {THREAT_ID: (0, 6, 0)},
        (2, "player-a"): {RANGED_ID: (0, -8, 0), SCREEN_ID: (0, -5, 0)},
        (2, "player-b"): {THREAT_ID: (-6, 0 if recipe == "original-v1" else 3, 0)},
        (3, "player-a"): {SCREEN_ID: (1, -4, 0)},
        (3, "player-b"): {THREAT_ID: (0, 9 if recipe == "original-v1" else 6, 0)},
        (4, "player-a"): {SCREEN_ID: (3, -4, 0)},
        (4, "player-b"): {THREAT_ID: (0, 8, 0)},
    }
    if recipe in ("revised-v4", "revised-v5", "revised-v6"):
        moves[(2, "player-b")] = {THREAT_ID: (-7, 7, 0)}
        moves[(3, "player-b")] = {THREAT_ID: (1, 2, 0)}
    if recipe in ("revised-v5", "revised-v6"):
        moves[(3, "player-a")] = {SCREEN_ID: (0, -3, 0)}
        moves[(4, "player-a")] = {SCREEN_ID: (2.3, -4.4, 0)}
        moves[(3, "player-b")] = {THREAT_ID: (0, 5, 0)}
        moves[(4, "player-b")] = {THREAT_ID: (1, 5, 0)}
    if recipe == "revised-v6":
        moves[(4, "player-a")] = {SCREEN_ID: (2.2, -4.48, 0)}
    return moves.get((battle_round, player_id), {})


def at_screen_choice(session: LocalGameSession) -> bool:
    state = session.lifecycle.state
    assert state is not None
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    if not (
        state.battle_round == 4
        and state.active_player_id == "player-a"
        and state.current_battle_phase is BattlePhase.MOVEMENT
        and request.decision_type == "select_movement_action"
    ):
        return False
    assert isinstance(request.payload, dict)
    return request.payload["unit_instance_id"] == SCREEN_ID


def submit_approach_choice(
    session: LocalGameSession,
    *,
    recipe: NativeRecipe,
    alternative: NativeAlternative | None = None,
) -> LifecycleStatus:
    """Submit exactly one declared choice; caller owns bounds, advancement and stops."""
    state = session.lifecycle.state
    assert state is not None
    assert 1 <= state.battle_round <= 4
    assert state.active_player_id is not None
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.actor_id is not None
    actor = request.actor_id
    public = session.view(viewer_player_id=actor)["pending_decision"]
    assert public is not None
    family = request.decision_type
    moves = approach_moves(
        battle_round=state.battle_round, player_id=state.active_player_id, recipe=recipe
    )
    if state.battle_round == 4 and state.active_player_id == "player-a":
        assert alternative in (None, "preserve", "screen")
        assert alternative is not None or not at_screen_choice(session)
        if alternative == "preserve":
            del moves[SCREEN_ID]
    proposal: JsonValue | None = None
    choice = ""
    choices: list[str] = []
    if family == "select_faction_rule_shooting_phase_start_option":
        for option in public["options"]:
            payload = option["payload"]
            assert isinstance(payload, dict)
            selected = payload["selected_named_weapon_ability_choice"]
            assert isinstance(selected, dict)
            if selected["keyword"] == "Ignores Cover":
                choices.append(option["option_id"])
        assert len(choices) == 1
        choice = choices[0]
    elif family == "select_faction_rule_battle_round_option":
        for option in public["options"]:
            payload = option["payload"]
            assert isinstance(payload, dict)
            if payload["selected_shadow_form_source_id"] == SHADOW_LORD_SOURCE_ID:
                choices.append(option["option_id"])
        assert len(choices) == 1
        choice = choices[0]
    elif family == "resolve_reaction_window":
        choice = "decline"
    elif family == "use_stratagem":
        choice = "decline_stratagem_window"
    elif family == "submit_stratagem_target_proposal":
        proposal = stratagem_decline_payload()
    elif family == "select_shooting_unit":
        choice = "complete_shooting_phase"
    elif family == "select_charging_unit":
        choice = "complete_charge_phase"
    elif family == "select_movement_unit":
        order = (
            *moves,
            *(
                unit.unit_instance_id
                for army in state.army_definitions
                if army.player_id == state.active_player_id
                for unit in army.units
                if unit.unit_instance_id not in moves
            ),
        )
        offered = {option["option_id"] for option in public["options"]}
        choice = next(unit_id for unit_id in order if unit_id in offered)
    elif family == "select_movement_action":
        payload = public["payload"]
        assert isinstance(payload, dict)
        choice = "normal_move" if payload["unit_instance_id"] in moves else "remain_stationary"
    elif family == "submit_movement_proposal":
        movement = MovementProposalRequest.from_decision_request_payload(public["payload"])
        dx, dy, dz = moves[movement.unit_instance_id]
        proposal = validate_json_value(
            MovementProposalPayload(
                proposal_request_id=movement.request_id,
                proposal_kind=movement.proposal_kind,
                unit_instance_id=movement.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="normal",
                witness=straight_line_witness_for_unit(
                    session.lifecycle,
                    unit_instance_id=movement.unit_instance_id,
                    dx=dx,
                    dy=dy,
                    dz=dz,
                ),
            ).to_payload()
        )
    else:
        raise AssertionError(f"Unenumerated native approach request: {family}")
    result_id = f"native-approach-{session.decision_record_count():04d}"
    viewer = ViewerContext.for_player(actor)
    if proposal is not None:
        return session.submit_viewer_parameterized_payload(
            viewer=viewer, request_id=public["request_id"], payload=proposal, result_id=result_id
        )
    return session.submit_viewer_option(
        viewer=viewer, request_id=public["request_id"], option_id=choice, result_id=result_id
    )


def native_producer() -> JsonValue:
    """Record actual producer HEAD and exact input bytes, including an uncommitted harness."""
    root = Path(__file__).resolve().parents[2]
    paths = (
        "tests/support/cavalcade_native_approach.py",
        "tests/support/cavalcade_native_qualification.py",
        "tests/support/cavalcade_native_prefix.py",
        "tests/support/cavalcade_v995.py",
        "tests/movement_submission_helpers.py",
        "tests/sequential_translation_helpers.py",
        "tests/factions/chaos_daemons/integration/fixtures/cavalcade_v995_deployment.json",
    )
    return {
        "head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "working_tree_status": subprocess.run(
            ["git", "status", "--short"], cwd=root, check=True, capture_output=True, text=True
        ).stdout,
        "input_sha256": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths
        },
    }


def reproduce_native_common(output: Path) -> LocalGameSession:
    """Fresh, fixed 900-second reproduction of the ordinary round-four common prefix.

    This is verification of the frozen experiment, not a new route search or a
    reinterpretation of its earlier eight-attempt, 300-second stage campaign.
    """
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    producer = native_producer()
    session = strict_mirror_session()
    setup = BoundedPolicyRunner(
        session=session,
        router=mirror_router(deployment_fixture()),
        limits=RunLimits(policy_seed=19, max_decisions=42, max_seconds=120),
    ).run(stop_at=RunBoundary("battle", "command"))
    assert len(setup.decisions) == 42
    assert all(decision.accepted for decision in setup.decisions)
    complete_native_prefix(session)
    assert session.decision_record_count() == 68
    recipes: tuple[tuple[NativeRecipe, int, str], ...] = (
        ("original-v1", 129, "end_on_model_overlap"),
        ("revised-v3", 130, "model_cannot_be_placed_at_endpoint"),
        ("revised-v4", 158, "model_cannot_be_placed_at_endpoint"),
        ("revised-v5", 212, "common-before-s"),
    )
    rejections: list[JsonValue] = []
    try:
        for recipe, expected_count, expected_stop in recipes:
            while True:
                assert time.monotonic() - started < 900, "Native reproduction time limit."
                assert session.decision_record_count() < 600, "Native reproduction record limit."
                if at_screen_choice(session):
                    assert expected_stop == "common-before-s"
                    assert session.decision_record_count() == expected_count
                    break
                status = submit_approach_choice(session, recipe=recipe)
                if status.status_kind is LifecycleStatusKind.INVALID:
                    assert session.decision_record_count() == expected_count
                    payload = status.payload
                    assert isinstance(payload, dict)
                    assert payload["violation_code"] == expected_stop
                    rejections.append(
                        validate_json_value(
                            {
                                "recipe": recipe,
                                "status": status.to_payload(),
                                "record": session.lifecycle.decision_controller.records[
                                    -1
                                ].to_payload(),
                            }
                        )
                    )
                    break
                assert status.status_kind is not LifecycleStatusKind.UNSUPPORTED, status
                advanced = session.advance_until_decision_or_terminal()
                assert advanced.status_kind not in (
                    LifecycleStatusKind.INVALID,
                    LifecycleStatusKind.UNSUPPORTED,
                ), advanced
    finally:
        (output / "common-checkpoint.json").write_text(
            json.dumps(session.to_persistence_payload(), sort_keys=True), encoding="utf-8"
        )
        (output / "common-rejections.json").write_text(
            json.dumps(rejections, indent=2), encoding="utf-8"
        )
    assert at_screen_choice(session)
    elapsed = time.monotonic() - started
    receipt: dict[str, JsonValue] = {
        "schema": "native-v995-round4-common-v1",
        "producer": producer,
        "interaction_area_inches": {"x": [14, 26], "y": [28, 40]},
        "records": session.decision_record_count(),
        "common_checkpoint_hash": cast(dict[str, JsonValue], session.to_persistence_payload())[
            "content_hash"
        ],
        "elapsed_seconds": elapsed,
        "limit_seconds": 900,
        "within_declared_limit": elapsed <= 900,
        "alternatives": {"preserve": "remain_stationary", "screen": [2.2, -4.48, 0]},
        "B_response": [1, 5, 0],
        "endpoint": "first B round-four Charge request, before charging-unit selection",
        "not_demonstrated": ["useful_screen", "charge_path", "combat", "E_attack", "learning"],
    }
    (output / "common-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2), flush=True)
    assert elapsed <= 900, "Completed native reproduction exceeded its declared time limit."
    return session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--qualify", action="store_true", help="Also construct and qualify both forks."
    )
    parser.add_argument(
        "--resume-common",
        action="store_true",
        help="Strictly restore the existing common checkpoint; do not repeat startup.",
    )
    args = parser.parse_args()
    output = cast(Path, args.output)
    common_started = None
    restored_checkpoint = None
    if args.resume_common:
        assert args.qualify, "Resume is only for exact common/fork qualification."
        common_started = time.monotonic()
        restored_checkpoint = json.loads(
            (output / "common-checkpoint.json").read_text(encoding="utf-8")
        )
        session = LocalGameSession.from_persistence_payload(restored_checkpoint)
        assert session.to_persistence_payload() == restored_checkpoint
        assert at_screen_choice(session)
    else:
        session = reproduce_native_common(output)
    if args.qualify:
        from tests.support.cavalcade_native_qualification import qualify_native_pair

        qualify_native_pair(
            session,
            output=output,
            common_started=common_started,
            restored_checkpoint=restored_checkpoint,
        )


if __name__ == "__main__":
    main()
