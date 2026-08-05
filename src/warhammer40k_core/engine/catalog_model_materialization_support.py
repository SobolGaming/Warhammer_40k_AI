from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID = "catalog-ir:model-materialization"


@dataclass(frozen=True, slots=True)
class MaterializeModelsDescriptor:
    destroyed_model_profile_ids: tuple[str, ...]
    result_model_profile_id: str
    result_model_name: str
    result_wargear_ids: tuple[str, ...]
    result_count: int
    result_materialization_descriptor_id: str
    result_base_size_datasheet_id: str
    required_materialization_descriptor_id: str | None
    excluded_materialization_descriptor_ids: tuple[str, ...]
    success_threshold: int


@dataclass(frozen=True, slots=True)
class ReplacementModelVariantDescriptor:
    materialization_descriptor_id: str
    wargear_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnitDatasheetReplacementDescriptor:
    required_absent_model_profile_ids: tuple[str, ...]
    replacement_datasheet_id: str
    replacement_model_profile_id: str
    model_variants: tuple[ReplacementModelVariantDescriptor, ...]
    pruned_model_profile_ids: tuple[str, ...]


def materialize_models_descriptor_for_clause(
    clause: RuleClause,
) -> MaterializeModelsDescriptor | None:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Model materialization classification requires RuleClause.")
    if len(clause.effects) != 1 or clause.effects[0].kind is not RuleEffectKind.MATERIALIZE_MODELS:
        return None
    if (
        clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.MODEL_DESTROYED
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.IMMEDIATE
    ):
        raise GameLifecycleError("Model materialization RuleIR shape is unsupported.")
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    if trigger_parameters != {
        "destruction_source_kinds": ("attack", "hazardous"),
        "timing_window": "after_attacking_unit_finished_attacks",
    }:
        raise GameLifecycleError("Model materialization trigger parameters are unsupported.")
    target_constraints = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    )
    dice_gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )
    if len(target_constraints) != 1 or len(dice_gates) != 1 or len(clause.conditions) != 2:
        raise GameLifecycleError("Model materialization conditions are unsupported.")
    if parameter_payload(target_constraints[0].parameters) != {
        "source_rules_unit_not_destroyed": True
    }:
        raise GameLifecycleError("Model materialization target condition is unsupported.")
    dice_parameters = parameter_payload(dice_gates[0].parameters)
    if dice_parameters.get("roll_expression") != "D6":
        raise GameLifecycleError("Model materialization requires a D6 trigger roll.")
    success_threshold = _required_int(dice_parameters, "success_threshold")
    if not 2 <= success_threshold <= 6:
        raise GameLifecycleError("Model materialization success threshold is invalid.")
    parameters = parameter_payload(clause.effects[0].parameters)
    if parameters.get("placement_trigger_kind") != "model_placed_on_battlefield":
        raise GameLifecycleError("Model materialization placement trigger is unsupported.")
    return MaterializeModelsDescriptor(
        destroyed_model_profile_ids=_required_string_tuple(
            parameters, "destroyed_model_profile_ids"
        ),
        result_model_profile_id=_required_string(parameters, "result_model_profile_id"),
        result_model_name=_required_string(parameters, "result_model_name"),
        result_wargear_ids=_required_string_tuple(parameters, "result_wargear_ids"),
        result_count=_required_positive_int(parameters, "result_count"),
        result_materialization_descriptor_id=_required_string(
            parameters, "result_materialization_descriptor_id"
        ),
        result_base_size_datasheet_id=_required_string(parameters, "result_base_size_datasheet_id"),
        required_materialization_descriptor_id=_optional_string(
            parameters, "required_materialization_descriptor_id"
        ),
        excluded_materialization_descriptor_ids=_optional_string_tuple(
            parameters, "excluded_materialization_descriptor_ids"
        ),
        success_threshold=success_threshold,
    )


def unit_datasheet_replacement_descriptor_for_clause(
    clause: RuleClause,
) -> UnitDatasheetReplacementDescriptor | None:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Datasheet replacement classification requires RuleClause.")
    if (
        len(clause.effects) != 1
        or clause.effects[0].kind is not RuleEffectKind.REPLACE_UNIT_DATASHEET
    ):
        return None
    if (
        clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.MODEL_DESTROYED
        or parameter_payload(clause.trigger.parameters)
        != {"timing_window": "after_attacking_unit_finished_attacks"}
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.PERMANENT
        or len(clause.conditions) != 1
        or clause.conditions[0].kind is not RuleConditionKind.TARGET_CONSTRAINT
    ):
        raise GameLifecycleError("Datasheet replacement RuleIR shape is unsupported.")
    condition_parameters = parameter_payload(clause.conditions[0].parameters)
    parameters = parameter_payload(clause.effects[0].parameters)
    variant_count = _required_positive_int(parameters, "replacement_model_variant_count")
    model_variants = tuple(
        ReplacementModelVariantDescriptor(
            materialization_descriptor_id=_required_string(
                parameters,
                f"replacement_model_variant_{index}_materialization_descriptor_id",
            ),
            wargear_ids=_required_string_tuple(
                parameters,
                f"replacement_model_variant_{index}_wargear_ids",
            ),
        )
        for index in range(1, variant_count + 1)
    )
    if len({variant.materialization_descriptor_id for variant in model_variants}) != len(
        model_variants
    ):
        raise GameLifecycleError(
            "Datasheet replacement materialization descriptors must be unique."
        )
    return UnitDatasheetReplacementDescriptor(
        required_absent_model_profile_ids=_required_string_tuple(
            condition_parameters, "required_absent_model_profile_ids"
        ),
        replacement_datasheet_id=_required_string(parameters, "replacement_datasheet_id"),
        replacement_model_profile_id=_required_string(parameters, "replacement_model_profile_id"),
        model_variants=model_variants,
        pruned_model_profile_ids=_required_string_tuple(parameters, "pruned_model_profile_ids"),
    )


def consumer_ids_for_effect_kind(effect_kind: RuleEffectKind) -> tuple[str, ...]:
    if effect_kind in {
        RuleEffectKind.MATERIALIZE_MODELS,
        RuleEffectKind.REPLACE_UNIT_DATASHEET,
    }:
        return (CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID,)
    return ()


def _required_string(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Model materialization {key} must be a string.")
    return value


def _optional_string(parameters: Mapping[str, object], key: str) -> str | None:
    value = parameters.get(key)
    if value is None:
        return None
    return _required_string(parameters, key)


def _required_string_tuple(parameters: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = parameters.get(key)
    if not isinstance(value, tuple) or not value:
        raise GameLifecycleError(f"Model materialization {key} must be a string tuple.")
    result: list[str] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not str:
            raise GameLifecycleError(f"Model materialization {key} must be a string tuple.")
        result.append(item)
    return tuple(result)


def _optional_string_tuple(parameters: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = parameters.get(key)
    if value is None:
        return ()
    return _required_string_tuple(parameters, key)


def _required_int(parameters: Mapping[str, object], key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Model materialization {key} must be an integer.")
    return value


def _required_positive_int(parameters: Mapping[str, object], key: str) -> int:
    value = _required_int(parameters, key)
    if value < 1:
        raise GameLifecycleError(f"Model materialization {key} must be positive.")
    return value


__all__ = (
    "CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID",
    "MaterializeModelsDescriptor",
    "ReplacementModelVariantDescriptor",
    "UnitDatasheetReplacementDescriptor",
    "consumer_ids_for_effect_kind",
    "materialize_models_descriptor_for_clause",
    "unit_datasheet_replacement_descriptor_for_clause",
)
