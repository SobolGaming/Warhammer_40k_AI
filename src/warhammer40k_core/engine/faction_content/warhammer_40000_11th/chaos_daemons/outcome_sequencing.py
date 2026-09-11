# pyright: reportPrivateUsage=false
from __future__ import annotations

from functools import partial
from typing import cast

from warhammer40k_core.engine.battle_shock_hooks import BattleShockOutcomeContext
from warhammer40k_core.engine.battle_shock_outcome_sequencing import (
    outcome_candidate,
    outcome_recorded,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as rules


def candidates(
    context: BattleShockOutcomeContext,
    *,
    hook_id: str,
    source_rule_id: str,
    battleline_revival_enabled: bool,
) -> tuple[TimingRuleCandidate, ...]:
    target = rules_unit_view_by_id(
        state=context.state, unit_instance_id=context.result.request.unit_instance_id
    )
    found: list[TimingRuleCandidate] = []
    for army in rules._chaos_daemons_armies(context.state):
        if army.player_id == context.result.request.player_id:
            if not context.result.passed or not rules._daemonic_manifestation_applies(
                state=context.state,
                daemon_player_id=army.player_id,
                rules_unit=target,
                battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
            ):
                continue
            effect_id = f"{hook_id}:daemonic-manifestation-battleline:{context.result.result_id}"
            if any(
                event.event_type == "healing_resolved"
                and isinstance(event.payload, dict)
                and isinstance(event.payload.get("effect"), dict)
                and cast(dict[str, JsonValue], event.payload["effect"]).get("effect_id")
                == effect_id
                for event in context.decisions.event_log.records
            ):
                continue
            activate = partial(
                rules._resolve_daemonic_manifestation,
                context=context,
                daemon_player_id=army.player_id,
                target_rules_unit=target,
                hook_id=hook_id,
                source_rule_id=source_rule_id,
                battleline_revival_enabled=battleline_revival_enabled,
            )
        else:
            if (
                context.result.passed
                or not rules._daemonic_terror_applies(
                    state=context.state,
                    daemon_army=army,
                    target_rules_unit=target,
                    battle_shocked_unit_ids=context.phase_start_battle_shocked_unit_ids,
                )
                or outcome_recorded(
                    context,
                    event_types=("chaos_daemons_daemonic_terror_mortal_wounds_applied",),
                    owner_player_id=army.player_id,
                    source_rule_id=source_rule_id,
                )
            ):
                continue
            activate = partial(
                rules._resolve_daemonic_terror,
                context=context,
                daemon_army=army,
                target_rules_unit=target,
                source_rule_id=source_rule_id,
            )
        found.append(
            outcome_candidate(
                context,
                source_rule_id=source_rule_id,
                owner_player_id=army.player_id,
                occurrence_id=hook_id,
                activate=activate,
            )
        )
    return tuple(found)
