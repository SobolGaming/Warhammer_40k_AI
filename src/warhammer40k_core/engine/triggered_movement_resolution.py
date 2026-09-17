from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.aircraft import (
    AircraftMovementPolicy,
    HoverModeState,
    aircraft_model_ids_for_scenario,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_movement_source import (
    ChargePlacement,
    battlefield_with_charge_placement,
    charge_placement_id,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.normal_move_history import NormalMoveState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
    TriggeredMovementResolution,
    TriggeredMovementViolation,
    TriggeredMovementViolationCode,
    _validate_identifier,
    _validate_identifier_tuple,
    _validate_positive_int,
)
from warhammer40k_core.engine.triggered_movement_physical_authority import (
    merge_triggered_movement_source_endpoints,
    require_triggered_movement_source_model_placements,
    resolve_triggered_movement_source_coherency,
    retained_triggered_movement_blocker_ids,
    validate_triggered_movement_source_witness,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityContext,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model


def resolve_triggered_movement(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: ChargePlacement,
    descriptor: TriggeredMovementDescriptor,
    path_witness: PathWitness,
    battle_round: int,
    battle_shocked_unit_ids: tuple[str, ...] = (),
    normal_move_states: tuple[NormalMoveState, ...] = (),
    hover_mode_states: tuple[HoverModeState, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    take_to_the_skies: bool = False,
    move_keyword_choice: JsonValue = None,
    surge_target_unit_instance_id: str | None = None,
) -> TriggeredMovementResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Triggered movement requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Triggered movement requires a RulesetDescriptor.")
    if type(unit_placement) not in {UnitPlacement, RulesUnitPlacement}:
        raise GameLifecycleError("Triggered movement requires a UnitPlacement.")
    if type(descriptor) is not TriggeredMovementDescriptor:
        raise GameLifecycleError("Triggered movement requires a descriptor.")
    if type(path_witness) is not PathWitness:
        raise GameLifecycleError("Triggered movement requires a PathWitness.")
    is_surge = descriptor.movement_kind is TriggeredMovementKind.SURGE
    if is_surge and take_to_the_skies:
        raise GameLifecycleError("Surge cannot take to the skies.")
    target_id: str | None = None
    unit_id = charge_placement_id(unit_placement)
    if is_surge:
        from warhammer40k_core.engine.surge_movement import validate_surge_target

        target_id = validate_surge_target(
            scenario=scenario,
            unit_instance_id=unit_id,
            target_id=surge_target_unit_instance_id,
        )
    triggered_round = _validate_positive_int("battle_round", battle_round)
    source_model_placements = require_triggered_movement_source_model_placements(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    validate_triggered_movement_source_witness(
        witness=path_witness,
        source_model_placements=source_model_placements,
    )
    restriction_violations = _triggered_movement_restriction_violations(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        descriptor=descriptor,
        battle_round=triggered_round,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
        normal_move_states=normal_move_states,
    )
    attempted_placement = merge_triggered_movement_source_endpoints(
        unit_placement=unit_placement,
        source_model_placements=source_model_placements,
        witness=path_witness,
    )
    maximum_distance = descriptor.max_distance_inches
    if take_to_the_skies:
        from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
        from warhammer40k_core.engine.take_to_the_skies import flight_penalty

        if descriptor.movement_mode is not MovementMode.NORMAL:
            raise GameLifecycleError("Reactive flight requires a Normal move.")
        maximum_distance = max(
            0.0,
            maximum_distance
            - flight_penalty(
                unit=rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_id),
                ruleset=ruleset_descriptor,
            ),
        )
    from warhammer40k_core.engine.move_ability_choices import (
        CHOICE_KEY,
        chosen_move_keywords,
        movement_ability_keywords,
    )
    from warhammer40k_core.engine.phases.movement_geometry import (
        _enemy_model_ids_with_keyword_any_for_player,
        _friendly_model_ids_with_keyword_any,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

    view = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_id)
    ability_keywords = movement_ability_keywords(view)
    choice_payload = {} if move_keyword_choice is None else {CHOICE_KEY: move_keyword_choice}
    temporary_keywords = chosen_move_keywords(choice_payload)
    if temporary_keywords and (is_surge or descriptor.movement_mode is not MovementMode.NORMAL):
        raise GameLifecycleError("Movement keywords require their descriptor's allowed move.")
    aircraft_model_ids = aircraft_model_ids_for_scenario(
        scenario,
        hover_mode_states=hover_mode_states,
    )
    path_validation_results: list[PathValidationResult] = []
    terrain_path_legality_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    friendly_retained_ids, enemy_retained_ids = retained_triggered_movement_blocker_ids(
        scenario=scenario,
        moving_player_id=unit_placement.player_id,
    )
    retained_model_ids = frozenset((*friendly_retained_ids, *enemy_retained_ids))
    model_contexts: list[
        tuple[ModelPlacement, PathValidationContext, TerrainPathLegalityContext]
    ] = []
    aircraft_policies: dict[str, JsonValue] = {}
    for placement in source_model_placements:
        unit = scenario.army_by_id(placement.army_id).unit_by_id(placement.unit_instance_id)
        aircraft_policy = AircraftMovementPolicy.from_unit(
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
            hover_mode_state=_hover_mode_state_for_unit(
                hover_mode_states=hover_mode_states, unit_instance_id=placement.unit_instance_id
            ),
        )
        if aircraft_policy.has_aircraft_keyword:
            aircraft_policies[placement.unit_instance_id] = validate_json_value(
                aircraft_policy.to_payload()
            )
        model = scenario.model_instance_for_placement(placement)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_poses = path_witness.poses_for_model(placement.model_instance_id)
        model_witness = PathWitness.for_paths(((placement.model_instance_id, model_poses),))
        legality_context = MovementLegalityContext.from_keywords(
            keywords=tuple(
                sorted(
                    {
                        *aircraft_policy.effective_keywords,
                        *ability_keywords,
                        *temporary_keywords,
                    }
                )
            ),
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=descriptor.movement_mode,
            take_to_the_skies=take_to_the_skies,
            unit=unit,
            model_instance_id=placement.model_instance_id,
            movement_phase_action=None,
            displacement_kind=descriptor.displacement_kind,
        )
        if is_surge:
            legality_context = replace(
                legality_context,
                engagement_policy=replace(
                    legality_context.engagement_policy,
                    may_transit_enemy_engagement=True,
                    may_end_in_enemy_engagement=True,
                ),
            )
        path_context = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=unit_placement,
                attempted_placement=attempted_placement,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            terrain=(),
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=unit_placement.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=_enemy_vehicle_monster_model_ids_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            friendly_model_transit_blocker_ids=tuple(
                sorted(
                    {
                        *friendly_retained_ids,
                        *_friendly_model_ids_with_keyword_any(
                            scenario=scenario,
                            player_id=unit_placement.player_id,
                            moving_model_instance_id=placement.model_instance_id,
                            keyword_any=legality_context.capabilities.friendly_model_transit_blocker_keywords,
                        ),
                    }
                )
            ),
            enemy_model_transit_blocker_ids=tuple(
                sorted(
                    {
                        *enemy_retained_ids,
                        *_enemy_model_ids_with_keyword_any_for_player(
                            scenario=scenario,
                            player_id=unit_placement.player_id,
                            keyword_any=legality_context.capabilities.enemy_model_transit_blocker_keywords,
                        ),
                    }
                )
            ),
            aircraft_model_ids=tuple(
                model_id
                for model_id in aircraft_model_ids
                if model_id != placement.model_instance_id and model_id not in retained_model_ids
            ),
            movement_distance_budget_inches=maximum_distance,
        )
        path_result = path_context.validate()
        terrain_context = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain,
            terrain_features=scenario.battlefield_state.terrain_features,
        )
        terrain_result = terrain_context.validate()
        model_contexts.append((placement, path_context, terrain_context))
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movements.append(
            validate_json_value(
                {
                    "model_instance_id": placement.model_instance_id,
                    "movement_inches": maximum_distance,
                    "start_pose": placement.pose.to_payload(),
                    "end_pose": path_witness.final_pose_for_model(
                        placement.model_instance_id
                    ).to_payload(),
                    "movement_distance_witness": (
                        None
                        if path_result.movement_distance_witness is None
                        else path_result.movement_distance_witness.to_payload()
                    ),
                    "path_validation_result": path_result.to_payload(),
                    "terrain_path_legality_result": terrain_result.to_payload(),
                }
            )
        )
    coherency_result, rollback_record = resolve_triggered_movement_source_coherency(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=unit_placement,
        attempted=attempted_placement,
        source_model_placements=source_model_placements,
        displacement_kind=descriptor.displacement_kind,
    )
    endpoint_rows: list[JsonValue] = []
    if (
        is_surge
        and target_id is not None
        and not restriction_violations
        and all(row.is_valid for row in path_validation_results)
        and all(row.is_valid for row in terrain_path_legality_results)
        and coherency_result.is_coherent
    ):
        from warhammer40k_core.engine.surge_endpoints import validate_surge_endpoints

        endpoint_rows, endpoint_codes = validate_surge_endpoints(
            scenario=scenario,
            ruleset=ruleset_descriptor,
            unit_instance_id=unit_id,
            target_id=target_id,
            attempted=attempted_placement,
            contexts=tuple(model_contexts),
        )
        restriction_violations += tuple(
            TriggeredMovementViolation(
                violation_code=TriggeredMovementViolationCode(code),
                message="Surge mandatory endpoint requirement was not satisfied.",
            )
            for code in endpoint_codes
        )
    from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
    from warhammer40k_core.engine.take_to_the_skies import flight_choice_context

    movement_payload: dict[str, JsonValue] = {
        **choice_payload,
        **flight_choice_context(
            unit=rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_id),
            ruleset=ruleset_descriptor,
            selected=take_to_the_skies,
        ),
        "triggered_movement_kind": descriptor.movement_kind.value,
        "displacement_kind": descriptor.displacement_kind.value,
        "source_rule_id": descriptor.source_rule_id,
        "trigger_timing": validate_json_value(descriptor.trigger_timing.to_payload()),
        "movement_phase_action": None,
        "movement_inches": maximum_distance,
        "model_movements": model_movements,
        "path_validation_results": validate_json_value(
            [result.to_payload() for result in path_validation_results]
        ),
        "terrain_path_legality_results": validate_json_value(
            [result.to_payload() for result in terrain_path_legality_results]
        ),
        "coherency_result": validate_json_value(coherency_result.to_payload()),
    }
    if is_surge:
        movement_payload["surge_target_unit_instance_id"] = target_id
        movement_payload["surge_model_endpoints"] = endpoint_rows
    if aircraft_policies:
        movement_payload["aircraft_movement_policies"] = dict(sorted(aircraft_policies.items()))
    if restriction_violations:
        movement_payload["restriction_violations"] = validate_json_value(
            [violation.to_payload() for violation in restriction_violations]
        )
    return TriggeredMovementResolution(
        unit_instance_id=unit_id,
        descriptor=descriptor,
        attempted_placement=attempted_placement,
        witness=path_witness,
        restriction_violations=restriction_violations,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
    )


