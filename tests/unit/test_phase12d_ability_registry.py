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


def test_source_backed_core_ability_rows_include_phase12d_families() -> None:
    rows = source_data.ability_rows()
    records = eleventh_edition_core_ability_catalog_records()
    payload = {
        "identity": source_data.source_package_identity_payload(),
        "rows": [row.to_payload() for row in rows],
    }
    blob = json.dumps(payload, sort_keys=True)
    ability_ids = {record.definition.ability_id for record in records}
    deep_strike = _record_by_ability_id(records, "core-deep-strike")
    firing_deck = _record_by_ability_id(records, "core-firing-deck")
    hazardous = _record_by_ability_id(records, "core-hazardous")
    deadly_demise = _record_by_ability_id(records, "core-deadly-demise")
    feel_no_pain = _record_by_ability_id(records, "core-feel-no-pain")
    infiltrators = _record_by_ability_id(records, "core-infiltrators")
    leader = _record_by_ability_id(records, "core-leader")
    fights_first = _record_by_ability_id(records, "core-fights-first")
    lone_operative = _record_by_ability_id(records, "core-lone-operative")
    scouts = _record_by_ability_id(records, "core-scouts")
    stealth = _record_by_ability_id(records, "core-stealth")
    support = _record_by_ability_id(records, "core-support")

    assert {
        "core-deadly-demise",
        "core-deep-strike",
        "core-feel-no-pain",
        "core-firing-deck",
        "core-fights-first",
        "core-hazardous",
        "core-infiltrators",
        "core-leader",
        "core-lone-operative",
        "core-scouts",
        "core-stealth",
        "core-support",
    }.issubset(ability_ids)
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert deep_strike.source_kind is AbilitySourceKind.DATASHEET
    assert deep_strike.datasheet_id == "core-deep-strike-unit"
    assert deep_strike.definition.keyword_gate.required_keywords == ("DEEP_STRIKE",)
    assert deep_strike.definition.handler_id == CORE_DEEP_STRIKE_HANDLER_ID
    assert firing_deck.source_kind is AbilitySourceKind.CORE
    assert firing_deck.definition.handler_id == CORE_FIRING_DECK_HANDLER_ID
    assert hazardous.source_kind is AbilitySourceKind.WEAPON
    assert hazardous.definition.handler_id == "core:hazardous"
    assert deadly_demise.source_kind is AbilitySourceKind.CORE
    assert deadly_demise.definition.handler_id == CORE_DEADLY_DEMISE_HANDLER_ID
    assert feel_no_pain.source_kind is AbilitySourceKind.CORE
    assert feel_no_pain.definition.handler_id == CORE_FEEL_NO_PAIN_HANDLER_ID
    assert infiltrators.source_kind is AbilitySourceKind.CORE
    assert infiltrators.definition.handler_id == CORE_INFILTRATORS_HANDLER_ID
    assert leader.source_kind is AbilitySourceKind.DATASHEET
    assert leader.datasheet_id == "core-character-leader"
    assert leader.definition.handler_id == CORE_LEADER_HANDLER_ID
    assert fights_first.source_kind is AbilitySourceKind.CORE
    assert fights_first.definition.handler_id == CORE_FIGHTS_FIRST_HANDLER_ID
    assert fights_first.definition.timing.phase is BattlePhaseKind.FIGHT
    assert lone_operative.source_kind is AbilitySourceKind.CORE
    assert lone_operative.definition.handler_id == CORE_LONE_OPERATIVE_HANDLER_ID
    assert scouts.source_kind is AbilitySourceKind.CORE
    assert scouts.definition.handler_id == CORE_SCOUTS_HANDLER_ID
    assert stealth.source_kind is AbilitySourceKind.CORE
    assert stealth.definition.handler_id == CORE_STEALTH_HANDLER_ID
    assert support.source_kind is AbilitySourceKind.DATASHEET
    assert support.datasheet_id == "core-character-support"
    assert support.definition.handler_id == CORE_SUPPORT_HANDLER_ID
    assert eleventh_edition_core_ability_index().all_records() == tuple(
        sorted(records, key=lambda record: record.record_id)
    )


