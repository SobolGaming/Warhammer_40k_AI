"""Source-preserving catalog Leadership replacements for the bearer's unit."""

from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier, ModifierOperation, ModifierTerm
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind, parameter_payload


def catalog_leadership_modifiers_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[Modifier, ...]:
    from warhammer40k_core.engine.catalog_rule_consumption import (
        catalog_rule_clauses_from_record,
        catalog_rule_record_source_matches_unit,
    )

    if type(ability_index) is not AbilityCatalogIndex or type(unit) is not UnitInstance:
        raise GameLifecycleError("Catalog Leadership requires typed catalog and unit authority.")
    if type(current_model_instance_ids) is not tuple or not current_model_instance_ids:
        raise GameLifecycleError("Catalog Leadership requires current model identity evidence.")
    validate_id = IdentifierValidator(GameLifecycleError)
    current_ids = tuple(
        validate_id("model_instance_id", item) for item in current_model_instance_ids
    )
    if len(set(current_ids)) != len(current_ids):
        raise GameLifecycleError("Catalog Leadership current model identities are duplicated.")
    modifiers: list[Modifier] = []
    for record in ability_index.records_for(TimingTriggerKind.PASSIVE_QUERY):
        if not ability_record_is_active_generic_rule_ir(record):
            continue
        if not catalog_rule_record_source_matches_unit(
            record=record, unit=unit, current_model_instance_ids=tuple(sorted(current_ids))
        ):
            continue
        for clause in catalog_rule_clauses_from_record(record):
            if (
                clause.target is None
                or clause.target.kind is not RuleTargetKind.THIS_UNIT
                or clause.trigger is not None
                or clause.conditions
            ):
                continue
            for index, effect in enumerate(clause.effects):
                parameters = parameter_payload(effect.parameters)
                if (
                    effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
                    or parameters.get("characteristic") != Characteristic.LEADERSHIP.value
                ):
                    continue
                value = _leadership_value(parameters.get("value"))
                modifiers.append(
                    ModifierTerm(ModifierOperation.SET, value).bind(
                        modifier_id=f"{record.record_id}:{clause.clause_id}:effect:{index}:leadership",
                        source_id=record.definition.source_id,
                        characteristic=Characteristic.LEADERSHIP,
                    )
                )
    return tuple(modifiers)


def catalog_leadership_modifiers_for_rules_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: RulesUnitView,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[Modifier, ...]:
    """A THIS_UNIT replacement affects every model in the attached rules unit."""
    return tuple(
        modifier
        for component in unit.components
        if any(
            unit.component_unit_id_for_model(model_id) == component.unit.unit_instance_id
            for model_id in current_model_instance_ids
        )
        for modifier in catalog_leadership_modifiers_for_unit(
            ability_index=ability_index,
            unit=component.unit,
            current_model_instance_ids=tuple(
                model_id
                for model_id in current_model_instance_ids
                if unit.component_unit_id_for_model(model_id) == component.unit.unit_instance_id
            ),
        )
    )


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
