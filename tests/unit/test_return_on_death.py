from __future__ import annotations

from typing import cast

from tests.shared.category_migration.return_on_death import (
    FIRST_DEATH_RETURN_TEXT,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    PARAMETERIZED_DECISION_OPTION_ID,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlePhase,
    Callable,
    CatalogReturnOnDeathRuntime,
    DamageKind,
    DecisionController,
    DecisionRequest,
    DecisionResult,
    DestructionSourceKind,
    DetachmentSelection,
    DiceExpression,
    DiceRollManager,
    DiceRollResult,
    DiceRollSpec,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    ModelPlacement,
    ModelProfileSelection,
    MortalWoundDestructionEvidence,
    ObjectiveRuleScope,
    PendingReturnOnDeath,
    PhaseEndObjectiveControlContext,
    Pose,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    RulesetDescriptor,
    RuleSourceText,
    RulesUnitObjectiveProximityWitness,
    RuntimeModifierRegistry,
    TimingTriggerKind,
    UnitDestroyedContext,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    _battle_state_with_destroyed_beta_unit,
    _battle_state_with_scenario,
    _beta_unit,
    _destroyed_model_placement_for_model,
    _destroyed_position_payload_for_model,
    _destroyed_position_payload_for_placement,
    _destroyed_position_payload_for_placement_payload,
    _first_alpha_model_pose,
    _muster_request,
    _mustered_armies,
    _pending_return_on_death,
    _placement_result,
    _record_return_captures,
    _return_on_death_record,
    _roll_result,
    _set_model_wounds,
    _set_unit_wounds,
    _unit_placement_at_destroyed_position,
    _unit_placement_for_model_at_destroyed_position,
    _unit_placement_for_unit,
    apply_damage_to_model,
    apply_direct_mortal_wounds_to_unit,
    apply_return_on_death_placement_decision,
    assert_parameterized_projection,
    build_return_on_death_placement_request,
    catalog_return_on_death_runtime_module,
    catalog_rule_clauses_from_record,
    compile_rule_source_text,
    create_deterministic_battlefield_scenario,
    datasheet_keyword_lexicon_source,
    initial_command_point_ledgers,
    initial_victory_point_ledgers,
    invalid_return_on_death_placement_status,
    muster_army,
    pytest,
    replace,
    resolve_return_phase_end_candidates,
    return_on_death_module,
)


def test_return_on_death_success_requests_placement_and_rejects_invalid_submission() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=2)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(_roll_result(pending=pending, value=6),),
    )

    request = resolve_return_phase_end_candidates(
        state=state,
        decisions=decisions,
        dice_manager=manager,
    )

    assert isinstance(request, DecisionRequest)
    assert request.decision_type == SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE
    alpha_pose = _first_alpha_model_pose(state)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(
            state=state,
            unit=_beta_unit(state),
            x=alpha_pose.position.x,
            y=alpha_pose.position.y,
        ),
    )
    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None
    assert not state.pending_return_on_death_by_id(pending.pending_id).resolved


