from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import replace
from importlib import import_module
from types import ModuleType
from typing import cast

import pytest

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
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeEventHandler,
    RuntimeEventStatus,
)
from warhammer40k_core.engine.faction_content.loader import (
    RuntimeContentModuleFamily,
    RuntimeContentModuleIndex,
    RuntimeContentModuleRef,
    load_runtime_content_contributions,
)
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle,
    runtime_content_module_index_for_ruleset,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerBinding,
    StratagemHandlerContext,
    StratagemHandlerExecutionResult,
    StratagemHandlerExecutionStatus,
    StratagemHandlerRegistry,
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
    module_index = RuntimeContentModuleIndex(
        faction_modules={"faction-alpha": module_name},
        detachment_modules={"detachment-alpha": module_name},
        enhancement_modules={},
        stratagem_modules={},
        datasheet_modules={},
        wargear_modules={},
        weapon_profile_modules={},
    )

    contributions = load_runtime_content_contributions(
        activation=activation,
        module_index=module_index,
    )

    assert contributions == (RuntimeContentContribution(),)
    assert calls == [module_name]
    assert module_index.module_paths_for_activation(activation) == (module_name,)


def test_runtime_loader_rejects_selected_content_without_module_ref() -> None:
    activation = _manual_activation(selected_faction_ids=("faction-alpha",))

    with pytest.raises(GameLifecycleError, match="missing selected support"):
        load_runtime_content_contributions(
            activation=activation,
            module_index=RuntimeContentModuleIndex.empty(),
        )


def test_runtime_event_index_dispatches_matching_subscriptions_deterministically() -> None:
    seen: list[str] = []

    def first_handler(event: RuntimeContentEvent) -> RuntimeContentEventResult:
        seen.append(f"first:{event.event_id}")
        return RuntimeContentEventResult(
            subscription_id="subscription-a",
            source_rule_id="source:first",
            status=RuntimeEventStatus.APPLIED,
            replay_payload={"event_id": event.event_id},
        )

    def second_handler(event: RuntimeContentEvent) -> RuntimeContentEventResult:
        seen.append(f"second:{event.event_id}")
        return RuntimeContentEventResult.applied(
            RuntimeContentEventSubscription(
                subscription_id="subscription-b",
                source_rule_id="source:second",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler=second_handler,
            )
        )

    index = RuntimeContentEventIndex.from_subscriptions(
        (
            RuntimeContentEventSubscription(
                subscription_id="subscription-b",
                source_rule_id="source:second",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler=second_handler,
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-a",
                source_rule_id="source:first",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler=first_handler,
            ),
            RuntimeContentEventSubscription(
                subscription_id="subscription-c",
                source_rule_id="source:wrong-trigger",
                trigger_kind=TimingTriggerKind.END_PHASE,
                handler=first_handler,
            ),
        )
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
        )
    )

    assert [result.subscription_id for result in results] == [
        "subscription-a",
        "subscription-b",
    ]
    assert seen == ["first:runtime-event-1", "second:runtime-event-1"]
    assert RuntimeContentEventResult.from_payload(results[0].to_payload()) == results[0]

    with pytest.raises(GameLifecycleError, match="subscription IDs must be unique"):
        RuntimeContentEventIndex.from_subscriptions(
            (
                RuntimeContentEventSubscription(
                    subscription_id="subscription-a",
                    source_rule_id="source:first",
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    handler=first_handler,
                ),
                RuntimeContentEventSubscription(
                    subscription_id="subscription-a",
                    source_rule_id="source:duplicate",
                    trigger_kind=TimingTriggerKind.START_PHASE,
                    handler=first_handler,
                ),
            )
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
    assert "object at 0x" not in encoded
    assert "<" not in encoded


def test_lifecycle_rebuilds_runtime_content_bundle_without_serializing_callables() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_canonical_lifecycle_config())
    lifecycle.advance_until_decision_or_terminal()
    payload = lifecycle.to_payload()
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    rebuilt = GameLifecycle.from_payload(payload)

    assert _runtime_content_bundle(rebuilt).to_summary_payload() == summary
    assert summary["activation"]["selected_faction_ids"] == ["core-marine-force"]
    assert "runtime_content_bundle" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(summary, sort_keys=True)


