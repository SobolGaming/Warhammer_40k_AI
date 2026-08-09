from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_army_muster_requests(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> tuple[ArmyMusterRequest, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig army_muster_requests must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if len(raw_values) != len(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    validated: list[ArmyMusterRequest] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ArmyMusterRequest:
            raise GameLifecycleError(
                "GameConfig army_muster_requests must contain ArmyMusterRequest values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("ArmyMusterRequest player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameConfig army_muster_requests must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    return tuple(sorted(validated, key=lambda request: request.player_id))


def validate_strict_roster_legality_requests(
    values: tuple[ArmyMusterRequest, ...],
) -> None:
    non_strict_player_ids = tuple(
        request.player_id for request in values if not request.roster_legality_required
    )
    if non_strict_player_ids:
        raise GameLifecycleError(
            "GameConfig production path requires roster_legality_required for every "
            "ArmyMusterRequest. Legacy smoke fixtures must set "
            "allow_legacy_non_strict_rosters explicitly."
        )


__all__ = (
    "validate_army_muster_requests",
    "validate_strict_roster_legality_requests",
)
