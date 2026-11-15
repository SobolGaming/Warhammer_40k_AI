"""Operator-only native branch construction, threat queries and exact replay checks."""

import hashlib
import json
import multiprocessing
import time
from pathlib import Path
from typing import cast

from tests.support.cavalcade_native_approach import (
    NativeAlternative,
    at_screen_choice,
    native_producer,
    submit_approach_choice,
)
from tests.support.cavalcade_native_prefix import RANGED_ID, SCREEN_ID, THREAT_ID

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_targets import (
    charge_target_candidates,
    closest_unit_distance_inches,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle_for_armies
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting_eligibility import (
    shooting_unit_can_select_to_shoot,
)
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.shooting_targets import (
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_terrain_visibility import shooting_terrain_areas_for_state


def continue_native_branch(
    session: LocalGameSession, *, alternative: NativeAlternative, started_at: float
) -> None:
    """Caller starts the 300-second clock before forking the common checkpoint."""
    assert at_screen_choice(session)
    for _ in range(100):
        assert time.monotonic() - started_at < 300, "Native branch construction time limit."
        state = session.lifecycle.state
        assert state is not None
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        if (
            state.battle_round == 4
            and state.active_player_id == "player-b"
            and state.current_battle_phase is BattlePhase.CHARGE
            and request.decision_type == "select_charging_unit"
        ):
            return
        status = submit_approach_choice(session, recipe="revised-v6", alternative=alternative)
        assert status.status_kind not in (
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        ), status
        advanced = session.advance_until_decision_or_terminal()
        assert advanced.status_kind not in (
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        ), advanced
    raise AssertionError("Native branch decision limit.")


def native_interaction_audit(session: LocalGameSession) -> JsonValue:
    """Read real equipment, physical range/LOS and live target restrictions, without rolls."""
    before = session.to_persistence_payload()
    assert isinstance(before, dict)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.current_battle_phase is not None
    config = session.lifecycle.config
    units = {unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units}
    ranged = units[RANGED_ID]
    scenario = battlefield_scenario_for_state(state=state)
    bundle = build_runtime_content_bundle_for_armies(
        config=config, armies=tuple(state.army_definitions)
    )
    profiles = tuple(
        profile
        for gear in config.army_catalog.wargear
        if gear.wargear_id in ranged.own_models[0].wargear_ids
        for profile in gear.weapon_profiles
        if profile.range_profile.distance_inches is not None
    )
    charge_audit: JsonValue = {"status": "not_evaluated_outside_B_charge_phase"}
    if state.current_battle_phase is BattlePhase.CHARGE and state.active_player_id == "player-b":
        assert state.charge_phase_state is not None
        restrictions = bundle.charge_target_restriction_hook_registry
        charge_audit = validate_json_value(
            {
                "ineligible_reason": charge_unit_ineligibility_reason(
                    state=state,
                    unit_instance_id=THREAT_ID,
                    ruleset_descriptor=config.ruleset_descriptor,
                    charge_state=state.charge_phase_state,
                    ignore_already_selected=False,
                    charge_target_restriction_hooks=restrictions,
                ),
                "S_and_E_target_candidates": [
                    candidate.to_payload()
                    for candidate in charge_target_candidates(
                        state=state,
                        unit_instance_id=THREAT_ID,
                        ruleset_descriptor=config.ruleset_descriptor,
                        charge_target_restriction_hooks=restrictions,
                    )
                    if candidate.target_unit_instance_id in (SCREEN_ID, RANGED_ID)
                ],
                "roll_path_melee_and_upgrade_outcomes": "not_evaluated",
            }
        )
    raw: dict[str, object] = {
        "checkpoint_hash": before["content_hash"],
        "round": state.battle_round,
        "active_player": state.active_player_id,
        "phase": state.current_battle_phase.value,
        "records": session.decision_record_count(),
        "rosters": [
            {
                "army_id": army.army_id,
                "legal": army.roster_legality_report.is_legal,
                "units": len(army.units),
                "models": sum(len(unit.own_models) for unit in army.units),
            }
            for army in state.army_definitions
        ],
        "roles": {
            unit_id: {
                "models": [
                    {
                        "id": model.model_instance_id,
                        "alive": model.is_alive,
                        "wounds": model.wounds_remaining,
                        "equipment": list(model.wargear_ids),
                    }
                    for model in units[unit_id].own_models
                ],
                "placements": [
                    placement.to_payload()
                    for placement in state.battlefield_state.unit_placement_by_id(
                        unit_id
                    ).model_placements
                ],
                "equipped_profiles": [
                    profile.to_payload()
                    for gear in config.army_catalog.wargear
                    if any(
                        gear.wargear_id in model.wargear_ids for model in units[unit_id].own_models
                    )
                    for profile in gear.weapon_profiles
                ],
            }
            for unit_id in (SCREEN_ID, THREAT_ID, RANGED_ID)
        },
        "E_shooter_state_prerequisite": shooting_unit_can_select_to_shoot(
            state=state, unit=ranged, army_catalog=config.army_catalog, player_id="player-a"
        ),
        "E_B_closest_physical_range_inches": closest_unit_distance_inches(
            scenario=scenario, source_unit_instance_id=RANGED_ID, target_unit_instance_id=THREAT_ID
        ),
        "E_equipped_ranged_profiles": [profile.to_payload() for profile in profiles],
        "E_B_independent_LOS": "separate_bounded_query_after_both_branch_proofs",
        "E_activation": "not_available_on_B_turn; later_A5_not_demonstrated",
        "E_B_full_cover_and_live_shooting_target_query": "not_evaluated",
        "B_charge_audit": charge_audit,
        "limits": (
            "Target eligibility and range/LOS queries are not an accepted attack or charge path."
        ),
    }
    result = validate_json_value(raw)
    assert session.to_persistence_payload() == before
    return result


def qualify_native_checkpoint(
    session: LocalGameSession,
    *,
    artifact_id: str,
    started_at: float | None = None,
    restored_checkpoint: JsonValue | None = None,
) -> JsonValue:
    """Separate 900-second operator qualification; late complete evidence stays visible."""
    started = time.monotonic() if started_at is None else started_at
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = (
        LocalGameSession.from_persistence_payload(checkpoint)
        if restored_checkpoint is None
        else session
    )
    if restored_checkpoint is not None:
        assert checkpoint == restored_checkpoint
    assert restored.to_persistence_payload() == checkpoint
    for player_id in () if restored_checkpoint is not None else ("player-a", "player-b"):
        assert restored.view(viewer_player_id=player_id) == session.view(viewer_player_id=player_id)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=player_id
        ) == session.events_since(EventStreamCursor(), viewer_player_id=player_id)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=artifact_id)).run()
    assert replay.reproduced_exactly
    assert not replay.diagnostics
    assert session.to_persistence_payload() == checkpoint
    elapsed = time.monotonic() - started
    return validate_json_value(
        {
            "checkpoint_hash": checkpoint["content_hash"],
            "strict_JSON_save_load_equal": True,
            "both_viewers_and_events_equal": (
                True if restored_checkpoint is None else "not_compared_to_original_live_process"
            ),
            "replay": replay.to_payload(),
            "elapsed_seconds": elapsed,
            "limit_seconds": 900,
            "within_declared_limit": elapsed <= 900,
        }
    )


