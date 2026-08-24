from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

CATALOG_IR_MODIFIER_IGNORE_PERMISSION_CONSUMER_ID = "catalog-ir:modifier-ignore-permission"


class ModifierIgnoreKind(StrEnum):
    MOVEMENT_CHARACTERISTIC = "movement_characteristic"
    ADVANCE_ROLL = "advance_roll"
    CHARGE_ROLL = "charge_roll"


@dataclass(frozen=True, slots=True)
class CatalogModifierIgnorePermission:
    permission_id: str
    record_id: str
    source_id: str
    rule_ir_hash: str
    clause_id: str
    modifier_kinds: tuple[ModifierIgnoreKind, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "permission_id",
            _validate_identifier("modifier-ignore permission_id", self.permission_id),
        )
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("modifier-ignore record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("modifier-ignore source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "rule_ir_hash",
            _validate_identifier("modifier-ignore rule_ir_hash", self.rule_ir_hash),
        )
        object.__setattr__(
            self,
            "clause_id",
            _validate_identifier("modifier-ignore clause_id", self.clause_id),
        )
        if type(self.modifier_kinds) is not tuple or not self.modifier_kinds:
            raise GameLifecycleError("Modifier-ignore permission requires modifier kinds.")
        kinds = tuple(ModifierIgnoreKind(kind) for kind in self.modifier_kinds)
        if len(set(kinds)) != len(kinds):
            raise GameLifecycleError("Modifier-ignore permission kinds must be unique.")
        object.__setattr__(self, "modifier_kinds", tuple(sorted(kinds, key=str)))

    def supports(self, kind: ModifierIgnoreKind) -> bool:
        if type(kind) is not ModifierIgnoreKind:
            raise GameLifecycleError("Modifier-ignore query requires a typed kind.")
        return kind in self.modifier_kinds

    def to_payload(self) -> dict[str, object]:
        return {
            "permission_id": self.permission_id,
            "record_id": self.record_id,
            "source_id": self.source_id,
            "rule_ir_hash": self.rule_ir_hash,
            "clause_id": self.clause_id,
            "modifier_kinds": [kind.value for kind in self.modifier_kinds],
        }


def clause_is_modifier_ignore_permission(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Modifier-ignore classification requires RuleClause.")
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.conditions
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or clause.duration.parameters
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    raw_kinds = parameters.get("modifier_kinds")
    if type(raw_kinds) is not tuple or not raw_kinds:
        return False
    if any(type(value) is not str for value in raw_kinds):
        return False
    try:
        kinds = tuple(ModifierIgnoreKind(value) for value in raw_kinds)
    except (TypeError, ValueError):  # fmt: skip
        return False
    return len(set(kinds)) == len(kinds) and parameters == {
        "ability": "modifier_ignore_permission",
        "modifier_kinds": raw_kinds,
        "selection": "any_or_all",
    }


def catalog_modifier_ignore_permissions_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[CatalogModifierIgnorePermission, ...]:
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Modifier-ignore query requires AbilityCatalogIndex.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Modifier-ignore query requires UnitInstance.")
    current_ids = _validate_identifier_tuple(
        "modifier-ignore current_model_instance_ids",
        current_model_instance_ids,
    )
    from warhammer40k_core.engine.catalog_rule_consumption import (
        catalog_rule_clauses_from_record,
        catalog_rule_record_source_matches_unit,
    )
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    permissions: list[CatalogModifierIgnorePermission] = []
    for record in ability_index.all_records():
        if not ability_record_is_active_generic_rule_ir(record):
            continue
        if not catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_ids,
        ):
            continue
        rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
        for clause in catalog_rule_clauses_from_record(record):
            if not clause_is_modifier_ignore_permission(clause):
                continue
            raw_kinds = parameter_payload(clause.effects[0].parameters)["modifier_kinds"]
            if type(raw_kinds) is not tuple or any(type(value) is not str for value in raw_kinds):
                raise GameLifecycleError("Modifier-ignore permission kind payload drifted.")
            kinds = tuple(ModifierIgnoreKind(value) for value in raw_kinds)
            permissions.append(
                CatalogModifierIgnorePermission(
                    permission_id=f"{rule_ir.source_id}:{clause.clause_id}:modifier-ignore",
                    record_id=record.record_id,
                    source_id=rule_ir.source_id,
                    rule_ir_hash=rule_ir.ir_hash(),
                    clause_id=clause.clause_id,
                    modifier_kinds=kinds,
                )
            )
    return tuple(sorted(permissions, key=lambda permission: permission.permission_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
