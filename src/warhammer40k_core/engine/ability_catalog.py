from __future__ import annotations

from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    KeywordGate,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_abilities as source_data,
)

ELEVENTH_EDITION_CORE_ABILITY_SOURCE_PACKAGE_ID = source_data.SOURCE_PACKAGE_ID


def eleventh_edition_core_ability_catalog_records() -> tuple[AbilityCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.core_ability_rows())


def eleventh_edition_core_ability_index() -> AbilityCatalogIndex:
    return AbilityCatalogIndex.from_records(eleventh_edition_core_ability_catalog_records())


def eleventh_edition_ability_catalog_records() -> tuple[AbilityCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.ability_rows())


def eleventh_edition_ability_index() -> AbilityCatalogIndex:
    return AbilityCatalogIndex.from_records(eleventh_edition_ability_catalog_records())


def catalog_ability_records_from_catalog(catalog: ArmyCatalog) -> tuple[AbilityCatalogRecord, ...]:
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Catalog ability record build requires an ArmyCatalog.")
    records: list[AbilityCatalogRecord] = []
    for datasheet in catalog.datasheets:
        for descriptor in datasheet.abilities:
            if descriptor.support is not CatalogAbilitySupport.GENERIC_RULE_IR:
                continue
            records.extend(
                _catalog_records_from_descriptor(
                    catalog=catalog,
                    datasheet_id=datasheet.datasheet_id,
                    descriptor=descriptor,
                )
            )
    return tuple(sorted(records, key=lambda record: record.record_id))


def build_player_ability_index(
    records: tuple[AbilityCatalogRecord, ...],
    *,
    army: ArmyDefinition,
    catalog: ArmyCatalog | None = None,
) -> AbilityCatalogIndex:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Player Ability index requires an ArmyDefinition.")
    if catalog is not None and type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Player Ability index catalog must be an ArmyCatalog.")
    validated_records = AbilityCatalogIndex.from_records(records).all_records()
    selected_datasheet_ids = frozenset(unit.datasheet_id for unit in army.units)
    selected_wargear_ids = _selected_unit_wargear_ids(army)
    selected_weapon_profile_ids = (
        _selected_weapon_profile_ids(catalog=catalog, wargear_ids=selected_wargear_ids)
        if catalog is not None
        else frozenset[str]()
    )
    selected_weapon_keywords = (
        _selected_weapon_keywords(catalog=catalog, wargear_ids=selected_wargear_ids)
        if catalog is not None
        else frozenset[str]()
    )

    player_records: list[AbilityCatalogRecord] = []
    for record in validated_records:
        if not _record_source_matches_player(
            record=record,
            army=army,
            selected_datasheet_ids=selected_datasheet_ids,
            selected_wargear_ids=selected_wargear_ids,
            selected_weapon_profile_ids=selected_weapon_profile_ids,
            selected_weapon_keywords=selected_weapon_keywords,
            has_weapon_profile_context=catalog is not None,
        ):
            continue
        if not _record_keyword_gate_matches_player(
            record=record,
            army=army,
            selected_weapon_keywords=selected_weapon_keywords,
        ):
            continue
        player_records.append(record)
    return AbilityCatalogIndex.from_records(tuple(player_records))


def _selected_unit_wargear_ids(army: ArmyDefinition) -> frozenset[str]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Selected wargear lookup requires an ArmyDefinition.")
    return frozenset(
        wargear_id
        for unit in army.units
        for model in unit.own_models
        for wargear_id in model.wargear_ids
    )


def _record_from_source_row(row: source_data.SourceAbilityRow) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"{source_data.SOURCE_PACKAGE_ID}:{row.source_kind}:{row.ability_id}",
        definition=AbilityDefinition(
            ability_id=row.ability_id,
            name=row.name,
            source_id=row.source_id,
            when_descriptor=row.when_descriptor,
            effect_descriptor=row.effect_descriptor,
            restrictions_descriptor=row.restrictions_descriptor,
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind(row.trigger_kind),
                phase=None if row.phase is None else battle_phase_kind_from_token(row.phase),
            ),
            keyword_gate=KeywordGate(
                required_keywords=row.required_keywords,
                forbidden_keywords=row.forbidden_keywords,
            ),
            handler_id=row.handler_id,
            required_input_keys=row.required_input_keys,
            replay_payload=validate_json_value(row.effect_payload),
        ),
        source_kind=AbilitySourceKind(row.source_kind),
        faction_id=row.faction_id,
        detachment_id=row.detachment_id,
        datasheet_id=row.datasheet_id,
        wargear_id=row.wargear_id,
        weapon_profile_id=row.weapon_profile_id,
        disabled=row.disabled,
    )


