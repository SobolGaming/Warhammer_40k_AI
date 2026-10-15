from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase16b_prebattle import (
    AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES,
    PARAMETERIZED_DECISION_OPTION_ID,
    SCOUT_MOVE_PROPOSAL_KIND,
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SELECT_REDEPLOY_UNIT_DECISION_TYPE,
    SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    Callable,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DecisionController,
    DecisionError,
    DecisionOption,
    DecisionRecord,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    DiceExpression,
    DiceRollManager,
    DiceRollSpec,
    DisembarkModeKind,
    EventRecord,
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
    ModelDisplacementKind,
    ModelPlacement,
    ModelProfileSelection,
    MovementPhaseActionKind,
    MovementProposalRequest,
    PathWitness,
    PlacementProposalPayload,
    Pose,
    PreBattleActionKind,
    PreBattleActionRecord,
    PreBattleAlternationCursor,
    PreBattlePlacementProposal,
    PreBattlePlacementProposalPayload,
    PreBattleProposalRequest,
    PreBattleProposalRequestPayload,
    PreBattleTimingWindowState,
    PreBattleViolationCode,
    ReplayArtifact,
    ReplayRunner,
    ReserveKind,
    ReserveState,
    ReserveStatus,
    RulesetDescriptor,
    ScoutAbilityInstance,
    ScoutMoveProposal,
    SetupStep,
    TerrainDisplayGeometry,
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    _advance_after_deployments,
    _advance_to_first_deployment_selection,
    _army_muster_request,
    _army_muster_requests,
    _assert_redeploy_replay_rejected_without_mutation,
    _catalog_with_datasheet_keywords,
    _clone_payload,
    _config,
    _decision_request,
    _event_types,
    _invalid_reason,
    _manual_prebattle_state,
    _mission_setup,
    _mission_setup_with_terrain_endpoint_feature,
    _model_source_for_id,
    _move_unit_placement,
    _option_for_prefix,
    _option_ids,
    _place_unit,
    _PoseFactory,
    _prebattle_placement_payload,
    _prebattle_placement_payload_for_request,
    _proposal_request_from_selection_payload,
    _redeploy_broken_coherency_pose,
    _redeploy_illegal_zone_pose,
    _redeploy_invalid_pose_factory,
    _redeploy_overlap_pose,
    _redeploy_placement_request,
    _restored_pending_request,
    _ruleset,
    _scout_move_witness,
    _scouts_ability_descriptors,
    _scouts_config,
    _select_scout_move,
    _submit_option,
    _submit_redeploy_placement_payload,
    _submit_scout_move,
    _terrain_endpoint_feature,
    _unit_selection,
    _unit_source_for_id,
    _vehicle_unit_selection,
    _violation_codes,
    _witness_with_first_start_drift,
    apply_scout_move,
    apply_scout_reserve_setup,
    authoritative_battlefield_transition_batch_or_none,
    chapter_approved_2026_27_mission_pack,
    create_empty_deployment_battlefield_state,
    dedicated_transport_scout_move_candidates_for_player,
    invalid_prebattle_proposal_status,
    json,
    leading_first_translation_paths,
    muster_army,
    pending_alternating_scout_after_first_action_payload,
    prebattle_action_kind_from_token,
    prebattle_action_selection_request,
    prebattle_timing_state_for_state,
    prebattle_violation_code_from_token,
    pytest,
    redeploy_timing_state_for_state,
    replace,
    resolve_prebattle_proposal,
    scout_move_candidates_for_player,
    submit_all_deployments_if_pending,
    validate_json_value,
    validate_prebattle_alternation_restore,
)


@pytest.mark.parametrize("event_type", sorted(AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES))
def test_physical_history_reads_each_registered_transition_shape(event_type: str) -> None:
    batch = BattlefieldTransitionBatch()
    payload: dict[str, JsonValue] = {"transition_batch": validate_json_value(batch.to_payload())}
    if event_type == "prebattle_scout_move_completed":
        payload = {"resolution": payload}
    event = EventRecord(event_id="physical-history", event_type=event_type, payload=payload)
    assert authoritative_battlefield_transition_batch_or_none(event=event) == batch


def test_physical_history_keeps_nonphysical_and_optional_batch_controls() -> None:
    controls: tuple[tuple[str, JsonValue], ...] = (
        ("prebattle_action_recorded", {"resolution": {"transition_batch": []}}),
        ("movement_activation_completed", {}),
        ("movement_activation_completed", {"transition_batch": None}),
    )
    for event_type, payload in controls:
        event = EventRecord(
            event_id="physical-history", event_type=event_type, payload=validate_json_value(payload)
        )
        assert authoritative_battlefield_transition_batch_or_none(event=event) is None
    malformed_payloads: tuple[JsonValue, ...] = (
        None,
        {"transition_batch": []},
        {"transition_batch": {}},
    )
    for malformed_payload in malformed_payloads:
        event = EventRecord(
            event_id="physical-history",
            event_type="movement_activation_completed",
            payload=validate_json_value(malformed_payload),
        )
        with pytest.raises(GameLifecycleError, match="Battlefield transition"):
            authoritative_battlefield_transition_batch_or_none(event=event)


