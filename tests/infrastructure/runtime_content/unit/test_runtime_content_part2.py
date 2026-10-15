from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17g_runtime_content import (
    CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    STRATAGEM_DECISION_TYPE,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityHandlerBinding,
    AbilityResolutionResult,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    AllocatedAttackDamageModifierBinding,
    ArmyCatalog,
    ArmyMusterRequest,
    AttackRerollPermissionBinding,
    AttackRerollPermissionContext,
    BattlePhase,
    Callable,
    CatalogDetachmentDefinition,
    CatalogEnhancementDefinition,
    CatalogStratagemDefinition,
    DamageRollModifierBinding,
    DecisionController,
    DecisionResult,
    DetachmentSelection,
    EnhancementAssignment,
    EnhancementCharacteristicModifier,
    EnhancementEffectBinding,
    EnhancementEffectContext,
    FactionRuleNamedHandler,
    FailedSaveDamageReplacementBinding,
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
    FightUnitSelectedContext,
    FightUnitSelectedEffectGrant,
    FightUnitSelectedHookBinding,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    HitRollModifierBinding,
    HitRollModifierContext,
    HookBinding,
    JsonValue,
    LifecycleHookEvent,
    Mapping,
    MissionSetup,
    ModelProfileSelection,
    ModuleType,
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RulesetDescriptor,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    RuntimeContentActivation,
    RuntimeContentBundle,
    RuntimeContentContribution,
    RuntimeContentEvent,
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeContentManifest,
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentModuleIndex,
    RuntimeContentModuleRef,
    RuntimeContentSemanticStatus,
    RuntimeContentSupportStatus,
    RuntimeEventHandler,
    RuntimeEventStatus,
    RuntimeHookBinding,
    RuntimeModifierRegistry,
    StartBattleHookBinding,
    StartBattleHookRegistry,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemHandler,
    StratagemHandlerBinding,
    StratagemHandlerContext,
    StratagemHandlerExecutionResult,
    StratagemHandlerExecutionStatus,
    StratagemHandlerRegistry,
    StratagemTargetBinding,
    StratagemTimingDescriptor,
    StratagemUseRecord,
    TextSpan,
    TimingTriggerKind,
    UnitMusterSelection,
    Wargear,
    WeaponKeyword,
    WoundRollModifierBinding,
    WoundRollModifierContext,
    _ability_record,
    _attribute_path,
    _canonical_lifecycle_config,
    _catalog_with_duplicate_runtime_enhancement_owner,
    _catalog_with_hazardous_bolt_rifle,
    _catalog_with_runtime_detachment_selection,
    _config,
    _manifest_row,
    _manual_activation,
    _mission_setup,
    _muster_request,
    _runtime_content_bundle,
    _stratagem_handler_context,
    _stratagem_record,
    _tracked_target_ability_record,
    _tracked_target_rule_ir,
    ast,
    build_runtime_content_bundle,
    chapter_approved_2026_27_mission_pack,
    combine_runtime_content_contributions,
    dedent,
    faction_execution_2026_27,
    fields,
    getsource,
    import_module,
    json,
    lifecycle_module,
    load_runtime_content_contributions,
    muster_army,
    parameters_from_pairs,
    pytest,
    replace,
    runtime_content_activation_for_armies,
    runtime_content_bundle_summary_payload,
    runtime_content_manifest_for_ruleset,
    runtime_content_module_index_for_ruleset,
    sys,
)


