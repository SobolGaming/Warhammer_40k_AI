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


def test_runtime_content_activation_derives_selected_sources_from_real_armies() -> None:
    catalog = _catalog_with_hazardous_bolt_rifle(
        _catalog_with_runtime_detachment_selection(ArmyCatalog.phase9a_canonical_content_pack())
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))

    activation = RuntimeContentActivation.from_armies(armies=(army,), catalog=catalog)
    payload = activation.to_payload()

    assert activation.selected_faction_ids == ("core-marine-force",)
    assert activation.selected_detachment_ids == ("core-combined-arms",)
    assert activation.selected_enhancement_ids == ("runtime-enhancement",)
    assert activation.selected_stratagem_ids == ("runtime-ambush",)
    assert activation.selected_datasheet_ids == ("core-intercessor-like-infantry",)
    assert activation.selected_wargear_ids == ("core-bolt-rifle",)
    assert activation.selected_weapon_profile_ids == ("core-bolt-rifle:standard",)
    assert activation.selected_weapon_keywords == ("HAZARDOUS", "RAPID_FIRE")
    assert activation.loaded_unit_instance_ids == ("army-alpha:intercessor-unit-1",)
    assert [
        assignment.to_payload() for assignment in activation.selected_enhancement_assignments
    ] == [
        {
            "bearer_model_instance_id": "army-alpha:intercessor-unit-1:core-intercessor-like:001",
            "assignment_id": "army-alpha:runtime-enhancement:intercessor-unit-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "runtime-enhancement",
            "target_unit_selection_id": "intercessor-unit-1",
            "bearer_unit_instance_id": "army-alpha:intercessor-unit-1",
            "source_id": "source:runtime-enhancement-assignment",
        }
    ]
    assert RuntimeContentActivation.from_payload(payload) == activation
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)


def test_runtime_loader_imports_only_selected_module_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.runtime_content_selected_module"
    module = ModuleType(module_name)
    calls: list[str] = []

    def runtime_contribution() -> RuntimeContentContribution:
        calls.append(module_name)
        return RuntimeContentContribution()

    module.__dict__["runtime_contribution"] = runtime_contribution
    monkeypatch.setitem(sys.modules, module_name, module)
    activation = _manual_activation(
        selected_faction_ids=("faction-alpha",),
        selected_detachment_ids=("detachment-alpha",),
    )
    manifest = RuntimeContentManifest(
        rows=(
            _manifest_row(
                content_id="faction-alpha",
                family=RuntimeContentModuleFamily.FACTION,
                module_path=module_name,
            ),
            _manifest_row(
                content_id="detachment-alpha",
                family=RuntimeContentModuleFamily.DETACHMENT,
                module_path=module_name,
            ),
        )
    )
    resolved_activation = manifest.resolve_activation(activation)

    contributions = load_runtime_content_contributions(
        activation=resolved_activation,
        manifest=manifest,
    )

    assert contributions == (RuntimeContentContribution(contribution_id=module_name),)
    assert calls == [module_name]
    assert resolved_activation.selected_module_paths == (module_name,)
    assert resolved_activation.reachable_content_ids == ("detachment-alpha", "faction-alpha")


def test_runtime_manifest_rejects_selected_content_without_row() -> None:
    activation = _manual_activation(selected_faction_ids=("faction-alpha",))

    with pytest.raises(GameLifecycleError, match="missing selected support"):
        RuntimeContentManifest(rows=()).resolve_activation(activation)


def test_runtime_manifest_resolves_transitive_source_only_and_supported_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "tests.runtime_content_dependency_module"
    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)
    module.__dict__["runtime_contribution"] = lambda: RuntimeContentContribution()
    activation = _manual_activation(selected_detachment_ids=("detachment-alpha",))
    manifest = RuntimeContentManifest(
        rows=(
            _manifest_row(
                content_id="detachment-alpha",
                family=RuntimeContentModuleFamily.DETACHMENT,
                support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
                dependency_ids=("granted-weapon-ability",),
            ),
            _manifest_row(
                content_id="granted-weapon-ability",
                family=RuntimeContentModuleFamily.WEAPON_PROFILE,
                module_path=module_name,
                execution_record_ids=("execution:weapon-ability",),
            ),
        )
    )

    resolved_activation = manifest.resolve_activation(activation)
    contributions = load_runtime_content_contributions(
        activation=resolved_activation,
        manifest=manifest,
    )

    assert resolved_activation.reachable_content_ids == (
        "detachment-alpha",
        "granted-weapon-ability",
    )
    assert resolved_activation.selected_module_paths == (module_name,)
    assert resolved_activation.selected_execution_record_ids == ("execution:weapon-ability",)
    assert len(resolved_activation.activation_hash) == 64
    assert contributions == (RuntimeContentContribution(contribution_id=module_name),)