@pytest.mark.parametrize("turn_player", ["player-a", "player-b"])
def test_return_on_death_full_health_restores_unit_and_battlefield_placement(
    turn_player: str,
) -> None:
    state = _battle_state_with_destroyed_beta_unit()
    state.active_player_id = turn_player
    pending = _pending_return_on_death(state=state, success_threshold=2)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    request = build_return_on_death_placement_request(state=state, pending=pending)
    decisions.request_decision(request)
    assert_parameterized_projection(GameLifecycle(state=state, decision_controller=decisions))
    result = _placement_result(
        request=request,
        placement=_unit_placement_at_destroyed_position(state=state, unit=_beta_unit(state)),
    )
    decisions.submit_result(result)

    resolved = apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert resolved.resolved
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.phase_movement_history import validate_phase_movement_history

    (setup,) = state.phase_movement_history
    assert setup.setup_kind is BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD
    assert setup.turn_player_id == turn_player
    validate_phase_movement_history(state=state, events=decisions.event_log.records)
    state.phase_movement_history.clear()
    with pytest.raises(GameLifecycleError, match="history differs"):
        validate_phase_movement_history(state=state, events=decisions.event_log.records)
    state.phase_movement_history.append(setup)
    from warhammer40k_core.engine.phase_movement_history import completion_phase_record

    event = decisions.event_log.records[-1]
    assert isinstance(event.payload, dict)
    for field, message in (
        ("unit_set_up", "unit presence evidence"),
        ("placement", "placement evidence"),
    ):
        altered = replace(event, payload={**event.payload, field: None})
        with pytest.raises(GameLifecycleError, match=message):
            completion_phase_record(state=state, event=altered, turn_player_id=turn_player)
    assert all(
        model.current_wounds == model.initial_wounds for model in _beta_unit(state).own_models
    )
    assert state.battlefield_state is not None
    assert not (
        set(_beta_unit(state).own_model_ids()) & set(state.battlefield_state.removed_model_ids)
    )


def test_return_on_death_rejects_far_placement_when_destroyed_position_is_legal() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=2)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0),
    )

    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None
    assert state.battlefield_state is not None
    assert set(_beta_unit(state).own_model_ids()) <= set(state.battlefield_state.removed_model_ids)


def test_return_on_death_rejects_far_placement_when_illegal_anchor_has_closer_candidate() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    anchor = _destroyed_model_placement_for_model(
        model_instance_id=beta.own_models[0].model_instance_id,
    ).with_pose(_first_alpha_model_pose(state))
    pending = replace(
        _pending_return_on_death(state=state, success_threshold=2),
        destroyed_position_payload=_destroyed_position_payload_for_placement(anchor),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    assert return_on_death_module._model_placement_within_enemy_engagement_range(  # pyright: ignore[reportPrivateUsage]
        state=state,
        model_placement=anchor,
        ruleset_descriptor=descriptor,
        owner_player_id=pending.owner_player_id,
    )
    closest = return_on_death_module._nearest_legal_destroyed_anchor_candidate(  # pyright: ignore[reportPrivateUsage]
        state=state,
        anchor=anchor,
        ruleset_descriptor=descriptor,
        owner_player_id=pending.owner_player_id,
    )
    far_placement = _unit_placement_for_unit(state=state, unit=beta, x=20.0, y=20.0)
    far_anchor = return_on_death_module._placement_for_model(  # pyright: ignore[reportPrivateUsage]
        placement=far_placement,
        model_instance_id=anchor.model_instance_id,
    )
    assert closest is not None
    assert closest.pose.distance_2d_to(anchor.pose) < far_anchor.pose.distance_2d_to(anchor.pose)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    result = _placement_result(request=request, placement=far_placement)

    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=descriptor,
    )

    assert status is not None
    assert state.battlefield_state is not None
    assert set(beta.own_model_ids()) <= set(state.battlefield_state.removed_model_ids)


