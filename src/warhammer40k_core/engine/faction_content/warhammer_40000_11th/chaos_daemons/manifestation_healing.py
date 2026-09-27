"""The existing Manifestation orchestrator's one-model healing sub-effect."""

from __future__ import annotations

from warhammer40k_core.core.dice import D3RollResult
from warhammer40k_core.engine.battle_shock_hooks import BattleShockOutcomeContext
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import healing_opposing_player_id
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.rules_units import RulesUnitView


def resolve_manifestation_healing(
    *,
    context: BattleShockOutcomeContext,
    daemon_player_id: str,
    target: RulesUnitView,
    hook_id: str,
    source_rule_id: str,
    d3_result: D3RollResult,
) -> LifecycleStatus | None:
    effect = HealingEffect(
        effect_id=f"{hook_id}:daemonic-manifestation:{context.result.result_id}",
        target_unit_instance_id=target.unit_instance_id,
        amount=d3_result.value,
        opposing_player_id=healing_opposing_player_id(
            state=context.state, player_id=daemon_player_id
        ),
        selection_actor_player_id=daemon_player_id,
        source_rule_id=source_rule_id,
        source_context={
            "hook_id": hook_id,
            "effect_kind": "daemonic_manifestation",
            "battle_shock_result_id": context.result.result_id,
            "player_id": daemon_player_id,
            "unit_instance_id": target.unit_instance_id,
            "single_model_heal": True,
            "d3_result": validate_json_value(d3_result.to_payload()),
        },
    )
    resolved, pending = resolve_healing_until_blocked(
        state=context.state,
        decisions=context.decisions,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    context.decisions.event_log.append(
        "chaos_daemons_daemonic_manifestation_healing_resolved",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "source_rule_id": source_rule_id,
            "battle_shock_result_id": context.result.result_id,
            "player_id": daemon_player_id,
            "unit_instance_id": target.unit_instance_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(resolved.to_payload()),
        },
    )
    if pending is None:
        return None
    return LifecycleStatus.waiting_for_decision(
        stage=context.state.stage,
        decision_request=pending,
        payload={"phase_body_status": "battle_shock_outcome_pending"},
    )
