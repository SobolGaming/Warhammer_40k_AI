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


def test_split_mixed_rolls_materialize_only_successes_before_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        pink_model_count=2,
        roll_values=(6, 1),
    )

    status = resolve_horror_completion(scenario.runtime, scenario.context)
    assert status is not None
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id="result:split:mixed",
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

    assert resolve_horror_completion(scenario.runtime, scenario.context) is None

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 2
    roll_events = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    assert [payload["successful"] for payload in roll_events] == [True, False]


def test_matching_sequence_model_destroyed_event_requires_typed_attribution() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
    )
    payload = copy.deepcopy(scenario.decisions.to_payload())
    source_event = next(
        record for record in payload["event_log"] if record["event_type"] == "model_destroyed"
    )
    destruction = cast(dict[str, JsonValue], source_event["payload"])
    del destruction["destruction_provenance"]
    malformed_decisions = DecisionController.from_payload(payload)
    malformed_context = replace(
        scenario.context,
        decisions=malformed_decisions,
        dice_manager=DiceRollManager(
            scenario.state.game_id,
            event_log=malformed_decisions.event_log,
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match="model_destroyed attribution payload is missing required fields",
    ):
        resolve_horror_completion(scenario.runtime, malformed_context)


def test_deadly_demise_collateral_finalizes_horror_composition_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    scenario.state.active_player_id = scenario.source_army.player_id
    battlefield = scenario.state.battlefield_state
    assert battlefield is not None
    scenario.state.replace_battlefield_state(
        replace(
            battlefield,
            placed_armies=tuple(
                replace(
                    placed_army,
                    unit_placements=tuple(
                        replace(
                            placement,
                            model_placements=tuple(
                                replace(model_placement, pose=Pose.at(12.5, 10.0))
                                for model_placement in placement.model_placements
                            ),
                        )
                        if placement.unit_instance_id
                        == scenario.attack_sequence.attacking_unit_instance_id
                        else placement
                        for placement in placed_army.unit_placements
                    ),
                )
                for placed_army in battlefield.placed_armies
            ),
        )
    )
    pink_model = scenario.bodyguard.own_models[0]
    enemy_unit = _unit_by_id(
        scenario.state,
        scenario.attack_sequence.attacking_unit_instance_id,
    )
    enemy_model = replace(
        enemy_unit.own_models[0],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 5)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in enemy_unit.own_models[0].characteristics
        ),
    )
    enemy_unit = replace(enemy_unit, own_models=(enemy_model,))
    enemy_army = replace(
        scenario.enemy_army,
        units=tuple(
            enemy_unit if unit.unit_instance_id == enemy_unit.unit_instance_id else unit
            for unit in scenario.enemy_army.units
        ),
    )
    scenario.state.replace_army_definitions([scenario.source_army, enemy_army])
    deadly_demise_source = DestructionReactionSource(
        source_id="test:horrors:deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="test:horrors:deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": 1},
        },
        optional=False,
    )
    scenario.state.record_model_destruction_reaction_sources(
        model_instance_id=enemy_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    source_sequence = _attack_sequence(
        package=scenario.package,
        attacker=scenario.bodyguard,
        attacker_player_id=scenario.source_army.player_id,
        target=enemy_unit,
        target_unit_instance_id=enemy_unit.unit_instance_id,
    )
    base_pool = source_sequence.attack_pools[0]
    lethal_profile = replace(
        base_pool.weapon_profile,
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(enemy_model.current_wounds),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    lethal_pool = replace(base_pool, weapon_profile=lethal_profile)
    attack_sequence = AttackSequence.start(
        sequence_id="deadly-demise:horror-composition-handoff",
        attacker_player_id=scenario.source_army.player_id,
        attacking_unit_instance_id=scenario.attached_unit_instance_id,
        attack_pools=(lethal_pool,),
        source_phase=BattlePhase.SHOOTING,
    )
    scenario.state.replace_shooting_phase_state(
        ShootingPhaseState(
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.source_army.player_id,
            selected_unit_ids=(scenario.attached_unit_instance_id,),
            shot_unit_ids=(scenario.attached_unit_instance_id,),
            attack_pools=attack_sequence.attack_pools,
            attack_sequence=attack_sequence,
        )
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=lethal_pool.weapon_profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.source_army.player_id,
    )
    save_option = mandatory_save_option(
        save_options_for_model(
            model=enemy_model,
            armor_penetration=0,
        )
    )
    assert save_option is not None
    save_spec = saving_throw_roll_spec(
        save_kind=save_option.save_kind,
        player_id=scenario.enemy_army.player_id,
        allocated_model_id=enemy_model.model_instance_id,
        attack_context_id=attack_sequence.attack_context_id(),
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id=scenario.enemy_army.player_id,
        model_instance_id=enemy_model.model_instance_id,
    )

    dice_manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:wound",
                spec=wound_spec,
                values=(6,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:save",
                spec=save_spec,
                values=(1,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:trigger",
                spec=deadly_demise_spec,
                values=(6,),
                source="fixed",
            ),
        ),
    )
    remaining, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    for decision_index in range(128):
        if status is None:
            if remaining is None:
                break
            remaining, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
                state=scenario.state,
                decisions=scenario.decisions,
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                attack_sequence=remaining,
                already_allocated_model_ids=allocated_model_ids,
                dice_manager=dice_manager,
            )
            continue
        request = status.decision_request
        assert request is not None
        assert is_mortal_wound_model_request(request)
        selected_model_id = (
            pink_model.model_instance_id
            if pink_model.model_instance_id in {option.option_id for option in request.options}
            else request.options[0].option_id
        )
        mortal_result = DecisionResult.for_request(
            result_id=f"result:horrors:deadly-demise:model:{decision_index}",
            request=request,
            selected_option_id=selected_model_id,
        )
        scenario.decisions.submit_result(mortal_result)
        assert remaining is not None
        remaining, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=scenario.state,
            decisions=scenario.decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            attack_sequence=remaining,
            result=mortal_result,
            already_allocated_model_ids=allocated_model_ids,
            dice_manager=dice_manager,
        )
    else:
        raise AssertionError("Deadly Demise mortal wound model choices did not drain.")

    assert remaining is None
    assert status is None
    pink_destruction = next(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload).get("model_instance_id")
        == pink_model.model_instance_id
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(pink_destruction)
    assert (
        attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.DEADLY_DEMISE
    )
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
    assert tuple(model.model_instance_id for model in updated.own_models) == (
        scenario.bodyguard.own_models[1].model_instance_id,
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        ("materialized_game_id", "Catalog materialization game identity drift"),
        ("missing_request_id", "Catalog materialization request_id must be a string"),
        (
            "missing_decision_record",
            "Catalog materialization lacks one accepted decision record",
        ),
        ("malformed_request_payload", "Catalog materialization request payload is malformed"),
        (
            "inactive_source",
            "Catalog materialization does not resolve to one active source provider",
        ),
        ("decision_identity", "Catalog materialization decision identity drift"),
        ("request_payload", "Catalog materialization request payload drift"),
        ("malformed_result_payload", "Catalog materialization result payload is malformed"),
        ("accepted_placement", "Catalog materialization accepted placement drift"),
        ("accepted_model_set", "Catalog materialization accepted model set drift"),
        ("roll_identity", "Catalog materialization roll identity drift"),
        ("roll_context", "Catalog materialization roll context drift"),
        (
            "completion_sequence",
            "Catalog materialization attack completion sequence drift",
        ),
        ("roll_before_completion", "Catalog materialization roll precedes its attack completion"),
        ("destroyed_model_source", "Catalog materialization destroyed model source drift"),
        ("destruction_evidence", "Catalog materialization destruction evidence drift"),
        ("malformed_roll_payload", "Catalog materialization roll payload is malformed"),
        ("roll_specification", "Catalog materialization roll specification drift"),
        ("unsuccessful_roll", "Catalog materialization successful roll result drift"),
        ("evidence_order", "Catalog materialization evidence order drift"),
        ("missing_terminal", "Catalog materialization lacks its placement terminal event"),
        ("terminal_payload", "Catalog materialization placement terminal payload drift"),
        (
            "request_provenance",
            "Catalog materialization decision request provenance drift",
        ),
        (
            "record_provenance",
            "Catalog materialization decision record provenance drift",
        ),
        ("malformed_materialized_event", "catalog materialization event payload is malformed"),
        (
            "malformed_completion_event",
            "catalog materialization attack completion event payload is malformed",
        ),
        ("completion_payload", "Catalog materialization completion payload drift"),
        ("invalid_battle_round", "Catalog materialization battle_round must be an integer"),
    ],
)
def test_authenticated_materialization_rejects_corrupted_evidence_graph(
    tamper_kind: str,
    expected_error: str,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    tampered_events, tampered_records = _corrupt_authenticated_materialization_evidence(
        scenario=scenario,
        event_records=event_records,
        decision_records=decision_records,
        tamper_kind=tamper_kind,
    )

    with pytest.raises(GameLifecycleError, match=expected_error):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=tampered_events,
            decision_records=tampered_records,
        )


