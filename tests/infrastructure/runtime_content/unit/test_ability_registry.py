# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase12d_ability_registry import (
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
    SOURCE_KEYWORD_SEQUENCE_PARTS,
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
    ArmyCatalog,
    ArmyMusterRequest,
    BattlePhaseKind,
    CatalogMovementTransitPermission,
    DetachmentSelection,
    GameLifecycleError,
    JsonValue,
    KeywordGate,
    ModelDisplacementKind,
    ModelProfileSelection,
    MovementCapabilitySet,
    MovementLegalityContext,
    MovementMode,
    MovementPhaseActionKind,
    ObjectiveRuleScope,
    RulesetDescriptor,
    RuleSourceText,
    TimingTriggerKind,
    UnitMusterSelection,
    Wargear,
    WeaponKeyword,
    _ability_record,
    _all_source_keywords,
    _catalog_with_hazardous_bolt_rifle,
    _context,
    _muster_request,
    _record_by_ability_id,
    _unit_selection,
    abilities_module,
    ability_records_for_context,
    ability_records_for_context_from_index,
    build_player_ability_index,
    catalog_movement_transit_permissions_for_model,
    catalog_rule_ir_consumers_for_rule,
    compile_rule_source_text,
    datasheet_keyword_lexicon_source,
    default_ability_handler_registry,
    eleventh_edition_ability_catalog_records,
    eleventh_edition_ability_index,
    eleventh_edition_core_ability_catalog_records,
    eleventh_edition_core_ability_index,
    execute_abilities_from_index,
    json,
    movement_capability_flags_from_index,
    muster_army,
    pytest,
    replace,
    source_data,
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
    assert hazardous.definition.timing.trigger_kind is TimingTriggerKind.AFTER_UNIT_ATTACKS_RESOLVED
    assert deadly_demise.source_kind is AbilitySourceKind.CORE
    assert deadly_demise.definition.handler_id == CORE_DEADLY_DEMISE_HANDLER_ID
    assert deadly_demise.definition.timing.trigger_kind is TimingTriggerKind.AFTER_MODEL_DESTROYED
    assert deadly_demise.definition.when_descriptor.startswith(
        "Each time a model with this ability is destroyed"
    )
    assert "when this unit is destroyed" not in deadly_demise.definition.when_descriptor.lower()
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


def test_ability_registry_value_objects_fail_fast_on_invalid_owned_types() -> None:
    timing = AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE)
    definition = _ability_record("owned-types").definition

    with pytest.raises(GameLifecycleError, match="AbilityExecutionContext"):
        timing.matches(cast(AbilityExecutionContext, object()))
    with pytest.raises(GameLifecycleError, match="timing must be a descriptor"):
        replace(definition, timing=cast(AbilityTimingDescriptor, object()))
    with pytest.raises(GameLifecycleError, match="keyword_gate must be"):
        replace(definition, keyword_gate=cast(KeywordGate, object()))
    with pytest.raises(GameLifecycleError, match="definition must be"):
        AbilityCatalogRecord(
            record_id="record:bad-definition",
            definition=cast(AbilityDefinition, object()),
        )
    with pytest.raises(GameLifecycleError, match="disabled must be a bool"):
        replace(_ability_record("bad-disabled"), disabled=cast(bool, 1))
    with pytest.raises(GameLifecycleError, match="battle_round must be at least 1"):
        replace(_context(trigger_kind=TimingTriggerKind.ANY_PHASE), battle_round=0)
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        replace(
            _context(trigger_kind=TimingTriggerKind.ANY_PHASE),
            state=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="event_log must be an EventLog"):
        replace(
            _context(trigger_kind=TimingTriggerKind.ANY_PHASE),
            event_log=cast(Any, object()),
        )

    record = _ability_record("result-shape")
    with pytest.raises(GameLifecycleError, match=r"Applied.*must not include reason"):
        replace(AbilityResolutionResult.applied(record), reason="unexpected")
    with pytest.raises(GameLifecycleError, match=r"Non-applied.*requires reason"):
        AbilityResolutionResult(
            record_id=record.record_id,
            ability_id=record.definition.ability_id,
            handler_id=record.definition.handler_id,
            source_id=record.definition.source_id,
            status=AbilityResolutionStatus.INVALID,
        )


def test_ability_registry_collections_and_bindings_reject_ambiguous_shapes() -> None:
    record = _ability_record("collection")
    timing = AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE)

    def handler(
        handled_record: AbilityCatalogRecord,
        _context_value: AbilityExecutionContext,
    ) -> AbilityResolutionResult:
        return AbilityResolutionResult.applied(handled_record)

    binding = AbilityHandlerBinding(
        handler_id="test:handler",
        timing=timing,
        required_input_keys=(),
        handler=handler,
    )
    with pytest.raises(GameLifecycleError, match="cannot register unsupported"):
        replace(binding, handler_id="unsupported:test")
    with pytest.raises(GameLifecycleError, match="timing must be a descriptor"):
        replace(binding, timing=cast(AbilityTimingDescriptor, object()))
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        replace(binding, handler=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        AbilityHandlerRegistry.from_bindings(cast(Any, [binding]))
    with pytest.raises(GameLifecycleError, match="must contain AbilityHandlerBinding"):
        AbilityHandlerRegistry.from_bindings(cast(Any, (object(),)))
    with pytest.raises(GameLifecycleError, match="duplicate IDs"):
        AbilityHandlerRegistry.from_bindings((binding, binding))
    with pytest.raises(GameLifecycleError, match="records must be a tuple"):
        AbilityCatalogIndex.from_records(cast(Any, [record]))
    with pytest.raises(GameLifecycleError, match="AbilityCatalogRecord values"):
        AbilityCatalogIndex.from_records(cast(Any, (object(),)))
    with pytest.raises(GameLifecycleError, match="duplicate IDs"):
        AbilityCatalogIndex.from_records((record, record))
    with pytest.raises(GameLifecycleError, match="requires a TimingTriggerKind"):
        AbilityCatalogIndex.from_records((record,)).records_for(cast(Any, "any_phase"))


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "CatalogMovementTransitPermission"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "DetachmentSelection", "JsonValue"]
__all__ += ["ModelDisplacementKind", "ModelProfileSelection", "MovementCapabilitySet"]
__all__ += ["MovementLegalityContext", "MovementMode", "MovementPhaseActionKind"]
__all__ += ["ObjectiveRuleScope", "RuleSourceText", "RulesetDescriptor"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "UnitMusterSelection", "Wargear", "WeaponKeyword"]
__all__ += ["_all_source_keywords", "_catalog_with_hazardous_bolt_rifle", "_muster_request"]
__all__ += ["_unit_selection", "abilities_module", "ability_records_for_context"]
__all__ += ["ability_records_for_context_from_index", "build_player_ability_index"]
__all__ += ["catalog_movement_transit_permissions_for_model"]
__all__ += ["catalog_rule_ir_consumers_for_rule", "compile_rule_source_text"]
__all__ += ["datasheet_keyword_lexicon_source", "default_ability_handler_registry"]
__all__ += ["eleventh_edition_ability_catalog_records", "eleventh_edition_ability_index"]
__all__ += ["movement_capability_flags_from_index", "muster_army"]
