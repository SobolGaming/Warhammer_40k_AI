from __future__ import annotations

from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_effect_history import (
    HistoricalEffectAuthority,
    historical_generic_effect_inventory,
    historical_generic_effect_may_match,
)
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_characteristic_operations_from_effects,
    generic_matching_unit_effect_applications,
)
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
from warhammer40k_core.engine.rules_unit_effects import (
    rules_unit_effect_applications_from_inventory,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.engine.runtime_characteristic_modifiers import (
    apply_objective_control_operations,
)
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    StickyObjectiveControlStatePayload,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_split_views import split_effect_predecessor_ids
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
    """Prove territorial control where the test-boundary facts suffice."""
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

    views = {
        unit_id: _contributor_rules_unit(context, unit_id)
        for unit_id in {unit_id for _, unit_id, _ in participants}
    }
    shocked = set(context.phase_start_battle_shocked_unit_ids)
    contributing = [
        (owner, unit_id, model)
        for owner, unit_id, model in participants
        if shocked.isdisjoint(_rules_unit_identities(views[unit_id]))
    ]
    if not may_be_sticky and all(owner != player_id for owner, _, _ in contributing):
        return False

    effect_targets = {
        predecessor
        for unit_id in {unit_id for _, unit_id, _ in contributing}
        for identity in _rules_unit_identities(views[unit_id])
        for predecessor in split_effect_predecessor_ids(
            armies=context.armies, unit_instance_id=identity
        )
    }
    if any(
        isinstance(model.characteristic(Characteristic.OBJECTIVE_CONTROL), RandomProfileValue)
        for _, _, model in contributing
    ):
        return None

    effects = _active_objective_control_effects(context, effect_targets)
    effects_by_unit = (
        {
            unit_id: generic_matching_unit_effect_applications(
                applications=rules_unit_effect_applications_from_inventory(
                    armies=context.armies, effects=effects, rules_unit=views[unit_id]
                ),
                effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            )
            for unit_id in {unit_id for _, unit_id, _ in contributing}
        }
        if effects
        else {}
    )
    scores = dict.fromkeys(context.player_ids, 0)
    for owner, unit_id, model in contributing:
        operations = generic_characteristic_operations_from_effects(
            effects=effects_by_unit.get(unit_id, ()),
            characteristic=Characteristic.OBJECTIVE_CONTROL,
            model_instance_id=model.model_instance_id,
        )
        scores[owner] += apply_objective_control_operations(
            value=model_objective_control_characteristic(model, battle_shocked=False),
            modifiers=operations,
            model_instance_id=model.model_instance_id,
        ).final
    score = scores[player_id]
    opposition = max((value for owner, value in scores.items() if owner != player_id), default=0)
    if score > opposition:
        return True
    if score < opposition or not may_be_sticky:
        return False
    return None


def _contributor_rules_unit(
    context: HistoricalBattleShockAuthorityContext, unit_id: str
) -> RulesUnitView:
    view = rules_unit_view_from_armies(armies=context.armies, unit_instance_id=unit_id)
    if (
        view.is_attached_rules_unit
        and view.unit_instance_id not in context.active_attached_unit_ids
    ):
        raise GameLifecycleError("Historical Objective Control contributor attachment drifted.")
    return view


def _rules_unit_identities(view: RulesUnitView) -> tuple[str, ...]:
    return (view.unit_instance_id, *view.component_unit_instance_ids)


def _active_objective_control_effects(
    context: HistoricalBattleShockAuthorityContext, target_ids: set[str]
) -> tuple[PersistingEffect, ...]:
    if not target_ids:
        return ()

    def matches(payload: dict[str, JsonValue]) -> bool:
        return _may_modify_objective_control(payload, target_ids)

    sources = context.historical_effect_sources
    if sources is None:
        if historical_generic_effect_may_match(
            context.event_records[: context.boundary_event_index], matches
        ):
            raise GameLifecycleError("Historical Objective Control effect lacks loaded sources.")
        return ()
    historical = HistoricalEffectAuthority(
        game_id=context.game_id,
        player_ids=context.player_ids,
        turn_order=context.turn_order,
        battle_phase_sequence=context.battle_phase_sequence,
        armies=context.armies,
        event_records=context.event_records,
        decision_records=context.decision_records,
        boundary_event_index=context.boundary_event_index,
        player_id=context.request.player_id,
        battle_round=context.request.battle_round,
        active_player_id=context.active_player_id,
        phase=context.phase,
        rules_unit_at_event=lambda unit_id, _index: context.rules_unit_containing_unit(unit_id),
    )
    return historical_generic_effect_inventory(
        historical=historical,
        runtime_content_bundle=sources,
        matches_payload=matches,
    )


def _may_modify_objective_control(payload: dict[str, JsonValue], unit_ids: set[str]) -> bool:
    effect = payload.get("effect")
    if (
        not isinstance(effect, dict)
        or effect.get("kind") != RuleEffectKind.MODIFY_CHARACTERISTIC.value
    ):
        return False
    target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(target_ids, list) or not all(type(unit_id) is str for unit_id in target_ids):
        raise GameLifecycleError("Historical Objective Control effect targets are invalid.")
    if unit_ids.isdisjoint(cast(list[str], target_ids)):
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