def test_phase14i_core_ability_rows_are_supported() -> None:
    rows = source_data.ability_rows()
    supported_handler_ids = {
        CORE_DEEP_STRIKE_HANDLER_ID,
        CORE_DEADLY_DEMISE_HANDLER_ID,
        CORE_FEEL_NO_PAIN_HANDLER_ID,
        CORE_FIRING_DECK_HANDLER_ID,
        CORE_FIGHTS_FIRST_HANDLER_ID,
        CORE_HAZARDOUS_HANDLER_ID,
        CORE_INFILTRATORS_HANDLER_ID,
        CORE_LEADER_HANDLER_ID,
        CORE_LONE_OPERATIVE_HANDLER_ID,
        CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID,
        CORE_SCOUTS_HANDLER_ID,
        CORE_STEALTH_HANDLER_ID,
        CORE_SUPPORT_HANDLER_ID,
    }

    assert [
        row.ability_id
        for row in rows
        if row.handler_id not in supported_handler_ids
        and not row.handler_id.startswith("unsupported:")
    ] == []
    assert (
        tuple(
            (row.ability_id, row.handler_id)
            for row in rows
            if row.handler_id.startswith("unsupported:")
        )
        == ()
    )


def test_phase14i_phase_owned_core_keyword_rows_execute_through_supported_handlers() -> None:
    records = eleventh_edition_core_ability_catalog_records()
    registry = default_ability_handler_registry()
    rows: tuple[
        tuple[str, TimingTriggerKind, BattlePhaseKind | None, tuple[str, ...]],
        ...,
    ] = (
        (
            "core-deep-strike",
            TimingTriggerKind.BEFORE_BATTLE,
            None,
            ("DEEP_STRIKE",),
        ),
        (
            "core-firing-deck",
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.SHOOTING,
            ("FIRING_DECK",),
        ),
        (
            "core-infiltrators",
            TimingTriggerKind.BEFORE_BATTLE,
            None,
            ("INFILTRATORS",),
        ),
        (
            "core-leader",
            TimingTriggerKind.BEFORE_BATTLE,
            None,
            ("LEADER",),
        ),
        (
            "core-scouts",
            TimingTriggerKind.BEFORE_BATTLE,
            None,
            ("SCOUTS",),
        ),
        (
            "core-support",
            TimingTriggerKind.BEFORE_BATTLE,
            None,
            ("SUPPORT",),
        ),
    )

    for ability_id, trigger_kind, phase, source_keywords in rows:
        record = _record_by_ability_id(records, ability_id)
        result = registry.execute(
            record=record,
            context=_context(
                trigger_kind=trigger_kind,
                phase=phase,
                source_keywords=source_keywords,
            ),
        )
        replay_payload = cast(dict[str, object], result.replay_payload)

        assert result.status is AbilityResolutionStatus.APPLIED
        assert replay_payload["effect_payload"] == {
            "effect_kind": "source_registered_core_keyword",
            "resolved_by": "phase_host",
        }


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
    catalog = eleventh_edition_ability_catalog_records()
    index = eleventh_edition_ability_index()
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


