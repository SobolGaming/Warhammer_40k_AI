from __future__ import annotations

from typing import cast

from tests.shared.category_migration.generic_rule_ability_registry import (
    _ENEMY_UNIT_ID,
    _RANGERS_UNIT_ID,
    _SHROUD_RUNNERS_UNIT_ID,
    _WARPTIDE_UNIT_ID,
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
    AdvanceEligibilityContext,
    AdvanceMoveContext,
    AdvanceMoveGrant,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BaseSizeDefinition,
    BattleFormationRequestContext,
    BattleFormationResultContext,
    BattlePhase,
    Callable,
    Characteristic,
    CharacteristicValue,
    DecisionController,
    DetachmentSelection,
    EffectExpiration,
    EnhancementAssignment,
    EnhancementEffectContext,
    FallBackEligibilityContext,
    FightActivationAbilityContext,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
    FightUnitSelectedContext,
    GameConfig,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    GenericRuleAbilityHookFamily,
    GenericRuleAbilityRegistry,
    GenericRuleAbilitySource,
    JsonValue,
    ModelGeometry,
    ModelInstance,
    ModelKeywordAssignment,
    ModelProfileSelection,
    ModifierOperation,
    ModifierTerm,
    MovementEndSurgeContext,
    ObjectiveControlModifierContext,
    PersistingEffect,
    PhaseEndObjectiveControlContext,
    ReserveArrivalDistanceContext,
    RuleEffectKind,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleIR,
    RulesetDescriptor,
    RuleTargetKind,
    RuntimeContentActivation,
    SaveOptionModifierContext,
    SetupStep,
    ShootingTargetRestrictionContext,
    ShootingUnitSelectedContext,
    StartingStrengthRecord,
    StratagemCategory,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    StratagemCostModifierContext,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    TimingTriggerKind,
    TurnEndRequestContext,
    TurnEndResultContext,
    UnitDestroyedContext,
    UnitInstance,
    UnitMusterSelection,
    WeaponKeyword,
    _aeldari_corsair_coterie_source,
    _aeldari_path_of_the_outcast_source,
    _army,
    _blood_legion_source,
    _court_of_the_phoenician_source,
    _grant_ability_effect,
    _keyword_any_state,
    _minimal_warptide_game_config,
    _model,
    _muster_request,
    _owner_player_id_for_unit_id,
    _raise_selected_to_fight_payload_error,
    _selected_to_fight_effect_payload,
    _selected_to_fight_grant_payload,
    _selected_to_fight_reroll_payload,
    _shadow_legion_enhancement_source,
    _shadow_legion_source,
    _unit,
    _warptide_activation,
    _warptide_cost_modifier_context,
    _warptide_grant_ability_effect,
    _warptide_setup_state,
    _warptide_source,
    _warptide_state,
    advance_move_lifecycle_hooks,
    blood_legion_ir,
    copy,
    corsair_enhancements,
    corsair_ir,
    court_ir,
    court_rule,
    dark_pacts,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
    generic_detachment_effects,
    generic_rule_ability_effects_for_unit,
    generic_rule_lifecycle_hook_handlers,
    generic_rule_lifecycle_hooks,
    generic_rule_persisting_effect,
    generic_rule_selected_to_fight_effects,
    path_outcast_ir,
    pytest,
    replace,
    rule_ir_grants_any_ability,
    shadow_legion_ir,
    validate_json_value,
    warptide_ir,
    with_unit_keywords,
)


def test_warptide_shudderblink_advance_move_grant_is_automatic_assault() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:assault-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    state.record_persisting_effect(effect)
    matching_effects = generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_move_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="advance",
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert descriptor.context_predicate(context, source, matching_effects)

    grant = descriptor.grant_builder(context, source, matching_effects)
    assert grant.hook_id == warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID
    assert grant.source_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert grant.automatic is True
    assert grant.granted_ranged_weapon_keywords == (WeaponKeyword.ASSAULT.value,)
    assert grant.unit_effect_expiration == "end_turn"
    assert isinstance(grant.unit_effect_payload, dict)
    assert grant.unit_effect_payload["granted_weapon_keywords"] == [WeaponKeyword.ASSAULT.value]


