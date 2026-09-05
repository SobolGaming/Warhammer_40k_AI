from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    mission_logical_terrain_areas,
    model_intersects_logical_terrain_area,
)
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.objective_geometry_sources import mission_objective_geometries
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryComponentTurnStartMembership,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance


def build_primary_rules_unit_membership_from_model_placements(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    owner_player_id: str,
    component_unit_instance_ids: tuple[str, ...],
    model_placements: tuple[ModelPlacement, ...],
) -> PrimaryRulesUnitTurnStartMembership:
    """Build one exact membership from an authenticated historical placement set."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary historical position tracking requires GameState.")
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise GameLifecycleError(
            "Primary historical position tracking requires mission and battlefield state."
        )
    if {feature.feature_id for feature in battlefield.terrain_features} != {
        feature.feature_id for feature in mission_setup.terrain_features
    }:
        raise GameLifecycleError(
            "Primary historical position tracking requires mission and battlefield terrain parity."
        )
    validated_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    validated_owner_id = _validate_identifier("owner_player_id", owner_player_id)
    validated_component_ids = _validate_identifier_tuple(
        "component_unit_instance_ids",
        component_unit_instance_ids,
    )
    if not validated_component_ids:
        raise GameLifecycleError(
            "Primary historical position tracking requires at least one component."
        )
    if type(model_placements) is not tuple or any(
        type(placement) is not ModelPlacement for placement in model_placements
    ):
        raise GameLifecycleError(
            "Primary historical position tracking requires typed model placements."
        )
    placements_by_id = {placement.model_instance_id: placement for placement in model_placements}
    if len(placements_by_id) != len(model_placements):
        raise GameLifecycleError(
            "Primary historical position tracking model placements are duplicated."
        )
    units_by_id: dict[str, tuple[str, UnitInstance]] = {
        unit.unit_instance_id: (army.player_id, unit)
        for army in state.army_definitions
        for unit in army.units
    }
    component_units: list[UnitInstance] = []
    for component_id in validated_component_ids:
        authoritative = units_by_id.get(component_id)
        if authoritative is None or authoritative[0] != validated_owner_id:
            raise GameLifecycleError(
                "Primary historical position tracking component identity drifted."
            )
        component_units.append(authoritative[1])
    return _build_membership(
        rules_unit_instance_id=validated_rules_unit_id,
        owner_player_id=validated_owner_id,
        component_units=tuple(component_units),
        placements_by_id=placements_by_id,
        logical_terrain_areas=mission_logical_terrain_areas(mission_setup),
        objectives=mission_objective_geometries(state),
    )


def _build_membership(
    *,
    rules_unit_instance_id: str,
    owner_player_id: str,
    component_units: tuple[UnitInstance, ...],
    placements_by_id: dict[str, ModelPlacement],
    logical_terrain_areas: tuple[MissionLogicalTerrainArea, ...],
    objectives: tuple[ObjectiveGeometry, ...],
) -> PrimaryRulesUnitTurnStartMembership:
    component_memberships: list[PrimaryComponentTurnStartMembership] = []
    for unit in component_units:
        geometry_models_by_id: dict[str, GeometryModel] = {}
        for model in unit.own_models:
            placement = placements_by_id.get(model.model_instance_id)
            if placement is None:
                continue
            if placement.player_id != owner_player_id:
                raise GameLifecycleError("Primary position evidence model placement owner drift.")
            if placement.unit_instance_id != unit.unit_instance_id:
                raise GameLifecycleError("Primary position evidence component placement drift.")
            geometry_models_by_id[model.model_instance_id] = geometry_model_for_placement(
                model=model,
                placement=placement,
            )
        logical_area_ids = tuple(
            sorted(
                {
                    area.logical_terrain_area_id
                    for area in logical_terrain_areas
                    for geometry_model in geometry_models_by_id.values()
                    if model_intersects_logical_terrain_area(geometry_model, area=area)
                }
            )
        )
        objective_witnesses = tuple(
            PrimaryObjectiveMarkerWitness(
                objective_marker_id=objective.objective_id,
                model_instance_ids=model_ids,
            )
            for objective in objectives
            for model_ids in (
                tuple(
                    sorted(
                        model_id
                        for model_id, geometry_model in geometry_models_by_id.items()
                        if measure_model_to_objective(
                            model=geometry_model, objective=objective
                        ).within_control_range
                    )
                ),
            )
            if model_ids
        )
        component_memberships.append(
            PrimaryComponentTurnStartMembership(
                unit_instance_id=unit.unit_instance_id,
                evaluated_model_instance_ids=tuple(sorted(geometry_models_by_id)),
                logical_terrain_area_ids=logical_area_ids,
                objective_marker_witnesses=objective_witnesses,
            )
        )
    return PrimaryRulesUnitTurnStartMembership(
        rules_unit_instance_id=rules_unit_instance_id,
        component_memberships=tuple(component_memberships),
    )


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", item)
        for item in cast(tuple[object, ...], value)
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = ("build_primary_rules_unit_membership_from_model_placements",)