def test_return_on_death_catalog_helpers_reject_malformed_runtime_shapes() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    record = _return_on_death_record()
    clause = catalog_rule_clauses_from_record(record)[0]
    current_phase = state.current_battle_phase
    assert current_phase is not None
    destroyed_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": current_phase.value,
        "destroying_player_id": "player-a",
        "target_unit_instance_id": beta.unit_instance_id,
        "model_instance_id": beta.own_models[0].model_instance_id,
        "destroyed_model_placement": {"source": "catalog-helper-test"},
    }

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        catalog_return_on_death_runtime_module._pending_return_on_death_for_event(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            completed_phase=current_phase.value,
            model_destroyed_event_id="event:bad-state",
            model_destroyed_payload=destroyed_payload,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id=beta.unit_instance_id,
            record=record,
            clause=clause,
        )
    with pytest.raises(GameLifecycleError, match="missing return effect"):
        catalog_return_on_death_runtime_module._return_effect_parameters(  # pyright: ignore[reportPrivateUsage]
            replace(clause, effects=())
        )
    with pytest.raises(GameLifecycleError, match="missing dice gate"):
        catalog_return_on_death_runtime_module._roll_gate_parameters(  # pyright: ignore[reportPrivateUsage]
            replace(clause, conditions=())
        )
    with pytest.raises(GameLifecycleError, match="missing trigger"):
        catalog_return_on_death_runtime_module._target_scope_for_trigger(  # pyright: ignore[reportPrivateUsage]
            replace(clause, trigger=None)
        )

    pending = catalog_return_on_death_runtime_module._pending_return_on_death_for_event(  # pyright: ignore[reportPrivateUsage]
        state=state,
        completed_phase=current_phase.value,
        model_destroyed_event_id="event:pending",
        model_destroyed_payload=destroyed_payload,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id=beta.unit_instance_id,
        record=record,
        clause=clause,
    )
    assert pending is not None
    state.return_on_death_consumed_keys.append(pending.consumed_key())
    assert not catalog_return_on_death_runtime_module.record_pending_return_on_death(
        pending=pending,
        event_log=DecisionController().event_log,
        state=state,
        phase=current_phase.value,
        model_destroyed_event_id="event:pending",
    )
    with pytest.raises(GameLifecycleError, match="capture requires GameState"):
        catalog_return_on_death_runtime_module.record_pending_return_on_death(
            pending=pending,
            event_log=DecisionController().event_log,
            state=object(),
            phase=current_phase.value,
            model_destroyed_event_id="event:pending",
        )
    with pytest.raises(GameLifecycleError, match="phase-end capture requires context"):
        catalog_return_on_death_runtime_module._model_destroyed_events_for_phase(  # pyright: ignore[reportPrivateUsage]
            cast(PhaseEndObjectiveControlContext, object())
        )
    with pytest.raises(GameLifecycleError, match="could not find destroyed unit"):
        catalog_return_on_death_runtime_module._army_and_unit_for_unit_id(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )
    with pytest.raises(GameLifecycleError, match="could not find destroyed model"):
        catalog_return_on_death_runtime_module._model_by_id(  # pyright: ignore[reportPrivateUsage]
            unit=beta,
            model_instance_id="model:missing",
        )

    assert not catalog_return_on_death_runtime_module._record_source_matches_destroyed_target(  # pyright: ignore[reportPrivateUsage]
        record=AbilityCatalogRecord(
            record_id="record:core-return",
            definition=record.definition,
            source_kind=AbilitySourceKind.CORE,
        ),
        unit=beta,
        destroyed_model_instance_id=beta.own_models[0].model_instance_id,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
    )
    assert not catalog_return_on_death_runtime_module._record_source_matches_destroyed_target(  # pyright: ignore[reportPrivateUsage]
        record=AbilityCatalogRecord(
            record_id="record:wargear-return",
            definition=record.definition,
            source_kind=AbilitySourceKind.WARGEAR,
            datasheet_id=beta.datasheet_id,
            wargear_id="wargear:missing",
        ),
        unit=beta,
        destroyed_model_instance_id=beta.own_models[0].model_instance_id,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
    )


def test_return_on_death_placement_validation_rejects_wrong_target_shapes() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(
        state=state,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
        restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
        wounds_remaining=1,
    )
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0),
    )

    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None


