"""Shared, read-only closest-part objective queries over canonical rules units."""

from __future__ import annotations

import math
from dataclasses import dataclass

from warhammer40k_core.core.objectives import (
    DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES,
    ObjectiveMarker,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.polygons import Point2D, triangulate_polygon
from warhammer40k_core.geometry.pose import Pose, validate_finite_number
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_objectives_2026_09 import (
    CONTROL_SOURCE_ID,
    MARKER_SOURCE_ID,
    TERRAIN_SOURCE_ID,
)


@dataclass(frozen=True, slots=True)
class ObjectiveGeometry:
    objective_id: str
    marker: ObjectiveMarker | None
    footprint_polygons: tuple[tuple[Point2D, ...], ...]

    def __post_init__(self) -> None:
        _identifier("objective_id", self.objective_id)
        if type(self.footprint_polygons) is not tuple:
            raise GameLifecycleError("Objective geometry polygons must be a tuple.")
        if self.marker is not None:
            if type(self.marker) is not ObjectiveMarker:
                raise GameLifecycleError("Objective geometry marker must be an ObjectiveMarker.")
            if self.marker.objective_marker_id != self.objective_id or self.footprint_polygons:
                raise GameLifecycleError("Objective geometry marker identity or shape drifted.")
        elif not self.footprint_polygons:
            raise GameLifecycleError("Terrain objective geometry requires its complete footprint.")
        for polygon in self.footprint_polygons:
            triangulate_polygon(polygon)

    @classmethod
    def from_marker(cls, marker: ObjectiveMarker) -> ObjectiveGeometry:
        if type(marker) is not ObjectiveMarker:
            raise GameLifecycleError("Objective geometry requires an ObjectiveMarker.")
        return cls(objective_id=marker.objective_marker_id, marker=marker, footprint_polygons=())

    @classmethod
    def from_terrain(
        cls, *, objective_id: str, footprint_polygons: tuple[tuple[Point2D, ...], ...]
    ) -> ObjectiveGeometry:
        return cls(objective_id=objective_id, marker=None, footprint_polygons=footprint_polygons)

    @property
    def source_ids(self) -> tuple[str, ...]:
        return (
            (MARKER_SOURCE_ID,)
            if self.marker is not None
            else (TERRAIN_SOURCE_ID, CONTROL_SOURCE_ID)
        )


@dataclass(frozen=True, slots=True)
class ObjectiveModelDistance:
    horizontal_distance_inches: float
    vertical_gap_inches: float
    within_control_range: bool

    def __post_init__(self) -> None:
        for value in (self.horizontal_distance_inches, self.vertical_gap_inches):
            if validate_finite_number("objective distance", value) < 0:
                raise GameLifecycleError("Objective distances must be non-negative.")
        if type(self.within_control_range) is not bool:
            raise GameLifecycleError("Objective control range must be a bool.")

    @property
    def closest_distance_inches(self) -> float:
        return math.hypot(self.horizontal_distance_inches, self.vertical_gap_inches)


@dataclass(frozen=True, slots=True)
class ObjectiveModelMeasurement:
    objective_id: str
    rules_unit_instance_id: str
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    distance: ObjectiveModelDistance

    def __post_init__(self) -> None:
        for name in (
            "objective_id",
            "rules_unit_instance_id",
            "player_id",
            "unit_instance_id",
            "model_instance_id",
        ):
            _identifier(name, getattr(self, name))
        if type(self.distance) is not ObjectiveModelDistance:
            raise GameLifecycleError("Objective measurement requires typed distance evidence.")

    @property
    def horizontal_distance_inches(self) -> float:
        return self.distance.horizontal_distance_inches

    @property
    def vertical_gap_inches(self) -> float:
        return self.distance.vertical_gap_inches

    @property
    def closest_distance_inches(self) -> float:
        return self.distance.closest_distance_inches

    @property
    def within_control_range(self) -> bool:
        return self.distance.within_control_range


def measure_model_to_objective(
    *, model: GeometryModel, objective: ObjectiveGeometry
) -> ObjectiveModelDistance:
    """Measure one physical model against the marker disk or terrain footprint union."""
    if type(model) is not GeometryModel or type(objective) is not ObjectiveGeometry:
        raise GameLifecycleError(
            "Objective measurement requires typed model and objective geometry."
        )
    marker = objective.marker
    if marker is not None:
        context = DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id=marker.objective_marker_id,
            marker_pose=Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            model=model,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        horizontal = context.horizontal_distance_inches()
        vertical = context.vertical_gap_inches()
        horizontal_limit = marker.control_horizontal_inches
        vertical_limit = marker.control_vertical_inches
    else:
        horizontal = min(
            shapely_backend.base_footprint_distance_to_polygon(model.base, model.pose, polygon)
            for polygon in objective.footprint_polygons
        )
        bottom, top = model.volume.vertical_interval(model.pose)
        vertical = max(bottom, -top, 0.0)
        horizontal_limit = 0.0
        vertical_limit = DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES
    return ObjectiveModelDistance(
        horizontal_distance_inches=horizontal,
        vertical_gap_inches=vertical,
        within_control_range=horizontal <= horizontal_limit and vertical <= vertical_limit,
    )


def measure_rules_unit_to_objective(
    *, scenario: BattlefieldScenario, rules_unit: RulesUnitView, objective: ObjectiveGeometry
) -> tuple[ObjectiveModelMeasurement, ...]:
    """Return deterministic per-model evidence, preserving attached component ownership.

    Models absent from the battlefield and destroyed models have no OC contribution.
    Distances remain paired per model, so horizontal and vertical minima from different
    members cannot accidentally establish range for the unit.
    """
    if type(scenario) is not BattlefieldScenario or type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Objective group query requires a scenario and RulesUnitView.")
    if type(objective) is not ObjectiveGeometry:
        raise GameLifecycleError("Objective group query requires ObjectiveGeometry.")
    if rules_unit != rules_unit_view_from_armies(
        armies=scenario.armies, unit_instance_id=rules_unit.unit_instance_id
    ):
        raise GameLifecycleError("Objective group query rules-unit identity drifted.")
    measurements: list[ObjectiveModelMeasurement] = []
    for model in rules_unit.alive_models():
        placement = scenario.battlefield_state.model_placement_or_none(model.model_instance_id)
        if placement is None:
            continue
        component_id = rules_unit.component_unit_id_for_model(model.model_instance_id)
        if (
            placement.player_id != rules_unit.owner_player_id
            or placement.unit_instance_id != component_id
        ):
            raise GameLifecycleError("Objective group query physical ownership drifted.")
        measurements.append(
            ObjectiveModelMeasurement(
                objective_id=objective.objective_id,
                rules_unit_instance_id=rules_unit.unit_instance_id,
                player_id=placement.player_id,
                unit_instance_id=component_id,
                model_instance_id=model.model_instance_id,
                distance=measure_model_to_objective(
                    model=geometry_model_for_placement(model=model, placement=placement),
                    objective=objective,
                ),
            )
        )
    return tuple(sorted(measurements, key=lambda row: row.model_instance_id))


_identifier = IdentifierValidator(GameLifecycleError)
