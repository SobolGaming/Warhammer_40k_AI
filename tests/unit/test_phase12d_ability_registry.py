from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.abilities import (
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
    tenth_edition_ability_catalog_records,
    tenth_edition_ability_index,
    tenth_edition_core_ability_catalog_records,
    tenth_edition_core_ability_index,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_legality import (
    MovementCapabilitySet,
    MovementLegalityContext,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_10th import (
    core_abilities as source_data,
)


def test_source_backed_core_ability_rows_include_phase12d_families() -> None:
    rows = source_data.ability_rows()
    records = tenth_edition_core_ability_catalog_records()
    payload = {
        "identity": source_data.source_package_identity_payload(),
        "rows": [row.to_payload() for row in rows],
    }
    blob = json.dumps(payload, sort_keys=True)
    ability_ids = {record.definition.ability_id for record in records}
    deep_strike = _record_by_ability_id(records, "core-deep-strike")
    hazardous = _record_by_ability_id(records, "core-hazardous")

    assert {
        "core-deadly-demise",
        "core-deep-strike",
        "core-feel-no-pain",
        "core-firing-deck",
        "core-hazardous",
        "core-infiltrators",
        "core-leader",
        "core-lone-operative",
        "core-scouts",
        "core-stealth",
    }.issubset(ability_ids)
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert deep_strike.source_kind is AbilitySourceKind.DATASHEET
    assert deep_strike.datasheet_id == "core-deep-strike-unit"
    assert deep_strike.definition.keyword_gate.required_keywords == ("DEEP_STRIKE",)
    assert deep_strike.definition.handler_id == "unsupported:phase-15b:deep-strike"
    assert hazardous.source_kind is AbilitySourceKind.WEAPON
    assert hazardous.definition.handler_id == "unsupported:phase-13d:hazardous"
    assert tenth_edition_core_ability_index().all_records() == tuple(
        sorted(records, key=lambda record: record.record_id)
    )


def test_ability_catalog_index_partitions_by_trigger_and_rejects_invalid_inputs() -> None:
    start_alpha = _ability_record("start-alpha", trigger_kind=TimingTriggerKind.START_PHASE)
    start_zulu = _ability_record("start-zulu", trigger_kind=TimingTriggerKind.START_PHASE)
    after_dice = _ability_record("after-dice", trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL)
    catalog = (start_zulu, after_dice, start_alpha)
    index = AbilityCatalogIndex.from_records(catalog)

    assert index == AbilityCatalogIndex.from_records(catalog)
    assert index.all_records() == tuple(sorted(catalog, key=lambda record: record.record_id))
    assert index.records_for(TimingTriggerKind.START_PHASE) == (start_alpha, start_zulu)
    assert index.records_for(TimingTriggerKind.AFTER_DICE_ROLL) == (after_dice,)
    assert index.records_for(TimingTriggerKind.END_TURN) == ()

    with pytest.raises(GameLifecycleError, match="duplicate IDs"):
        AbilityCatalogIndex.from_records((start_alpha, start_alpha))
    with pytest.raises(GameLifecycleError, match="AbilityCatalogRecord values"):
        AbilityCatalogIndex.from_records(cast(tuple[AbilityCatalogRecord, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="requires a TimingTriggerKind"):
        index.records_for(cast(TimingTriggerKind, "start_phase"))
    with pytest.raises(GameLifecycleError, match="requires an AbilityCatalogIndex"):
        ability_records_for_context_from_index(
            index=cast(AbilityCatalogIndex, object()),
            context=_context(trigger_kind=TimingTriggerKind.START_PHASE),
        )
    with pytest.raises(GameLifecycleError, match="keywords cannot be both"):
        KeywordGate(required_keywords=("Fly",), forbidden_keywords=("FLY",))


def test_ability_index_lookup_is_equivalent_to_full_tuple_scan_for_real_catalog() -> None:
    catalog = tenth_edition_ability_catalog_records()
    index = tenth_edition_ability_index()
    all_source_keywords = _all_source_keywords(catalog)
    phase_by_trigger = {
        TimingTriggerKind.START_PHASE: BattlePhaseKind.SHOOTING,
        TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET: BattlePhaseKind.SHOOTING,
    }

    assert index.all_records() == tuple(sorted(catalog, key=lambda record: record.record_id))
    for trigger_kind in TimingTriggerKind:
        context = _context(
            trigger_kind=trigger_kind,
            phase=phase_by_trigger.get(trigger_kind),
            source_keywords=all_source_keywords,
        )
        assert ability_records_for_context_from_index(index=index, context=context) == (
            ability_records_for_context(records=catalog, context=context)
        )


def test_registry_executes_only_opted_in_bucket_and_rejects_unsupported_handlers() -> None:
    supported = _ability_record(
        "supported",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        handler_id="test:apply",
        required_keywords=("Fly",),
        required_input_keys=("roll_id",),
    )
    unsupported = _ability_record(
        "unsupported",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        handler_id="unsupported:phase-x:future",
        required_keywords=("Fly",),
    )
    wrong_trigger = _ability_record(
        "wrong-trigger",
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler_id="test:apply",
        required_keywords=("Fly",),
    )
    index = AbilityCatalogIndex.from_records((wrong_trigger, unsupported, supported))

    def handler(
        record: AbilityCatalogRecord,
        context: AbilityExecutionContext,
    ) -> AbilityResolutionResult:
        return AbilityResolutionResult.applied(
            record,
            replay_payload={
                "source_keywords": list(context.source_keywords),
                "trigger_payload": context.trigger_payload,
            },
        )

    registry = AbilityHandlerRegistry.empty().with_handler(
        handler_id="test:apply",
        timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
        handler=handler,
        required_input_keys=("event_id",),
    )
    missing_input = _context(
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        source_keywords=("FLY",),
    )
    valid_context = _context(
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        source_keywords=("FLY",),
        trigger_payload={"roll_id": "roll-1", "event_id": "event-1"},
    )

    assert tuple(
        record.record_id for record in index.records_for(TimingTriggerKind.START_PHASE)
    ) == (wrong_trigger.record_id,)
    invalid_results = execute_abilities_from_index(
        registry=registry,
        index=index,
        context=missing_input,
    )
    assert tuple(result.status for result in invalid_results) == (
        AbilityResolutionStatus.INVALID,
        AbilityResolutionStatus.UNSUPPORTED,
    )
    assert invalid_results[0].reason == "missing_input:roll_id,event_id"
    valid_results = execute_abilities_from_index(
        registry=registry,
        index=index,
        context=valid_context,
    )
    assert tuple(result.status for result in valid_results) == (
        AbilityResolutionStatus.APPLIED,
        AbilityResolutionStatus.UNSUPPORTED,
    )
    assert valid_results[0].replay_payload == {
        "source_keywords": ["FLY"],
        "trigger_payload": {"roll_id": "roll-1", "event_id": "event-1"},
    }
    assert valid_results[1].reason == "unsupported_handler"

    duplicate_binding = AbilityHandlerBinding(
        handler_id="test:duplicate",
        timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
        required_input_keys=(),
        handler=handler,
    )
    with pytest.raises(GameLifecycleError, match="duplicate IDs"):
        AbilityHandlerRegistry.from_bindings((duplicate_binding, duplicate_binding))
    with pytest.raises(GameLifecycleError, match="cannot register unsupported"):
        registry.with_handler(
            handler_id="unsupported:bad",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
            handler=handler,
        )


def test_keyword_gated_movement_capabilities_are_dispatched_from_ability_index() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    full_index = tenth_edition_ability_index()
    empty_index = AbilityCatalogIndex.from_records(())
    capabilities = MovementCapabilitySet.from_keywords(
        ("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
    )
    empty_capabilities = MovementCapabilitySet.from_keywords(
        ("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
        ability_index=empty_index,
    )

    assert movement_capability_flags_from_index(
        index=full_index,
        keywords=("Fly", "Infantry"),
    ) == ("can_traverse_ruins_walls", "has_fly", "is_infantry")
    assert (
        movement_capability_flags_from_index(
            index=full_index,
            keywords=("Fly", "Infantry"),
            registry=AbilityHandlerRegistry.empty(),
        )
        == ()
    )
    assert capabilities.has_fly
    assert capabilities.is_infantry
    assert capabilities.can_move_through_models
    assert capabilities.can_traverse_ruins_walls
    assert not empty_capabilities.has_fly
    assert not empty_capabilities.can_traverse_ruins_walls
    assert empty_capabilities.keywords == ("FLY", "INFANTRY")
    missing_handler_capabilities = MovementCapabilitySet.from_keywords(
        ("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
        ability_registry=AbilityHandlerRegistry.empty(),
    )
    assert not missing_handler_capabilities.has_fly
    assert not missing_handler_capabilities.can_traverse_ruins_walls
    legality_context = MovementLegalityContext.from_keywords(
        keywords=("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=empty_index,
    )
    assert not legality_context.capabilities.has_fly

    registry_results = execute_abilities_from_index(
        registry=default_ability_handler_registry(),
        index=full_index,
        context=AbilityExecutionContext.passive_keyword_gate(source_keywords=("Vehicle",)),
    )
    assert len(registry_results) == 1
    assert registry_results[0].status is AbilityResolutionStatus.APPLIED
    assert registry_results[0].source_id.endswith(":keyword-vehicle")


def test_player_ability_index_filters_selected_sources() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog,
            unit_selections=(
                _unit_selection(),
                _unit_selection(
                    unit_selection_id="leader-1",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
                _unit_selection(
                    unit_selection_id="deep-1",
                    datasheet_id="core-deep-strike-unit",
                    model_profile_id="core-deep-strike-model",
                    model_count=3,
                ),
            ),
        ),
    )
    matching = (
        _ability_record("core-any"),
        _ability_record(
            "faction-match",
            source_kind=AbilitySourceKind.FACTION,
            faction_id="core-marine-force",
        ),
        _ability_record(
            "detachment-match",
            source_kind=AbilitySourceKind.DETACHMENT,
            detachment_id="core-combined-arms",
        ),
        _ability_record(
            "datasheet-match",
            source_kind=AbilitySourceKind.DATASHEET,
            datasheet_id="core-deep-strike-unit",
            required_keywords=("Deep Strike",),
        ),
        _ability_record(
            "wargear-match",
            source_kind=AbilitySourceKind.WARGEAR,
            wargear_id="core-bolt-rifle",
        ),
        _ability_record(
            "weapon-match",
            source_kind=AbilitySourceKind.WEAPON,
            weapon_profile_id="core-bolt-rifle:standard",
        ),
    )
    non_matching = (
        _ability_record(
            "faction-miss",
            source_kind=AbilitySourceKind.FACTION,
            faction_id="other-faction",
        ),
        _ability_record(
            "detachment-miss",
            source_kind=AbilitySourceKind.DETACHMENT,
            detachment_id="other-detachment",
        ),
        _ability_record(
            "datasheet-miss",
            source_kind=AbilitySourceKind.DATASHEET,
            datasheet_id="core-transport",
        ),
        _ability_record(
            "wargear-miss",
            source_kind=AbilitySourceKind.WARGEAR,
            wargear_id="missing-wargear",
        ),
        _ability_record(
            "weapon-miss",
            source_kind=AbilitySourceKind.WEAPON,
            weapon_profile_id="missing-profile",
        ),
        _ability_record("keyword-miss", required_keywords=("Scouts",)),
    )
    index = build_player_ability_index((*matching, *non_matching), army=army, catalog=catalog)

    assert tuple(record.definition.ability_id for record in index.all_records()) == tuple(
        sorted(record.definition.ability_id for record in matching)
    )


def test_player_index_retains_source_backed_weapon_keyword_records() -> None:
    records = tenth_edition_ability_catalog_records()
    normal_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    normal_army = muster_army(
        catalog=normal_catalog,
        request=_muster_request(normal_catalog, unit_selections=(_unit_selection(),)),
    )
    normal_index = build_player_ability_index(records, army=normal_army, catalog=normal_catalog)
    hazardous_catalog = _catalog_with_hazardous_bolt_rifle(normal_catalog)
    hazardous_army = muster_army(
        catalog=hazardous_catalog,
        request=_muster_request(hazardous_catalog, unit_selections=(_unit_selection(),)),
    )
    hazardous_index = build_player_ability_index(
        records,
        army=hazardous_army,
        catalog=hazardous_catalog,
    )
    profile_specific = _ability_record(
        "selected-profile",
        source_kind=AbilitySourceKind.WEAPON,
        weapon_profile_id="core-bolt-rifle:standard",
    )
    unselected_profile = _ability_record(
        "unselected-profile",
        source_kind=AbilitySourceKind.WEAPON,
        weapon_profile_id="missing-profile",
    )
    profile_index = build_player_ability_index(
        (unselected_profile, profile_specific),
        army=normal_army,
        catalog=normal_catalog,
    )

    assert "core-hazardous" not in {
        record.definition.ability_id for record in normal_index.all_records()
    }
    assert "core-hazardous" in {
        record.definition.ability_id for record in hazardous_index.all_records()
    }
    assert tuple(record.definition.ability_id for record in profile_index.all_records()) == (
        "selected-profile",
    )


def test_weapon_ability_execution_enforces_weapon_event_keywords() -> None:
    hazardous = _record_by_ability_id(tenth_edition_ability_catalog_records(), "core-hazardous")
    registry = default_ability_handler_registry()
    missing_keyword = registry.execute(
        record=hazardous,
        context=_context(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
    )
    matching_keyword = registry.execute(
        record=hazardous,
        context=_context(
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_keywords=("Hazardous",),
        ),
    )

    assert missing_keyword.status is AbilityResolutionStatus.INVALID
    assert missing_keyword.reason == "keyword_gate_closed"
    assert matching_keyword.status is AbilityResolutionStatus.UNSUPPORTED
    assert matching_keyword.reason == "unsupported_handler"


def test_ability_records_context_and_results_round_trip_as_json_payloads() -> None:
    record = _ability_record(
        "payload",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-deep-strike-unit",
        handler_id="unsupported:future",
        required_keywords=("Deep Strike",),
        replay_payload={"source": "test"},
    )
    context = _context(
        trigger_kind=TimingTriggerKind.BEFORE_BATTLE,
        source_keywords=("Deep Strike",),
        trigger_payload={"setup_step": "declare_reserves"},
    )
    result = AbilityResolutionResult.unsupported(record, reason="unsupported_handler")
    encoded = json.dumps(
        {
            "record": record.to_payload(),
            "context": context.to_payload(),
            "result": result.to_payload(),
        },
        sort_keys=True,
    )

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert AbilityCatalogRecord.from_payload(record.to_payload()) == record
    assert AbilityExecutionContext.from_payload(context.to_payload()) == context
    assert AbilityResolutionResult.from_payload(result.to_payload()) == result


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
            detachment_id="core-combined-arms",
        ),
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
