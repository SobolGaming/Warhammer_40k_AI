from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from importlib import import_module
from types import ModuleType
from typing import cast

import pytest

import warhammer40k_core.engine.lifecycle as lifecycle_module
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import (
    DetachmentDefinition as CatalogDetachmentDefinition,
)
from warhammer40k_core.core.detachment import (
    EnhancementDefinition as CatalogEnhancementDefinition,
)
from warhammer40k_core.core.detachment import (
    StratagemDefinition as CatalogStratagemDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityHandlerBinding,
    AbilityResolutionResult,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementCharacteristicModifier,
    EnhancementEffectBinding,
    EnhancementEffectContext,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
    combine_runtime_content_contributions,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeEventHandler,
    RuntimeEventStatus,
)
from warhammer40k_core.engine.faction_content.loader import (
    RuntimeContentModuleIndex,
    RuntimeContentModuleRef,
    load_runtime_content_contributions,
)
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle,
    runtime_content_activation_for_armies,
    runtime_content_manifest_for_ruleset,
    runtime_content_module_index_for_ruleset,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandler,
    StratagemHandlerBinding,
    StratagemHandlerContext,
    StratagemHandlerExecutionResult,
    StratagemHandlerExecutionStatus,
    StratagemHandlerRegistry,
)
from warhammer40k_core.engine.faction_rule_execution import FactionRuleNamedHandler
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTimingDescriptor,
    StratagemUseRecord,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
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

    with pytest.raises(GameLifecycleError, match="requires ArmyCatalog"):
        RuntimeContentManifest.from_catalog(
            catalog=cast(ArmyCatalog, object()),
            generated_rows=(),
        )


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


def test_runtime_content_bundle_builds_player_filtered_indexes_and_summary_payload() -> None:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    activation = RuntimeContentActivation.from_armies(armies=(army,), catalog=catalog)
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
    assert summary["fall_back_hook_ids"] == []
    assert summary["enhancement_effect_binding_ids"] == []
    assert summary["fight_activation_ability_hook_ids"] == []
    assert summary["contribution_ids"] == ["runtime-content:module-default"]
    assert len(summary["bundle_summary_hash"]) == 64
    assert "object at 0x" not in encoded
    assert "<" not in encoded


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


def _manual_activation(
    *,
    selected_faction_ids: tuple[str, ...] = (),
    selected_detachment_ids: tuple[str, ...] = (),
) -> RuntimeContentActivation:
    return RuntimeContentActivation(
        selected_faction_ids=selected_faction_ids,
        selected_detachment_ids=selected_detachment_ids,
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )


def _manifest_row(
    *,
    content_id: str,
    family: RuntimeContentModuleFamily,
    module_path: str | None = None,
    support_status: RuntimeContentSupportStatus = RuntimeContentSupportStatus.SUPPORTED,
    dependency_ids: tuple[str, ...] = (),
    execution_record_ids: tuple[str, ...] = (),
    support_reason: str | None = None,
    unsupported_reason: str | None = None,
    required_for_matched_play: bool = True,
) -> RuntimeContentManifestRow:
    return RuntimeContentManifestRow(
        content_id=content_id,
        family=family,
        source_ids=(f"source:{content_id}",),
        owner_faction_id=None,
        owner_detachment_id=None,
        source_package_id="source-package-id:test",
        source_package_hash="source-package-hash:test",
        execution_record_ids=execution_record_ids,
        module_path=module_path,
        support_status=support_status,
        dependency_ids=dependency_ids,
        support_reason=support_reason,
        unsupported_reason=unsupported_reason,
        required_for_matched_play=required_for_matched_play,
    )


