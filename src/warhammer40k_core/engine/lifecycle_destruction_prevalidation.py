from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine.cult_ambush import SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_triggers import destroyed_unit_context
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
from warhammer40k_core.engine.timing_request_candidates import selected_timing_request_is_current
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.tracked_targets import SELECT_TRACKED_TARGET_DECISION_TYPE
from warhammer40k_core.engine.unit_destruction_sequencing import unit_destruction_timing_context

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


def validate_destruction_request_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
) -> None:
    if request.decision_type not in (
        SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
        SELECT_TRACKED_TARGET_DECISION_TYPE,
    ):
        return
    history = rule_trigger_history(decisions)
    if request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE:
        payload = request.payload
        selected_death_batch = any(
            batch.selected_participant_id is not None
            and batch.context.timing_window.descriptor.trigger_kind
            is TimingTriggerKind.AFTER_UNIT_DESTROYED
            for batch in history.batches
        )
        if not selected_death_batch and (
            not isinstance(payload, dict)
            or (
                payload.get("replacement") is not True
                and "destroyed_trigger_event_id" not in payload
            )
        ):
            return
    triggers = tuple(
        trigger
        for trigger in history.ready()
        if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION
        and trigger.trigger_id in history.released
    )
    if len(triggers) != 1:
        raise GameLifecycleError("Unit-destruction choice requires one released source occurrence.")
    context = destroyed_unit_context(state=state, decisions=decisions, trigger=triggers[0])
    if context is None:
        raise GameLifecycleError("Unit-destruction choice lacks a logical unit destruction.")
    if not selected_timing_request_is_current(
        decisions=decisions,
        context=unit_destruction_timing_context(context),
        request=request,
        candidates=runtime_bundle_provider().unit_destroyed_hook_registry.candidates_for(context),
    ):
        raise GameLifecycleError("Unit-destruction choice source template drift.")


def invalid_destruction_request_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
) -> LifecycleStatus | None:
    try:
        validate_destruction_request_authority(
            state=state,
            decisions=decisions,
            request=request,
            runtime_bundle_provider=runtime_bundle_provider,
        )
    except GameLifecycleError as error:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(error),
            payload={"invalid_reason": "unit_destruction_source_authority_drift"},
        )
    return None
