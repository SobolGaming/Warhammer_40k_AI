from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.aircraft import aircraft_model_ids_for_scenario
from warhammer40k_core.engine.aircraft_rules import AIRCRAFT_INGRESS_ONLY, aircraft_rules_unit
from warhammer40k_core.engine.base_contact_authority import (
    contact_query_for_move,
    contacts_for_validated_move,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_geometry_models_for_player as _enemy_geometry_models_for_player,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pathing import (
    PathConstraintViolation,
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model as GeometryModel

_validate_identifier = IdentifierValidator(GameLifecycleError)


def validate_fight_paths(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    movement_mode: MovementMode,
    displacement_kind: ModelDisplacementKind,
    distance_budget_inches: float,
    proposal: FightMovementProposal,
) -> tuple[tuple[PathValidationResult, ...], tuple[TerrainPathLegalityResult, ...]]:
    path_results: list[PathValidationResult] = []
    terrain_results: list[TerrainPathLegalityResult] = []
    terrain_features = scenario.battlefield_state.terrain_features
    terrain_volumes = fight_terrain_volumes_for_features(terrain_features)
    unit = scenario.unit_instance_for_placement(before)
    if "AIRCRAFT" in aircraft_rules_unit(scenario, before.unit_instance_id).keywords:
        return (
            (
                PathValidationResult.invalid(
                    PathConstraintViolation(
                        violation_code=AIRCRAFT_INGRESS_ONLY,
                        message="AIRCRAFT units may only make ingress moves.",
                    ),
                    sampled_pose_count=0,
                    model_collision_check_count=0,
                    terrain_collision_check_count=0,
                    engagement_check_count=0,
                ),
            ),
            (),
        )
    for placement in before.model_placements:
        moving_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=unit.keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
            movement_phase_action=None,
            displacement_kind=displacement_kind,
        )
        path_context = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=before,
                attempted_placement=after,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=before.player_id,
            ),
            terrain=(),
            aircraft_model_ids=tuple(
                mid
                for mid in aircraft_model_ids_for_scenario(scenario)
                if mid != placement.model_instance_id
            ),
            movement_distance_budget_inches=distance_budget_inches,
        )
        terrain_context = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain_volumes,
            terrain_features=terrain_features,
        )
        terrain_result = terrain_context.validate()
        path_results.append(
            contacts_for_validated_move(
                path_context=path_context,
                terrain_context=terrain_context,
                path_result=path_context.validate(),
                terrain_result=terrain_result,
                query=contact_query_for_move(
                    path_context=path_context,
                    terrain_context=terrain_context,
                    scenario=scenario,
                    unit_instance_id=before.unit_instance_id,
                    ruleset=ruleset_descriptor,
                    fight_proposal=proposal,
                ),
            )
        )
        terrain_results.append(terrain_result)
    return (tuple(path_results), tuple(terrain_results))


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[GeometryModel, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[GeometryModel] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            placements = (
                attempted_placement.model_placements
                if current_unit_placement.unit_instance_id == unit_placement.unit_instance_id
                else current_unit_placement.model_placements
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


def fight_terrain_volumes_for_features(
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[TerrainVolume, ...]:
    volumes: list[TerrainVolume] = []
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
        volumes.extend(feature.terrain_volumes())
    return tuple(volumes)