def _catalog_records_from_descriptor(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    descriptor: DatasheetAbilityDescriptor,
) -> tuple[AbilityCatalogRecord, ...]:
    if descriptor.rule_ir_payload is None:
        raise GameLifecycleError("Catalog generic rule ability descriptor is missing rule_ir.")
    try:
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload))
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog generic rule ability descriptor has invalid IR.") from exc
    if len(rule_ir.clauses) == 1:
        return (
            _catalog_record_from_rule_ir(
                catalog=catalog,
                datasheet_id=datasheet_id,
                descriptor=descriptor,
                rule_ir=rule_ir,
                clause=None,
            ),
        )
    return tuple(
        _catalog_record_from_rule_ir(
            catalog=catalog,
            datasheet_id=datasheet_id,
            descriptor=descriptor,
            rule_ir=rule_ir,
            clause=clause,
        )
        for clause in rule_ir.clauses
    )


def _catalog_record_from_rule_ir(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    descriptor: DatasheetAbilityDescriptor,
    rule_ir: RuleIR,
    clause: RuleClause | None,
) -> AbilityCatalogRecord:
    replay_payload: dict[str, object] = {"rule_ir": rule_ir.to_payload()}
    if clause is not None:
        replay_payload["runtime_clause_id"] = clause.clause_id
    return AbilityCatalogRecord(
        record_id=_catalog_record_id(
            catalog=catalog,
            datasheet_id=datasheet_id,
            descriptor=descriptor,
            clause=clause,
        ),
        definition=AbilityDefinition(
            ability_id=descriptor.ability_id,
            name=descriptor.name,
            source_id=descriptor.source_id,
            when_descriptor=_catalog_when_descriptor(descriptor),
            effect_descriptor=descriptor.effect_description,
            restrictions_descriptor=_catalog_restrictions_descriptor(descriptor),
            timing=(
                _catalog_timing_descriptor(rule_ir)
                if clause is None
                else _catalog_timing_descriptor_for_clause(clause)
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(replay_payload),
        ),
        source_kind=_catalog_ability_source_kind(descriptor.source_kind),
        datasheet_id=datasheet_id,
        wargear_id=descriptor.source_wargear_id,
    )


def _catalog_record_id(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    descriptor: DatasheetAbilityDescriptor,
    clause: RuleClause | None,
) -> str:
    base_id = f"{catalog.source_package_id}:catalog-ability:{datasheet_id}:{descriptor.ability_id}"
    if clause is None:
        return base_id
    return f"{base_id}:{clause.clause_id}"


def _catalog_ability_source_kind(source_kind: CatalogAbilitySourceKind) -> AbilitySourceKind:
    if source_kind is CatalogAbilitySourceKind.DATASHEET:
        return AbilitySourceKind.DATASHEET
    if source_kind is CatalogAbilitySourceKind.WARGEAR:
        return AbilitySourceKind.WARGEAR
    raise GameLifecycleError("Catalog generic rule ability source kind is unsupported.")


def _catalog_timing_descriptor(rule_ir: RuleIR) -> AbilityTimingDescriptor:
    for clause in rule_ir.clauses:
        setup_reactive_timing = _catalog_setup_reactive_timing_descriptor_for_clause(clause)
        if setup_reactive_timing is not None:
            return setup_reactive_timing
    for clause in rule_ir.clauses:
        charge_move_timing = _catalog_charge_move_end_timing_descriptor_for_clause(clause)
        if charge_move_timing is not None:
            return charge_move_timing
    for clause in rule_ir.clauses:
        fall_back_timing = _catalog_fall_back_selection_timing_descriptor_for_clause(clause)
        if fall_back_timing is not None:
            return fall_back_timing
    for clause in rule_ir.clauses:
        post_shoot_timing = _catalog_post_shoot_timing_descriptor_for_clause(clause)
        if post_shoot_timing is not None:
            return post_shoot_timing
    for clause in rule_ir.clauses:
        battle_round_timing = _catalog_battle_round_timing_descriptor_for_clause(clause)
        if battle_round_timing is not None:
            return battle_round_timing
    for clause in rule_ir.clauses:
        fight_selected_timing = _catalog_fight_selected_timing_descriptor_for_clause(clause)
        if fight_selected_timing is not None:
            return fight_selected_timing
    for clause in rule_ir.clauses:
        phase_timing = _catalog_phase_timing_descriptor_for_clause(clause)
        if phase_timing is not None:
            return phase_timing
    turn_timing = _catalog_turn_timing_descriptor(rule_ir)
    if turn_timing is not None:
        return turn_timing
    if any(
        _effect_is_passive_rule_exception_grant(effect)
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        clause.trigger is None
        and any(effect.kind is RuleEffectKind.GRANT_ABILITY for effect in clause.effects)
        for clause in rule_ir.clauses
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        _effect_is_shadow_of_chaos_status(effect)
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        effect.kind in {RuleEffectKind.MODIFY_CHARACTERISTIC, RuleEffectKind.SET_CHARACTERISTIC}
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        effect.kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        _effect_is_feel_no_pain_grant(effect)
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        clause.trigger is None
        and any(effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY for effect in clause.effects)
        for clause in rule_ir.clauses
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        effect.kind
        in {
            RuleEffectKind.MODIFY_DICE_ROLL,
            RuleEffectKind.REROLL_PERMISSION,
        }
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL)
    return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE)


