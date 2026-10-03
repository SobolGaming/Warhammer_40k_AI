"""Core Action Battle-shock policy and explicit catalog RuleIR permission."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

ACTION_BATTLE_SHOCK_PERMISSION = "can_perform_actions_while_battle_shocked"
ACTION_BATTLE_SHOCK_CONSUMER_ID = "catalog-ir:action-battle-shock-permission"
ACTION_BATTLE_SHOCK_SOURCE_ID = "faq:bbe268a2-b1fd-43ab-8b24-fd4363730c3f"
ACTION_BATTLE_SHOCK_PERMISSION_SOURCE_ID = "faq:4c654d00-318d-4665-9e46-26cfab179a29"
ACTION_BATTLE_SHOCK_EVENT = "mission_action_battle_shock_applied"


def effect_grants_action_battle_shock_permission(effect: RuleEffectSpec) -> bool:
    return effect.kind is RuleEffectKind.GRANT_ABILITY and parameter_payload(effect.parameters) == {
        "ability": ACTION_BATTLE_SHOCK_PERMISSION
    }


def clause_grants_action_battle_shock_permission(clause: RuleClause) -> bool:
    """Only an unconditional permanent unit grant has this consumer."""
    return (
        clause.is_supported
        and clause.trigger is None
        and not clause.conditions
        and clause.target is not None
        and clause.target.kind is RuleTargetKind.THIS_UNIT
        and not clause.target.parameters
        and len(clause.effects) == 1
        and effect_grants_action_battle_shock_permission(clause.effects[0])
        and clause.duration is not None
        and clause.duration.kind is RuleDurationKind.PERMANENT
        and not clause.duration.parameters
    )


def action_battle_shock_permission_sources(
    *,
    state: GameState,
    unit_instance_id: str,
    present_model_ids: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Read source-owned permission, optionally at an authenticated start boundary."""
    sources: set[str] = set()
    for view in current_rules_unit_views_for_identity(
        state=state, unit_instance_id=unit_instance_id
    ):
        present = (
            set(present_model_ids)
            if present_model_ids is not None
            else {model.model_instance_id for model in view.alive_models()}
        )
        for component in view.components:
            unit = component.unit
            if not present.intersection(unit.own_model_ids()):
                continue
            for ability in unit.datasheet_abilities:
                if (
                    ability.support is not CatalogAbilitySupport.GENERIC_RULE_IR
                    or ability.source_kind is not CatalogAbilitySourceKind.DATASHEET
                    or ability.rule_ir_payload is None
                ):
                    continue
                rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
                if rule.source_id != ability.source_id:
                    raise GameLifecycleError("Action Battle-shock permission source drifted.")
                if any(clause_grants_action_battle_shock_permission(c) for c in rule.clauses):
                    sources.add(rule.source_id)
    return tuple(sorted(sources))


def action_battle_shock_descriptor_consumer_ids(
    *, ability: DatasheetAbilityDescriptor, consumer_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Do not advertise this bounded unit-datasheet consumer for other sources."""
    if ability.source_kind is CatalogAbilitySourceKind.DATASHEET:
        return consumer_ids
    return tuple(value for value in consumer_ids if value != ACTION_BATTLE_SHOCK_CONSUMER_ID)