def _muster_request(catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("runtime-enhancement",),
            stratagem_ids=("runtime-ambush",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="intercessor-unit-1",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _ability_record(
    *,
    ability_id: str,
    source_kind: AbilitySourceKind,
    faction_id: str | None = None,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"record:{ability_id}",
        definition=AbilityDefinition(
            ability_id=ability_id,
            name=ability_id,
            source_id=f"source:{ability_id}",
            when_descriptor="test timing",
            effect_descriptor="test effect",
            restrictions_descriptor="test restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_PHASE),
        ),
        source_kind=source_kind,
        faction_id=faction_id,
    )


def _stratagem_record(*, stratagem_id: str, detachment_id: str) -> StratagemCatalogRecord:
    return StratagemCatalogRecord(
        record_id=f"record:{stratagem_id}",
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=stratagem_id,
            source_id=f"source:{stratagem_id}",
            command_point_cost=0,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="test timing",
            target_descriptor="test target",
            effect_descriptor="test effect",
            restrictions_descriptor="test restrictions",
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhase.MOVEMENT,
            ),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=detachment_id,
    )


def _stratagem_handler_context(*, handler_id: str) -> StratagemHandlerContext:
    config = _config()
    state = GameState.from_config(config)
    definition = StratagemDefinition(
        stratagem_id="runtime-stratagem",
        name="Runtime Stratagem",
        source_id="source:runtime-stratagem",
        command_point_cost=0,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="test timing",
        target_descriptor="test target",
        effect_descriptor="test effect",
        restrictions_descriptor="test restrictions",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.MOVEMENT,
        ),
        handler_id=handler_id,
    )
    eligibility_context = StratagemEligibilityContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding.none()
    use_record = StratagemUseRecord(
        use_id="stratagem-use:runtime",
        player_id="player-a",
        stratagem_id=definition.stratagem_id,
        source_id=definition.source_id,
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        timing_window_id=None,
        request_id="request:runtime",
        result_id="result:runtime",
        selected_option_id="option:runtime",
        target_binding=target_binding,
        targeted_unit_instance_ids=(),
        affected_unit_instance_ids=(),
        command_point_cost=0,
        command_point_transaction_id=None,
        handler_id=handler_id,
    )
    return StratagemHandlerContext(
        state=state,
        decisions=DecisionController(),
        result=DecisionResult(
            result_id="result:runtime",
            request_id="request:runtime",
            decision_type=STRATAGEM_DECISION_TYPE,
            actor_id="player-a",
            selected_option_id="option:runtime",
            payload=None,
        ),
        eligibility_context=eligibility_context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )


def _config() -> GameConfig:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    return GameConfig(
        game_id="runtime-content-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(catalog),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="enemy-unit",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
    )


def _canonical_lifecycle_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="runtime-content-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="enemy-unit",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    if type(bundle) is not RuntimeContentBundle:
        raise AssertionError("Runtime content bundle was not rebuilt.")
    return bundle


def _catalog_with_hazardous_bolt_rifle(catalog: ArmyCatalog) -> ArmyCatalog:
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id != "core-bolt-rifle":
            updated_wargear.append(wargear)
            continue
        updated_wargear.append(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(profile, keywords=(WeaponKeyword.HAZARDOUS,))
                    for profile in wargear.weapon_profiles
                ),
            )
        )
    return replace(catalog, wargear=tuple(updated_wargear))


def _catalog_with_duplicate_runtime_enhancement_owner() -> ArmyCatalog:
    catalog = _catalog_with_runtime_detachment_selection(
        ArmyCatalog.phase9a_canonical_content_pack()
    )
    primary_detachment = catalog.detachments[0]
    duplicate_detachment = replace(
        primary_detachment,
        detachment_id="core-combined-arms-duplicate",
    )
    return replace(catalog, detachments=(primary_detachment, duplicate_detachment))


def _catalog_with_runtime_detachment_selection(catalog: ArmyCatalog) -> ArmyCatalog:
    updated_detachments: list[CatalogDetachmentDefinition] = []
    for detachment in catalog.detachments:
        if detachment.detachment_id != "core-combined-arms":
            updated_detachments.append(detachment)
            continue
        updated_detachments.append(
            replace(
                detachment,
                enhancement_ids=(*detachment.enhancement_ids, "runtime-enhancement"),
                stratagem_ids=(*detachment.stratagem_ids, "runtime-ambush"),
            )
        )
    return replace(
        catalog,
        detachments=tuple(updated_detachments),
        enhancements=(
            *catalog.enhancements,
            CatalogEnhancementDefinition(
                enhancement_id="runtime-enhancement",
                name="Runtime Enhancement",
                source_id="source:runtime-enhancement",
                points=0,
            ),
        ),
        stratagems=(
            *catalog.stratagems,
            CatalogStratagemDefinition(
                stratagem_id="runtime-ambush",
                name="Runtime Ambush",
                source_id="source:runtime-ambush",
                command_point_cost=0,
            ),
        ),
    )
