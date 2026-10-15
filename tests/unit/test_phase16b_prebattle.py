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


def test_order56_scout_values_are_finite_and_source_examples_are_preserved() -> None:
    from warhammer40k_core.engine.prebattle_instance_selection import (
        scout_distance_options_for_model_ids,
    )

    model_ids = ("model-1", "model-2")

    assert scout_distance_options_for_model_ids(
        model_instance_ids=model_ids,
        ability_instances=(
            ScoutAbilityInstance(model_instance_id="model-1", distance_inches=6.0),
            ScoutAbilityInstance(model_instance_id="model-1", distance_inches=8.0),
            ScoutAbilityInstance(model_instance_id="model-2", distance_inches=6.0),
            ScoutAbilityInstance(model_instance_id="model-2", distance_inches=8.0),
        ),
    ) == (6.0, 8.0)
    assert scout_distance_options_for_model_ids(
        model_instance_ids=model_ids,
        ability_instances=(
            ScoutAbilityInstance(model_instance_id="model-1", distance_inches=6.0),
            ScoutAbilityInstance(model_instance_id="model-2", distance_inches=8.0),
        ),
    ) == (6.0,)
    with pytest.raises(GameLifecycleError, match="Every model must have a Scouts ability"):
        scout_distance_options_for_model_ids(
            model_instance_ids=model_ids,
            ability_instances=(
                ScoutAbilityInstance(model_instance_id="model-1", distance_inches=8.0),
            ),
        )


