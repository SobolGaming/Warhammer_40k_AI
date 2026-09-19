"""Source-authorized Emergency Disembark maximal, closest, and engaged set-up."""

from __future__ import annotations

from fractions import Fraction

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.transports import (
    TransportOperationViolation,
    TransportOperationViolationCode,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance
from warhammer40k_core.geometry.emergency_disembark_fit import (
    AxisAlignedRectObstacle,
    CircleObstacle,
    CircularEmergencyPoseQuery,
    circular_emergency_pose_exists,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.visibility_algebra import VisibilityComputationError
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_emergency_disembark_placement_2026_09 as placement_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_disembark_2026_09 as oversized_source,
)

PLACEMENT_POLICY = placement_source.PLACEMENT_POLICY
OVERSIZED_POLICY = oversized_source.DISEMBARK_POLICY
_SOURCE_RULE_ID = PLACEMENT_POLICY.source_rule_id


def append_unit_placement_drift_violations(
    *,
    violations: list[TransportOperationViolation],
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    allow_partial: bool,
) -> None:
    if attempted_placement.unit_instance_id != unit.unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Transport placement unit_instance_id does not match unit.",
                unit_instance_id=unit.unit_instance_id,
            )
        )
        return
    attempted_model_ids = tuple(
        sorted(placement.model_instance_id for placement in attempted_placement.model_placements)
    )
    expected_model_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    if allow_partial:
        if set(attempted_model_ids) - set(expected_model_ids):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                    message="Emergency Disembark placement references an unknown model.",
                    unit_instance_id=unit.unit_instance_id,
                )
            )
        return
    if attempted_model_ids != expected_model_ids:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Disembark placement must include every model in the unit.",
                unit_instance_id=unit.unit_instance_id,
            )
        )


def append_emergency_disembark_placement_violations(
    *,
    violations: list[TransportOperationViolation],
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    models: tuple[Model, ...],
    transport_models: tuple[Model, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
) -> None:
    _require_placement_policy()
    _require_circular_models((*models, *transport_models))
    living_models = unit.alive_own_models()
    placed_ids = {placement.model_instance_id for placement in attempted_placement.model_placements}
    omitted = tuple(model for model in living_models if model.model_instance_id not in placed_ids)
    battlefield_models, enemies = _battlefield_models(
        scenario=scenario,
        player_id=attempted_placement.player_id,
        own_model_ids=placed_ids,
        transport_models=transport_models,
    )
    neighbor_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_horizontal_inches,
        "max_horizontal_inches",
    )
    vertical_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_vertical_inches,
        "max_vertical_inches",
    )
    span_limit = (
        None
        if ruleset_descriptor.coherency_policy.max_unit_span_inches is None
        else Fraction(str(ruleset_descriptor.coherency_policy.max_unit_span_inches))
    )
    engagement = Fraction(str(ruleset_descriptor.engagement_policy.horizontal_inches))
    engagement_vertical = Fraction(str(ruleset_descriptor.engagement_policy.vertical_inches))
    try:
        for omitted_model in omitted:
            passenger = _geometry_model_from_instance(omitted_model)
            if _omitted_model_is_placeable(
                passenger=passenger,
                transport_models=transport_models,
                blocker_models=(*battlefield_models, *models),
                enemy_models=enemies,
                partner_models=models,
                neighbor_limit=neighbor_limit,
                vertical_limit=vertical_limit,
                span_limit=span_limit,
                engagement=engagement,
                engagement_vertical=engagement_vertical,
                terrain_features=terrain_features,
                objective_markers=objective_markers,
                battlefield_width_inches=battlefield_width_inches,
                battlefield_depth_inches=battlefield_depth_inches,
            ):
                violations.append(
                    TransportOperationViolation(
                        violation_code=(
                            TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
                        ),
                        message="Emergency Disembark omitted a model that can still be set up.",
                        model_instance_id=omitted_model.model_instance_id,
                        unit_instance_id=unit.unit_instance_id,
                        source_rule_id=_SOURCE_RULE_ID,
                    )
                )
        for placed in models:
            others = tuple(model for model in models if model.model_id != placed.model_id)
            _append_placed_model_violations(
                violations=violations,
                unit=unit,
                placed=placed,
                transport_models=transport_models,
                blocker_models=(*battlefield_models, *others),
                enemy_models=enemies,
                partner_models=others,
                neighbor_limit=neighbor_limit,
                vertical_limit=vertical_limit,
                span_limit=span_limit,
                engagement=engagement,
                engagement_vertical=engagement_vertical,
                terrain_features=terrain_features,
                objective_markers=objective_markers,
                ruleset_descriptor=ruleset_descriptor,
                battlefield_width_inches=battlefield_width_inches,
                battlefield_depth_inches=battlefield_depth_inches,
            )
    except VisibilityComputationError as exc:
        raise GameLifecycleError("Emergency Disembark placement proof is unresolved.") from exc
    except GeometryError as exc:
        raise GameLifecycleError(str(exc)) from exc


