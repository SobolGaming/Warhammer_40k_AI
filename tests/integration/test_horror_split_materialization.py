# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.horror_split_materialization import (
    CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
    CATALOG_MODELS_MATERIALIZED_EVENT,
    CATALOG_UNIT_DATASHEET_REPLACED_EVENT,
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
    RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachedUnitFormation,
    AttackSequence,
    AttackSequenceCompletedContext,
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    BattlePhase,
    BattleRoundFlow,
    CanonicalCatalogPackage,
    CatalogModelMaterializationRuntime,
    Characteristic,
    CharacteristicValue,
    DamageProfile,
    DecisionController,
    DecisionRecord,
    DecisionResult,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionSourceKind,
    DetachmentSelection,
    DiceExpression,
    DiceRollManager,
    DiceRollResult,
    DiceRollSpec,
    EffectExpiration,
    EventRecord,
    FeelNoPainSource,
    FightActivationSelection,
    FightEligibilityKind,
    FightPhaseHandler,
    FightPhaseState,
    FightPhaseStepKind,
    FightsFirstRegistry,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    ModelDestructionAttribution,
    ModelInstance,
    ModelPlacement,
    ModelProfileSelection,
    MovementPhaseHandler,
    OutOfPhaseShootingState,
    PersistingEffect,
    PlacedArmy,
    PlacementProposalPayload,
    Pose,
    ProposalKind,
    RangedAttackPool,
    ReactionQueue,
    ReactionQueueFrame,
    ReactionWindow,
    RulesetDescriptor,
    RuntimeContentActivation,
    RuntimeContentBundle,
    RuntimeContentContribution,
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeModifierRegistry,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingType,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
    UnitFactory,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    WeaponKeyword,
    _alive_unit_placement_or_none,
    _army,
    _attack_sequence,
    _authenticated_materialization_evidence,
    _configure_phase_lifecycle,
    _corrupt_authenticated_materialization_evidence,
    _game_config,
    _model_count_unit,
    _parameterized_result,
    _placement_payload,
    _record_split_interrupt_activation,
    _record_successful_materialization_rolls,
    _required_string_list,
    _restored_phase_lifecycle,
    _retained_horror_model,
    _runtime_content_bundle,
    _single_model_unit,
    _split_scenario,
    _SplitScenario,
    _tamper_materialization_lifecycle_payload,
    _unique_event_index,
    _unit_by_id,
    _unit_placement,
    apply_feel_no_pain_decision,
    apply_recorded_catalog_model_materialization_placement,
    assert_parameterized_projection,
    attack_sequence_wound_roll_spec,
    authenticated_catalog_materialized_model_payloads_by_unit_id,
    battle_phase_kind_from_token,
    battle_state_with_armies,
    catalog_ability_records_from_catalog,
    copy,
    dataclass,
    deadly_demise_trigger_roll_spec,
    feel_no_pain_roll_spec,
    horrors_package,
    invalid_catalog_model_materialization_placement_status,
    is_mortal_wound_model_request,
    lifecycle_module,
    mandatory_save_option,
    player_ability_index,
    pytest,
    reconcile_after_attack_sequence,
    replace,
    resolve_attack_sequence_until_blocked,
    resolve_horror_completion,
    resolve_mortal_wound_decision,
    resolve_selected_target_mortal_wound_effect,
    rule_model_destruction,
    rules_unit_view_by_id,
    save_options_for_model,
    saving_throw_roll_spec,
    validate_json_value,
)


