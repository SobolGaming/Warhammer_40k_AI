from __future__ import annotations

from math import isfinite
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_movement_source import ChargePlacement
from warhammer40k_core.engine.charge_rule_effects import (
    unit_has_vehicle_or_monster_keyword,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model as GeometryModel

_validate_identifier = IdentifierValidator(GameLifecycleError)
CHARGE_MOVE_ACTION = "charge_move"


def _geometry_models_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    return physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: ChargePlacement,
) -> tuple[GeometryModel, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[GeometryModel, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[GeometryModel] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(enemy_models)


def _friendly_geometry_models_for_charge_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: ChargePlacement,
    attempted_placement: ChargePlacement,
    moving_model_instance_id: str,
) -> tuple[GeometryModel, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[GeometryModel] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            endpoints = {m.model_instance_id: m for m in attempted_placement.model_placements}
            placements = tuple(
                endpoints.get(m.model_instance_id, m)
                for m in current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _closest_distance_between_model_groups(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> float:
    if not first_models or not second_models:
        raise GameLifecycleError("Charge distance requires non-empty model groups.")
    return min(
        first_model.range_to(second_model)
        for first_model in first_models
        for second_model in second_models
    )


def _model_groups_are_engaged(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    return any(
        first_model.is_within_engagement_range(
            second_model,
            horizontal_inches=horizontal_inches,
            vertical_inches=vertical_inches,
        )
        for first_model in first_models
        for second_model in second_models
    )


def _charge_move_transition_batch(
    *,
    before: ChargePlacement,
    after: ChargePlacement,
    witness: PathWitness,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    displacement_records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Charge Move transition references an unknown model.")
        if placement.pose == before_poses[placement.model_instance_id]:
            continue
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.CHARGE.value,
                source_step=CHARGE_MOVE_ACTION,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(displacements=tuple(displacement_records))


def _validate_charge_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: ChargePlacement,
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Charge Move requires a PathWitness.")
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError("Charge Move witness must match the selected unit models.")


def _terrain_volumes_for_features(
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[TerrainVolume, ...]:
    volumes: list[TerrainVolume] = []
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
        volumes.extend(feature.terrain_volumes())
    return tuple(volumes)


def _validate_distance_map(field_name: str, value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    distances: dict[str, float] = {}
    for raw_key, raw_distance in cast(dict[object, object], value).items():
        unit_id = _validate_identifier(field_name, raw_key)
        if type(raw_distance) not in {int, float}:
            raise GameLifecycleError(f"{field_name} values must be numbers.")
        distance = float(cast(int | float, raw_distance))
        if not isfinite(distance) or distance < 0.0:
            raise GameLifecycleError(f"{field_name} distances must be non-negative.")
        distances[unit_id] = distance
    return dict(sorted(distances.items()))


def _validate_path_validation_results(
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("path_validation_results must be a tuple.")
    results: list[PathValidationResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PathValidationResult:
            raise GameLifecycleError(
                "path_validation_results must contain PathValidationResult values."
            )
        results.append(value)
    return tuple(results)


def _validate_terrain_path_legality_results(
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("terrain_path_legality_results must be a tuple.")
    results: list[TerrainPathLegalityResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainPathLegalityResult:
            raise GameLifecycleError(
                "terrain_path_legality_results must contain TerrainPathLegalityResult values."
            )
        results.append(value)
    return tuple(results)


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    json_value = validate_json_value(value)
    if not isinstance(json_value, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return json_value


__all__ = (
    "_charge_move_transition_batch",
    "_closest_distance_between_model_groups",
    "_enemy_geometry_models_for_player",
    "_friendly_geometry_models_for_charge_path",
    "_friendly_vehicle_monster_model_ids",
    "_geometry_models_for_unit",
    "_geometry_models_for_unit_placement",
    "_model_groups_are_engaged",
    "_terrain_volumes_for_features",
    "_validate_charge_witness_matches_unit",
    "_validate_distance_map",
    "_validate_json_object",
    "_validate_path_validation_results",
    "_validate_terrain_path_legality_results",
)
