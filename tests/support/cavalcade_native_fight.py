"""Continue the native Cavalcade preserve arm through its initial melee rolls."""

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import cast

from tests.support.cavalcade_native_approach import native_producer
from tests.support.cavalcade_native_charge import digest, snapshot, write_json
from tests.support.cavalcade_native_prefix import RANGED_ID, THREAT_ID

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    FightMovementProposal,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
    replay_event_log_hash,
)
from warhammer40k_core.engine.stratagems import stratagem_decline_payload

HELLBLADE = "000001115:hellblade"
HORN = "000001115:juggernauts-bladed-horn"
FIGHT_SUBMISSIONS = 40
DECLINES = {
    "resolve_reaction_window": "decline",
    "select_dice_reroll": "decline",
    "select_fight_activation_ability": "decline_fight_activation_ability",
    "use_stratagem": "decline_stratagem_window",
}
ORDER_OR_ALLOCATION = frozenset(
    {
        "select_allocation_order",
        "select_attack_weapon_group",
        "select_damage_allocation_model",
        "select_post_roll_attack_pool",
        "select_resolve_target_unit",
    }
)


def melee_proposal(request: DecisionRequest) -> JsonValue:
    """Declare the equipped pair for each model offered the Lord of Change."""
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    assert proposal.unit_instance_id == THREAT_ID
    assert proposal.target_unit_instance_ids == (RANGED_ID,)
    declarations: list[MeleeWeaponDeclaration] = []
    equipped: dict[str, set[str]] = {}
    for row in proposal.available_weapons:
        assert isinstance(row, dict)
        if row["engaged_target_unit_instance_ids"] == []:
            continue
        assert row["engaged_target_unit_instance_ids"] == [RANGED_ID]
        model = cast(str, row["model_instance_id"])
        gear = cast(str, row["wargear_id"])
        assert gear in (HELLBLADE, HORN)
        assert row["is_extra_attacks"] == (gear == HORN)
        assert row["required_weapon_ability_selections"] == []
        model_gear = equipped.setdefault(model, set())
        assert gear not in model_gear
        model_gear.add(gear)
        declarations.append(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=model,
                wargear_id=gear,
                weapon_profile_id=cast(str, row["weapon_profile_id"]),
                weapon_instance_id=cast(str, row["weapon_instance_id"]),
                target_allocations=(MeleeTargetAllocation(RANGED_ID),),
            )
        )
    assert equipped
    assert all(gear == {HELLBLADE, HORN} for gear in equipped.values())
    return validate_json_value(
        MeleeDeclarationProposal(
            proposal.request_id,
            proposal.proposal_kind,
            proposal.actor_id,
            proposal.battle_round,
            proposal.unit_instance_id,
            proposal.source_decision_request_id,
            proposal.source_decision_result_id,
            tuple(declarations),
        ).to_payload()
    )


def fight_choice(request: DecisionRequest) -> tuple[str | None, JsonValue]:
    family = request.decision_type
    if family == "submit_movement_proposal":
        movement = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert movement.unit_instance_id in (THREAT_ID, RANGED_ID)
        assert movement.proposal_kind is ProposalKind.PILE_IN
        return None, validate_json_value(
            FightMovementProposal(
                movement.request_id,
                movement.proposal_kind,
                movement.unit_instance_id,
                "pile_in",
                MovementMode.PILE_IN,
            ).to_payload()
        )
    if family == "submit_melee_declaration":
        return None, melee_proposal(request)
    if family == "submit_stratagem_target_proposal":
        return None, stratagem_decline_payload()
    if family == "select_fight_activation":
        choice = f"fight:normal:{THREAT_ID}"
    elif family in DECLINES:
        choice = DECLINES[family]
    elif family in ORDER_OR_ALLOCATION:
        choice = min(option.option_id for option in request.options)
    else:
        raise AssertionError(f"Unhandled native Fight decision: {family}")
    assert choice in {option.option_id for option in request.options}
    return choice, None