def _catalog_timing_descriptor_for_clause(clause: RuleClause) -> AbilityTimingDescriptor:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog timing descriptor requires a RuleClause.")
    setup_reactive_timing = _catalog_setup_reactive_timing_descriptor_for_clause(clause)
    if setup_reactive_timing is not None:
        return setup_reactive_timing
    charge_move_timing = _catalog_charge_move_end_timing_descriptor_for_clause(clause)
    if charge_move_timing is not None:
        return charge_move_timing
    fall_back_timing = _catalog_fall_back_selection_timing_descriptor_for_clause(clause)
    if fall_back_timing is not None:
        return fall_back_timing
    post_shoot_timing = _catalog_post_shoot_timing_descriptor_for_clause(clause)
    if post_shoot_timing is not None:
        return post_shoot_timing
    if _clause_has_turn_end_reserve_permission(clause):
        turn_timing = _catalog_turn_timing_descriptor_for_clause(clause)
        if turn_timing is not None:
            return turn_timing
    battle_round_timing = _catalog_battle_round_timing_descriptor_for_clause(clause)
    if battle_round_timing is not None:
        return battle_round_timing
    fight_selected_timing = _catalog_fight_selected_timing_descriptor_for_clause(clause)
    if fight_selected_timing is not None:
        return fight_selected_timing
    phase_timing = _catalog_phase_timing_descriptor_for_clause(clause)
    if phase_timing is not None:
        return phase_timing
    if clause.trigger is not None and clause.trigger.kind in {
        RuleTriggerKind.UNIT_DESTROYED,
        RuleTriggerKind.MODEL_DESTROYED,
    }:
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED)
    if any(
        _effect_is_passive_rule_exception_grant(effect)
        or _effect_is_shadow_of_chaos_status(effect)
        or _effect_is_feel_no_pain_grant(effect)
        or effect.kind in {RuleEffectKind.MODIFY_CHARACTERISTIC, RuleEffectKind.SET_CHARACTERISTIC}
        or effect.kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if clause.trigger is None and any(
        effect.kind in {RuleEffectKind.GRANT_ABILITY, RuleEffectKind.GRANT_WEAPON_ABILITY}
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY)
    if any(
        effect.kind
        in {
            RuleEffectKind.MODIFY_DICE_ROLL,
            RuleEffectKind.REROLL_PERMISSION,
        }
        for effect in clause.effects
    ):
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL)
    return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE)


def _catalog_setup_reactive_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    if (
        parameters.get("edge") != "end"
        or parameters.get("owner") != "opponent"
        or parameters.get("phase") != "movement"
        or parameters.get("timing_window") != "end_opponent_movement_phase"
    ):
        return None
    if not any(_effect_is_setup_reactive_action(effect) for effect in clause.effects):
        return None
    return AbilityTimingDescriptor(
        trigger_kind=TimingTriggerKind.END_PHASE,
        phase=battle_phase_kind_from_token("movement"),
    )


