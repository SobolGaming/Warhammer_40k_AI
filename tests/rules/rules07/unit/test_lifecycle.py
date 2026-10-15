from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase9b_lifecycle import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlePhase,
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    BattleRoundFlow,
    ChargePhaseState,
    ChargeRollRequest,
    ChargeRollResult,
    ChargingUnitSelection,
    CommandPhaseHandler,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    DiceRollManager,
    FightPhaseState,
    FightsFirstRegistry,
    GameConfig,
    GameConfigPayload,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    GameStatePayload,
    GeometrySourceKind,
    HeightSourceKind,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
    ModelProfileSelection,
    MovementPhaseState,
    ObjectiveControlTiming,
    PlaceholderPhaseHandler,
    RulesetDescriptor,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupCompletionGate,
    SetupSequenceDescriptor,
    SetupStep,
    SetupStepKind,
    ShootingPhaseState,
    UnitMusterSelection,
    WargearSelection,
    _advance_to_battle,
    _advance_to_secondary_mission_step,
    _army_muster_request,
    _army_muster_requests,
    _battle_flow,
    _battle_lifecycle_for_consistency,
    _battle_state,
    _choose_secondaries,
    _complete_setup_through_gate,
    _config,
    _decline_stratagem_window_if_pending,
    _descriptor_with_sequences,
    _lifecycle_is_in_battle,
    _mission_setup,
    _pending_request,
    _phase_state_consistency_payload,
    _public_secondary_choices,
    _request_payload,
    _start_lifecycle,
    _state,
    _state_battle_phase,
    _submit_pending,
    accepted_model_geometry,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    drain_pending_secondary_mission_setup,
    ensure_army_mustered_events_for_fixture,
    game_lifecycle_stage_from_token,
    inspect,
    json,
    lifecycle_status_kind_from_token,
    muster_army,
    pytest,
    replace,
    seed_completed_fight_phase,
    submit_all_deployments_if_pending,
)


def test_phase_wrap_switches_active_player() -> None:
    state = _battle_state()
    flow = _battle_flow()

    for _ in range(5):
        if state.current_battle_phase is BattlePhase.FIGHT:
            seed_completed_fight_phase(state)
        flow.advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.battle_round == 1
    assert state.active_player_id == "player-b"
    assert state.current_battle_phase is BattlePhase.COMMAND


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BattlePhaseKind"]
__all__ += ["BattlePhaseSequenceDescriptor", "BattleRoundFlow", "ChargePhaseState"]
__all__ += ["ChargeRollRequest", "ChargeRollResult", "ChargingUnitSelection"]
__all__ += ["DECLINE_STRATAGEM_WINDOW_OPTION_ID", "CommandPhaseHandler"]
__all__ += ["DEFAULT_MAX_LIFECYCLE_TRANSITIONS", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "DiceRollManager"]
__all__ += ["FightPhaseState", "FightsFirstRegistry", "GameConfig", "GameConfigPayload"]
__all__ += ["GameLifecycleError", "GameLifecyclePayload", "GameLifecycleStage", "GameState"]
__all__ += ["GameStatePayload", "GeometrySourceKind", "HeightSourceKind", "JsonValue"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup"]
__all__ += ["ModelGeometryCatalogRecord", "ModelGeometryCatalogRecordPayload"]
__all__ += ["ModelProfileSelection", "MovementPhaseState", "ObjectiveControlTiming"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "PlaceholderPhaseHandler", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupCompletionGate"]
__all__ += ["SetupSequenceDescriptor", "SetupStep", "SetupStepKind", "ShootingPhaseState"]
__all__ += ["TACTICAL_SECONDARY_DRAW_DECISION_TYPE", "UnitMusterSelection", "WargearSelection"]
__all__ += ["_advance_to_battle", "_advance_to_secondary_mission_step", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_battle_lifecycle_for_consistency", "_choose_secondaries"]
__all__ += ["_complete_setup_through_gate", "_config", "_decline_stratagem_window_if_pending"]
__all__ += ["_descriptor_with_sequences", "_lifecycle_is_in_battle", "_mission_setup"]
__all__ += ["_pending_request", "_phase_state_consistency_payload", "_public_secondary_choices"]
__all__ += ["_request_payload", "_start_lifecycle", "_state", "_state_battle_phase"]
__all__ += ["_submit_pending", "accepted_model_geometry", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["drain_pending_secondary_mission_setup", "ensure_army_mustered_events_for_fixture"]
__all__ += ["game_lifecycle_stage_from_token", "inspect", "json"]
__all__ += ["lifecycle_status_kind_from_token", "muster_army", "pytest", "replace"]
__all__ += ["submit_all_deployments_if_pending"]
