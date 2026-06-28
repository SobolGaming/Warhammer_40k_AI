from __future__ import annotations

from warhammer40k_core.engine.battle_formation_hooks import BattleFormationHookBinding
from warhammer40k_core.engine.cult_ambush import (
    BATTLE_FORMATION_HOOK_ID,
    SOURCE_RULE_ID,
    TURN_END_HOOK_ID,
    UNIT_DESTROYED_HOOK_ID,
    apply_cult_ambush_marker_ingress_selection,
    cult_ambush_marker_ingress_request,
    grant_initial_resurgence_points,
    request_cult_ambush_resurgence,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookBinding

CONTRIBUTION_ID = SOURCE_RULE_ID


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_formation_hook_bindings=(
            BattleFormationHookBinding(
                hook_id=BATTLE_FORMATION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=grant_initial_resurgence_points,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=request_cult_ambush_resurgence,
            ),
        ),
        turn_end_hook_bindings=(
            TurnEndHookBinding(
                hook_id=TURN_END_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=cult_ambush_marker_ingress_request,
                result_handler=apply_cult_ambush_marker_ingress_selection,
            ),
        ),
    )