def test_authenticated_materialization_rejects_duplicate_event_identity() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization event identities are duplicated",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=(*event_records, event_records[0]),
            decision_records=decision_records,
        )


def test_authenticated_materialization_rejects_reused_roll_and_decision_evidence() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    events = list(event_records)
    materialized_index = _unique_event_index(events, CATALOG_MODELS_MATERIALIZED_EVENT)
    materialized = events[materialized_index]
    terminal = events[materialized_index + 1]
    cloned_materialized = replace(
        materialized,
        event_id="event:catalog-materialization:reused-evidence",
    )
    terminal_payload = copy.deepcopy(cast(dict[str, JsonValue], terminal.payload))
    terminal_payload["source_event_id"] = cloned_materialized.event_id
    cloned_terminal = replace(
        terminal,
        event_id="event:catalog-materialization:reused-evidence:terminal",
        payload=terminal_payload,
    )

    with pytest.raises(GameLifecycleError, match="Catalog materialization evidence is reused"):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=(*events, cloned_materialized, cloned_terminal),
            decision_records=decision_records,
        )


def test_authenticated_materialization_requires_active_provider_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )

    def no_bindings(_runtime: CatalogModelMaterializationRuntime) -> tuple[Any, ...]:
        return ()

    monkeypatch.setattr(CatalogModelMaterializationRuntime, "bindings", no_bindings)

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization has no active runtime provider binding",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=event_records,
            decision_records=decision_records,
        )


