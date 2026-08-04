from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def split_attached_rules_unit_if_required(
    *,
    state: GameState,
    event_log: EventLog,
    rules_unit_instance_id: str,
) -> tuple[str, ...]:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        return ()
    bodyguard_alive = any(
        model.is_alive
        for component in rules_unit.components
        if component.role == "bodyguard"
        for model in component.unit.own_models
    )
    leader_or_support_alive = any(
        model.is_alive
        for component in rules_unit.components
        if component.role in {"leader", "support"}
        for model in component.unit.own_models
    )
    if bodyguard_alive == leader_or_support_alive:
        return ()
    surviving_unit_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for component in rules_unit.components
            if any(model.is_alive for model in component.unit.own_models)
        )
    )
    if not surviving_unit_ids:
        raise GameLifecycleError("Attached-unit split requires surviving component units.")
    state.recover_starting_strength_after_attached_unit_split(
        player_id=rules_unit.owner_player_id,
        attached_unit_instance_id=rules_unit.unit_instance_id,
        surviving_unit_instance_ids=surviving_unit_ids,
        event_log=event_log,
    )
    return surviving_unit_ids
