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


def test_phase16b_restore_derives_cursor_history_from_authoritative_decision_order(
    pending_alternating_scout_after_first_action_payload: GameLifecyclePayload,
) -> None:
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(
                json.dumps(pending_alternating_scout_after_first_action_payload, sort_keys=True)
            ),
        )
    )
    player_b_selection = lifecycle.decision_controller.queue.peek_next()
    proposal_status = _submit_option(
        lifecycle,
        request=player_b_selection,
        option_id="scout_move:army-beta:scout-unit-1",
        result_id="phase16b-cursor-history-scout-select-b-1",
    )
    proposal_request = _decision_request(proposal_status)
    if lifecycle.state is None:
        raise GameLifecycleError("Cursor-history regression requires GameState.")
    _submit_scout_move(
        lifecycle,
        request=proposal_request,
        result_id="phase16b-cursor-history-scout-apply-b-1",
        witness=_scout_move_witness(lifecycle.state, request=proposal_request, dx=-1.0),
    )
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    state_payload = cast(dict[str, Any], payload["state"])
    records = cast(list[dict[str, Any]], state_payload["prebattle_action_records"])
    assert len(records) == 2
    records[0]["action_id"], records[1]["action_id"] = (
        records[1]["action_id"],
        records[0]["action_id"],
    )
    cursor = cast(dict[str, Any], state_payload["prebattle_alternation_cursor"])
    cursor["last_action_id"] = records[0]["action_id"]
    cursor["last_unit_instance_id"] = records[0]["unit_instance_id"]

    with pytest.raises(GameLifecycleError, match="verified action order"):
        GameLifecycle.from_payload(payload)


def test_phase16b_scout_cursor_skips_only_player_without_unresolved_rule() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="vehicle-1"),),
            player_b_unit_selections=(
                _unit_selection(unit_selection_id="scout-unit-1"),
                _unit_selection(unit_selection_id="scout-unit-2"),
            ),
        )
    )
    first_request = _decision_request(status)
    assert first_request.actor_id == "player-b"
    first_proposal_status = _submit_option(
        lifecycle,
        request=first_request,
        option_id="scout_move:army-beta:scout-unit-1",
        result_id="phase16b-skip-empty-scout-select-b-1",
    )
    first_proposal = _decision_request(first_proposal_status)
    assert lifecycle.state is not None
    follow_up = _submit_scout_move(
        lifecycle,
        request=first_proposal,
        result_id="phase16b-skip-empty-scout-apply-b-1",
        witness=_scout_move_witness(lifecycle.state, request=first_proposal, dx=-1.0),
    )

    next_request = _decision_request(follow_up)
    assert next_request.actor_id == "player-b"
    assert "scout_move:army-beta:scout-unit-2" in _option_ids(next_request)


def test_phase16b_scout_move_rejects_endpoint_only_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    before_request_id = request.request_id
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()
    before_record_count = len(lifecycle.decision_controller.records)

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-endpoint-only-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0, endpoint_only=True),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.ENDPOINT_ONLY_PATH.value in _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == before_request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_scout_move_rejects_witness_start_drift_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()
    before_record_count = len(lifecycle.decision_controller.records)

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-start-drift-scout",
        witness=_witness_with_first_start_drift(
            _scout_move_witness(lifecycle.state, request=request, dx=-3.0)
        ),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.WITNESS_START_DRIFT.value in _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_malformed_scout_submission_rejects_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    before_record_count = len(lifecycle.decision_controller.records)
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout Move test request requires scout_distance_inches.")
    proposal = ScoutMoveProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
        game_id=request_context.game_id,
        ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id=request_context.source_rule_id,
        scout_distance_inches=request_context.scout_distance_inches,
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
        context=request_context.context,
    )
    payload = validate_json_value(proposal.to_payload())
    if not isinstance(payload, dict):
        raise GameLifecycleError("Scout Move proposal test payload must be an object.")
    payload.pop("witness")

    invalid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-malformed-scout",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "malformed_prebattle_proposal"
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16b_scout_move_request_drift_rejects_before_queue_pop() -> None:
    config = _scouts_config()
    lifecycle, status = _advance_after_deployments(config)
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout Move test request requires scout_distance_inches.")
    proposal = ScoutMoveProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=request_context.proposal_kind,
        game_id="phase16b-drifted-game",
        ruleset_descriptor_hash="phase16b-drifted-ruleset",
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id="phase16b-drifted-source",
        scout_distance_inches=request_context.scout_distance_inches + 1.0,
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
        context=request_context.context,
    )
    result = DecisionResult(
        result_id="phase16b-drifted-scout",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(proposal.to_payload()),
    )

    invalid_status = invalid_prebattle_proposal_status(
        state=lifecycle.state,
        request=request,
        result=result,
        ruleset_descriptor=_ruleset(),
        army_catalog=config.army_catalog,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_request_drift"
    assert {
        PreBattleViolationCode.GAME_ID_DRIFT.value,
        PreBattleViolationCode.RULESET_HASH_DRIFT.value,
        PreBattleViolationCode.SOURCE_RULE_DRIFT.value,
    } <= _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "event payload is invalid"),
        ({}, "resolution is invalid"),
        ({"resolution": []}, "resolution is invalid"),
        ({"resolution": {}}, "batch is invalid"),
        ({"resolution": {"transition_batch": None}}, "batch is invalid"),
        ({"resolution": {"transition_batch": []}}, "batch is invalid"),
        ({"resolution": {"transition_batch": {}}}, "batch is invalid"),
    ],
)
def test_scout_physical_history_rejects_malformed_transition(
    payload: JsonValue, message: str
) -> None:
    event = EventRecord(
        event_id="physical-history", event_type="prebattle_scout_move_completed", payload=payload
    )
    with pytest.raises(GameLifecycleError, match=message):
        authoritative_battlefield_transition_batch_or_none(event=event)