def test_authenticated_second_split_rejects_missing_required_model_source() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack",
        destroyed_horror_kinds=("blue",),
    )
    source_model = scenario.source_army.units[0].own_models[0]
    assert "horror-materialization:blue-horror" in source_model.source_ids
    tampered_model = replace(
        source_model,
        keyword_assignment=replace(
            source_model.keyword_assignment,
            materialization_descriptor_id=None,
            source_ids=tuple(
                source_id
                for source_id in source_model.keyword_assignment.source_ids
                if source_id != "horror-materialization:blue-horror"
            ),
        ),
        source_ids=tuple(
            source_id
            for source_id in source_model.source_ids
            if source_id != "horror-materialization:blue-horror"
        ),
    )
    tampered_unit = replace(scenario.source_army.units[0], own_models=(tampered_model,))
    tampered_army = replace(
        scenario.source_army,
        units=(tampered_unit, *scenario.source_army.units[1:]),
    )

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization destroyed model source drift",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(tampered_army, scenario.enemy_army),
            event_records=event_records,
            decision_records=decision_records,
        )


__all__: list[str] = []
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "AttachedUnitFormation"]
__all__ += ["AttackSequenceCompletedContext", "BattleRoundFlow", "BattlefieldPlacementKind"]
__all__ += ["BattlefieldRuntimeState", "BattlefieldTransitionBatch"]
__all__ += ["BattlefieldTransitionBatchPayload", "CanonicalCatalogPackage"]
__all__ += ["DECLINE_DESTRUCTION_REACTION_OPTION_ID", "DecisionRecord", "DetachmentSelection"]
__all__ += ["DiceExpression", "DiceRollSpec", "EffectExpiration", "EventRecord"]
__all__ += ["FeelNoPainSource", "FightActivationSelection", "FightEligibilityKind"]
__all__ += ["FightPhaseHandler", "FightPhaseState", "FightPhaseStepKind", "FightsFirstRegistry"]
__all__ += ["GameConfig", "GameState", "LifecycleStatusKind", "LocalGameSession"]
__all__ += ["MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT", "ModelInstance", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "MovementPhaseHandler", "OutOfPhaseShootingState"]
__all__ += ["PersistingEffect", "PlacedArmy", "PlacementProposalPayload", "ProposalKind"]
__all__ += ["RULE_MODEL_DESTRUCTION_FINALIZED_EVENT", "RangedAttackPool", "ReactionQueue"]
__all__ += ["ReactionQueueFrame", "ReactionWindow", "RuntimeContentActivation"]
__all__ += ["RuntimeContentBundle", "RuntimeContentContribution", "RuntimeContentEventContext"]
__all__ += ["RuntimeContentEventHandlerBinding", "RuntimeContentEventResult"]
__all__ += ["RuntimeContentEventSubscription", "RuntimeModifierRegistry"]
__all__ += ["SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE"]
__all__ += ["ShootingPhaseHandler", "ShootingType", "TimingTriggerKind", "TimingWindow"]
__all__ += ["TimingWindowDescriptor", "UnitFactory", "UnitInstance", "UnitMusterSelection"]
__all__ += ["UnitPlacement", "_SplitScenario", "_alive_unit_placement_or_none", "_army"]
__all__ += ["_configure_phase_lifecycle", "_model_count_unit"]
__all__ += ["_record_split_interrupt_activation", "_record_successful_materialization_rolls"]
__all__ += ["_required_string_list", "_restored_phase_lifecycle", "_retained_horror_model"]
__all__ += ["_single_model_unit", "_tamper_materialization_lifecycle_payload", "_unit_placement"]
__all__ += ["assert_parameterized_projection", "battle_phase_kind_from_token"]
__all__ += ["battle_state_with_armies", "catalog_ability_records_from_catalog", "dataclass"]
__all__ += ["feel_no_pain_roll_spec", "horrors_package"]
__all__ += ["invalid_catalog_model_materialization_placement_status", "lifecycle_module"]
__all__ += ["player_ability_index", "reconcile_after_attack_sequence"]
__all__ += ["resolve_mortal_wound_decision", "resolve_selected_target_mortal_wound_effect"]
__all__ += ["rule_model_destruction", "rules_unit_view_by_id", "validate_json_value"]