def test_phase16b_redeploy_records_removal_and_placement_batches() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
        )
    )
    request = _decision_request(status)

    assert request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert "redeploy:army-beta:intercessor-unit-2" in _option_ids(request)

    proposal_status = _submit_option(
        lifecycle,
        request=request,
        option_id="redeploy:army-beta:intercessor-unit-2",
        result_id="phase16b-redeploy-select",
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE
    payload = _prebattle_placement_payload_for_request(
        lifecycle,
        request=proposal_request,
        pose_factory=lambda index: Pose.at(
            56.0 - ((index // 3) * 1.8),
            34.0 + ((index % 3) * 1.8),
            0.0,
            facing_degrees=180.0,
        ),
    )

    follow_up = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-redeploy-place",
            request_id=proposal_request.request_id,
            decision_type=proposal_request.decision_type,
            actor_id=proposal_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )

    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.TERMINAL,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    assert lifecycle.state is not None
    records = tuple(
        record
        for record in lifecycle.state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.REDEPLOY
    )
    assert len(records) == 1
    resolution = cast(dict[str, JsonValue], records[0].payload)
    removal_batch = cast(dict[str, JsonValue], resolution["removal_batch"])
    placement_batch = cast(dict[str, JsonValue], resolution["placement_batch"])
    assert len(cast(list[JsonValue], removal_batch["removals"])) == 5
    assert len(cast(list[JsonValue], placement_batch["placements"])) == 5
    assert cast(list[JsonValue], placement_batch["displacements"]) == []
    assert _event_types(lifecycle).count("prebattle_redeploy_completed") == 1
    payload_blob = json.dumps(records[0].to_payload(), sort_keys=True)
    assert "<" not in payload_blob
    assert "object at 0x" not in payload_blob


def test_phase16b_redeploys_use_first_turn_authority_without_rolloff() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, status = _advance_after_deployments(_config(catalog=catalog))
    request = _decision_request(status)
    assert lifecycle.state is not None
    assert request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    assert request.actor_id == lifecycle.state.turn_order[0]
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type != "roll_off_resolved":
            continue
        assert isinstance(event.payload, dict)
        roll_request = event.payload["request"]
        assert isinstance(roll_request, dict)
        assert roll_request.get("purpose") != "sequencing_conflict"
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    result = DecisionResult.for_request(
        result_id="order36-redeploy-owner-completes",
        request=request,
        selected_option_id="complete_redeploys",
    )
    after = lifecycle.submit_decision(result)
    replayed = restored.submit_decision(result)
    assert replayed.to_payload() == after.to_payload()
    next_request = _decision_request(after)
    assert next_request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    assert next_request.actor_id == lifecycle.state.turn_order[1]
    assert restored.to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize(
    "drift_kind", ["actor", "option_label", "option_payload", "option_inventory"]
)
def test_phase16b_redeploy_authority_rejects_drift_without_mutation(drift_kind: str) -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, status = _advance_after_deployments(_config(catalog=catalog))
    request = _decision_request(status)
    payload = _clone_payload(cast(dict[str, Any], lifecycle.to_payload()))
    pending = payload["decisions"]["queue"]["pending_requests"][0]
    issued = next(
        event["payload"]
        for event in reversed(payload["decisions"]["event_log"])
        if event["event_type"] == "decision_requested"
        and event["payload"]["request_id"] == request.request_id
    )
    for changed in (pending, issued):
        if drift_kind == "actor":
            changed["actor_id"] = "player-b" if request.actor_id == "player-a" else "player-a"
        elif drift_kind == "option_label":
            changed["options"][0]["label"] = "Forged redeploy label"
        elif drift_kind == "option_payload":
            changed["options"][0]["payload"]["source_rule_id"] = "forged-redeploy"
        else:
            changed["options"].pop()
    _assert_redeploy_replay_rejected_without_mutation(
        payload,
        result_id=f"order36-redeploy-{drift_kind}",
    )


def test_phase16b_simultaneous_scouts_start_with_first_turn_player_and_alternate_by_unit() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(
                _unit_selection(unit_selection_id="scout-unit-1"),
                _unit_selection(unit_selection_id="scout-unit-2"),
            ),
            player_b_unit_selections=(
                _unit_selection(unit_selection_id="scout-unit-1"),
                _unit_selection(unit_selection_id="scout-unit-2"),
            ),
        )
    )
    first_request = _decision_request(status)

    assert first_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    assert first_request.actor_id == "player-a"
    assert "scout_move:army-alpha:scout-unit-1" in _option_ids(first_request)
    assert "scout_move:army-alpha:scout-unit-2" in _option_ids(first_request)
    assert not any(
        event.event_type == "sequencing_order_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("conflict_id") == "prebattle-sequencing:resolve_prebattle_actions"
        for event in lifecycle.decision_controller.event_log.records
    )
    replay_initial_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    first_proposal_status = _submit_option(
        lifecycle,
        request=first_request,
        option_id="scout_move:army-alpha:scout-unit-1",
        result_id="phase16b-alternating-scout-select-a-1",
    )
    first_proposal = _decision_request(first_proposal_status)
    assert lifecycle.state is not None
    second_status = _submit_scout_move(
        lifecycle,
        request=first_proposal,
        result_id="phase16b-alternating-scout-apply-a-1",
        witness=_scout_move_witness(lifecycle.state, request=first_proposal, dx=1.0),
    )
    second_request = _decision_request(second_status)

    assert second_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    assert second_request.actor_id == "player-b"
    assert "scout_move:army-beta:scout-unit-1" in _option_ids(second_request)
    assert "scout_move:army-alpha:scout-unit-2" not in _option_ids(second_request)

    restored_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(restored_payload)
    restored_second_request = restored.decision_controller.queue.peek_next()
    assert restored_second_request == second_request
    drifted_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(restored_payload, sort_keys=True)),
    )
    drifted_cursor = cast(dict[str, Any], drifted_payload["state"])["prebattle_alternation_cursor"]
    assert isinstance(drifted_cursor, dict)
    drifted_cursor["next_player_id"] = "player-a"
    with pytest.raises(GameLifecycleError, match="pending decision actor drifted"):
        GameLifecycle.from_payload(drifted_payload)
    second_proposal_status = _submit_option(
        restored,
        request=restored_second_request,
        option_id="scout_move:army-beta:scout-unit-1",
        result_id="phase16b-alternating-scout-select-b-1",
    )
    second_proposal = _decision_request(second_proposal_status)
    assert restored.state is not None
    third_status = _submit_scout_move(
        restored,
        request=second_proposal,
        result_id="phase16b-alternating-scout-apply-b-1",
        witness=_scout_move_witness(restored.state, request=second_proposal, dx=-1.0),
    )
    third_request = _decision_request(third_status)

    assert third_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    assert third_request.actor_id == "player-a"
    assert "scout_move:army-alpha:scout-unit-2" in _option_ids(third_request)
    assert restored.state.prebattle_alternation_cursor is not None
    assert restored.state.prebattle_alternation_cursor.next_player_id == "player-a"
    assert restored.state.prebattle_alternation_cursor.resolved_action_count == 2

    artifact = ReplayArtifact.capture(
        artifact_id="phase16b-alternating-scout-replay",
        initial_lifecycle_payload=replay_initial_payload,
        final_lifecycle=restored,
    )
    replay_result = ReplayRunner(artifact).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_phase16b_restore_rejects_duplicate_prebattle_action_decision_ownership(
    pending_alternating_scout_after_first_action_payload: GameLifecyclePayload,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(
            json.dumps(pending_alternating_scout_after_first_action_payload, sort_keys=True)
        ),
    )
    state_payload = cast(dict[str, Any], payload["state"])
    records = cast(list[dict[str, Any]], state_payload["prebattle_action_records"])
    original = records[-1]
    duplicate = cast(dict[str, Any], json.loads(json.dumps(original, sort_keys=True)))
    duplicate["action_id"] = "prebattle-action-000002"
    duplicate["action_kind"] = PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value
    duplicate["unit_instance_id"] = None
    duplicate["payload"] = {
        "game_id": state_payload["game_id"],
        "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
        "player_id": original["player_id"],
    }
    records.append(duplicate)
    cursor = cast(dict[str, Any], state_payload["prebattle_alternation_cursor"])
    cursor["resolved_action_count"] = 2
    cursor["last_action_id"] = duplicate["action_id"]
    cursor["last_unit_instance_id"] = None

    with pytest.raises(GameLifecycleError, match="request_id must be unique"):
        GameLifecycle.from_payload(payload)
    duplicate["request_id"] = "decision-request-forged-duplicate-owner"
    with pytest.raises(GameLifecycleError, match="result_id must be unique"):
        GameLifecycle.from_payload(payload)


