"""Advance the shared lifecycle, pausing at engine-owned choices."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import (
    catalog_selected_target_battle_shock_continuation as _selected_target_bs,
)
from warhammer40k_core.engine.core_ability_selection import request_core_ability_selection_if_needed
from warhammer40k_core.engine.phase import GameLifecycleStage, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def advance_once(host: GameLifecycle) -> LifecycleStatus:
    state = host._require_state()
    selection_status = request_core_ability_selection_if_needed(
        state=state,
        decisions=host.decision_controller,
        registry=host._shooting_phase_handler.runtime_modifier_registry,
    )
    if selection_status is not None:
        return selection_status
    from warhammer40k_core.engine.rule_trigger_runtime import advance_rule_triggers

    trigger_status = advance_rule_triggers(
        state=state,
        decisions=host.decision_controller,
        runtime_bundle_provider=host._require_runtime_content_bundle,
        shooting_handler_provider=lambda: host._shooting_phase_handler,
    )
    if trigger_status is not None:
        return trigger_status
    from warhammer40k_core.engine.interrupted_charge import advance_interrupted_charge

    interrupted = advance_interrupted_charge(
        state=state,
        decisions=host.decision_controller,
        reaction_queue=host.reaction_queue,
        handler=host._charge_phase_handler,
    )
    if interrupted is not None:
        return interrupted
    from warhammer40k_core.engine.charge_target_continuation import refresh_pending_charge_move

    charge_continuation = refresh_pending_charge_move(
        state=state,
        decisions=host.decision_controller,
        handler=host._charge_phase_handler,
    )
    if charge_continuation is not None:
        return charge_continuation
    pending_request = host._pending_decision_request()
    continuation_status = (
        _selected_target_bs.advance_catalog_selected_target_battle_shock_lifecycle(
            state=state,
            decisions=host.decision_controller,
            pending_request=pending_request,
            runtime_content_bundle=host._runtime_content_bundle,
        )
    )
    if continuation_status is not None:
        return continuation_status
    from warhammer40k_core.engine.retained_shooting import advance_retained_shooting

    retained_shooting_status = advance_retained_shooting(
        runtime_modifier_registry=host._shooting_phase_handler.runtime_modifier_registry,
        state=state,
        decisions=host.decision_controller,
        ruleset_descriptor=host._require_config().ruleset_descriptor,
        army_catalog=host._require_config().army_catalog,
    )
    if retained_shooting_status is not None:
        return retained_shooting_status
    out_of_phase_status = host._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
        state=state,
        decisions=host.decision_controller,
    )
    if out_of_phase_status is not None:
        if host._reconcile_catalog_model_state_changes():
            host._refresh_runtime_content_bundle_if_armies_mustered()
        return out_of_phase_status
    forced_fight_status = host._fight_phase_handler.advance_forced_fight_activations_if_needed(
        state=state,
        decisions=host.decision_controller,
        reaction_queue=host.reaction_queue,
    )
    if forced_fight_status is not None:
        if host._reconcile_catalog_model_state_changes():
            host._refresh_runtime_content_bundle_if_armies_mustered()
        return forced_fight_status
    if state.stage is GameLifecycleStage.COMPLETE:
        return LifecycleStatus.terminal(
            stage=GameLifecycleStage.COMPLETE,
            message="Game lifecycle is complete.",
            payload=state.game_result_payload(),
        )
    if state.stage is GameLifecycleStage.SETUP:
        status = host._setup_flow.advance(
            state=state,
            decisions=host.decision_controller,
            config=host._require_config(),
            reaction_frame_count=len(host.reaction_queue.frames),
        )
        host._refresh_runtime_content_bundle_if_armies_mustered()
        return status
    status = host._require_battle_round_flow().advance(
        state=state,
        decisions=host.decision_controller,
        reaction_queue=host.reaction_queue,
    )
    if host._reconcile_catalog_model_state_changes():
        host._refresh_runtime_content_bundle_if_armies_mustered()
    return status
