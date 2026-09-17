"""Deployment endpoint validation shared by every deployment submission."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.large_model_setup import oversized_deployment_violation
from warhammer40k_core.engine.prebattle import (
    PreBattleViolation,
    PreBattleViolationCode,
    _models_overlap_with_volume,
    _require_mission_setup,
    model_is_within_battlefield,
    model_owner_player_id,
    moving_models_overlap,
    unit_for_model,
)
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model

_EPSILON = 1e-9
_INFILTRATORS_DISTANCE_INCHES = 8.0


def append_setup_geometry_violations(
    *,
    violations: list[PreBattleViolation],
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
        if model_owner_player_id(scenario=scenario, model_instance_id=model.model_id)
        != view.owner_player_id
    )
    own_model_ids = {model.model_id for model in models}
    own_model_ids.update(model.model_instance_id for model in view.alive_models())
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    markers = tuple(marker.to_objective_marker() for marker in mission_setup.objective_markers)
    any_outside_zone = False
    for model in models:
        if not model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        ):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Pre-battle placement crosses the battlefield edge.",
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
        if not in_deployment_zone:
            reason = oversized_deployment_violation(
                model=model,
                zones=deployment_zones,
                mission=mission_setup,
                player_id=view.owner_player_id,
            )
            if reason is not None:
                any_outside_zone = True
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode(reason),
                        message=(
                            "Pre-battle setup requires ordinary zone containment or "
                            "proven oversized edge setup."
                        ),
                        model_instance_id=model.model_id,
                    )
                )
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.MODEL_OVERLAP,
                        message="Pre-battle placement overlaps another model.",
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
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Pre-battle placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=unit_for_model(view=view, model_instance_id=model.model_id),
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=battlefield_state.terrain_features,
            violation_code=PreBattleViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Pre-battle placement",
        )
        if terrain_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=markers,
            violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Pre-battle placement",
        )
        if objective_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP,
                    message=objective_violation.message,
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )
    overlap = moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.MODEL_OVERLAP,
                message="Pre-battle placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )
    if any_outside_zone:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message="Pre-battle placement must be wholly within the player's deployment zone.",
                field="model_placements",
            )
        )
