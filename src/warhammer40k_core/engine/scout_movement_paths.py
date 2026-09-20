from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.aircraft import aircraft_model_ids_for_scenario
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.volume import Model

_validate_identifier = IdentifierValidator(GameLifecycleError)

if TYPE_CHECKING:
    from warhammer40k_core.engine.prebattle import PreBattleViolation


def append_scout_path_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    current: UnitPlacement,
    attempted: UnitPlacement,
    witness: PathWitness,
    scout_distance_inches: float,
) -> None:
    from warhammer40k_core.engine.prebattle import (
        PreBattleViolation,
        PreBattleViolationCode,
        _enemy_geometry_models_for_player,  # pyright: ignore[reportPrivateUsage]
        _require_mission_setup,
    )

    mission_setup = _require_mission_setup(state)
    battlefield_state = scenario.battlefield_state
    terrain_volumes = tuple(
        volume
        for feature in battlefield_state.terrain_features
        for volume in feature.terrain_volumes()
    )
    aircraft_model_ids = aircraft_model_ids_for_scenario(scenario=scenario)
    for placement in current.model_placements:
        model = scenario.model_instance_for_placement(placement)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=scenario.unit_instance_for_placement(current).keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=MovementMode.NORMAL,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind.SCOUT_MOVE,
        )
        path_result = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=current,
                attempted_placement=attempted,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=current.player_id,
            ),
            terrain=terrain_volumes,
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=current.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=_enemy_vehicle_monster_model_ids_for_player(
                scenario=scenario,
                player_id=current.player_id,
            ),
            aircraft_model_ids=tuple(
                mid for mid in aircraft_model_ids if mid != placement.model_instance_id
            ),
            movement_distance_budget_inches=scout_distance_inches,
        ).validate()
        if not path_result.is_valid:
            first_violation = path_result.violations[0]
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.PATH_VALIDATION_FAILED,
                    message=first_violation.message,
                    field="witness",
                    model_instance_id=first_violation.model_id,
                    blocker_id=first_violation.blocker_id,
                )
            )
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain_volumes,
            terrain_features=battlefield_state.terrain_features,
        ).validate()
        if not terrain_result.is_valid:
            first_terrain_violation = terrain_result.violations[0]
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.TERRAIN_PATH_VALIDATION_FAILED,
                    message=first_terrain_violation.message,
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                    blocker_id=first_terrain_violation.terrain_id,
                )
            )
        end_model = geometry_model_for_placement(
            model=model,
            placement=placement.with_pose(
                witness.final_pose_for_model(placement.model_instance_id)
            ),
        )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=end_model,
            objective_markers=tuple(
                marker.to_objective_marker() for marker in mission_setup.objective_markers
            ),
            violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Scout Move endpoint",
        )
        if objective_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP,
                    message=objective_violation.message,
                    field="witness",
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[Model] = []
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


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not bool({"VEHICLE", "MONSTER"}.intersection(unit.keywords)):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _enemy_vehicle_monster_model_ids_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not bool({"VEHICLE", "MONSTER"}.intersection(unit.keywords)):
                continue
            model_ids.extend(
                placement.model_instance_id for placement in unit_placement.model_placements
            )
    return tuple(sorted(model_ids))
