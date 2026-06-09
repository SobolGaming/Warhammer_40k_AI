from __future__ import annotations

from enum import StrEnum


class CatalogContentScopeError(ValueError):
    """Raised when catalog content scope data violates CORE V2 invariants."""


class CatalogContentScope(StrEnum):
    MATCHED_PLAY = "matched_play"
    COMBAT_PATROL = "combat_patrol"
    LEGENDS = "legends"
    FORGE_WORLD = "forge_world"
    KILL_TEAM = "kill_team"


SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES = frozenset({CatalogContentScope.MATCHED_PLAY})


def catalog_content_scope_from_token(token: object) -> CatalogContentScope:
    if type(token) is CatalogContentScope:
        return token
    if type(token) is not str:
        raise CatalogContentScopeError("CatalogContentScope token must be a string.")
    try:
        return CatalogContentScope(token)
    except ValueError as exc:
        raise CatalogContentScopeError(f"Unsupported CatalogContentScope token: {token}.") from exc
