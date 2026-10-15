from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase16e_setup_completion import (
    SECONDARY_MISSION_DECISION_TYPE,
    ArmyCatalog,
    ArmyMusterRequest,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
    DedicatedTransportSetupConsequence,
    DetachmentSelection,
    DiceExpression,
    DiceRollManager,
    DiceRollSpec,
    EventLog,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelPlacement,
    ModelProfileSelection,
    Path,
    RulesetDescriptor,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupCompletionGate,
    SetupCompletionViolationCode,
    SetupLegalityReport,
    SetupStep,
    TransportCapacityProfile,
    TransportCargoState,
    UnitMusterSelection,
    UnitPlacement,
    _advance_setup_state_to_step,
    _advance_to_first_deployment_selection,
    _army_muster_request,
    _army_muster_requests,
    _cargo_dedicated_transport_config,
    _config,
    _decision_request,
    _dedicated_transport_state_without_transport_reconciliation,
    _empty_dedicated_transport_config,
    _mission_setup,
    _payload_object,
    _place_transport,
    _pre_battle_gate_ready_state,
    _ruleset,
    _single_event_payload,
    _state_at_final_setup_step_without_deployments,
    _submit_result,
    _transport_cargo_state,
    _transport_roster_request,
    _unit_selection,
    _violation_codes,
    chapter_approved_2026_27_mission_pack,
    create_empty_deployment_battlefield_state,
    default_deployment_pose,
    json,
    muster_army,
    pytest,
    submit_all_deployments_if_pending,
)
from tests.shared.repository_root import REPOSITORY_ROOT


def test_phase16e_gate_rejects_incomplete_setup_with_reaction_queue() -> None:
    config = _config()
    state = GameState.from_config(config)
    status = SetupCompletionGate().invalid_status_if_not_ready(
        state=state,
        decisions=DecisionController(),
        config=config,
        reaction_frame_count=2,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    report_payload = status.payload["setup_legality_report"]
    assert isinstance(report_payload, dict)
    violations = report_payload["violations"]
    assert isinstance(violations, list)
    codes = {
        violation["violation_code"]
        for violation in violations
        if isinstance(violation, dict) and isinstance(violation["violation_code"], str)
    }
    assert SetupCompletionViolationCode.SETUP_SEQUENCE_INCOMPLETE.value in codes
    assert SetupCompletionViolationCode.REACTION_QUEUE_NOT_DRAINED.value in codes
    assert SetupCompletionViolationCode.MISSING_ARMY.value in codes
    assert SetupCompletionViolationCode.UNRESOLVED_SECONDARY_MISSIONS.value in codes
    assert SetupCompletionViolationCode.MISSING_BATTLEFIELD.value in codes
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_empty_dedicated_transport_manifest_without_consequence() -> None:
    config = _empty_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    assert SetupCompletionViolationCode.ILLEGAL_DEDICATED_TRANSPORT_SETUP.value in (
        _violation_codes(report)
    )
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == [
        "dedicated_transport_setup_consequences",
        "battlefield_state",
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_non_empty_dedicated_transport_manifest_without_cargo() -> None:
    config = _cargo_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == ["transport_cargo_states"]
    assert transport_violations[0].detail == {
        "source_id": "manifest:transport-unit",
        "expected_embarked_unit_instance_ids": ["army-alpha:passenger-unit"],
    }
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_lifecycle_replay_round_trip_preserves_battle_start_record() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-replay-deploy",
    )
    payload = lifecycle.to_payload()

    restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    )

    assert restored.to_payload() == payload
    assert _single_event_payload(restored, "battle_started") == _single_event_payload(
        lifecycle,
        "battle_started",
    )


def test_phase16e_setup_gate_paths_do_not_call_deterministic_placement_bridge() -> None:
    root = REPOSITORY_ROOT
    checked_paths = (
        root / "src" / "warhammer40k_core" / "engine" / "setup_completion.py",
        root / "src" / "warhammer40k_core" / "engine" / "setup_flow.py",
        root / "src" / "warhammer40k_core" / "engine" / "lifecycle.py",
    )

    offenders = [
        str(path.relative_to(root))
        for path in checked_paths
        if "create_deterministic_battlefield_scenario" in path.read_text(encoding="utf-8")
        or "phase10a_deterministic_bridge" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_phase16e_setup_completion_events_do_not_shift_later_rng_history() -> None:
    setup_step_payload: dict[str, JsonValue] = {
        "game_id": "phase16e-rng-game",
        "completed_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
    }
    base_log = EventLog()
    base_log.append("setup_step_completed", setup_step_payload)
    augmented_log = EventLog()
    augmented_log.append("setup_completion_gate_passed", {"game_id": "phase16e-rng-game"})
    augmented_log.append("battle_started", {"game_id": "phase16e-rng-game"})
    augmented_log.append("setup_step_completed", setup_step_payload)
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=5, sides=6),
        reason="Phase 16E RNG neutrality probe",
        roll_type="phase16e_rng_neutrality_probe",
        actor_id="phase16e-rng",
    )

    base_roll = DiceRollManager("phase16e-rng-seed", event_log=base_log).roll(spec)
    augmented_roll = DiceRollManager("phase16e-rng-seed", event_log=augmented_log).roll(spec)

    assert augmented_roll.current_values == base_roll.current_values
    assert augmented_roll.current_total == base_roll.current_total


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "DecisionOption", "DecisionRequest"]
__all__ += ["DecisionResult", "DedicatedTransportCapacityProfile", "DedicatedTransportManifest"]
__all__ += ["DedicatedTransportSetupConsequence", "DetachmentSelection", "GameConfig"]
__all__ += ["GameLifecycleError", "LifecycleStatus", "MissionSetup", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "Path", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SetupLegalityReport", "TransportCapacityProfile", "TransportCargoState"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "_advance_setup_state_to_step"]
__all__ += ["_army_muster_request", "_army_muster_requests", "_decision_request"]
__all__ += ["_mission_setup", "_payload_object", "_place_transport"]
__all__ += ["_pre_battle_gate_ready_state", "_ruleset"]
__all__ += ["_state_at_final_setup_step_without_deployments", "_submit_result"]
__all__ += ["_transport_cargo_state", "_transport_roster_request", "_unit_selection"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["default_deployment_pose", "muster_army", "pytest"]