def _catalog_phase_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    phase = parameters.get("phase")
    edge = parameters.get("edge")
    if type(phase) is not str or phase not in {
        "any",
        "command",
        "movement",
        "shooting",
        "charge",
        "fight",
    }:
        return None
    if edge == "start":
        trigger_kind = TimingTriggerKind.START_PHASE
    elif edge == "end":
        trigger_kind = TimingTriggerKind.END_PHASE
    else:
        return None
    return AbilityTimingDescriptor(
        trigger_kind=trigger_kind,
        phase=None if phase == "any" else battle_phase_kind_from_token(phase),
    )


def _catalog_fight_selected_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
        return None
    parameters = parameter_payload(trigger.parameters)
    if parameters.get("phase") != "fight" or parameters.get("timing_window") != "selected_to_fight":
        return None
    return AbilityTimingDescriptor(
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        phase=battle_phase_kind_from_token("fight"),
    )


def _catalog_charge_move_end_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    if (
        parameters.get("edge") == "after"
        and parameters.get("phase") == "charge"
        and parameters.get("timing_window") == "charge_move_end"
        and parameters.get("subject") in {"this_unit", "that_unit", "a_unit"}
    ):
        return AbilityTimingDescriptor(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
            phase=battle_phase_kind_from_token("charge"),
        )
    return None


def _catalog_fall_back_selection_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
        return None
    parameters = parameter_payload(trigger.parameters)
    if (
        parameters.get("selected_unit_allegiance") == "enemy"
        and parameters.get("selection") == "fall_back"
        and parameters.get("timing_window") == "just_after_enemy_unit_selected_to_fall_back"
    ):
        return AbilityTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            phase=battle_phase_kind_from_token("movement"),
        )
    return None


def _catalog_post_shoot_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    if (
        parameters.get("edge") != "after"
        or parameters.get("owner") != "active_player"
        or parameters.get("phase") != "shooting"
        or parameters.get("timing_window") != "just_after_friendly_unit_has_shot"
        or parameters.get("target_relationship") != "hit_by_those_attacks"
    ):
        return None
    if parameters.get("subject") not in {"this_model", "this_unit", "bearer"}:
        return None
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return None
    if (
        clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters).get("endpoint") != "phase"
    ):
        return None
    if not any(_effect_is_status_denial(effect) for effect in clause.effects):
        return None
    return AbilityTimingDescriptor(
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        phase=battle_phase_kind_from_token("shooting"),
    )


def _catalog_turn_timing_descriptor(rule_ir: RuleIR) -> AbilityTimingDescriptor | None:
    if not any(
        _effect_is_turn_end_reserve_permission(effect)
        for clause in rule_ir.clauses
        for effect in clause.effects
    ):
        return None
    for clause in rule_ir.clauses:
        trigger = clause.trigger
        if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
            continue
        parameters = parameter_payload(trigger.parameters)
        if parameters.get("phase") != "turn":
            continue
        edge = parameters.get("edge")
        if edge == "end":
            return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.END_TURN)
        if edge == "start":
            return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_TURN)
    return None


def _catalog_battle_round_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    if parameters.get("phase") != "battle_round":
        return None
    edge = parameters.get("edge")
    if edge == "start":
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    if edge == "end":
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.END_BATTLE_ROUND)
    return None


def _catalog_turn_timing_descriptor_for_clause(
    clause: RuleClause,
) -> AbilityTimingDescriptor | None:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    parameters = parameter_payload(trigger.parameters)
    if parameters.get("phase") != "turn":
        return None
    edge = parameters.get("edge")
    if edge == "end":
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.END_TURN)
    if edge == "start":
        return AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_TURN)
    return None


def _clause_has_turn_end_reserve_permission(clause: RuleClause) -> bool:
    return any(_effect_is_turn_end_reserve_permission(effect) for effect in clause.effects)