def _append_placed_model_violations(
    *,
    violations: list[TransportOperationViolation],
    unit: UnitInstance,
    placed: Model,
    transport_models: tuple[Model, ...],
    blocker_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    vertical_limit: Fraction,
    span_limit: Fraction | None,
    engagement: Fraction,
    engagement_vertical: Fraction,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    ruleset_descriptor: RulesetDescriptor,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> None:
    ordinary = _ordinary_size_fits(placed, transport_models)
    unengaged_exists = _pose_exists(
        passenger=placed,
        transport_models=transport_models,
        blocker_models=blocker_models,
        enemy_models=enemy_models,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        vertical_limit=vertical_limit,
        span_limit=span_limit,
        engagement=engagement,
        engagement_vertical=engagement_vertical,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=True,
        ordinary_size_fit=ordinary,
        closer_than_center=None,
    )
    engaged = _model_is_engaged(placed, enemy_models, ruleset_descriptor)
    if ordinary and unengaged_exists and engaged:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
                message=(
                    "Emergency Disembark must remain unengaged when an unengaged set-up exists."
                ),
                model_instance_id=placed.model_id,
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=_SOURCE_RULE_ID,
            )
        )
    require_unengaged = (not ordinary) or unengaged_exists
    if _closer_pose_exists(
        passenger=placed,
        transport_models=transport_models,
        blocker_models=blocker_models,
        enemy_models=enemy_models,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        vertical_limit=vertical_limit,
        span_limit=span_limit,
        engagement=engagement,
        engagement_vertical=engagement_vertical,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=require_unengaged,
        ordinary_size_fit=ordinary,
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST,
                message="Emergency Disembark must set up as close as possible to the Transport.",
                model_instance_id=placed.model_id,
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=_SOURCE_RULE_ID,
            )
        )