def test_warptide_shudderblink_advance_move_predicate_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:assault-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_move_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    normal_move_context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="normal_move",
        movement_request_id="warptide-normal-request",
        movement_result_id="warptide-normal-result",
    )

    assert not descriptor.context_predicate(normal_move_context, source, ())
    assert not descriptor.context_predicate(normal_move_context, source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(AdvanceMoveContext, object()), source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(
            normal_move_context,
            cast(GenericRuleAbilitySource, object()),
            (effect,),
        )
    with pytest.raises(GameLifecycleError, match="hook ID requires source"):
        descriptor.hook_id(cast(GenericRuleAbilitySource, object()))


def test_warptide_advance_move_lifecycle_binding_dispatches_generic_handler() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    record = source.record
    context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="advance",
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )
    bindings = advance_move_lifecycle_hooks.advance_move_hook_bindings(
        activation=_warptide_activation(),
        execution_records=(record,),
    )

    assert len(bindings) == 1
    assert bindings[0].handler(context) is None

    state.record_persisting_effect(
        _warptide_grant_ability_effect(
            source=source,
            effect_id="warptide:shudderblink:assault-after-advance",
            target_unit_instance_id=_WARPTIDE_UNIT_ID,
            ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
        )
    )
    grant = bindings[0].handler(context)
    assert grant is not None
    assert grant.automatic is True
    with pytest.raises(GameLifecycleError, match="requires context"):
        bindings[0].handler(cast(AdvanceMoveContext, object()))


def test_warptide_advance_move_lifecycle_bindings_are_fail_fast() -> None:
    record = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID).record

    with pytest.raises(GameLifecycleError, match="require activation"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=(record,),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=(replace(record, rule_ir_hash="0" * 64),),
        )
    assert (
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=RuntimeContentActivation(
                selected_faction_ids=(warptide_ir.CHAOS_DAEMONS_FACTION_ID,),
                selected_detachment_ids=(),
                selected_enhancement_ids=(),
                selected_stratagem_ids=(),
                selected_datasheet_ids=(),
                selected_wargear_ids=(),
                selected_weapon_profile_ids=(),
                selected_weapon_keywords=(),
                loaded_unit_instance_ids=(),
            ),
            execution_records=(record,),
        )
        == ()
    )


def test_advance_move_grant_payload_round_trips_automatic_default() -> None:
    grant = AdvanceMoveGrant(
        hook_id="warptide:auto-advance",
        source_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
        label="Shudderblink",
        granted_ranged_weapon_keywords=(WeaponKeyword.ASSAULT.value,),
        automatic=True,
        replay_payload={"source": "warptide-test"},
    )

    payload = grant.to_payload()
    assert payload.get("automatic") is True
    assert AdvanceMoveGrant.from_payload(payload).automatic is True

    payload.pop("automatic")
    assert AdvanceMoveGrant.from_payload(payload).automatic is False


def test_warptide_shudderblink_advance_eligibility_grants_charge_after_advance() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:charge-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    state.record_persisting_effect(effect)
    matching_effects = generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert descriptor.context_predicate(context, source, matching_effects)

    grant = descriptor.grant_builder(context, source, matching_effects)
    assert grant.hook_id == warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID
    assert grant.source_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert grant.can_shoot is True
    assert grant.can_declare_charge is True
    assert isinstance(grant.replay_payload, dict)
    assert grant.replay_payload["effect_kind"] == "shudderblink_advance_eligibility"


