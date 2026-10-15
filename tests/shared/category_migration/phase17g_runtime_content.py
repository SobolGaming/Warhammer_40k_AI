from __future__ import annotations

import ast
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import fields, replace
from importlib import import_module
from inspect import getsource
from textwrap import dedent
from types import ModuleType
from typing import cast

import pytest

import warhammer40k_core.engine.lifecycle as lifecycle_module
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import DetachmentDefinition as CatalogDetachmentDefinition
from warhammer40k_core.core.detachment import EnhancementDefinition as CatalogEnhancementDefinition
from warhammer40k_core.core.detachment import StratagemDefinition as CatalogStratagemDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityHandlerBinding,
    AbilityResolutionResult,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierBinding,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
)
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
from warhammer40k_core.engine.faction_content.bundle_payloads import (
    runtime_content_bundle_summary_payload,
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
from warhammer40k_core.engine.faction_content.hooks import RuntimeHookBinding
from warhammer40k_core.engine.faction_content.loader import (
    RuntimeContentModuleIndex,
    RuntimeContentModuleRef,
    load_runtime_content_contributions,
)
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentSemanticStatus,
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
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedEffectGrant,
    FightUnitSelectedHookBinding,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.lifecycle_hooks import HookBinding, LifecycleHookEvent
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionBinding,
    AttackRerollPermissionContext,
    DamageRollModifierBinding,
    FailedSaveDamageReplacementBinding,
    HitRollModifierBinding,
    HitRollModifierContext,
    RuntimeModifierRegistry,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.start_battle_hooks import (
    StartBattleHookBinding,
    StartBattleHookRegistry,
)
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
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_execution_2026_27


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
    semantic_status: RuntimeContentSemanticStatus = RuntimeContentSemanticStatus.PLACEHOLDER,
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
        semantic_status=semantic_status,
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
        force_disposition_id="purge-the-foe",
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
        enhancement_assignments=(
            EnhancementAssignment(
                model_profile_id="core-intercessor-like",
                model_index=1,
                enhancement_id="runtime-enhancement",
                target_unit_selection_id="intercessor-unit-1",
                source_id="source:runtime-enhancement-assignment",
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


def _tracked_target_ability_record() -> AbilityCatalogRecord:
    rule_ir = _tracked_target_rule_ir()
    return AbilityCatalogRecord(
        record_id="record:runtime-tracked-target",
        definition=AbilityDefinition(
            ability_id="runtime-tracked-target",
            name="Runtime Tracked Target",
            source_id="source:runtime-tracked-target",
            when_descriptor="test battle-round start timing",
            effect_descriptor="test tracked target",
            restrictions_descriptor="test restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.FACTION,
        faction_id="core-marine-force",
    )


def _tracked_target_rule_ir() -> RuleIR:
    span = TextSpan(text="runtime tracked target", start=0, end=22)
    return RuleIR(
        rule_id="runtime-tracked-target-rule",
        source_id="runtime-tracked-target-source",
        normalized_text=span.text,
        parser_version="runtime-content-test",
        clauses=(
            RuleClause(
                clause_id="runtime-tracked-target-reroll",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("actor", "model_in_this_models_unit"),
                            ("attack_kind", "ranged"),
                            ("roll_type", "hit"),
                            ("target_reference", "tracked_target"),
                            ("tracked_target_owner", "this_unit"),
                            ("tracked_target_role", "prey"),
                        )
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (
                                ("actor", "model_in_this_models_unit"),
                                ("attack_kind", "ranged"),
                                ("gate_subject", "attack_target"),
                                ("relationship", "attack_targets_tracked_target"),
                                ("target_reference", "tracked_target"),
                                ("tracked_target_owner", "this_unit"),
                                ("tracked_target_role", "prey"),
                            )
                        ),
                    ),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.REROLL_PERMISSION,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (
                                ("roll_type", "hit"),
                                ("target_reference", "tracked_target"),
                                ("tracked_target_owner", "this_unit"),
                                ("tracked_target_role", "prey"),
                            )
                        ),
                    ),
                ),
            ),
            RuleClause(
                clause_id="runtime-tracked-target-selection",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "start"),
                            ("phase", "battle_round"),
                            ("timing_window", "battle_round_start"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.ENEMY_UNIT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.SELECT_TRACKED_TARGET,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (
                                ("replacement", False),
                                ("selection_kind", "select_one"),
                                ("target_allegiance", "enemy"),
                                ("target_lifecycle", "until_destroyed"),
                                ("target_scope", "enemy_unit"),
                                ("tracked_target_owner", "this_unit"),
                                ("tracked_target_role", "prey"),
                            )
                        ),
                    ),
                ),
            ),
        ),
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
                force_disposition_id="purge-the-foe",
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
                force_disposition_id="take-and-hold",
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
                force_disposition_id="purge-the-foe",
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
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    if type(bundle) is not RuntimeContentBundle:
        raise AssertionError("Runtime content bundle was not rebuilt.")
    return bundle


