from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destruction_for_model,
    validate_retained_placement,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def remove_destroyed_model_from_battlefield(*, state: GameState, model_instance_id: str) -> None:
    from warhammer40k_core.engine.damage_allocation import model_by_id

    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if model.is_alive:
        raise GameLifecycleError("Only destroyed models can be removed from battlefield.")
    retained = retained_destruction_for_model(state=state, model_instance_id=model_instance_id)
    if retained is not None:
        validate_retained_placement(state=state, record=retained)
        if retained.stage not in (
            RetainedDestructionStage.RESOLVING,
            RetainedDestructionStage.SUSPENDED,
            RetainedDestructionStage.DECLINED,
            RetainedDestructionStage.NOT_TRIGGERED,
        ):
            raise GameLifecycleError("Fight On Death model cannot be removed before completion.")
        if retained.stage in (
            RetainedDestructionStage.RESOLVING,
            RetainedDestructionStage.SUSPENDED,
        ):
            if any(
                retained.cause_id in cause.parent_cause_ids and not cause.is_consumed
                for cause in state.model_destruction_cause_authorities
            ):
                raise GameLifecycleError(
                    "Retained destruction cannot remove a parent before its casualty completes."
                )
            updated = replace(retained, stage=RetainedDestructionStage.REMOVED)
            # The owner keeps the continuation through post-removal reaction choices.
            # Its physical presence ends in the immediately following removal.
            effect = next(
                effect
                for effect in state.persisting_effects
                if effect.effect_id == retained.effect_id
            )
            replacement = replace(
                effect,
                effect_payload={
                    "effect_kind": "retained_model_destruction",
                    "destruction": updated.to_payload(),
                },
            )
            state.remove_persisting_effects_by_id((effect.effect_id,))
            state.record_persisting_effect(replacement)
        else:
            state.remove_persisting_effects_by_id((retained.effect_id,))
    from warhammer40k_core.engine.battlefield_state import PlacementError

    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed model removal requires battlefield_state.")
    try:
        state.replace_battlefield_state(battlefield.with_removed_models((model_instance_id,)))
    except PlacementError as exc:
        raise GameLifecycleError("Destroyed model removal failed.") from exc