def test_random_wounds_materialization_uses_recorded_health_for_placement_and_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        random_materialized_wounds=True,
    )
    assert resolve_horror_completion(scenario.runtime, scenario.context) is not None
    request = scenario.decisions.queue.peek_next()
    body = cast(dict[str, JsonValue], request.payload)
    rows = cast(list[dict[str, JsonValue]], body["models"])
    assert len(rows) == 2
    assert all(
        type(row["starting_wounds"]) is int and 3 <= row["starting_wounds"] <= 8 for row in rows
    )
    lifecycle = GameLifecycle(state=scenario.state, decision_controller=scenario.decisions)
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    from warhammer40k_core.engine.random_profile_restore import validate_random_profile_history

    validate_random_profile_history(
        state=GameState.from_payload(scenario.state.to_payload()),
        catalog=scenario.package.army_catalog,
        pending_requests=scenario.decisions.queue.pending_requests,
        event_records=scenario.decisions.event_log.records,
        decision_records=scenario.decisions.records,
    )
    session = LocalGameSession(lifecycle)
    before = tuple(
        event
        for event in scenario.decisions.event_log.records
        if event.event_type == "random_characteristic_rolled"
    )
    assert len(before) == 2
    for viewer in (scenario.source_army.player_id, scenario.enemy_army.player_id):
        session.view(viewer_player_id=viewer)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="random-wounds-placement",
        payload=_placement_payload(
            request=request, army=scenario.source_army, unit=scenario.bodyguard
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    after = tuple(
        event
        for event in scenario.decisions.event_log.records
        if event.event_type == "random_characteristic_rolled"
    )
    assert after == before
    assert any(
        event.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
        for event in scenario.decisions.event_log.records
    )
    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert {model.model_instance_id: model.initial_wounds for model in updated.own_models} == {
        row["model_instance_id"]: row["starting_wounds"] for row in rows
    }
    validate_random_profile_history(
        state=scenario.state,
        catalog=scenario.package.army_catalog,
        pending_requests=scenario.decisions.queue.pending_requests,
        event_records=scenario.decisions.event_log.records,
        decision_records=scenario.decisions.records,
    )


@pytest.mark.parametrize(
    ("pink_datasheet_id", "blue_datasheet_id", "source_phase"),
    [
        ("000002584", "000002583", BattlePhase.SHOOTING),
        ("000002584", "000002583", BattlePhase.FIGHT),
        ("000004127", "000004128", BattlePhase.SHOOTING),
        ("000004127", "000004128", BattlePhase.FIGHT),
    ],
)
def test_split_materializes_models_then_hands_off_attached_unit_datasheet(
    pink_datasheet_id: str,
    blue_datasheet_id: str,
    source_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id=pink_datasheet_id,
        blue_datasheet_id=blue_datasheet_id,
        destruction_kind="attack",
        source_phase=source_phase,
    )
    starting_strength = scenario.state.starting_strength_record_for_unit(
        scenario.attached_unit_instance_id
    )

    status = resolve_horror_completion(scenario.runtime, scenario.context)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = scenario.decisions.queue.peek_next()
    assert request.decision_type == SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE
    assert request.actor_id == scenario.source_army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert len(cast(list[JsonValue], request_payload["models"])) == 2
    assert request_payload["source_phase"] == source_phase.value
    pending_lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    restored_pending_lifecycle = GameLifecycle.from_payload(pending_lifecycle.to_payload())
    assert (
        restored_pending_lifecycle.decision_controller.queue.peek_next().to_payload()
        == request.to_payload()
    )

    assert_parameterized_projection(restored_pending_lifecycle)
    valid_payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    stale_payload = dict(valid_payload)
    stale_payload["proposal_request_id"] = "stale-split-request"
    stale_result = _parameterized_result(
        request=request,
        payload=validate_json_value(stale_payload),
        result_id="result:split:stale",
    )
    stale_status = invalid_catalog_model_materialization_placement_status(
        state=scenario.state,
        request=request,
        result=stale_result,
        decisions=scenario.decisions,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert stale_status is not None
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert scenario.decisions.queue.peek_next() == request

    result = _parameterized_result(
        request=request,
        payload=valid_payload,
        result_id=f"result:split:{pink_datasheet_id}",
    )
    assert (
        invalid_catalog_model_materialization_placement_status(
            state=scenario.state,
            request=request,
            result=result,
            decisions=scenario.decisions,
            ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=scenario.package.army_catalog,
        )
        is None
    )
    scenario.decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert len(placements) == 2
    assert {placement.placement_kind for placement in placements} == {
        BattlefieldPlacementKind.SPLIT_UNIT
    }
    assert {placement.source_phase for placement in placements} == {source_phase.value}

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None
    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    updated_bodyguard = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated_bodyguard.datasheet_id == blue_datasheet_id
    assert len(updated_bodyguard.own_models) == 2
    assert scenario.destroyed_model_instance_id not in updated_bodyguard.own_model_ids()
    assert {model.model_profile_id for model in updated_bodyguard.own_models} == {
        f"{blue_datasheet_id}:blue-horrors"
    }
    assert all(model.base_size.diameter_mm == 25.0 for model in updated_bodyguard.own_models)
    assert all(
        "horror-materialization:blue-horror" in model.source_ids
        for model in updated_bodyguard.own_models
    )
    assert all("BLUE" in model.keywords for model in updated_bodyguard.own_models)
    assert all("BRIMSTONE" not in model.keywords for model in updated_bodyguard.own_models)
    assert "PINK" not in updated_bodyguard.keywords
    rules_unit = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.bodyguard.unit_instance_id,
    )
    assert rules_unit.is_attached_rules_unit
    assert len(rules_unit.alive_models()) == 3
    assert starting_strength.starting_model_count == 2
    assert (
        scenario.state.starting_strength_record_for_unit(scenario.attached_unit_instance_id)
        == starting_strength
    )
    assert scenario.state.battlefield_state is not None
    assert scenario.destroyed_model_instance_id not in (
        scenario.state.battlefield_state.removed_model_ids
    )
    event_types = tuple(record.event_type for record in scenario.decisions.event_log.records)
    assert CATALOG_MODELS_MATERIALIZED_EVENT in event_types
    assert CATALOG_UNIT_DATASHEET_REPLACED_EVENT in event_types
    assert "battlefield_models_placed" in event_types
    materialized_event = next(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
    )
    materialized_payload = cast(dict[str, JsonValue], materialized_event.payload)
    assert materialized_payload["source_phase"] == source_phase.value
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, materialized_payload["transition_batch"])
    )
    assert {placement.source_phase for placement in transition.placements} == {source_phase.value}
    restored = GameState.from_payload(scenario.state.to_payload())
    from warhammer40k_core.engine.model_ownership_history import historical_physical_unit_id

    assert (
        scenario.destroyed_model_instance_id
        not in _unit_by_id(restored, scenario.bodyguard.unit_instance_id).own_model_ids()
    )
    assert (
        historical_physical_unit_id(
            state=restored, model_instance_id=scenario.destroyed_model_instance_id
        )
        == scenario.bodyguard.unit_instance_id
    )
    with pytest.raises(GameLifecycleError, match="Historical model ownership requires one"):
        historical_physical_unit_id(state=restored, model_instance_id="unobserved-model")
    assert _unit_by_id(restored, scenario.bodyguard.unit_instance_id).datasheet_id == (
        blue_datasheet_id
    )
    assert GameState.from_payload(restored.to_payload()).to_payload() == restored.to_payload()
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    restored_materialized = next(
        record
        for record in restored_decisions.event_log.records
        if record.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
    )
    restored_payload = cast(dict[str, JsonValue], restored_materialized.payload)
    restored_transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, restored_payload["transition_batch"])
    )
    assert {placement.source_phase for placement in restored_transition.placements} == {
        source_phase.value
    }
    authenticated_models = authenticated_catalog_materialized_model_payloads_by_unit_id(
        game_id=scenario.state.game_id,
        catalog=scenario.package.army_catalog,
        expected_armies=(scenario.source_army, scenario.enemy_army),
        event_records=scenario.decisions.event_log.records,
        decision_records=scenario.decisions.records,
    )
    assert set(authenticated_models[scenario.bodyguard.unit_instance_id]) == set(
        cast(list[str], materialized_payload["model_instance_ids"])
    )
    resolved_lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    restored_resolved_lifecycle = GameLifecycle.from_payload(resolved_lifecycle.to_payload())
    restored_resolved_state = restored_resolved_lifecycle.state
    assert restored_resolved_state is not None
    assert (
        _unit_by_id(
            restored_resolved_state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == blue_datasheet_id
    )
    assert restored_resolved_lifecycle.decision_controller.to_payload() == (
        scenario.decisions.to_payload()
    )


def test_split_complete_standalone_wipe_skips_empty_datasheet_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        attached=False,
    )

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None

    unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert unit.datasheet_id == "000002584"
    assert unit.own_models
    assert not any(model.is_alive for model in unit.own_models)
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )


