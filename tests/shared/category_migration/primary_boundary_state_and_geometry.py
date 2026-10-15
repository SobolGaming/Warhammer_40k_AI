from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_boundary_lifecycle_bindings import (
    _OC_SOURCE_RULE_ID,
    PARAMETERIZED_DECISION_OPTION_ID,
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    BattlePhase,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DestructionSourceKind,
    DiceExpression,
    DiceRollManager,
    DiceRollResult,
    DiceRollSpec,
    GameLifecycle,
    GameLifecyclePayload,
    GameState,
    JsonValue,
    ModelDestructionAttribution,
    ModelPlacement,
    ObjectiveControlRecord,
    ObjectiveMarkerRole,
    PendingReturnOnDeath,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    RulesetDescriptor,
    StickyObjectiveControlState,
    UnitInstance,
    UnitPlacement,
    VictoryPointSourceKind,
    append_authenticated_normal_move,
    apply_return_on_death_placement_decision,
    bound_primary_scoring_commit_checkpoint,
    canonical_json,
    cast,
    deepcopy,
    json_loads,
    mark_pending_primary_scoring_boundaries,
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    record_primary_turn_start_evidence_for_fixture,
    replace,
    rules_unit_objective_proximity_witness,
    validate_json_value,
    with_model_offsets,
    with_unit_keywords,
)


def _swap_secondary_scoring_evidence_bindings(
    first: dict[str, object],
    second: dict[str, object],
) -> None:
    first_metadata = _json_object(first["metadata"], label="first secondary metadata")
    second_metadata = _json_object(second["metadata"], label="second secondary metadata")
    for key in (
        SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
        SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    ):
        first_value = first_metadata[key]
        second_value = second_metadata[key]
        assert isinstance(first_value, str)
        assert isinstance(second_value, str)
        first_metadata[key] = second_value
        second_metadata[key] = first_value


def _replace_secondary_scoring_evidence_binding_from_payload(
    *,
    target_payload: GameLifecyclePayload,
    target_transaction: dict[str, object],
    donor_payload: GameLifecyclePayload,
    donor_transaction: dict[str, object],
) -> None:
    target_metadata = _json_object(
        target_transaction["metadata"],
        label="target secondary metadata",
    )
    donor_metadata = _json_object(
        donor_transaction["metadata"],
        label="donor secondary metadata",
    )
    donor_evidence_id = donor_metadata[SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY]
    donor_evidence_hash = donor_metadata[SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY]
    assert isinstance(donor_evidence_id, str)
    assert isinstance(donor_evidence_hash, str)
    donor_state = _json_object(donor_payload["state"], label="donor lifecycle state")
    donor_records = _json_list(
        donor_state["secondary_scoring_state_evidence_records"],
        label="donor secondary scoring evidence records",
    )
    matches = tuple(
        record
        for record in donor_records
        if _json_object(record, label="donor secondary scoring evidence")["evidence_id"]
        == donor_evidence_id
    )
    if len(matches) != 1:
        raise AssertionError("donor secondary scoring evidence was not found")
    target_state = _json_object(target_payload["state"], label="target lifecycle state")
    target_records = _json_list(
        target_state["secondary_scoring_state_evidence_records"],
        label="target secondary scoring evidence records",
    )
    target_records.append(deepcopy(matches[0]))
    target_metadata[SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY] = donor_evidence_id
    target_metadata[SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY] = donor_evidence_hash


def _queue_pending_window(*, lifecycle: GameLifecycle, pending_window: str) -> None:
    state = lifecycle.state
    assert state is not None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
        actor_id=state.active_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "pending_window": pending_window,
            }
        ),
        options=(DecisionOption(option_id="continue", label="continue"),),
    )
    lifecycle.decision_controller.request_decision(request)
    mark_pending_primary_scoring_boundaries(
        state=state,
        pending_window=pending_window,
        pending_decision_request_id=request.request_id,
    )


def _emit_oc_event(*, decisions: DecisionController, record: ObjectiveControlRecord) -> None:
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": _OC_SOURCE_RULE_ID,
        },
    )


def _place_player_on_role(
    state: GameState,
    *,
    player_id: str,
    role: ObjectiveMarkerRole,
) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is role
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
        )
    )


def _first_unit(state: GameState, *, player_id: str) -> UnitInstance:
    return next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )


def _zone_anchor_away_from_home(state: GameState, *, zone_player_id: str) -> tuple[float, float]:
    assert state.mission_setup is not None
    zone = next(
        candidate
        for candidate in state.mission_setup.deployment_zones
        if candidate.player_id == zone_player_id
    )
    home_role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if zone_player_id == "player-a"
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    home = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is home_role
    )
    corners = (
        (zone.min_x + 2.0, zone.min_y + 2.0),
        (zone.max_x - 2.0, zone.min_y + 2.0),
        (zone.min_x + 2.0, zone.max_y - 2.0),
        (zone.max_x - 2.0, zone.max_y - 2.0),
    )
    target = max(
        corners,
        key=lambda point: (point[0] - home.x_inches) ** 2 + (point[1] - home.y_inches) ** 2,
    )
    assert zone.contains_point(target[0], target[1])
    return target


def _place_in_player_deployment_zone_away_from_home(
    state: GameState,
    *,
    moving_player_id: str,
    zone_player_id: str,
) -> None:
    assert state.battlefield_state is not None
    target = _zone_anchor_away_from_home(state, zone_player_id=zone_player_id)
    unit = _first_unit(state, player_id=moving_player_id)
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    offsets = ((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8))
    updated: list[ModelPlacement] = []
    for index, model_placement in enumerate(placement.model_placements):
        dx, dy = offsets[index] if index < len(offsets) else (0.0, 0.0)
        updated.append(
            model_placement.with_pose(
                Pose.at(
                    target[0] + dx,
                    target[1] + dy,
                    model_placement.pose.position.z,
                    facing_degrees=model_placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(tuple(updated))
    )


def _authenticated_move_unit_to(
    *,
    lifecycle: GameLifecycle,
    unit_instance_id: str,
    x: float,
    y: float,
    suffix: str,
) -> None:
    state = lifecycle.state
    assert state is not None
    append_authenticated_normal_move(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=unit_instance_id,
        suffix=suffix,
        pose_transform=lambda pose: Pose.at(
            x,
            y,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )


def _place_unit_interior_non_overlapping(state: GameState, *, unit_instance_id: str) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (0.0, 2.0), (2.0, 2.0)),
        )
    )


def _place_player_away_from_objectives(state: GameState, *, player_id: str) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((18.0, 18.0), (18.8, 18.0), (19.6, 18.0), (18.0, 18.8), (18.8, 18.8)),
        )
    )


def _destroy_first_model(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
) -> None:
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    model = unit.own_models[0]
    _destroy_model_with_event(
        state=state,
        decisions=decisions,
        model_instance_id=model.model_instance_id,
    )


def _destroy_all_models(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
) -> None:
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    for model in tuple(unit.own_models):
        _destroy_model_with_event(
            state=state,
            decisions=decisions,
            model_instance_id=model.model_instance_id,
        )


def _destroy_model_with_event(
    *,
    state: GameState,
    decisions: DecisionController,
    model_instance_id: str,
) -> None:
    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture

    assert state.active_player_id is not None
    destroy_rule_model_for_fixture(
        state=state,
        decisions=decisions,
        model_id=model_instance_id,
        destroying_player_id=state.active_player_id,
        source_unit_id=None,
        source_model_id=None,
    )


def _destroy_unit_with_events(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    return_model_only: bool = False,
    leave_surviving_model: bool = False,
) -> UnitPlacement:
    assert state.battlefield_state is not None
    assert state.active_player_id is not None
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    original_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    source_unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-a"
        for candidate in army.units
    )
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=source_unit.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_unit.own_models[0].model_instance_id,
    )
    destroyed_events: list[str] = []
    departures: list[PrimaryBattlefieldDepartureState] = []
    models_to_destroy = unit.own_models[:1] if leave_surviving_model else unit.own_models
    for model in models_to_destroy:
        from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture

        event = destroy_rule_model_for_fixture(
            state=state,
            decisions=decisions,
            model_id=model.model_instance_id,
            destroying_player_id="player-a",
            source_unit_id=source_unit.unit_instance_id,
            source_model_id=source_unit.own_models[0].model_instance_id,
        )
        destroyed_events.append(event.event_id)
        model_departures = record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model.model_instance_id,),
            source_id=f"core-rules:primary-unit-destruction-tracking:{event.event_id}",
            occurrence_id=event.event_id,
        )
        departures.extend(model_departures)
        for departure in model_departures:
            record_primary_battlefield_departure_event(
                event_log=decisions.event_log,
                departure=departure,
            )
    if not leave_surviving_model:
        last_event_id = destroyed_events[-1]
        source_id = f"core-rules:primary-unit-destruction-tracking:{last_event_id}"
        destruction_ids_before = tuple(
            destruction.destruction_id for destruction in state.primary_unit_destruction_states
        )
        state.record_primary_unit_destruction(
            destruction_attribution=attribution,
            source_model_destroyed_event_id=last_event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            source_battlefield_departure_ids=tuple(
                departure.departure_id for departure in departures
            ),
            unattributed_cause=None,
            source_mutation_id=None,
            destroyed_unit_instance_id=unit.unit_instance_id,
            source_id=f"{source_id}:{unit.unit_instance_id}",
        )
        record_new_primary_unit_destruction_events(
            state=state,
            event_log=decisions.event_log,
            destruction_ids_before=destruction_ids_before,
        )
    first_model = original_placement.model_placements[0]
    pending = PendingReturnOnDeath(
        pending_id="p2-return-on-death-pending",
        source_rule_id="p2-return-on-death-rule",
        source_ability_id="p2-return-on-death-ability",
        source_clause_id="p2-return-on-death-clause",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=(
            ReturnDestroyedTargetScope.DESTROYED_MODEL
            if return_model_only
            else ReturnDestroyedTargetScope.DESTROYED_UNIT
        ),
        destroyed_unit_instance_id=unit_instance_id,
        destroyed_model_instance_id=(first_model.model_instance_id if return_model_only else None),
        destroyed_position_payload=validate_json_value(
            {
                "source": "model_destroyed_event",
                "model_destroyed_event_id": destroyed_events[0],
                "model_destroyed_payload": {
                    "model_instance_id": first_model.model_instance_id,
                    "destroyed_model_placement": first_model.to_payload(),
                },
            }
        ),
        trigger_battle_round=state.battle_round,
        trigger_phase=BattlePhase.COMMAND.value,
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=2,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
        wounds_remaining=None,
        resolved=False,
    )
    state.record_pending_return_on_death(pending)
    stored = state.pending_return_on_death_by_id(pending.pending_id)
    decisions.event_log.append(
        RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "model_destroyed_event_id": destroyed_events[0],
            "pending": stored.to_payload(),
        },
    )
    return original_placement


