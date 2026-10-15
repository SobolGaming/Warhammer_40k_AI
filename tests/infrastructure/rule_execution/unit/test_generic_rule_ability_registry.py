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


def test_generic_rule_ability_registry_rejects_duplicate_descriptors() -> None:
    descriptor = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities[0]

    with pytest.raises(GameLifecycleError, match="descriptors must be unique"):
        GenericRuleAbilityRegistry(advance_eligibility_abilities=(descriptor, descriptor))


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("missing_effect", "requires effect object"),
        ("parameters_not_list", "requires parameters"),
        ("parameter_not_object", "parameter must be an object"),
        ("parameter_missing_key", "parameter requires key"),
        ("duplicate_parameter", "parameters must be unique"),
    ],
)
def test_generic_lifecycle_effect_parameter_validation_fails_closed(
    case: str,
    expected_error: str,
) -> None:
    payload: dict[str, JsonValue] = {
        "effect": {"parameters": [{"key": "model_proximity_inches", "value": 3.0}]}
    }
    effect = cast(dict[str, JsonValue], payload["effect"])
    if case == "missing_effect":
        payload["effect"] = None
    elif case == "parameters_not_list":
        effect["parameters"] = None
    elif case == "parameter_not_object":
        effect["parameters"] = ["invalid"]
    elif case == "parameter_missing_key":
        effect["parameters"] = [{"value": 3.0}]
    elif case == "duplicate_parameter":
        effect["parameters"] = [
            {"key": "model_proximity_inches", "value": 3.0},
            {"key": "model_proximity_inches", "value": 4.0},
        ]
    else:
        raise AssertionError(f"Unhandled test case: {case}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        generic_rule_lifecycle_hooks._effect_parameters(  # pyright: ignore[reportPrivateUsage]
            payload
        )


def test_generic_lifecycle_scalar_parameter_validation_is_typed_and_positive() -> None:
    assert (
        generic_rule_lifecycle_hooks._optional_bool_parameter(  # pyright: ignore[reportPrivateUsage]
            {}, "requires_charge_move"
        )
        is False
    )
    assert (
        generic_rule_lifecycle_hooks._optional_bool_parameter(  # pyright: ignore[reportPrivateUsage]
            {"requires_charge_move": True}, "requires_charge_move"
        )
        is True
    )
    with pytest.raises(GameLifecycleError, match="must be a bool"):
        generic_rule_lifecycle_hooks._optional_bool_parameter(  # pyright: ignore[reportPrivateUsage]
            {"requires_charge_move": 1}, "requires_charge_move"
        )

    assert (
        generic_rule_lifecycle_hooks._positive_float_parameter(  # pyright: ignore[reportPrivateUsage]
            {"distance": 3}, "distance"
        )
        == 3.0
    )
    assert (
        generic_rule_lifecycle_hooks._positive_float_parameter(  # pyright: ignore[reportPrivateUsage]
            {"distance": 3.5}, "distance"
        )
        == 3.5
    )
    with pytest.raises(GameLifecycleError, match="must be numeric"):
        generic_rule_lifecycle_hooks._positive_float_parameter(  # pyright: ignore[reportPrivateUsage]
            {"distance": "three"}, "distance"
        )
    with pytest.raises(GameLifecycleError, match="must be positive"):
        generic_rule_lifecycle_hooks._positive_float_parameter(  # pyright: ignore[reportPrivateUsage]
            {"distance": 0}, "distance"
        )


def test_generic_lifecycle_record_and_assignment_validation_fails_closed() -> None:
    source = _shadow_legion_source()
    missing_rule_id = replace(source.record, rule_id=None)
    missing_hash = copy.copy(source.record)
    object.__setattr__(missing_hash, "rule_ir_hash", None)
    stale_hash = copy.copy(source.record)
    object.__setattr__(stale_hash, "rule_ir_hash", "stale-rule-ir-hash")

    with pytest.raises(GameLifecycleError, match="requires rule_id"):
        generic_rule_lifecycle_hooks._record_rule_id(  # pyright: ignore[reportPrivateUsage]
            missing_rule_id
        )
    with pytest.raises(GameLifecycleError, match="requires rule_ir_hash"):
        generic_rule_lifecycle_hooks._validate_record_rule_ir_hash(  # pyright: ignore[reportPrivateUsage]
            record=missing_hash,
            rule_ir=source.rule_ir,
        )
    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        generic_rule_lifecycle_hooks._validate_record_rule_ir_hash(  # pyright: ignore[reportPrivateUsage]
            record=stale_hash,
            rule_ir=source.rule_ir,
        )
    with pytest.raises(GameLifecycleError, match="resolver must be callable"):
        generic_rule_lifecycle_hooks._rule_ir_for_record(  # pyright: ignore[reportPrivateUsage]
            source.record,
            rule_ir_resolver=cast(Callable[[str], RuleIR], object()),
        )
    with pytest.raises(GameLifecycleError, match="must grant exactly one ability"):
        generic_rule_lifecycle_hooks._single_grant_ability_payload(  # pyright: ignore[reportPrivateUsage]
            (),
            ability="fight_activation_melee_targeting_distance",
        )
    with pytest.raises(GameLifecycleError, match="assignments must be a mapping"):
        generic_rule_lifecycle_hooks._validate_assignment_mapping(  # pyright: ignore[reportPrivateUsage]
            object()
        )
    with pytest.raises(GameLifecycleError, match="requires runtime assignments"):
        generic_rule_lifecycle_hooks._validate_assignment_mapping(  # pyright: ignore[reportPrivateUsage]
            {"army-a:bearer": object()}
        )