def test_warptide_shudderblink_advance_eligibility_predicate_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:charge-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert not descriptor.context_predicate(context, source, ())
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(AdvanceEligibilityContext, object()), source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(
            context,
            cast(GenericRuleAbilitySource, object()),
            (effect,),
        )
    with pytest.raises(GameLifecycleError, match="hook ID requires source"):
        descriptor.hook_id(cast(GenericRuleAbilitySource, object()))


def test_warptide_soul_hungry_cost_modifier_reduces_core_reactive_stratagems() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:soul-hungry:cost",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,
    )
    state.record_persisting_effect(effect)
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.stratagem_cost_modifier_abilities
        if ability.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    context = _warptide_cost_modifier_context(state=state, target_unit_id=_WARPTIDE_UNIT_ID)

    assert descriptor.context_predicate(context, source)
    assert descriptor.modifier_builder(context, source) == ModifierTerm(
        ModifierOperation.SUBTRACT, 1
    )

    enemy_context = _warptide_cost_modifier_context(state=state, target_unit_id=_ENEMY_UNIT_ID)
    assert not descriptor.context_predicate(enemy_context, source)


def test_warptide_soul_hungry_cost_modifier_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.stratagem_cost_modifier_abilities
        if ability.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    context = _warptide_cost_modifier_context(state=state, target_unit_id=_WARPTIDE_UNIT_ID)

    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(StratagemCostModifierContext, object()), source)
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(context, cast(GenericRuleAbilitySource, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.modifier_builder(cast(StratagemCostModifierContext, object()), source)
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.modifier_builder(context, cast(GenericRuleAbilitySource, object()))
    with pytest.raises(GameLifecycleError, match="modifier ID requires source"):
        descriptor.modifier_id(cast(GenericRuleAbilitySource, object()))


def test_court_runtime_contribution_delegates_cost_modifier_to_generic_ir() -> None:
    contribution = court_rule.runtime_contribution()

    assert contribution.contribution_id == court_rule.CONTRIBUTION_ID
    assert contribution.stratagem_cost_modifier_bindings == ()


def test_generic_rule_ability_source_validates_rule_ir_hash() -> None:
    source = _shadow_legion_source()
    stale_record = replace(source.record, rule_ir_hash="0" * 64)

    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        GenericRuleAbilitySource(record=stale_record, rule_ir=source.rule_ir)


def test_rule_ir_grants_any_ability_uses_grant_ability_parameters() -> None:
    source = _shadow_legion_source()

    assert rule_ir_grants_any_ability(
        source.rule_ir,
        abilities=(shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,),
    )
    assert not rule_ir_grants_any_ability(source.rule_ir, abilities=("missing_ability",))


def test_generic_rule_ability_effects_for_unit_enforces_required_keyword_any() -> None:
    state = _keyword_any_state()
    source = _aeldari_path_of_the_outcast_source(
        path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID
    )
    required_keywords = (path_outcast_ir.RANGERS_KEYWORD, path_outcast_ir.SHROUD_RUNNERS_KEYWORD)
    ranger_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:rangers",
        target_unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    shroud_runner_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:shroud-runners",
        target_unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    enemy_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:enemy",
        target_unit_instance_id=_ENEMY_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    for effect in (ranger_effect, shroud_runner_effect, enemy_effect):
        state.record_persisting_effect(effect)

    assert generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
    ) == (ranger_effect,)
    assert generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
    ) == (shroud_runner_effect,)
    assert (
        generic_rule_ability_effects_for_unit(
            state=state,
            source=source,
            unit_instance_id=_ENEMY_UNIT_ID,
            ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        )
        == ()
    )


