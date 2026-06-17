from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)

CATALOG_IR_CHARGE_ROLL_CONSUMER_ID = "catalog-ir:charge-roll-modifier"
CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID = "catalog-ir:leadership-characteristic-query"


def catalog_charge_roll_modifiers_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
) -> tuple[RollModifier, ...]:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    modifiers: list[RollModifier] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    ):
        rule_ir = _rule_ir_from_record(record)
        for clause in rule_ir.clauses:
            if not _clause_targets_this_unit(clause):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if not _effect_is_charge_roll_modifier(effect):
                    continue
                parameters = parameter_payload(effect.parameters)
                delta = _int_parameter(parameters, key="delta")
                modifiers.append(
                    RollModifier(
                        modifier_id=(
                            f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}"
                        ),
                        source_id=record.definition.source_id,
                        operand=delta,
                    )
                )
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))


def catalog_leadership_characteristic_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
) -> int | None:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    resolved_value: int | None = None
    resolved_source_id: str | None = None
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        rule_ir = _rule_ir_from_record(record)
        for clause in rule_ir.clauses:
            if not _clause_targets_this_unit(clause):
                continue
            for effect in clause.effects:
                if not _effect_is_leadership_set(effect):
                    continue
                value = _leadership_value(parameter_payload(effect.parameters).get("value"))
                if resolved_value is not None and resolved_value != value:
                    raise GameLifecycleError(
                        "Catalog Leadership query found conflicting set-characteristic effects."
                    )
                resolved_value = value
                resolved_source_id = record.definition.source_id
    if resolved_value is not None and resolved_source_id is None:
        raise GameLifecycleError("Catalog Leadership query resolved without a source.")
    return resolved_value


def catalog_rule_ir_consumers_for_rule(rule_ir: RuleIR) -> tuple[str, ...]:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleIR.")
    consumer_ids: set[str] = set()
    for clause in rule_ir.clauses:
        if not _clause_targets_this_unit(clause):
            continue
        for effect in clause.effects:
            if _effect_is_charge_roll_modifier(effect):
                consumer_ids.add(CATALOG_IR_CHARGE_ROLL_CONSUMER_ID)
            if _effect_is_leadership_set(effect):
                consumer_ids.add(CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID)
    return tuple(sorted(consumer_ids))


def _unit_scoped_generic_records(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    if type(trigger_kind) is not TimingTriggerKind:
        raise GameLifecycleError("Catalog rule consumer trigger kind must be TimingTriggerKind.")
    return tuple(
        record
        for record in ability_index.records_for(trigger_kind)
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        and _record_source_matches_unit(record=record, unit=unit)
    )


def _rule_ir_from_record(record: AbilityCatalogRecord) -> RuleIR:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogRecord.")
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(record.definition.replay_payload)


def _record_source_matches_unit(*, record: AbilityCatalogRecord, unit: UnitInstance) -> bool:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id == unit.datasheet_id
    if record.source_kind is AbilitySourceKind.WARGEAR:
        return record.datasheet_id == unit.datasheet_id and record.wargear_id in _unit_wargear_ids(
            unit
        )
    return False


def _unit_wargear_ids(unit: UnitInstance) -> frozenset[str]:
    return frozenset(
        wargear_id for selection in unit.wargear_selections for wargear_id in selection.wargear_ids
    )


def _clause_targets_this_unit(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT


def _effect_is_charge_roll_modifier(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return False
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    return roll_type in {"charge", "charge_roll"}


def _effect_is_leadership_set(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CHARACTERISTIC:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("characteristic") == Characteristic.LEADERSHIP.value


def _int_parameter(parameters: Mapping[str, object], *, key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be an integer.")
    return value


def _leadership_value(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is str:
        stripped = value.strip()
        if stripped.endswith("+"):
            stripped = stripped[:-1]
        if stripped.isdecimal():
            return int(stripped)
    raise GameLifecycleError("Catalog Leadership set-characteristic value is invalid.")


def _validate_ability_index(ability_index: AbilityCatalogIndex) -> AbilityCatalogIndex:
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogIndex.")
    return ability_index


def _validate_unit(unit: UnitInstance) -> UnitInstance:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Catalog rule consumer requires a UnitInstance.")
    return unit