def _return_destroyed_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    original_placement: UnitPlacement,
    return_model_only: bool = False,
) -> None:
    from warhammer40k_core.engine.return_on_death import resolve_return_on_death_occurrence

    pending = state.pending_return_on_death_by_id("p2-return-on-death-pending")
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="p2-return-on-death-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="return_on_death_phase_end_gate",
                    roll_type="return_on_death",
                    actor_id=pending.owner_player_id,
                    reroll_forbidden_rule_ids=(pending.source_rule_id,),
                ),
                values=(6,),
                source="injected",
            ),
        ),
    )
    request = resolve_return_on_death_occurrence(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        pending=pending,
    )
    assert isinstance(request, DecisionRequest)
    decisions.request_decision(request)
    attempted_placement = (
        original_placement.with_model_placements((original_placement.model_placements[0],))
        if return_model_only
        else original_placement
    )
    result = DecisionResult(
        result_id=f"{request.request_id}-placement-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": attempted_placement.to_payload(),
            }
        ),
    )
    decisions.submit_result(result)
    apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )


def _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle: GameLifecycle) -> None:
    state = lifecycle.state
    assert state is not None
    record = state.objective_control_records[-1]
    authority = next(
        candidate
        for candidate in state.objective_control_record_authorities
        if candidate.objective_control_record_id == record.record_id
    )
    commit = bound_primary_scoring_commit_checkpoint(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = state.primary_scoring_state_evidence_records[-1]
    assert evidence.scoring_commit_checkpoint_id == commit.checkpoint_id
    assert authority.boundary_checkpoint.model_states != commit.model_states


def _offset_checkpoint_model_state(
    row: PrimaryMissionBoundaryModelState,
) -> PrimaryMissionBoundaryModelState:
    placement_json = row.model_placement_json
    if placement_json is None:
        return row
    placement = ModelPlacement.from_payload(json_loads(placement_json))
    moved = placement.with_pose(
        Pose.at(
            placement.pose.position.x,
            placement.pose.position.y + 12.0,
            placement.pose.position.z,
            facing_degrees=placement.pose.facing.degrees,
        )
    )
    return replace(row, model_placement_json=canonical_json(moved.to_payload()))


def _checkpoint_with_model_states(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    model_states: tuple[PrimaryMissionBoundaryModelState, ...],
) -> PrimaryMissionBoundaryCheckpoint:
    return PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=model_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_card_jsons=checkpoint.active_secondary_mission_card_jsons,
        completed_mission_action_state_jsons=checkpoint.completed_mission_action_state_jsons,
        primary_unit_destruction_state_jsons=checkpoint.primary_unit_destruction_state_jsons,
        starting_strength_record_jsons=checkpoint.starting_strength_record_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )


def _json_object(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise AssertionError(f"{label} must be a JSON object.")
    return cast(dict[str, object], value)


def _json_map(value: object, *, label: str) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], _json_object(value, label=label))


def _json_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise AssertionError(f"{label} must be a JSON list.")
    return cast(list[object], value)


