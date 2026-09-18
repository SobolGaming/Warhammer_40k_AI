# pyright: reportPrivateUsage=false
"""Shared physical endpoint authority for every disembark mode and component."""

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportOperationViolation,
    TransportOperationViolationCode,
    _enemy_unit_ids_engaged_with_transport,
    _model_owner_unit_id,
    disembark_mode_kind_from_token,
)
from warhammer40k_core.engine.transports import (
    validate_transport_identifier as _validate_identifier,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_disembark_2026_09 as disembark_source,
)

_EPSILON = 1e-9
DISEMBARK_POLICY = disembark_source.DISEMBARK_POLICY


def append_disembark_endpoint_violations(
    *,
    violations: list[TransportOperationViolation],
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    models: tuple[Model, ...],
    transport_models: tuple[Model, ...],
    distance_inches: float,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    disembark_mode: DisembarkModeKind,
    allowed_enemy_engagement_unit_ids: tuple[str, ...] = (),
) -> None:
    mode = disembark_mode_kind_from_token(disembark_mode)
    placed_models = _placed_geometry_models(scenario)
    own_model_ids = {model.model_id for model in models}
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    enemy_models = tuple(
        blocker
        for blocker in blockers
        if _model_owner_player_id(scenario=scenario, model_instance_id=blocker.model_id)
        != attempted_placement.player_id
    )
    combat_engagement_unit_ids = (
        _enemy_unit_ids_engaged_with_transport(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            transport_models=transport_models,
        )
        if mode is DisembarkModeKind.COMBAT_DISEMBARK
        else ()
    )
    allowed_engagement_units = {
        *combat_engagement_unit_ids,
        *allowed_enemy_engagement_unit_ids,
    }
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Disembark placement crosses the battlefield edge.",
                    model_instance_id=model.model_id,
                    unit_instance_id=attempted_placement.unit_instance_id,
                )
            )
        ordinary_distance = _model_wholly_within_any_transport_model(
            model,
            transport_models=transport_models,
            distance_inches=distance_inches,
        )
        oversized = not ordinary_distance and not any(
            base_fits_disembark_distance(model.base, transport.base, distance_inches)
            for transport in transport_models
        )
        if not ordinary_distance and not (
            oversized
            and any(
                model.range_to(transport) <= DISEMBARK_POLICY.maximum_base_distance_inches
                for transport in transport_models
            )
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.DISEMBARK_DISTANCE,
                    message=(
                        "Disembark needs ordinary containment or proven oversized "
                        "placement within one inch."
                    ),
                    source_rule_id=DISEMBARK_POLICY.source_rule_id,
                    model_instance_id=model.model_id,
                    unit_instance_id=attempted_placement.unit_instance_id,
                )
            )
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    TransportOperationViolation(
                        violation_code=TransportOperationViolationCode.MODEL_OVERLAP,
                        message="Disembark placement overlaps another model.",
                        model_instance_id=model.model_id,
                        blocker_id=blocker.model_id,
                    )
                )
        for enemy_model in enemy_models:
            if model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                enemy_unit_id = rules_unit_view_from_armies(
                    armies=scenario.armies,
                    unit_instance_id=_model_owner_unit_id(
                        scenario=scenario,
                        model_instance_id=enemy_model.model_id,
                    ),
                ).unit_instance_id
                if not oversized and (
                    mode is DisembarkModeKind.EMERGENCY_DISEMBARK
                    or enemy_unit_id in allowed_engagement_units
                ):
                    continue
                violations.append(
                    TransportOperationViolation(
                        violation_code=TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Disembark placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=terrain_features,
            violation_code=TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Disembark placement",
        )
        if terrain_violation is not None:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_marker_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=objective_markers,
            violation_code=TransportOperationViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Disembark placement",
        )
        if objective_marker_violation is not None:
            violations.append(
                TransportOperationViolation(
                    violation_code=(
                        TransportOperationViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP
                    ),
                    message=objective_marker_violation.message,
                    model_instance_id=objective_marker_violation.model_instance_id,
                    blocker_id=objective_marker_violation.blocker_id,
                )
            )
    overlap = _moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.MODEL_OVERLAP,
                message="Disembark placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )


def _model_wholly_within_any_transport_model(
    model: Model,
    *,
    transport_models: tuple[Model, ...],
    distance_inches: float,
) -> bool:
    return any(
        shapely_backend.footprint_for_base(transport_model.base, transport_model.pose)
        .buffer(distance_inches)
        .covers(shapely_backend.footprint_for_base(model.base, model.pose))
        for transport_model in transport_models
    )


def _placed_geometry_models(scenario: BattlefieldScenario) -> tuple[Model, ...]:
    models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(models)


def _model_owner_player_id(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return model_placement.player_id
    raise GameLifecycleError("model_instance_id is not placed.")


def _model_is_within_battlefield(
    model: Model,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    return (
        min_x >= -_EPSILON
        and min_y >= -_EPSILON
        and max_x <= battlefield_width_inches + _EPSILON
        and max_y <= battlefield_depth_inches + _EPSILON
    )


def _models_overlap_with_volume(first: Model, second: Model) -> bool:
    if first.volume.vertical_gap_to(first.pose, second.volume, second.pose) != 0.0:
        return False
    if not _model_pair_can_overlap_horizontally(first, second):
        return False
    return first.base_overlaps(second)


def _moving_models_overlap(models: tuple[Model, ...]) -> tuple[str, str] | None:
    for index, first in enumerate(models):
        for second in models[index + 1 :]:
            if _models_overlap_with_volume(first, second):
                return (first.model_id, second.model_id)
    return None


def _model_pair_can_overlap_horizontally(first: Model, second: Model) -> bool:
    return first.pose.distance_2d_to(second.pose) <= (
        first.base.max_radius() + second.base.max_radius()
    )
