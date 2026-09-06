"""Living model authority for Battle-shock, independent of target geometry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock import BattleShockTestReason
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView


def command_test_allows_off_battlefield(
    *, reason: BattleShockTestReason, phase: BattlePhase, player_id: str, active_player_id: str
) -> bool:
    from warhammer40k_core.engine.battle_shock import BattleShockTestReason

    return (
        phase is BattlePhase.COMMAND
        and player_id == active_player_id
        and reason
        in {
            BattleShockTestReason.COMMAND_PHASE_REQUIRED,
            BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        }
    )


def battle_shock_model_ids(
    *,
    rules_unit: RulesUnitView,
    battlefield: BattlefieldRuntimeState,
    state: GameState | None,
    allow_off_battlefield: bool,
) -> tuple[str, ...]:
    """Require a whole living rules unit, or authenticated destroyed departures.

    Only Command obligations admit wholly embarked or wholly reserve models.
    Missing placements alone never authorize a test or confer geometry.
    """
    alive_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    placed_ids: set[str] = set()
    for component in rules_unit.components:
        placement = battlefield.unit_placement_or_none(component.unit.unit_instance_id)
        if placement is None:
            continue
        own_ids = set(component.unit.own_model_ids())
        for model in placement.model_placements:
            if model.model_instance_id not in own_ids:
                raise GameLifecycleError("Battlefield unit placement contains unknown model.")
            if model.model_instance_id in alive_ids:
                placed_ids.add(model.model_instance_id)
    embarked_ids: set[str] = set() if state is None else set(state.embarked_model_ids())
    reserve_ids: set[str] = set() if state is None else set(state.unarrived_reserve_model_ids())
    unavailable_ids = embarked_ids | reserve_ids
    if placed_ids & unavailable_ids:
        raise GameLifecycleError("Battle-shock target has conflicting battlefield presence.")
    if (
        allow_off_battlefield
        and alive_ids
        and not placed_ids
        and (alive_ids <= embarked_ids or alive_ids <= reserve_ids)
    ):
        return tuple(sorted(alive_ids))
    destroyed_departure_ids: set[str] = (
        set()
        if state is None
        else {
            model_id
            for departure in state.primary_battlefield_departure_states
            if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
            and departure.rules_unit_instance_id == rules_unit.unit_instance_id
            for model_id in departure.removed_model_instance_ids
        }
    )
    if not placed_ids or not (alive_ids - placed_ids) <= destroyed_departure_ids:
        raise GameLifecycleError(
            "Battle-shock target does not have every alive model on the battlefield or lacks "
            "authenticated embarkation, reserve, or destroyed-departure authority."
        )
    return tuple(sorted(placed_ids))