def test_phase16b_restore_rejects_scout_action_relabelled_as_completion(
    pending_alternating_scout_after_first_action_payload: GameLifecyclePayload,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(
            json.dumps(pending_alternating_scout_after_first_action_payload, sort_keys=True)
        ),
    )
    state_payload = cast(dict[str, Any], payload["state"])
    records = cast(list[dict[str, Any]], state_payload["prebattle_action_records"])
    record = records[-1]
    record["action_kind"] = PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value
    record["unit_instance_id"] = None
    record["payload"] = {
        "game_id": state_payload["game_id"],
        "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
        "player_id": record["player_id"],
    }
    cursor = cast(dict[str, Any], state_payload["prebattle_alternation_cursor"])
    cursor["last_unit_instance_id"] = None

    with pytest.raises(GameLifecycleError, match="semantic drift"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("drift_field", ["unit_instance_id", "source_rule_id", "payload"])
def test_phase16b_restore_rejects_scout_action_semantic_drift(
    pending_alternating_scout_after_first_action_payload: GameLifecyclePayload,
    drift_field: str,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(
            json.dumps(pending_alternating_scout_after_first_action_payload, sort_keys=True)
        ),
    )
    state_payload = cast(dict[str, Any], payload["state"])
    records = cast(list[dict[str, Any]], state_payload["prebattle_action_records"])
    record = records[-1]
    if drift_field == "unit_instance_id":
        record["unit_instance_id"] = "army-alpha:scout-unit-2"
        cursor = cast(dict[str, Any], state_payload["prebattle_alternation_cursor"])
        cursor["last_unit_instance_id"] = record["unit_instance_id"]
    elif drift_field == "source_rule_id":
        record["source_rule_id"] = "core_rules:scouts:drifted"
    else:
        resolution_payload = cast(dict[str, Any], record["payload"])
        transition_payload = cast(dict[str, Any], resolution_payload["transition_batch"])
        displacements = cast(list[dict[str, Any]], transition_payload["displacements"])
        displacements[0]["source_event_id"] = "forged-scout-transition-source"

    with pytest.raises(GameLifecycleError, match="semantic drift"):
        GameLifecycle.from_payload(payload)


def test_phase16b_configless_restore_requires_catalog_only_during_live_scout_window() -> None:
    catalog = _catalog_with_datasheet_keywords({})
    state = _manual_prebattle_state(catalog=catalog)
    cursor = PreBattleAlternationCursor.start(
        game_id=state.game_id,
        ordered_player_ids=state.turn_order,
    )
    state.set_prebattle_alternation_cursor(cursor)
    pending_request = DecisionRequest(
        request_id="phase16b-configless-pending-scout",
        decision_type=SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"game_id": state.game_id},
        options=(DecisionOption(option_id="complete", label="Complete"),),
    )

    with pytest.raises(GameLifecycleError, match="pending pre-battle alternation"):
        validate_prebattle_alternation_restore(
            state=state,
            army_catalog=None,
            decision_records=(),
            pending_decision_requests=(pending_request,),
        )

    state.set_prebattle_alternation_cursor(cursor.aligned_to(None))
    assert state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    validate_prebattle_alternation_restore(
        state=state,
        army_catalog=None,
        decision_records=(),
        pending_decision_requests=(),
    )


def test_phase16b_battle_restore_does_not_recompute_scouts_from_disembarked_unit() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {
            "core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS"),
            "core-transport": ("Transport", "Vehicle"),
        }
    )
    config = _config(
        catalog=catalog,
        player_a_unit_selections=(
            _unit_selection(unit_selection_id="scout-unit-1"),
            _unit_selection(
                unit_selection_id="transport-unit-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
        player_b_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_secondary_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    second_secondary_status = _submit_option(
        lifecycle,
        request=first_secondary_request,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16b-later-scout-secondary-a",
    )
    if lifecycle.state is None:
        raise GameLifecycleError("Later Scout restore regression requires GameState.")
    state = lifecycle.state
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id="army-alpha:transport-unit-1",
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("Infantry",),
            ),
            embarked_unit_instance_ids=("army-alpha:scout-unit-1",),
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=("army-alpha:scout-unit-1",),
            disembarked_this_phase_unit_instance_ids=(),
        )
    )
    deployment_status = _submit_option(
        lifecycle,
        request=_decision_request(second_secondary_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16b-later-scout-secondary-b",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16b-later-scout-deploy",
    )

    assert state.stage is GameLifecycleStage.BATTLE
    assert state.prebattle_alternation_cursor is not None
    assert state.prebattle_alternation_cursor.next_player_id is None
    assert state.prebattle_alternation_cursor.resolved_action_count == 0
    assert not state.prebattle_action_records_for_step(
        player_id="player-a",
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
    )
    movement_selection_request = _decision_request(movement_status)
    movement_action_status = _submit_option(
        lifecycle,
        request=movement_selection_request,
        option_id="army-alpha:scout-unit-1",
        result_id="phase16b-later-scout-select-passenger",
    )
    placement_status = _submit_option(
        lifecycle,
        request=_decision_request(movement_action_status),
        option_id=MovementPhaseActionKind.DISEMBARK.value,
        result_id="phase16b-later-scout-select-disembark",
    )
    placement_request = _decision_request(placement_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    army, scout_unit = _unit_source_for_id(
        state=state,
        unit_instance_id="army-alpha:scout-unit-1",
    )
    disembark_poses = (
        Pose.at(6.1, 22.5),
        Pose.at(7.0, 23.8),
        Pose.at(7.0, 25.2),
        Pose.at(6.1, 26.5),
        Pose.at(5.8, 24.5),
    )
    attempted_placement = UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=scout_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=scout_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(scout_unit.own_models, disembark_poses, strict=True)
        ),
    )
    disembark_payload = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=scout_unit.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=attempted_placement,
        transport_unit_instance_id="army-alpha:transport-unit-1",
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    ).to_payload()
    post_disembark_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-later-scout-place-disembark",
            request_id=placement_request.request_id,
            decision_type=placement_request.decision_type,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(disembark_payload),
        )
    )

    assert post_disembark_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    current_candidates = scout_move_candidates_for_player(
        state=state,
        army_catalog=catalog,
        player_id="player-a",
    )
    assert tuple(candidate.unit_instance_id for candidate in current_candidates) == (
        scout_unit.unit_instance_id,
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize("selected_distance", [6.0, 8.0])
def test_phase16b_scout_distance_is_sourced_from_datasheet_ability_descriptors(
    selected_distance: float,
) -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline")},
        scouts_distances_by_datasheet={"core-intercessor-like-infantry": (6.0, 8.0)},
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
        )
    )
    request = _decision_request(status)

    assert request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    scout_options = tuple(
        option for option in request.options if option.option_id.startswith("scout_move:")
    )
    assert {
        cast(dict[str, object], option.payload)["scout_distance_inches"] for option in scout_options
    } == {6.0, 8.0}
    option = next(
        option
        for option in scout_options
        if cast(dict[str, object], option.payload)["scout_distance_inches"] == selected_distance
    )
    assert isinstance(option.payload, dict)
    assert option.payload["scout_distance_inches"] == selected_distance
    scout_instances = option.payload["scout_ability_instances"]
    assert isinstance(scout_instances, list)
    assert len(scout_instances) == 10
    source_ids: set[str] = set()
    for instance in scout_instances:
        assert isinstance(instance, dict)
        source_id = instance["source_id"]
        assert type(source_id) is str
        source_ids.add(source_id)
    assert source_ids == {
        "datasheet:core-intercessor-like-infantry:ability:scouts:1",
        "datasheet:core-intercessor-like-infantry:ability:scouts:2",
    }

    proposal_request = _decision_request(
        _submit_option(
            lifecycle,
            request=request,
            option_id=option.option_id,
            result_id="order56-scout-distance",
        )
    )
    request_context = PreBattleProposalRequest.from_decision_request_payload(
        proposal_request.payload
    )
    assert request_context.scout_distance_inches == selected_distance

    assert (
        _restored_pending_request(lifecycle, proposal_request).to_payload()
        == proposal_request.to_payload()
    )