def _omitted_model_is_placeable(
    *,
    passenger: Model,
    transport_models: tuple[Model, ...],
    blocker_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    vertical_limit: Fraction,
    span_limit: Fraction | None,
    engagement: Fraction,
    engagement_vertical: Fraction,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    ordinary = _ordinary_size_fits(passenger, transport_models)
    if _pose_exists(
        passenger=passenger,
        transport_models=transport_models,
        blocker_models=blocker_models,
        enemy_models=enemy_models,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        vertical_limit=vertical_limit,
        span_limit=span_limit,
        engagement=engagement,
        engagement_vertical=engagement_vertical,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=True,
        ordinary_size_fit=ordinary,
        closer_than_center=None,
    ):
        return True
    if not ordinary:
        return False
    return _pose_exists(
        passenger=passenger,
        transport_models=transport_models,
        blocker_models=blocker_models,
        enemy_models=enemy_models,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        vertical_limit=vertical_limit,
        span_limit=span_limit,
        engagement=engagement,
        engagement_vertical=engagement_vertical,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=False,
        ordinary_size_fit=True,
        closer_than_center=None,
    )


def _closer_pose_exists(
    *,
    passenger: Model,
    transport_models: tuple[Model, ...],
    blocker_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    vertical_limit: Fraction,
    span_limit: Fraction | None,
    engagement: Fraction,
    engagement_vertical: Fraction,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    require_unengaged: bool,
    ordinary_size_fit: bool,
) -> bool:
    nearest = _nearest_transport(passenger, transport_models)
    closer_than = Fraction(str(passenger.pose.distance_2d_to(nearest.pose))) - Fraction(
        str(PLACEMENT_POLICY.closest_tolerance_inches)
    )
    if closer_than <= 0:
        return False
    return _pose_exists(
        passenger=passenger,
        transport_models=transport_models,
        blocker_models=blocker_models,
        enemy_models=enemy_models,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        vertical_limit=vertical_limit,
        span_limit=span_limit,
        engagement=engagement,
        engagement_vertical=engagement_vertical,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=require_unengaged,
        ordinary_size_fit=ordinary_size_fit,
        closer_than_center=closer_than,
    )


def _pose_exists(
    *,
    passenger: Model,
    transport_models: tuple[Model, ...],
    blocker_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    vertical_limit: Fraction,
    span_limit: Fraction | None,
    engagement: Fraction,
    engagement_vertical: Fraction,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    require_unengaged: bool,
    ordinary_size_fit: bool,
    closer_than_center: Fraction | None,
) -> bool:
    passenger_radius = Fraction(str(_circular_radius(passenger)))
    coherent_partners = tuple(
        model
        for model in partner_models
        if _vertical_gap_between(passenger, model) <= float(vertical_limit)
    )
    overlapping = (
        _circle_from_model(model) for model in blocker_models if _shares_elevation(passenger, model)
    )
    overlap_obstacles = (*overlapping, *_objective_circles(passenger, objective_markers))
    unengaged_obstacles = tuple(
        (_circle_from_model(enemy), engagement)
        for enemy in enemy_models
        if _vertical_gap_between(passenger, enemy) <= float(engagement_vertical)
    )
    neighbors = tuple((_circle_from_model(model), neighbor_limit) for model in coherent_partners)
    spans = (
        ()
        if span_limit is None
        else tuple((_circle_from_model(model), span_limit) for model in coherent_partners)
    )
    setup = Fraction(str(PLACEMENT_POLICY.setup_distance_inches))
    oversized = Fraction(str(OVERSIZED_POLICY.maximum_base_distance_inches))
    for transport in transport_models:
        transport_radius = Fraction(str(_circular_radius(transport)))
        containment = (
            transport_radius + setup - passenger_radius
            if ordinary_size_fit
            else transport_radius + passenger_radius + oversized
        )
        query = CircularEmergencyPoseQuery(
            transport_x=Fraction(str(transport.pose.position.x)),
            transport_y=Fraction(str(transport.pose.position.y)),
            transport_radius=transport_radius,
            passenger_radius=passenger_radius,
            containment_center_limit=containment,
            battlefield_width=Fraction(str(battlefield_width_inches)),
            battlefield_depth=Fraction(str(battlefield_depth_inches)),
            overlap_obstacles=overlap_obstacles,
            unengaged_obstacles=unengaged_obstacles,
            require_unengaged=require_unengaged,
            closer_than_center=closer_than_center,
            neighbor_obstacles=neighbors,
            span_obstacles=spans,
            rect_obstacles=_terrain_wall_rects(
                terrain_features=terrain_features,
                passenger=passenger,
                transport=transport,
                containment_center_limit=containment,
                closer_than_center=closer_than_center,
            ),
        )
        if circular_emergency_pose_exists(query):
            return True
    return False


def append_emergency_disembark_rules_unit_omission_violations(
    *,
    violations: list[TransportOperationViolation],
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    attempted_placement: RulesUnitPlacement,
    transport_placement: UnitPlacement,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
) -> None:
    _require_placement_policy()
    placed_ids = {placement.model_instance_id for placement in attempted_placement.model_placements}
    placed_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in attempted_placement.model_placements
    )
    transport_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in transport_placement.model_placements
    )
    _require_circular_models((*placed_models, *transport_models))
    battlefield_models, enemies = _battlefield_models(
        scenario=scenario,
        player_id=attempted_placement.player_id,
        own_model_ids=placed_ids,
        transport_models=transport_models,
    )
    neighbor_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_horizontal_inches,
        "max_horizontal_inches",
    )
    vertical_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_vertical_inches,
        "max_vertical_inches",
    )
    span_limit = (
        None
        if ruleset_descriptor.coherency_policy.max_unit_span_inches is None
        else Fraction(str(ruleset_descriptor.coherency_policy.max_unit_span_inches))
    )
    engagement = Fraction(str(ruleset_descriptor.engagement_policy.horizontal_inches))
    engagement_vertical = Fraction(str(ruleset_descriptor.engagement_policy.vertical_inches))
    try:
        for omitted_model in rules_unit.alive_models():
            if omitted_model.model_instance_id in placed_ids:
                continue
            passenger = _geometry_model_from_instance(omitted_model)
            if _omitted_model_is_placeable(
                passenger=passenger,
                transport_models=transport_models,
                blocker_models=(*battlefield_models, *placed_models),
                enemy_models=enemies,
                partner_models=placed_models,
                neighbor_limit=neighbor_limit,
                vertical_limit=vertical_limit,
                span_limit=span_limit,
                engagement=engagement,
                engagement_vertical=engagement_vertical,
                terrain_features=terrain_features,
                objective_markers=objective_markers,
                battlefield_width_inches=battlefield_width_inches,
                battlefield_depth_inches=battlefield_depth_inches,
            ):
                violations.append(
                    TransportOperationViolation(
                        violation_code=(
                            TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
                        ),
                        message="Emergency Disembark omitted a model that can still be set up.",
                        model_instance_id=omitted_model.model_instance_id,
                        unit_instance_id=rules_unit.unit_instance_id,
                        source_rule_id=_SOURCE_RULE_ID,
                    )
                )
    except VisibilityComputationError as exc:
        raise GameLifecycleError("Emergency Disembark placement proof is unresolved.") from exc
    except GeometryError as exc:
        raise GameLifecycleError(str(exc)) from exc


