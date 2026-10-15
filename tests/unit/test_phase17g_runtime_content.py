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


def test_runtime_manifest_generation_merges_catalog_rows_and_generated_support() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    generated_detachment_row = RuntimeContentManifestRow(
        content_id="core-combined-arms",
        family=RuntimeContentModuleFamily.DETACHMENT,
        source_ids=(),
        owner_faction_id=None,
        owner_detachment_id=None,
        source_package_id="source-package-id:generated",
        source_package_hash="source-package-hash:generated",
        execution_record_ids=("execution:detachment",),
        module_path="tests.runtime_content_generated_detachment",
        support_status=RuntimeContentSupportStatus.SUPPORTED,
        dependency_ids=("generated-weapon-ability",),
    )
    generated_dependency_row = _manifest_row(
        content_id="generated-weapon-ability",
        family=RuntimeContentModuleFamily.WEAPON_PROFILE,
        module_path="tests.runtime_content_generated_weapon",
        execution_record_ids=("execution:weapon",),
    )

    manifest = RuntimeContentManifest.from_catalog(
        catalog=catalog,
        generated_rows=(generated_detachment_row, generated_dependency_row),
    )
    activation = _manual_activation(selected_detachment_ids=("core-combined-arms",))
    resolved = manifest.resolve_activation(activation)
    detachment_row = manifest.row_for_content_id("core-combined-arms")
    enhancement_row = manifest.row_for_content_id("runtime-enhancement")
    stratagem_row = manifest.row_for_content_id("runtime-ambush")
    wargear_row = manifest.row_for_content_id("core-bolt-rifle")
    summary_row = generated_dependency_row.to_summary_payload()

    assert detachment_row.source_ids != ()
    assert detachment_row.source_package_id == "source-package-id:generated"
    assert detachment_row.source_package_hash == "source-package-hash:generated"
    assert detachment_row.dependency_ids == (
        "generated-weapon-ability",
        "runtime-ambush",
        "runtime-enhancement",
    )
    assert enhancement_row.owner_detachment_id == "core-combined-arms"
    assert stratagem_row.owner_detachment_id == "core-combined-arms"
    assert wargear_row.dependency_ids == ("core-bolt-rifle:standard",)
    assert resolved.selected_module_paths == (
        "tests.runtime_content_generated_detachment",
        "tests.runtime_content_generated_weapon",
    )
    assert resolved.selected_execution_record_ids == (
        "execution:detachment",
        "execution:weapon",
    )
    assert summary_row["support_status"] == RuntimeContentSupportStatus.SUPPORTED.value
    assert summary_row["semantic_status"] == RuntimeContentSemanticStatus.PLACEHOLDER.value

    with pytest.raises(GameLifecycleError, match="requires ArmyCatalog"):
        RuntimeContentManifest.from_catalog(
            catalog=cast(ArmyCatalog, object()),
            generated_rows=(),
        )


