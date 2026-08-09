from __future__ import annotations

from enum import StrEnum


class TerrainClassificationError(ValueError):
    """Raised when terrain classification metadata is invalid."""


class TerrainAreaClassification(StrEnum):
    DENSE = "dense"
    LIGHT = "light"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def terrain_area_classification_from_token(token: object) -> TerrainAreaClassification:
    if type(token) is TerrainAreaClassification:
        return token
    if type(token) is not str:
        raise TerrainClassificationError("Terrain area classification token must be a string.")
    try:
        return TerrainAreaClassification(token)
    except ValueError as exc:
        raise TerrainClassificationError("Unsupported terrain area classification token.") from exc