def test_generic_rule_ability_effects_for_unit_rejects_empty_required_keyword_any() -> None:
    state = _keyword_any_state()
    source = _aeldari_path_of_the_outcast_source(
        path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID
    )
    effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:empty",
        target_unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=(),
    )
    state.record_persisting_effect(effect)

    with pytest.raises(GameLifecycleError, match="required_keyword_any must not be empty"):
        generic_rule_ability_effects_for_unit(
            state=state,
            source=source,
            unit_instance_id=_RANGERS_UNIT_ID,
            ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("missing_effect", "payload must be an object"),
        ("missing_kind", "effect kind must be a string"),
        ("unknown_kind", "effect kind is unsupported"),
        ("parameters_not_list", "effect parameters must be a list"),
        ("parameter_not_object", "payload must be an object"),
        ("parameter_missing_key", "effect parameter requires key"),
        ("duplicate_parameter", "effect parameters are duplicated"),
        ("wrong_target", "effects must target this model"),
        ("wrong_dice_quantity", "mortal wounds require one die"),
        ("wrong_dice_sides", "mortal wounds require a D3"),
        ("wrong_modifier", r"mortal wounds require a \+1 modifier"),
        ("missing_duration", "payload must be an object"),
        ("wrong_duration_kind", "reroll duration is unsupported"),
        ("duration_parameters_not_list", "duration parameters must be a list"),
        ("duration_parameter_not_object", "payload must be an object"),
        ("wrong_duration_endpoint", "rerolls must expire at phase end"),
    ],
)
def test_selected_to_fight_rule_ir_payload_validation_fails_closed(
    case: str,
    expected_error: str,
) -> None:
    payload = _selected_to_fight_effect_payload()
    with pytest.raises(GameLifecycleError, match=expected_error):
        _raise_selected_to_fight_payload_error(case=case, payload=payload)


def test_selected_to_fight_rule_ir_payload_helpers_accept_canonical_payload() -> None:
    payload = _selected_to_fight_effect_payload()

    assert (
        generic_rule_selected_to_fight_effects._effect_kind(  # pyright: ignore[reportPrivateUsage]
            payload
        )
        is RuleEffectKind.INFLICT_MORTAL_WOUNDS
    )
    parameters = generic_rule_selected_to_fight_effects._effect_parameters(  # pyright: ignore[reportPrivateUsage]
        payload
    )
    generic_rule_selected_to_fight_effects._require_this_model_target(  # pyright: ignore[reportPrivateUsage]
        payload
    )
    generic_rule_selected_to_fight_effects._validate_self_mortal_wound_parameters(  # pyright: ignore[reportPrivateUsage]
        parameters
    )
    generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
        payload
    )


