"""Frozen operator charge experiment on the native round-four alternatives.

Prepare both inputs and the procedure before running either response. This is a
finite path experiment, not a complete charge generator or a tactical policy.
"""

import argparse
import hashlib
import json
import multiprocessing
import shutil
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
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.base import CircularBase, OvalBase
from warhammer40k_core.geometry.pathing import ModelPath, PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload
from warhammer40k_core.geometry.volume import Model

ALTERNATIVES: tuple[NativeAlternative, ...] = ("preserve", "screen")
# Preserve the original front-rank-first movement order.
MODEL_ORDER = (4, 5, 2, 3, 0, 1)


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
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    return formation_templates(scenario)


def formation_templates(scenario: BattlefieldScenario) -> list[JsonValue]:
    """Two jointly packed formations for this retained native six-model fixture.

    This is a finite operator recipe. It preserves the actual bases/facings and
    constructs every endpoint before applying a movement budget. A whole template
    is admitted or excluded; individual converging paths are never clipped.
    """
    models = tuple(
        sorted(
            physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=THREAT_ID),
            key=lambda model: model.model_id,
        )
    )
    targets = physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=RANGED_ID)
    assert len(targets) == 1
    return formation_templates_for_models(models, targets[0])


def formation_templates_for_models(models: tuple[Model, ...], target: Model) -> list[JsonValue]:
    """Construct the complete packed endpoint sets from the real role geometry."""
    assert len(models) == 6
    assert isinstance(target.base, CircularBase)
    assert all(isinstance(model.base, OvalBase) for model in models)
    base = models[0].base
    assert isinstance(base, OvalBase)
    assert all(model.base == base and model.pose.facing.degrees == 90 for model in models)
    width, length = base.width, base.length
    x, y = target.pose.position.x, target.pose.position.y

    def boundary(index: int, px: float, gap: float, *, upper: bool = False) -> Pose:
        model = models[index]

        def pose(py: float) -> Pose:
            return Pose.at(px, py, model.pose.position.z, facing_degrees=90)

        low, high = y - 12, y
        assert replace(model, pose=pose(high)).range_to(target) < gap
        for _ in range(60):
            mid = (low + high) / 2
            if replace(model, pose=pose(mid)).range_to(target) > gap:
                low = mid
            else:
                high = mid
        return pose(2 * y - high if upper else high)

    # Translate each complete column by its leader's displacement. This keeps
    # rank spacing and explicit lateral clearance instead of collapsing ranks.
    leaders = (
        boundary(4, x + 0.4 * width, 0.249999),
        boundary(5, x + 0.4 * width + width + 0.05, 0.999999),
    )
    columns: dict[int, Pose] = {}
    for indices, leader in zip(((0, 2, 4), (1, 3, 5)), leaders, strict=True):
        start = models[indices[-1]].pose.position
        for index in indices:
            p = models[index].pose.position
            columns[index] = Pose.at(
                p.x + leader.position.x - start.x,
                p.y + leader.position.y - start.y,
                p.z,
                facing_degrees=90,
            )
    arc = {
        4: boundary(4, x - width + 0.05, 0.249999),
        5: boundary(5, x + target.base.radius + width / 2 + 0.25 - 0.01, 0.249999, upper=True),
        2: boundary(2, x + 0.1 * width, 0.249999),
        3: boundary(3, x + 1.4 * width, 0.999999),
        0: Pose.at(
            x - 0.35 * width, y - (2 * length + 0.95), models[0].pose.position.z, facing_degrees=90
        ),
        1: Pose.at(
            x + 1.2 * width, y - (2 * length + 0.4), models[1].pose.position.z, facing_degrees=90
        ),
    }
    templates: list[JsonValue] = []
    for name, goals in (("columns", columns), ("arc", arc)):
        ends = [replace(model, pose=goals[i]) for i, model in enumerate(models)]
        assert not any(a.base_overlaps(b) for i, a in enumerate(ends) for b in ends[i + 1 :])
        templates.append(
            validate_json_value(
                {
                    "formation": name,
                    "endpoints": [
                        {
                            "model_id": models[i].model_id,
                            "start": models[i].pose.to_payload(),
                            "end": goals[i].to_payload(),
                            "range_before": models[i].range_to(target),
                            "range_after": ends[i].range_to(target),
                        }
                        for i in MODEL_ORDER
                    ],
                }
            )
        )
    return templates


def template_fits(
    template: JsonValue, budget: float, *, preferred: float, engagement: float
) -> bool:
    """Conservative geometric admission; full native validation remains required."""
    assert isinstance(template, dict)
    assert isinstance(template["endpoints"], list)
    for row in template["endpoints"]:
        assert isinstance(row, dict)
        start = Pose.from_payload(cast(PosePayload, row["start"]))
        end = Pose.from_payload(cast(PosePayload, row["end"]))
        if start.distance_3d_to(end) > budget + 1e-8:
            return False
        before, after = (
            float(cast(float, row["range_before"])),
            float(cast(float, row["range_after"])),
        )
        if after >= before:
            return False
        # If the simple distance bound permits a required goal, this recipe
        # requires satisfying it directly, avoiding an invented impossibility claim.
        if any(
            before - goal <= budget + 1e-8 and after > goal + 1e-8
            for goal in (preferred, engagement)
        ):
            return False
    return True


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
    assert template is not None
    assert common.lifecycle.config is not None
    freeze_procedure(
        output,
        inputs,
        template,
        common.lifecycle.config.ruleset_descriptor,
        provenance={"common_content_hash": checkpoint["content_hash"]},
    )


