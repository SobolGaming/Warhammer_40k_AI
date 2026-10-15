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


def test_return_on_death_failed_roll_resolves_without_restoring_target() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=5)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(_roll_result(pending=pending, value=1),),
    )
    from warhammer40k_core.engine.return_on_death_sequencing import return_phase_end_candidates
    from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext

    before_discovery = (state.to_payload(), decisions.to_payload())
    assert state.current_battle_phase is not None
    candidates = return_phase_end_candidates(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=state.current_battle_phase,
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        dice_manager=manager,
    )
    assert (state.to_payload(), decisions.to_payload()) == before_discovery
    assert len(candidates) == 1
    assert candidates[0].participant.player_id == pending.owner_player_id

    request = resolve_return_phase_end_candidates(
        state=state,
        decisions=decisions,
        dice_manager=manager,
    )

    assert request is None
    assert state.pending_return_on_death_by_id(pending.pending_id).resolved
    assert state.battlefield_state is not None
    assert set(_beta_unit(state).own_model_ids()) <= set(state.battlefield_state.removed_model_ids)


@pytest.mark.parametrize("whole_unit_destroyed", [True, False])
def test_return_on_death_fixed_wounds_restores_exact_remaining_wounds(
    whole_unit_destroyed: bool,
) -> None:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    if whole_unit_destroyed:
        state = _battle_state_with_destroyed_beta_unit()
    else:
        model_id = beta.own_models[0].model_instance_id
        _set_model_wounds(state, model_instance_id=model_id, wounds_remaining=0)
        assert state.battlefield_state is not None
        state.battlefield_state = state.battlefield_state.with_removed_models((model_id,))
    pending = _pending_return_on_death(
        state=state,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
        restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
        wounds_remaining=1,
    )
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    request = build_return_on_death_placement_request(state=state, pending=pending)
    decisions.request_decision(request)
    destroyed_model_id = pending.destroyed_model_instance_id
    assert destroyed_model_id is not None
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_model_at_destroyed_position(
            state=state,
            unit=_beta_unit(state),
            model_instance_id=destroyed_model_id,
        ),
    )
    decisions.submit_result(result)

    resolved = apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    returned_model = next(
        model
        for model in _beta_unit(state).own_models
        if model.model_instance_id == destroyed_model_id
    )
    assert resolved.resolved
    assert returned_model.current_wounds == 1
    assert bool(state.phase_movement_history) is whole_unit_destroyed
    from warhammer40k_core.engine.phase_movement_history import validate_phase_movement_history

    validate_phase_movement_history(state=state, events=decisions.event_log.records)
    assert state.battlefield_state is not None
    assert destroyed_model_id not in state.battlefield_state.removed_model_ids


def test_return_on_death_stale_pending_submission_rejects_before_mutation() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    state.resolve_pending_return_on_death(pending.pending_id)
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


def test_return_on_death_rejects_zero_fixed_wounds_before_runtime_mutation() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    with pytest.raises(GameLifecycleError, match="wounds_remaining"):
        _pending_return_on_death(
            state=state,
            target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
            restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
            wounds_remaining=0,
        )


def test_return_on_death_pending_payload_round_trips() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)

    assert PendingReturnOnDeath.from_payload(pending.to_payload()) == pending


def test_return_on_death_runtime_empty_indexes_have_no_hooks() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    assert runtime.unit_destroyed_bindings() == ()
    assert runtime.phase_end_bindings() == ()