__all__: list[str] = []
__all__ += ["Any", "ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest"]
__all__ += ["BattlefieldPlacementKind", "Callable", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "DatasheetAbilityDescriptor", "DatasheetDefinition"]
__all__ += ["DatasheetKeywordSet", "DecisionController", "DecisionError", "DecisionOption"]
__all__ += ["DecisionRecord", "DecisionRequest", "DecisionResult", "DetachmentSelection"]
__all__ += ["DiceExpression", "DiceRollManager", "DiceRollSpec", "DisembarkModeKind"]
__all__ += ["GameConfig", "GameLifecycle", "GameLifecyclePayload", "GameLifecycleStage"]
__all__ += ["GameState", "LifecycleStatus", "LifecycleStatusKind", "MissionSetup"]
__all__ += ["ModelDisplacementKind", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["MovementPhaseActionKind", "MovementProposalRequest"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "PathWitness", "PlacementProposalPayload", "Pose"]
__all__ += ["PreBattleActionKind", "PreBattleActionRecord", "PreBattleAlternationCursor"]
__all__ += ["PreBattlePlacementProposal", "PreBattlePlacementProposalPayload"]
__all__ += ["PreBattleProposalRequest", "PreBattleProposalRequestPayload"]
__all__ += ["PreBattleTimingWindowState", "PreBattleViolationCode", "ReplayArtifact"]
__all__ += ["ReplayRunner", "ReserveKind", "ReserveState", "ReserveStatus", "RulesetDescriptor"]
__all__ += ["SCOUT_MOVE_PROPOSAL_KIND", "SECONDARY_MISSION_DECISION_TYPE"]
__all__ += ["SELECT_DEPLOYMENT_UNIT_DECISION_TYPE", "SELECT_PREBATTLE_ACTION_DECISION_TYPE"]
__all__ += ["SELECT_REDEPLOY_UNIT_DECISION_TYPE", "SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE"]
__all__ += ["SUBMIT_SCOUT_MOVE_DECISION_TYPE", "ScoutAbilityInstance", "ScoutMoveProposal"]
__all__ += ["SetupStep", "TerrainDisplayGeometry", "TerrainFeatureDefinition"]
__all__ += ["TerrainFeatureKind", "TransportCapacityProfile", "TransportCargoState"]
__all__ += ["TransportMovementStatus", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["_PoseFactory", "_advance_after_deployments"]
__all__ += ["_advance_to_first_deployment_selection", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_assert_redeploy_replay_rejected_without_mutation"]
__all__ += ["_catalog_with_datasheet_keywords", "_clone_payload", "_config", "_decision_request"]
__all__ += ["_event_types", "_invalid_reason", "_manual_prebattle_state", "_mission_setup"]
__all__ += ["_mission_setup_with_terrain_endpoint_feature", "_model_source_for_id"]
__all__ += ["_move_unit_placement", "_option_for_prefix", "_option_ids", "_place_unit"]
__all__ += ["_prebattle_placement_payload", "_prebattle_placement_payload_for_request"]
__all__ += ["_proposal_request_from_selection_payload", "_redeploy_broken_coherency_pose"]
__all__ += ["_redeploy_illegal_zone_pose", "_redeploy_invalid_pose_factory"]
__all__ += ["_redeploy_overlap_pose", "_redeploy_placement_request", "_restored_pending_request"]
__all__ += ["_ruleset", "_scout_move_witness", "_scouts_ability_descriptors", "_scouts_config"]
__all__ += ["_select_scout_move", "_submit_option", "_submit_redeploy_placement_payload"]
__all__ += ["_submit_scout_move", "_terrain_endpoint_feature", "_unit_selection"]
__all__ += ["_unit_source_for_id", "_vehicle_unit_selection", "_violation_codes"]
__all__ += ["_witness_with_first_start_drift", "apply_scout_move", "apply_scout_reserve_setup"]
__all__ += ["cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_empty_deployment_battlefield_state"]
__all__ += ["dedicated_transport_scout_move_candidates_for_player"]
__all__ += ["invalid_prebattle_proposal_status", "json", "leading_first_translation_paths"]
__all__ += ["muster_army", "pending_alternating_scout_after_first_action_payload"]
__all__ += ["prebattle_action_kind_from_token", "prebattle_action_selection_request"]
__all__ += ["prebattle_timing_state_for_state", "prebattle_violation_code_from_token"]
__all__ += ["redeploy_timing_state_for_state", "replace", "resolve_prebattle_proposal"]
__all__ += ["scout_move_candidates_for_player", "submit_all_deployments_if_pending"]
__all__ += ["validate_prebattle_alternation_restore"]