def test_phase16b_scout_keyword_without_descriptor_fails_fast() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")},
        scouts_distances_by_datasheet={"core-intercessor-like-infantry": ()},
    )

    with pytest.raises(GameLifecycleError, match="structured datasheet ability descriptor"):
        _advance_after_deployments(
            _config(
                catalog=catalog,
                player_a_unit_selections=(
                    _vehicle_unit_selection(unit_selection_id="enemy-unit-1"),
                ),
            )
        )


def test_phase16b_replay_restore_preserves_pending_redeploy_request() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, request = _redeploy_placement_request(catalog)

    assert request.decision_type == SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE
    restored_request = _restored_pending_request(lifecycle, request)

    assert restored_request.to_payload() == request.to_payload()
    assert PreBattleProposalRequest.from_decision_request_payload(
        restored_request.payload
    ) == PreBattleProposalRequest.from_decision_request_payload(request.payload)


def test_phase16b_replay_restore_rejects_pending_redeploy_mission_setup_drift() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, _request = _redeploy_placement_request(catalog)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    decisions = cast(dict[str, JsonValue], payload["decisions"])
    queue = cast(dict[str, JsonValue], decisions["queue"])
    pending_requests = cast(list[JsonValue], queue["pending_requests"])
    pending_request = cast(dict[str, JsonValue], pending_requests[0])
    request_payload = cast(dict[str, JsonValue], pending_request["payload"])
    proposal_request = cast(dict[str, JsonValue], request_payload["proposal_request"])
    mission_setup = cast(dict[str, JsonValue], proposal_request["mission_setup"])
    mission_setup["mission_pool_entry_id"] = "phase16b-drifted-mission-entry"

    with pytest.raises(GameLifecycleError, match="mission_setup drifted from state"):
        GameLifecycle.from_payload(payload)


def test_phase16b_replay_restore_preserves_pending_scout_move_request() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))

    assert request.decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE
    restored_request = _restored_pending_request(lifecycle, request)

    assert restored_request.to_payload() == request.to_payload()
    assert PreBattleProposalRequest.from_decision_request_payload(
        restored_request.payload
    ) == PreBattleProposalRequest.from_decision_request_payload(request.payload)


