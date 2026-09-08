"""Fight action entitlement, independent of retained physical presence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destructions,
    validate_retained_placement,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def model_has_fight_action_authority(*, state: GameState, model_instance_id: str) -> bool:
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield

    if not model_is_present_on_battlefield(state=state, model_instance_id=model_instance_id):
        return False
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    return model.is_alive or model_instance_id in fight_on_death_model_ids_for_rules_unit(
        state=state, unit_instance_id=state.unit_instance_id_for_model(model_instance_id)
    )


def fight_on_death_model_ids_for_rules_unit(
    *, state: GameState, unit_instance_id: str
) -> tuple[str, ...]:
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    own_ids = {model.model_instance_id for model in view.own_models}
    result: list[str] = []
    for record in retained_destructions(state=state):
        if (
            record.model_instance_id not in own_ids
            or record.selected_action is not RetainedAttackAction.FIGHT
            or record.stage is not RetainedDestructionStage.WAITING
        ):
            continue
        validate_retained_placement(state=state, record=record)
        result.append(record.model_instance_id)
    return tuple(sorted(result))
