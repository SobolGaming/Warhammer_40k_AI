from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError


def primary_player_turn_key(
    *,
    battle_round: int,
    active_player_id: str,
    turn_order: tuple[str, ...],
    label: str = "Primary scoring player turn",
) -> tuple[int, int]:
    """Return a chronological key for one player's turn in a two-player battle."""
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(f"{label} battle_round must be a positive integer.")
    ordered_players = _identifier_tuple("turn_order", turn_order)
    requested_player = _identifier(f"{label} active_player_id", active_player_id)
    if requested_player not in ordered_players:
        raise GameLifecycleError(f"{label} references an unknown active player.")
    return battle_round, ordered_players.index(requested_player)


def primary_own_turn_interval_contains(
    *,
    owner_player_id: str,
    started_battle_round: int,
    query_battle_round: int,
    query_active_player_id: str,
    turn_order: tuple[str, ...],
) -> bool:
    """Return whether a query turn is in [own-turn start, next own-turn start)."""
    start_key = primary_player_turn_key(
        battle_round=started_battle_round,
        active_player_id=owner_player_id,
        turn_order=turn_order,
        label="Primary scoring own-turn start",
    )
    expire_key = primary_player_turn_key(
        battle_round=started_battle_round + 1,
        active_player_id=owner_player_id,
        turn_order=turn_order,
        label="Primary scoring own-turn expiration",
    )
    query_key = primary_player_turn_key(
        battle_round=query_battle_round,
        active_player_id=query_active_player_id,
        turn_order=turn_order,
        label="Primary scoring query turn",
    )
    return start_key <= query_key < expire_key


def _identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple with at least two values.")
    raw_values = cast(tuple[object, ...], values)
    identifiers = tuple(_identifier(field_name, value) for value in raw_values)
    if len(identifiers) < 2:
        raise GameLifecycleError(f"{field_name} must be a tuple with at least two values.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "primary_own_turn_interval_contains",
    "primary_player_turn_key",
)
