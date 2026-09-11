# pyright: reportPrivateUsage=false
from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.battle_shock_hooks import BattleShockOutcomeContext
from warhammer40k_core.engine.battle_shock_outcome_sequencing import (
    outcome_candidate,
    outcome_recorded,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as rules


def candidates(context: BattleShockOutcomeContext) -> tuple[TimingRuleCandidate, ...]:
    if context.result.passed:
        return ()
    target = rules_unit_view_by_id(
        state=context.state, unit_instance_id=context.result.request.unit_instance_id
    )
    return tuple(
        outcome_candidate(
            context,
            source_rule_id=rules.SOURCE_RULE_ID,
            owner_player_id=army.player_id,
            occurrence_id=rules.HOOK_ID,
            activate=partial(
                rules._apply_delirium_mortal_wounds,
                context=context,
                chaos_knights_player_id=army.player_id,
                target_rules_unit=target,
            ),
        )
        for army in rules.chaos_knights_armies(context.state)
        if army.player_id != context.result.request.player_id
        and rules.DreadAbility.DELIRIUM
        in rules.active_dread_abilities_for_player(context.state, player_id=army.player_id)
        and rules._unit_is_below_half_strength(
            context.state, player_id=target.owner_player_id, rules_unit=target
        )
        and rules._unit_within_dread_aura(
            state=context.state, dread_army=army, target_unit_instance_id=target.unit_instance_id
        )
        and not outcome_recorded(
            context,
            event_types=("chaos_knights_delirium_mortal_wounds_applied",),
            owner_player_id=army.player_id,
            source_rule_id=rules.SOURCE_RULE_ID,
        )
    )
