"""Frozen operator charge experiment on the native round-four alternatives.

Prepare both inputs and the procedure before running either response. This is a
finite path experiment, not a complete charge generator or a tactical policy.
"""

import argparse
import hashlib
import json
import math
import multiprocessing
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

from tests.support.cavalcade_native_approach import NativeAlternative, native_producer
from tests.support.cavalcade_native_prefix import RANGED_ID, THREAT_ID
from tests.support.cavalcade_native_qualification import (
    continue_native_branch,
    qualify_native_checkpoint,
)

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import ModelPath, PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload
from warhammer40k_core.geometry.volume import Model

ALTERNATIVES: tuple[NativeAlternative, ...] = ("preserve", "screen")
ROTATIONS = (0, -15, 15, -30, 30, -45, 45, 60)
# Closest starting rank first; then alternate around E. No dice-dependent order.
MODEL_ORDER = (4, 5, 2, 3, 0, 1)
ANGLES = (-50, 10, -110, 70, -170, 130)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")


def digest(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def snapshot(session: LocalGameSession) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    pending = session.lifecycle.pending_decision_request()
    return validate_json_value(
        {
            "round": state.battle_round,
            "phase": state.current_battle_phase.value if state.current_battle_phase else None,
            "active_player": state.active_player_id,
            "pending": pending.to_payload() if pending is not None else None,
            "models": [
                {
                    "unit": unit.unit_instance_id,
                    "id": model.model_instance_id,
                    "alive": model.is_alive,
                    "wounds": model.wounds_remaining,
                    "equipment": list(model.wargear_ids),
                }
                for army in state.army_definitions
                for unit in army.units
                for model in unit.own_models
            ],
            "placements": state.battlefield_state.to_payload(),
            "records": session.decision_record_count(),
            "command_points": [ledger.to_payload() for ledger in state.command_point_ledgers],
            "faction_resources": [ledger.to_payload() for ledger in state.faction_resource_ledgers],
            "unit_resources": [ledger.to_payload() for ledger in state.unit_resource_ledgers],
            "RNG_seed_sha256": hashlib.sha256(state.private_rng_seed.encode()).hexdigest(),
            "event_history_sha256": digest(
                validate_json_value(
                    [
                        event.to_payload()
                        for event in session.lifecycle.decision_controller.event_log.records
                    ]
                )
            ),
            "lifecycle_sha256": digest(cast(JsonValue, session.lifecycle.to_payload())),
        }
    )


def contact_templates(session: LocalGameSession) -> list[JsonValue]:
    """Eight predetermined rings; only distance geometry is read, never future RNG.

    Each ring places six actual, unchanged-facing models at 0.25-inch physical
    range of E. Bisection locates that radial endpoint; it does not validate paths
    or test alternate rules outcomes. Engine submission remains authoritative.
    """
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    models = tuple(
        sorted(
            physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=THREAT_ID),
            key=lambda model: model.model_id,
        )
    )
    targets = physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=RANGED_ID)
    assert len(models) == 6
    assert len(targets) == 1
    target = targets[0]
    templates: list[JsonValue] = []
    for rotation in ROTATIONS:
        endpoints: list[JsonValue] = []
        for index, angle in zip(MODEL_ORDER, ANGLES, strict=True):
            model = models[index]
            theta = math.radians(angle + rotation)
            low, high = 0.0, 20.0

            def pose(radius: float, theta: float = theta, model: Model = model) -> Pose:
                return Pose.at(
                    target.pose.position.x + radius * math.cos(theta),
                    target.pose.position.y + radius * math.sin(theta),
                    model.pose.position.z,
                    facing_degrees=model.pose.facing.degrees,
                )

            for _ in range(60):
                mid = (low + high) / 2
                if replace(model, pose=pose(mid)).range_to(target) < 0.25:
                    low = mid
                else:
                    high = mid
            endpoints.append(
                validate_json_value(
                    {
                        "model_id": model.model_id,
                        "start": model.pose.to_payload(),
                        "end": pose(high).to_payload(),
                    }
                )
            )
        templates.append({"rotation_degrees": rotation, "endpoints": endpoints})
    return templates