def test_stratagem_handler_registry_is_explicit_and_fail_closed() -> None:
    context = _stratagem_handler_context(handler_id="faction:runtime-handler")

    missing = StratagemHandlerRegistry.empty().execute(
        handler_id="faction:runtime-handler",
        context=context,
    )

    assert missing.status is StratagemHandlerExecutionStatus.UNSUPPORTED
    assert missing.reason == "missing_handler"

    def handler(handler_context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
        return StratagemHandlerExecutionResult.applied(
            handler_id=handler_context.definition.handler_id,
            replay_payload={"use_id": handler_context.use_record.use_id},
        )

    registry = StratagemHandlerRegistry.empty().with_handler(
        handler_id="faction:runtime-handler",
        handler=handler,
    )
    applied = registry.execute(handler_id="faction:runtime-handler", context=context)

    assert applied.status is StratagemHandlerExecutionStatus.APPLIED
    assert applied.replay_payload == {"use_id": "stratagem-use:runtime"}
    assert StratagemHandlerExecutionResult.from_payload(applied.to_payload()) == applied

    validator_calls: list[str] = []

    def validator(
        handler_context: StratagemHandlerContext,
    ) -> StratagemHandlerExecutionResult:
        validator_calls.append(handler_context.definition.handler_id)
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_context.definition.handler_id,
            reason="target_state_invalid",
        )

    validating_registry = StratagemHandlerRegistry.empty().with_handler(
        handler_id="faction:validated-handler",
        handler=handler,
        validator=validator,
    )
    validation_result = validating_registry.validate(
        handler_id="faction:validated-handler",
        context=_stratagem_handler_context(handler_id="faction:validated-handler"),
    )

    assert validation_result.status is StratagemHandlerExecutionStatus.INVALID
    assert validation_result.reason == "target_state_invalid"
    assert validator_calls == ["faction:validated-handler"]

    with pytest.raises(GameLifecycleError, match="validator must be callable"):
        StratagemHandlerBinding(
            handler_id="faction:bad-validator",
            handler=handler,
            validator=cast(StratagemHandler, object()),
        )
    with pytest.raises(GameLifecycleError, match="handler IDs must be unique"):
        StratagemHandlerRegistry.from_bindings(
            (
                StratagemHandlerBinding(handler_id="faction:duplicate", handler=handler),
                StratagemHandlerBinding(handler_id="faction:duplicate", handler=handler),
            )
        )
    with pytest.raises(GameLifecycleError, match="cannot register unsupported"):
        StratagemHandlerBinding(handler_id="unsupported:faction", handler=handler)


def test_runtime_content_bundle_scopes_faction_execution_registry_to_selected_ids() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    selected_record, unselected_record = faction_execution_2026_27.execution_records()[:2]
    activation = RuntimeContentActivation.from_armies(
        armies=(army,),
        catalog=catalog,
    ).with_reachable_content(
        reachable_content_ids=("core-combined-arms",),
        selected_module_paths=(),
        source_package_ids=("source-package-id:test",),
        source_package_hashes=("source-package-hash:test",),
        selected_execution_record_ids=(selected_record.execution_id,),
        unsupported_content_ids=(),
        unsupported_reasons_by_content_id={},
    )

    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(),
        faction_execution_records=(selected_record, unselected_record),
    )
    diagnostic_bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(),
        faction_execution_records=(selected_record, unselected_record),
        include_unselected_faction_execution_records=True,
    )

    assert [
        record.execution_id for record in bundle.faction_rule_execution_registry.all_records()
    ] == [selected_record.execution_id]
    assert {
        record.execution_id
        for record in diagnostic_bundle.faction_rule_execution_registry.all_records()
    } == {selected_record.execution_id, unselected_record.execution_id}

    missing_activation = activation.with_reachable_content(
        reachable_content_ids=activation.reachable_content_ids,
        selected_module_paths=(),
        source_package_ids=activation.source_package_ids,
        source_package_hashes=activation.source_package_hashes,
        selected_execution_record_ids=("execution:missing",),
        unsupported_content_ids=(),
        unsupported_reasons_by_content_id={},
    )
    with pytest.raises(GameLifecycleError, match="selected unknown faction execution records"):
        RuntimeContentBundle.from_contributions(
            activation=missing_activation,
            armies=(army,),
            catalog=catalog,
            contributions=(),
            faction_execution_records=(selected_record,),
        )


