from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine import abilities as abilities_module
from warhammer40k_core.engine.abilities import (
    CORE_DEADLY_DEMISE_HANDLER_ID,
    CORE_DEEP_STRIKE_HANDLER_ID,
    CORE_FEEL_NO_PAIN_HANDLER_ID,
    CORE_FIGHTS_FIRST_HANDLER_ID,
    CORE_FIRING_DECK_HANDLER_ID,
    CORE_HAZARDOUS_HANDLER_ID,
    CORE_INFILTRATORS_HANDLER_ID,
    CORE_LEADER_HANDLER_ID,
    CORE_LONE_OPERATIVE_HANDLER_ID,
    CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID,
    CORE_SCOUTS_HANDLER_ID,
    CORE_STEALTH_HANDLER_ID,
    CORE_SUPPORT_HANDLER_ID,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityHandlerBinding,
    AbilityHandlerRegistry,
    AbilityResolutionResult,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    KeywordGate,
    ability_records_for_context,
    ability_records_for_context_from_index,
    default_ability_handler_registry,
    execute_abilities_from_index,
    movement_capability_flags_from_index,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    eleventh_edition_ability_catalog_records,
    eleventh_edition_ability_index,
    eleventh_edition_core_ability_catalog_records,
    eleventh_edition_core_ability_index,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.catalog_rule_consumption import (
    CatalogMovementTransitPermission,
    catalog_movement_transit_permissions_for_model,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.movement_legality import (
    MovementCapabilitySet,
    MovementLegalityContext,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_abilities as source_data,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def _record_by_ability_id(
    records: tuple[AbilityCatalogRecord, ...],
    ability_id: str,
) -> AbilityCatalogRecord:
    for record in records:
        if record.definition.ability_id == ability_id:
            return record
    raise AssertionError(f"missing ability_id {ability_id}")


def _all_source_keywords(records: tuple[AbilityCatalogRecord, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                keyword
                for record in records
                for keyword in record.definition.keyword_gate.required_keywords
            }
        )
    )


def _ability_record(
    ability_id: str,
    *,
    trigger_kind: TimingTriggerKind = TimingTriggerKind.ANY_PHASE,
    phase: BattlePhaseKind | None = None,
    handler_id: str = "record_only",
    source_kind: AbilitySourceKind = AbilitySourceKind.CORE,
    faction_id: str | None = None,
    detachment_id: str | None = None,
    datasheet_id: str | None = None,
    wargear_id: str | None = None,
    weapon_profile_id: str | None = None,
    required_keywords: tuple[str, ...] = (),
    required_input_keys: tuple[str, ...] = (),
    replay_payload: JsonValue = None,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"record:{ability_id}",
        definition=AbilityDefinition(
            ability_id=ability_id,
            name=ability_id.replace("-", " ").title(),
            source_id=f"source:{ability_id}",
            when_descriptor="test timing",
            effect_descriptor="test effect",
            restrictions_descriptor="test restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind, phase=phase),
            keyword_gate=KeywordGate(required_keywords=required_keywords),
            handler_id=handler_id,
            required_input_keys=required_input_keys,
            replay_payload=replay_payload,
        ),
        source_kind=source_kind,
        faction_id=faction_id,
        detachment_id=detachment_id,
        datasheet_id=datasheet_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile_id,
    )


def _context(
    *,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhaseKind | None = None,
    source_keywords: tuple[str, ...] = (),
    trigger_payload: JsonValue = None,
) -> AbilityExecutionContext:
    return AbilityExecutionContext(
        game_id="game-1",
        player_id="player-a",
        battle_round=1,
        phase=phase,
        active_player_id="player-a",
        trigger_kind=trigger_kind,
        source_keywords=source_keywords,
        trigger_payload=trigger_payload,
    )


def _muster_request(
    catalog: ArmyCatalog,
    *,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str = "intercessor-1",
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


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


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "AbilityCatalogRecord", "AbilityDefinition"]
__all__ += ["AbilityExecutionContext", "AbilityHandlerBinding", "AbilityHandlerRegistry"]
__all__ += ["AbilityResolutionResult", "AbilityResolutionStatus", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "Any", "ArmyCatalog", "ArmyMusterRequest"]
__all__ += ["CORE_DEADLY_DEMISE_HANDLER_ID", "CORE_DEEP_STRIKE_HANDLER_ID", "BattlePhaseKind"]
__all__ += ["CORE_FEEL_NO_PAIN_HANDLER_ID", "CORE_FIGHTS_FIRST_HANDLER_ID"]
__all__ += ["CORE_FIRING_DECK_HANDLER_ID", "CORE_HAZARDOUS_HANDLER_ID"]
__all__ += ["CORE_INFILTRATORS_HANDLER_ID", "CORE_LEADER_HANDLER_ID"]
__all__ += ["CORE_LONE_OPERATIVE_HANDLER_ID", "CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID"]
__all__ += ["CORE_SCOUTS_HANDLER_ID", "CORE_STEALTH_HANDLER_ID", "CORE_SUPPORT_HANDLER_ID"]
__all__ += ["CatalogMovementTransitPermission", "DetachmentSelection"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameLifecycleError", "JsonValue"]
__all__ += ["KeywordGate", "ModelDisplacementKind", "ModelProfileSelection"]
__all__ += ["MovementCapabilitySet", "MovementLegalityContext", "MovementMode"]
__all__ += ["MovementPhaseActionKind", "ObjectiveRuleScope", "RuleSourceText"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "RulesetDescriptor", "TimingTriggerKind"]
__all__ += ["UnitMusterSelection", "Wargear", "WeaponKeyword", "_ability_record"]
__all__ += ["_all_source_keywords", "_catalog_with_hazardous_bolt_rifle", "_context"]
__all__ += ["_muster_request", "_record_by_ability_id", "_unit_selection", "abilities_module"]
__all__ += ["ability_records_for_context", "ability_records_for_context_from_index"]
__all__ += ["build_player_ability_index", "cast"]
__all__ += ["catalog_movement_transit_permissions_for_model"]
__all__ += ["catalog_rule_ir_consumers_for_rule", "compile_rule_source_text"]
__all__ += ["datasheet_keyword_lexicon_source", "default_ability_handler_registry"]
__all__ += ["eleventh_edition_ability_catalog_records", "eleventh_edition_ability_index"]
__all__ += ["eleventh_edition_core_ability_catalog_records"]
__all__ += ["eleventh_edition_core_ability_index", "execute_abilities_from_index", "json"]
__all__ += ["movement_capability_flags_from_index", "muster_army", "pytest", "replace"]
__all__ += ["source_data"]