def test_generic_lifecycle_binding_inputs_fail_closed() -> None:
    activation = _warptide_activation()

    with pytest.raises(GameLifecycleError, match="Fall Back bindings require activation"):
        generic_rule_lifecycle_hooks.fall_back_eligibility_hook_bindings(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=(),
        )
    with pytest.raises(GameLifecycleError, match="Fall Back bindings require execution records"):
        generic_rule_lifecycle_hooks.fall_back_eligibility_hook_bindings(
            activation=activation,
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                [],
            ),
        )
    with pytest.raises(GameLifecycleError, match="Fall Back bindings require execution records"):
        generic_rule_lifecycle_hooks.fall_back_eligibility_hook_bindings(
            activation=activation,
            execution_records=(cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),),
        )
    with pytest.raises(GameLifecycleError, match="fight activation bindings require activation"):
        generic_rule_lifecycle_hooks.fight_activation_ability_hook_bindings(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=(),
        )
    with pytest.raises(
        GameLifecycleError, match="fight activation bindings require execution records"
    ):
        generic_rule_lifecycle_hooks.fight_activation_ability_hook_bindings(
            activation=activation,
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                [],
            ),
        )
    with pytest.raises(GameLifecycleError, match="RuleIR resolver must be callable"):
        generic_rule_lifecycle_hooks.fight_activation_ability_hook_bindings(
            activation=activation,
            execution_records=(),
            rule_ir_resolver=cast(Callable[[str], RuleIR], object()),
        )
    with pytest.raises(
        GameLifecycleError, match="fight activation bindings require execution records"
    ):
        generic_rule_lifecycle_hooks.fight_activation_ability_hook_bindings(
            activation=activation,
            execution_records=(cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),),
        )


