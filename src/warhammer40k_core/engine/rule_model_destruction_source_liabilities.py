from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.effects import PersistingEffect
    from warhammer40k_core.engine.game_state import GameState


def validate_rule_destruction_source_liabilities(
    *,
    state: GameState,
    source_effect_ids: tuple[str, ...],
    rules_unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    effect_by_id = {effect.effect_id: effect for effect in state.persisting_effects}
    missing_ids = tuple(
        effect_id for effect_id in source_effect_ids if effect_id not in effect_by_id
    )
    if missing_ids:
        raise GameLifecycleError("Rule destruction source liability effect is missing.")
    effects = tuple(effect_by_id[effect_id] for effect_id in source_effect_ids)
    if any(rules_unit_instance_id not in effect.target_unit_instance_ids for effect in effects):
        raise GameLifecycleError("Rule destruction source liability target drift.")
    return effects


def consume_rule_destruction_source_liabilities(
    *,
    state: GameState,
    source_effect_ids: tuple[str, ...],
    rules_unit_instance_id: str,
) -> None:
    effects = validate_rule_destruction_source_liabilities(
        state=state,
        source_effect_ids=source_effect_ids,
        rules_unit_instance_id=rules_unit_instance_id,
    )
    state.remove_persisting_effects_by_id(source_effect_ids)
    for effect in effects:
        remaining_targets = tuple(
            unit_id
            for unit_id in effect.target_unit_instance_ids
            if unit_id != rules_unit_instance_id
        )
        if remaining_targets:
            state.record_persisting_effect(
                replace(effect, target_unit_instance_ids=remaining_targets)
            )


__all__ = (
    "consume_rule_destruction_source_liabilities",
    "validate_rule_destruction_source_liabilities",
)