def test_phase16b_redeploy_rejects_request_drift_and_wrong_actor_without_mutation() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, request = _redeploy_placement_request(catalog)
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_battlefield = lifecycle.state.battlefield_state.to_payload()
    before_record_count = len(lifecycle.decision_controller.records)
    payload = _prebattle_placement_payload_for_request(
        lifecycle,
        request=request,
        pose_factory=lambda index: Pose.at(
            56.0 - ((index // 3) * 1.8),
            34.0 + ((index % 3) * 1.8),
            0.0,
            facing_degrees=180.0,
        ),
    )
    drifted_payload = dict(payload)
    drifted_payload["setup_step"] = SetupStep.RESOLVE_PREBATTLE_ACTIONS.value

    invalid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-redeploy-wrong-step",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=drifted_payload,
        )
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_request_drift"
    assert PreBattleViolationCode.SETUP_STEP_DRIFT.value in _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield

    with pytest.raises(DecisionError, match="actor"):
        lifecycle.submit_decision(
            DecisionResult(
                result_id="phase16b-redeploy-wrong-actor",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id="player-a",
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=payload,
            )
        )
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield


@pytest.mark.parametrize(
    ("case_id", "expected_violation"),
    [
        (
            "illegal-zone",
            PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION,
        ),
        (
            "overlap",
            PreBattleViolationCode.MODEL_OVERLAP,
        ),
        (
            "broken-coherency",
            PreBattleViolationCode.UNIT_COHERENCY_BROKEN,
        ),
    ],
)
def test_phase16b_redeploy_invalid_geometry_rejects_without_mutation(
    case_id: str,
    expected_violation: PreBattleViolationCode,
) -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, request = _redeploy_placement_request(catalog)

    invalid_status = _submit_redeploy_placement_payload(
        lifecycle,
        request=request,
        result_id=f"phase16b-redeploy-{case_id}",
        payload=_prebattle_placement_payload_for_request(
            lifecycle,
            request=request,
            pose_factory=_redeploy_invalid_pose_factory(case_id),
        ),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert expected_violation.value in _violation_codes(invalid_status)


def test_phase16b_redeploy_rejects_stale_unit_state_and_engagement_without_mutation() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, request = _redeploy_placement_request(catalog)
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    stale_payload = _prebattle_placement_payload_for_request(
        lifecycle,
        request=request,
        pose_factory=lambda index: Pose.at(
            56.0 - ((index // 3) * 1.8),
            34.0 + ((index % 3) * 1.8),
            0.0,
            facing_degrees=180.0,
        ),
    )
    lifecycle.state.replace_battlefield_state(
        lifecycle.state.battlefield_state.without_unit_placement("army-beta:intercessor-unit-2")
    )

    stale_status = _submit_redeploy_placement_payload(
        lifecycle,
        request=request,
        result_id="phase16b-redeploy-stale-unit",
        payload=stale_payload,
    )

    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert PreBattleViolationCode.UNIT_NOT_PLACED.value in _violation_codes(stale_status)

    lifecycle, request = _redeploy_placement_request(catalog)
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    enemy_placement = lifecycle.state.battlefield_state.unit_placement_by_id(
        "army-alpha:enemy-unit-1"
    )
    enemy_pose = enemy_placement.model_placements[0].pose
    _move_unit_placement(
        lifecycle.state,
        unit_instance_id="army-alpha:enemy-unit-1",
        dx=48.0 - enemy_pose.position.x,
        dy=20.0 - enemy_pose.position.y,
    )
    engagement_status = _submit_redeploy_placement_payload(
        lifecycle,
        request=request,
        result_id="phase16b-redeploy-engagement",
        payload=_prebattle_placement_payload_for_request(
            lifecycle,
            request=request,
            pose_factory=lambda index: Pose.at(
                51.5 + ((index // 3) * 1.8),
                20.0 + ((index % 3) * 1.8),
                0.0,
                facing_degrees=180.0,
            ),
        ),
    )

    assert engagement_status.status_kind is LifecycleStatusKind.INVALID
    assert PreBattleViolationCode.ENEMY_ENGAGEMENT_RANGE.value in _violation_codes(
        engagement_status
    )


def test_phase16b_redeploy_rejects_illegal_terrain_endpoint_without_mutation() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-vehicle-monster": ("Monster", "Vehicle", "REDEPLOY")}
    )
    lifecycle, request = _redeploy_placement_request(
        catalog,
        player_a_unit_selections=(_unit_selection(unit_selection_id="non-redeploy-enemy"),),
        player_b_unit_selections=(
            _vehicle_unit_selection(unit_selection_id="vehicle-redeploy-unit"),
        ),
        mission_setup=_mission_setup_with_terrain_endpoint_feature(),
    )

    invalid_status = _submit_redeploy_placement_payload(
        lifecycle,
        request=request,
        result_id="phase16b-redeploy-terrain-endpoint",
        payload=_prebattle_placement_payload_for_request(
            lifecycle,
            request=request,
            pose_factory=lambda _index: Pose.at(49.0, 17.0, 3.0, facing_degrees=180.0),
        ),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert PreBattleViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value in _violation_codes(invalid_status)


def test_phase16b_scout_move_rejects_over_distance_path_without_mutation() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-over-distance-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-7.0),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.PATH_VALIDATION_FAILED.value in _violation_codes(invalid_status)
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_valid_scout_move_records_displacements_without_movement_phase_state() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None

    follow_up = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-valid-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
    )

    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.TERMINAL,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    records = tuple(
        record
        for record in lifecycle.state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.SCOUT_MOVE
    )
    assert len(records) == 1
    resolution = cast(dict[str, JsonValue], records[0].payload)
    transition_batch = cast(dict[str, JsonValue], resolution["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    assert len(displacements) == 5
    assert {cast(str, record["displacement_kind"]) for record in displacements} == {
        ModelDisplacementKind.SCOUT_MOVE.value
    }
    assert lifecycle.state.movement_phase_state is not None
    scout_unit_id = "army-beta:intercessor-unit-2"
    assert scout_unit_id not in lifecycle.state.movement_phase_state.moved_unit_ids
    assert scout_unit_id not in lifecycle.state.movement_phase_state.selected_unit_ids
    assert lifecycle.state.advanced_unit_states == []
    assert lifecycle.state.fell_back_unit_states == []


def test_phase16b_scout_move_requires_more_than_eight_from_enemy() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    _move_unit_placement(
        lifecycle.state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        dx=47.0,
        dy=-21.0,
    )
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-too-close-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.SCOUT_ENEMY_DISTANCE.value in _violation_codes(invalid_status)
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_completion_options_record_prebattle_action_records() -> None:
    redeploy_catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    redeploy_lifecycle, redeploy_status = _advance_after_deployments(
        _config(
            catalog=redeploy_catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
        )
    )
    redeploy_request = _decision_request(redeploy_status)
    assert redeploy_request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    _submit_option(
        redeploy_lifecycle,
        request=redeploy_request,
        option_id="complete_redeploys",
        result_id="phase16b-complete-redeploys",
    )
    assert redeploy_lifecycle.state is not None
    assert any(
        record.action_kind is PreBattleActionKind.COMPLETE_REDEPLOYS
        for record in redeploy_lifecycle.state.prebattle_action_records
    )

    prebattle_lifecycle, prebattle_status = _advance_after_deployments(_scouts_config())
    prebattle_request = _decision_request(prebattle_status)
    assert prebattle_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    _submit_option(
        prebattle_lifecycle,
        request=prebattle_request,
        option_id="complete_prebattle_actions",
        result_id="phase16b-complete-prebattle",
    )
    assert prebattle_lifecycle.state is not None
    assert any(
        record.action_kind is PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS
        for record in prebattle_lifecycle.state.prebattle_action_records
    )
    restored_completion = GameLifecycle.from_payload(prebattle_lifecycle.to_payload())
    assert restored_completion.state == prebattle_lifecycle.state


def test_phase16b_scout_reserve_setup_uses_structured_proposal_and_validation() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    state = _manual_prebattle_state(catalog=catalog)
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )
    request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        player_id="player-b",
    )
    option = _option_for_prefix(request, "scout_reserve_setup:")
    selection_result = DecisionResult.for_request(
        result_id="phase16b-scout-reserve-select",
        request=request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        catalog=catalog,
        selection_request=request,
        result=selection_result,
    )
    proposal = PreBattlePlacementProposal.from_payload(
        cast(
            PreBattlePlacementProposalPayload,
            _prebattle_placement_payload(
                state=state,
                request_context=proposal_request,
                pose_factory=lambda index: Pose.at(
                    57.0 - ((index // 3) * 1.8),
                    32.0 + ((index % 3) * 1.8),
                    0.0,
                    facing_degrees=180.0,
                ),
            ),
        )
    )

    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        request=proposal_request,
        proposal=proposal,
    )
    assert resolution.is_valid
    assert resolution.transition_batch is not None
    assert len(resolution.transition_batch.placements) == 5

    invalid_proposal = replace(
        proposal,
        model_placements=tuple(
            placement.with_pose(Pose.at(28.0, placement.pose.position.y, 0.0))
            for placement in proposal.model_placements
        ),
    )
    invalid_resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        request=proposal_request,
        proposal=invalid_proposal,
    )
    assert not invalid_resolution.is_valid
    assert PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION in {
        violation.violation_code for violation in invalid_resolution.violations
    }


def test_phase16b_scout_reserve_setup_apply_records_arrival_action_and_event() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    state = _manual_prebattle_state(catalog=catalog)
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )
    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        player_id="player-b",
    )
    option = _option_for_prefix(selection_request, "scout_reserve_setup:")
    selection_result = DecisionResult.for_request(
        result_id="phase16b-apply-scout-reserve-select",
        request=selection_request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        catalog=catalog,
        selection_request=selection_request,
        result=selection_result,
    )
    request = proposal_request.to_decision_request()
    result = DecisionResult(
        result_id="phase16b-apply-scout-reserve-place",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=_prebattle_placement_payload(
            state=state,
            request_context=proposal_request,
            pose_factory=lambda index: Pose.at(
                57.0 - ((index // 3) * 1.8),
                32.0 + ((index % 3) * 1.8),
                0.0,
                facing_degrees=180.0,
            ),
        ),
    )
    decisions = DecisionController()

    resolution = apply_scout_reserve_setup(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
    )

    assert resolution.is_valid
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    reserve_state = state.reserve_state_for_unit("army-beta:intercessor-unit-2")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.ARRIVED
    assert reserve_state.arrived_phase == SetupStep.RESOLVE_PREBATTLE_ACTIONS.value
    records = tuple(
        record
        for record in state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.SCOUT_RESERVE_SETUP
    )
    assert len(records) == 1
    assert (
        records[0].to_payload()
        == PreBattleActionRecord.from_payload(records[0].to_payload()).to_payload()
    )
    assert "prebattle_scout_reserve_setup_completed" in (
        event.event_type for event in decisions.event_log.records
    )
    timing = prebattle_timing_state_for_state(state, army_catalog=catalog)
    assert timing.next_player_id is None
    validate_prebattle_alternation_restore(
        state=state,
        army_catalog=catalog,
        decision_records=(
            DecisionRecord(
                record_id="decision-record-000001",
                request=selection_request,
                result=selection_result,
            ),
            DecisionRecord(
                record_id="decision-record-000002",
                request=request,
                result=result,
            ),
        ),
        pending_decision_requests=(),
    )


def test_phase16b_prebattle_timing_and_proposal_payloads_are_replay_safe() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    state = _manual_prebattle_state(catalog=catalog)
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )

    timing = prebattle_timing_state_for_state(state, army_catalog=catalog)
    assert timing.next_player_id == "player-b"
    assert timing.to_payload()["available_action_count_by_player"] == {
        "player-a": 0,
        "player-b": 1,
    }
    with pytest.raises(GameLifecycleError, match="requires a pre-battle step"):
        PreBattleTimingWindowState(
            setup_step=SetupStep.DEPLOY_ARMIES,
            next_player_id=None,
            available_action_count_by_player={},
            completed_player_ids=(),
        )

    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        player_id="player-b",
    )
    selection_result = DecisionResult.for_request(
        result_id="phase16b-payload-scout-reserve-select",
        request=selection_request,
        selected_option_id=_option_for_prefix(
            selection_request,
            "scout_reserve_setup:",
        ).option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        catalog=catalog,
        selection_request=selection_request,
        result=selection_result,
    )
    payload = proposal_request.to_payload()
    assert PreBattleProposalRequest.from_payload(payload) == proposal_request
    request = proposal_request.to_decision_request()
    assert (
        PreBattleProposalRequest.from_decision_request_payload(request.payload) == proposal_request
    )
    request_payload_json = json.dumps(request.payload, sort_keys=True)
    assert "<" not in request_payload_json
    assert "object at 0x" not in request_payload_json

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        PreBattleProposalRequest.from_decision_request_payload(())
    with pytest.raises(GameLifecycleError, match="payload missing request"):
        PreBattleProposalRequest.from_decision_request_payload({})
    bad_payload = dict(payload)
    bad_payload["legal_deployment_zones"] = []
    with pytest.raises(GameLifecycleError, match="requires deployment zones"):
        PreBattleProposalRequest.from_payload(cast(PreBattleProposalRequestPayload, bad_payload))


def test_phase16b_prebattle_action_record_round_trips_and_rejects_invalid_tokens() -> None:
    record = PreBattleActionRecord(
        action_id="prebattle-action-000001",
        game_id="phase16b-game",
        player_id="player-a",
        setup_step=SetupStep.REDEPLOY_UNITS,
        action_kind=PreBattleActionKind.REDEPLOY,
        unit_instance_id="army-alpha:intercessor-unit-1",
        source_rule_id="core_rules:redeploy",
        request_id="decision-request-000001",
        result_id="decision-result-000001",
        payload={"is_valid": True},
    )

    assert PreBattleActionRecord.from_payload(record.to_payload()) == record
    assert (
        prebattle_action_kind_from_token(PreBattleActionKind.REDEPLOY)
        is PreBattleActionKind.REDEPLOY
    )
    assert (
        prebattle_violation_code_from_token(PreBattleViolationCode.UNIT_NOT_ELIGIBLE)
        is PreBattleViolationCode.UNIT_NOT_ELIGIBLE
    )
    scout_instance = ScoutAbilityInstance.from_payload(
        {
            "model_instance_id": "army-alpha:intercessor-unit-1:model-1",
            "distance_inches": 6,
            "source_id": "core_rules:scouts",
        }
    )
    assert scout_instance.to_payload()["distance_inches"] == 6.0

    with pytest.raises(GameLifecycleError, match="token must be a string"):
        prebattle_action_kind_from_token(3)
    with pytest.raises(GameLifecycleError, match="Unsupported PreBattleActionKind"):
        prebattle_action_kind_from_token("unsupported-action")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        prebattle_violation_code_from_token(None)
    with pytest.raises(GameLifecycleError, match="Unsupported PreBattleViolationCode"):
        prebattle_violation_code_from_token("unsupported-violation")

    bad_step_payload = record.to_payload()
    bad_step_payload["setup_step"] = cast(str, 3)
    with pytest.raises(GameLifecycleError, match="setup_step token must be a string"):
        PreBattleActionRecord.from_payload(bad_step_payload)

    bad_step_payload = record.to_payload()
    bad_step_payload["setup_step"] = "unsupported-step"
    with pytest.raises(GameLifecycleError, match="Unsupported setup step token"):
        PreBattleActionRecord.from_payload(bad_step_payload)

    with pytest.raises(GameLifecycleError, match="action_id must be a string"):
        PreBattleActionRecord(
            action_id=cast(str, 3),
            game_id="phase16b-game",
            player_id="player-a",
            setup_step=SetupStep.REDEPLOY_UNITS,
            action_kind=PreBattleActionKind.REDEPLOY,
            source_rule_id="core_rules:redeploy",
            request_id="decision-request-000001",
            result_id="decision-result-000001",
        )
    with pytest.raises(GameLifecycleError, match="action_id must not be empty"):
        PreBattleActionRecord(
            action_id=" ",
            game_id="phase16b-game",
            player_id="player-a",
            setup_step=SetupStep.REDEPLOY_UNITS,
            action_kind=PreBattleActionKind.REDEPLOY,
            source_rule_id="core_rules:redeploy",
            request_id="decision-request-000001",
            result_id="decision-result-000001",
        )
    with pytest.raises(GameLifecycleError, match="must be a positive finite number"):
        ScoutAbilityInstance(
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            distance_inches=0,
            source_id="core_rules:scouts",
        )


def test_phase16b_dedicated_transport_with_non_scout_cargo_is_ineligible() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-transport": ("Transport", "Vehicle", "DEDICATED_TRANSPORT")}
    )
    state = _manual_prebattle_state(
        catalog=catalog,
        player_b_unit_selections=(
            _unit_selection(unit_selection_id="intercessor-unit-2"),
            _unit_selection(
                unit_selection_id="transport-unit-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id="army-beta:transport-unit-1",
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("Infantry",),
            ),
            embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            disembarked_this_phase_unit_instance_ids=(),
        )
    )
    _place_unit(
        state,
        unit_instance_id="army-beta:transport-unit-1",
        pose_factory=lambda _index: Pose.at(55.0, 20.0, 0.0, facing_degrees=180.0),
    )

    assert (
        dedicated_transport_scout_move_candidates_for_player(
            state=state,
            army_catalog=catalog,
            player_id="player-b",
        )
        == ()
    )


@pytest.mark.parametrize("selected_distance", [6.0, 8.0])
def test_phase16b_dedicated_transport_scout_move_uses_cargo_scouts_and_records_action(
    selected_distance: float,
) -> None:
    catalog = _catalog_with_datasheet_keywords(
        {
            "core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS"),
            "core-transport": ("Transport", "Vehicle", "DEDICATED_TRANSPORT"),
        },
        scouts_distances_by_datasheet={"core-intercessor-like-infantry": (6.0, 8.0)},
    )
    state = _manual_prebattle_state(
        catalog=catalog,
        player_b_unit_selections=(
            _unit_selection(unit_selection_id="intercessor-unit-2"),
            _unit_selection(
                unit_selection_id="transport-unit-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id="army-beta:transport-unit-1",
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("Infantry",),
            ),
            embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            disembarked_this_phase_unit_instance_ids=(),
        )
    )
    _place_unit(
        state,
        unit_instance_id="army-beta:transport-unit-1",
        pose_factory=lambda _index: Pose.at(55.0, 20.0, 0.0, facing_degrees=180.0),
    )
    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        player_id="player-b",
    )
    options = tuple(
        option
        for option in selection_request.options
        if option.option_id.startswith("dedicated_transport_scout_move:")
    )
    assert len(options) == 2
    option = next(
        option
        for option in options
        if isinstance(option.payload, dict)
        and option.payload["scout_distance_inches"] == selected_distance
    )
    selection_result = DecisionResult.for_request(
        result_id="phase16b-dedicated-transport-select",
        request=selection_request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        catalog=catalog,
        selection_request=selection_request,
        result=selection_result,
    )
    assert proposal_request.action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE
    assert proposal_request.scout_distance_inches == selected_distance
    if proposal_request.scout_distance_inches is None:
        raise GameLifecycleError("Dedicated Transport Scout Move requires scout_distance_inches.")
    request = proposal_request.to_decision_request()
    result = DecisionResult(
        result_id="phase16b-dedicated-transport-scout",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            ScoutMoveProposal(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                game_id=proposal_request.game_id,
                ruleset_descriptor_hash=proposal_request.ruleset_descriptor_hash,
                setup_step=proposal_request.setup_step,
                player_id=proposal_request.player_id,
                unit_instance_id=proposal_request.unit_instance_id,
                action_kind=proposal_request.action_kind,
                source_rule_id=proposal_request.source_rule_id,
                scout_distance_inches=proposal_request.scout_distance_inches,
                witness=_scout_move_witness(state, request=request),
                context=proposal_request.context,
            ).to_payload()
        ),
    )
    decisions = DecisionController()

    resolution = apply_scout_move(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
    )

    assert resolution.is_valid
    records = tuple(
        record
        for record in state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE
    )
    assert len(records) == 1
    assert records[0].unit_instance_id == "army-beta:transport-unit-1"
    assert "prebattle_scout_move_completed" in (
        event.event_type for event in decisions.event_log.records
    )


