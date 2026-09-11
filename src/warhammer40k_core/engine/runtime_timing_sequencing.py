from __future__ import annotations

from functools import partial

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventContext,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_window_events import (
    record_timing_window_boundary,
    timing_window_boundary_state,
)
from warhammer40k_core.engine.timing_windows import TimingWindow


def resolve_runtime_timing_window(
    *,
    state: GameState,
    decisions: DecisionController,
    window: TimingWindow,
    index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
    resolution_order: tuple[str, ...] = (),
    complete_window: bool = True,
) -> LifecycleStatus | None:
    if timing_window_boundary_state(
        decisions=decisions, window=window, resolution_order=resolution_order
    )[1]:
        return None
    record_timing_window_boundary(
        decisions=decisions,
        window=window,
        completed=False,
        resolution_order=resolution_order,
    )

    outcome = resolve_timing_rule_candidates(
        decisions=decisions,
        context=SequencingConflictContext(
            conflict_id=window.window_id,
            game_id=state.game_id,
            timing_window=window,
            player_ids=state.player_ids,
            active_player_id=window.active_player_id,
        ),
        discover=partial(
            runtime_timing_candidates,
            state=state,
            decisions=decisions,
            window=window,
            index=index,
            runtime_modifier_registry=runtime_modifier_registry,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            resolution_order=resolution_order,
        ),
        next_request_id=state.next_decision_request_id,
    )
    if type(outcome) is DecisionRequest:
        decisions.request_decision(outcome)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=outcome,
            payload={"phase_body_status": "runtime_timing_order_pending"},
        )
    if isinstance(outcome, LifecycleStatus):
        return outcome
    if complete_window:
        record_timing_window_boundary(
            decisions=decisions,
            window=window,
            completed=True,
            resolution_order=resolution_order,
        )
    return None


def runtime_timing_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    window: TimingWindow,
    index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
    resolution_order: tuple[str, ...] = (),
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.mission_timing_candidates import mission_timing_candidates

    mission_candidates = mission_timing_candidates(state=state, decisions=decisions, window=window)
    if not index.subscriptions_for(window.descriptor.trigger_kind):
        return mission_candidates
    if ruleset_descriptor is None or army_catalog is None:
        raise GameLifecycleError("Runtime timing rules require configured ruleset and catalog.")
    payload = validate_json_value(
        {
            "timing_window": window.to_payload(),
            "resolution_order": list(resolution_order),
        }
    )
    return mission_candidates + tuple(
        candidate
        for player_id in state.player_ids
        for candidate in index.candidates_for(
            RuntimeContentEventContext(
                event=RuntimeContentEvent(
                    event_id=f"{window.window_id}:runtime:{player_id}",
                    game_id=state.game_id,
                    player_id=player_id,
                    battle_round=window.battle_round,
                    trigger_kind=window.descriptor.trigger_kind,
                    phase=window.phase,
                    active_player_id=window.active_player_id,
                    event_payload=payload,
                ),
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                army_catalog=army_catalog,
                runtime_modifier_registry=runtime_modifier_registry,
            )
        )
    )
