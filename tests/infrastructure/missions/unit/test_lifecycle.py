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


def test_select_secondary_missions_emits_secret_requests_for_both_players() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_secondary_mission_step(lifecycle)

    first_status = lifecycle.advance_until_decision_or_terminal()
    assert first_status.decision_request is not None
    assert _request_payload(first_status.decision_request)["secret"] is True
    assert first_status.decision_request.actor_id == "player-a"
    _submit_pending(lifecycle, option_id="tactical", result_number=1)

    second_status = lifecycle.advance_until_decision_or_terminal()
    assert second_status.decision_request is not None
    assert _request_payload(second_status.decision_request)["secret"] is True
    assert second_status.decision_request.actor_id == "player-b"
    _submit_pending(lifecycle, option_id="fixed:assassination:bring_it_down", result_number=2)

    assert lifecycle.state is not None
    assert lifecycle.state.missing_secondary_mission_player_ids() == ()


def test_secondary_mission_public_payload_reveals_after_all_choices() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:bring_it_down:cleanse",
    )
    assert lifecycle.state is not None

    player_a_payload = lifecycle.state.to_public_payload(viewer_player_id="player-a")
    player_b_payload = lifecycle.state.to_public_payload(viewer_player_id="player-b")
    assert {
        "player_id": "player-b",
        "selected": True,
        "hidden": False,
        "mode": "fixed",
        "fixed_mission_ids": ["bring_it_down", "cleanse"],
    } in _public_secondary_choices(player_a_payload)
    assert {
        "player_id": "player-a",
        "selected": True,
        "hidden": False,
        "mode": "tactical",
        "fixed_mission_ids": [],
    } in _public_secondary_choices(player_b_payload)
    assert "bring_it_down" in json.dumps(player_b_payload, sort_keys=True)
    assert "cleanse" in json.dumps(player_b_payload, sort_keys=True)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BattlePhase"]
__all__ += ["BattlePhaseKind", "BattlePhaseSequenceDescriptor", "BattleRoundFlow"]
__all__ += ["ChargePhaseState", "ChargeRollRequest", "ChargeRollResult", "ChargingUnitSelection"]
__all__ += ["DECLINE_STRATAGEM_WINDOW_OPTION_ID", "CommandPhaseHandler"]
__all__ += ["DEFAULT_MAX_LIFECYCLE_TRANSITIONS", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "DiceRollManager"]
__all__ += ["FightPhaseState", "FightsFirstRegistry", "GameConfig", "GameConfigPayload"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecyclePayload", "GameLifecycleStage"]
__all__ += ["GameState", "GameStatePayload", "GeometrySourceKind", "HeightSourceKind"]
__all__ += ["JsonValue", "LifecycleStatus", "LifecycleStatusKind", "MissionSetup"]
__all__ += ["ModelGeometryCatalogRecord", "ModelGeometryCatalogRecordPayload"]
__all__ += ["ModelProfileSelection", "MovementPhaseState", "ObjectiveControlTiming"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "PlaceholderPhaseHandler", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupCompletionGate"]
__all__ += ["SetupSequenceDescriptor", "SetupStep", "SetupStepKind", "ShootingPhaseState"]
__all__ += ["TACTICAL_SECONDARY_DRAW_DECISION_TYPE", "UnitMusterSelection", "WargearSelection"]
__all__ += ["_advance_to_battle", "_army_muster_request", "_army_muster_requests", "_battle_flow"]
__all__ += ["_battle_lifecycle_for_consistency", "_battle_state", "_complete_setup_through_gate"]
__all__ += ["_config", "_decline_stratagem_window_if_pending", "_descriptor_with_sequences"]
__all__ += ["_lifecycle_is_in_battle", "_mission_setup", "_pending_request"]
__all__ += ["_phase_state_consistency_payload", "_state", "_state_battle_phase"]
__all__ += ["accepted_model_geometry", "cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_deterministic_battlefield_scenario", "drain_pending_secondary_mission_setup"]
__all__ += ["ensure_army_mustered_events_for_fixture", "game_lifecycle_stage_from_token"]
__all__ += ["inspect", "lifecycle_status_kind_from_token", "muster_army", "pytest", "replace"]
__all__ += ["seed_completed_fight_phase", "submit_all_deployments_if_pending"]
