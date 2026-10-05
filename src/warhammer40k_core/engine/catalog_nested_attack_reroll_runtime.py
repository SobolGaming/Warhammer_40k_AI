"""Nested conditions use the shared target, measurement and recorded control owners."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_effect_target_model_ids,
    source_applies_to_rules_unit,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_rule_attack_conditions import (
    closest_attack_target_distance_inches,
)
from warhammer40k_core.engine.objective_geometry import measure_rules_unit_to_objective
from warhammer40k_core.engine.objective_geometry_sources import mission_objective_geometries
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_views_for_state
from warhammer40k_core.engine.runtime_modifiers import AttackRerollPermissionContext
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.shooting_terrain_visibility import shooting_terrain_areas_for_state
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import SourceBackedRerollPermissionContext
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.rules.rule_ir import parameter_payload


def nested_attack_reroll_handler(
    source: CatalogDatasheetClauseSource,
    restrictions: ShootingTargetRestrictionHookRegistry | None,
) -> Callable[[AttackRerollPermissionContext], SourceBackedRerollPermissionContext | None]:
    def handler(
        context: AttackRerollPermissionContext,
    ) -> SourceBackedRerollPermissionContext | None:
        if (
            context.source_phase is not BattlePhase.SHOOTING
            or context.player_id != source.player_id
            or context.roll_type != "attack_sequence.hit"
            or context.timing_window != "attack_sequence.hit"
            or not source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            )
            or context.attacker_model_instance_id
            not in current_effect_target_model_ids(state=context.state, source=source)
        ):
            return None
        if context.weapon_profile is None or context.shooting_type is None:
            raise GameLifecycleError(
                "Nested attack reroll requires the actual weapon and shooting type."
            )
        if not _target_is_closest_eligible(context, restrictions):
            return None
        objectives = _opponent_controlled_objectives_in_target_range(context)
        parameters = parameter_payload(source.clause.effects[0].parameters)
        value = parameters["reroll_unmodified_value"]
        if type(value) is not int:
            raise GameLifecycleError("Nested attack reroll requires an integer reroll value.")
        payload: dict[str, JsonValue] = {
            "catalog_record_id": source.record.record_id,
            "source_rule_id": source.rule_ir.source_id,
            "source_clause_id": source.clause.clause_id,
            "source_unit_instance_id": source.unit.unit_instance_id,
            "nested_conditions": {
                "closest_eligible_target_unit_instance_id": context.target_unit_instance_id,
                "opponent_controlled_objective_ids": list(objectives),
                "improved_reroll_applies": bool(objectives),
            },
        }
        if not objectives:
            payload["conditional_hit_reroll"] = {"reroll_unmodified_values": [value]}
        return SourceBackedRerollPermissionContext(
            permission=RerollPermission(
                source_id=source.binding_id,
                timing_window=context.timing_window,
                owning_player_id=context.player_id,
                eligible_roll_type=context.roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
            source_payload=payload,
        )

    return handler


def _target_is_closest_eligible(
    context: AttackRerollPermissionContext,
    restrictions: ShootingTargetRestrictionHookRegistry | None,
) -> bool:
    # These are the same complete detection/history inputs as ordinary declarations.
    from warhammer40k_core.engine.phases.shooting_eligibility import (
        _detection_range_bonus_inches_by_target_id,
        _hidden_target_model_ids,
        _target_unit_ids_with_recent_ranged_attacks,
    )

    state = context.state
    scenario = battlefield_scenario_for_state(state=state)
    ruleset = state.runtime_ruleset_descriptor()
    attacker = rules_unit_view_by_id(
        state=state, unit_instance_id=context.attacking_unit_instance_id
    )
    model_id = context.attacker_model_instance_id
    if model_id is None or context.weapon_profile is None or context.shooting_type is None:
        raise GameLifecycleError("Closest eligible target requires complete attack context.")
    component = next(
        (
            component
            for component in attacker.components
            if model_id in component.unit.own_model_ids()
        ),
        None,
    )
    if component is None:
        raise GameLifecycleError("Closest eligible attacker does not belong to its rules unit.")
    enemies = tuple(
        view.unit_instance_id
        for view in rules_unit_views_for_state(state=state)
        if view.owner_player_id != context.player_id
    )
    hidden = _hidden_target_model_ids(
        state=state, ruleset_descriptor=ruleset, target_unit_ids=enemies
    )
    recent = _target_unit_ids_with_recent_ranged_attacks(state=state, target_unit_ids=enemies)
    bonuses = _detection_range_bonus_inches_by_target_id(state=state, target_unit_ids=enemies)
    distances: dict[str, float] = {}
    for enemy_id in enemies:
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            attacker_unit=component.unit,
            attacker_model_instance_id=model_id,
            weapon_profile=context.weapon_profile,
            target_unit_id=enemy_id,
            terrain_features=scenario.battlefield_state.terrain_features,
            terrain_areas=shooting_terrain_areas_for_state(state),
            hidden_target_model_ids=hidden,
            target_unit_ids_with_recent_ranged_attacks=recent,
            target_detection_range_bonus_inches=bonuses.get(enemy_id, 0),
        )
        if not candidate.is_legal:
            continue
        if context.shooting_type is ShootingType.SNAP:
            from warhammer40k_core.engine.phases.shooting_targeting import (
                _snap_shooting_type_allowed_for_unit_target,
            )

            if not _snap_shooting_type_allowed_for_unit_target(
                scenario=scenario,
                candidate=cast(dict[str, JsonValue], candidate.to_payload()),
                rules_unit=attacker,
                target_unit_id=enemy_id,
            ):
                continue
        elif context.shooting_type not in candidate.shooting_types:
            continue
        if restrictions is not None and restrictions.restrictions_for(
            ShootingTargetRestrictionContext(
                state=state,
                player_id=context.player_id,
                battle_round=state.battle_round,
                attacking_unit_instance_id=context.attacking_unit_instance_id,
                attacker_model_instance_id=model_id,
                target_unit_instance_id=enemy_id,
                shooting_type=context.shooting_type,
            )
        ):
            continue
        distances[enemy_id] = closest_attack_target_distance_inches(
            state=state,
            attacking_unit_instance_id=context.attacking_unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=enemy_id,
        )
    target = rules_unit_view_by_id(state=state, unit_instance_id=context.target_unit_instance_id)
    return target.unit_instance_id in distances and distances[target.unit_instance_id] == min(
        distances.values()
    )


def _opponent_controlled_objectives_in_target_range(
    context: AttackRerollPermissionContext,
) -> tuple[str, ...]:
    state = context.state
    # Core 14.02 updates control at phase/turn boundaries, not after every casualty.
    # The complete last engine-recorded boundary includes secured/sticky control.
    owners: dict[str, str | None] = {}
    for record in reversed(state.objective_control_records):
        for result in record.results:
            if result.objective_id not in owners:
                owners[result.objective_id] = result.controlled_by_player_id
    scenario = battlefield_scenario_for_state(state=state)
    target = rules_unit_view_by_id(state=state, unit_instance_id=context.target_unit_instance_id)
    return tuple(
        sorted(
            objective.objective_id
            for objective in mission_objective_geometries(state)
            if owners.get(objective.objective_id) not in {None, context.player_id}
            and any(
                measurement.within_control_range
                for measurement in measure_rules_unit_to_objective(
                    scenario=scenario, rules_unit=target, objective=objective
                )
            )
        )
    )