def _write_json(path: Path, value: JsonValue) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")


def qualify_native_pair(
    common: LocalGameSession,
    *,
    output: Path,
    common_started: float | None = None,
    restored_checkpoint: JsonValue | None = None,
) -> None:
    """One fixed serial campaign: common and two branches; no attacks or seed search."""
    assert at_screen_choice(common)
    common_checkpoint = common.to_persistence_payload()
    common_records = tuple(common.lifecycle.decision_controller.records)
    common_started = time.monotonic() if common_started is None else common_started
    _write_json(output / "qualification-producer.json", native_producer())

    # Reproduce the fourth rejected route on its own fork. It is not a committed
    # attempt in either final alternative, and its limited verification is explicit.
    rejected = common.fork()
    selected = submit_approach_choice(rejected, recipe="revised-v5", alternative="screen")
    assert selected.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    rejected.advance_until_decision_or_terminal()
    status = submit_approach_choice(rejected, recipe="revised-v5", alternative="screen")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["violation_code"] == "model_cannot_be_placed_at_endpoint"
    _write_json(output / "rejected-S4-checkpoint.json", rejected.to_persistence_payload())
    _write_json(
        output / "rejected-S4-diagnostic.json",
        validate_json_value(
            {
                "status": status.to_payload(),
                "record": rejected.lifecycle.decision_controller.records[-1].to_payload(),
                "strict_save_load_and_ReplayRunner": "not_evaluated_for_this_diagnostic_fork",
            }
        ),
    )
    common_qualification = qualify_native_checkpoint(
        common,
        artifact_id="native-round4-common",
        started_at=common_started,
        restored_checkpoint=restored_checkpoint,
    )
    _write_json(output / "common-qualification.json", common_qualification)
    assert isinstance(common_qualification, dict)
    assert common_qualification["within_declared_limit"] is True
    print("COMMON_QUALIFIED", json.dumps(common_qualification), flush=True)

    branches: list[tuple[NativeAlternative, LocalGameSession]] = []
    alternatives: tuple[NativeAlternative, ...] = ("preserve", "screen")
    for alternative in alternatives:
        started = time.monotonic()
        branch = common.fork()
        try:
            continue_native_branch(branch, alternative=alternative, started_at=started)
        finally:
            _write_json(output / f"{alternative}-checkpoint.json", branch.to_persistence_payload())
        assert (
            tuple(branch.lifecycle.decision_controller.records[: len(common_records)])
            == common_records
        )
        assert common.to_persistence_payload() == common_checkpoint
        elapsed = time.monotonic() - started
        construction = {
            "alternative": alternative,
            "elapsed_seconds": elapsed,
            "limit_seconds": 300,
            "within_declared_limit": elapsed <= 300,
            "clock": (
                "fork validation, ordinary continuation, checkpoint output "
                "and common-prefix equality checks; audits run separately after both proofs"
            ),
            "endpoint": "B round-four Charge before charging-unit selection",
            "later_A_turn": "round five remains; no E activation or attack demonstrated",
        }
        _write_json(output / f"{alternative}-construction.json", validate_json_value(construction))
        print("BRANCH_CONSTRUCTED", json.dumps(construction), flush=True)
        assert elapsed <= 300, "Completed branch construction exceeded its declared time limit."
        qualification = qualify_native_checkpoint(
            branch, artifact_id=f"native-round4-{alternative}"
        )
        _write_json(output / f"{alternative}-qualification.json", qualification)
        assert isinstance(qualification, dict)
        assert qualification["within_declared_limit"] is True
        print("BRANCH_QUALIFIED", alternative, json.dumps(qualification), flush=True)
        branches.append((alternative, branch))
    for alternative, branch in branches:
        audit = native_interaction_audit(branch)
        _write_json(output / f"{alternative}-audit.json", audit)
        bounded_native_visibility(branch, output=output, alternative=alternative)
    assert common.to_persistence_payload() == common_checkpoint