def _battlefield_models(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    own_model_ids: set[str],
    transport_models: tuple[Model, ...],
) -> tuple[tuple[Model, ...], tuple[Model, ...]]:
    transport_ids = {model.model_id for model in transport_models}
    blockers: list[Model] = []
    enemies: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for placement in unit_placement.model_placements:
                if (
                    placement.model_instance_id in own_model_ids
                    or placement.model_instance_id in transport_ids
                ):
                    continue
                model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                blockers.append(model)
                if placement.player_id != player_id:
                    enemies.append(model)
    return tuple(blockers), tuple(enemies)


def _ordinary_size_fits(model: Model, transport_models: tuple[Model, ...]) -> bool:
    distance = float(PLACEMENT_POLICY.setup_distance_inches)
    return any(
        base_fits_disembark_distance(model.base, transport.base, distance)
        for transport in transport_models
    )


def _geometry_model_from_instance(model: ModelInstance) -> Model:
    return Model(
        model_id=model.model_instance_id,
        pose=Pose.at(0.0, 0.0),
        base=model.geometry.base_shape(),
        volume=ModelVolume(height=model.geometry.height_inches),
    )


def _circle_from_model(model: Model) -> CircleObstacle:
    return CircleObstacle(
        x=Fraction(str(model.pose.position.x)),
        y=Fraction(str(model.pose.position.y)),
        radius=Fraction(str(_circular_radius(model))),
    )


def _circular_radius(model: Model) -> float:
    base = model.base
    if type(base) is not CircularBase:
        raise GeometryError("Emergency Disembark placement requires circular bases.")
    return base.radius


def _require_circular_models(models: tuple[Model, ...]) -> None:
    for model in models:
        _circular_radius(model)


def _nearest_transport(passenger: Model, transport_models: tuple[Model, ...]) -> Model:
    if not transport_models:
        raise GameLifecycleError("Emergency Disembark placement requires a Transport model.")
    return min(
        transport_models,
        key=lambda transport: passenger.pose.distance_2d_to(transport.pose),
    )


