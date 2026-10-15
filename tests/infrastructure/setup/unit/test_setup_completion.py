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


def test_phase16e_full_setup_enters_battle_through_completion_gate() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()

    follow_up = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-deploy",
    )

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is not None
    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
        LifecycleStatusKind.TERMINAL,
    }

    battle_started = _single_event_payload(lifecycle, "battle_started")
    legality_report = _payload_object(battle_started, "setup_legality_report")
    pre_checkpoint = _payload_object(battle_started, "pre_battle_checkpoint")
    post_checkpoint = _payload_object(battle_started, "post_battle_start_checkpoint")

    assert battle_started["record_id"] == "battle-start:phase16e-game:round-01"
    assert battle_started["completed_setup_step"] == SetupStep.RESOLVE_PREBATTLE_ACTIONS.value
    assert battle_started["battle_round"] == 1
    assert battle_started["active_player_id"] == "player-a"
    assert battle_started["first_battle_phase"] == "command"
    assert legality_report["is_legal"] is True
    assert legality_report["violations"] == []
    assert pre_checkpoint["stage"] == GameLifecycleStage.SETUP.value
    assert post_checkpoint["stage"] == GameLifecycleStage.BATTLE.value

    encoded = json.dumps(lifecycle.to_payload(), sort_keys=True)
    assert "phase10a_deterministic_bridge" not in encoded
    assert " object at 0x" not in encoded
    assert "<" not in encoded


def test_phase16e_gate_rejects_direct_setup_step_bypass_with_unplaced_units() -> None:
    config = _config()
    state = _state_at_final_setup_step_without_deployments(config)
    gate = SetupCompletionGate()

    report = gate.evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    assert SetupCompletionViolationCode.UNRESOLVED_DEPLOYMENT.value in _violation_codes(report)
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_game_state_final_setup_step_requires_completion_gate() -> None:
    state = _state_at_final_setup_step_without_deployments(_config())

    with pytest.raises(
        GameLifecycleError,
        match="Final setup step completion requires the setup completion gate",
    ):
        state.complete_current_setup_step()

    assert state.stage is GameLifecycleStage.SETUP
    assert state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    assert state.battle_round == 0


def test_phase16e_gate_rejects_pending_setup_decisions_without_queue_pop() -> None:
    config = _config()
    state = _pre_battle_gate_ready_state()
    decisions = DecisionController()
    pending_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type="phase16e_pending_setup_probe",
        actor_id="player-a",
        payload={"probe": "phase16e"},
        options=(
            DecisionOption(
                option_id="phase16e-probe-option",
                label="Phase 16E Probe Option",
                payload={"probe": "phase16e"},
            ),
        ),
    )
    decisions.request_decision(pending_request)

    status = SetupCompletionGate().invalid_status_if_not_ready(
        state=state,
        decisions=decisions,
        config=config,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    report_payload = status.payload["setup_legality_report"]
    assert isinstance(report_payload, dict)
    violations = report_payload["violations"]
    assert isinstance(violations, list)
    assert any(
        isinstance(violation, dict)
        and violation["violation_code"] == SetupCompletionViolationCode.PENDING_DECISION_QUEUE.value
        for violation in violations
    )
    assert decisions.queue.peek_next() == pending_request
    assert state.stage is GameLifecycleStage.SETUP


def test_phase16e_gate_rejects_empty_manifest_with_cargo_or_deployment() -> None:
    config = _empty_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)
    state.transport_cargo_states.append(
        _transport_cargo_state(
            transport_unit_instance_id="army-alpha:transport-unit",
            embarked_unit_instance_ids=(),
        )
    )
    _place_transport(state)

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
    assert [violation.field for violation in transport_violations] == [
        "dedicated_transport_setup_consequences",
        "transport_cargo_states",
        "battlefield_state",
        "battlefield_state",
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_non_empty_manifest_with_mismatched_cargo_or_consequence() -> None:
    config = _cargo_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)
    state.transport_cargo_states.append(
        _transport_cargo_state(
            transport_unit_instance_id="army-alpha:transport-unit",
            embarked_unit_instance_ids=(),
        )
    )
    state.dedicated_transport_setup_consequences.append(
        DedicatedTransportSetupConsequence.empty_dedicated_transport(
            player_id="player-a",
            transport_unit_instance_id="army-alpha:transport-unit",
            source_id="manifest:transport-unit",
        )
    )

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
    assert [violation.field for violation in transport_violations] == [
        "transport_cargo_states",
        "dedicated_transport_setup_consequences",
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "DecisionResult"]
__all__ += ["DedicatedTransportCapacityProfile", "DedicatedTransportManifest"]
__all__ += ["DetachmentSelection", "DiceExpression", "DiceRollManager", "DiceRollSpec"]
__all__ += ["EventLog", "GameConfig", "GameLifecycle", "GameLifecyclePayload", "GameState"]
__all__ += ["JsonValue", "LifecycleStatus", "MissionSetup", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "Path", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SetupLegalityReport", "TransportCapacityProfile", "TransportCargoState"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "_advance_setup_state_to_step"]
__all__ += ["_army_muster_request", "_army_muster_requests", "_decision_request"]
__all__ += ["_mission_setup", "_ruleset", "_submit_result", "_transport_roster_request"]
__all__ += ["_unit_selection", "cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_empty_deployment_battlefield_state", "default_deployment_pose", "muster_army"]
