"""Source-authorized Emergency Disembark maximal, closest, and engaged set-up."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainEndpointSupportPolicy,
)
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
from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance
from warhammer40k_core.geometry.emergency_setup_proof import (
    EmergencySetupQuery,
    SetupTerrain,
    emergency_setup_pose_exists,
    emergency_setup_pose_is_legal,
)
from warhammer40k_core.geometry.placement_predicates import rational
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
    attempted_ids = tuple(
        sorted(row.model_instance_id for row in attempted_placement.model_placements)
    )
    expected_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    invalid = (
        bool(set(attempted_ids) - set(expected_ids))
        if allow_partial
        else attempted_ids != expected_ids
    )
    if invalid:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Emergency Disembark placement references an unknown model."
                if allow_partial
                else "Disembark placement must include every model in the unit.",
                unit_instance_id=unit.unit_instance_id,
            )
        )


@dataclass(frozen=True, slots=True)
class _PlacementContext:
    ruleset: RulesetDescriptor
    transports: tuple[Model, ...]
    models: tuple[Model, ...]
    blockers: tuple[Model, ...]
    enemies: tuple[Model, ...]
    terrain: tuple[TerrainFeatureDefinition, ...]
    objectives: tuple[ObjectiveMarker, ...]
    width: float
    depth: float

    def query(self, passenger: Model, unit: UnitInstance) -> EmergencySetupQuery:
        ordinary = any(
            base_fits_disembark_distance(
                passenger.base, transport.base, float(PLACEMENT_POLICY.setup_distance_inches)
            )
            for transport in self.transports
        )
        partners = tuple(model for model in self.models if model.model_id != passenger.model_id)
        policy = self.ruleset.coherency_policy
        required_neighbors = (
            policy.required_neighbors_large_unit
            if policy.large_unit_model_count_threshold is not None
            and len(partners) + 1 >= policy.large_unit_model_count_threshold
            else policy.required_neighbors_small_unit
        )
        if required_neighbors is None:
            raise GameLifecycleError(
                "Emergency Disembark requires a neighbor-count coherency policy."
            )
        return EmergencySetupQuery(
            passenger=passenger,
            transports=self.transports,
            blockers=(*self.blockers, *partners),
            enemies=self.enemies,
            partners=partners,
            terrain=tuple(_setup_terrain(feature, unit, self.ruleset) for feature in self.terrain),
            objective_disks=tuple(
                (
                    marker.x_inches,
                    marker.y_inches,
                    marker.z_inches,
                    marker.marker_diameter_inches / 2,
                )
                for marker in self.objectives
                if marker.blocks_placement
            ),
            width=rational(self.width),
            depth=rational(self.depth),
            neighbor_limit=_required_inches(policy.max_horizontal_inches, "max_horizontal_inches"),
            vertical_limit=_required_inches(policy.max_vertical_inches, "max_vertical_inches"),
            span_limit=None
            if policy.max_unit_span_inches is None
            else rational(policy.max_unit_span_inches),
            engagement=rational(self.ruleset.engagement_policy.horizontal_inches),
            engagement_vertical=rational(self.ruleset.engagement_policy.vertical_inches),
            setup_distance=Fraction(PLACEMENT_POLICY.setup_distance_inches),
            oversized_distance=rational(OVERSIZED_POLICY.maximum_base_distance_inches),
            ordinary_size_fit=ordinary,
            require_unengaged=not ordinary,
            closer_than=None,
            closest_tolerance=rational(PLACEMENT_POLICY.closest_tolerance_inches),
            required_neighbors=required_neighbors,
        )


def _setup_terrain(
    feature: TerrainFeatureDefinition,
    unit: UnitInstance,
    ruleset: RulesetDescriptor,
) -> SetupTerrain:
    policy = ruleset.terrain_movement_policy.policy_for_feature_kind(feature.feature_kind)
    allowed = policy.endpoint_support_policy is not TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP
    return SetupTerrain(
        feature=feature,
        ground_allowed=allowed,
        elevated_allowed=allowed
        and policy.endpoint_support_policy
        is not TerrainEndpointSupportPolicy.ALLOWED_ON_GROUND_FLOOR_ONLY
        and (
            not policy.ground_floor_only_unless_keyword
            or bool(set(unit.keywords).intersection(policy.upper_floor_allowed_keywords))
        ),
        no_overhang=policy.no_overhang_required,
        ground_containment=policy.endpoint_support_policy
        is TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
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
    rules_unit_placement: RulesUnitPlacement | None = None,
) -> None:
    physical_models = (
        models
        if rules_unit_placement is None
        else tuple(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(row), placement=row
            )
            for row in rules_unit_placement.model_placements
        )
    )
    context = _context(
        scenario,
        ruleset_descriptor,
        attempted_placement.player_id,
        physical_models,
        transport_models,
        terrain_features,
        objective_markers,
        battlefield_width_inches,
        battlefield_depth_inches,
    )
    placed_ids = {model.model_id for model in models}
    for instance in unit.alive_own_models():
        if instance.model_instance_id not in placed_ids:
            _append_omission(violations, context, instance, unit, unit.unit_instance_id)
    for model in models:
        query = context.query(model, unit)
        if not _exists(query, submitted=True):
            violations.append(
                _violation(
                    TransportOperationViolationCode.EMERGENCY_DISEMBARK_ENDPOINT_ILLEGAL,
                    "Emergency Disembark endpoint fails the legal set-up geometry proof.",
                    model.model_id,
                    unit.unit_instance_id,
                )
            )
            continue
        unengaged_exists = _exists(replace(query, require_unengaged=True))
        policy = ruleset_descriptor.engagement_policy
        if unengaged_exists and any(
            model.is_within_engagement_range(
                enemy,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            )
            for enemy in context.enemies
        ):
            violations.append(
                _violation(
                    TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
                    "Emergency Disembark must remain unengaged when an unengaged set-up exists.",
                    model.model_id,
                    unit.unit_instance_id,
                )
            )
        if _exists(
            replace(
                query,
                require_unengaged=not query.ordinary_size_fit or unengaged_exists,
                closer_than=model,
            )
        ):
            violations.append(
                _violation(
                    TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST,
                    "Emergency Disembark must set up as close as possible to the Transport.",
                    model.model_id,
                    unit.unit_instance_id,
                )
            )


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
    models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(row), placement=row
        )
        for row in attempted_placement.model_placements
    )
    transports = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(row), placement=row
        )
        for row in transport_placement.model_placements
    )
    context = _context(
        scenario,
        ruleset_descriptor,
        attempted_placement.player_id,
        models,
        transports,
        terrain_features,
        objective_markers,
        battlefield_width_inches,
        battlefield_depth_inches,
    )
    placed_ids = {model.model_id for model in models}
    for model in rules_unit.alive_models():
        if model.model_instance_id not in placed_ids:
            _append_omission(
                violations,
                context,
                model,
                rules_unit.component_unit_for_model(model.model_instance_id),
                rules_unit.unit_instance_id,
            )


def _append_omission(
    violations: list[TransportOperationViolation],
    context: _PlacementContext,
    model: ModelInstance,
    unit: UnitInstance,
    rules_unit_id: str,
) -> None:
    passenger = Model(
        model_id=model.model_instance_id,
        pose=Pose.at(0, 0),
        base=model.geometry.base_shape(),
        volume=ModelVolume(height=model.geometry.height_inches),
    )
    if _exists(context.query(passenger, unit)):
        violations.append(
            _violation(
                TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE,
                "Emergency Disembark omitted a model that can still be set up.",
                model.model_instance_id,
                rules_unit_id,
            )
        )


def _exists(query: EmergencySetupQuery, *, submitted: bool = False) -> bool:
    try:
        return (
            emergency_setup_pose_is_legal(query)
            if submitted
            else emergency_setup_pose_exists(query)
        )
    except VisibilityComputationError as exc:
        raise GameLifecycleError("Emergency Disembark placement proof is unresolved.") from exc
    except GeometryError as exc:
        raise GameLifecycleError(str(exc)) from exc


def _violation(
    code: TransportOperationViolationCode,
    message: str,
    model_id: str,
    unit_id: str,
) -> TransportOperationViolation:
    return TransportOperationViolation(
        violation_code=code,
        message=message,
        model_instance_id=model_id,
        unit_instance_id=unit_id,
        source_rule_id=_SOURCE_RULE_ID,
    )


def _context(
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    player_id: str,
    models: tuple[Model, ...],
    transports: tuple[Model, ...],
    terrain: tuple[TerrainFeatureDefinition, ...],
    objectives: tuple[ObjectiveMarker, ...],
    width: float,
    depth: float,
) -> _PlacementContext:
    _require_placement_policy()
    excluded_ids = {model.model_id for model in (*models, *transports)}
    blockers: list[Model] = []
    enemies: list[Model] = []
    for army in scenario.battlefield_state.placed_armies:
        for unit in army.unit_placements:
            for row in unit.model_placements:
                if row.model_instance_id in excluded_ids:
                    continue
                model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(row), placement=row
                )
                blockers.append(model)
                if row.player_id != player_id:
                    enemies.append(model)
    return _PlacementContext(
        ruleset,
        transports,
        models,
        tuple(blockers),
        tuple(enemies),
        terrain,
        objectives,
        width,
        depth,
    )


def _required_inches(value: float | None, field_name: str) -> Fraction:
    if value is None:
        raise GameLifecycleError(f"Emergency Disembark coherency requires {field_name}.")
    return rational(value)


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
