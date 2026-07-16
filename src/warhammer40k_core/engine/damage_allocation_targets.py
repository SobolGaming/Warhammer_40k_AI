from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView


class DamageKind(StrEnum):
    NORMAL = "normal"
    MORTAL = "mortal"


class DamageAllocationTargetState(StrEnum):
    ALLOCATABLE = "allocatable"
    PRESENT_WITHOUT_LIVING_MODELS = "present_without_living_models"
    ABSENT = "absent"


def damage_allocation_target_state(
    *,
    state: GameState,
    target_unit_instance_id: str,
) -> DamageAllocationTargetState:
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Damage allocation target state requires battlefield_state.")
    placed_model_ids = set(battlefield.placed_model_ids())
    if any(
        model.is_alive and model.model_instance_id in placed_model_ids
        for model in rules_unit.own_models
    ):
        return DamageAllocationTargetState.ALLOCATABLE
    if any(
        model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        )
        for model in rules_unit.own_models
    ):
        return DamageAllocationTargetState.PRESENT_WITHOUT_LIVING_MODELS
    return DamageAllocationTargetState.ABSENT


def assert_damage_allocation_target_is_allocatable(
    *,
    state: GameState,
    target_unit_instance_id: str,
) -> None:
    target_state = damage_allocation_target_state(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )
    if target_state is DamageAllocationTargetState.PRESENT_WITHOUT_LIVING_MODELS:
        raise GameLifecycleError("Damage allocation target is present but has no living models.")
    if target_state is DamageAllocationTargetState.ABSENT:
        raise GameLifecycleError("Damage allocation target is absent from the battlefield.")


def allocatable_rules_unit(*, state: GameState, unit_id: str) -> RulesUnitView:
    assert_damage_allocation_target_is_allocatable(
        state=state,
        target_unit_instance_id=unit_id,
    )
    return rules_unit_view_by_id(state=state, unit_instance_id=unit_id)


def damage_kind_from_token(token: object) -> DamageKind:
    if type(token) is DamageKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DamageKind token must be a string.")
    try:
        return DamageKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DamageKind token: {token}.") from exc