@pytest.mark.parametrize("source_phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_real_attack_pipeline_hands_off_attached_horror_component(
    source_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        source_phase=source_phase,
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    pink_model = scenario.bodyguard.own_models[0]
    valid_save_model = replace(
        pink_model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 6)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in pink_model.characteristics
        ),
    )
    bodyguard = replace(scenario.bodyguard, own_models=(valid_save_model,))
    source_army = replace(
        scenario.source_army,
        units=tuple(
            bodyguard if unit.unit_instance_id == bodyguard.unit_instance_id else unit
            for unit in scenario.source_army.units
        ),
    )
    scenario.state.replace_army_definitions([source_army, scenario.enemy_army])
    base_pool = scenario.attack_sequence.attack_pools[0]
    lethal_profile = replace(
        base_pool.weapon_profile,
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    lethal_pool = replace(base_pool, weapon_profile=lethal_profile)
    attack_sequence = AttackSequence.start(
        sequence_id=f"real-pipeline:{source_phase.value}:horror-split",
        attacker_player_id=scenario.enemy_army.player_id,
        attacking_unit_instance_id=scenario.attack_sequence.attacking_unit_instance_id,
        attack_pools=(lethal_pool,),
        source_phase=source_phase,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=lethal_pool.weapon_profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.enemy_army.player_id,
    )
    save_option = mandatory_save_option(
        save_options_for_model(
            model=valid_save_model,
            armor_penetration=0,
        )
    )
    assert save_option is not None
    save_spec = saving_throw_roll_spec(
        save_kind=save_option.save_kind,
        player_id=scenario.source_army.player_id,
        allocated_model_id=valid_save_model.model_instance_id,
        attack_context_id=attack_sequence.attack_context_id(),
    )
    manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id=f"roll:real-pipeline:{source_phase.value}:wound",
                spec=wound_spec,
                values=(6,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id=f"roll:real-pipeline:{source_phase.value}:save",
                spec=save_spec,
                values=(1,),
                source="fixed",
            ),
        ),
    )

    remaining, _allocated_ids, blocked = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=manager,
    )

    assert remaining is None
    assert blocked is None
    destroyed_event = next(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    assert destroyed_payload["target_unit_instance_id"] == scenario.attached_unit_instance_id
    completed_event = next(
        record
        for record in reversed(scenario.decisions.event_log.records)
        if record.event_type == "attack_sequence_completed"
        and cast(dict[str, JsonValue], record.payload).get("sequence_id")
        == attack_sequence.sequence_id
    )
    completed_sequence = replace(attack_sequence, used_pool_indices=(0,), pool_index=1)
    context = replace(
        scenario.context,
        attack_sequence=completed_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
        source_phase=source_phase,
    )
    from tests.horror_destruction_helpers import finish_prior_horror_destruction_triggers

    finish_prior_horror_destruction_triggers(state=scenario.state, decisions=scenario.decisions)
    assert resolve_horror_completion(scenario.runtime, context) is not None
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:real-pipeline:{source_phase.value}",
    )
    scenario.decisions.submit_result(result)
    apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert resolve_horror_completion(scenario.runtime, context) is None
    assert _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )


def test_real_hazardous_attack_uses_typed_destruction_once_for_horror_split() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="hazardous",
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    enemy_model = scenario.enemy_army.units[0].own_models[0]
    valid_save_model = replace(
        enemy_model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 6)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in enemy_model.characteristics
        ),
    )
    enemy_unit = replace(scenario.enemy_army.units[0], own_models=(valid_save_model,))
    enemy_army = replace(scenario.enemy_army, units=(enemy_unit,))
    scenario.state.replace_army_definitions([scenario.source_army, enemy_army])
    base_pool = scenario.attack_sequence.attack_pools[0]
    hazardous_profile = replace(
        base_pool.weapon_profile,
        profile_id="real-hazardous:horror-split",
        keywords=(WeaponKeyword.TORRENT, WeaponKeyword.HAZARDOUS),
        abilities=(),
    )
    hazardous_pool = replace(
        base_pool,
        weapon_profile_id=hazardous_profile.profile_id,
        weapon_profile=hazardous_profile,
    )
    attack_sequence = AttackSequence.start(
        sequence_id="real-hazardous:horror-split",
        attacker_player_id=scenario.source_army.player_id,
        attacking_unit_instance_id=scenario.attached_unit_instance_id,
        attack_pools=(hazardous_pool,),
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=hazardous_profile.profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.source_army.player_id,
    )
    hazardous_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(f"Hazardous tests for {scenario.attached_unit_instance_id} after shooting"),
        roll_type="hazardous_test",
        actor_id=scenario.attached_unit_instance_id,
    )

    remaining, _allocated_ids, blocked = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=(
            manager := DiceRollManager(
                scenario.state.game_id,
                event_log=scenario.decisions.event_log,
                injected_results=(
                    DiceRollResult.from_values(
                        roll_id="roll:real-hazardous:horror-split:wound",
                        spec=wound_spec,
                        values=(1,),
                        source="fixed",
                    ),
                    DiceRollResult.from_values(
                        roll_id="roll:real-hazardous:horror-split:test",
                        spec=hazardous_spec,
                        values=(1,),
                        source="fixed",
                    ),
                    DiceRollResult.from_values(
                        roll_id="roll:real-hazardous:horror-split:split",
                        spec=DiceRollSpec(
                            expression=DiceExpression(quantity=1, sides=6),
                            reason=(
                                f"Model materialization for {scenario.destroyed_model_instance_id}"
                            ),
                            roll_type="catalog.model_materialization.trigger",
                            actor_id=scenario.source_army.player_id,
                        ),
                        values=(6,),
                        source="fixed",
                    ),
                ),
            )
        ),
    )

    assert remaining is None
    assert blocked is None
    completed_event = next(
        record
        for record in reversed(scenario.decisions.event_log.records)
        if record.event_type == "attack_sequence_completed"
        and cast(dict[str, JsonValue], record.payload).get("sequence_id")
        == attack_sequence.sequence_id
    )
    completed_sequence = replace(attack_sequence, used_pool_indices=(0,), pool_index=1)
    context = replace(
        scenario.context,
        dice_manager=manager,
        attack_sequence=completed_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    status = resolve_horror_completion(scenario.runtime, context)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        sum(
            record.event_type == "hazardous_mortal_wounds_applied"
            for record in scenario.decisions.event_log.records
        )
        == 1
    )
    hazardous_destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload).get("model_instance_id")
        == scenario.destroyed_model_instance_id
    )
    assert len(hazardous_destroyed_payloads) == 1
    assert isinstance(
        hazardous_destroyed_payloads[0]["destroyed_model_placement"],
        dict,
    )
    assert (
        ModelDestructionAttribution.from_model_destroyed_payload(
            hazardous_destroyed_payloads[0]
        ).destruction_provenance.destruction_source_kind
        is DestructionSourceKind.HAZARDOUS
    )
    assert (
        sum(
            record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


def test_split_failed_attached_wipe_skips_handoff_and_retains_attachment() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        roll_values=(1,),
    )

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )
    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    bodyguard = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert bodyguard.own_models
    assert not any(model.is_alive for model in bodyguard.own_models)
    retained_view = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.leader.unit_instance_id,
    )
    assert retained_view.is_attached_rules_unit
    assert retained_view.unit_instance_id == scenario.attached_unit_instance_id