def test_runtime_builder_loads_core_source_only_content_and_validates_ruleset() -> None:
    bundle = build_runtime_content_bundle(_canonical_lifecycle_config())
    summary = bundle.to_summary_payload()

    assert summary["activation"]["selected_faction_ids"] == ["core-marine-force"]
    assert "core:hazardous" in summary["ability_handler_ids"]
    assert (
        runtime_content_module_index_for_ruleset(RulesetDescriptor.warhammer_40000_eleventh())
        .faction_modules["core-marine-force"]
        .endswith(".common.empty")
    )

    with pytest.raises(GameLifecycleError, match="requires GameConfig"):
        build_runtime_content_bundle(cast(GameConfig, object()))
    with pytest.raises(GameLifecycleError, match="requires RulesetDescriptor"):
        runtime_content_module_index_for_ruleset(cast(RulesetDescriptor, object()))


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
    module_index = RuntimeContentModuleIndex(
        faction_modules={"faction-alpha": "tests.runtime_content_contract_module"},
        detachment_modules={},
        enhancement_modules={},
        stratagem_modules={},
        datasheet_modules={},
        wargear_modules={},
        weapon_profile_modules={},
    )
    module = ModuleType("tests.runtime_content_contract_module")
    monkeypatch.setitem(sys.modules, "tests.runtime_content_contract_module", module)

    assert module_index.module_paths_for_activation(activation) == (
        "tests.runtime_content_contract_module",
    )
    with pytest.raises(GameLifecycleError, match="must expose runtime_contribution"):
        load_runtime_content_contributions(activation=activation, module_index=module_index)

    module.__dict__["runtime_contribution"] = "not-callable"
    with pytest.raises(GameLifecycleError, match="must be callable"):
        load_runtime_content_contributions(activation=activation, module_index=module_index)

    module.__dict__["runtime_contribution"] = lambda: object()
    with pytest.raises(GameLifecycleError, match="returned invalid"):
        load_runtime_content_contributions(activation=activation, module_index=module_index)

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
    module_index = runtime_content_module_index_for_ruleset(
        RulesetDescriptor.warhammer_40000_eleventh()
    )

    module_paths = module_index.module_paths_for_activation(activation)
    contributions = load_runtime_content_contributions(
        activation=activation,
        module_index=module_index,
    )

    assert module_paths == (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "death_guard.detachments.tallyband_summoners.manifest",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.manifest",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.plague_marines",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.units.typhus",
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard.wargear.plague_weapons",
    )
    assert contributions == (RuntimeContentContribution(),) * 5


def test_runtime_event_results_and_dispatch_fail_closed() -> None:
    def handler(_event: RuntimeContentEvent) -> RuntimeContentEventResult:
        return RuntimeContentEventResult.invalid(
            subscription,
            reason="rule_invalid",
            replay_payload={"reason": "rule_invalid"},
        )

    subscription = RuntimeContentEventSubscription(
        subscription_id="subscription-runtime",
        source_rule_id="source:runtime",
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler=handler,
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

    index = RuntimeContentEventIndex.from_subscriptions((subscription,))
    result = index.dispatch(event)[0]

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
        RuntimeContentEventSubscription(
            subscription_id="subscription-bad",
            source_rule_id="source:bad",
            trigger_kind=TimingTriggerKind.START_PHASE,
            handler=cast(RuntimeEventHandler, None),
        )
    with pytest.raises(GameLifecycleError, match="requires a TimingTriggerKind"):
        index.subscriptions_for(cast(TimingTriggerKind, "start_phase"))

    other_subscription = RuntimeContentEventSubscription(
        subscription_id="subscription-other",
        source_rule_id="source:runtime",
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler=handler,
    )

    def drifting_handler(_event: RuntimeContentEvent) -> RuntimeContentEventResult:
        return RuntimeContentEventResult.applied(other_subscription)

    drift_index = RuntimeContentEventIndex.from_subscriptions(
        (
            RuntimeContentEventSubscription(
                subscription_id="subscription-runtime",
                source_rule_id="source:runtime",
                trigger_kind=TimingTriggerKind.START_PHASE,
                handler=drifting_handler,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="subscription_id drift"):
        drift_index.dispatch(event)


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
