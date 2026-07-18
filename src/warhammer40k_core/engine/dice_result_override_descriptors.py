from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_resources import UnitStartingResourceAllocation
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    parameter_payload,
)

ASPECT_SHRINE_TOKEN_RESOURCE_KIND = "aeldari:aspect-shrine-token"


@dataclass(frozen=True, slots=True)
class DiceResultOverrideDescriptor:
    descriptor_id: str
    source_rule_id: str
    ability_id: str
    clause_id: str
    roll_types: tuple[str, ...]
    replacement_value: int
    resource_kind: str
    resource_cost: int
    excluded_model_keywords: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "descriptor_id",
            _validate_identifier("DiceResultOverrideDescriptor descriptor_id", self.descriptor_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "DiceResultOverrideDescriptor source_rule_id", self.source_rule_id
            ),
        )
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("DiceResultOverrideDescriptor ability_id", self.ability_id),
        )
        object.__setattr__(
            self,
            "clause_id",
            _validate_identifier("DiceResultOverrideDescriptor clause_id", self.clause_id),
        )
        object.__setattr__(self, "roll_types", _validate_roll_types(self.roll_types))
        object.__setattr__(
            self,
            "replacement_value",
            _validate_d6_value(
                "DiceResultOverrideDescriptor replacement_value", self.replacement_value
            ),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier("DiceResultOverrideDescriptor resource_kind", self.resource_kind),
        )
        object.__setattr__(
            self,
            "resource_cost",
            _validate_positive_int(
                "DiceResultOverrideDescriptor resource_cost", self.resource_cost
            ),
        )
        object.__setattr__(
            self,
            "excluded_model_keywords",
            _validate_keyword_tuple(
                "DiceResultOverrideDescriptor excluded_model_keywords",
                self.excluded_model_keywords,
            ),
        )


def dice_result_override_descriptors_for_abilities(
    abilities: tuple[DatasheetAbilityDescriptor, ...],
) -> tuple[DiceResultOverrideDescriptor, ...]:
    if type(abilities) is not tuple:
        raise GameLifecycleError("Dice result override abilities must be a tuple.")
    descriptors: list[DiceResultOverrideDescriptor] = []
    for ability in abilities:
        if type(ability) is not DatasheetAbilityDescriptor:
            raise GameLifecycleError(
                "Dice result override abilities must contain DatasheetAbilityDescriptor values."
            )
        if ability.rule_ir_payload is None:
            continue
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
        for clause in rule_ir.clauses:
            for effect_index, effect in enumerate(clause.effects):
                if effect.kind is not RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT:
                    continue
                parameters = parameter_payload(effect.parameters)
                descriptors.append(
                    DiceResultOverrideDescriptor(
                        descriptor_id=(
                            f"{rule_ir.source_id}:{clause.clause_id}:"
                            f"dice-result-override:{effect_index}"
                        ),
                        source_rule_id=rule_ir.source_id,
                        ability_id=ability.ability_id,
                        clause_id=clause.clause_id,
                        roll_types=_required_string_tuple(parameters, "roll_types"),
                        replacement_value=_required_int(parameters, "replacement_value"),
                        resource_kind=_required_string(parameters, "resource_kind"),
                        resource_cost=_required_int(parameters, "resource_cost"),
                        excluded_model_keywords=_required_string_tuple(
                            parameters, "excluded_model_keywords"
                        ),
                    )
                )
    descriptor_ids = [descriptor.descriptor_id for descriptor in descriptors]
    if len(descriptor_ids) != len(set(descriptor_ids)):
        raise GameLifecycleError("Dice result override descriptor identities must be unique.")
    return tuple(sorted(descriptors, key=lambda descriptor: descriptor.descriptor_id))


def dice_result_override_resource_entitlement(
    *,
    abilities: tuple[DatasheetAbilityDescriptor, ...],
    resource_kind: str,
) -> DiceResultOverrideDescriptor | None:
    requested_kind = _validate_identifier("resource_kind", resource_kind)
    matching = tuple(
        descriptor
        for descriptor in dice_result_override_descriptors_for_abilities(abilities)
        if descriptor.resource_kind == requested_kind
    )
    if len(matching) > 1:
        raise GameLifecycleError(
            "A unit must not carry multiple dice result override entitlements for one resource."
        )
    return None if not matching else matching[0]


def validate_dice_result_override_starting_resources(
    *,
    abilities: tuple[DatasheetAbilityDescriptor, ...],
    allocations: tuple[UnitStartingResourceAllocation, ...],
) -> None:
    if type(allocations) is not tuple:
        raise GameLifecycleError("Dice result override starting resources must be a tuple.")
    for allocation in allocations:
        if type(allocation) is not UnitStartingResourceAllocation:
            raise GameLifecycleError(
                "Dice result override starting resources must contain allocations."
            )
        if (
            dice_result_override_resource_entitlement(
                abilities=abilities,
                resource_kind=allocation.resource_kind,
            )
            is None
        ):
            raise GameLifecycleError(
                "Unit starting resource allocation has no source-backed entitlement."
            )


def _required_string(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Dice result override parameter {key} must be a string.")
    return value.strip()


def _required_int(parameters: Mapping[str, object], key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Dice result override parameter {key} must be an integer.")
    return value


def _required_string_tuple(parameters: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = parameters.get(key)
    if type(value) is not tuple:
        raise GameLifecycleError(f"Dice result override parameter {key} must be a tuple.")
    return cast(tuple[str, ...], value)


def _validate_roll_types(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError("Dice result override roll_types must be a non-empty tuple.")
    validated: list[str] = []
    for value in values:
        if value not in {"hit", "wound"}:
            raise GameLifecycleError("Dice result override roll_types contain an invalid value.")
        if value in validated:
            raise GameLifecycleError("Dice result override roll_types must be unique.")
        validated.append(value)
    return tuple(validated)


def _validate_keyword_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(canonical_keyword_token(value) for value in values)
    if len(validated) != len(set(validated)):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


def _validate_d6_value(field_name: str, value: int) -> int:
    if type(value) is not int or value < 1 or value > 6:
        raise GameLifecycleError(f"{field_name} must be an integer from 1 through 6.")
    return value


def _validate_positive_int(field_name: str, value: int) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
