from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attached_unit_reconciliation import (
    validate_attached_rules_unit_identity_after_destruction,
)
from warhammer40k_core.engine.fight_on_death import fight_on_death_model_ids_for_rules_unit
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_model_presence import (
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def active_fight_activation_rules_unit(
    *,
    state: GameState,
    activation: FightActivationSelection,
) -> RulesUnitView | None:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    awaiting_model_ids = fight_on_death_model_ids_for_rules_unit(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    rules_unit_model_ids = frozenset(model.model_instance_id for model in rules_unit.own_models)
    if not set(awaiting_model_ids).issubset(rules_unit_model_ids):
        raise GameLifecycleError("Fight On Death awaiting model is outside its activation unit.")
    present_model_ids = frozenset(
        model.model_instance_id
        for model in rules_unit.own_models
        if model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        )
    )
    if not present_model_ids:
        return None
    missing_alive_ids = tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.own_models
            if model.is_alive and model.model_instance_id not in present_model_ids
        )
    )
    if missing_alive_ids:
        raise GameLifecycleError("Active fight rules unit has unplaced living models.")
    if not set(awaiting_model_ids).issubset(present_model_ids):
        raise GameLifecycleError("Fight On Death awaiting model is not placed.")
    return rules_unit


def validate_attached_rules_unit_after_fight_activation(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> None:
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
    )