__all__: list[str] = []
__all__ += ["AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["ArmyMusterRequest", "BattlefieldTransitionBatch", "Callable"]
__all__ += ["CatalogAbilitySourceKind", "CatalogAbilitySupport", "DatasheetAbilityDescriptor"]
__all__ += ["DatasheetDefinition", "DatasheetKeywordSet", "DetachmentSelection", "DiceExpression"]
__all__ += ["DiceRollManager", "DiceRollSpec", "EventRecord", "GameConfig", "GameState"]
__all__ += ["LifecycleStatus", "MissionSetup", "ModelProfileSelection", "PathWitness"]
__all__ += ["SCOUT_MOVE_PROPOSAL_KIND", "SECONDARY_MISSION_DECISION_TYPE", "RulesetDescriptor"]
__all__ += ["SELECT_DEPLOYMENT_UNIT_DECISION_TYPE", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "UnitInstance"]
__all__ += ["UnitMusterSelection", "_PoseFactory", "_advance_to_first_deployment_selection"]
__all__ += ["_army_muster_request", "_army_muster_requests", "_mission_setup"]
__all__ += ["_model_source_for_id", "_redeploy_broken_coherency_pose"]
__all__ += ["_redeploy_illegal_zone_pose", "_redeploy_overlap_pose"]
__all__ += ["_scouts_ability_descriptors", "_terrain_endpoint_feature"]
__all__ += ["_witness_with_first_start_drift"]
__all__ += ["authoritative_battlefield_transition_batch_or_none"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["invalid_prebattle_proposal_status", "leading_first_translation_paths", "muster_army"]
__all__ += ["pending_alternating_scout_after_first_action_payload"]
__all__ += ["redeploy_timing_state_for_state"]
