"""Explicit engine evaluation before pure Objective Control calculations."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.ruleset_descriptor import TerrainObjectiveControlPolicy
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    resolve_objective_control,
)
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_rules_unit_to_objective,
)
from warhammer40k_core.engine.objective_geometry_sources import (
    linked_objective_geometry,
    terrain_objective_geometry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_evaluation import (
    evaluate_unit_profile_characteristics,
    has_random_profile_characteristics,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_is_battle_shocked,
    rules_unit_views_from_armies,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.missions import MissionActionDefinition
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.unit_factory import ModelInstance


def evaluate_objective_control(
    context: ObjectiveControlContext,
    *,
    decisions: DecisionController | None,
    scope_id: str,
) -> ObjectiveControlRecord:
    return resolve_objective_control(
        prepare_objective_control(context, decisions=decisions, scope_id=scope_id)
    )


def prepare_objective_control(
    context: ObjectiveControlContext,
    *,
    decisions: DecisionController | None,
    scope_id: str,
) -> ObjectiveControlContext:
    if not any(
        isinstance(model.characteristic(Characteristic.OBJECTIVE_CONTROL), RandomProfileValue)
        for army in context.scenario.armies
        for unit in army.units
        for model in unit.own_models
    ):
        return context
    geometries = [ObjectiveGeometry.from_marker(marker) for marker in context.objective_markers]
    if (
        context.ruleset_descriptor is not None
        and context.ruleset_descriptor.objective_policy.terrain_objective_control_policy
        is TerrainObjectiveControlPolicy.TERRAIN_AREA_OCCUPANCY
    ):
        geometries.extend(
            terrain_objective_geometry(objective, terrain_features=context.terrain_features)
            for objective in context.terrain_objectives
        )
        geometries.extend(
            linked_objective_geometry(objective, terrain_areas=context.terrain_areas)
            for objective in context.objective_terrain_areas
        )
    state = context.state
    for unit in rules_unit_views_from_armies(armies=context.scenario.armies):
        if (
            state is not None
            and rules_unit_is_battle_shocked(state=state, unit_instance_id=unit.unit_instance_id)
        ) or (state is None and unit.unit_instance_id in context.battle_shocked_unit_ids):
            continue
        model_ids = tuple(
            sorted(
                {
                    measurement.model_instance_id
                    for geometry in geometries
                    for measurement in measure_rules_unit_to_objective(
                        scenario=context.scenario, rules_unit=unit, objective=geometry
                    )
                    if measurement.within_control_range
                }
            )
        )
        if not model_ids or not any(
            isinstance(
                unit.model_by_id(model_id).characteristic(Characteristic.OBJECTIVE_CONTROL),
                RandomProfileValue,
            )
            for model_id in model_ids
        ):
            continue
        if state is None or decisions is None:
            raise GameLifecycleError(
                "Random Objective Control requires an engine evaluation boundary."
            )
        evaluate_unit_profile_characteristics(
            state=state,
            decisions=decisions,
            unit_instance_id=unit.unit_instance_id,
            scope_id=scope_id,
            characteristics=(Characteristic.OBJECTIVE_CONTROL,),
            model_instance_ids=model_ids,
        )
    if state is None:
        return context
    return replace(
        context, scenario=replace(context.scenario, armies=tuple(state.army_definitions))
    )


def objective_control_boundary_scope(context: ObjectiveControlContext) -> str:
    return (
        f"objective-control:round-{context.battle_round:02d}:{context.active_player_id}:"
        f"{context.phase}:{context.timing.value}"
    )


def prepare_mission_action_profile_values(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    actions: tuple[MissionActionDefinition, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    from warhammer40k_core.engine.mission_action_eligibility import (
        mission_action_pre_oc_ineligibility_reason,
    )
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlTiming,
        model_objective_control_characteristic,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if not has_random_profile_characteristics(
        state=state, characteristics=(Characteristic.OBJECTIVE_CONTROL,)
    ):
        return
    phase = state.current_battle_phase
    actions = tuple(
        action for action in actions if phase is not None and action.start_phase == phase.value
    )
    if not actions or state.battlefield_state is None or phase is None:
        return
    scope_id = f"mission-action-options:decision-request-{state.decision_request_count + 1:06d}"
    placed_ids = frozenset(state.battlefield_state.placed_model_ids())
    for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if (
            mission_action_pre_oc_ineligibility_reason(
                state=state,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            is not None
        ):
            continue
        models = tuple(
            model for model in unit.alive_models() if model.model_instance_id in placed_ids
        )
        fixed_models = tuple(
            model
            for model in models
            if not isinstance(
                model.characteristic(Characteristic.OBJECTIVE_CONTROL), RandomProfileValue
            )
        )

        def positive(model: ModelInstance, owner: RulesUnitView = unit) -> bool:
            value = model_objective_control_characteristic(
                model,
                battle_shocked=False,
                state=state,
                unit_instance_id=owner.component_unit_id_for_model(model.model_instance_id),
                runtime_modifier_registry=runtime_modifier_registry,
                model_instance_id=model.model_instance_id,
            )
            return value.is_numeric and value.final > 0

        if any(positive(model) for model in fixed_models):
            continue
        for model in models:
            if model in fixed_models:
                continue
            evaluate_unit_profile_characteristics(
                state=state,
                decisions=decisions,
                unit_instance_id=unit.unit_instance_id,
                scope_id=scope_id,
                characteristics=(Characteristic.OBJECTIVE_CONTROL,),
                model_instance_ids=(model.model_instance_id,),
            )
            refreshed = rules_unit_view_by_id(
                state=state, unit_instance_id=unit.unit_instance_id
            ).model_by_id(model.model_instance_id)
            if positive(refreshed):
                break
    non_control_policies = {
        "trappable_terrain_area",
        "plunderable_terrain_area",
        "terrain_area_in_enemy_territory",
        "visible_enemy_unit_within_18_not_surveilled_this_turn",
    }
    if any(action.target_policy not in non_control_policies for action in actions):
        prepare_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=phase,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                runtime_modifier_registry=runtime_modifier_registry,
            ),
            decisions=decisions,
            scope_id=scope_id,
        )


def prepare_objective_control_after_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    event_id: str,
) -> None:
    """Publish fresh control values after an accepted physical world change."""
    if not any(
        isinstance(value, RandomProfileValue)
        and value.characteristic is Characteristic.OBJECTIVE_CONTROL
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        for value in model.characteristics
    ):
        return
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming

    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Post-placement Objective Control requires a battle phase.")
    prepare_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        ),
        decisions=decisions,
        scope_id=f"objective-control-placement:{event_id}",
    )


def record_unavailable_mission_action_profiles(
    *, state: GameState, decisions: DecisionController
) -> None:
    request_id = f"decision-request-{state.decision_request_count + 1:06d}"
    scope_id = f"mission-action-options:{request_id}"
    if any(
        event.event_type == "random_profile_values_evaluated"
        and isinstance(event.payload, dict)
        and event.payload.get("scope_id") == scope_id
        for event in decisions.event_log.records
    ):
        phase = state.current_battle_phase
        if phase is None:
            raise GameLifecycleError("Mission Action evaluation requires a phase.")
        decisions.event_log.append(
            "mission_action_profile_options_unavailable",
            {
                "request_id": request_id,
                "battle_round": state.battle_round,
                "phase": phase.value,
            },
        )