def test_generic_rule_ir_handler_requires_registry_binding() -> None:
    generic_rule_ir = _ability_record(
        "generic-rule-ir",
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    )

    result = AbilityHandlerRegistry.empty().execute(
        record=generic_rule_ir,
        context=_context(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
    )

    assert result.status is AbilityResolutionStatus.UNSUPPORTED
    assert result.reason == "missing_handler"


def test_keyword_gated_movement_capabilities_are_dispatched_from_ability_index() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    full_index = eleventh_edition_ability_index()
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
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
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


def test_generic_rule_ir_movement_transit_permissions_are_consumed_by_model_context() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog,
            unit_selections=(
                _unit_selection(
                    unit_selection_id="transport-1",
                    datasheet_id="core-transport",
                    model_profile_id="core-transport",
                    model_count=1,
                ),
            ),
        ),
    )
    unit = army.units[0]
    model_instance_id = unit.own_models[0].model_instance_id
    current_model_instance_ids = unit.own_model_ids()
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase12d:test:move-over-friendly-monster-vehicle-terrain",
            raw_text=(
                "Each time this model makes a Normal or Advance move, it can move over "
                'friendly Monster and Vehicle models and terrain features that are 4" '
                "or less in height as if they were not there."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    matching_record = _ability_record(
        "semantic-move-over",
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=unit.datasheet_id,
        replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
    )
    mismatched_record = _ability_record(
        "semantic-move-over-mismatch",
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
        replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
    )
    matching_index = AbilityCatalogIndex.from_records(
        (*eleventh_edition_ability_catalog_records(), matching_record)
    )
    mismatched_index = AbilityCatalogIndex.from_records(
        (*eleventh_edition_ability_catalog_records(), mismatched_record)
    )
    direct_permissions = catalog_movement_transit_permissions_for_model(
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
        movement_mode=MovementMode.NORMAL.value,
    )

    normal_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )
    advance_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.ADVANCE,
        movement_phase_action=MovementPhaseActionKind.ADVANCE.value,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )
    fall_back_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.FALL_BACK,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )
    missing_model_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=None,
        current_model_instance_ids=current_model_instance_ids,
    )
    missing_evidence_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=(),
    )
    mismatched_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=mismatched_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )

    assert normal_context.capabilities.is_vehicle
    assert normal_context.capabilities.blocks_friendly_vehicle_monster_pass_through
    assert normal_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert normal_context.capabilities.terrain_as_if_absent_height_inches == 4.0
    assert advance_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert advance_context.capabilities.terrain_as_if_absent_height_inches == 4.0
    assert not fall_back_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert fall_back_context.capabilities.terrain_as_if_absent_height_inches is None
    assert mismatched_context.capabilities.is_vehicle
    assert not mismatched_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert mismatched_context.capabilities.terrain_as_if_absent_height_inches is None
    assert not missing_model_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert missing_model_context.capabilities.terrain_as_if_absent_height_inches is None
    assert not missing_evidence_context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert missing_evidence_context.capabilities.terrain_as_if_absent_height_inches is None
    assert len(direct_permissions) == 1
    assert direct_permissions[0].ability_id == "semantic-move-over"
    assert direct_permissions[0].movement_modes == ("advance", "normal")
    assert direct_permissions[0].model_keyword_any == ("MONSTER", "VEHICLE")
    assert direct_permissions[0].terrain_height_max_inches == 4.0
    with pytest.raises(GameLifecycleError, match="current evidence"):
        catalog_movement_transit_permissions_for_model(
            ability_index=matching_index,
            unit=unit,
            model_instance_id="missing-model",
            current_model_instance_ids=current_model_instance_ids,
            movement_mode=MovementMode.NORMAL.value,
        )
    assert (
        catalog_movement_transit_permissions_for_model(
            ability_index=matching_index,
            unit=unit,
            model_instance_id=model_instance_id,
            current_model_instance_ids=current_model_instance_ids,
            movement_mode=MovementMode.FALL_BACK.value,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="must not duplicate values"):
        CatalogMovementTransitPermission(
            record_id="record",
            ability_id="ability",
            source_rule_id="source",
            clause_id="clause",
            movement_modes=("normal", "normal"),
            model_keyword_any=("MONSTER", "VEHICLE"),
            terrain_height_max_inches=4.0,
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        CatalogMovementTransitPermission(
            record_id="record",
            ability_id="ability",
            source_rule_id="source",
            clause_id="clause",
            movement_modes=(),
            model_keyword_any=("MONSTER", "VEHICLE"),
            terrain_height_max_inches=4.0,
        )
    with pytest.raises(GameLifecycleError, match="finite and non-negative"):
        CatalogMovementTransitPermission(
            record_id="record",
            ability_id="ability",
            source_rule_id="source",
            clause_id="clause",
            movement_modes=("normal",),
            model_keyword_any=("MONSTER", "VEHICLE"),
            terrain_height_max_inches=-1.0,
        )


def test_generic_rule_ir_move_through_models_and_terrain_permissions_are_consumed() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog,
            unit_selections=(
                _unit_selection(
                    unit_selection_id="transport-1",
                    datasheet_id="core-transport",
                    model_profile_id="core-transport",
                    model_count=1,
                ),
            ),
        ),
    )
    unit = army.units[0]
    model_instance_id = unit.own_models[0].model_instance_id
    current_model_instance_ids = unit.own_model_ids()
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase12d:test:move-through-models-terrain-auto-pass",
            raw_text=(
                "Each time this unit makes a Normal, Advance or Fall Back move, it can move "
                "through models (excluding Titanic models) and terrain features. When doing so, "
                "it can move within Engagement Range of enemy models, but cannot end that move "
                "within Engagement Range of them, and any Desperate Escape test is automatically "
                "passed."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    matching_record = _ability_record(
        "semantic-move-through-models-terrain",
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=unit.datasheet_id,
        replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
    )
    matching_index = AbilityCatalogIndex.from_records(
        (*eleventh_edition_ability_catalog_records(), matching_record)
    )
    direct_permissions = catalog_movement_transit_permissions_for_model(
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
        movement_mode=MovementMode.FALL_BACK.value,
    )
    fall_back_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.FALL_BACK,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )
    normal_context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        ability_index=matching_index,
        unit=unit,
        model_instance_id=model_instance_id,
        current_model_instance_ids=current_model_instance_ids,
    )

    assert len(direct_permissions) == 2
    assert tuple(permission.permission for permission in direct_permissions) == (
        "move_through_models",
        "move_through_terrain_features",
    )
    assert direct_permissions[0].excluded_model_keyword_any == ("TITANIC",)
    assert direct_permissions[0].enemy_engagement_range_transit
    assert direct_permissions[0].desperate_escape_tests_auto_passed
    for context in (fall_back_context, normal_context):
        assert context.capabilities.can_move_through_models
        assert context.capabilities.can_move_through_friendly_models
        assert context.capabilities.can_move_through_enemy_models
        assert context.capabilities.can_move_through_terrain
        assert context.capabilities.can_transit_enemy_engagement_range
        assert context.capabilities.enemy_model_transit_blocker_keywords == ("TITANIC",)
        assert context.capabilities.friendly_model_transit_blocker_keywords == ("TITANIC",)
        assert context.capabilities.desperate_escape_tests_auto_passed


