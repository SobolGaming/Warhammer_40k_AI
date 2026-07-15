from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalRestrictionContext,
    ReserveArrivalRestrictionHookRegistry,
)
from warhammer40k_core.engine.reserves import (
    ReservePlacementViolation,
    ReservePlacementViolationCode,
    ReserveState,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView


def reserve_arrival_restriction_violations(
    *,
    state: object,
    scenario: BattlefieldScenario,
    reserve_state: ReserveState,
    rules_unit: RulesUnitView,
    attempted_rules_unit_placement: RulesUnitPlacement,
    placement_kind: BattlefieldPlacementKind,
    registry: ReserveArrivalRestrictionHookRegistry,
) -> tuple[ReservePlacementViolation, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Reserve-arrival restriction resolution requires GameState.")
    if type(registry) is not ReserveArrivalRestrictionHookRegistry:
        raise GameLifecycleError("Reserve-arrival restriction resolution requires registry.")
    restrictions = registry.restrictions_for(
        ReserveArrivalRestrictionContext(
            state=state,
            scenario=scenario,
            reserve_state=reserve_state,
            rules_unit=rules_unit,
            attempted_rules_unit_placement=attempted_rules_unit_placement,
            placement_kind=placement_kind,
        )
    )
    return tuple(
        ReservePlacementViolation(
            violation_code=ReservePlacementViolationCode.RESERVE_ARRIVAL_ABILITY_RESTRICTION,
            message=("Reserve placement violates a source-backed minimum-distance ability."),
            model_instance_id=restriction.arriving_model_instance_id,
            blocker_id=restriction.source_model_instance_id,
        )
        for restriction in restrictions
    )
