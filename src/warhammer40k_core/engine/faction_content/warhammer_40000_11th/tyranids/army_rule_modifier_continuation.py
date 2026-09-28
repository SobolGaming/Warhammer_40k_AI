"""Shadow target-batch authority across nested test and modifier decisions."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.command_phase_start_hooks import (
    COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND,
    CommandPhaseStartNestedPendingAuthorityContext,
    CommandPhaseStartNestedResultContext,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState, FactionRuleStatePayload
from warhammer40k_core.engine.phase import GameLifecycleError


def shadow_source_state_from_nested_request(
    *,
    context: CommandPhaseStartNestedResultContext | CommandPhaseStartNestedPendingAuthorityContext,
) -> FactionRuleState | None:
    from warhammer40k_core.engine.battle_shock_modifier_continuation import (
        battle_shock_modifier_execution,
    )

    from . import army_rule as owner

    execution = battle_shock_modifier_execution(context.request)
    if execution is not None:
        if execution["source_kind"] != COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND:
            return None
        base = owner._payload_object(execution["base_payload"])
        source = FactionRuleState.from_payload(
            cast(
                FactionRuleStatePayload,
                owner._payload_object(base["source_faction_rule_state"]),
            )
        )
        if source not in context.state.faction_rule_states:
            raise GameLifecycleError("Shadow modifier source state drifted.")
        payload = owner._payload_object(source.payload)
        if (
            source.source_rule_id != owner.SOURCE_RULE_ID
            or source.state_kind != owner.SHADOW_STATE_KIND
            or payload.get("hook_id") != owner.HOOK_ID
        ):
            return None
        owner._validate_shadow_continuation_occurrence(
            state=context.state,
            decisions=context.decisions,
            active_player_id=context.active_player_id,
            source_state=source,
        )
        if type(context) is CommandPhaseStartNestedPendingAuthorityContext:
            request_payload = owner._payload_object(execution["request"])
            next_id = owner._validate_shadow_continuation_prefix(
                state=context.state,
                decisions=context.decisions,
                active_player_id=context.active_player_id,
                source_state=source,
            )
            if request_payload["request_id"] != next_id:
                raise GameLifecycleError("Shadow modifier target order drifted.")
        return source
    return _existing_nested_source(context=context)


def _existing_nested_source(
    *,
    context: CommandPhaseStartNestedResultContext | CommandPhaseStartNestedPendingAuthorityContext,
) -> FactionRuleState | None:
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockPendingOutcomeAuthorityContext,
    )
    from warhammer40k_core.engine.battle_shock_resolution_authority import (
        parse_pending_battle_shock_reroll_authority,
    )
    from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE

    from .army_rule import (
        _payload_object,
        _validate_shadow_continuation_occurrence,
        shadow_source_state_from_pending_authority,
        validate_shadow_outcome_result_prefix,
    )

    request = context.request
    if request.decision_type == DICE_REROLL_DECISION_TYPE:
        authority = parse_pending_battle_shock_reroll_authority(request)
        if authority.source_kind != COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND:
            return None
        return shadow_source_state_from_pending_authority(
            state=context.state,
            authority=authority,
        )
    outcome = context.battle_shock_hooks.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=context.state,
            decisions=context.decisions,
            request=request,
        )
    )
    if outcome is None:
        return None
    resolved_event = context.decisions.event_log.records[outcome.resolved_event_index]
    resolved_payload = _payload_object(resolved_event.payload)
    if (
        resolved_event.event_type != "battle_shock_test_resolved"
        or resolved_payload.get("battle_shock_result") != outcome.result.to_payload()
    ):
        raise GameLifecycleError("Shadow in the Warp outcome result authority drifted.")
    raw_source_state = resolved_payload.get("source_faction_rule_state")
    if not isinstance(raw_source_state, dict):
        raise GameLifecycleError("Shadow in the Warp outcome lacks source-state authority.")
    source_state = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw_source_state))
    if source_state not in context.state.faction_rule_states:
        raise GameLifecycleError("Shadow in the Warp outcome source state drifted.")
    _validate_shadow_continuation_occurrence(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        source_state=source_state,
    )
    validate_shadow_outcome_result_prefix(
        state=context.state,
        decisions=context.decisions,
        source_state=source_state,
        result=outcome.result,
    )
    return source_state
