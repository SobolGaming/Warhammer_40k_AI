from __future__ import annotations

from warhammer40k_core.engine.battle_formation_hooks import BattleFormationHookBinding
from warhammer40k_core.engine.cult_ambush import (
    BATTLE_FORMATION_HOOK_ID,
    SOURCE_RULE_ID,
    TURN_END_HOOK_ID,
    UNIT_DESTROYED_HOOK_ID,
    apply_cult_ambush_marker_ingress_selection,
    grant_initial_resurgence_points,
)
from warhammer40k_core.engine.cult_ambush_destruction_candidates import (
    candidates as destruction_candidates,
)
from warhammer40k_core.engine.cult_ambush_timing_candidates import (
    candidates as cult_ambush_candidates,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
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
                candidate_handler=destruction_candidates,
            ),
        ),
        turn_end_hook_bindings=(
            TurnEndHookBinding(
                hook_id=TURN_END_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                candidate_handler=cult_ambush_candidates,
                trigger_kind=TimingTriggerKind.END_PHASE,
                result_handler=apply_cult_ambush_marker_ingress_selection,
            ),
        ),
    )
