from __future__ import annotations

from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_effect_history import historical_generic_effect_may_match
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.objective_control_sources import resolve_objective_control_sources
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.objective_geometry_sources import (
    linked_objective_geometry,
    terrain_objective_geometry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    StickyObjectiveControlStatePayload,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.rules.rule_ir import RuleEffectKind


def prior_sticky_candidates(
    context: HistoricalBattleShockAuthorityContext, player_id: str
) -> tuple[StickyObjectiveControlState, ...]:
    """An earlier registration may still be active. This does not prove retention."""
    candidates: list[StickyObjectiveControlState] = []
    for event in context.event_records[: context.boundary_event_index]:
        if event.event_type not in {
            "sticky_objective_control_state_recorded",
            "generic_stratagem_sticky_objective_control_registered",
        }:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Historical sticky objective event requires a payload.")
        row = event.payload.get("sticky_objective_control_state")
        if not isinstance(row, dict):
            raise GameLifecycleError("Historical sticky objective event requires a state.")
        if row.get("player_id") == player_id:
            candidates.append(
                StickyObjectiveControlState.from_payload(
                    cast(StickyObjectiveControlStatePayload, row)
                )
            )
    return tuple(candidates)


def historical_territorial_control(
    *,
    context: HistoricalBattleShockAuthorityContext,
    player_id: str,
    objective_groups: tuple[tuple[str, ...], ...],
    sticky_candidates: tuple[StickyObjectiveControlState, ...],
) -> bool | None:
    """Prove control for this casualty check where the event-bound facts suffice."""
    relevant_ids = {objective_id for group in objective_groups for objective_id in group}
    if not relevant_ids:
        return False
    mission = context.mission_setup
    markers, terrain, linked = resolve_objective_control_sources(
        objective_markers=tuple(
            marker.to_objective_marker() for marker in mission.objective_markers
        ),
        terrain_features=context.terrain_features,
        ruleset_descriptor=context.ruleset_descriptor,
        explicit_terrain_objectives=(),
        objective_terrain_areas=mission.objective_terrain_areas,
    )
    geometries = {
        **{
            marker.objective_marker_id: ObjectiveGeometry.from_marker(marker)
            for marker in markers
            if marker.objective_marker_id in relevant_ids
        },
        **{
            objective.objective_id: terrain_objective_geometry(
                objective, terrain_features=context.terrain_features
            )
            for objective in terrain
            if objective.objective_id in relevant_ids
        },
        **{
            definition.objective_marker_id: linked_objective_geometry(
                definition, terrain_areas=mission.terrain_areas
            )
            for definition in linked
            if definition.objective_marker_id in relevant_ids
        },
    }
    statuses = {
        objective_id: _historical_control_at_objective(
            context=context,
            objective=geometries[objective_id],
            player_id=player_id,
            may_be_sticky=any(state.objective_id == objective_id for state in sticky_candidates),
        )
        for objective_id in sorted(relevant_ids)
    }
    could_control = False
    for group in objective_groups:
        if not group:
            continue
        if 2 * sum(statuses[objective_id] is True for objective_id in group) >= len(group):
            return True
        could_control |= 2 * sum(
            statuses[objective_id] is not False for objective_id in group
        ) >= len(group)
    return None if could_control else False


def _historical_control_at_objective(
    *,
    context: HistoricalBattleShockAuthorityContext,
    objective: ObjectiveGeometry,
    player_id: str,
    may_be_sticky: bool,
) -> bool | None:
    participants: list[tuple[str, str, ModelInstance]] = []
    for row in context.physical_models:
        if row.presence != "battlefield" or row.pose is None:
            continue
        unit, army = context.unit_and_army_for_model(row.model_instance_id)
        model = unit.own_model_by_id(row.model_instance_id)
        geometry = geometry_model_for_placement(
            model=model,
            placement=ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=row.model_instance_id,
                pose=row.pose,
                split_origin=unit.split_origin,
            ),
        )
        if measure_model_to_objective(model=geometry, objective=objective).within_control_range:
            participants.append((army.player_id, unit.unit_instance_id, model))

    if not may_be_sticky and all(owner != player_id for owner, _, _ in participants):
        return False

    phase_start_shocked = context.phase_start_battle_shocked_unit_ids
    complex_lineage = bool(context.starting_attached_unit_records) or any(
        army.attached_units or army.unit_splits for army in context.armies
    )
    if phase_start_shocked and complex_lineage and participants:
        return None

    contributing = [
        (owner, unit_id, model)
        for owner, unit_id, model in participants
        if unit_id not in phase_start_shocked
    ]
    if not may_be_sticky and all(owner != player_id for owner, _, _ in contributing):
        return False

    unit_ids = {unit_id for _, unit_id, _ in contributing}
    if contributing and (
        historical_generic_effect_may_match(
            context.event_records[: context.boundary_event_index],
            lambda payload: _may_modify_objective_control(
                payload, None if complex_lineage else unit_ids
            ),
        )
        or any(
            isinstance(model.characteristic(Characteristic.OBJECTIVE_CONTROL), RandomProfileValue)
            for _, _, model in contributing
        )
    ):
        # This bounded proof does not reconstruct dynamic OC or transferred effect targets.
        return None

    scores = dict.fromkeys(context.player_ids, 0)
    for owner, _, model in contributing:
        scores[owner] += model_objective_control_characteristic(model, battle_shocked=False).final
    score = scores[player_id]
    opposition = max((value for owner, value in scores.items() if owner != player_id), default=0)
    if score > opposition:
        return True
    if score < opposition or not may_be_sticky:
        return False
    return None


def _may_modify_objective_control(payload: dict[str, JsonValue], unit_ids: set[str] | None) -> bool:
    effect = payload.get("effect")
    if (
        not isinstance(effect, dict)
        or effect.get("kind") != RuleEffectKind.MODIFY_CHARACTERISTIC.value
    ):
        return False
    target_ids = payload.get("target_unit_instance_ids")
    if (
        unit_ids is not None
        and isinstance(target_ids, list)
        and target_ids
        and all(isinstance(unit_id, str) for unit_id in target_ids)
        and unit_ids.isdisjoint(cast(list[str], target_ids))
    ):
        return False
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Historical Objective Control effect parameters are invalid.")
    return any(
        isinstance(parameter, dict)
        and parameter.get("key") == "characteristic"
        and parameter.get("value") == Characteristic.OBJECTIVE_CONTROL.value
        for parameter in parameters
    )