def test_mortal_wound_destruction_preserves_placement_through_return_on_death() -> None:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    destroyed_model = beta.own_models[0]
    source_unit = state.army_definitions[0].units[0]
    assert state.battlefield_state is not None
    destroyed_placement = state.battlefield_state.model_placement_by_id(
        destroyed_model.model_instance_id
    )
    decisions = DecisionController()
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=beta.unit_instance_id,
        model_instance_id=destroyed_model.model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )

    application = apply_direct_mortal_wounds_to_unit(
        state=state,
        decisions=decisions,
        application_id="application:return-on-death:mortal-wounds",
        source_rule_id="rule:return-on-death:mortal-wounds",
        source_context={"source_kind": "return_on_death_regression"},
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id="player-a",
            source_rules_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_unit.own_models[0].model_instance_id,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.COMMAND,
            source_step="return_on_death_regression",
        ),
        target_unit_instance_id=beta.unit_instance_id,
        mortal_wounds=destroyed_model.current_wounds,
        spill_over=False,
    )

    assert application.applications[-1].destroyed
    model_destroyed_event = next(
        record
        for record in decisions.event_log.records
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload).get("model_instance_id")
        == destroyed_model.model_instance_id
    )
    model_destroyed_payload = cast(dict[str, JsonValue], model_destroyed_event.payload)
    assert model_destroyed_payload["destroyed_model_placement"] == (
        destroyed_placement.to_payload()
    )
    source_witness = RulesUnitObjectiveProximityWitness.from_payload(
        model_destroyed_payload["source_rules_unit_objective_proximity_witness"]
    )
    destroyed_witness = RulesUnitObjectiveProximityWitness.from_payload(
        model_destroyed_payload["destroyed_rules_unit_objective_proximity_witness"]
    )
    assert source_witness.rules_unit_instance_id == source_unit.unit_instance_id
    assert source_witness.component_unit_instance_ids == (source_unit.unit_instance_id,)
    assert destroyed_witness.rules_unit_instance_id == beta.unit_instance_id
    assert destroyed_witness.component_unit_instance_ids == (beta.unit_instance_id,)

    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records(
                (_return_on_death_record(wounds_remaining=1),)
            )
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is BattlePhase.COMMAND
    _record_return_captures(
        runtime,
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=decisions.event_log,
            completed_phase=current_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ),
    )
    assert len(state.pending_return_on_death) == 1
    pending = state.pending_return_on_death[0]
    request = resolve_return_phase_end_candidates(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(
            state.game_id,
            event_log=decisions.event_log,
            injected_results=(_roll_result(pending=pending, value=6),),
        ),
    )
    assert isinstance(request, DecisionRequest)
    placement = UnitPlacement(
        army_id=destroyed_placement.army_id,
        player_id=destroyed_placement.player_id,
        unit_instance_id=destroyed_placement.unit_instance_id,
        model_placements=(destroyed_placement,),
    )

    result = _placement_result(request=request, placement=placement)
    decisions.submit_result(result)
    resolved = apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert resolved.resolved
    assert (
        state.battlefield_state.model_placement_by_id(destroyed_model.model_instance_id)
        == destroyed_placement
    )
    returned_model = next(
        model
        for model in _beta_unit(state).own_models
        if model.model_instance_id == destroyed_model.model_instance_id
    )
    assert returned_model.is_alive
    assert returned_model.current_wounds == 1


__all__: list[str] = []
__all__ += ["AbilityDefinition", "AbilityTimingDescriptor", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["ArmyMusterRequest", "Callable", "DecisionResult", "DetachmentSelection"]
__all__ += ["FIRST_DEATH_RETURN_TEXT", "DiceExpression", "DiceRollResult", "DiceRollSpec"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameLifecycleStage", "GameState"]
__all__ += ["ModelPlacement", "ModelProfileSelection", "ObjectiveRuleScope"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "PendingReturnOnDeath", "Pose", "RuleSourceText"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "TimingTriggerKind", "UnitDestroyedContext"]
__all__ += ["UnitInstance", "UnitMusterSelection", "_destroyed_position_payload_for_model"]
__all__ += ["_destroyed_position_payload_for_placement_payload", "_muster_request"]
__all__ += ["_mustered_armies", "_set_model_wounds", "_set_unit_wounds"]
__all__ += ["_unit_placement_for_model_at_destroyed_position", "compile_rule_source_text"]
__all__ += ["create_deterministic_battlefield_scenario", "datasheet_keyword_lexicon_source"]
__all__ += ["initial_command_point_ledgers", "initial_victory_point_ledgers", "muster_army"]
