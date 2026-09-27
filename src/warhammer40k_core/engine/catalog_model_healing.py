"""Model-bound catalog healing through the shared engine owner."""

from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import UnitInstance


def restore_catalog_model_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    effect_id: str,
    unit: UnitInstance,
    model_id: str,
    amount: int,
    opposing_player_id: str,
    source_rule_id: str,
    source_context: dict[str, JsonValue],
) -> tuple[HealingEffect, DecisionRequest | None]:
    effect = HealingEffect(
        effect_id=effect_id,
        target_unit_instance_id=rules_unit_view_by_id(
            state=state, unit_instance_id=unit.unit_instance_id
        ).unit_instance_id,
        amount=amount,
        opposing_player_id=opposing_player_id,
        source_rule_id=source_rule_id,
        source_context={**source_context, "healing_model_instance_id": model_id},
    )
    return resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
    )


def catalog_model_missing_wounds(*, unit: UnitInstance, source_model_id: str) -> int:
    for model in unit.own_models:
        if model.model_instance_id == source_model_id:
            if not model.is_alive:
                raise GameLifecycleError("Catalog model healing requires a living source.")
            return model.initial_wounds - model.current_wounds
    raise GameLifecycleError("Catalog model healing source is not owned by the unit.")