def apply_triggered_movement_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    resolution: TriggeredMovementResolution,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Triggered movement apply requires battlefield_state.")
    if type(resolution) is not TriggeredMovementResolution:
        raise GameLifecycleError("Triggered movement apply requires a resolution.")
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid triggered movement cannot mutate battlefield_state.")
    return battlefield_with_charge_placement(battlefield_state, resolution.attempted_placement)


def _triggered_movement_restriction_violations(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: ChargePlacement,
    descriptor: TriggeredMovementDescriptor,
    battle_round: int,
    battle_shocked_unit_ids: tuple[str, ...],
    normal_move_states: tuple[NormalMoveState, ...],
) -> tuple[TriggeredMovementViolation, ...]:
    violations: list[TriggeredMovementViolation] = []
    prior_normal_moves = _validate_normal_move_state_tuple(normal_move_states)
    if descriptor.movement_kind is TriggeredMovementKind.SURGE:
        battle_shocked_ids = set(
            _validate_identifier_tuple("battle_shocked_unit_ids", battle_shocked_unit_ids)
        )
        from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

        view = rules_unit_view_from_armies(
            armies=scenario.armies, unit_instance_id=charge_placement_id(unit_placement)
        )
        if battle_shocked_ids.intersection(
            {view.unit_instance_id, *view.component_unit_instance_ids}
        ):
            violations.append(
                TriggeredMovementViolation(
                    violation_code=TriggeredMovementViolationCode.BATTLE_SHOCKED_SURGE_FORBIDDEN,
                    message="Battle-shocked units cannot make surge moves.",
                )
            )
        if scenario_physically_engaged_enemy_rules_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=charge_placement_id(unit_placement),
        ):
            violations.append(
                TriggeredMovementViolation(
                    violation_code=TriggeredMovementViolationCode.ENGAGEMENT_RANGE_SURGE_FORBIDDEN,
                    message="Units within Engagement Range cannot make surge moves.",
                )
            )
    requested_key = (
        battle_round,
        descriptor.trigger_timing.phase,
        unit_placement.player_id,
        charge_placement_id(unit_placement),
    )
    matching_prior_moves = tuple(
        state for state in prior_normal_moves if state.same_phase_key() == requested_key
    )
    if (
        descriptor.movement_kind is not TriggeredMovementKind.SURGE
        and descriptor.movement_mode is MovementMode.NORMAL
        and matching_prior_moves
    ):
        violations.append(
            TriggeredMovementViolation(
                violation_code=(TriggeredMovementViolationCode.NORMAL_MOVE_ALREADY_USED_THIS_PHASE),
                message="Unit already made a Normal move this phase.",
            )
        )
    return tuple(violations)


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: ChargePlacement,
    attempted_placement: ChargePlacement,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            endpoints = {
                model.model_instance_id: model for model in attempted_placement.model_placements
            }
            placements = tuple(
                endpoints.get(model.model_instance_id, model)
                for model in current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                if not scenario.model_is_present_at_placement(placement):
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[Model, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
                if scenario.model_is_present_at_placement(placement)
            )
    return tuple(enemy_models)


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
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
                and scenario.model_is_present_at_placement(placement)
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
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if scenario.model_is_present_at_placement(placement)
            )
    return tuple(sorted(model_ids))


def _unit_has_vehicle_or_monster_keyword(keywords: tuple[str, ...]) -> bool:
    return "VEHICLE" in keywords or "MONSTER" in keywords


def _hover_mode_state_for_unit(
    *,
    hover_mode_states: tuple[HoverModeState, ...],
    unit_instance_id: str,
) -> HoverModeState | None:
    if type(hover_mode_states) is not tuple:
        raise GameLifecycleError("hover_mode_states must be a tuple.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    found: HoverModeState | None = None
    for hover_mode_state in cast(tuple[object, ...], hover_mode_states):
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_states must contain HoverModeState values.")
        if hover_mode_state.unit_instance_id != requested_unit_id:
            continue
        if found is not None:
            raise GameLifecycleError("hover_mode_states must be unique by unit.")
        found = hover_mode_state
    return found if found is not None and found.active else None


def _validate_normal_move_state_tuple(values: object) -> tuple[NormalMoveState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("normal_move_states must be a tuple.")
    return tuple(_validate_normal_move_state(value) for value in cast(tuple[object, ...], values))


def _validate_normal_move_state(value: object) -> NormalMoveState:
    if type(value) is not NormalMoveState:
        raise GameLifecycleError("normal_move_states must contain NormalMoveState values.")
    return value