def prepare_repair(previous: Path, output: Path) -> None:
    """Freeze a repair of qualified partial histories; retain all rolls/rejections."""
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "procedure.json").exists(), "Never overwrite a frozen campaign."
    inputs: dict[str, JsonValue] = {}
    template = None
    ruleset = None
    for alternative in ALTERNATIVES:
        source = previous / f"{alternative}-checkpoint.json"
        checkpoint = json.loads(source.read_text(encoding="utf-8"))
        proof = json.loads(
            (previous / f"{alternative}-qualification.json").read_text(encoding="utf-8")
        )
        assert proof["checkpoint_hash"] == checkpoint["content_hash"]
        assert proof["strict_JSON_save_load_equal"]
        assert proof["replay"]["status"] == "reproduced"
        before = json.loads(
            (previous / f"{alternative}-response.json").read_text(encoding="utf-8")
        )["after"]
        assert before["phase"] == "charge"
        state = checkpoint["lifecycle"]["state"]
        assert state["charge_phase_state"]["active_selection"]["unit_instance_id"] == THREAT_ID
        scenario = BattlefieldScenario.from_payload(
            {
                "armies": state["army_definitions"],
                "battlefield_state": state["battlefield_state"],
                "present_destroyed_model_ids": [],
            }
        )
        current = formation_templates(scenario)
        if template is None:
            template = current
        else:
            assert current == template
        current_ruleset = RulesetDescriptor.from_payload(
            checkpoint["lifecycle"]["config"]["ruleset_descriptor"]
        )
        if ruleset is None:
            ruleset = current_ruleset
        else:
            assert current_ruleset == ruleset
        shutil.copyfile(source, output / f"{alternative}-input.json")
        inputs[alternative] = validate_json_value(
            {
                "content_hash": checkpoint["content_hash"],
                "before": before,
                "inherited_partial_history_qualification": proof,
                "input_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    assert template is not None
    assert ruleset is not None
    freeze_procedure(
        output,
        inputs,
        template,
        ruleset,
        provenance={
            "continuation": (
                "authorized repair after eight retained rejected paths; keep existing natural rolls"
            ),
            "retained_procedure": json.loads(
                (previous / "procedure-sha256.json").read_text(encoding="utf-8")
            ),
        },
    )


def freeze_procedure(
    output: Path,
    inputs: dict[str, JsonValue],
    templates: list[JsonValue],
    ruleset: RulesetDescriptor,
    *,
    provenance: JsonValue,
) -> None:
    procedure: JsonValue = {
        "schema": "native-bloodcrusher-E-charge-v4",
        "producer": native_producer(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "provenance": provenance,
        "inputs": inputs,
        "templates": templates,
        "preferred_distance_inches": ruleset.charge_policy.preferred_target_distance_inches,
        "engagement_distance_inches": ruleset.engagement_policy.horizontal_inches,
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
                "whole disjoint formations only; exclude budget/goal-infeasible templates; "
                "complete straight paths in frozen model order, never independently clip"
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
        assert start.distance_3d_to(goal) <= budget + 1e-8, "Whole formation exceeds charge budget."
        paths.append((row["model_id"], (start, goal)))
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
    state = session.lifecycle.state
    assert state is not None
    assert state.charge_phase_state is not None
    selected = THREAT_ID in state.charge_phase_state.selected_unit_ids
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
                movement = MovementProposalRequest.from_decision_request_payload(public["payload"])
                assert movement.unit_instance_id == THREAT_ID
                assert state.charge_phase_state is not None
                distance = state.charge_phase_state.move_pending_distance_state()
                assert distance is not None
                budget = distance.roll_result.movement_budget.maximum_distance_inches
                templates = [
                    t
                    for t in procedure["templates"]
                    if template_fits(
                        t,
                        budget,
                        preferred=procedure["preferred_distance_inches"],
                        engagement=procedure["engagement_distance_inches"],
                    )
                ]
                if attempt >= min(8, len(templates)):
                    outcome = "frozen_whole_formation_templates_exhausted"
                    break
                witness = path_for_template(templates[attempt], budget)
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
    parser.add_argument("--repair-from", type=Path)
    parser.add_argument("--alternative", choices=ALTERNATIVES)
    parser.add_argument("--qualify-saved", action="store_true")
    args = parser.parse_args()
    if args.alternative is None:
        assert (args.common is None) != (args.repair_from is None)
        if args.repair_from is not None:
            prepare_repair(args.repair_from, args.output)
        else:
            prepare(args.common, args.output)
    else:
        assert args.common is None
        assert args.repair_from is None
        supervised(args.output, args.alternative, qualification=args.qualify_saved)


if __name__ == "__main__":
    main()
