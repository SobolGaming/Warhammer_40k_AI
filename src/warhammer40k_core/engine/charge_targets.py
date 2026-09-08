from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import (
    battlefield_scenario_for_state,
    fight_present_rules_unit_views,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.charge_declaration import ChargeTargetCandidate
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookRegistry,
    TargetRestriction,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def charge_target_restriction(
    *,
    state: GameState,
    charging_unit_instance_id: str,
    target_unit_instance_id: str,
    registry: ChargeTargetRestrictionHookRegistry | None,
) -> TargetRestriction | None:
    if registry is None:
        return None
    if type(registry) is not ChargeTargetRestrictionHookRegistry:
        raise GameLifecycleError("Charge target restriction requires a registry.")
    restrictions = registry.restrictions_for(
        ChargeTargetRestrictionContext(
            state=state,
            player_id=_active_player_id(state),
            battle_round=state.battle_round,
            charging_unit_instance_id=charging_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
        )
    )
    return restrictions[0] if restrictions else None


def charge_target_candidates(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[ChargeTargetCandidate, ...]:
    scenario = _battlefield_scenario(state)
    max_range = ruleset_descriptor.charge_policy.max_declaration_range_inches
    candidates: list[ChargeTargetCandidate] = []
    for target in fight_present_rules_unit_views(state=state):
        if target.owner_player_id == _active_player_id(state):
            continue
        target_id = target.unit_instance_id
        distance = closest_unit_distance_inches(
            scenario=scenario,
            source_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_id,
        )
        is_legal = distance <= max_range
        restriction = charge_target_restriction(
            state=state,
            charging_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_id,
            registry=charge_target_restriction_hooks,
        )
        violation_code: str | None
        if is_legal and restriction is not None:
            is_legal = False
            violation_code = restriction.violation_code
        else:
            violation_code = None if is_legal else "target_out_of_declaration_range"
        candidates.append(
            ChargeTargetCandidate(
                target_unit_instance_id=target_id,
                closest_distance_inches=distance,
                is_legal=is_legal,
                violation_code=violation_code,
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.target_unit_instance_id))


def closest_unit_distance_inches(
    *,
    scenario: BattlefieldScenario,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
) -> float:
    source_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=source_unit_instance_id,
    )
    target_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
    )
    if not source_models or not target_models:
        raise GameLifecycleError("Charge distance requires placed models.")
    return min(
        source_model.range_to(target_model)
        for source_model in source_models
        for target_model in target_models
    )


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    try:
        scenario = battlefield_scenario_for_state(state=state)
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Charge battlefield scenario is invalid.") from exc
    return scenario


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Charge phase requires active_player_id.")
    return state.active_player_id
