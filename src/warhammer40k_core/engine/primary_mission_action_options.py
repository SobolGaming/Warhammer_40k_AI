from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.missions import MissionActionDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_for_id,
)
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
    model_intersects_logical_terrain_area,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
)
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_identities_share_lineage,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.shooting_terrain_visibility import (
    shooting_terrain_areas_for_state,
)


@dataclass(frozen=True, slots=True)
class PrimaryMissionActionStartTarget:
    unit_instance_id: str
    target_id: str
    condition_target_id: str | None


def primary_mission_action_start_targets(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[PrimaryMissionActionStartTarget, ...]:
    policy = mission_action_policy_for_id(action.mission_action_id)
    _validate_runtime_action(action=action, policy=policy)
    if policy.start_timing == "shooting_phase_action_start_from_battle_round_two" and (
        state.battle_round < 2
    ):
        return ()
    if _once_per_turn_used(state=state, player_id=player_id, policy=policy):
        return ()
    eligible_units = _eligible_rules_units(
        state=state,
        player_id=player_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if not eligible_units:
        return ()
    if policy.target_policy == "terrain_area_in_enemy_territory":
        targets = _terrain_targets(
            state=state,
            player_id=player_id,
            eligible_units=eligible_units,
        )
    elif policy.target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        targets = _surveil_targets(
            state=state,
            player_id=player_id,
            eligible_units=eligible_units,
        )
    else:
        targets = _objective_targets(
            state=state,
            player_id=player_id,
            policy=policy,
            eligible_units=eligible_units,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    return tuple(
        target
        for target in targets
        if _use_limit_allows_target(
            state=state,
            player_id=player_id,
            policy=policy,
            target=target,
        )
    )


def primary_mission_action_target_kind(target_policy: str) -> str:
    if target_policy == "terrain_area_in_enemy_territory":
        return "terrain_area"
    if target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        return "enemy_rules_unit"
    return "objective_marker"


def _validate_runtime_action(
    *,
    action: MissionActionDefinition,
    policy: MissionActionPolicyDescriptor,
) -> None:
    expected_source_id = f"{policy.source_package_id}:action:{policy.mission_action_id}"
    actual = (
        action.mission_action_id,
        action.mission_id,
        action.mission_kind,
        action.start_phase,
        action.start_timing,
        action.completion_timing,
        action.eligible_unit_policy,
        action.target_policy,
        action.interruption_conditions,
        action.victory_points,
        action.scoring_source_id,
        action.source_id,
    )
    expected = (
        policy.mission_action_id,
        policy.primary_mission_id,
        "primary",
        policy.start_phase,
        policy.start_timing,
        policy.completion_timing,
        policy.eligible_unit_policy,
        policy.target_policy,
        policy.interruption_conditions,
        0,
        policy.scoring_source_id,
        expected_source_id,
    )
    if actual != expected:
        raise GameLifecycleError("Primary Mission Action runtime descriptor drifted.")


def _eligible_rules_units(
    *,
    state: GameState,
    player_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[RulesUnitView, ...]:
    return tuple(
        rules_unit
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if rules_unit.owner_player_id == player_id
        and mission_action_unit_ineligibility_reason(
            state=state,
            player_id=player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        is None
    )


def _objective_targets(
    *,
    state: GameState,
    player_id: str,
    policy: MissionActionPolicyDescriptor,
    eligible_units: tuple[RulesUnitView, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[PrimaryMissionActionStartTarget, ...]:
    mission_setup = state.mission_setup
    phase = state.current_battle_phase
    if mission_setup is None or phase is None:
        raise GameLifecycleError("Primary objective Action requires mission battle state.")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    eligible_ids = {unit.unit_instance_id for unit in eligible_units}
    home_ids = set(home_objective_ids(mission_setup, player_id=player_id))
    marker_by_id = {
        marker.objective_marker_id: marker for marker in mission_setup.objective_markers
    }
    active_markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.status is PrimaryMissionMarkerStatus.ACTIVE
    )
    if (
        "friendly_operation_marker_requires_more_than_one" in policy.target_policy
        and sum(
            marker.owner_player_id == player_id and marker.marker_kind == "operation"
            for marker in active_markers
        )
        <= 1
    ):
        return ()
    if (
        "opponent_operation_marker_requires_more_than_one" in policy.target_policy
        and sum(
            marker.owner_player_id != player_id and marker.marker_kind == "operation"
            for marker in active_markers
        )
        <= 1
    ):
        return ()
    targets: set[tuple[str, str]] = set()
    for result in record.results:
        objective = marker_by_id.get(result.objective_id)
        if objective is None or not _objective_policy_allows(
            objective_id=result.objective_id,
            objective_role=objective.objective_role,
            player_id=player_id,
            policy=policy,
            home_ids=home_ids,
            active_markers=active_markers,
        ):
            continue
        for contribution in result.contributors:
            if contribution.player_id != player_id:
                continue
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(state.army_definitions),
                unit_instance_id=contribution.unit_instance_id,
            )
            if rules_unit_id in eligible_ids:
                targets.add((rules_unit_id, result.objective_id))
    return tuple(
        PrimaryMissionActionStartTarget(
            unit_instance_id=unit_id,
            target_id=objective_id,
            condition_target_id=objective_id,
        )
        for unit_id, objective_id in sorted(targets)
    )


def _objective_policy_allows(
    *,
    objective_id: str,
    objective_role: ObjectiveMarkerRole,
    player_id: str,
    policy: MissionActionPolicyDescriptor,
    home_ids: set[str],
    active_markers: tuple[PrimaryMissionMarkerState, ...],
) -> bool:
    target_policy = policy.target_policy
    if target_policy.startswith("central_objective"):
        return objective_role is ObjectiveMarkerRole.CENTRAL
    if objective_id in home_ids:
        return False
    if target_policy == "objective_marker_excluding_home_not_decoy":
        return not any(
            marker.owner_player_id == player_id
            and marker.mission_id == policy.primary_mission_id
            and marker.objective_marker_id == objective_id
            for marker in active_markers
        )
    if target_policy == "objective_marker_excluding_home_without_friendly_operation_marker":
        return not any(
            marker.owner_player_id == player_id
            and marker.marker_kind == "operation"
            and marker.objective_marker_id == objective_id
            for marker in active_markers
        )
    return target_policy == "objective_marker_excluding_home"


def _terrain_targets(
    *,
    state: GameState,
    player_id: str,
    eligible_units: tuple[RulesUnitView, ...],
) -> tuple[PrimaryMissionActionStartTarget, ...]:
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise GameLifecycleError("Primary terrain Action requires mission battlefield state.")
    opponent_id = next(candidate for candidate in state.player_ids if candidate != player_id)
    areas = tuple(
        area
        for area in mission_logical_terrain_areas(mission_setup)
        if logical_terrain_area_within_player_territory(
            area,
            mission_setup=mission_setup,
            player_id=opponent_id,
        )
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    targets: set[tuple[str, str]] = set()
    for rules_unit in eligible_units:
        for component in rules_unit.components:
            placement = battlefield.unit_placement_or_none(component.unit.unit_instance_id)
            if placement is None:
                continue
            for model_placement in placement.model_placements:
                model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(model_placement),
                    placement=model_placement,
                )
                for area in areas:
                    if model_intersects_logical_terrain_area(model, area=area):
                        targets.add((rules_unit.unit_instance_id, area.logical_terrain_area_id))
    return tuple(
        PrimaryMissionActionStartTarget(
            unit_instance_id=unit_id,
            target_id=area_id,
            condition_target_id=area_id,
        )
        for unit_id, area_id in sorted(targets)
    )


def _surveil_targets(
    *,
    state: GameState,
    player_id: str,
    eligible_units: tuple[RulesUnitView, ...],
) -> tuple[PrimaryMissionActionStartTarget, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Surveil requires battlefield state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    terrain_areas = shooting_terrain_areas_for_state(state)
    enemy_units = tuple(
        unit
        for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if unit.owner_player_id != player_id
        and any(
            model.is_alive and model.model_instance_id in battlefield.placed_model_ids()
            for model in unit.own_models
        )
        and not _surveilled_this_turn(state=state, target_unit_id=unit.unit_instance_id)
    )
    targets: set[tuple[str, str]] = set()
    for observer in eligible_units:
        for target in enemy_units:
            if not _rules_unit_within_18(
                scenario=scenario,
                observer=observer,
                target_unit_id=target.unit_instance_id,
            ):
                continue
            if any(
                any(model.is_alive for model in component.unit.own_models)
                and battlefield.unit_placement_or_none(component.unit.unit_instance_id) is not None
                and unit_has_line_of_sight_to_target(
                    state=state,
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    observing_unit=component.unit,
                    target_unit_id=target.unit_instance_id,
                    placed_alive_models_only=True,
                    terrain_features=battlefield.terrain_features,
                    terrain_areas=terrain_areas,
                )
                for component in observer.components
            ):
                targets.add((observer.unit_instance_id, target.unit_instance_id))
    return tuple(
        PrimaryMissionActionStartTarget(
            unit_instance_id=unit_id,
            target_id=target_id,
            condition_target_id=None,
        )
        for unit_id, target_id in sorted(targets)
    )


def _rules_unit_within_18(
    *,
    scenario: BattlefieldScenario,
    observer: RulesUnitView,
    target_unit_id: str,
) -> bool:
    return any(
        any(model.is_alive for model in component.unit.own_models)
        and scenario.battlefield_state.unit_placement_or_none(component.unit.unit_instance_id)
        is not None
        and target_within_shooting_selection_range(
            scenario=scenario,
            attacking_unit_instance_id=component.unit.unit_instance_id,
            target_unit_instance_id=target_unit_id,
            max_range_inches=18,
            placed_alive_attacker_models_only=True,
            placed_alive_target_models_only=True,
        )
        for component in observer.components
    )


def _surveilled_this_turn(*, state: GameState, target_unit_id: str) -> bool:
    return any(
        action.mission_action_id == "surveil-enemy-unit"
        and rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=action.target_id,
            second_unit_instance_id=target_unit_id,
        )
        and action.battle_round_started == state.battle_round
        and action.player_id == state.active_player_id
        for action in state.mission_action_states
    )


def _once_per_turn_used(
    *, state: GameState, player_id: str, policy: MissionActionPolicyDescriptor
) -> bool:
    return policy.use_limit == "once_per_turn" and any(
        action.player_id == player_id
        and action.mission_action_id == policy.mission_action_id
        and action.battle_round_started == state.battle_round
        for action in state.mission_action_states
    )


def _use_limit_allows_target(
    *,
    state: GameState,
    player_id: str,
    policy: MissionActionPolicyDescriptor,
    target: PrimaryMissionActionStartTarget,
) -> bool:
    if policy.use_limit != "unlimited_different_objective_per_unit_this_phase":
        return True
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Primary Mission Action use limit requires battle phase.")
    current = tuple(
        action
        for action in state.mission_action_states
        if action.player_id == player_id
        and action.mission_action_id == policy.mission_action_id
        and action.battle_round_started == state.battle_round
        and action.phase_started == phase.value
    )
    return not any(
        action.unit_instance_id == target.unit_instance_id or action.target_id == target.target_id
        for action in current
    )


__all__ = (
    "PrimaryMissionActionStartTarget",
    "primary_mission_action_start_targets",
    "primary_mission_action_target_kind",
)