def test_attack_reconciliation_retains_canonical_attached_identity() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        roll_values=(1,),
    )

    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    retained_view = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.leader.unit_instance_id,
    )
    assert retained_view.is_attached_rules_unit
    assert retained_view.unit_instance_id == scenario.attached_unit_instance_id


def test_split_multiple_failed_rolls_do_not_construct_empty_replacement_unit() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        pink_model_count=3,
        roll_values=(1, 2, 3),
    )

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None

    roll_events = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    assert len(roll_events) == 3
    assert all(
        cast(dict[str, JsonValue], record.payload)["successful"] is False for record in roll_events
    )
    unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert len(unit.own_models) == 3
    assert not any(model.is_alive for model in unit.own_models)
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )


@pytest.mark.parametrize(
    "source_kind",
    [DestructionSourceKind.ABILITY, DestructionSourceKind.DEADLY_DEMISE],
)
def test_matching_attack_sequence_id_does_not_override_destruction_provenance(
    source_kind: DestructionSourceKind,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=source_kind.value,
        event_sequence_matches=True,
        retained_horror_kinds=("blue",),
    )

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None
    assert scenario.decisions.queue.pending_requests == ()
    assert all(
        record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
        for record in scenario.decisions.event_log.records
    )
    assert (
        _unit_by_id(
            scenario.state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == "000002583"
    )


@pytest.mark.parametrize(
    ("source_kind", "source_step"),
    [
        (DestructionSourceKind.ABILITY, "ability_resolution"),
        (DestructionSourceKind.DEADLY_DEMISE, "deadly_demise_collateral"),
        (DestructionSourceKind.ABILITY, "mortal_wound_feel_no_pain_continuation"),
        (DestructionSourceKind.ABILITY, "generic_rule_model_destruction"),
    ],
)
def test_non_attack_destruction_reconciles_horror_datasheet_from_composition(
    source_kind: DestructionSourceKind,
    source_step: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=source_kind.value,
        retained_horror_kinds=("blue",),
        non_attack_source_step=source_step,
    )
    starting_strength = scenario.state.starting_strength_record_for_unit(
        scenario.attached_unit_instance_id
    )

    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = _game_config(scenario)
    lifecycle._runtime_content_bundle = _runtime_content_bundle(scenario)
    lifecycle._reconcile_catalog_model_state_changes()

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    assert (
        scenario.state.starting_strength_record_for_unit(scenario.attached_unit_instance_id)
        == starting_strength
    )
    rules_unit = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.bodyguard.unit_instance_id,
    )
    assert rules_unit.is_attached_rules_unit
    assert len(rules_unit.alive_models()) == 2
    replacement_events = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
    )
    assert len(replacement_events) == 1
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    assert (
        _unit_by_id(
            restored_state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == "000002583"
    )
    assert (
        len(
            tuple(
                record
                for record in restored_decisions.event_log.records
                if record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            )
        )
        == 1
    )


@pytest.mark.parametrize("select_reaction", [False, True])
def test_non_attack_handoff_waits_for_optional_destruction_reaction_finalization(
    select_reaction: bool,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    pink_model_id = scenario.bodyguard.own_models[0].model_instance_id
    liability = PersistingEffect(
        effect_id="test:horrors:pending-reaction:liability",
        source_rule_id="test:horrors:pending-reaction:rule",
        owner_player_id=scenario.enemy_army.player_id,
        target_unit_instance_ids=(scenario.attached_unit_instance_id,),
        started_battle_round=scenario.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=scenario.state.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=scenario.enemy_army.player_id,
        ),
        effect_payload={"effect_kind": "test_rule_destruction_liability"},
    )
    scenario.state.record_persisting_effect(liability)
    reaction = DestructionReactionSource(
        source_id="test:horrors:pending-reaction:fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="test:horrors:pending-reaction:source-rule",
    )
    scenario.state.record_model_destruction_reaction_sources(
        model_instance_id=pink_model_id,
        sources=(reaction,),
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=scenario.state,
        decisions=scenario.decisions,
        model_instance_id=pink_model_id,
        rules_unit_instance_id=scenario.attached_unit_instance_id,
        destroying_player_id=scenario.enemy_army.player_id,
        source_rule_id="test:horrors:pending-reaction:destruction",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.SHOOTING,
        source_step="ability_resolution",
        source_result_id="test:horrors:pending-reaction:source-result",
        completion_event_type="test_horror_rule_destruction_completed",
        completion_event_payload={"model_instance_id": pink_model_id},
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=scenario.state,
            decisions=scenario.decisions,
        )
        is False
    )
    pending_unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert pending_unit.datasheet_id == "000002584"
    assert pink_model_id in pending_unit.own_model_ids()
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is False
    )
    request = restored_decisions.queue.peek_next()
    selected_option_id = (
        reaction.source_id if select_reaction else DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    result = DecisionResult.for_request(
        result_id=f"result:horrors:pending-reaction:{select_reaction}",
        request=request,
        selected_option_id=selected_option_id,
    )
    restored_decisions.submit_result(result)
    from warhammer40k_core.engine.retained_destruction_cleanup import (
        begin_retained_destruction_cleanup,
    )
    from warhammer40k_core.engine.retained_destruction_rule import resume_retained_rule_destruction
    from warhammer40k_core.engine.retained_destruction_selection import apply_retention_selection

    retained = apply_retention_selection(
        state=restored_state, decisions=restored_decisions, result=result
    )
    if select_reaction:
        assert (
            scenario.runtime.reconcile_non_attack_model_destruction_events(
                state=restored_state, decisions=restored_decisions
            )
            is False
        )
        cleanup_status = begin_retained_destruction_cleanup(
            state=restored_state, decisions=restored_decisions, reason="phase_end"
        )
    else:
        cleanup_status = resume_retained_rule_destruction(
            state=restored_state,
            decisions=restored_decisions,
            record=retained,
        )
    assert cleanup_status is None

    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is True
    )
    updated = _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is False
    )
    assert (
        sum(
            record.event_type == RULE_MODEL_DESTRUCTION_FINALIZED_EVENT
            for record in restored_decisions.event_log.records
        )
        == 1
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored_decisions.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize("use_feel_no_pain", [False, True])
def test_selected_target_mortal_wounds_finalize_horror_composition_handoff(
    use_feel_no_pain: bool,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
        game_id="order65-horror-final-0",
    )
    pink_model_id = scenario.bodyguard.own_models[0].model_instance_id
    fnp_source = FeelNoPainSource(
        source_id="test:horrors:selected-target:fnp-a",
        threshold=5,
    )
    if use_feel_no_pain:
        scenario.state.record_model_feel_no_pain_sources(
            model_instance_id=pink_model_id,
            sources=(
                fnp_source,
                FeelNoPainSource(
                    source_id="test:horrors:selected-target:fnp-b",
                    threshold=6,
                ),
            ),
        )
    selected_result = DecisionResult(
        result_id=f"result:horrors:selected-target:{use_feel_no_pain}",
        request_id="request:horrors:selected-target",
        decision_type="select_catalog_post_shoot_hit_target_effect",
        actor_id=scenario.enemy_army.player_id,
        selected_option_id=scenario.attached_unit_instance_id,
        payload={"target_unit_instance_id": scenario.attached_unit_instance_id},
    )
    resolution = resolve_selected_target_mortal_wound_effect(
        state=scenario.state,
        decisions=scenario.decisions,
        result=selected_result,
        selected_target_payload={"phase": BattlePhase.SHOOTING.value},
        record={"source_rule_id": "test:selected-target:mortal-wounds"},
        effect_payload={
            "effect": {
                "kind": "inflict_mortal_wounds",
                "parameters": [
                    {"key": "damage_kind", "value": "mortal_wounds"},
                    {"key": "mortal_wounds_expression", "value": "1"},
                    {"key": "roll_count", "value": 3},
                    {"key": "roll_expression", "value": "D6"},
                    {"key": "success_threshold", "value": 4},
                    {"key": "target_scope", "value": "selected_unit"},
                ],
            }
        },
        target_unit_ids=(scenario.attached_unit_instance_id,),
        recorded_effects_before_mortal_wounds=(),
        remaining_effect_records_after_mortal_wounds=(),
        remaining_effect_start_index=1,
    )
    if resolution.pending_status is None:
        assert resolution.resolved_payload is not None
    else:
        routed = None
        decision_index = 0
        while routed is None or routed.request is not None:
            request = scenario.decisions.queue.peek_next()
            is_model_choice = is_mortal_wound_model_request(request)
            selected_option_id = (
                pink_model_id
                if is_model_choice
                and pink_model_id in {option.option_id for option in request.options}
                else request.options[0].option_id
            )
            if not is_model_choice and use_feel_no_pain:
                selected_option_id = fnp_source.source_id
            decision_index += 1
            mortal_result = DecisionResult.for_request(
                result_id=f"result:horrors:selected-target:mortal:{decision_index}",
                request=request,
                selected_option_id=selected_option_id,
            )
            scenario.decisions.submit_result(mortal_result)
            dice_manager = None
            if not is_model_choice and use_feel_no_pain:
                fnp_spec = feel_no_pain_roll_spec(
                    source=fnp_source,
                    player_id=scenario.source_army.player_id,
                    model_instance_id=pink_model_id,
                    wound_index=1,
                )
                dice_manager = DiceRollManager(
                    scenario.state.game_id,
                    event_log=scenario.decisions.event_log,
                    injected_results=(
                        DiceRollResult.from_values(
                            roll_id="roll:horrors:selected-target:fnp",
                            spec=fnp_spec,
                            values=(1,),
                            source="fixed",
                        ),
                    ),
                )
            routed = resolve_mortal_wound_decision(
                state=scenario.state,
                decisions=scenario.decisions,
                request=request,
                result=mortal_result,
                next_request_id=f"request:horrors:selected-target:mortal:{decision_index + 1}",
                dice_manager=dice_manager,
            )
            if routed.request is not None:
                scenario.decisions.request_decision(routed.request)
        assert routed.application is not None

    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = _game_config(scenario)
    lifecycle._runtime_content_bundle = _runtime_content_bundle(scenario)
    lifecycle._reconcile_catalog_model_state_changes()
    lifecycle._reconcile_catalog_model_state_changes()

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    finalizations = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
    )
    assert len(finalizations) == 1
    finalization_payload = cast(dict[str, JsonValue], finalizations[0].payload)
    evidence = cast(dict[str, JsonValue], finalization_payload["destruction_evidence"])
    assert evidence["source_step"] == "selected_target_mortal_wounds"
    assert finalization_payload["physical_unit_instance_ids"] == [
        scenario.bodyguard.unit_instance_id
    ]
    assert finalization_payload["rules_unit_instance_ids"] == [scenario.attached_unit_instance_id]
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