def test_selected_to_fight_enhancement_bearer_and_entrypoints_require_exact_types() -> None:
    state = _keyword_any_state()
    state = replace(
        state,
        battle_phase_index=state.battle_phase_sequence.index(BattlePhase.FIGHT),
    )
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    assignment = EnhancementAssignment(
        model_profile_id="selected-to-fight-datasheet-profile",
        model_index=1,
        enhancement_id="selected-to-fight-test",
        target_unit_selection_id="selected-to-fight-unit",
        source_id="selected-to-fight-assignment",
    )
    bearer = generic_rule_selected_to_fight_effects.SelectedToFightEnhancementBearer(
        army=army,
        assignment=assignment,
        physical_unit=unit,
        model=model,
        selected_rules_unit_instance_id=unit.unit_instance_id,
    )
    assert bearer.model is model

    with pytest.raises(GameLifecycleError, match="requires ArmyDefinition"):
        generic_rule_selected_to_fight_effects.SelectedToFightEnhancementBearer(
            army=cast(ArmyDefinition, object()),
            assignment=assignment,
            physical_unit=unit,
            model=model,
            selected_rules_unit_instance_id=unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires assignment"):
        generic_rule_selected_to_fight_effects.SelectedToFightEnhancementBearer(
            army=army,
            assignment=cast(EnhancementAssignment, object()),
            physical_unit=unit,
            model=model,
            selected_rules_unit_instance_id=unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires physical unit"):
        generic_rule_selected_to_fight_effects.SelectedToFightEnhancementBearer(
            army=army,
            assignment=assignment,
            physical_unit=cast(UnitInstance, object()),
            model=model,
            selected_rules_unit_instance_id=unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires model"):
        generic_rule_selected_to_fight_effects.SelectedToFightEnhancementBearer(
            army=army,
            assignment=assignment,
            physical_unit=unit,
            model=cast(ModelInstance, object()),
            selected_rules_unit_instance_id=unit.unit_instance_id,
        )

    context = FightUnitSelectedContext(
        state=state,
        player_id=army.player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        fight_type="normal",
        ordering_band="remaining_combats",
        request_id="selected-to-fight-request",
        result_id="selected-to-fight-result",
    )
    source = _shadow_legion_source()
    with pytest.raises(GameLifecycleError, match="lookup requires context"):
        generic_rule_selected_to_fight_effects.selected_to_fight_enhancement_bearer_is_alive(
            cast(FightUnitSelectedContext, object()),
            source,
            (),
        )
    with pytest.raises(GameLifecycleError, match="lookup requires source"):
        generic_rule_selected_to_fight_effects.selected_to_fight_enhancement_bearer_is_alive(
            context,
            cast(GenericRuleAbilitySource, object()),
            (),
        )
    with pytest.raises(GameLifecycleError, match="matching effects must be a tuple"):
        generic_rule_selected_to_fight_effects.selected_to_fight_enhancement_bearer_is_alive(
            context,
            source,
            cast(tuple[PersistingEffect, ...], []),
        )

    with pytest.raises(GameLifecycleError, match="grant requires context"):
        generic_rule_selected_to_fight_effects.build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
            cast(FightUnitSelectedContext, object()),
            source,
            (),
            ability_id="selected-to-fight-ability",
            hook_id="selected-to-fight-hook",
            label="Selected to Fight",
        )
    with pytest.raises(GameLifecycleError, match="grant requires source"):
        generic_rule_selected_to_fight_effects.build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
            context,
            cast(GenericRuleAbilitySource, object()),
            (),
            ability_id="selected-to-fight-ability",
            hook_id="selected-to-fight-hook",
            label="Selected to Fight",
        )
    with pytest.raises(GameLifecycleError, match="grant effects must be a tuple"):
        generic_rule_selected_to_fight_effects.build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
            context,
            source,
            cast(tuple[PersistingEffect, ...], []),
            ability_id="selected-to-fight-ability",
            hook_id="selected-to-fight-hook",
            label="Selected to Fight",
        )
    with pytest.raises(GameLifecycleError, match="grant label must be non-empty"):
        generic_rule_selected_to_fight_effects.build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
            context,
            source,
            (),
            ability_id="selected-to-fight-ability",
            hook_id="selected-to-fight-hook",
            label=" ",
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("unrelated_grant", "unrelated ability grant"),
        ("invalid_reroll_type", "must be for Hit or Wound"),
        ("specific_reroll", "must permit the whole roll"),
        ("duplicate_reroll", "permissions are duplicated"),
        ("unsupported_effect", "contains an unsupported effect"),
        ("missing_grant", "requires one hook ability grant"),
        ("missing_immediate", "requires one immediate effect"),
        ("missing_wound_reroll", "requires Hit and Wound rerolls"),
    ],
)
def test_selected_to_fight_effect_set_validation_fails_closed(
    case: str,
    expected_error: str,
) -> None:
    source = _shadow_legion_source()
    ability_id = "selected-to-fight-ability"
    assignment = EnhancementAssignment(
        model_profile_id="selected-to-fight-datasheet-profile",
        model_index=1,
        enhancement_id="selected-to-fight-test",
        target_unit_selection_id="selected-to-fight-unit",
        source_id="selected-to-fight-assignment",
    )
    grant = _selected_to_fight_grant_payload(ability_id)
    mortal_wounds = _selected_to_fight_effect_payload()
    hit_reroll = _selected_to_fight_reroll_payload("hit")
    wound_reroll = _selected_to_fight_reroll_payload("wound")
    effect_payloads: list[dict[str, JsonValue]] = [
        grant,
        mortal_wounds,
        hit_reroll,
        wound_reroll,
    ]
    if case == "unrelated_grant":
        effect_payloads[0] = _selected_to_fight_grant_payload("unrelated-ability")
    elif case == "invalid_reroll_type":
        effect_payloads[2] = _selected_to_fight_reroll_payload("save")
    elif case == "specific_reroll":
        hit_effect = cast(dict[str, JsonValue], hit_reroll["effect"])
        hit_parameters = cast(list[JsonValue], hit_effect["parameters"])
        hit_parameters.append({"key": "reroll_unmodified_value", "value": 1})
    elif case == "duplicate_reroll":
        effect_payloads[3] = _selected_to_fight_reroll_payload("hit")
    elif case == "unsupported_effect":
        unsupported_effect: dict[str, JsonValue] = {
            "target": {"kind": RuleTargetKind.THIS_MODEL.value},
            "effect": {
                "kind": RuleEffectKind.MODIFY_CHARACTERISTIC.value,
                "parameters": [],
            },
        }
        effect_payloads = [unsupported_effect]
    elif case == "missing_grant":
        effect_payloads = [mortal_wounds, hit_reroll, wound_reroll]
    elif case == "missing_immediate":
        effect_payloads = [grant, hit_reroll, wound_reroll]
    elif case == "missing_wound_reroll":
        effect_payloads = [grant, mortal_wounds, hit_reroll]
    else:
        raise AssertionError(f"Unhandled test case: {case}")
    result = RuleExecutionResult(
        rule_id="selected-to-fight-rule",
        source_id="selected-to-fight-source",
        rule_ir_hash="selected-to-fight-rule-ir-hash",
        status=RuleExecutionStatus.APPLIED,
        effect_payloads=tuple(effect_payloads),
    )

    with pytest.raises(GameLifecycleError, match=expected_error):
        generic_rule_selected_to_fight_effects._selected_to_fight_effects(  # pyright: ignore[reportPrivateUsage]
            source=source,
            result=result,
            assignment=assignment,
            ability_id=ability_id,
        )


