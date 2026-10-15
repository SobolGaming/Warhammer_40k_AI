from __future__ import annotations

from tests.shared.category_migration.phase17n_step5b_marker_conditions import (
    PRIMARY_OPERATION_MARKER_KIND,
    PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_MARKER_CONDITIONS,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    BattlefieldRegionKind,
    BattlePhase,
    DecisionResult,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    MarkerAnchorKind,
    MissionSetup,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    PrimaryConsecrationDesignationState,
    PrimaryMissionChoiceData,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    PrimaryScoringConditionContext,
    RuntimeModifierRegistry,
    VictoryPointSourceKind,
    _action_marker,
    _action_marker_progress,
    _bind_force_dispositions,
    _consecrate_setup,
    _consecrated_progress,
    _consecration_designation,
    _marker,
    _non_home_objective_ids,
    _objective_context,
    _opponent_territory_non_home_objective_ids,
    _primary_awards_by_condition,
    _resolved_primary_action,
    _smoke_setup,
    active_decoy_objective_ids,
    consecrated_marker_source_identity,
    decoy_marker_source_identity,
    evaluate_marker_scoring_condition,
    evaluate_primary_scoring_condition,
    home_objective_ids,
    mission_scoring_policies_from_setup,
    phase17n_consecrate_pending_fixture,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    primary_consecration_designation_id,
    primary_mission_marker_id,
    primary_scoring_rules_from_definition,
    pytest,
    replace,
    resolve_primary_mission_actions_at_turn_end,
    score_primary_objective_control_boundary,
    triangulated_marker_source_identity,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_step5b_fails_closed_on_unknown_or_duplicate_marker_objectives() -> None:
    setup = _smoke_setup()
    objective_id = _non_home_objective_ids(setup)[0]
    unknown = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_marker_source_identity(),
        objective_id="step5b-unknown-objective",
        index=1,
    )
    first = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_marker_source_identity(),
        objective_id=objective_id,
        index=2,
    )
    duplicate = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_marker_source_identity(),
        objective_id=objective_id,
        index=3,
    )
    with pytest.raises(GameLifecycleError, match="unknown objective"):
        active_decoy_objective_ids(
            PrimaryMissionProgressState.empty().add_marker(unknown),
            player_id="player-a",
            mission_id="primary-smoke-and-mirrors",
            mission_setup=setup,
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate an objective"):
        active_decoy_objective_ids(
            PrimaryMissionProgressState.empty().add_marker(first).add_marker(duplicate),
            player_id="player-a",
            mission_id="primary-smoke-and-mirrors",
            mission_setup=setup,
        )


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldRegionKind", "DecisionResult", "GameLifecycle"]
__all__ += ["GameState", "MarkerAnchorKind", "MissionSetup", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlResult", "ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_OPERATION_MARKER_KIND"]
__all__ += ["PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION"]
__all__ += ["PRIMARY_SCORING_MARKER_CONDITIONS", "PRIMARY_SCORING_SPATIAL_CONDITIONS"]
__all__ += ["PrimaryConsecrationDesignationState", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionMarkerState", "PrimaryScoringConditionContext"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "RuntimeModifierRegistry"]
__all__ += ["VictoryPointSourceKind", "_action_marker_progress", "_bind_force_dispositions"]
__all__ += ["_consecrate_setup", "_consecrated_progress", "_consecration_designation", "_marker"]
__all__ += ["_objective_context", "_opponent_territory_non_home_objective_ids"]
__all__ += ["_primary_awards_by_condition", "_resolved_primary_action"]
__all__ += ["consecrated_marker_source_identity", "evaluate_marker_scoring_condition"]
__all__ += ["evaluate_primary_scoring_condition", "home_objective_ids"]
__all__ += ["mission_scoring_policies_from_setup", "phase17n_consecrate_pending_fixture"]
__all__ += ["phase17n_event_setup", "phase17n_started_primary_action_fixture"]
__all__ += ["primary_consecration_designation_id", "primary_mission_marker_id"]
__all__ += ["primary_scoring_rules_from_definition", "replace"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
__all__ += ["score_primary_objective_control_boundary", "triangulated_marker_source_identity"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