def test_generic_lifecycle_shared_handlers_reject_wrong_context_types() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY
    source = _shadow_legion_source()

    fight_grant = (
        generic_rule_lifecycle_hook_handlers.fight_unit_selected_grant_handler_for_descriptor(
            source,
            registry.fight_unit_selected_grant_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        fight_grant(cast(FightUnitSelectedContext, object()))

    battle_request = (
        generic_rule_lifecycle_hook_handlers.battle_formation_request_handler_for_descriptor(
            source,
            registry.battle_formation_abilities[0],
        )
    )
    battle_result = (
        generic_rule_lifecycle_hook_handlers.battle_formation_result_handler_for_descriptor(
            source,
            registry.battle_formation_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        battle_request(cast(BattleFormationRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        battle_result(cast(BattleFormationResultContext, object()))

    cost_choice_request = (
        generic_rule_lifecycle_hook_handlers.stratagem_cost_choice_request_handler_for_descriptor(
            source,
            registry.stratagem_cost_choice_abilities[0],
        )
    )
    cost_choice_result = (
        generic_rule_lifecycle_hook_handlers.stratagem_cost_choice_result_handler_for_descriptor(
            source,
            registry.stratagem_cost_choice_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        cost_choice_request(cast(StratagemCostChoiceRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        cost_choice_result(cast(StratagemCostChoiceResultContext, object()))

    cost_modifier = (
        generic_rule_lifecycle_hook_handlers.stratagem_cost_modifier_handler_for_descriptor(
            source,
            registry.stratagem_cost_modifier_abilities[0],
        )
    )
    save_modifier = (
        generic_rule_lifecycle_hook_handlers.save_option_modifier_handler_for_descriptor(
            source,
            registry.save_option_modifier_abilities[0],
        )
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        cost_modifier(cast(StratagemCostModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        save_modifier(cast(SaveOptionModifierContext, object()))


def test_generic_lifecycle_internal_sources_require_exact_types_and_rule_id() -> None:
    source = _shadow_legion_source()

    with pytest.raises(GameLifecycleError, match="requires execution record"):
        generic_rule_lifecycle_hooks._GenericFallBackEligibilitySource(  # pyright: ignore[reportPrivateUsage]
            record=cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),
            rule_ir=source.rule_ir,
        )
    with pytest.raises(GameLifecycleError, match="requires RuleIR"):
        generic_rule_lifecycle_hooks._GenericFallBackEligibilitySource(  # pyright: ignore[reportPrivateUsage]
            record=source.record,
            rule_ir=cast(RuleIR, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires execution record"):
        generic_rule_lifecycle_hooks._GenericFightActivationAbilitySource(  # pyright: ignore[reportPrivateUsage]
            record=cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),
            rule_ir=source.rule_ir,
            assignments_by_bearer_unit_id={},
        )
    with pytest.raises(GameLifecycleError, match="requires RuleIR"):
        generic_rule_lifecycle_hooks._GenericFightActivationAbilitySource(  # pyright: ignore[reportPrivateUsage]
            record=source.record,
            rule_ir=cast(RuleIR, object()),
            assignments_by_bearer_unit_id={},
        )
    with pytest.raises(GameLifecycleError, match="requires rule_id"):
        generic_rule_lifecycle_hooks._GenericFightActivationAbilitySource(  # pyright: ignore[reportPrivateUsage]
            record=replace(source.record, rule_id=None),
            rule_ir=source.rule_ir,
            assignments_by_bearer_unit_id={},
        )


__all__: list[str] = []
__all__ += ["AdvanceEligibilityContext", "AdvanceMoveContext", "AdvanceMoveGrant", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition", "BattlePhase"]
__all__ += ["CORE_FIRE_OVERWATCH_HANDLER_ID", "Characteristic", "CharacteristicValue"]
__all__ += ["DecisionController", "DetachmentSelection", "EffectExpiration"]
__all__ += ["EnhancementAssignment", "EnhancementEffectContext", "FallBackEligibilityContext"]
__all__ += ["FightActivationAbilityContext", "FightPhaseStartRequestContext"]
__all__ += ["FightPhaseStartResultContext", "GameConfig", "GameLifecycleStage", "GameState"]
__all__ += ["GenericRuleAbilityHookFamily", "GenericRuleAbilitySource", "ModelGeometry"]
__all__ += ["ModelInstance", "ModelKeywordAssignment", "ModelProfileSelection"]
__all__ += ["ModifierOperation", "ModifierTerm", "MovementEndSurgeContext"]
__all__ += ["ObjectiveControlModifierContext", "PersistingEffect"]
__all__ += ["PhaseEndObjectiveControlContext", "ReserveArrivalDistanceContext", "RuleEffectKind"]
__all__ += ["RuleExecutionResult", "RuleExecutionStatus", "RuleTargetKind", "RulesetDescriptor"]
__all__ += ["SetupStep", "ShootingTargetRestrictionContext", "ShootingUnitSelectedContext"]
__all__ += ["StartingStrengthRecord", "StratagemCategory", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemTargetBinding", "StratagemTargetKind"]
__all__ += ["StratagemTargetSpec", "StratagemTimingDescriptor", "TimingTriggerKind"]
__all__ += ["TurnEndRequestContext", "TurnEndResultContext", "UnitDestroyedContext"]
__all__ += ["_ENEMY_UNIT_ID", "UnitInstance", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["_RANGERS_UNIT_ID", "_SHROUD_RUNNERS_UNIT_ID", "_WARPTIDE_UNIT_ID"]
__all__ += ["_aeldari_corsair_coterie_source", "_aeldari_path_of_the_outcast_source", "_army"]
__all__ += ["_blood_legion_source", "_court_of_the_phoenician_source", "_grant_ability_effect"]
__all__ += ["_keyword_any_state", "_minimal_warptide_game_config", "_model", "_muster_request"]
__all__ += ["_owner_player_id_for_unit_id", "_raise_selected_to_fight_payload_error"]
__all__ += ["_selected_to_fight_effect_payload", "_selected_to_fight_grant_payload"]
__all__ += ["_selected_to_fight_reroll_payload", "_shadow_legion_enhancement_source", "_unit"]
__all__ += ["_warptide_cost_modifier_context", "_warptide_grant_ability_effect"]
__all__ += ["_warptide_setup_state", "_warptide_source", "_warptide_state"]
__all__ += ["advance_move_lifecycle_hooks", "blood_legion_ir", "corsair_enhancements"]
__all__ += ["corsair_ir", "court_ir", "court_rule", "dark_pacts"]
__all__ += ["faction_generic_ir_support_2026_27", "generic_detachment_effects"]
__all__ += ["generic_rule_ability_effects_for_unit", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_selected_to_fight_effects", "path_outcast_ir"]
__all__ += ["rule_ir_grants_any_ability", "shadow_legion_ir", "validate_json_value"]
__all__ += ["warptide_ir", "with_unit_keywords"]