def _tactical_secondary_amount(
    state: GameState,
    *,
    player_id: str,
    secondary_mission_id: str,
) -> int:
    ledger = state.victory_point_ledger_for_player(player_id)
    amounts = tuple(
        transaction.amount
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
        and transaction.source_id == secondary_mission_id
    )
    assert len(amounts) == 1
    return amounts[0]


def _sticky_state_for(
    state: GameState,
    *,
    player_id: str,
    objective_id: str,
    active_player_id: str,
) -> StickyObjectiveControlState:
    originating = next(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    )
    destroyed = next(
        unit
        for army in state.army_definitions
        if army.player_id != player_id
        for unit in army.units
    )
    return StickyObjectiveControlState(
        state_id=f"p2-sticky-{player_id}-{objective_id}",
        game_id=state.game_id,
        player_id=player_id,
        objective_id=objective_id,
        source_rule_id="p2-sticky-source",
        source_event_id="p2-sticky-event",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        active_player_id=active_player_id,
        originating_unit_instance_id=originating.unit_instance_id,
        destroyed_unit_instance_id=destroyed.unit_instance_id,
        replay_payload={"source": "p2-sticky"},
    )


def _set_unit_starting_wounds(state: GameState, unit_instance_id: str, *, wounds: int) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = list(army.units)
        for unit_index, unit in enumerate(units):
            if unit.unit_instance_id != unit_instance_id:
                continue
            units[unit_index] = replace(
                unit,
                own_models=tuple(
                    replace(model, starting_wounds=wounds, wounds_remaining=wounds)
                    for model in unit.own_models
                ),
            )
            state.army_definitions[army_index] = replace(army, units=tuple(units))
            return
    raise AssertionError(f"unit {unit_instance_id} was not found")


def _add_unit_keyword(state: GameState, unit_instance_id: str, *, keyword: str) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = list(army.units)
        for unit_index, unit in enumerate(units):
            if unit.unit_instance_id != unit_instance_id:
                continue
            units[unit_index] = with_unit_keywords(
                unit, keywords=tuple(sorted({*unit.keywords, keyword}))
            )
            state.army_definitions[army_index] = replace(army, units=tuple(units))
            return
    raise AssertionError(f"unit {unit_instance_id} was not found")


__all__: list[str] = []
__all__ += ["BattlePhase", "DecisionController", "DecisionOption", "DecisionRequest"]
__all__ += ["DecisionResult", "DestructionSourceKind", "DiceExpression", "DiceRollManager"]
__all__ += ["DiceRollResult", "DiceRollSpec", "GameLifecycle", "GameLifecyclePayload"]
__all__ += ["GameState", "JsonValue", "ModelDestructionAttribution", "ModelPlacement"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "ObjectiveControlRecord", "ObjectiveMarkerRole"]
__all__ += ["PendingReturnOnDeath", "Pose", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryMissionBoundaryCheckpoint", "PrimaryMissionBoundaryModelState"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE", "ReturnDestroyedTargetScope"]
__all__ += ["ReturnRestoreWoundsMode", "RulesetDescriptor"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "StickyObjectiveControlState"]
__all__ += ["_OC_SOURCE_RULE_ID", "UnitInstance", "UnitPlacement", "VictoryPointSourceKind"]
__all__ += ["_add_unit_keyword", "_assert_scoring_commit_differs_from_oc_checkpoint"]
__all__ += ["_authenticated_move_unit_to", "_checkpoint_with_model_states", "_destroy_all_models"]
__all__ += ["_destroy_first_model", "_destroy_model_with_event", "_destroy_unit_with_events"]
__all__ += ["_emit_oc_event", "_first_unit", "_json_list", "_json_map", "_json_object"]
__all__ += ["_offset_checkpoint_model_state", "_place_in_player_deployment_zone_away_from_home"]
__all__ += ["_place_player_away_from_objectives", "_place_player_on_role"]
__all__ += ["_place_unit_interior_non_overlapping", "_queue_pending_window"]
__all__ += ["_replace_secondary_scoring_evidence_binding_from_payload", "_return_destroyed_unit"]
__all__ += ["_set_unit_starting_wounds", "_sticky_state_for"]
__all__ += ["_swap_secondary_scoring_evidence_bindings", "_tactical_secondary_amount"]
__all__ += ["_zone_anchor_away_from_home", "append_authenticated_normal_move"]
__all__ += ["apply_return_on_death_placement_decision", "bound_primary_scoring_commit_checkpoint"]
__all__ += ["canonical_json", "cast", "deepcopy", "json_loads"]
__all__ += ["mark_pending_primary_scoring_boundaries"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures"]
__all__ += ["record_primary_turn_start_evidence_for_fixture", "replace"]
__all__ += ["rules_unit_objective_proximity_witness", "validate_json_value", "with_model_offsets"]
__all__ += ["with_unit_keywords"]