def test_return_on_death_runtime_fail_fast_filter_and_out_of_phase_paths() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        sequencing_active_player_id=cast(str, state.active_player_id),
        state=state,
        decisions=DecisionController(),
        completed_phase=current_phase,
        model_destroyed_event_id="event:return-runtime",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "destroyed_model_placement": {"source": "runtime-test"},
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_player_id="player-b",
    )
    runtime_missing_index = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={},
        armies=tuple(state.army_definitions),
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        runtime_missing_index.unit_destroyed_handler(context)

    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    with pytest.raises(GameLifecycleError, match="destroyed player drift"):
        runtime.unit_destroyed_handler(
            replace(context, destroying_player_id="player-b", destroyed_player_id="player-a")
        )

    filtered_state = _battle_state_with_scenario()
    filtered_decisions = DecisionController()
    filtered_phase = filtered_state.current_battle_phase
    assert filtered_phase is not None
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": "other-game",
            "battle_round": filtered_state.battle_round,
            "active_player_id": filtered_state.active_player_id,
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round + 1,
            "active_player_id": filtered_state.active_player_id,
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round,
            "active_player_id": "player-b",
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    out_of_phase_event = filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round,
            "active_player_id": filtered_state.active_player_id,
            "phase": "movement",
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    _record_return_captures(
        runtime,
        PhaseEndObjectiveControlContext(
            state=filtered_state,
            event_log=filtered_decisions.event_log,
            completed_phase=filtered_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ),
    )
    (out_of_phase_pending,) = filtered_state.pending_return_on_death
    assert out_of_phase_pending.trigger_phase == filtered_phase.value
    assert out_of_phase_pending.destroyed_position_payload == {
        "source": "model_destroyed_event",
        "model_destroyed_event_id": out_of_phase_event.event_id,
        "model_destroyed_payload": out_of_phase_event.payload,
    }

    malformed_event_decisions = DecisionController()
    malformed_event_decisions.event_log.append("model_destroyed", [])
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        _record_return_captures(
            runtime,
            PhaseEndObjectiveControlContext(
                state=filtered_state,
                event_log=malformed_event_decisions.event_log,
                completed_phase=filtered_phase,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ),
        )

    missing_index_state = _battle_state_with_scenario()
    missing_index_decisions = DecisionController()
    missing_index_phase = missing_index_state.current_battle_phase
    assert missing_index_phase is not None
    missing_index_beta = _beta_unit(missing_index_state)
    missing_index_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": missing_index_state.game_id,
            "battle_round": missing_index_state.battle_round,
            "active_player_id": missing_index_state.active_player_id,
            "phase": missing_index_phase.value,
            "target_unit_instance_id": missing_index_beta.unit_instance_id,
            "model_instance_id": missing_index_beta.own_models[0].model_instance_id,
        },
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        _record_return_captures(
            runtime_missing_index,
            PhaseEndObjectiveControlContext(
                state=missing_index_state,
                event_log=missing_index_decisions.event_log,
                completed_phase=missing_index_phase,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ),
        )


def test_first_death_return_unit_destroyed_hook_records_pending_once() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    decisions = DecisionController()
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        sequencing_active_player_id=cast(str, state.active_player_id),
        state=state,
        decisions=decisions,
        completed_phase=current_phase,
        model_destroyed_event_id="event:unit-destroyed-return",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "destroyed_model_placement": {"source": "unit-destroyed-test"},
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_player_id="player-b",
    )

    bindings = runtime.unit_destroyed_bindings()
    runtime.unit_destroyed_handler(context)
    runtime.unit_destroyed_handler(context)

    assert len(bindings) == 1
    assert len(state.pending_return_on_death) == 1
    assert state.pending_return_on_death[0].destroyed_model_instance_id == destroyed_model_id


def test_return_on_death_defensive_validation_rejects_malformed_pending_records() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    malformed_pending_calls: tuple[Callable[[], PendingReturnOnDeath], ...] = (
        lambda: replace(
            pending,
            target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
            destroyed_model_instance_id=None,
        ),
        lambda: replace(pending, engagement_range_restriction=False),
        lambda: replace(
            pending,
            restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
            wounds_remaining=1,
        ),
        lambda: replace(pending, roll_count=0),
        lambda: replace(pending, success_threshold=1),
        lambda: replace(pending, resolved=cast(bool, "no")),
    )

    for malformed_pending_call in malformed_pending_calls:
        with pytest.raises(GameLifecycleError):
            malformed_pending_call()

    resolved = _pending_return_on_death(state=state, success_threshold=2).mark_resolved()
    assert resolved.mark_resolved() == resolved