def _model_is_engaged(
    model: Model,
    enemies: tuple[Model, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    policy = ruleset_descriptor.engagement_policy
    return any(
        model.is_within_engagement_range(
            enemy,
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        )
        for enemy in enemies
    )


def _shares_elevation(passenger: Model, other: Model) -> bool:
    return _vertical_gap_between(passenger, other) == 0.0


def _vertical_gap_between(passenger: Model, other: Model) -> float:
    return passenger.volume.vertical_gap_to(passenger.pose, other.volume, other.pose)


def _objective_circles(
    passenger: Model,
    objective_markers: tuple[ObjectiveMarker, ...],
) -> tuple[CircleObstacle, ...]:
    passenger_interval = passenger.volume.vertical_interval(passenger.pose)
    circles: list[CircleObstacle] = []
    for marker in objective_markers:
        if not marker.blocks_placement:
            continue
        if _interval_gap(passenger_interval, (marker.z_inches, marker.z_inches)) != 0.0:
            continue
        circles.append(
            CircleObstacle(
                x=Fraction(str(marker.x_inches)),
                y=Fraction(str(marker.y_inches)),
                radius=Fraction(str(marker.marker_diameter_inches)) / 2,
            )
        )
    return tuple(circles)


def _terrain_wall_rects(
    *,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    passenger: Model,
    transport: Model,
    containment_center_limit: Fraction,
    closer_than_center: Fraction | None,
) -> tuple[AxisAlignedRectObstacle, ...]:
    passenger_interval = passenger.volume.vertical_interval(passenger.pose)
    passenger_radius = Fraction(str(_circular_radius(passenger)))
    search = containment_center_limit + passenger_radius
    if closer_than_center is not None:
        search = min(search, closer_than_center + passenger_radius)
    transport_x = Fraction(str(transport.pose.position.x))
    transport_y = Fraction(str(transport.pose.position.y))
    rects: list[AxisAlignedRectObstacle] = []
    for feature in terrain_features:
        for wall in feature.walls:
            wall_interval = (wall.bottom_z_inches, wall.bottom_z_inches + wall.height_inches)
            if _interval_gap(passenger_interval, wall_interval) != 0.0:
                continue
            min_x, min_y, max_x, max_y = wall.bounds()
            if not _aabb_reaches_disk(
                min_x=min_x,
                min_y=min_y,
                max_x=max_x,
                max_y=max_y,
                center_x=float(transport_x),
                center_y=float(transport_y),
                radius=float(search),
            ):
                continue
            if not _is_cardinal_rotation(wall.rotation_degrees):
                raise VisibilityComputationError(
                    "Emergency Disembark terrain proof requires a cardinal wall."
                )
            rects.append(
                AxisAlignedRectObstacle(
                    min_x=Fraction(str(min_x)),
                    max_x=Fraction(str(max_x)),
                    min_y=Fraction(str(min_y)),
                    max_y=Fraction(str(max_y)),
                )
            )
    return tuple(rects)


def _is_cardinal_rotation(degrees: float) -> bool:
    return degrees % 180.0 in {0.0, 90.0}


def _aabb_reaches_disk(
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    center_x: float,
    center_y: float,
    radius: float,
) -> bool:
    dx = 0.0
    if center_x < min_x:
        dx = min_x - center_x
    elif center_x > max_x:
        dx = center_x - max_x
    dy = 0.0
    if center_y < min_y:
        dy = min_y - center_y
    elif center_y > max_y:
        dy = center_y - max_y
    return dx * dx + dy * dy <= radius * radius


def _interval_gap(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_bottom, first_top = first
    second_bottom, second_top = second
    if first_top < second_bottom:
        return second_bottom - first_top
    if second_top < first_bottom:
        return first_bottom - second_top
    return 0.0


def _required_inches(value: float | None, field_name: str) -> Fraction:
    if value is None:
        raise GameLifecycleError(f"Emergency Disembark coherency requires {field_name}.")
    return Fraction(str(value))


def _require_placement_policy() -> None:
    if (
        PLACEMENT_POLICY.setup_distance_inches != 6
        or PLACEMENT_POLICY.requires_closest_possible is not True
        or PLACEMENT_POLICY.prefers_unengaged is not True
        or PLACEMENT_POLICY.allows_engaged_when_unengaged_impossible is not True
        or PLACEMENT_POLICY.destroys_only_unplaceable_models is not True
    ):
        raise GameLifecycleError("Emergency Disembark placement policy drifted.")
    if OVERSIZED_POLICY.maximum_base_distance_inches != 1:
        raise GameLifecycleError("Emergency Disembark oversized distance policy drifted.")