def test_split_triggers_for_hazardous_but_not_non_attack_destruction() -> None:
    hazardous = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="hazardous",
    )
    status = resolve_horror_completion(hazardous.runtime, hazardous.context)
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    non_attack = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
    )
    assert resolve_horror_completion(non_attack.runtime, non_attack.context) is None
    assert non_attack.decisions.queue.pending_requests == ()
    assert all(
        record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
        for record in non_attack.decisions.event_log.records
    )


@pytest.mark.parametrize("parent_battle_phase", [BattlePhase.SHOOTING, BattlePhase.MOVEMENT])
def test_adapter_submission_dispatches_model_placed_runtime_events(
    parent_battle_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        parent_battle_phase=parent_battle_phase,
    )
    status = resolve_horror_completion(scenario.runtime, scenario.context)
    assert status is not None
    request = scenario.decisions.queue.peek_next()
    payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    config = _game_config(scenario)
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = config
    lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    lifecycle._movement_phase_handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    seen_model_ids: list[str] = []
    seen_phase_evidence: list[tuple[str, str, str]] = []
    subscription = RuntimeContentEventSubscription(
        subscription_id="test:model-placed:subscription",
        source_rule_id="test:model-placed:rule",
        trigger_kind=TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
        handler_id="test:model-placed:handler",
        filters={"player_id": scenario.source_army.player_id},
    )

    def record_placement(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        event_payload = cast(dict[str, JsonValue], context.event.event_payload)
        seen_model_ids.append(cast(str, event_payload["model_instance_id"]))
        seen_phase_evidence.append(
            (
                cast(str, event_payload["source_phase"]),
                cast(str, event_payload["action_phase"]),
                cast(str, event_payload["parent_battle_phase"]),
            )
        )
        return RuntimeContentEventResult.applied(
            subscription,
            replay_payload={"model_instance_id": event_payload["model_instance_id"]},
        )

    activation = RuntimeContentActivation.from_armies(
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
    )
    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="test:horror:model-placed",
                event_subscriptions=(subscription,),
                event_handler_bindings=(
                    RuntimeContentEventHandlerBinding(
                        handler_id="test:model-placed:handler",
                        handler=record_placement,
                    ),
                ),
            ),
        ),
        base_ability_records=catalog_ability_records_from_catalog(config.army_catalog),
    )
    lifecycle._runtime_content_bundle = bundle
    lifecycle._runtime_content_activation_input_hash = (
        lifecycle_module._runtime_content_activation_input_hash(
            config=config,
            armies=(scenario.source_army, scenario.enemy_army),
        )
    )
    lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=lifecycle._phase_handlers(),
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        runtime_event_index=bundle.event_index,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(lifecycle=lifecycle)

    submission_status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=payload,
        result_id="result:split:adapter",
    )

    assert submission_status.status_kind is not LifecycleStatusKind.INVALID
    assert tuple(sorted(seen_model_ids)) == tuple(
        sorted(cast(list[str], cast(dict[str, JsonValue], request.payload)["model_instance_ids"]))
    )
    assert set(seen_phase_evidence) == {
        (
            parent_battle_phase.value,
            BattlePhase.SHOOTING.value,
            parent_battle_phase.value,
        )
    }
    resolved_events = tuple(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "runtime_content_event_resolved"
    )
    assert len(resolved_events) == 2
    assert all(
        cast(dict[str, JsonValue], record.payload)["trigger_kind"]
        == TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD.value
        for record in resolved_events
    )