def test_runtime_event_filters_and_module_index_validation_are_fail_closed() -> None:
    config = _config()
    state = GameState.from_config(config)
    decisions = DecisionController()

    def unexpected_handler(_context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        raise AssertionError("filtered subscription should not dispatch")

    filtered_index = RuntimeContentEventIndex.from_subscriptions(
        (
            RuntimeContentEventSubscription(
                subscription_id="subscription-active-player",
                source_rule_id="source:active-player",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:unexpected",
                filters={"active_player_id": "player-b"},
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-player",
                source_rule_id="source:player",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:unexpected",
                filters={"player_id": "player-b"},
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-source-unit",
                source_rule_id="source:source-unit",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:unexpected",
                filters={"source_unit_instance_id": "unit-b"},
            ),
        ),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            (
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:unexpected",
                    handler=unexpected_handler,
                ),
            )
        ),
    )
    event = RuntimeContentEvent(
        event_id="event-filtered",
        game_id="game-filtered",
        player_id="player-a",
        battle_round=1,
        trigger_kind=TimingTriggerKind.START_PHASE,
        phase=None,
        active_player_id="player-a",
        source_unit_instance_id="unit-a",
    )

    assert (
        filtered_index.dispatch(
            event,
            state=state,
            decisions=decisions,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == ()
    )
    assert filtered_index.to_summary_payload()[0]["subscription_id"] == (
        "subscription-active-player"
    )
    assert (
        RuntimeContentEventHandlerBinding(
            handler_id="handler:summary",
            handler=lambda context: RuntimeContentEventResult.applied(
                RuntimeContentEventSubscription(
                    subscription_id="subscription:summary",
                    source_rule_id=context.event.event_id,
                    trigger_kind=context.event.trigger_kind,
                    handler_id="handler:summary",
                )
            ),
        ).to_summary_payload()["handler_id"]
        == "handler:summary"
    )

    with pytest.raises(GameLifecycleError, match="filters must be a mapping"):
        RuntimeContentEventSubscription(
            subscription_id="subscription-bad-filter",
            source_rule_id="source:bad-filter",
            trigger_kind=TimingTriggerKind.START_PHASE,
            handler_id="handler:unexpected",
            filters=cast(Mapping[str, JsonValue], ()),
        )
    with pytest.raises(
        GameLifecycleError,
        match="target_unit_instance_ids must not contain duplicates",
    ):
        RuntimeContentEvent(
            event_id="event-duplicate-targets",
            game_id="game-filtered",
            player_id="player-a",
            battle_round=1,
            trigger_kind=TimingTriggerKind.START_PHASE,
            target_unit_instance_ids=("unit-a", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="battle_round must be positive"):
        RuntimeContentEvent(
            event_id="event-invalid-round",
            game_id="game-filtered",
            player_id="player-a",
            battle_round=0,
            trigger_kind=TimingTriggerKind.START_PHASE,
        )
    with pytest.raises(GameLifecycleError, match="RuntimeEventStatus token"):
        RuntimeContentEventResult(
            subscription_id="subscription-bad-status",
            source_rule_id="source:bad-status",
            status=cast(RuntimeEventStatus, 17),
            reason="bad_status",
        )
    with pytest.raises(GameLifecycleError, match="Unsupported RuntimeEventStatus"):
        RuntimeContentEventResult(
            subscription_id="subscription-bad-status-token",
            source_rule_id="source:bad-status-token",
            status=cast(RuntimeEventStatus, "bad-status"),
            reason="bad_status",
        )
    with pytest.raises(GameLifecycleError, match="handler bindings must be a tuple"):
        RuntimeContentEventHandlerRegistry.from_bindings(
            cast(tuple[RuntimeContentEventHandlerBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="must contain RuntimeContentEventHandlerBinding"):
        RuntimeContentEventHandlerRegistry.from_bindings(
            cast(tuple[RuntimeContentEventHandlerBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="handler IDs must be unique"):
        RuntimeContentEventHandlerRegistry.from_bindings(
            (
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:duplicate",
                    handler=unexpected_handler,
                ),
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:duplicate",
                    handler=unexpected_handler,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="requires handler registry"):
        RuntimeContentEventIndex.from_subscriptions(
            (),
            handler_registry=cast(RuntimeContentEventHandlerRegistry, object()),
        )
    with pytest.raises(GameLifecycleError, match="subscriptions must be a tuple"):
        RuntimeContentEventIndex.from_subscriptions(
            cast(tuple[RuntimeContentEventSubscription, ...], []),
            handler_registry=RuntimeContentEventHandlerRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires a RuntimeContentEvent"):
        filtered_index.dispatch(
            cast(RuntimeContentEvent, object()),
            state=state,
            decisions=decisions,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )

    module_index = RuntimeContentModuleIndex(
        faction_modules={"faction-alpha": "tests.runtime_content_alpha"},
        detachment_modules={"detachment-alpha": "tests.runtime_content_detachment"},
        enhancement_modules={},
        stratagem_modules={},
        datasheet_modules={},
        wargear_modules={},
        weapon_profile_modules={},
    )
    activation = RuntimeContentActivation(
        selected_faction_ids=("faction-alpha",),
        selected_detachment_ids=("detachment-alpha",),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=("source-only-wargear",),
        selected_weapon_profile_ids=("source-only-profile",),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )

    assert module_index.module_paths_for_activation(activation) == (
        "tests.runtime_content_alpha",
        "tests.runtime_content_detachment",
    )
    assert (
        RuntimeContentModuleIndex.empty().refs_for_activation(
            RuntimeContentActivation(
                selected_faction_ids=(),
                selected_detachment_ids=(),
                selected_enhancement_ids=(),
                selected_stratagem_ids=(),
                selected_datasheet_ids=(),
                selected_wargear_ids=("source-only-wargear",),
                selected_weapon_profile_ids=("source-only-profile",),
                selected_weapon_keywords=(),
                loaded_unit_instance_ids=(),
            )
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="lookup requires activation"):
        module_index.refs_for_activation(cast(RuntimeContentActivation, object()))
    with pytest.raises(GameLifecycleError, match="missing selected support"):
        RuntimeContentModuleIndex.empty().refs_for_activation(
            RuntimeContentActivation(
                selected_faction_ids=("missing-faction",),
                selected_detachment_ids=(),
                selected_enhancement_ids=(),
                selected_stratagem_ids=(),
                selected_datasheet_ids=(),
                selected_wargear_ids=(),
                selected_weapon_profile_ids=(),
                selected_weapon_keywords=(),
                loaded_unit_instance_ids=(),
            )
        )


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilityExecutionContext"]
__all__ += ["AbilityHandlerBinding", "AbilityResolutionResult", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "AllocatedAttackDamageModifierBinding", "ArmyCatalog"]
__all__ += ["ArmyMusterRequest", "AttackRerollPermissionBinding", "AttackRerollPermissionContext"]
__all__ += ["CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID", "BattlePhase", "Callable"]
__all__ += ["CatalogDetachmentDefinition", "CatalogEnhancementDefinition"]
__all__ += ["CatalogStratagemDefinition", "DamageRollModifierBinding", "DecisionResult"]
__all__ += ["DetachmentSelection", "EnhancementAssignment", "EnhancementCharacteristicModifier"]
__all__ += ["EnhancementEffectBinding", "EnhancementEffectContext", "FactionRuleNamedHandler"]
__all__ += ["FailedSaveDamageReplacementBinding", "FallBackEligibilityContext"]
__all__ += ["FallBackEligibilityGrant", "FallBackEligibilityHookBinding"]
__all__ += ["FightActivationAbilityContext", "FightActivationAbilityHookBinding"]
__all__ += ["FightActivationAbilityOption", "FightUnitSelectedContext"]
__all__ += ["FightUnitSelectedEffectGrant", "FightUnitSelectedHookBinding"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameConfig", "GameLifecycle"]
__all__ += ["HitRollModifierBinding", "HitRollModifierContext", "HookBinding"]
__all__ += ["LifecycleHookEvent", "MissionSetup", "ModelProfileSelection", "ModuleType"]
__all__ += ["RuleClause", "RuleCondition", "RuleConditionKind", "RuleEffectKind"]
__all__ += ["RuleEffectSpec", "RuleIR", "RuleTargetKind", "RuleTargetSpec", "RuleTrigger"]
__all__ += ["RuleTriggerKind", "RulesetDescriptor", "RuntimeContentBundle"]
__all__ += ["RuntimeContentContribution", "RuntimeContentManifest", "RuntimeContentManifestRow"]
__all__ += ["RuntimeContentModuleFamily", "RuntimeContentModuleRef"]
__all__ += ["RuntimeContentSemanticStatus", "RuntimeContentSupportStatus", "RuntimeEventHandler"]
__all__ += ["STRATAGEM_DECISION_TYPE", "RuntimeHookBinding", "StartBattleHookBinding"]
__all__ += ["StartBattleHookRegistry", "StratagemAvailabilityKind", "StratagemCatalogRecord"]
__all__ += ["StratagemCategory", "StratagemDefinition", "StratagemEligibilityContext"]
__all__ += ["StratagemHandler", "StratagemHandlerBinding", "StratagemHandlerContext"]
__all__ += ["StratagemHandlerExecutionResult", "StratagemHandlerExecutionStatus"]
__all__ += ["StratagemHandlerRegistry", "StratagemTargetBinding", "StratagemTimingDescriptor"]
__all__ += ["StratagemUseRecord", "TextSpan", "UnitMusterSelection", "Wargear", "WeaponKeyword"]
__all__ += ["WoundRollModifierBinding", "WoundRollModifierContext", "_ability_record"]
__all__ += ["_attribute_path", "_canonical_lifecycle_config"]
__all__ += ["_catalog_with_duplicate_runtime_enhancement_owner"]
__all__ += ["_catalog_with_hazardous_bolt_rifle", "_catalog_with_runtime_detachment_selection"]
__all__ += ["_manifest_row", "_manual_activation", "_mission_setup", "_muster_request"]
__all__ += ["_runtime_content_bundle", "_stratagem_handler_context", "_stratagem_record"]
__all__ += ["_tracked_target_ability_record", "_tracked_target_rule_ir", "ast"]
__all__ += ["build_runtime_content_bundle", "chapter_approved_2026_27_mission_pack"]
__all__ += ["combine_runtime_content_contributions", "dedent", "faction_execution_2026_27"]
__all__ += ["fields", "getsource", "import_module", "json", "lifecycle_module"]
__all__ += ["load_runtime_content_contributions", "muster_army", "parameters_from_pairs"]
__all__ += ["replace", "runtime_content_activation_for_armies"]
__all__ += ["runtime_content_bundle_summary_payload", "runtime_content_manifest_for_ruleset"]
__all__ += ["runtime_content_module_index_for_ruleset", "sys"]
