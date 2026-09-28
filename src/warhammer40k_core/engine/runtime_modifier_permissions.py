"""Loaded catalog authority carried by an immutable runtime modifier registry."""

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_permission_indexes(indexes: tuple[tuple[str, AbilityCatalogIndex], ...]) -> None:
    if (
        type(indexes) is not tuple
        or any(type(row) is not tuple or len(row) != 2 for row in indexes)
        or any(
            type(player) is not str or not player or type(index) is not AbilityCatalogIndex
            for player, index in indexes
        )
        or len({player for player, _ in indexes}) != len(indexes)
    ):
        raise GameLifecycleError("Modifier permission indexes require unique typed owners.")


def permission_index_for_owner(
    indexes: tuple[tuple[str, AbilityCatalogIndex], ...],
    player_id: str,
) -> AbilityCatalogIndex:
    for owner, index in indexes:
        if owner == player_id:
            return index
    if indexes:
        raise GameLifecycleError("Modifier permission catalog owner is missing.")
    # An explicitly empty registry has no catalog-backed content; persisted grants
    # remain discoverable by the same subject query.
    return AbilityCatalogIndex.from_records(())