@pytest.mark.parametrize(
    ("parent_battle_phase", "out_of_phase_path"),
    [
        (BattlePhase.MOVEMENT, "fire_overwatch"),
        (BattlePhase.CHARGE, "source_backed_out_of_phase_shooting"),
    ],
)
def test_out_of_phase_split_restores_and_preserves_action_and_parent_phase_evidence(
    parent_battle_phase: BattlePhase,
    out_of_phase_path: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        source_phase=BattlePhase.SHOOTING,
        parent_battle_phase=parent_battle_phase,
    )

    status = resolve_horror_completion(scenario.runtime, scenario.context)

    assert status is not None
    request = scenario.decisions.queue.peek_next()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["action_phase"] == BattlePhase.SHOOTING.value
    assert request_payload["parent_battle_phase"] == parent_battle_phase.value
    assert request_payload["source_phase"] == parent_battle_phase.value
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    restored_request = restored_decisions.queue.peek_next()
    result = _parameterized_result(
        request=restored_request,
        payload=_placement_payload(
            request=restored_request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:split:{out_of_phase_path}",
    )
    assert (
        invalid_catalog_model_materialization_placement_status(
            state=restored_state,
            request=restored_request,
            result=result,
            decisions=restored_decisions,
            ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=scenario.package.army_catalog,
        )
        is None
    )
    restored_decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=restored_state,
        decisions=restored_decisions,
        request=restored_request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert {placement.source_phase for placement in placements} == {parent_battle_phase.value}
    for event_type in (CATALOG_MODELS_MATERIALIZED_EVENT, "battlefield_models_placed"):
        event = next(
            record
            for record in restored_decisions.event_log.records
            if record.event_type == event_type
        )
        event_payload = cast(dict[str, JsonValue], event.payload)
        assert event_payload["action_phase"] == BattlePhase.SHOOTING.value
        assert event_payload["parent_battle_phase"] == parent_battle_phase.value
        assert event_payload["source_phase"] == parent_battle_phase.value
    replayed = DecisionController.from_payload(restored_decisions.to_payload())
    assert replayed.to_payload() == restored_decisions.to_payload()


def test_overwatch_split_resumes_completed_sequence_and_resolves_reaction_frame() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        source_phase=BattlePhase.SHOOTING,
        parent_battle_phase=BattlePhase.MOVEMENT,
        pink_model_count=2,
        roll_values=(6, 6),
    )
    _record_successful_materialization_rolls(scenario)
    scenario.state.replace_out_of_phase_shooting_state(
        OutOfPhaseShootingState(
            battle_round=scenario.state.battle_round,
            player_id=scenario.enemy_army.player_id,
            parent_phase=BattlePhase.MOVEMENT,
            source_rule_id="core:fire-overwatch",
            source_decision_request_id="request:fire-overwatch",
            source_decision_result_id="result:fire-overwatch",
            source_context={
                "triggering_enemy_unit_instance_id": scenario.attached_unit_instance_id,
            },
            selected_unit_instance_id=scenario.attack_sequence.attacking_unit_instance_id,
            target_unit_ids=(scenario.attached_unit_instance_id,),
            attack_pools=scenario.attack_sequence.attack_pools,
            attack_sequence=scenario.attack_sequence,
        )
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    split_status = lifecycle.advance_until_decision_or_terminal()

    assert split_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    split_request = scenario.decisions.queue.peek_next()
    out_of_phase = scenario.state.out_of_phase_shooting_state
    assert out_of_phase is not None
    assert out_of_phase.attack_sequence is None
    assert out_of_phase.pending_completed_attack_sequence == scenario.attack_sequence
    phase_kind = battle_phase_kind_from_token(BattlePhase.MOVEMENT.value)
    reaction_window = ReactionWindow(
        timing_window=TimingWindow(
            window_id="window:fire-overwatch:horror-split",
            descriptor=TimingWindowDescriptor(
                descriptor_id="window:fire-overwatch:horror-split:descriptor",
                trigger_kind=TimingTriggerKind.DURING_PHASE,
                source_rule_id="core:fire-overwatch",
                phase=phase_kind,
                source_step="movement",
            ),
            game_id=scenario.state.game_id,
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.state.active_player_id,
            phase=phase_kind,
        ),
        eligible_player_ids=(scenario.enemy_army.player_id,),
    )
    reaction_queue = ReactionQueue.from_payload(
        {
            "frames": [
                ReactionQueueFrame(
                    reaction_window=reaction_window,
                    parent_phase=phase_kind,
                    parent_step="movement",
                    resume_token="resume:fire-overwatch:horror-split",
                    request_id=split_request.request_id,
                ).to_payload()
            ]
        }
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
        reaction_queue=reaction_queue,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored = _restored_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    for placement_index in range(1, 3):
        restored_state = restored.state
        assert restored_state is not None
        restored_out_of_phase = restored_state.out_of_phase_shooting_state
        assert restored_out_of_phase is not None
        assert restored_out_of_phase.pending_completed_attack_sequence is not None
        restored_request = restored.decision_controller.queue.peek_next()
        assert restored.reaction_queue.frames[-1].request_id == restored_request.request_id
        session = LocalGameSession(lifecycle=restored)
        status = session.submit_parameterized_payload(
            request_id=restored_request.request_id,
            payload=_placement_payload(
                request=restored_request,
                army=scenario.source_army,
                unit=scenario.bodyguard,
                y_offset=-(placement_index - 1) * 1.2,
            ),
            result_id=f"result:fire-overwatch:horror-split:placement:{placement_index}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        if placement_index == 1:
            assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            assert status.decision_request is not None
            assert restored.reaction_queue.frames
            assert (
                restored.reaction_queue.frames[-1].request_id == status.decision_request.request_id
            )
            restored = _restored_phase_lifecycle(lifecycle=restored, scenario=scenario)

    assert restored.reaction_queue.frames == ()
    restored_state = restored.state
    assert restored_state is not None
    assert restored_state.out_of_phase_shooting_state is None
    assert _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )
    assert (
        sum(
            record.event_type == "out_of_phase_shooting_completed"
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )


def test_fight_interrupt_split_resumes_completed_activation_and_resolves_reaction_frame() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        source_phase=BattlePhase.FIGHT,
        fight_interrupt_activation=True,
    )
    _record_successful_materialization_rolls(scenario)
    fight_state = scenario.state.fight_phase_state
    assert fight_state is not None
    assert fight_state.active_activation is not None
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    split_status = lifecycle.advance_until_decision_or_terminal()

    assert split_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    split_request = scenario.decisions.queue.peek_next()
    pending_fight_state = scenario.state.fight_phase_state
    assert pending_fight_state is not None
    assert pending_fight_state.attack_sequence is None
    assert pending_fight_state.pending_completed_attack_sequence == scenario.attack_sequence
    phase_kind = battle_phase_kind_from_token(BattlePhase.FIGHT.value)
    reaction_window = ReactionWindow(
        timing_window=TimingWindow(
            window_id="window:fight-interrupt:horror-split",
            descriptor=TimingWindowDescriptor(
                descriptor_id="window:fight-interrupt:horror-split:descriptor",
                trigger_kind=TimingTriggerKind.DURING_PHASE,
                source_rule_id="core:counter-offensive",
                phase=phase_kind,
                source_step="fight",
            ),
            game_id=scenario.state.game_id,
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.state.active_player_id,
            phase=phase_kind,
        ),
        eligible_player_ids=(scenario.enemy_army.player_id,),
    )
    reaction_queue = ReactionQueue.from_payload(
        {
            "frames": [
                ReactionQueueFrame(
                    reaction_window=reaction_window,
                    parent_phase=phase_kind,
                    parent_step="fight",
                    resume_token="resume:fight-interrupt:horror-split",
                    request_id=split_request.request_id,
                ).to_payload()
            ]
        }
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
        reaction_queue=reaction_queue,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored = _restored_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored_state = restored.state
    assert restored_state is not None
    restored_fight_state = restored_state.fight_phase_state
    assert restored_fight_state is not None
    assert restored_fight_state.pending_completed_attack_sequence is not None
    restored_request = restored.decision_controller.queue.peek_next()
    session = LocalGameSession(lifecycle=restored)

    status = session.submit_parameterized_payload(
        request_id=restored_request.request_id,
        payload=_placement_payload(
            request=restored_request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id="result:fight-interrupt:horror-split:placement",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert restored.reaction_queue.frames == ()
    completed_fight_state = restored_state.fight_phase_state
    assert completed_fight_state is not None
    assert completed_fight_state.active_activation is None
    assert completed_fight_state.pending_completed_attack_sequence is None
    assert _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )
    # This post-executor materialization fixture supplies no executed HIT.
    # Selection/final completion occurs once without inventing actual fighting.
    events = restored.decision_controller.event_log.records
    assert sum(event.event_type == "unit_has_fought" for event in events) == 0
    assert sum(event.event_type == "fight_selection_completed" for event in events) == 1
    assert sum(event.event_type == "fight_activation_completed" for event in events) == 1
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "source_rule",
        "clause",
        "descriptor",
        "roll",
        "result_count",
        "model_profile",
        "wargear",
        "model_ids",
    ],
)
def test_restored_split_request_revalidates_authoritative_catalog_and_roll_evidence(
    tamper_kind: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
    )
    assert resolve_horror_completion(scenario.runtime, scenario.context) is not None
    lifecycle_payload = copy.deepcopy(
        GameLifecycle(
            state=scenario.state,
            decision_controller=scenario.decisions,
        ).to_payload()
    )
    _tamper_materialization_lifecycle_payload(lifecycle_payload, tamper_kind=tamper_kind)
    restored = GameLifecycle.from_payload(lifecycle_payload)
    restored_state = restored.state
    assert restored_state is not None
    request = restored.decision_controller.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:split:tampered:{tamper_kind}",
    )

    invalid = invalid_catalog_model_materialization_placement_status(
        state=restored_state,
        request=request,
        result=result,
        decisions=restored.decision_controller,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert restored.decision_controller.queue.peek_next() == request


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        (
            "malformed_application",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "malformed_applications",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "malformed_application_item",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "missing_destroyed_model_id",
            "Catalog materialization model_instance_id must be a string",
        ),
        ("wrong_sequence", "Catalog materialization destruction evidence drift"),
    ],
)
def test_authenticated_hazardous_materialization_rejects_corrupted_provenance(
    tamper_kind: str,
    expected_error: str,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="hazardous"
    )
    events = list(event_records)
    hazardous_index = _unique_event_index(events, "hazardous_mortal_wounds_applied")
    hazardous_payload = copy.deepcopy(cast(dict[str, JsonValue], events[hazardous_index].payload))
    if tamper_kind == "malformed_application":
        hazardous_payload["mortal_wound_application"] = None
    elif tamper_kind == "malformed_applications":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        application["applications"] = None
    elif tamper_kind == "malformed_application_item":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        application["applications"] = [None]
    elif tamper_kind == "missing_destroyed_model_id":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        applications = cast(list[JsonValue], application["applications"])
        cast(dict[str, JsonValue], applications[0])["model_instance_id"] = None
    elif tamper_kind == "wrong_sequence":
        hazardous_payload["sequence_id"] = "attack-sequence:unrelated"
    else:
        raise AssertionError(f"Unsupported Hazardous evidence tamper: {tamper_kind}")
    events[hazardous_index] = replace(events[hazardous_index], payload=hazardous_payload)

    with pytest.raises(GameLifecycleError, match=expected_error):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=tuple(events),
            decision_records=decision_records,
        )