def object_payload(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def view_evidence(session: LocalGameSession, player_id: str) -> JsonValue:
    return validate_json_value(
        {
            "view": session.view(viewer_player_id=player_id),
            "events": session.events_since(EventStreamCursor(), viewer_player_id=player_id),
        }
    )


def require_charge_boundary(session: LocalGameSession) -> None:
    state = session.lifecycle.state
    assert state is not None
    assert state.battle_round == 4
    assert state.active_player_id == "player-b"
    assert state.current_battle_phase is BattlePhase.FIGHT
    assert session.lifecycle.config.game_id == "cavalcade-v995-mirror"
    assert len(state.army_definitions) == 2
    for army in state.army_definitions:
        assert army.roster_legality_report.is_legal
        assert sum(len(unit.own_models) for unit in army.units) == 39
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == "submit_movement_proposal"
    movement = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert movement.proposal_kind is ProposalKind.PILE_IN
    assert movement.unit_instance_id == THREAT_ID
    events = session.lifecycle.decision_controller.event_log.records
    (roll,) = (
        object_payload(object_payload(event.payload)["roll_result"])
        for event in events
        if event.event_type == "charge_roll_resolved"
    )
    dice = object_payload(roll["roll_state"])
    assert dice["current_values"] == [5, 3]
    assert dice["rerolls"] == []
    assert roll["value"] == 9
    (charge,) = (
        object_payload(event.payload)
        for event in events
        if event.event_type == "charge_move_completed"
    )
    assert charge["unit_instance_id"] == THREAT_ID
    assert charge["selected_target_unit_instance_ids"] == [RANGED_ID]
    assert charge["maximum_distance_inches"] == 9
    assert len(cast(list[JsonValue], charge["model_movements"])) == 6
    effects = [
        object_payload(event.payload)
        for event in events
        if event.event_type == "unit_move_completed_mortal_wounds_resolved"
    ]
    assert all(effect["target_unit_instance_id"] == RANGED_ID for effect in effects)
    assert [effect["mortal_wounds"] for effect in effects] == [3, 1, 3]


def attack_evidence(events: tuple[EventRecord, ...], sequence: AttackSequence) -> JsonValue:
    assert sequence.source_phase is BattlePhase.FIGHT
    assert sequence.attacking_unit_instance_id == THREAT_ID
    assert not sequence.is_complete
    assert sequence.attack_pools
    assert {pool.wargear_id for pool in sequence.attack_pools} == {HELLBLADE, HORN}
    assert all(pool.attacks > 0 for pool in sequence.attack_pools)
    assert all(pool.target_unit_instance_id == RANGED_ID for pool in sequence.attack_pools)
    steps = [
        object_payload(event.payload)
        for event in events
        if event.event_type == "attack_sequence_step"
    ]
    assert all(step["sequence_id"] == sequence.sequence_id for step in steps)
    assert {cast(str, step["step"]) for step in steps} >= {"hit", "wound"}
    assert all(step["step"] in ("hit", "critical_hit", "wound", "critical_wound") for step in steps)
    movements = [
        object_payload(event.payload)
        for event in events
        if event.event_type == "fight_movement_completed"
    ]
    assert [movement["unit_instance_id"] for movement in movements] == [THREAT_ID, RANGED_ID]
    assert all(movement["proposal_kind"] == "pile_in" for movement in movements)
    return validate_json_value(sequence.to_payload())


def model_outcomes(
    before: dict[str, JsonValue], after: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    initial_models, final_models = before["models"], after["models"]
    assert isinstance(initial_models, list)
    assert isinstance(final_models, list)
    assert len(initial_models) == len(final_models) == 78
    target_outcome: dict[str, JsonValue] = {}
    for initial, final in zip(initial_models, final_models, strict=True):
        initial_model, final_model = object_payload(initial), object_payload(final)
        assert initial_model["alive"] is True
        if initial_model["unit"] == RANGED_ID:
            assert not target_outcome
            assert initial_model == final_model
            assert initial_model["wounds"] == 11
            target_outcome = {"model": initial_model["id"], "before": 11, "after": 11}
        else:
            assert initial_model == final_model
    assert target_outcome
    return target_outcome


def respond(input_path: Path, output: Path) -> None:
    output.mkdir(parents=True)
    restoration_started = time.monotonic()
    raw = input_path.read_bytes()
    initial = object_payload(json.loads(raw))
    session = LocalGameSession.from_persistence_payload(initial)
    assert digest(session.to_persistence_payload()) == digest(initial)
    require_charge_boundary(session)
    controller = session.lifecycle.decision_controller
    initial_records = controller.records
    initial_events = controller.event_log.records
    before = object_payload(snapshot(session))
    restoration_seconds = time.monotonic() - restoration_started
    assert restoration_seconds <= 900, "Completed native Fight input restoration was late."
    procedure = {
        "producer": native_producer(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_file_sha256": hashlib.sha256(raw).hexdigest(),
        "checkpoint_content_hash": initial["content_hash"],
        "source_identity": initial["source_identity"],
        "horizon": "wound-roll Command Re-roll request before first melee allocation",
        "restoration_seconds": restoration_seconds,
        "restoration_limit_seconds": 900,
        "response_limit_seconds": 300,
        "decision_limit": FIGHT_SUBMISSIONS,
    }
    write_json(output / "procedure.json", procedure)
    started = time.monotonic()
    for index in range(FIGHT_SUBMISSIONS):
        assert time.monotonic() - started <= 300
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.actor_id is not None
        viewer = ViewerContext.for_player(request.actor_id)
        issued = session.view_for_context(viewer=viewer)["pending_decision"]
        assert issued is not None
        public = DecisionRequest.from_payload(cast(DecisionRequestPayload, issued))
        choice, proposal = fight_choice(public)
        result_id = f"native-fight-{session.decision_record_count():04d}"
        journal = {
            "request": issued,
            "choice": choice,
            "proposal": proposal,
            "result_id": result_id,
        }
        write_json(output / f"choice-{index:02}.json", journal)
        if choice is None:
            status = session.submit_viewer_parameterized_payload(
                viewer=viewer, request_id=public.request_id, payload=proposal, result_id=result_id
            )
        else:
            status = session.submit_viewer_option(
                viewer=viewer, request_id=public.request_id, option_id=choice, result_id=result_id
            )
        write_json(output / f"status-{index:02}.json", status.to_payload())
        print("CHOICE", index, request.decision_type, choice, status.status_kind.value, flush=True)
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status

    assert controller.records[: len(initial_records)] == initial_records
    assert controller.event_log.records[: len(initial_events)] == initial_events
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.decision_type == "use_stratagem"
    assert pending.actor_id == "player-b"
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    after = object_payload(snapshot(session))
    assert before["phase"] == after["phase"] == "fight"
    for key in ("placements", "command_points", "faction_resources", "unit_resources"):
        assert before[key] == after[key], key
    target_outcome = model_outcomes(before, after)
    events = controller.event_log.records_since(len(initial_events))
    checkpoint = object_payload(session.to_persistence_payload())
    assert checkpoint["source_identity"] == initial["source_identity"]
    write_json(output / "checkpoint.json", checkpoint)
    write_json(
        output / "viewers.json",
        {player_id: view_evidence(session, player_id) for player_id in ("player-a", "player-b")},
    )
    write_json(
        output / "response.json",
        {
            "input": initial["content_hash"],
            "output": checkpoint["content_hash"],
            "decisions": [
                record.to_payload() for record in controller.records[len(initial_records) :]
            ],
            "events": [event.to_payload() for event in events],
            "before": before,
            "after": after,
            "target_wounds": target_outcome,
            "pending_sequence": attack_evidence(events, sequence),
            "rng_draws_before": object_payload(initial["rng_state"])["draw_count"],
            "rng_draws_after": object_payload(checkpoint["rng_state"])["draw_count"],
            "elapsed_seconds": time.monotonic() - started,
        },
    )
    assert time.monotonic() - started <= 300, "Completed native Fight response was late."


def qualify(input_path: Path, output: Path) -> None:
    started = time.monotonic()
    raw = input_path.read_bytes()
    procedure = json.loads((output / "procedure.json").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == procedure["input_file_sha256"]
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == procedure["source_sha256"]
    initial = object_payload(json.loads(raw))
    checkpoint = object_payload(json.loads((output / "checkpoint.json").read_bytes()))
    response = json.loads((output / "response.json").read_bytes())
    assert initial["content_hash"] == response["input"]
    assert checkpoint["content_hash"] == response["output"]
    assert response["elapsed_seconds"] <= procedure["response_limit_seconds"]
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert digest(restored.to_persistence_payload()) == digest(checkpoint)
    viewers = json.loads((output / "viewers.json").read_bytes())
    assert viewers.keys() == {"player-a", "player-b"}
    tail_count = len(response["decisions"])
    checkpoints: list[ReplayProjectionCheckpoint] = []
    for player_id, expected in viewers.items():
        assert view_evidence(restored, player_id) == expected
        checkpoints.append(
            ReplayProjectionCheckpoint.from_lifecycle(
                lifecycle=restored.lifecycle,
                checkpoint_id=f"native-fight-final:{player_id}",
                decision_record_index=tail_count,
                viewer_player_id=player_id,
                projection_schema=expected["view"]["projection_schema"],
                projection_state_hash=expected["view"]["projection_state_hash"],
            )
        )

    def replay_view(
        lifecycle: GameLifecycle, boundary: ReplayProjectionCheckpoint
    ) -> ReplayProjectionSnapshot:
        assert digest(cast(JsonValue, lifecycle.to_payload())) == checkpoint["lifecycle_hash"]
        viewer = boundary.viewer_player_id
        actual = view_evidence(LocalGameSession(lifecycle=lifecycle), viewer)
        assert actual == viewers[viewer]
        view = object_payload(object_payload(actual)["view"])
        return ReplayProjectionSnapshot(
            viewer, cast(str, view["projection_schema"]), cast(str, view["projection_state_hash"])
        )

    artifact = ReplayArtifact.capture(
        artifact_id="native-preserve-first-melee",
        initial_lifecycle_payload=cast(GameLifecyclePayload, initial["lifecycle"]),
        final_lifecycle=restored.lifecycle,
        projection_checkpoints=tuple(checkpoints),
    )
    assert [record.to_payload() for record in artifact.decision_records] == response["decisions"]
    assert [event.to_payload() for event in artifact.event_records] == response["events"]
    replay_path = output / "fight-replay.json"
    write_json(replay_path, artifact.to_payload())
    proof = ReplayRunner.from_payload(
        json.loads(replay_path.read_bytes()), projection_provider=replay_view
    ).run()
    assert proof.reproduced_exactly, proof
    assert not proof.diagnostics
    assert proof.reproduced_decision_count == tail_count
    assert proof.reproduced_event_count == len(
        restored.lifecycle.decision_controller.event_log.records
    )
    assert proof.final_event_log_hash == replay_event_log_hash(restored.lifecycle)
    write_json(
        output / "qualification.json",
        {
            "input": initial["content_hash"],
            "output": checkpoint["content_hash"],
            "strict_JSON_save_load_equal": True,
            "both_viewers_and_events_equal": True,
            "final_lifecycle_equal": True,
            "replay": proof.to_payload(),
            "elapsed_seconds": time.monotonic() - started,
            "limit_seconds": 900,
        },
    )
    assert time.monotonic() - started <= 900, "Completed native Fight qualification was late."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charge-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualify-saved", action="store_true")
    args = parser.parse_args()
    operation = qualify if args.qualify_saved else respond
    operation(args.charge_checkpoint, args.output)


if __name__ == "__main__":
    main()
