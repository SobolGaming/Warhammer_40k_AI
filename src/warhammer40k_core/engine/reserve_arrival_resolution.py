"""Oversized reserve setup through shared engine-owned validation."""

from __future__ import annotations

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
)
from warhammer40k_core.core.objectives import (
    ObjectiveMarker,
)
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    UnitPlacement,
    battlefield_placement_kind_from_token,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
)

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.reserves import (
    _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    _RESERVE_ENEMY_DISTANCE_INCHES,
    LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
    LargeModelReservePlacementException,
    ReinforcementPlacement,
    ReserveArrivalCandidate,
    ReservePlacementViolation,
    ReservePlacementViolationCode,
    ReserveState,
    StrategicReserveRule,
    _validate_large_model_exception_tuple,
    _validate_positive_int,
    _validate_positive_number,
    _validate_reserve_placement_violation_tuple,
    append_common_reserve_placement_violations,
    append_enemy_deployment_zone_violations,
    append_reserve_state_violations,
    append_strategic_reserves_edge_violations,
    append_unit_placement_drift_violations,
    reserve_arrival_transition_batch,
    source_rule_id_for_placement_kind,
    validate_deployment_zone_tuple,
    validate_objective_marker_tuple,
    validate_terrain_feature_tuple,
)
from warhammer40k_core.engine.rules_unit_placement import (
    RulesUnitPlacement,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyContext,
)
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_setup_2026_09 as large_model_source,
)


def resolve_reserve_arrival(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    reserve_state: ReserveState,
    attempted_placement: UnitPlacement | RulesUnitPlacement,
    battle_round: int,
    placement_kind: BattlefieldPlacementKind,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    enemy_deployment_zones: tuple[DeploymentZone, ...] = (),
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = (),
    strategic_reserve_rule: StrategicReserveRule | None = None,
    deep_strike_enemy_horizontal_distance_inches: float | None = None,
    additional_violations: tuple[ReservePlacementViolation, ...] = (),
) -> ReinforcementPlacement:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("resolve_reserve_arrival scenario must be a scenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("resolve_reserve_arrival requires a RulesetDescriptor.")
    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("resolve_reserve_arrival reserve_state must be ReserveState.")
    if type(attempted_placement) is UnitPlacement:
        rules_unit_placement = RulesUnitPlacement.single(attempted_placement)
    elif type(attempted_placement) is RulesUnitPlacement:
        rules_unit_placement = attempted_placement
    else:
        raise GameLifecycleError(
            "resolve_reserve_arrival attempted_placement must be UnitPlacement or "
            "RulesUnitPlacement."
        )
    placement_kind = battlefield_placement_kind_from_token(placement_kind)
    requested_round = _validate_positive_int("battle_round", battle_round)
    width = _validate_positive_number("battlefield_width_inches", battlefield_width_inches)
    depth = _validate_positive_number("battlefield_depth_inches", battlefield_depth_inches)
    features = validate_terrain_feature_tuple("terrain_features", terrain_features)
    markers = validate_objective_marker_tuple("objective_markers", objective_markers)
    deployment_zones = validate_deployment_zone_tuple(
        "enemy_deployment_zones",
        enemy_deployment_zones,
    )
    exceptions = _validate_large_model_exception_tuple(
        "large_model_exceptions",
        large_model_exceptions,
    )
    supplied_violations = _validate_reserve_placement_violation_tuple(
        "additional_violations",
        additional_violations,
    )
    strategic_rule = strategic_reserve_rule or StrategicReserveRule()
    if type(strategic_rule) is not StrategicReserveRule:
        raise GameLifecycleError("strategic_reserve_rule must be a StrategicReserveRule.")
    deep_strike_enemy_distance = (
        None
        if deep_strike_enemy_horizontal_distance_inches is None
        else _validate_positive_number(
            "deep_strike_enemy_horizontal_distance_inches",
            deep_strike_enemy_horizontal_distance_inches,
        )
    )
    if (
        deep_strike_enemy_distance is not None
        and placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE
    ):
        raise GameLifecycleError(
            "deep_strike_enemy_horizontal_distance_inches only applies to Deep Strike placement."
        )

    view = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=reserve_state.unit_instance_id,
    )
    qualifying_edges = strategic_rule.qualifying_edges_for_battle_round(requested_round)
    candidate = ReserveArrivalCandidate(
        reserve_state=reserve_state,
        battle_round=requested_round,
        placement_kind=placement_kind,
        attempted_rules_unit_placement=rules_unit_placement,
        qualifying_edges=qualifying_edges,
        large_model_exceptions=exceptions,
    )
    violations: list[ReservePlacementViolation] = list(supplied_violations)
    append_reserve_state_violations(
        violations=violations,
        reserve_state=reserve_state,
        view=view,
        placement_kind=placement_kind,
        battle_round=requested_round,
        mission_policy=ruleset_descriptor.mission_policy,
        strategic_reserve_rule=strategic_rule,
    )
    append_unit_placement_drift_violations(
        violations=violations,
        view=view,
        attempted_rules_unit_placement=rules_unit_placement,
    )

    models = rules_unit_placement.geometry_models(scenario)
    if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES:
        append_strategic_reserves_edge_violations(
            violations=violations,
            models=models,
            battle_round=requested_round,
            battlefield_width_inches=width,
            battlefield_depth_inches=depth,
            strategic_reserve_rule=strategic_rule,
            qualifying_edges=qualifying_edges,
            large_model_exceptions=exceptions,
        )
        if requested_round == 2:
            append_enemy_deployment_zone_violations(
                violations=violations,
                models=models,
                enemy_deployment_zones=deployment_zones,
            )
    append_common_reserve_placement_violations(
        violations=violations,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        view=view,
        attempted_rules_unit_placement=rules_unit_placement,
        models=models,
        battlefield_width_inches=width,
        battlefield_depth_inches=depth,
        terrain_features=features,
        objective_markers=markers,
        enemy_distance_inches=(
            strategic_rule.enemy_horizontal_distance_inches
            if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES
            else deep_strike_enemy_distance
            if deep_strike_enemy_distance is not None
            else _RESERVE_ENEMY_DISTANCE_INCHES
        ),
    )
    coherency_result = UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor,
        unit_instance_id=view.unit_instance_id,
    ).validate_models(models)
    if not coherency_result.is_coherent:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.UNIT_COHERENCY_BROKEN,
                message="Reserve placement violates unit coherency.",
            )
        )

    exception_model_ids = {exception.model_instance_id for exception in exceptions}
    large_model_exception_used = bool(exception_model_ids)

    exempt_ids = tuple(
        sorted(
            model.model_instance_id
            for model in view.alive_models()
            if model.model_instance_id in exception_model_ids
            and large_model_source.SETUP_POLICY.reserve_exempt_keyword in model.keywords
        )
    )
    restrictions = (
        LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS if exception_model_ids - set(exempt_ids) else ()
    )
    transition_batch = None
    if not violations:
        transition_batch = reserve_arrival_transition_batch(
            attempted_rules_unit_placement=rules_unit_placement,
            placement_kind=placement_kind,
            source_rule_id=source_rule_id_for_placement_kind(placement_kind),
        )
    return ReinforcementPlacement(
        candidate=candidate,
        violations=tuple(violations),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
        large_model_exception_used=large_model_exception_used,
        aircraft_exception_model_ids=exempt_ids,
        post_arrival_restrictions=restrictions,
    )