@pytest.mark.parametrize(
    ("invalid_model_ids", "expected_error"),
    [
        (None, "Catalog materialization model_instance_ids must be a string list"),
        ([""], "Catalog materialization model_instance_ids must be a string list"),
        (
            ["duplicate", "duplicate"],
            "Catalog materialization model_instance_ids contains duplicates",
        ),
    ],
)
def test_catalog_materialization_required_model_ids_fail_closed(
    invalid_model_ids: JsonValue,
    expected_error: str,
) -> None:
    _scenario, _event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    materialization_record = next(
        record
        for record in decision_records
        if record.request.decision_type
        == SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE
    )
    request_payload = copy.deepcopy(
        cast(dict[str, JsonValue], materialization_record.request.payload)
    )
    request_payload["model_instance_ids"] = invalid_model_ids

    with pytest.raises(GameLifecycleError, match=expected_error):
        _required_string_list(request_payload, "model_instance_ids")


def test_horror_catalog_keeps_materialized_profiles_out_of_mustering() -> None:
    package = horrors_package()
    for pink_datasheet_id, blue_datasheet_id in (
        ("000002584", "000002583"),
        ("000004127", "000004128"),
    ):
        pink = package.army_catalog.datasheet_by_id(pink_datasheet_id)
        assert tuple(profile.model_profile_id for profile in pink.composition) == (
            f"{pink_datasheet_id}:pink-horrors",
        )
        materialized = pink.model_profile_by_id(f"{pink_datasheet_id}:blue-horror-brimstone-horror")
        assert materialized.base_size.diameter_mm == 25.0
        pink_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"pink-{pink_datasheet_id}",
            datasheet_id=pink_datasheet_id,
            model_profile_id=f"{pink_datasheet_id}:pink-horrors",
        )
        blue_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"blue-{blue_datasheet_id}",
            datasheet_id=blue_datasheet_id,
            model_profile_id=f"{blue_datasheet_id}:blue-horrors",
        )
        assert pink_unit.own_models[0].wargear_ids == (
            f"{pink_datasheet_id}:coruscating-pink-flames",
            f"{pink_datasheet_id}:pink-claws",
        )
        assert blue_unit.own_models[0].wargear_ids == (
            f"{blue_datasheet_id}:coruscating-blue-flames",
            f"{blue_datasheet_id}:blue-claws",
        )
        assert "BLUE" in blue_unit.keywords
        assert "BRIMSTONE" not in blue_unit.keywords
        assert "PINK" in pink_unit.keywords
        assert "BLUE" not in pink_unit.keywords
        for kind, keyword in (("blue", "BLUE"), ("brimstone", "BRIMSTONE")):
            model = _retained_horror_model(
                package=package,
                pink_datasheet_id=pink_datasheet_id,
                bodyguard=pink_unit,
                horror_kind=kind,
                index=1,
            )
            assert set(model.keywords).intersection({"PINK", "BLUE", "BRIMSTONE"}) == {keyword}
            assert ModelInstance.from_payload(model.to_payload()) == model


