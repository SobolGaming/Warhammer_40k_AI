"""Combine validated content contributions without owning runtime bundle construction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine.faction_content import bundle_validation as _bundle_validation
from warhammer40k_core.engine.faction_content.hooks import combine_any_hook_bindings

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

_combine_unique_values = _bundle_validation.combine_unique_values
_contribution_values = _bundle_validation.contribution_values


def _combine_contribution_values[T](
    contributions: tuple[RuntimeContentContribution, ...],
    field_name: str,
    getter: Callable[[RuntimeContentContribution], tuple[T, ...]],
    identifier_for: Callable[[T], str],
) -> tuple[T, ...]:
    return _combine_unique_values(
        field_name,
        _contribution_values(contributions, getter),
        identifier_for,
    )


def combine_runtime_content_contributions(
    *,
    contribution_id: str,
    contributions: tuple[RuntimeContentContribution, ...],
) -> RuntimeContentContribution:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

    validated_contributions = _bundle_validation.validate_runtime_content_contributions(
        contributions, RuntimeContentContribution
    )
    return RuntimeContentContribution(
        contribution_id=contribution_id,
        ability_records=_combine_contribution_values(
            validated_contributions,
            "ability record",
            lambda contribution: contribution.ability_records,
            lambda record: record.record_id,
        ),
        stratagem_records=_combine_contribution_values(
            validated_contributions,
            "Stratagem record",
            lambda contribution: contribution.stratagem_records,
            lambda record: record.record_id,
        ),
        ability_handler_bindings=_combine_contribution_values(
            validated_contributions,
            "ability handler binding",
            lambda contribution: contribution.ability_handler_bindings,
            lambda binding: binding.handler_id,
        ),
        stratagem_handler_bindings=_combine_contribution_values(
            validated_contributions,
            "Stratagem handler binding",
            lambda contribution: contribution.stratagem_handler_bindings,
            lambda binding: binding.handler_id,
        ),
        rule_runtime_bindings=_combine_contribution_values(
            validated_contributions,
            "RuleIR binding",
            lambda contribution: contribution.rule_runtime_bindings,
            lambda binding: binding.binding_id,
        ),
        event_subscriptions=_combine_contribution_values(
            validated_contributions,
            "event subscription",
            lambda contribution: contribution.event_subscriptions,
            lambda subscription: subscription.subscription_id,
        ),
        event_handler_bindings=_combine_contribution_values(
            validated_contributions,
            "event handler binding",
            lambda contribution: contribution.event_handler_bindings,
            lambda binding: binding.handler_id,
        ),
        hook_bindings=combine_any_hook_bindings(
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.hook_bindings,
            )
        ),
        enhancement_effect_bindings=_combine_unique_values(
            "enhancement effect binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.enhancement_effect_bindings,
            ),
            lambda binding: binding.effect_id,
        ),
        stratagem_cost_modifier_bindings=_combine_unique_values(
            "Stratagem cost modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.stratagem_cost_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        unit_characteristic_modifier_bindings=_combine_unique_values(
            "unit characteristic modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.unit_characteristic_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        hit_roll_modifier_bindings=_combine_unique_values(
            "Hit roll modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.hit_roll_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        model_ability_grant_bindings=_combine_unique_values(
            "Model ability grant binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.model_ability_grant_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        wound_roll_modifier_bindings=_combine_unique_values(
            "Wound roll modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.wound_roll_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        save_option_modifier_bindings=_combine_unique_values(
            "save option modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.save_option_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        movement_budget_modifier_bindings=_combine_unique_values(
            "movement budget modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.movement_budget_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        objective_control_modifier_bindings=_combine_unique_values(
            "Objective Control modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.objective_control_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        advance_roll_modifier_bindings=_combine_unique_values(
            "advance roll modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.advance_roll_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        charge_roll_modifier_bindings=_combine_unique_values(
            "charge roll modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.charge_roll_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        weapon_profile_modifier_bindings=_combine_unique_values(
            "weapon profile modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.weapon_profile_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        attack_reroll_permission_bindings=_combine_unique_values(
            "attack reroll permission binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.attack_reroll_permission_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        post_roll_weapon_profile_modifier_bindings=_combine_unique_values(
            "post-roll weapon profile modifier binding",
            _contribution_values(
                validated_contributions,
                lambda contribution: contribution.post_roll_weapon_profile_modifier_bindings,
            ),
            lambda binding: binding.modifier_id,
        ),
        faction_named_handlers=_bundle_validation.merge_named_handlers(
            tuple(contribution.faction_named_handlers for contribution in validated_contributions)
        ),
    )