def test_runtime_manifest_validation_is_fail_fast() -> None:
    valid_row = _manifest_row(
        content_id="source-only",
        family=RuntimeContentModuleFamily.WARGEAR,
        support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
    )

    with pytest.raises(GameLifecycleError, match="require module_path"):
        _manifest_row(content_id="supported-missing", family=RuntimeContentModuleFamily.FACTION)
    with pytest.raises(GameLifecycleError, match="must not import code"):
        _manifest_row(
            content_id="source-only-import",
            family=RuntimeContentModuleFamily.WARGEAR,
            module_path="tests.runtime_content_source_only",
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        RuntimeContentManifest(rows=cast(tuple[RuntimeContentManifestRow, ...], [valid_row]))
    with pytest.raises(GameLifecycleError, match="must contain RuntimeContentManifestRow"):
        RuntimeContentManifest(rows=cast(tuple[RuntimeContentManifestRow, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="content IDs must be unique"):
        RuntimeContentManifest(rows=(valid_row, valid_row))
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        RuntimeContentManifestRow(
            content_id="bad-family-type",
            family=cast(RuntimeContentModuleFamily, 17),
            source_ids=("source:bad-family-type",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported RuntimeContentModuleFamily"):
        RuntimeContentManifestRow(
            content_id="bad-family-token",
            family=cast(RuntimeContentModuleFamily, "bad-family"),
            source_ids=("source:bad-family-token",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
    with pytest.raises(GameLifecycleError, match="RuntimeContentSupportStatus token"):
        RuntimeContentManifestRow(
            content_id="bad-status-type",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=("source:bad-status-type",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=cast(RuntimeContentSupportStatus, 17),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported RuntimeContentSupportStatus"):
        RuntimeContentManifestRow(
            content_id="bad-status-token",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=("source:bad-status-token",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=cast(RuntimeContentSupportStatus, "bad-status"),
        )
    with pytest.raises(GameLifecycleError, match="RuntimeContentSemanticStatus token"):
        RuntimeContentManifestRow(
            content_id="bad-semantic-status-type",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=("source:bad-semantic-status-type",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            semantic_status=cast(RuntimeContentSemanticStatus, 17),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported RuntimeContentSemanticStatus"):
        RuntimeContentManifestRow(
            content_id="bad-semantic-status-token",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=("source:bad-semantic-status-token",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            semantic_status=cast(RuntimeContentSemanticStatus, "bad-semantic-status"),
        )
    with pytest.raises(GameLifecycleError, match="dependency_ids must not contain duplicates"):
        _manifest_row(
            content_id="duplicate-dependencies",
            family=RuntimeContentModuleFamily.FACTION,
            module_path="tests.runtime_content_duplicate_dependencies",
            dependency_ids=("dependency-a", "dependency-a"),
        )
    with pytest.raises(GameLifecycleError, match="content_id must not be empty"):
        RuntimeContentManifestRow(
            content_id=" ",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=("source:blank",),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id="source-package-id:test",
            source_package_hash="source-package-hash:test",
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
    with pytest.raises(GameLifecycleError, match="absolute and normalized"):
        _manifest_row(
            content_id="bad-module-path",
            family=RuntimeContentModuleFamily.FACTION,
            module_path="tests..runtime_content",
        )
    duplicate_owner_catalog = _catalog_with_duplicate_runtime_enhancement_owner()
    with pytest.raises(GameLifecycleError, match="multiple owners"):
        RuntimeContentManifest.from_catalog(catalog=duplicate_owner_catalog, generated_rows=())
    with pytest.raises(GameLifecycleError, match="requires activation"):
        RuntimeContentManifest(rows=(valid_row,)).resolve_activation(
            cast(RuntimeContentActivation, object())
        )


def test_runtime_manifest_records_unsupported_content_and_fails_closed_by_default() -> None:
    activation = _manual_activation(selected_detachment_ids=("detachment-alpha",))
    manifest = RuntimeContentManifest(
        rows=(
            _manifest_row(
                content_id="detachment-alpha",
                family=RuntimeContentModuleFamily.DETACHMENT,
                support_status=RuntimeContentSupportStatus.UNSUPPORTED,
                unsupported_reason="structured_semantics_pending",
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="unsupported required content"):
        manifest.resolve_activation(activation)

    resolved = manifest.resolve_activation(
        activation,
        fail_on_required_unsupported=False,
    )

    assert resolved.selected_module_paths == ()
    assert resolved.unsupported_content_ids == ("detachment-alpha",)
    assert resolved.unsupported_reasons_by_content_id == {
        "detachment-alpha": "structured_semantics_pending"
    }
    immutable_reasons = cast(dict[str, str], resolved.unsupported_reasons_by_content_id)
    with pytest.raises(TypeError):
        immutable_reasons["detachment-alpha"] = "mutated_reason"
    assert resolved.source_package_ids == ("source-package-id:test",)
    assert resolved.source_package_hashes == ("source-package-hash:test",)
    assert RuntimeContentActivation.from_payload(resolved.to_payload()) == resolved

    with pytest.raises(GameLifecycleError, match="require unsupported_reason"):
        _manifest_row(
            content_id="unsupported-without-reason",
            family=RuntimeContentModuleFamily.DETACHMENT,
            support_status=RuntimeContentSupportStatus.UNSUPPORTED,
        )
    with pytest.raises(GameLifecycleError, match="cannot include unsupported_reason"):
        _manifest_row(
            content_id="supported-with-unsupported-reason",
            family=RuntimeContentModuleFamily.DETACHMENT,
            module_path="tests.runtime_content_supported",
            unsupported_reason="invalid_reason",
        )


def test_runtime_event_index_dispatches_matching_subscriptions_deterministically() -> None:
    seen: list[str] = []
    config = _config()
    state = GameState.from_config(config)
    decisions = DecisionController()

    def first_handler(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        seen.append(f"first:{context.event.event_id}:{context.state.game_id}")
        return RuntimeContentEventResult(
            subscription_id="subscription-a",
            source_rule_id="source:first",
            status=RuntimeEventStatus.APPLIED,
            replay_payload={"event_id": context.event.event_id},
        )

    def second_handler(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        seen.append(f"second:{context.event.event_id}:{context.army_catalog.catalog_id}")
        return RuntimeContentEventResult.applied(
            RuntimeContentEventSubscription(
                subscription_id="subscription-b",
                source_rule_id="source:second",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:second",
            )
        )

    index = RuntimeContentEventIndex.from_subscriptions(
        (
            RuntimeContentEventSubscription(
                subscription_id="subscription-b",
                source_rule_id="source:second",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:second",
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-a",
                source_rule_id="source:first",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:first",
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-c",
                source_rule_id="source:wrong-trigger",
                trigger_kind=TimingTriggerKind.END_PHASE,
                handler_id="handler:first",
                filters={"player_id": "player-b"},
            ),
        ),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            (
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:first",
                    handler=first_handler,
                ),
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:second",
                    handler=second_handler,
                ),
            )
        ),
    )

    results = index.dispatch(
        RuntimeContentEvent(
            event_id="runtime-event-1",
            game_id="game-1",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert [result.subscription_id for result in results] == [
        "subscription-a",
        "subscription-b",
    ]
    assert seen == [
        "first:runtime-event-1:runtime-content-game",
        "second:runtime-event-1:phase9a-canonical",
    ]
    assert RuntimeContentEventResult.from_payload(results[0].to_payload()) == results[0]

    with pytest.raises(GameLifecycleError, match="subscription IDs must be unique"):
        RuntimeContentEventIndex.from_subscriptions(
            (
                RuntimeContentEventSubscription(
                    subscription_id="subscription-a",
                    source_rule_id="source:first",
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    handler_id="handler:first",
                ),
                RuntimeContentEventSubscription(
                    subscription_id="subscription-a",
                    source_rule_id="source:duplicate",
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    handler_id="handler:first",
                ),
            ),
            handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
                (
                    RuntimeContentEventHandlerBinding(
                        handler_id="handler:first",
                        handler=first_handler,
                    ),
                )
            ),
        )


def test_runtime_content_bundle_builds_player_filtered_indexes_and_summary_payload() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    activation = RuntimeContentActivation.from_armies(armies=(army,), catalog=catalog)

    def fall_back_handler(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return None

    fall_back_binding = FallBackEligibilityHookBinding(
        hook_id="runtime:fall-back-hook",
        source_id="runtime:fall-back-source",
        handler=fall_back_handler,
    )

    def attack_reroll_handler(
        _context: AttackRerollPermissionContext,
    ) -> None:
        return None

    attack_reroll_binding = AttackRerollPermissionBinding(
        modifier_id="runtime:attack-reroll-permission",
        source_id="runtime:attack-reroll-source",
        handler=attack_reroll_handler,
    )

    contribution = RuntimeContentContribution(
        ability_records=(
            _ability_record(
                ability_id="runtime-faction-ability",
                source_kind=AbilitySourceKind.FACTION,
                faction_id="core-marine-force",
            ),
        ),
        stratagem_records=(
            _stratagem_record(
                stratagem_id="runtime-ambush",
                detachment_id="core-combined-arms",
            ),
        ),
        fall_back_hook_bindings=(fall_back_binding,),
        attack_reroll_permission_bindings=(attack_reroll_binding,),
    )

    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(contribution,),
    )
    summary = bundle.to_summary_payload()
    encoded = json.dumps(summary, sort_keys=True)

    assert summary["ability_index_record_ids_by_player_id"]["player-a"] == [
        "record:runtime-faction-ability"
    ]
    assert summary["stratagem_index_record_ids_by_player_id"]["player-a"] == [
        "record:runtime-ambush"
    ]
    assert "core:hazardous" in summary["ability_handler_ids"]
    assert summary["fall_back_hook_ids"] == ["runtime:fall-back-hook"]
    assert summary["enhancement_effect_binding_ids"] == []
    assert summary["fight_activation_ability_hook_ids"] == []
    assert summary["unit_characteristic_modifier_ids"] == []
    assert summary["hit_roll_modifier_ids"] == []
    assert summary["wound_roll_modifier_ids"] == []
    assert summary["save_option_modifier_ids"] == []
    assert summary["movement_budget_modifier_ids"] == []
    assert summary["objective_control_modifier_ids"] == []
    assert summary["attack_reroll_permission_modifier_ids"] == ["runtime:attack-reroll-permission"]
    assert summary["contribution_ids"] == ["runtime-content:module-default"]
    assert len(summary["bundle_summary_hash"]) == 64
    assert "object at 0x" not in encoded
    assert "<" not in encoded
    assert tuple(
        binding.binding
        for binding in bundle.hook_bindings_for_event(LifecycleHookEvent.FALL_BACK_ELIGIBILITY)
    ) == (fall_back_binding,)

    bundle_without_attack_reroll = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(replace(contribution, attack_reroll_permission_bindings=()),),
    )
    summary_without_attack_reroll = bundle_without_attack_reroll.to_summary_payload()

    assert summary_without_attack_reroll["attack_reroll_permission_modifier_ids"] == []
    assert summary_without_attack_reroll["bundle_summary_hash"] != summary["bundle_summary_hash"]


def test_runtime_content_bundle_summary_hash_tracks_every_previously_omitted_registry() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    activation = RuntimeContentActivation.from_armies(armies=(army,), catalog=catalog)
    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(RuntimeContentContribution(),),
    )
    baseline_summary = bundle.to_summary_payload()
    runtime_modifiers = bundle.runtime_modifier_registry
    start_battle_binding = StartBattleHookBinding(
        hook_id="runtime:start-battle-hook",
        source_id="runtime:start-battle-source",
        request_handler=lambda _context: None,
    )
    damage_roll_binding = DamageRollModifierBinding(
        modifier_id="runtime:damage-roll-modifier",
        source_id="runtime:damage-roll-source",
        handler=lambda _context: 0,
    )
    allocated_damage_binding = AllocatedAttackDamageModifierBinding(
        modifier_id="runtime:allocated-attack-damage-modifier",
        source_id="runtime:allocated-attack-damage-source",
        handler=lambda _context: 0,
    )
    failed_save_binding = FailedSaveDamageReplacementBinding(
        modifier_id="runtime:failed-save-damage-replacement",
        source_id="runtime:failed-save-damage-replacement-source",
        handler=lambda _context: None,
    )
    variants = (
        (
            "start_battle_hook_ids",
            start_battle_binding.hook_id,
            replace(
                bundle,
                start_battle_hook_registry=StartBattleHookRegistry.from_bindings(
                    (*bundle.start_battle_hook_registry.all_bindings(), start_battle_binding)
                ),
            ),
        ),
        (
            "damage_roll_modifier_ids",
            damage_roll_binding.modifier_id,
            replace(
                bundle,
                runtime_modifier_registry=replace(
                    runtime_modifiers,
                    damage_roll_modifier_bindings=(
                        *runtime_modifiers.damage_roll_modifier_bindings,
                        damage_roll_binding,
                    ),
                ),
            ),
        ),
        (
            "allocated_attack_damage_modifier_ids",
            allocated_damage_binding.modifier_id,
            replace(
                bundle,
                runtime_modifier_registry=replace(
                    runtime_modifiers,
                    allocated_attack_damage_modifier_bindings=(
                        *runtime_modifiers.allocated_attack_damage_modifier_bindings,
                        allocated_damage_binding,
                    ),
                ),
            ),
        ),
        (
            "failed_save_damage_replacement_modifier_ids",
            failed_save_binding.modifier_id,
            replace(
                bundle,
                runtime_modifier_registry=replace(
                    runtime_modifiers,
                    failed_save_damage_replacement_bindings=(
                        *runtime_modifiers.failed_save_damage_replacement_bindings,
                        failed_save_binding,
                    ),
                ),
            ),
        ),
    )

    for summary_field, binding_id, variant in variants:
        variant_summary = variant.to_summary_payload()
        variant_payload = cast(Mapping[str, JsonValue], variant_summary)

        assert binding_id in cast(list[str], variant_payload[summary_field])
        assert variant_summary["bundle_summary_hash"] != baseline_summary["bundle_summary_hash"]


def test_runtime_content_bundle_summary_has_static_registry_family_parity() -> None:
    source = dedent(getsource(runtime_content_bundle_summary_payload))
    tree = ast.parse(source)
    payload_assignments = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "payload" for target in node.targets)
        and isinstance(node.value, ast.Dict)
    )
    assert len(payload_assignments) == 1
    payload_dict = cast(ast.Dict, payload_assignments[0].value)
    payload_dependencies = {
        path
        for value in payload_dict.values
        for node in ast.walk(value)
        if isinstance(node, ast.Attribute)
        if (path := _attribute_path(node)) is not None
    }
    bundle_registry_paths = {
        f"bundle.{field.name}"
        for field in fields(RuntimeContentBundle)
        if field.name.endswith("_registry")
    }
    runtime_modifier_binding_paths = {
        f"bundle.runtime_modifier_registry.{field.name}"
        for field in fields(RuntimeModifierRegistry)
        if field.name.endswith("_bindings")
    }

    assert bundle_registry_paths <= payload_dependencies
    assert runtime_modifier_binding_paths <= payload_dependencies


def test_runtime_content_bundle_event_keyed_hooks_match_legacy_registries() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    activation = RuntimeContentActivation.from_armies(armies=(army,), catalog=catalog)

    def fall_back_handler(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return None

    fall_back_binding = FallBackEligibilityHookBinding(
        hook_id="runtime:fall-back-parity-hook",
        source_id="runtime:fall-back-parity-source",
        handler=fall_back_handler,
    )
    contribution = RuntimeContentContribution(
        ability_records=(_tracked_target_ability_record(),),
        fall_back_hook_bindings=(fall_back_binding,),
    )

    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(army,),
        catalog=catalog,
        contributions=(contribution,),
    )
    battle_round_start_registry_ids = {
        binding.hook_id for binding in bundle.battle_round_start_hook_registry.all_bindings()
    }
    battle_round_start_event_ids = {
        binding.hook_id
        for binding in bundle.hook_bindings_for_event(LifecycleHookEvent.BATTLE_ROUND_START)
    }
    fall_back_registry_ids = {
        binding.hook_id for binding in bundle.fall_back_hook_registry.all_bindings()
    }
    fall_back_event_ids = {
        binding.hook_id
        for binding in bundle.hook_bindings_for_event(LifecycleHookEvent.FALL_BACK_ELIGIBILITY)
    }

    assert battle_round_start_registry_ids == {CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID}
    assert battle_round_start_event_ids == battle_round_start_registry_ids
    assert fall_back_registry_ids == {"runtime:fall-back-parity-hook"}
    assert fall_back_event_ids == fall_back_registry_ids


def test_runtime_content_contribution_stores_hooks_in_canonical_tuple() -> None:
    def fall_back_handler(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return None

    fall_back_binding = FallBackEligibilityHookBinding(
        hook_id="combined:shared-hook",
        source_id="combined:fall-back-source",
        handler=fall_back_handler,
    )

    def fight_unit_selected_handler(
        _context: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return ()

    fight_unit_selected_binding = FightUnitSelectedHookBinding(
        hook_id="combined:shared-hook",
        source_id="combined:fight-unit-selected-source",
        handler=fight_unit_selected_handler,
    )

    def generic_handler() -> None:
        return None

    generic_binding: HookBinding[LifecycleHookEvent, Callable[[], None]] = HookBinding(
        hook_id="combined:generic-hook",
        source_id="combined:generic-source",
        handler=generic_handler,
    )
    generic_hook_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=generic_binding,
    )

    legacy_contribution = RuntimeContentContribution(fall_back_hook_bindings=(fall_back_binding,))
    canonical_contribution = RuntimeContentContribution(
        hook_bindings=(fight_unit_selected_binding, fall_back_binding)
    )
    generic_contribution = RuntimeContentContribution(hook_bindings=(generic_hook_binding,))

    assert tuple(binding.binding for binding in legacy_contribution.hook_bindings) == (
        fall_back_binding,
    )
    assert tuple(binding.lifecycle_event for binding in canonical_contribution.hook_bindings) == (
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        LifecycleHookEvent.FIGHT_UNIT_SELECTED,
    )
    assert tuple(binding.binding for binding in canonical_contribution.hook_bindings) == (
        fall_back_binding,
        fight_unit_selected_binding,
    )
    assert generic_contribution.hook_bindings == (generic_hook_binding,)
    assert canonical_contribution.fall_back_hook_bindings == (fall_back_binding,)
    assert canonical_contribution.fight_unit_selected_hook_bindings == (
        fight_unit_selected_binding,
    )

    with pytest.raises(
        GameLifecycleError,
        match="hook binding IDs must be unique per lifecycle event",
    ):
        RuntimeContentContribution(
            hook_bindings=(fall_back_binding,),
            fall_back_hook_bindings=(fall_back_binding,),
        )


def test_runtime_content_contribution_combiner_merges_surfaces_and_rejects_duplicates() -> None:
    ability_record = _ability_record(
        ability_id="combined-ability",
        source_kind=AbilitySourceKind.FACTION,
        faction_id="core-marine-force",
    )
    stratagem_record = _stratagem_record(
        stratagem_id="combined-stratagem",
        detachment_id="core-combined-arms",
    )

    def ability_handler(
        record: AbilityCatalogRecord,
        context: AbilityExecutionContext,
    ) -> AbilityResolutionResult:
        return AbilityResolutionResult.applied(record)

    ability_binding = AbilityHandlerBinding(
        handler_id="combined:ability-handler",
        timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_PHASE),
        required_input_keys=(),
        handler=ability_handler,
    )

    def named_handler(context: object) -> object:
        return context

    def fall_back_handler(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return None

    fall_back_binding = FallBackEligibilityHookBinding(
        hook_id="combined:fall-back-hook",
        source_id="combined:fall-back-source",
        handler=fall_back_handler,
    )

    def enhancement_effect_handler(
        _context: EnhancementEffectContext,
    ) -> tuple[EnhancementCharacteristicModifier, ...]:
        return ()

    enhancement_effect_binding = EnhancementEffectBinding(
        effect_id="combined:enhancement-effect",
        source_id="combined:enhancement-source",
        enhancement_id="combined-enhancement",
        handler=enhancement_effect_handler,
    )

    def fight_activation_ability_handler(
        _context: FightActivationAbilityContext,
    ) -> FightActivationAbilityOption | None:
        return None

    fight_activation_ability_binding = FightActivationAbilityHookBinding(
        hook_id="combined:fight-activation-ability-hook",
        source_id="combined:fight-activation-ability-source",
        handler=fight_activation_ability_handler,
    )

    def fight_unit_selected_handler(
        _context: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return ()

    fight_unit_selected_binding = FightUnitSelectedHookBinding(
        hook_id="combined:fight-unit-selected-hook",
        source_id="combined:fight-unit-selected-source",
        handler=fight_unit_selected_handler,
    )

    def hit_roll_modifier_handler(_context: HitRollModifierContext) -> int:
        return 0

    hit_roll_modifier_binding = HitRollModifierBinding(
        modifier_id="combined:hit-roll-modifier",
        source_id="combined:hit-roll-source",
        handler=hit_roll_modifier_handler,
    )

    def wound_roll_modifier_handler(_context: WoundRollModifierContext) -> int:
        return 0

    wound_roll_modifier_binding = WoundRollModifierBinding(
        modifier_id="combined:wound-roll-modifier",
        source_id="combined:wound-roll-source",
        handler=wound_roll_modifier_handler,
    )

    combined = combine_runtime_content_contributions(
        contribution_id="combined:manifest",
        contributions=(
            RuntimeContentContribution(
                contribution_id="combined:records",
                ability_records=(ability_record,),
                ability_handler_bindings=(ability_binding,),
                fall_back_hook_bindings=(fall_back_binding,),
                enhancement_effect_bindings=(enhancement_effect_binding,),
                fight_activation_ability_hook_bindings=(fight_activation_ability_binding,),
                hook_bindings=(fight_unit_selected_binding,),
                hit_roll_modifier_bindings=(hit_roll_modifier_binding,),
                wound_roll_modifier_bindings=(wound_roll_modifier_binding,),
            ),
            RuntimeContentContribution(
                contribution_id="combined:stratagems",
                stratagem_records=(stratagem_record,),
                faction_named_handlers={
                    "combined:named-handler": cast(FactionRuleNamedHandler, named_handler)
                },
            ),
        ),
    )

    assert combined.contribution_id == "combined:manifest"
    assert combined.ability_records == (ability_record,)
    assert combined.stratagem_records == (stratagem_record,)
    assert combined.ability_handler_bindings == (ability_binding,)
    assert combined.fall_back_hook_bindings == (fall_back_binding,)
    assert combined.enhancement_effect_bindings == (enhancement_effect_binding,)
    assert combined.fight_activation_ability_hook_bindings == (fight_activation_ability_binding,)
    assert combined.fight_unit_selected_hook_bindings == (fight_unit_selected_binding,)
    assert combined.hit_roll_modifier_bindings == (hit_roll_modifier_binding,)
    assert combined.wound_roll_modifier_bindings == (wound_roll_modifier_binding,)
    assert tuple(combined.faction_named_handlers) == ("combined:named-handler",)

    with pytest.raises(GameLifecycleError, match="ability record IDs must be unique"):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-records",
            contributions=(
                RuntimeContentContribution(ability_records=(ability_record,)),
                RuntimeContentContribution(ability_records=(ability_record,)),
            ),
        )
    with pytest.raises(GameLifecycleError, match="ability handler binding IDs must be unique"):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-handlers",
            contributions=(
                RuntimeContentContribution(ability_handler_bindings=(ability_binding,)),
                RuntimeContentContribution(ability_handler_bindings=(ability_binding,)),
            ),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Fall Back eligibility hook binding IDs must be unique",
    ):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-fall-back-hooks",
            contributions=(
                RuntimeContentContribution(fall_back_hook_bindings=(fall_back_binding,)),
                RuntimeContentContribution(fall_back_hook_bindings=(fall_back_binding,)),
            ),
        )
    with pytest.raises(
        GameLifecycleError,
        match="enhancement effect binding IDs must be unique",
    ):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-enhancement-effects",
            contributions=(
                RuntimeContentContribution(
                    enhancement_effect_bindings=(enhancement_effect_binding,)
                ),
                RuntimeContentContribution(
                    enhancement_effect_bindings=(enhancement_effect_binding,)
                ),
            ),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Fight activation ability hook binding IDs must be unique",
    ):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-fight-activation-ability-hooks",
            contributions=(
                RuntimeContentContribution(
                    fight_activation_ability_hook_bindings=(fight_activation_ability_binding,)
                ),
                RuntimeContentContribution(
                    fight_activation_ability_hook_bindings=(fight_activation_ability_binding,)
                ),
            ),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Hit roll modifier binding IDs must be unique",
    ):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-hit-roll-modifiers",
            contributions=(
                RuntimeContentContribution(hit_roll_modifier_bindings=(hit_roll_modifier_binding,)),
                RuntimeContentContribution(hit_roll_modifier_bindings=(hit_roll_modifier_binding,)),
            ),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Wound roll modifier binding IDs must be unique",
    ):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-wound-roll-modifiers",
            contributions=(
                RuntimeContentContribution(
                    wound_roll_modifier_bindings=(wound_roll_modifier_binding,)
                ),
                RuntimeContentContribution(
                    wound_roll_modifier_bindings=(wound_roll_modifier_binding,)
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="faction handler IDs must be unique"):
        combine_runtime_content_contributions(
            contribution_id="combined:duplicate-named-handlers",
            contributions=(
                RuntimeContentContribution(
                    faction_named_handlers={
                        "combined:named-handler": cast(FactionRuleNamedHandler, named_handler)
                    },
                ),
                RuntimeContentContribution(
                    faction_named_handlers={
                        "combined:named-handler": cast(FactionRuleNamedHandler, named_handler)
                    },
                ),
            ),
        )


def test_lifecycle_rebuilds_runtime_content_bundle_without_serializing_callables() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_canonical_lifecycle_config())
    lifecycle.advance_until_decision_or_terminal()
    payload = lifecycle.to_payload()
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    rebuilt = GameLifecycle.from_payload(payload)
    audit_payload = payload.get("runtime_content_audit")

    assert _runtime_content_bundle(rebuilt).to_summary_payload() == summary
    assert summary["activation"]["selected_faction_ids"] == ["core-marine-force"]
    assert isinstance(audit_payload, dict)
    assert audit_payload["bundle_summary_hash"] == summary["bundle_summary_hash"]
    assert "object at 0x" not in json.dumps(summary, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)


def test_lifecycle_direct_runtime_bundle_initializes_canonical_audit() -> None:
    config = _canonical_lifecycle_config()
    source_lifecycle = GameLifecycle()
    source_lifecycle.start(config)
    source_lifecycle.advance_until_decision_or_terminal()
    bundle = _runtime_content_bundle(source_lifecycle)

    lifecycle = GameLifecycle(
        state=source_lifecycle.state,
        _config=config,
        _runtime_content_bundle=bundle,
    )

    audit_payload = lifecycle.to_payload().get("runtime_content_audit")

    assert audit_payload == bundle.to_summary_payload()


def test_lifecycle_runtime_content_refresh_uses_input_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_canonical_lifecycle_config())
    lifecycle.advance_until_decision_or_terminal()
    bundle = _runtime_content_bundle(lifecycle)

    def fail_activation_refresh(*_args: object, **_kwargs: object) -> RuntimeContentActivation:
        raise AssertionError("runtime content activation should be cached")

    monkeypatch.setattr(
        lifecycle_module,
        "runtime_content_activation_for_armies",
        fail_activation_refresh,
    )

    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )

    assert require_runtime_content_bundle() is bundle


def test_runtime_builder_loads_core_source_only_content_and_validates_ruleset() -> None:
    config = _canonical_lifecycle_config()
    bundle = build_runtime_content_bundle(config)
    summary = bundle.to_summary_payload()

    assert summary["activation"]["selected_faction_ids"] == ["core-marine-force"]
    assert summary["selected_module_paths"] == []
    assert summary["source_package_ids"] == [config.army_catalog.source_package_id]
    assert summary["source_package_hashes"] == []
    assert "core:hazardous" in summary["ability_handler_ids"]
    manifest_row = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        config=config,
    ).row_for_content_id("core-marine-force")
    assert manifest_row.support_status is RuntimeContentSupportStatus.SOURCE_ONLY
    assert (
        runtime_content_module_index_for_ruleset(RulesetDescriptor.warhammer_40000_eleventh())
        .faction_modules["death-guard"]
        .endswith(".death_guard.manifest")
    )
    assert (
        runtime_content_activation_for_armies(
            config=config,
            armies=tuple(
                muster_army(catalog=config.army_catalog, request=request)
                for request in config.army_muster_requests
            ),
        ).activation_hash
        == bundle.activation.activation_hash
    )

    with pytest.raises(GameLifecycleError, match="requires GameConfig"):
        build_runtime_content_bundle(cast(GameConfig, object()))
    with pytest.raises(GameLifecycleError, match="requires RulesetDescriptor"):
        runtime_content_module_index_for_ruleset(cast(RulesetDescriptor, object()))
    with pytest.raises(GameLifecycleError, match="requires GameConfig"):
        runtime_content_manifest_for_ruleset(
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            config=cast(GameConfig, object()),
        )


def test_runtime_event_results_and_dispatch_fail_closed() -> None:
    config = _config()
    state = GameState.from_config(config)
    decisions = DecisionController()

    def handler(_context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        return RuntimeContentEventResult.invalid(
            subscription,
            reason="rule_invalid",
            replay_payload={"reason": "rule_invalid"},
        )

    subscription = RuntimeContentEventSubscription(
        subscription_id="subscription-runtime",
        source_rule_id="source:runtime",
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler_id="handler:runtime",
    )
    event = RuntimeContentEvent.from_payload(
        {
            "event_id": "event-runtime",
            "game_id": "game-runtime",
            "player_id": "player-a",
            "battle_round": 1,
            "trigger_kind": TimingTriggerKind.START_PHASE.value,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-a",
            "source_unit_instance_id": None,
            "target_unit_instance_ids": ["unit-b", "unit-a"],
            "event_payload": {"window": "start"},
        }
    )

    index = RuntimeContentEventIndex.from_subscriptions(
        (subscription,),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            (
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:runtime",
                    handler=handler,
                ),
            )
        ),
    )
    result = index.dispatch(
        event,
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )[0]

    assert event.target_unit_instance_ids == ("unit-a", "unit-b")
    assert result.status is RuntimeEventStatus.INVALID
    assert (
        RuntimeContentEventResult.unsupported(
            subscription,
            reason="missing_support",
        ).reason
        == "missing_support"
    )
    assert RuntimeContentEventIndex.empty().all_subscriptions() == ()

    with pytest.raises(GameLifecycleError, match="cannot include reason"):
        RuntimeContentEventResult(
            subscription_id="subscription-runtime",
            source_rule_id="source:runtime",
            status=RuntimeEventStatus.APPLIED,
            reason="unexpected",
        )
    with pytest.raises(GameLifecycleError, match="requires reason"):
        RuntimeContentEventResult(
            subscription_id="subscription-runtime",
            source_rule_id="source:runtime",
            status=RuntimeEventStatus.INVALID,
        )
    with pytest.raises(GameLifecycleError, match="must be callable"):
        RuntimeContentEventHandlerBinding(
            handler_id="handler:bad",
            handler=cast(RuntimeEventHandler, None),
        )
    with pytest.raises(GameLifecycleError, match="requires a TimingTriggerKind"):
        index.subscriptions_for(cast(TimingTriggerKind, "start_phase"))
    with pytest.raises(GameLifecycleError, match="references missing handler"):
        RuntimeContentEventIndex.from_subscriptions(
            (
                RuntimeContentEventSubscription(
                    subscription_id="subscription-missing",
                    source_rule_id="source:missing",
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    handler_id="handler:missing",
                ),
            ),
            handler_registry=RuntimeContentEventHandlerRegistry.empty(),
        )

    other_subscription = RuntimeContentEventSubscription(
        subscription_id="subscription-other",
        source_rule_id="source:runtime",
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler_id="handler:other",
    )

    def drifting_handler(_context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        return RuntimeContentEventResult.applied(other_subscription)

    drift_index = RuntimeContentEventIndex.from_subscriptions(
        (
            RuntimeContentEventSubscription(
                subscription_id="subscription-runtime",
                source_rule_id="source:runtime",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler_id="handler:drift",
            ),
        ),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            (
                RuntimeContentEventHandlerBinding(
                    handler_id="handler:drift",
                    handler=drifting_handler,
                ),
            )
        ),
    )
    with pytest.raises(GameLifecycleError, match="subscription_id drift"):
        drift_index.dispatch(
            event,
            state=state,
            decisions=decisions,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


__all__: list[str] = []
__all__ += ["AbilityDefinition", "ArmyMusterRequest", "CatalogDetachmentDefinition"]
__all__ += ["CatalogEnhancementDefinition", "CatalogStratagemDefinition", "DecisionResult"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "DetachmentSelection", "EnhancementAssignment"]
__all__ += ["MissionSetup", "ModelProfileSelection", "RuleClause", "RuleCondition"]
__all__ += ["RuleConditionKind", "RuleEffectKind", "RuleEffectSpec", "RuleIR", "RuleTargetKind"]
__all__ += ["RuleTargetSpec", "RuleTrigger", "RuleTriggerKind", "RuntimeContentModuleIndex"]
__all__ += ["STRATAGEM_DECISION_TYPE", "RuntimeContentModuleRef", "StratagemAvailabilityKind"]
__all__ += ["StratagemCatalogRecord", "StratagemCategory", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemHandler", "StratagemHandlerBinding"]
__all__ += ["StratagemHandlerContext", "StratagemHandlerExecutionResult"]
__all__ += ["StratagemHandlerExecutionStatus", "StratagemHandlerRegistry"]
__all__ += ["StratagemTargetBinding", "StratagemTimingDescriptor", "StratagemUseRecord"]
__all__ += ["TextSpan", "UnitMusterSelection", "Wargear", "WeaponKeyword", "_mission_setup"]
__all__ += ["_stratagem_handler_context", "_tracked_target_rule_ir"]
__all__ += ["chapter_approved_2026_27_mission_pack", "faction_execution_2026_27", "import_module"]
__all__ += ["parameters_from_pairs"]
