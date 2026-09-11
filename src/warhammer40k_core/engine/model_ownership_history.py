from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.model_destruction_cause_authority import (
    consumed_model_destruction_cause_authority_for_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def historical_physical_unit_id(*, state: GameState, model_instance_id: str) -> str:
    """Resolve immutable model ownership, including models pruned by replacement."""
    owners = {
        unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        if model_instance_id in unit.own_model_ids()
    }
    owners.update(
        consumed_model_destruction_cause_authority_for_event(
            state=state, event=authority.model_destroyed_event
        ).physical_unit_instance_id
        for authority in state.model_destruction_cause_authorities
        if authority.model_instance_id == model_instance_id
        and authority.model_destroyed_event is not None
    )
    if len(owners) != 1:
        raise GameLifecycleError("Historical model ownership requires one authoritative unit.")
    return next(iter(owners))


def historical_model_ids_by_physical_unit(state: GameState) -> dict[str, tuple[str, ...]]:
    models_by_unit = {
        unit.unit_instance_id: set(unit.own_model_ids())
        for army in state.army_definitions
        for unit in army.units
    }
    for authority in state.model_destruction_cause_authorities:
        if authority.model_destroyed_event is None:
            continue
        physical_id = historical_physical_unit_id(
            state=state, model_instance_id=authority.model_instance_id
        )
        if physical_id not in models_by_unit:
            raise GameLifecycleError("Historical model ownership references a missing unit.")
        models_by_unit[physical_id].add(authority.model_instance_id)
    return {unit_id: tuple(sorted(models)) for unit_id, models in models_by_unit.items()}
