"""Deployment endpoint validation shared by every deployment submission."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementViolation,
    DeploymentPlacementViolationCode,
    _require_mission_setup,
    _validate_identifier,
    model_owner_player_id_from_state,
    rules_unit_has_keyword,
    unit_for_model,
)
from warhammer40k_core.engine.deployment_ability_queries import (
    rules_unit_has_infiltrators as _rules_unit_has_infiltrators,
)
from warhammer40k_core.engine.deployment_ability_queries import (
    rules_unit_has_mixed_infiltrators as _rules_unit_has_mixed_infiltrators,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.large_model_setup import oversized_deployment_violation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model

_EPSILON = 1e-9
_INFILTRATORS_DISTANCE_INCHES = 8.0


def append_geometry_violations(
    *,
    violations: list[DeploymentPlacementViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    view: RulesUnitView,
    models: tuple[Model, ...],
    deployment_zones: tuple[DeploymentZone, ...],
) -> None:
    mission_setup = _require_mission_setup(state)
    battlefield_state = scenario.battlefield_state
    placed_models = scenario.placed_geometry_models()
    enemy_models = tuple(
        model
        for model in placed_models
        if _model_owner_player_id(scenario=scenario, model_instance_id=model.model_id)
        != view.owner_player_id
    )
    own_model_ids = {model.model_id for model in models}
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    markers = tuple(marker.to_objective_marker() for marker in mission_setup.objective_markers)
    all_infiltrators = _rules_unit_has_infiltrators(state=state, view=view)
    any_outside_zone = False
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        ):
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Deployment placement crosses the battlefield edge.",
                    model_instance_id=model.model_id,
                )
            )
        in_deployment_zone = any(
            shapely_backend.base_footprint_within_deployment_zone(
                model.base,
                model.pose,
                zone,
            )
            for zone in deployment_zones
        )
        if not in_deployment_zone and not all_infiltrators:
            reason = oversized_deployment_violation(
                model=model,
                zones=deployment_zones,
                mission=mission_setup,
                player_id=view.owner_player_id,
            )
            if reason is not None:
                any_outside_zone = True
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=DeploymentPlacementViolationCode(reason),
                        message=(
                            "Deployment requires ordinary zone containment or proven "
                            "oversized edge setup."
                        ),
                        model_instance_id=model.model_id,
                    )
                )
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=DeploymentPlacementViolationCode.MODEL_OVERLAP,
                        message="Deployment placement overlaps another model.",
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
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=DeploymentPlacementViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Deployment placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
            if all_infiltrators and model.base_distance_to(enemy_model) <= (
                _INFILTRATORS_DISTANCE_INCHES + _EPSILON
            ):
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=(
                            DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_UNIT_DISTANCE
                        ),
                        message="INFILTRATORS deployment must be more than 8 inches from enemies.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=unit_for_model(view=view, model_instance_id=model.model_id),
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=battlefield_state.terrain_features,
            violation_code=DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Deployment placement",
        )
        if terrain_violation is not None:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=markers,
            violation_code=(
                DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value
            ),
            placement_label="Deployment placement",
        )
        if objective_violation is not None:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=(
                        DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP
                    ),
                    message=objective_violation.message,
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )
    overlap = _moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.MODEL_OVERLAP,
                message="Deployment placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )
    if any_outside_zone and not all_infiltrators:
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message="Deployment placement must be wholly within the player's deployment zone.",
                field="model_placements",
            )
        )
        if _rules_unit_has_mixed_infiltrators(state=state, view=view):
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.INFILTRATORS_KEYWORD_REQUIRED,
                    message=(
                        "INFILTRATORS deployment requires every component unit to have the ability."
                    ),
                    field="unit_instance_id",
                )
            )
    if all_infiltrators:
        _append_infiltrator_enemy_zone_violations(
            violations=violations,
            state=state,
            models=models,
        )
    if rules_unit_has_keyword(view, "FORTIFICATION"):
        violations.append(
            DeploymentPlacementViolation(
                violation_code=(
                    DeploymentPlacementViolationCode.FORTIFICATION_DEPLOYMENT_UNSUPPORTED
                ),
                message="Fortification deployment restrictions are not yet source-backed.",
                field="unit_instance_id",
            )
        )


def _append_infiltrator_enemy_zone_violations(
    *,
    violations: list[DeploymentPlacementViolation],
    state: GameState,
    models: tuple[Model, ...],
) -> None:
    mission_setup = _require_mission_setup(state)
    for model in models:
        for zone in mission_setup.enemy_deployment_zones_for_player(
            model_owner_player_id_from_state(state=state, model_instance_id=model.model_id)
        ):
            distance = shapely_backend.base_footprint_distance_to_deployment_zone(
                model.base,
                model.pose,
                zone,
            )
            if distance <= _INFILTRATORS_DISTANCE_INCHES + _EPSILON:
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=(
                            DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_ZONE_DISTANCE
                        ),
                        message=(
                            "INFILTRATORS deployment must be more than 8 inches from the "
                            "enemy deployment zone."
                        ),
                        model_instance_id=model.model_id,
                        blocker_id=zone.deployment_zone_id,
                    )
                )


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
    if not first.base_overlaps(second):
        return False
    return first.volume.vertical_gap_to(first.pose, second.volume, second.pose) <= _EPSILON


def _moving_models_overlap(models: tuple[Model, ...]) -> tuple[str, str] | None:
    for first_index, first in enumerate(models):
        for second in models[first_index + 1 :]:
            if _models_overlap_with_volume(first, second):
                return first.model_id, second.model_id
    return None


def _model_owner_player_id(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return placed_army.player_id
    raise GameLifecycleError("model_instance_id is not placed.")
