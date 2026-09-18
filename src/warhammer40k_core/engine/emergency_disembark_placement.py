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
    CircleObstacle,
    CircularEmergencyPoseQuery,
    circular_emergency_pose_exists,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
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
    objective_markers: tuple[ObjectiveMarker, ...],
) -> None:
    _require_placement_policy()
    _require_circular_models((*models, *transport_models))
    living_models = unit.alive_own_models()
    placed_ids = {placement.model_instance_id for placement in attempted_placement.model_placements}
    omitted = tuple(model for model in living_models if model.model_instance_id not in placed_ids)
    battlefield_blockers, enemies = _battlefield_circles(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        player_id=attempted_placement.player_id,
        own_model_ids=placed_ids,
        objective_markers=objective_markers,
        transport_models=transport_models,
    )
    neighbor_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_horizontal_inches,
        "max_horizontal_inches",
    )
    span_limit = (
        None
        if ruleset_descriptor.coherency_policy.max_unit_span_inches is None
        else Fraction(str(ruleset_descriptor.coherency_policy.max_unit_span_inches))
    )
    try:
        for omitted_model in omitted:
            passenger = _geometry_model_from_instance(omitted_model)
            if _omitted_model_is_placeable(
                passenger=passenger,
                transport_models=transport_models,
                blockers=(*battlefield_blockers, *(_circle_from_model(model) for model in models)),
                enemies=enemies,
                partner_models=models,
                neighbor_limit=neighbor_limit,
                span_limit=span_limit,
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
            blockers = (
                *battlefield_blockers,
                *(_circle_from_model(model) for model in others),
            )
            _append_placed_model_violations(
                violations=violations,
                unit=unit,
                placed=placed,
                transport_models=transport_models,
                blockers=blockers,
                enemies=enemies,
                partner_models=others,
                neighbor_limit=neighbor_limit,
                span_limit=span_limit,
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
    blockers: tuple[CircleObstacle, ...],
    enemies: tuple[tuple[CircleObstacle, Fraction], ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    span_limit: Fraction | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> None:
    ordinary = _ordinary_size_fits(placed, transport_models)
    unengaged_exists = _pose_exists(
        passenger=placed,
        transport_models=transport_models,
        blockers=blockers,
        enemies=enemies,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        span_limit=span_limit,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        require_unengaged=True,
        ordinary_size_fit=ordinary,
        closer_than_center=None,
    )
    if ordinary and unengaged_exists and _model_is_engaged(placed, enemies):
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
        blockers=blockers,
        enemies=enemies,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        span_limit=span_limit,
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
    blockers: tuple[CircleObstacle, ...],
    enemies: tuple[tuple[CircleObstacle, Fraction], ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    span_limit: Fraction | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    ordinary = _ordinary_size_fits(passenger, transport_models)
    if _pose_exists(
        passenger=passenger,
        transport_models=transport_models,
        blockers=blockers,
        enemies=enemies,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        span_limit=span_limit,
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
        blockers=blockers,
        enemies=enemies,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        span_limit=span_limit,
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
    blockers: tuple[CircleObstacle, ...],
    enemies: tuple[tuple[CircleObstacle, Fraction], ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    span_limit: Fraction | None,
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
        blockers=blockers,
        enemies=enemies,
        partner_models=partner_models,
        neighbor_limit=neighbor_limit,
        span_limit=span_limit,
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
    blockers: tuple[CircleObstacle, ...],
    enemies: tuple[tuple[CircleObstacle, Fraction], ...],
    partner_models: tuple[Model, ...],
    neighbor_limit: Fraction,
    span_limit: Fraction | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    require_unengaged: bool,
    ordinary_size_fit: bool,
    closer_than_center: Fraction | None,
) -> bool:
    passenger_radius = Fraction(str(_circular_radius(passenger)))
    neighbors = tuple((_circle_from_model(model), neighbor_limit) for model in partner_models)
    spans = (
        ()
        if span_limit is None
        else tuple((_circle_from_model(model), span_limit) for model in partner_models)
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
            overlap_obstacles=blockers,
            unengaged_obstacles=enemies,
            require_unengaged=require_unengaged,
            closer_than_center=closer_than_center,
            neighbor_obstacles=neighbors,
            span_obstacles=spans,
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
    battlefield_blockers, enemies = _battlefield_circles(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        player_id=attempted_placement.player_id,
        own_model_ids=placed_ids,
        objective_markers=objective_markers,
        transport_models=transport_models,
    )
    neighbor_limit = _required_inches(
        ruleset_descriptor.coherency_policy.max_horizontal_inches,
        "max_horizontal_inches",
    )
    span_limit = (
        None
        if ruleset_descriptor.coherency_policy.max_unit_span_inches is None
        else Fraction(str(ruleset_descriptor.coherency_policy.max_unit_span_inches))
    )
    blockers = (*battlefield_blockers, *(_circle_from_model(model) for model in placed_models))
    try:
        for omitted_model in rules_unit.alive_models():
            if omitted_model.model_instance_id in placed_ids:
                continue
            passenger = _geometry_model_from_instance(omitted_model)
            if _omitted_model_is_placeable(
                passenger=passenger,
                transport_models=transport_models,
                blockers=blockers,
                enemies=enemies,
                partner_models=placed_models,
                neighbor_limit=neighbor_limit,
                span_limit=span_limit,
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


def _battlefield_circles(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    player_id: str,
    own_model_ids: set[str],
    objective_markers: tuple[ObjectiveMarker, ...],
    transport_models: tuple[Model, ...],
) -> tuple[tuple[CircleObstacle, ...], tuple[tuple[CircleObstacle, Fraction], ...]]:
    transport_ids = {model.model_id for model in transport_models}
    engagement = Fraction(str(ruleset_descriptor.engagement_policy.horizontal_inches))
    blockers: list[CircleObstacle] = []
    enemies: list[tuple[CircleObstacle, Fraction]] = []
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
                circle = _circle_from_model(model)
                blockers.append(circle)
                if placement.player_id != player_id:
                    enemies.append((circle, engagement))
    for marker in objective_markers:
        if not marker.blocks_placement:
            continue
        blockers.append(
            CircleObstacle(
                x=Fraction(str(marker.x_inches)),
                y=Fraction(str(marker.y_inches)),
                radius=Fraction(str(marker.marker_diameter_inches)) / 2,
            )
        )
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
    enemies: tuple[tuple[CircleObstacle, Fraction], ...],
) -> bool:
    radius = _circular_radius(model)
    for obstacle, engagement in enemies:
        center = model.pose.distance_2d_to(
            Pose.at(float(obstacle.x), float(obstacle.y), model.pose.position.z)
        )
        if max(0.0, center - radius - float(obstacle.radius)) <= float(engagement):
            return True
    return False


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
