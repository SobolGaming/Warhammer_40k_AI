"""Structured catalog permissions for the Core pre-battle split procedure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from warhammer40k_core.core.datasheet import CatalogAbilitySupport
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

UNIT_SPLIT_CONSUMER_ID = "catalog-ir:prebattle-unit-split"


def clause_is_unit_split_permission(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.SETUP
        or parameter_payload(clause.trigger.parameters)
        != {"timing_window": "declare_battle_formations", "edge": "before"}
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.conditions
        or clause.duration is not None
        or len(clause.effects) != 1
        or clause.effects[0].kind is not RuleEffectKind.SPLIT_UNIT
    ):
        return False
    parameters = parameter_payload(clause.effects[0].parameters)
    if set(parameters) != {"first_strength", "second_strength", "optional"}:
        return False
    first, second = parameters["first_strength"], parameters["second_strength"]
    return type(parameters["optional"]) is bool and (
        (first is None and second is None)
        or (type(first) is int and type(second) is int and first > 0 and second > 0)
    )


@dataclass(frozen=True, slots=True)
class UnitSplitPermission:
    player_id: str
    source_id: str
    source_unit_id: str
    target_unit_id: str
    specified_strengths: tuple[int, int] | None
    optional: bool


def unit_split_permissions(army: ArmyDefinition) -> tuple[UnitSplitPermission, ...]:
    """Read source snapshots so completed and declined opportunities remain auditable.

    Only the declared pre-battle window is executable. Other shapes containing a
    split effect raise a domain error instead of advertising partial semantics.
    """
    original = replace(army, units=army.source_units(), unit_splits=())
    views = rules_unit_views_from_armies(armies=(original,))
    permissions: list[UnitSplitPermission] = []
    for unit in original.units:
        for ability in unit.datasheet_abilities:
            if ability.support is not CatalogAbilitySupport.GENERIC_RULE_IR:
                continue
            if ability.rule_ir_payload is None:
                raise GameLifecycleError("Generic split permission is missing RuleIR.")
            rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
            for clause in rule.clauses:
                effects = tuple(e for e in clause.effects if e.kind is RuleEffectKind.SPLIT_UNIT)
                if not effects:
                    continue
                if rule.source_id != ability.source_id:
                    raise GameLifecycleError("Unit split catalog and RuleIR source identity drift.")
                if not clause_is_unit_split_permission(clause):
                    raise GameLifecycleError("Unsupported catalog unit split permission semantics.")
                parameters = parameter_payload(effects[0].parameters)
                if set(parameters) != {"first_strength", "second_strength", "optional"}:
                    raise GameLifecycleError("Unsupported unit split effect parameters.")
                first, second = parameters["first_strength"], parameters["second_strength"]
                optional = parameters["optional"]
                if type(optional) is not bool:
                    raise GameLifecycleError("Unit split optional must be a boolean.")
                strengths: tuple[int, int] | None
                if first is None and second is None:
                    strengths = None
                elif type(first) is int and type(second) is int and first > 0 and second > 0:
                    strengths = (first, second)
                else:
                    raise GameLifecycleError("Unit split strengths require two positive counts.")
                target = next(
                    v for v in views if unit.unit_instance_id in v.component_unit_instance_ids
                )
                permissions.append(
                    UnitSplitPermission(
                        player_id=army.player_id,
                        source_id=rule.source_id,
                        source_unit_id=unit.unit_instance_id,
                        target_unit_id=target.unit_instance_id,
                        specified_strengths=strengths,
                        optional=optional,
                    )
                )
    keys = [(p.source_id, p.source_unit_id, p.target_unit_id) for p in permissions]
    if len(keys) != len(set(keys)):
        raise GameLifecycleError("Unit split permissions have duplicate source identities.")
    return tuple(
        sorted(permissions, key=lambda p: (p.source_id, p.source_unit_id, p.target_unit_id))
    )