def test_runtime_loader_validates_module_contract_and_skips_unmapped_wargear_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activation = RuntimeContentActivation(
        selected_faction_ids=("faction-alpha",),
        selected_detachment_ids=(),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=("source-only-wargear",),
        selected_weapon_profile_ids=("source-only-profile",),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )
    manifest = RuntimeContentManifest(
        rows=(
            _manifest_row(
                content_id="faction-alpha",
                family=RuntimeContentModuleFamily.FACTION,
                module_path="tests.runtime_content_contract_module",
            ),
            _manifest_row(
                content_id="source-only-wargear",
                family=RuntimeContentModuleFamily.WARGEAR,
                support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
                dependency_ids=("source-only-profile",),
            ),
            _manifest_row(
                content_id="source-only-profile",
                family=RuntimeContentModuleFamily.WEAPON_PROFILE,
                support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            ),
        )
    )
    module = ModuleType("tests.runtime_content_contract_module")
    monkeypatch.setitem(sys.modules, "tests.runtime_content_contract_module", module)
    resolved_activation = manifest.resolve_activation(activation)

    assert resolved_activation.selected_module_paths == ("tests.runtime_content_contract_module",)
    with pytest.raises(GameLifecycleError, match="requires resolved activation"):
        load_runtime_content_contributions(activation=activation, manifest=manifest)
    with pytest.raises(GameLifecycleError, match="must expose runtime_contribution"):
        load_runtime_content_contributions(activation=resolved_activation, manifest=manifest)

    module.__dict__["runtime_contribution"] = "not-callable"
    with pytest.raises(GameLifecycleError, match="must be callable"):
        load_runtime_content_contributions(activation=resolved_activation, manifest=manifest)

    module.__dict__["runtime_contribution"] = lambda: object()
    with pytest.raises(GameLifecycleError, match="returned invalid"):
        load_runtime_content_contributions(activation=resolved_activation, manifest=manifest)

    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        RuntimeContentModuleIndex(
            faction_modules=cast(Mapping[str, str], ()),
            detachment_modules={},
            enhancement_modules={},
            stratagem_modules={},
            datasheet_modules={},
            wargear_modules={},
            weapon_profile_modules={},
        )
    with pytest.raises(GameLifecycleError, match="absolute and normalized"):
        RuntimeContentModuleRef(
            family=RuntimeContentModuleFamily.FACTION,
            content_id="faction-alpha",
            module_path=".relative",
        )
    with pytest.raises(GameLifecycleError, match="Unsupported RuntimeContentModuleFamily"):
        RuntimeContentModuleRef(
            family=cast(RuntimeContentModuleFamily, "unknown"),
            content_id="faction-alpha",
            module_path="tests.runtime_content_contract_module",
        )


def test_pilot_faction_content_modules_have_expected_export_shapes() -> None:
    helper_module_paths = (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.common.attack_hooks",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.common.aura_handlers",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.common.modifiers",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.common.resource_handlers",
    )
    contribution_module_paths = (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.army_rule",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.manifest",
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.flyblown_host.enhancements"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.flyblown_host.manifest"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.flyblown_host.rule"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.flyblown_host.stratagems"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.tallyband_summoners.enhancements"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.tallyband_summoners.manifest"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.tallyband_summoners.rule"
        ),
        (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
            "death_guard.detachments.tallyband_summoners.stratagems"
        ),
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.plague_marines",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.typhus",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.wargear.plague_weapons",
    )

    for module_path in helper_module_paths:
        module = import_module(module_path)

        assert type(module.__doc__) is str
        assert "runtime_contribution" not in module.__dict__

    for module_path in contribution_module_paths:
        module = import_module(module_path)
        contribution = module.runtime_contribution()

        assert type(contribution) is RuntimeContentContribution