def _effect_is_feel_no_pain_grant(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("ability") == "Feel No Pain"


def _effect_is_setup_reactive_action(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.OUT_OF_PHASE_ACTION:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("action_group") == "setup_reactive_shoot_charge" and parameters.get(
        "action"
    ) in {"shoot", "charge"}


def _effect_is_passive_rule_exception_grant(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("ability") in {
        "can_advance_and_charge",
        "can_fall_back_and_charge",
        "can_fall_back_and_shoot",
        "can_advance_and_shoot_and_charge",
    }


def _effect_is_shadow_of_chaos_status(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "within_shadow_of_chaos"
        and parameters.get("rules_context") == "shadow_of_chaos"
        and parameters.get("owner") == "your_army"
    )


def _effect_is_status_denial(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "status_denial" and parameters.get("operation") == "deny"
    )


def _effect_is_turn_end_reserve_permission(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.PLACEMENT_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("placement_kind") == "turn_end_reserves"
        and parameters.get("reserve_kind") == "strategic_reserves"
        and parameters.get("action") == "remove_from_battlefield_to_strategic_reserves"
    )


def _catalog_when_descriptor(descriptor: DatasheetAbilityDescriptor) -> str:
    if descriptor.timing_tags:
        return f"Catalog timing tags: {','.join(descriptor.timing_tags)}."
    return "Catalog generic rule IR."


def _catalog_restrictions_descriptor(descriptor: DatasheetAbilityDescriptor) -> str:
    if descriptor.source_kind is CatalogAbilitySourceKind.WARGEAR:
        if descriptor.source_wargear_id is None:
            raise GameLifecycleError("Wargear catalog ability is missing source_wargear_id.")
        return f"Selected wargear required: {descriptor.source_wargear_id}."
    return f"Datasheet ability source kind: {descriptor.source_kind.value}."


def _record_source_matches_player(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    selected_datasheet_ids: frozenset[str],
    selected_wargear_ids: frozenset[str],
    selected_weapon_profile_ids: frozenset[str],
    selected_weapon_keywords: frozenset[str],
    has_weapon_profile_context: bool,
) -> bool:
    source_kind = record.source_kind
    if source_kind in {AbilitySourceKind.CORE, AbilitySourceKind.KEYWORD}:
        return True
    if source_kind is AbilitySourceKind.FACTION:
        return record.faction_id == army.detachment_selection.faction_id
    if source_kind is AbilitySourceKind.DETACHMENT:
        return record.detachment_id in army.detachment_selection.detachment_ids
    if source_kind is AbilitySourceKind.ENHANCEMENT:
        return (
            record.detachment_id in army.detachment_selection.detachment_ids
            and record.definition.ability_id in army.detachment_selection.enhancement_ids
        )
    if source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id in selected_datasheet_ids
    if source_kind is AbilitySourceKind.WARGEAR:
        return record.wargear_id in selected_wargear_ids
    if source_kind is AbilitySourceKind.WEAPON:
        if not has_weapon_profile_context:
            return False
        if record.weapon_profile_id is not None:
            return record.weapon_profile_id in selected_weapon_profile_ids
        return record.definition.keyword_gate.matches(tuple(selected_weapon_keywords))
    raise GameLifecycleError(f"Unsupported AbilitySourceKind: {source_kind}.")


def _record_keyword_gate_matches_player(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    selected_weapon_keywords: frozenset[str],
) -> bool:
    if record.definition.keyword_gate.is_empty:
        return True
    if record.source_kind is AbilitySourceKind.WEAPON:
        return record.definition.keyword_gate.matches(tuple(selected_weapon_keywords))
    return any(
        record.definition.keyword_gate.matches((*unit.keywords, *unit.faction_keywords))
        for unit in army.units
    )


def _selected_weapon_profile_ids(
    *,
    catalog: ArmyCatalog | None,
    wargear_ids: frozenset[str],
) -> frozenset[str]:
    if catalog is None:
        return frozenset()
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        selected.update(profile.profile_id for profile in wargear.weapon_profiles)
    return frozenset(selected)


def _selected_weapon_keywords(
    *,
    catalog: ArmyCatalog | None,
    wargear_ids: frozenset[str],
) -> frozenset[str]:
    if catalog is None:
        return frozenset()
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        for profile in wargear.weapon_profiles:
            selected.update(_canonical_keyword(keyword.value) for keyword in profile.keywords)
            selected.update(
                _canonical_keyword(ability.ability_kind.value) for ability in profile.abilities
            )
    return frozenset(selected)


def _wargear_by_id(*, catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in catalog.wargear:
        if wargear.wargear_id == requested_id:
            return wargear
    raise GameLifecycleError("Player Ability index references unknown wargear.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")