__all__: list[str] = []
__all__ += ["Any", "ArmyDefinition", "ArmyMusterRequest", "AttachedUnitFormation"]
__all__ += ["AttackSequenceCompletedContext", "BattlefieldRuntimeState"]
__all__ += ["CanonicalCatalogPackage", "CatalogModelMaterializationRuntime", "DecisionRecord"]
__all__ += ["DetachmentSelection", "EventRecord", "FightActivationSelection"]
__all__ += ["FightEligibilityKind", "FightPhaseHandler", "FightPhaseState", "FightPhaseStepKind"]
__all__ += ["FightsFirstRegistry", "GameConfig", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["PlacedArmy", "PlacementProposalPayload", "Pose", "ProposalKind", "RangedAttackPool"]
__all__ += ["RuntimeModifierRegistry", "ShootingPhaseState", "ShootingType", "UnitFactory"]
__all__ += ["UnitInstance", "UnitMusterSelection", "UnitPlacement", "_SplitScenario"]
__all__ += ["_alive_unit_placement_or_none", "_army", "_attack_sequence"]
__all__ += ["_corrupt_authenticated_materialization_evidence", "_model_count_unit"]
__all__ += ["_record_split_interrupt_activation", "_unit_placement"]
__all__ += ["apply_feel_no_pain_decision", "battle_state_with_armies", "dataclass"]
__all__ += ["deadly_demise_trigger_roll_spec", "player_ability_index"]
