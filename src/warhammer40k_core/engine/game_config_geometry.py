from __future__ import annotations

from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogError,
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_optional_game_config_model_geometries(
    values: object | None,
    *,
    catalog: ArmyCatalog,
    army_muster_requests: tuple[ArmyMusterRequest, ...],
) -> tuple[ModelGeometryCatalogRecord, ...] | None:
    if values is None:
        return None
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig model_geometries must be a tuple when present.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise GameLifecycleError(
            "GameConfig model_geometries must be omitted when no reviewed geometry is available."
        )
    known_model_profile_ids = {
        profile.model_profile_id
        for datasheet in catalog.datasheets
        for profile in datasheet.model_profiles
    }
    selected_model_profile_ids = {
        profile.model_profile_id
        for request in army_muster_requests
        for selection in request.unit_selections
        for profile in selection.model_profile_selections
    }
    validated: list[ModelGeometryCatalogRecord] = []
    seen_model_profile_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not ModelGeometryCatalogRecord:
            raise GameLifecycleError(
                "GameConfig model_geometries must contain ModelGeometryCatalogRecord values."
            )
        if value.model_profile_id not in known_model_profile_ids:
            raise GameLifecycleError(
                "GameConfig model_geometries reference an unknown catalog model profile."
            )
        if value.model_profile_id in seen_model_profile_ids:
            raise GameLifecycleError(
                "GameConfig model_geometries must be unique by model_profile_id."
            )
        seen_model_profile_ids.add(value.model_profile_id)
        validated.append(value)
    missing_selected_profile_ids = sorted(
        selected_model_profile_ids.difference(seen_model_profile_ids)
    )
    if missing_selected_profile_ids:
        raise GameLifecycleError(
            "GameConfig model_geometries are incomplete for selected model profiles: "
            + ", ".join(missing_selected_profile_ids)
        )
    return tuple(sorted(validated, key=lambda record: record.model_profile_id))


def game_config_model_geometries_from_payload(
    values: list[ModelGeometryCatalogRecordPayload],
) -> tuple[ModelGeometryCatalogRecord, ...]:
    try:
        return tuple(ModelGeometryCatalogRecord.from_payload(value) for value in values)
    except (KeyError, TypeError, ModelGeometryCatalogError) as exc:
        raise GameLifecycleError("GameConfig model_geometries payload is invalid.") from exc


__all__ = (
    "game_config_model_geometries_from_payload",
    "validate_optional_game_config_model_geometries",
)