def test_malformed_passive_query_movement_transit_ir_fails_closed_at_runtime() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog,
            unit_selections=(
                _unit_selection(
                    unit_selection_id="transport-1",
                    datasheet_id="core-transport",
                    model_profile_id="core-transport",
                    model_count=1,
                ),
            ),
        ),
    )
    unit = army.units[0]
    model_instance_id = unit.own_models[0].model_instance_id
    current_model_instance_ids = unit.own_model_ids()
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase12d:test:malformed-move-over-friendly-monster-vehicle-terrain",
            raw_text=(
                "Each time this model makes a Normal or Advance move, it can move over "
                'friendly Monster and Vehicle models and terrain features that are 4" '
                "or less in height as if they were not there."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    clause = rule_ir.clauses[0]
    malformed_rule_irs = (
        replace(rule_ir, clauses=(replace(clause, target=None),)),
        replace(rule_ir, clauses=(replace(clause, trigger=None),)),
    )

    for index, malformed_rule_ir in enumerate(malformed_rule_irs, start=1):
        record = _ability_record(
            f"malformed-semantic-move-over-{index}",
            trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            source_kind=AbilitySourceKind.DATASHEET,
            datasheet_id=unit.datasheet_id,
            replay_payload=cast(JsonValue, {"rule_ir": malformed_rule_ir.to_payload()}),
        )
        ability_index = AbilityCatalogIndex.from_records(
            (*eleventh_edition_ability_catalog_records(), record)
        )
        direct_permissions = catalog_movement_transit_permissions_for_model(
            ability_index=ability_index,
            unit=unit,
            model_instance_id=model_instance_id,
            current_model_instance_ids=current_model_instance_ids,
            movement_mode=MovementMode.NORMAL.value,
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=unit.keywords,
            ruleset_descriptor=descriptor,
            movement_mode=MovementMode.NORMAL,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            ability_index=ability_index,
            unit=unit,
            model_instance_id=model_instance_id,
            current_model_instance_ids=current_model_instance_ids,
        )

        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert direct_permissions == ()
        assert not legality_context.capabilities.can_move_over_friendly_vehicle_monster_models
        assert legality_context.capabilities.terrain_as_if_absent_height_inches is None


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
    records = eleventh_edition_ability_catalog_records()
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
    hazardous = _record_by_ability_id(eleventh_edition_ability_catalog_records(), "core-hazardous")
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
    assert matching_keyword.status is AbilityResolutionStatus.APPLIED
    replay_payload = cast(dict[str, object], matching_keyword.replay_payload)
    assert replay_payload["effect_payload"] == {
        "effect_kind": "hazardous_weapon_test",
        "resolved_by": "attack_sequence",
    }
    assert replay_payload["source_keywords"] == ["HAZARDOUS"]


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
            detachment_ids=("core-combined-arms",),
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