def test_generic_lifecycle_generated_handlers_reject_wrong_context_types() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY
    source = _shadow_legion_source()

    advance = generic_rule_lifecycle_hooks._advance_eligibility_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.advance_eligibility_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        advance(cast(AdvanceEligibilityContext, object()))

    target_restriction = (
        generic_rule_lifecycle_hooks._shooting_target_restriction_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.shooting_target_restriction_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        target_restriction(cast(ShootingTargetRestrictionContext, object()))

    shooting_grant = (
        generic_rule_lifecycle_hooks._shooting_unit_selected_grant_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.shooting_unit_selected_grant_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        shooting_grant(cast(ShootingUnitSelectedContext, object()))

    movement_surge = generic_rule_lifecycle_hooks._movement_end_surge_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.movement_end_surge_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        movement_surge(cast(MovementEndSurgeContext, object()))

    reserve_arrival = generic_rule_lifecycle_hooks._reserve_arrival_distance_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.reserve_arrival_distance_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        reserve_arrival(cast(ReserveArrivalDistanceContext, object()))

    phase_end_objective = (
        generic_rule_lifecycle_hooks._phase_end_objective_control_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.phase_end_objective_control_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        phase_end_objective(cast(PhaseEndObjectiveControlContext, object()))

    enhancement = generic_rule_lifecycle_hooks._enhancement_effect_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.enhancement_effect_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        enhancement(cast(EnhancementEffectContext, object()))

    objective_modifier = (
        generic_rule_lifecycle_hooks._objective_control_modifier_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.objective_control_modifier_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        objective_modifier(cast(ObjectiveControlModifierContext, object()))

    unit_destroyed = generic_rule_lifecycle_hooks._unit_destroyed_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.unit_destroyed_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        unit_destroyed(cast(UnitDestroyedContext, object()))

    turn_end_request = generic_rule_lifecycle_hooks._turn_end_candidate_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.turn_end_abilities[0],
    )
    turn_end_result = generic_rule_lifecycle_hooks._turn_end_result_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
        source,
        registry.turn_end_abilities[0],
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        turn_end_request(cast(TurnEndRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        turn_end_result(cast(TurnEndResultContext, object()))

    fight_start_request = (
        generic_rule_lifecycle_hooks._fight_phase_start_candidate_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.fight_phase_start_abilities[0],
        )
    )
    fight_start_result = (
        generic_rule_lifecycle_hooks._fight_phase_start_result_handler_for_descriptor(  # pyright: ignore[reportPrivateUsage]
            source,
            registry.fight_phase_start_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        fight_start_request(cast(FightPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        fight_start_result(cast(FightPhaseStartResultContext, object()))

    fall_back_source = generic_rule_lifecycle_hooks._GenericFallBackEligibilitySource(  # pyright: ignore[reportPrivateUsage]
        record=source.record,
        rule_ir=source.rule_ir,
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        generic_rule_lifecycle_hooks._fall_back_grant_for_context(  # pyright: ignore[reportPrivateUsage]
            context=cast(FallBackEligibilityContext, object()),
            source=fall_back_source,
        )

    fight_activation_rule_source = _aeldari_path_of_the_outcast_source(
        path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID
    )
    fight_activation_source = generic_rule_lifecycle_hooks._GenericFightActivationAbilitySource(  # pyright: ignore[reportPrivateUsage]
        record=fight_activation_rule_source.record,
        rule_ir=fight_activation_rule_source.rule_ir,
        assignments_by_bearer_unit_id={},
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        generic_rule_lifecycle_hooks._fight_activation_option_for_context(  # pyright: ignore[reportPrivateUsage]
            context=cast(FightActivationAbilityContext, object()),
            source=fight_activation_source,
        )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattleFormationRequestContext", "BattleFormationResultContext"]
__all__ += ["CORE_FIRE_OVERWATCH_HANDLER_ID", "Callable", "Characteristic", "CharacteristicValue"]
__all__ += ["DecisionController", "DetachmentSelection", "EffectExpiration", "GameConfig"]
__all__ += ["GameLifecycleStage", "GameState", "GenericRuleAbilityHookFamily"]
__all__ += ["GenericRuleAbilityRegistry", "ModelGeometry", "ModelKeywordAssignment"]
__all__ += ["ModelProfileSelection", "RuleIR", "RulesetDescriptor", "SaveOptionModifierContext"]
__all__ += ["SetupStep", "StartingStrengthRecord", "StratagemCategory"]
__all__ += ["StratagemCostChoiceRequestContext", "StratagemCostChoiceResultContext"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemTargetBinding"]
__all__ += ["StratagemTargetKind", "StratagemTargetSpec", "StratagemTimingDescriptor"]
__all__ += ["TimingTriggerKind", "UnitMusterSelection", "_aeldari_corsair_coterie_source"]
__all__ += ["_army", "_blood_legion_source", "_court_of_the_phoenician_source"]
__all__ += ["_minimal_warptide_game_config", "_model", "_muster_request"]
__all__ += ["_owner_player_id_for_unit_id", "_shadow_legion_enhancement_source", "_unit"]
__all__ += ["_warptide_setup_state", "blood_legion_ir", "copy", "corsair_enhancements"]
__all__ += ["corsair_ir", "court_ir", "dark_pacts", "faction_generic_ir_support_2026_27"]
__all__ += ["generic_detachment_effects", "generic_rule_lifecycle_hook_handlers"]
__all__ += ["generic_rule_persisting_effect", "validate_json_value", "with_unit_keywords"]