def test_return_on_death_decision_and_restore_defensive_paths() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    placement = _unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0)
    result = _placement_result(request=request, placement=placement)
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    malformed_inputs = (
        (
            replace(request, decision_type="other_decision"),
            result,
        ),
        (
            replace(
                request,
                payload={
                    **cast(dict[str, JsonValue], request.payload),
                    "submission_kind": "other_submission",
                },
            ),
            result,
        ),
        (
            request,
            replace(result, actor_id="player-a"),
        ),
        (
            request,
            replace(
                result,
                payload={
                    "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                    "attempted_placement": "not-an-object",
                },
            ),
        ),
    )
    for malformed_request, malformed_result in malformed_inputs:
        assert (
            invalid_return_on_death_placement_status(
                state=state,
                request=malformed_request,
                result=malformed_result,
                ruleset_descriptor=descriptor,
            )
            is not None
        )

    with pytest.raises(GameLifecycleError, match="placement requires RulesetDescriptor"):
        return_on_death_module._validate_return_on_death_placement(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=pending,
            placement=placement,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
        )
    no_battlefield_state = _battle_state_with_destroyed_beta_unit()
    no_battlefield_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        return_on_death_module._validate_return_on_death_placement(  # pyright: ignore[reportPrivateUsage]
            state=no_battlefield_state,
            pending=_pending_return_on_death(state=no_battlefield_state),
            placement=placement,
            ruleset_descriptor=descriptor,
        )
    with pytest.raises(GameLifecycleError, match="destroyed model placement evidence"):
        return_on_death_module._validate_return_on_death_placement(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=replace(pending, destroyed_position_payload={"source": "test"}),
            placement=_unit_placement_at_destroyed_position(state=state, unit=_beta_unit(state)),
            ruleset_descriptor=descriptor,
        )
    with pytest.raises(GameLifecycleError, match="destroyed position unit drift"):
        return_on_death_module._assert_destroyed_position_anchor(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=replace(pending, destroyed_unit_instance_id="unit:other"),
            placement=_unit_placement_at_destroyed_position(state=state, unit=_beta_unit(state)),
            ruleset_descriptor=descriptor,
        )
    model_pending = _pending_return_on_death(
        state=state,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
        restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
        wounds_remaining=1,
    )
    model_pending_model_id = model_pending.destroyed_model_instance_id
    assert model_pending_model_id is not None
    with pytest.raises(GameLifecycleError, match="destroyed position model drift"):
        return_on_death_module._assert_destroyed_position_anchor(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=replace(
                model_pending,
                destroyed_model_instance_id=_beta_unit(state).own_models[1].model_instance_id,
            ),
            placement=_unit_placement_for_model_at_destroyed_position(
                state=state,
                unit=_beta_unit(state),
                model_instance_id=model_pending_model_id,
            ),
            ruleset_descriptor=descriptor,
        )
    with pytest.raises(GameLifecycleError, match="missing destroyed anchor model"):
        return_on_death_module._placement_for_model(  # pyright: ignore[reportPrivateUsage]
            placement=_unit_placement_at_destroyed_position(state=state, unit=_beta_unit(state)),
            model_instance_id="model:missing",
        )
    incomplete_payload = cast(
        JsonValue,
        {
            "source": "model_destroyed_event",
            "model_destroyed_payload": {"destroyed_model_placement": {"army_id": "army-beta"}},
        },
    )
    with pytest.raises(GameLifecycleError, match="destroyed model placement is incomplete"):
        return_on_death_module._destroyed_model_placement_from_pending(  # pyright: ignore[reportPrivateUsage]
            replace(pending, destroyed_position_payload=incomplete_payload)
        )
    anchor_payload = _destroyed_model_placement_for_model(
        model_instance_id=_beta_unit(state).own_models[0].model_instance_id,
    ).to_payload()
    malformed_pose_payload = cast(
        JsonValue,
        {
            "source": "model_destroyed_event",
            "model_destroyed_payload": {
                "destroyed_model_placement": {**anchor_payload, "pose": "not-an-object"}
            },
        },
    )
    with pytest.raises(GameLifecycleError, match="placement pose must be object"):
        return_on_death_module._destroyed_model_placement_from_pending(  # pyright: ignore[reportPrivateUsage]
            replace(pending, destroyed_position_payload=malformed_pose_payload)
        )
    with pytest.raises(GameLifecycleError, match="currently supports exactly one D6"):
        return_on_death_module._return_on_death_roll_spec(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=replace(pending, roll_count=2),
        )
    with pytest.raises(GameLifecycleError, match="requires pending record"):
        build_return_on_death_placement_request(
            state=state,
            pending=cast(PendingReturnOnDeath, object()),
        )
    with pytest.raises(GameLifecycleError, match="model is unknown"):
        return_on_death_module._model_by_id(  # pyright: ignore[reportPrivateUsage]
            state=state,
            model_instance_id="model:missing",
        )
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        return_on_death_module._unit_by_id(  # pyright: ignore[reportPrivateUsage]
            state=state,
            unit_instance_id="unit:missing",
        )
    with pytest.raises(GameLifecycleError, match="cannot update an unknown model"):
        return_on_death_module._army_definitions_with_model_wounds(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            model_instance_id="model:missing",
            wounds_remaining=1,
        )
    with pytest.raises(GameLifecycleError, match="cannot update an unknown unit"):
        return_on_death_module._army_definitions_with_unit_full_health(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )


def test_return_on_death_defensive_helpers_reject_malformed_payloads() -> None:
    malformed_calls = (
        lambda: return_on_death_module._payload_object([]),  # pyright: ignore[reportPrivateUsage]
        lambda: return_on_death_module._payload_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="pending_id",
        ),
        lambda: return_on_death_module._target_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: return_on_death_module._target_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: return_on_death_module._restore_wounds_mode_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: return_on_death_module._restore_wounds_mode_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: return_on_death_module._validate_supported_token(  # pyright: ignore[reportPrivateUsage]
            "placement_anchor",
            "anywhere",
            supported=("destroyed_position",),
        ),
        lambda: return_on_death_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "pending_id",
            1,
        ),
        lambda: return_on_death_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "pending_id",
            "",
        ),
        lambda: return_on_death_module._validate_non_negative_int(  # pyright: ignore[reportPrivateUsage]
            "source_effect_index",
            -1,
        ),
        lambda: return_on_death_module._validate_positive_int(  # pyright: ignore[reportPrivateUsage]
            "roll_count",
            0,
        ),
        lambda: return_on_death_module._validate_d6_threshold(  # pyright: ignore[reportPrivateUsage]
            "success_threshold",
            7,
        ),
    )

    for malformed_call in malformed_calls:
        with pytest.raises(GameLifecycleError):
            malformed_call()


def test_first_death_return_phase_end_hook_captures_model_destroyed_once() -> None:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    destroyed_placement = state.battlefield_state.model_placement_by_id(
        destroyed_model_id
    ).to_payload()
    _set_model_wounds(state, model_instance_id=destroyed_model_id, wounds_remaining=0)
    state.battlefield_state = state.battlefield_state.with_removed_models((destroyed_model_id,))
    decisions = DecisionController()
    model_destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": "command",
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": state.army_definitions[0].units[0].unit_instance_id,
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "damage_kind": "normal",
            "damage_event_id": "damage:event:first-death",
            "destroyed_model_placement": destroyed_placement,
            "destroyed_model_rules_triggered": True,
        },
    )
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None

    _record_return_captures(
        runtime,
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=decisions.event_log,
            completed_phase=current_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ),
    )
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
    assert pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
    assert pending.destroyed_model_instance_id == destroyed_model_id
    assert not pending.resolved
    assert state.battlefield_state is not None
    assert destroyed_model_id in state.battlefield_state.removed_model_ids
    assert pending.destroyed_position_payload == {
        "source": "model_destroyed_event",
        "model_destroyed_event_id": model_destroyed_event.event_id,
        "model_destroyed_payload": model_destroyed_event.payload,
    }


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest"]
__all__ += ["BattlePhase", "DamageKind", "DecisionRequest", "DecisionResult"]
__all__ += ["DestructionSourceKind", "DetachmentSelection", "DiceExpression", "DiceRollResult"]
__all__ += ["FIRST_DEATH_RETURN_TEXT", "GENERIC_RULE_IR_ABILITY_HANDLER_ID", "DiceRollSpec"]
__all__ += ["GameLifecycle", "GameLifecycleStage", "GameState", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "MortalWoundDestructionEvidence", "ObjectiveRuleScope"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "Pose", "RuleSourceText"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "RulesUnitObjectiveProximityWitness", "UnitInstance"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "_destroyed_position_payload_for_model"]
__all__ += ["_destroyed_position_payload_for_placement"]
__all__ += ["_destroyed_position_payload_for_placement_payload", "_first_alpha_model_pose"]
__all__ += ["_muster_request", "_mustered_armies", "_set_unit_wounds", "apply_damage_to_model"]
__all__ += ["apply_direct_mortal_wounds_to_unit", "assert_parameterized_projection"]
__all__ += ["catalog_return_on_death_runtime_module", "catalog_rule_clauses_from_record"]
__all__ += ["compile_rule_source_text", "create_deterministic_battlefield_scenario"]
__all__ += ["datasheet_keyword_lexicon_source", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "muster_army"]