def _attribute_path(node: ast.Attribute) -> str | None:
    parts = [node.attr]
    value = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name):
        return None
    parts.append(value.id)
    return ".".join(reversed(parts))


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
        canonical_detachment_id="core-combined-arms-duplicate",
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


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilityExecutionContext"]
__all__ += ["AbilityHandlerBinding", "AbilityResolutionResult", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "AllocatedAttackDamageModifierBinding", "ArmyCatalog"]
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
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameConfig", "GameLifecycle"]
__all__ += ["GameLifecycleError", "GameState", "HitRollModifierBinding", "HitRollModifierContext"]
__all__ += ["HookBinding", "JsonValue", "LifecycleHookEvent", "Mapping", "MissionSetup"]
__all__ += ["ModelProfileSelection", "ModuleType", "RuleClause", "RuleCondition"]
__all__ += ["RuleConditionKind", "RuleEffectKind", "RuleEffectSpec", "RuleIR", "RuleTargetKind"]
__all__ += ["RuleTargetSpec", "RuleTrigger", "RuleTriggerKind", "RulesetDescriptor"]
__all__ += ["RuntimeContentActivation", "RuntimeContentBundle", "RuntimeContentContribution"]
__all__ += ["RuntimeContentEvent", "RuntimeContentEventContext"]
__all__ += ["RuntimeContentEventHandlerBinding", "RuntimeContentEventHandlerRegistry"]
__all__ += ["RuntimeContentEventIndex", "RuntimeContentEventResult"]
__all__ += ["RuntimeContentEventSubscription", "RuntimeContentManifest"]
__all__ += ["RuntimeContentManifestRow", "RuntimeContentModuleFamily"]
__all__ += ["RuntimeContentModuleIndex", "RuntimeContentModuleRef"]
__all__ += ["RuntimeContentSemanticStatus", "RuntimeContentSupportStatus", "RuntimeEventHandler"]
__all__ += ["RuntimeEventStatus", "RuntimeHookBinding", "RuntimeModifierRegistry"]
__all__ += ["STRATAGEM_DECISION_TYPE", "StartBattleHookBinding", "StartBattleHookRegistry"]
__all__ += ["StratagemAvailabilityKind", "StratagemCatalogRecord", "StratagemCategory"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemHandler"]
__all__ += ["StratagemHandlerBinding", "StratagemHandlerContext"]
__all__ += ["StratagemHandlerExecutionResult", "StratagemHandlerExecutionStatus"]
__all__ += ["StratagemHandlerRegistry", "StratagemTargetBinding", "StratagemTimingDescriptor"]
__all__ += ["StratagemUseRecord", "TextSpan", "TimingTriggerKind", "UnitMusterSelection"]
__all__ += ["Wargear", "WeaponKeyword", "WoundRollModifierBinding", "WoundRollModifierContext"]
__all__ += ["_ability_record", "_attribute_path", "_canonical_lifecycle_config"]
__all__ += ["_catalog_with_duplicate_runtime_enhancement_owner"]
__all__ += ["_catalog_with_hazardous_bolt_rifle", "_catalog_with_runtime_detachment_selection"]
__all__ += ["_config", "_manifest_row", "_manual_activation", "_mission_setup", "_muster_request"]
__all__ += ["_runtime_content_bundle", "_stratagem_handler_context", "_stratagem_record"]
__all__ += ["_tracked_target_ability_record", "_tracked_target_rule_ir", "ast"]
__all__ += ["build_runtime_content_bundle", "cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["combine_runtime_content_contributions", "dedent", "faction_execution_2026_27"]
__all__ += ["fields", "getsource", "import_module", "json", "lifecycle_module"]
__all__ += ["load_runtime_content_contributions", "muster_army", "parameters_from_pairs"]
__all__ += ["pytest", "replace", "runtime_content_activation_for_armies"]
__all__ += ["runtime_content_bundle_summary_payload", "runtime_content_manifest_for_ruleset"]
__all__ += ["runtime_content_module_index_for_ruleset", "sys"]