__all__: list[str] = []
__all__ += ["AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["ArmyMusterRequest", "BattlefieldPlacementKind", "BattlefieldTransitionBatch"]
__all__ += ["Callable", "CatalogAbilitySourceKind", "CatalogAbilitySupport"]
__all__ += ["DatasheetAbilityDescriptor", "DatasheetDefinition", "DatasheetKeywordSet"]
__all__ += ["DecisionController", "DecisionError", "DecisionOption", "DecisionRecord"]
__all__ += ["DecisionRequest", "DetachmentSelection", "DiceExpression", "DiceRollManager"]
__all__ += ["DiceRollSpec", "DisembarkModeKind", "GameConfig", "GameLifecycleStage", "GameState"]
__all__ += ["LifecycleStatus", "MissionSetup", "ModelDisplacementKind", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "MovementPhaseActionKind", "MovementProposalRequest"]
__all__ += ["PathWitness", "PlacementProposalPayload", "Pose", "PreBattleActionKind"]
__all__ += ["PreBattleActionRecord", "PreBattleAlternationCursor", "PreBattlePlacementProposal"]
__all__ += ["PreBattlePlacementProposalPayload", "PreBattleProposalRequestPayload"]
__all__ += ["PreBattleTimingWindowState", "ReplayArtifact", "ReplayRunner", "ReserveKind"]
__all__ += ["ReserveState", "ReserveStatus", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_DEPLOYMENT_UNIT_DECISION_TYPE"]
__all__ += ["SELECT_PREBATTLE_ACTION_DECISION_TYPE", "SELECT_REDEPLOY_UNIT_DECISION_TYPE"]
__all__ += ["SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE", "SUBMIT_SCOUT_MOVE_DECISION_TYPE"]
__all__ += ["ScoutAbilityInstance", "SetupStep", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "TransportCapacityProfile"]
__all__ += ["TransportCargoState", "TransportMovementStatus", "UnitInstance"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "_PoseFactory"]
__all__ += ["_advance_to_first_deployment_selection", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_assert_redeploy_replay_rejected_without_mutation"]
__all__ += ["_clone_payload", "_event_types", "_manual_prebattle_state", "_mission_setup"]
__all__ += ["_mission_setup_with_terrain_endpoint_feature", "_model_source_for_id"]
__all__ += ["_move_unit_placement", "_option_for_prefix", "_place_unit"]
__all__ += ["_prebattle_placement_payload", "_prebattle_placement_payload_for_request"]
__all__ += ["_proposal_request_from_selection_payload", "_redeploy_broken_coherency_pose"]
__all__ += ["_redeploy_illegal_zone_pose", "_redeploy_invalid_pose_factory"]
__all__ += ["_redeploy_overlap_pose", "_redeploy_placement_request", "_restored_pending_request"]
__all__ += ["_scouts_ability_descriptors", "_submit_redeploy_placement_payload"]
__all__ += ["_terrain_endpoint_feature", "_unit_source_for_id", "apply_scout_move"]
__all__ += ["apply_scout_reserve_setup", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_empty_deployment_battlefield_state"]
__all__ += ["dedicated_transport_scout_move_candidates_for_player"]
__all__ += ["leading_first_translation_paths", "muster_army"]
__all__ += ["pending_alternating_scout_after_first_action_payload"]
__all__ += ["prebattle_action_kind_from_token", "prebattle_action_selection_request"]
__all__ += ["prebattle_timing_state_for_state", "prebattle_violation_code_from_token"]
__all__ += ["redeploy_timing_state_for_state", "replace", "resolve_prebattle_proposal"]
__all__ += ["scout_move_candidates_for_player", "submit_all_deployments_if_pending"]
__all__ += ["validate_prebattle_alternation_restore"]