def _visibility_worker(
    lifecycle_payload: GameLifecyclePayload, lifecycle_hash: str, runtime_id: str, output: str
) -> None:
    """Read-only canonical clone of an already strictly qualified endpoint."""
    assert verified_engine_build_identity().build_id == runtime_id
    assert (
        hashlib.sha256(canonical_json(cast(JsonValue, lifecycle_payload)).encode()).hexdigest()
        == lifecycle_hash
    )
    lifecycle = GameLifecycle.from_payload(lifecycle_payload)
    assert lifecycle.to_payload() == lifecycle_payload
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    ranged = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == RANGED_ID
    )
    result = unit_has_line_of_sight_to_target(
        state=state,
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        observing_unit=ranged,
        target_unit_id=THREAT_ID,
        terrain_features=state.battlefield_state.terrain_features,
        terrain_areas=shooting_terrain_areas_for_state(state),
        placed_alive_models_only=True,
    )
    assert lifecycle.to_payload() == lifecycle_payload
    _write_json(
        Path(output),
        {"status": "answered", "E_B_independent_LOS": result, "lifecycle_unchanged": True},
    )


def bounded_native_visibility(
    session: LocalGameSession, *, output: Path, alternative: NativeAlternative
) -> None:
    """At most 300 seconds including child startup, canonical load and the LOS query."""
    started = time.monotonic()
    checkpoint = session.to_persistence_payload()
    result_path = output / f"{alternative}-visibility-result.json"
    assert not result_path.exists()
    assert isinstance(checkpoint, dict)
    lifecycle_payload = session.lifecycle.to_payload()
    assert cast(JsonValue, lifecycle_payload) == checkpoint["lifecycle"]
    runtime_id = verified_engine_build_identity().build_id
    process = multiprocessing.get_context("spawn").Process(
        target=_visibility_worker,
        args=(lifecycle_payload, checkpoint["lifecycle_hash"], runtime_id, str(result_path)),
    )
    process.start()
    while process.is_alive() and time.monotonic() - started < 300:
        process.join(timeout=min(1.0, max(0.0, 300 - (time.monotonic() - started))))
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
    elapsed = time.monotonic() - started
    assert session.to_persistence_payload() == checkpoint
    _write_json(
        output / f"{alternative}-visibility-receipt.json",
        validate_json_value(
            {
                "checkpoint_hash": checkpoint["content_hash"],
                "status": "unresolved_time_limit"
                if timed_out
                else (
                    "answered"
                    if process.exitcode == 0 and result_path.exists()
                    else "worker_failed"
                ),
                "elapsed_seconds": elapsed,
                "limit_seconds": 300,
                "exitcode": process.exitcode,
                "clock": (
                    "startup, read-only canonical lifecycle clone, independent LOS query; "
                    "termination follows cap"
                ),
                "authority": (
                    "already strictly restored/replayed endpoint; child never supplies gameplay"
                ),
                "runtime_build_id": runtime_id,
                "parent_checkpoint_unchanged": True,
            }
        ),
    )
    print(
        "VISIBILITY_FINISHED",
        alternative,
        elapsed,
        "timeout" if timed_out else process.exitcode,
        flush=True,
    )
