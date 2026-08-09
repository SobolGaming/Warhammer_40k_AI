from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import (
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, SpatialIndexState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    classification_is_solid,
    model_intersects_terrain_area,
)
from warhammer40k_core.geometry.visibility import VisibilityBlockerRecord
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def shooting_visibility_cache_key(
    *,
    scenario: BattlefieldScenario,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    terrain_areas: tuple[PlacedTerrainArea, ...] = (),
) -> str:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("shooting_visibility_cache_key requires a BattlefieldScenario.")
    features = _validate_terrain_features(terrain_features)
    areas = validate_shooting_terrain_areas(terrain_areas)
    spatial_state = SpatialIndexState.from_terrain_features(
        features,
        model_blocker_revision=_model_blocker_revision(scenario.placed_geometry_models()),
    )
    base_key = spatial_state.los_cache_key()
    if not areas:
        return base_key
    payload = {
        "base_los_cache_key": base_key,
        "terrain_areas": [area.to_payload() for area in areas],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"los:{hashlib.sha256(encoded).hexdigest()[:16]}"


def validate_shooting_terrain_areas(
    values: object,
) -> tuple[PlacedTerrainArea, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("terrain_areas must be a tuple.")
    areas: list[PlacedTerrainArea] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlacedTerrainArea:
            raise GameLifecycleError("terrain_areas must contain PlacedTerrainArea values.")
        if value.terrain_area_id in seen:
            raise GameLifecycleError("terrain_areas must not contain duplicate IDs.")
        seen.add(value.terrain_area_id)
        areas.append(value)
    return tuple(sorted(areas, key=lambda area: area.terrain_area_id))


def shooting_terrain_areas_for_state(state: GameState) -> tuple[PlacedTerrainArea, ...]:
    mission_setup = state.mission_setup
    if mission_setup is None:
        return ()
    return validate_shooting_terrain_areas(mission_setup.terrain_areas)


def terrain_visibility_areas_from_placements(
    terrain_areas: tuple[PlacedTerrainArea, ...],
) -> tuple[TerrainVisibilityArea, ...]:
    return tuple(
        TerrainVisibilityArea(
            terrain_area_id=area.terrain_area_id,
            classification=area.classification,
            footprint_polygon=tuple(
                (point.x_inches, point.y_inches) for point in area.footprint_polygon
            ),
        )
        for area in validate_shooting_terrain_areas(terrain_areas)
    )


def model_within_solid_terrain(
    *,
    ruleset_descriptor: RulesetDescriptor,
    model: Model,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
) -> bool:
    for area in terrain_visibility_areas_from_placements(terrain_areas):
        if classification_is_solid(area.classification) and model_intersects_terrain_area(
            model, area
        ):
            return True
    return any(
        _feature_is_solid(ruleset_descriptor, feature) and _model_intersects_feature(model, feature)
        for feature in _validate_terrain_features(terrain_features)
    )


def blocker_record_is_solid(
    *,
    ruleset_descriptor: RulesetDescriptor,
    record: VisibilityBlockerRecord,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    if record.terrain_area_classification is not None:
        return classification_is_solid(record.terrain_area_classification)
    if record.terrain_feature_id is None:
        return False
    for feature in _validate_terrain_features(terrain_features):
        if feature.feature_id == record.terrain_feature_id:
            return _feature_is_solid(ruleset_descriptor, feature)
    return False


def _feature_is_solid(
    ruleset_descriptor: RulesetDescriptor,
    feature: TerrainFeatureDefinition,
) -> bool:
    if classification_is_solid(feature.classification):
        return True
    policy = ruleset_descriptor.terrain_visibility_policy.policy_for_feature_kind(
        TerrainFeatureKind(feature.feature_kind)
    )
    return policy.line_of_sight_policy is LineOfSightPolicy.DENSE_COVER


def _model_intersects_feature(model: Model, feature: TerrainFeatureDefinition) -> bool:
    from warhammer40k_core.geometry import shapely_backend

    return shapely_backend.base_footprint_intersects_polygon(
        model.base,
        model.pose,
        feature.rules_footprint_points(),
    )


def _validate_terrain_features(
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("terrain_features must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GameLifecycleError(
                "terrain_features must contain TerrainFeatureDefinition values."
            )
        if value.feature_id in seen:
            raise GameLifecycleError("terrain_features must not contain duplicate IDs.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _model_blocker_revision(models: tuple[Model, ...]) -> int:
    payload = [
        {
            "model_id": model.model_id,
            "pose": model.pose.to_payload(),
            "base": model.base.to_payload(),
            "volume": model.volume.to_payload(),
        }
        for model in sorted(models, key=lambda item: item.model_id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)
