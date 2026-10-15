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
        movement_mode=MovementMode.NORMAL,
        take_to_the_skies=True,
    )
    empty_capabilities = MovementCapabilitySet.from_keywords(
        ("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        take_to_the_skies=True,
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
        movement_mode=MovementMode.NORMAL,
        take_to_the_skies=True,
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
            objective_scope=ObjectiveRuleScope.CORE_RULES,
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
            objective_scope=ObjectiveRuleScope.CORE_RULES,
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
            objective_scope=ObjectiveRuleScope.CORE_RULES,
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
        context=_context(trigger_kind=TimingTriggerKind.AFTER_UNIT_ATTACKS_RESOLVED),
    )
    matching_keyword = registry.execute(
        record=hazardous,
        context=_context(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ATTACKS_RESOLVED,
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


def test_p24f_deadly_demise_handler_uses_model_destroyed_timing() -> None:
    deadly_demise = _record_by_ability_id(
        eleventh_edition_ability_catalog_records(),
        "core-deadly-demise",
    )
    registry = default_ability_handler_registry()
    unit_destroyed = registry.execute(
        record=deadly_demise,
        context=_context(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            source_keywords=("Deadly Demise",),
        ),
    )
    model_destroyed = registry.execute(
        record=deadly_demise,
        context=_context(
            trigger_kind=TimingTriggerKind.AFTER_MODEL_DESTROYED,
            source_keywords=("Deadly Demise",),
        ),
    )

    assert unit_destroyed.status is AbilityResolutionStatus.INVALID
    assert unit_destroyed.reason == "timing_window_mismatch"
    assert model_destroyed.status is AbilityResolutionStatus.APPLIED
    replay_payload = cast(dict[str, object], model_destroyed.replay_payload)
    assert replay_payload["trigger_kind"] == "after_model_destroyed"


@pytest.mark.parametrize(
    ("source_kind", "owner_fields", "message"),
    [
        (AbilitySourceKind.CORE, {"faction_id": "owned"}, "cannot own IDs"),
        (AbilitySourceKind.KEYWORD, {"wargear_id": "owned"}, "cannot own IDs"),
        (AbilitySourceKind.FACTION, {}, "requires faction_id"),
        (AbilitySourceKind.DETACHMENT, {}, "requires detachment_id"),
        (AbilitySourceKind.DATASHEET, {}, "requires datasheet_id"),
        (AbilitySourceKind.ENHANCEMENT, {}, "requires detachment_id"),
        (AbilitySourceKind.WARGEAR, {}, "requires wargear_id"),
        (AbilitySourceKind.WEAPON, {}, "requires weapon_profile_id or keyword gate"),
    ],
)
def test_ability_catalog_records_require_source_owned_identity(
    source_kind: AbilitySourceKind,
    owner_fields: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=message):
        cast(Any, _ability_record)("bad-owner", source_kind=source_kind, **owner_fields)


def test_ability_validation_helpers_cover_tokens_keywords_and_handler_context() -> None:
    assert abilities_module.ability_source_kind_from_token(AbilitySourceKind.CORE) is (
        AbilitySourceKind.CORE
    )
    assert (
        abilities_module.ability_resolution_status_from_token(AbilityResolutionStatus.APPLIED)
        is AbilityResolutionStatus.APPLIED
    )
    for converter in (
        abilities_module.ability_source_kind_from_token,
        abilities_module.ability_resolution_status_from_token,
    ):
        with pytest.raises(GameLifecycleError, match="must be a string"):
            converter(1)
        with pytest.raises(GameLifecycleError, match="Unsupported"):
            converter("not-supported")

    assert abilities_module._validate_optional_phase("phase", None) is None
    assert abilities_module._validate_optional_phase("phase", BattlePhaseKind.COMMAND) is (
        BattlePhaseKind.COMMAND
    )
    assert abilities_module._validate_optional_phase("phase", "shooting") is (
        BattlePhaseKind.SHOOTING
    )
    with pytest.raises(GameLifecycleError, match="phase is invalid"):
        abilities_module._validate_optional_phase("phase", "not-supported")
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        abilities_module._validate_keyword_tuple("keywords", ["INFANTRY"])
    with pytest.raises(GameLifecycleError, match="duplicate keywords"):
        abilities_module._validate_keyword_tuple("keywords", ("Deep Strike", "DEEP-STRIKE"))
    assert abilities_module._validate_keyword("keyword", "Deep Strike") == "DEEP_STRIKE"
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        abilities_module._validate_identifier_tuple("ids", ["id"])
    assert abilities_module._validate_optional_identifier("id", None) is None
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        abilities_module._validate_positive_int("count", True)
    with pytest.raises(GameLifecycleError, match="at least 1"):
        abilities_module._validate_positive_int("count", 0)
    with pytest.raises(GameLifecycleError, match="must be a bool"):
        abilities_module._validate_bool("flag", 1)

    timing = AbilityTimingDescriptor(
        trigger_kind=TimingTriggerKind.ANY_PHASE,
        phase=BattlePhaseKind.MOVEMENT,
        timing_window_id="window-a",
    )
    matching_context = replace(
        _context(trigger_kind=TimingTriggerKind.ANY_PHASE, phase=BattlePhaseKind.MOVEMENT),
        timing_window_id="window-a",
    )
    assert abilities_module._handler_timing_matches(
        timing=timing,
        context=matching_context,
    )
    assert not abilities_module._handler_timing_matches(
        timing=timing,
        context=replace(matching_context, phase=BattlePhaseKind.SHOOTING),
    )
    assert not abilities_module._handler_timing_matches(
        timing=timing,
        context=replace(matching_context, timing_window_id="window-b"),
    )
    with pytest.raises(GameLifecycleError, match="timing requires a descriptor"):
        abilities_module._handler_timing_matches(
            timing=cast(Any, object()), context=matching_context
        )
    with pytest.raises(GameLifecycleError, match="execution context"):
        abilities_module._handler_timing_matches(timing=timing, context=cast(Any, object()))

    assert (
        abilities_module._missing_required_input_keys(
            context=matching_context,
            required_input_keys=(),
        )
        == ()
    )
    assert abilities_module._missing_required_input_keys(
        context=matching_context,
        required_input_keys=("target",),
    ) == ("target",)
    payload_context = replace(matching_context, trigger_payload={"target": "unit-1"})
    assert abilities_module._missing_required_input_keys(
        context=payload_context,
        required_input_keys=("target", "mode"),
    ) == ("mode",)


def test_ability_result_identity_and_movement_payloads_fail_closed() -> None:
    record = _ability_record("result-contract")
    result = AbilityResolutionResult.applied(record)
    for field_name in ("record_id", "ability_id", "handler_id", "source_id"):
        with pytest.raises(GameLifecycleError, match="drift"):
            abilities_module._validate_result_matches_record(
                result=cast(Any, replace)(result, **{field_name: f"wrong:{field_name}"}),
                record=record,
            )

    with pytest.raises(GameLifecycleError, match="require an AbilityResolutionResult"):
        abilities_module.movement_capability_flags_from_result(cast(Any, object()))
    assert (
        abilities_module.movement_capability_flags_from_result(
            AbilityResolutionResult.unsupported(record, reason="not-applied")
        )
        == ()
    )
    invalid_payloads: tuple[JsonValue, ...] = (
        None,
        {},
        {"effect_payload": None},
        {"effect_payload": {}},
        {"effect_payload": {"movement_capability_flags": "FLY"}},
    )
    for payload in invalid_payloads:
        with pytest.raises(GameLifecycleError, match=r"payload|capability flags"):
            abilities_module.movement_capability_flags_from_result(
                AbilityResolutionResult.applied(record, replay_payload=payload)
            )
    payload = cast(
        JsonValue,
        {"effect_payload": {"movement_capability_flags": ["WALK", "FLY"]}},
    )
    assert abilities_module.movement_capability_flags_from_result(
        AbilityResolutionResult.applied(record, replay_payload=payload)
    ) == ("FLY", "WALK")


__all__: list[str] = []
__all__ += ["AbilityDefinition", "AbilityHandlerBinding", "ArmyMusterRequest"]
__all__ += ["CORE_DEADLY_DEMISE_HANDLER_ID", "CORE_DEEP_STRIKE_HANDLER_ID"]
__all__ += ["CORE_FEEL_NO_PAIN_HANDLER_ID", "CORE_FIGHTS_FIRST_HANDLER_ID"]
__all__ += ["CORE_FIRING_DECK_HANDLER_ID", "CORE_HAZARDOUS_HANDLER_ID"]
__all__ += ["CORE_INFILTRATORS_HANDLER_ID", "CORE_LEADER_HANDLER_ID"]
__all__ += ["CORE_LONE_OPERATIVE_HANDLER_ID", "CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID"]
__all__ += ["CORE_SCOUTS_HANDLER_ID", "CORE_STEALTH_HANDLER_ID", "CORE_SUPPORT_HANDLER_ID"]
__all__ += ["DetachmentSelection", "ModelProfileSelection", "UnitMusterSelection", "Wargear"]
__all__ += ["WeaponKeyword", "datasheet_keyword_lexicon_source"]
__all__ += ["eleventh_edition_core_ability_index", "json", "source_data"]