def test_real_edition_index_loads_only_selected_pilot_faction_modules() -> None:
    config = _canonical_lifecycle_config()
    activation = RuntimeContentActivation(
        selected_faction_ids=("death-guard",),
        selected_detachment_ids=("tallyband-summoners",),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=("plague-marines", "typhus"),
        selected_wargear_ids=("plague-weapons",),
        selected_weapon_profile_ids=("plague-weapons:standard",),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=("death-guard:unit-1",),
    )
    manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        config=config,
    )
    resolved_activation = manifest.resolve_activation(activation)

    contributions = load_runtime_content_contributions(
        activation=resolved_activation,
        manifest=manifest,
    )

    assert resolved_activation.selected_module_paths == (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "death_guard.detachments.tallyband_summoners.manifest",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.manifest",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.plague_marines",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.typhus",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.wargear.plague_weapons",
    )
    assert {contribution.contribution_id for contribution in contributions} == {
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "death_guard.units.plague_marines",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.typhus",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "death_guard.wargear.plague_weapons",
        "warhammer_40000_11th:death_guard:detachment:tallyband_summoners:manifest:scaffold",
        "warhammer_40000_11th:death_guard:faction_manifest:scaffold",
    }
    assert "phase17f:phase17e:death-guard:army-rule" in (
        resolved_activation.selected_execution_record_ids
    )
    assert (
        runtime_content_module_index_for_ruleset(RulesetDescriptor.warhammer_40000_eleventh())
        .wargear_modules["plague-weapons"]
        .endswith(".death_guard.wargear.plague_weapons")
    )


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilityExecutionContext"]
__all__ += ["AbilityHandlerBinding", "AbilityResolutionResult", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "AllocatedAttackDamageModifierBinding"]
__all__ += ["ArmyMusterRequest", "AttackRerollPermissionBinding", "AttackRerollPermissionContext"]
__all__ += ["CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID", "BattlePhase", "Callable"]
__all__ += ["CatalogDetachmentDefinition", "CatalogEnhancementDefinition"]
__all__ += ["CatalogStratagemDefinition", "DamageRollModifierBinding", "DecisionController"]
__all__ += ["DecisionResult", "DetachmentSelection", "EnhancementAssignment"]
__all__ += ["EnhancementCharacteristicModifier", "EnhancementEffectBinding"]
__all__ += ["EnhancementEffectContext", "FactionRuleNamedHandler"]
__all__ += ["FailedSaveDamageReplacementBinding", "FallBackEligibilityContext"]
__all__ += ["FallBackEligibilityGrant", "FallBackEligibilityHookBinding"]
__all__ += ["FightActivationAbilityContext", "FightActivationAbilityHookBinding"]
__all__ += ["FightActivationAbilityOption", "FightUnitSelectedContext"]
__all__ += ["FightUnitSelectedEffectGrant", "FightUnitSelectedHookBinding"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameConfig", "GameLifecycle", "GameState"]
__all__ += ["HitRollModifierBinding", "HitRollModifierContext", "HookBinding", "JsonValue"]
__all__ += ["LifecycleHookEvent", "MissionSetup", "ModelProfileSelection", "RuleClause"]
__all__ += ["RuleCondition", "RuleConditionKind", "RuleEffectKind", "RuleEffectSpec", "RuleIR"]
__all__ += ["RuleTargetKind", "RuleTargetSpec", "RuleTrigger", "RuleTriggerKind"]
__all__ += ["RuntimeContentEvent", "RuntimeContentEventContext"]
__all__ += ["RuntimeContentEventHandlerBinding", "RuntimeContentEventHandlerRegistry"]
__all__ += ["RuntimeContentEventIndex", "RuntimeContentEventResult"]
__all__ += ["RuntimeContentEventSubscription", "RuntimeEventHandler", "RuntimeEventStatus"]
__all__ += ["STRATAGEM_DECISION_TYPE", "RuntimeHookBinding", "RuntimeModifierRegistry"]
__all__ += ["StartBattleHookBinding", "StartBattleHookRegistry", "StratagemAvailabilityKind"]
__all__ += ["StratagemCatalogRecord", "StratagemCategory", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemTargetBinding", "StratagemTimingDescriptor"]
__all__ += ["StratagemUseRecord", "TextSpan", "TimingTriggerKind", "UnitMusterSelection"]
__all__ += ["Wargear", "WeaponKeyword", "WoundRollModifierBinding", "WoundRollModifierContext"]
__all__ += ["_ability_record", "_attribute_path"]
__all__ += ["_catalog_with_duplicate_runtime_enhancement_owner"]
__all__ += ["_catalog_with_hazardous_bolt_rifle", "_config", "_mission_setup"]
__all__ += ["_runtime_content_bundle", "_stratagem_record", "_tracked_target_ability_record"]
__all__ += ["_tracked_target_rule_ir", "ast", "build_runtime_content_bundle"]
__all__ += ["chapter_approved_2026_27_mission_pack", "combine_runtime_content_contributions"]
__all__ += ["dedent", "fields", "getsource", "json", "lifecycle_module", "parameters_from_pairs"]
__all__ += ["replace", "runtime_content_activation_for_armies"]
__all__ += ["runtime_content_bundle_summary_payload"]
