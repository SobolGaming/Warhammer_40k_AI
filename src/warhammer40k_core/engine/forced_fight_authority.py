"""Canonical ownership for live and historical forced-Fight entitlement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def forced_fight_selecting_player_id(
    *, state: GameState, source_unit_instance_id: str, eligible_unit_instance_ids: tuple[str, ...]
) -> str:
    # Include immutable attached identities even after their living components
    # separate. Ownership is independent of battlefield presence or survival.
    owners = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for attached in state.starting_attached_unit_records:
        if attached.attached_unit_instance_id in owners and (
            owners[attached.attached_unit_instance_id] != attached.player_id
        ):
            raise GameLifecycleError("Forced Fight historical ownership is inconsistent.")
        owners[attached.attached_unit_instance_id] = attached.player_id
    if source_unit_instance_id not in owners or any(
        unit_id not in owners for unit_id in eligible_unit_instance_ids
    ):
        raise GameLifecycleError("Forced Fight ownership requires known unit identities.")
    pending_owners = {owners[unit_id] for unit_id in eligible_unit_instance_ids}
    if len(pending_owners) != 1 or owners[source_unit_instance_id] in pending_owners:
        raise GameLifecycleError("Forced Fight response units must belong to one opponent.")
    player_id = next(iter(pending_owners))
    if player_id not in state.player_ids:
        raise GameLifecycleError("Forced Fight owner is not a player in this game.")
    return player_id
