from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierContext,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    CatalogAllocatedAttackDamageModifierDescriptor,
    CatalogConditionalInvulnerableSaveDescriptor,
    CatalogInvulnerableSaveDescriptor,
)
from warhammer40k_core.engine.runtime_modifiers import SaveOptionModifierContext
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.rules.rule_ir import RuleTargetKind


class SourceAppliesToRulesUnit(Protocol):
    def __call__(self, *, context_unit_id: str, state: object) -> bool: ...


class SourceModelIds(Protocol):
    def __call__(self, *, state: object) -> tuple[str, ...]: ...


class AliveRulesUnitModelIds(Protocol):
    def __call__(self, *, state: object, unit_instance_id: str) -> tuple[str, ...]: ...


def passive_invulnerable_save_handler(
    *,
    descriptor: CatalogInvulnerableSaveDescriptor,
    source_rule_id: str,
    source_applies_to_rules_unit: SourceAppliesToRulesUnit,
    source_model_ids: SourceModelIds,
    alive_rules_unit_model_ids: AliveRulesUnitModelIds,
) -> Callable[[SaveOptionModifierContext], tuple[SaveOption, ...]]:
    def handler(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
        allocated_model_id = context.allocated_model_instance_id
        if allocated_model_id is None or not source_applies_to_rules_unit(
            context_unit_id=context.target_unit_instance_id,
            state=context.state,
        ):
            return context.save_options
        if (
            descriptor.target_kind is RuleTargetKind.THIS_MODEL
            and allocated_model_id not in source_model_ids(state=context.state)
        ):
            return context.save_options
        if (
            descriptor.target_kind is RuleTargetKind.THIS_UNIT
            and allocated_model_id
            not in alive_rules_unit_model_ids(
                state=context.state,
                unit_instance_id=context.target_unit_instance_id,
            )
        ):
            return context.save_options
        return _save_options_with_invulnerable_grant(
            save_options=context.save_options,
            target_number=descriptor.target_number,
            source_rule_id=source_rule_id,
        )

    return handler


def conditional_invulnerable_save_handler(
    *,
    descriptor: CatalogConditionalInvulnerableSaveDescriptor,
    source_rule_id: str,
    source_applies_to_rules_unit: SourceAppliesToRulesUnit,
    source_model_ids: SourceModelIds,
) -> Callable[[SaveOptionModifierContext], tuple[SaveOption, ...]]:
    def handler(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
        allocated_model_id = context.allocated_model_instance_id
        profile = context.weapon_profile
        if (
            allocated_model_id is None
            or profile is None
            or profile.range_profile.kind is not RangeProfileKind.DISTANCE
            or descriptor.attack_kind != "ranged"
            or not source_applies_to_rules_unit(
                context_unit_id=context.target_unit_instance_id,
                state=context.state,
            )
            or allocated_model_id not in source_model_ids(state=context.state)
        ):
            return context.save_options
        return _save_options_with_invulnerable_grant(
            save_options=context.save_options,
            target_number=descriptor.target_number,
            source_rule_id=source_rule_id,
        )

    return handler


def allocated_attack_damage_modifier_handler(
    *,
    descriptor: CatalogAllocatedAttackDamageModifierDescriptor,
    source_applies_to_rules_unit: SourceAppliesToRulesUnit,
    source_model_ids: SourceModelIds,
) -> Callable[[AllocatedAttackDamageModifierContext], int]:
    def handler(context: AllocatedAttackDamageModifierContext) -> int:
        if not source_applies_to_rules_unit(
            context_unit_id=context.target_unit_instance_id,
            state=context.state,
        ) or context.allocated_model_instance_id not in source_model_ids(state=context.state):
            return 0
        return descriptor.delta

    return handler


def _save_options_with_invulnerable_grant(
    *,
    save_options: tuple[SaveOption, ...],
    target_number: int,
    source_rule_id: str,
) -> tuple[SaveOption, ...]:
    if any(
        option.save_kind is SaveKind.INVULNERABLE
        and option.target_number <= target_number
        and option.characteristic_target_number <= target_number
        for option in save_options
    ):
        return save_options
    replacement = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=target_number,
        characteristic_target_number=target_number,
        armor_penetration=0,
        source_rule_ids=(source_rule_id,),
    )
    return (
        *tuple(option for option in save_options if option.save_kind is not SaveKind.INVULNERABLE),
        replacement,
    )