def prepare(common_path: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "procedure.json").exists(), "Never overwrite a frozen campaign."
    checkpoint = json.loads(common_path.read_text(encoding="utf-8"))
    common = LocalGameSession.from_persistence_payload(checkpoint)
    assert common.to_persistence_payload() == checkpoint
    common_records = tuple(common.lifecycle.decision_controller.records)
    inputs: dict[str, JsonValue] = {}
    template = None
    for alternative in ALTERNATIVES:
        started = time.monotonic()
        branch = common.fork()
        try:
            continue_native_branch(branch, alternative=alternative, started_at=started)
        finally:
            write_json(output / f"{alternative}-input.json", branch.to_persistence_payload())
        assert (
            tuple(branch.lifecycle.decision_controller.records[: len(common_records)])
            == common_records
        )
        assert common.to_persistence_payload() == checkpoint
        elapsed = time.monotonic() - started
        write_json(
            output / f"{alternative}-construction.json", {"seconds": elapsed, "limit_seconds": 300}
        )
        assert elapsed <= 300
        templates = contact_templates(branch)
        if template is None:
            template = templates
        else:
            assert templates == template, "B and E geometry must match before either charge."
        saved = cast(dict[str, JsonValue], branch.to_persistence_payload())
        inputs[alternative] = {"content_hash": saved["content_hash"], "before": snapshot(branch)}
        print("PREPARED", alternative, elapsed, flush=True)
    procedure: JsonValue = {
        "schema": "native-bloodcrusher-E-charge-v3",
        "producer": native_producer(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "common_content_hash": checkpoint["content_hash"],
        "inputs": inputs,
        "templates": template,
        "response_limit_seconds": 300,
        "strict_input_restoration_limit_seconds": 900,
        "path_attempt_limit": 8,
        "decision_limit": 80,
        "choices": {
            "charger": THREAT_ID,
            "target": RANGED_ID,
            "rerolls": "keep natural roll",
            "optional_reactions_and_stratagems": "decline",
            "mandatory_charge_ability_target": RANGED_ID,
            "mandatory_wound_allocation": "lexicographically first offered model",
            "path": (
                "straight segment toward each frozen endpoint, capped at "
                "max(0, rolled budget - 0.001); frozen model order"
            ),
            "rejected_path": "next frozen template; exhausted or unresolved remains incomplete",
            "other_chargers": "complete charge phase",
            "horizon": "first pending Fight decision; submit no Fight choice or attack",
        },
        "qualification_limit_seconds": 900,
        "claims_excluded": [
            "useful_screen",
            "melee_attack",
            "E_attack",
            "tactical_benefit",
            "learning",
        ],
    }
    write_json(output / "procedure.json", procedure)
    write_json(output / "procedure-sha256.json", {"sha256": digest(procedure)})
    print("PROCEDURE_FROZEN", digest(procedure), flush=True)


def path_for_template(template: JsonValue, budget: float) -> PathWitness:
    assert isinstance(template, dict)
    rows = template["endpoints"]
    assert isinstance(rows, list)
    assert len(rows) == 6
    paths: list[ModelPath] = []
    for row in rows:
        assert isinstance(row, dict)
        assert isinstance(row["model_id"], str)
        start = Pose.from_payload(cast(PosePayload, row["start"]))
        goal = Pose.from_payload(cast(PosePayload, row["end"]))
        distance = start.distance_3d_to(goal)
        fraction = min(1.0, max(0.0, budget - 0.001) / distance)
        end = Pose.at(
            start.position.x + fraction * (goal.position.x - start.position.x),
            start.position.y + fraction * (goal.position.y - start.position.y),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        paths.append((row["model_id"], (start, end)))
    return PathWitness.for_paths(tuple(paths))


def respond(output: Path, alternative: NativeAlternative) -> None:
    restoration_started = time.monotonic()
    publish_response_phase(output, alternative, phase="restoration", started=restoration_started)
    procedure = json.loads((output / "procedure.json").read_text(encoding="utf-8"))
    expected = json.loads((output / "procedure-sha256.json").read_text(encoding="utf-8"))["sha256"]
    assert digest(procedure) == expected
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == procedure["source_sha256"]
    assert not (output / f"{alternative}-response.json").exists(), "Do not reroll a campaign."
    checkpoint = json.loads((output / f"{alternative}-input.json").read_text(encoding="utf-8"))
    assert checkpoint["content_hash"] == procedure["inputs"][alternative]["content_hash"]
    session = LocalGameSession.from_persistence_payload(checkpoint)
    assert session.to_persistence_payload() == checkpoint
    restored_at = time.monotonic()
    write_json(
        output / f"{alternative}-input-restoration.json",
        {
            "elapsed_seconds": restored_at - restoration_started,
            "limit_seconds": 900,
            "strict_persistence_equal": True,
            "checkpoint_content_hash": checkpoint["content_hash"],
        },
    )
    assert restored_at - restoration_started <= 900
    initial_records = session.decision_record_count()
    initial_events = len(session.lifecycle.decision_controller.event_log.records)
    started = time.monotonic()
    publish_response_phase(output, alternative, phase="response", started=started)
    journal: list[JsonValue] = []
    attempt = 0
    selected = False
    outcome = "incomplete"
    try:
        for _ in range(80):
            assert time.monotonic() - started < 300, "Frozen response time limit."
            state = session.lifecycle.state
            assert state is not None
            request = session.lifecycle.pending_decision_request()
            assert request is not None
            assert request.actor_id is not None
            if state.current_battle_phase is BattlePhase.FIGHT:
                outcome = "first_Fight_decision_before_attacks"
                break
            assert state.current_battle_phase is BattlePhase.CHARGE
            public = session.view(viewer_player_id=request.actor_id)["pending_decision"]
            assert public is not None
            family = request.decision_type
            choice = ""
            proposal = None
            if family == "select_charging_unit":
                choice = THREAT_ID if not selected else "complete_charge_phase"
                selected = True
            elif family == "select_charge_targets":
                choices = [
                    option["option_id"]
                    for option in public["options"]
                    if isinstance(option["payload"], dict)
                    and option["payload"]["target_ids"] == [RANGED_ID]
                ]
                choice = choices[0] if choices else "decline_charge_targets"
            elif family == "select_dice_reroll" or family == "resolve_reaction_window":
                choice = "decline"
            elif family == "use_stratagem":
                choice = "decline_stratagem_window"
            elif family == "submit_stratagem_target_proposal":
                proposal = stratagem_decline_payload()
            elif family == "submit_movement_proposal":
                if attempt == 8:
                    outcome = "frozen_path_attempts_exhausted"
                    break
                movement = MovementProposalRequest.from_decision_request_payload(public["payload"])
                assert movement.unit_instance_id == THREAT_ID
                assert state.charge_phase_state is not None
                distance = state.charge_phase_state.move_pending_distance_state()
                assert distance is not None
                budget = distance.roll_result.movement_budget.maximum_distance_inches
                witness = path_for_template(procedure["templates"][attempt], budget)
                proposal = validate_json_value(
                    ChargeMoveProposal(
                        proposal_request_id=movement.request_id,
                        proposal_kind=movement.proposal_kind,
                        unit_instance_id=THREAT_ID,
                        movement_phase_action="charge_move",
                        movement_mode=MovementMode.CHARGE,
                        charge_target_unit_instance_ids=(RANGED_ID,),
                        witness=witness,
                    ).to_payload()
                )
                attempt += 1
            elif family == "select_catalog_unit_move_completed_mortal_wounds_target":
                choices = [
                    option["option_id"]
                    for option in public["options"]
                    if isinstance(option["payload"], dict)
                    and isinstance(
                        option["payload"].get("selected_unit_move_completed_mortal_wounds_target"),
                        dict,
                    )
                    and cast(
                        dict[str, JsonValue],
                        option["payload"]["selected_unit_move_completed_mortal_wounds_target"],
                    )["target_unit_instance_id"]
                    == RANGED_ID
                ]
                assert len(choices) == 1, "Mandatory native ability must target E."
                choice = choices[0]
            elif family == "select_mortal_wound_model":
                choice = min(option["option_id"] for option in public["options"])
            else:
                outcome = f"unhandled_native_choice:{family}"
                break
            if proposal is None:
                choice = next(
                    option["option_id"]
                    for option in public["options"]
                    if option["option_id"] == choice
                )
            result_id = f"native-charge-{session.decision_record_count():04d}"
            # Preserve the exact pending state and attempted path before expensive validation.
            write_json(output / f"{alternative}-pending.json", session.to_persistence_payload())
            entry: dict[str, JsonValue] = {
                "request": validate_json_value(request.to_payload()),
                "issued_viewer_request": validate_json_value(public),
                "option": choice,
                "proposal": proposal,
            }
            journal.append(entry)
            write_json(output / f"{alternative}-journal.json", journal)
            viewer = ViewerContext.for_player(request.actor_id)
            choice_started = time.monotonic()
            if proposal is None:
                status = session.submit_viewer_option(
                    viewer=viewer,
                    request_id=public["request_id"],
                    option_id=choice,
                    result_id=result_id,
                )
            else:
                status = session.submit_viewer_parameterized_payload(
                    viewer=viewer,
                    request_id=public["request_id"],
                    payload=proposal,
                    result_id=result_id,
                )
            entry["status"] = validate_json_value(status.to_payload())
            entry["elapsed_seconds"] = time.monotonic() - choice_started
            write_json(output / f"{alternative}-journal.json", journal)
            write_json(
                output / f"{alternative}-last-returned.json", session.to_persistence_payload()
            )
            print("CHOICE", alternative, family, choice, status.status_kind.value, flush=True)
            assert status.status_kind is not LifecycleStatusKind.UNSUPPORTED, status
            if status.status_kind is LifecycleStatusKind.INVALID:
                if family != "submit_movement_proposal":
                    outcome = "rejected_native_choice"
                    break
                continue
            advanced = session.advance_until_decision_or_terminal()
            assert advanced.status_kind not in (
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            ), advanced
        else:
            outcome = "frozen_decision_limit"
    finally:
        write_json(output / f"{alternative}-checkpoint.json", session.to_persistence_payload())
        write_json(
            output / f"{alternative}-live-viewers.json",
            {
                player_id: {
                    "view": session.view(viewer_player_id=player_id),
                    "events": session.events_since(EventStreamCursor(), viewer_player_id=player_id),
                }
                for player_id in ("player-a", "player-b")
            },
        )
        write_json(
            output / f"{alternative}-replay.json",
            session.replay_artifact(artifact_id=f"native-charge-{alternative}"),
        )
        write_json(
            output / f"{alternative}-response.json",
            {
                "procedure_sha256": expected,
                "outcome": outcome,
                "elapsed_seconds": time.monotonic() - started,
                "limit_seconds": 300,
                "attempts": attempt,
                "initial_records": initial_records,
                "response_events_including_RNG_and_native_abilities": [
                    event.to_payload()
                    for event in session.lifecycle.decision_controller.event_log.records_since(
                        initial_events
                    )
                ],
                "after": snapshot(session),
            },
        )


def qualify_saved(output: Path, alternative: NativeAlternative) -> None:
    started = time.monotonic()
    checkpoint = json.loads((output / f"{alternative}-checkpoint.json").read_text(encoding="utf-8"))
    session = LocalGameSession.from_persistence_payload(checkpoint)
    assert session.to_persistence_payload() == checkpoint
    original_live = json.loads(
        (output / f"{alternative}-live-viewers.json").read_text(encoding="utf-8")
    )
    for player_id in ("player-a", "player-b"):
        assert session.view(viewer_player_id=player_id) == original_live[player_id]["view"]
        assert (
            session.events_since(EventStreamCursor(), viewer_player_id=player_id)
            == original_live[player_id]["events"]
        )
    proof = qualify_native_checkpoint(
        session,
        artifact_id=f"native-charge-{alternative}",
        started_at=started,
        restored_checkpoint=checkpoint,
    )
    assert isinstance(proof, dict)
    proof["both_viewers_and_events_equal"] = True
    write_json(output / f"{alternative}-qualification.json", proof)
    print("QUALIFIED", alternative, json.dumps(proof), flush=True)
    assert proof["within_declared_limit"] is True


def publish_response_phase(
    output: Path, alternative: NativeAlternative, *, phase: str, started: float
) -> None:
    target = output / f"{alternative}-worker-phase.json"
    temporary = target.with_suffix(".tmp")
    write_json(temporary, {"phase": phase, "started": started})
    temporary.replace(target)


def supervised(output: Path, alternative: NativeAlternative, *, qualification: bool) -> None:
    limit = 900
    label = "qualification" if qualification else "response"
    started = time.monotonic()
    phase_started = started
    phase = "qualification" if qualification else "restoration"
    phase_path = output / f"{alternative}-worker-phase.json"
    assert qualification or not phase_path.exists(), "Never retry or overwrite a campaign."
    process = multiprocessing.get_context("spawn").Process(
        target=qualify_saved if qualification else respond, args=(output, alternative)
    )
    process.start()
    while process.is_alive():
        if not qualification and phase_path.exists():
            current = json.loads(phase_path.read_text(encoding="utf-8"))
            phase = current["phase"]
            assert phase in ("restoration", "response")
            phase_started = current["started"] if phase == "response" else started
            limit = 300 if phase == "response" else 900
        if time.monotonic() - phase_started > limit:
            break
        process.join(timeout=0.25)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
    phase_elapsed = time.monotonic() - phase_started
    within_limit = phase_elapsed <= limit
    write_json(
        output / f"{alternative}-{label}-supervision.json",
        {
            "limit_seconds": limit,
            "last_phase": phase,
            "last_phase_elapsed_seconds": phase_elapsed,
            "within_declared_limit": within_limit,
            "elapsed_seconds": time.monotonic() - started,
            "timed_out": timed_out,
            "exit_code": process.exitcode,
            "clock": (
                "strict input restoration separately <=900; native response <=300 "
                "including durable output; complete checkpoint qualification separately <=900"
            ),
            "timeout_meaning": (
                "unresolved; last pending/returned states are diagnostics, not a completed charge"
            ),
        },
    )
    assert not timed_out, f"Native {label} remained unresolved at its frozen cap."
    assert process.exitcode == 0, f"Native {label} worker failed; preserve its diagnostics."
    assert within_limit, f"Native {label} completed late; retain the result without approval."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--common", type=Path)
    parser.add_argument("--alternative", choices=ALTERNATIVES)
    parser.add_argument("--qualify-saved", action="store_true")
    args = parser.parse_args()
    if args.alternative is None:
        assert args.common is not None
        prepare(args.common, args.output)
    else:
        assert args.common is None
        supervised(args.output, args.alternative, qualification=args.qualify_saved)


if __name__ == "__main__":
    main()
