from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockCompletedOutcomeAuthorityContext,
    BattleShockHookRegistry,
    BattleShockPendingOutcomeAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_resolution import BattleShockResolutionResult
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    BattleShockResolutionAuthority,
    parse_battle_shock_resolution_authority,
    parse_pending_battle_shock_reroll_authority,
)
from warhammer40k_core.engine.battle_shock_source_family_authority import (
    validate_battle_shock_source_family_authority,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_state import (
    DesperateEscapeBattleShockContinuationPhase,
    DesperateEscapeBattleShockContinuationSourceKind,
    MovementPhaseState,
    PendingDesperateEscapeBattleShockContinuation,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

_FORCED_SOURCE_KIND = "forced_desperate_escape_battle_shock"
_VOLUNTARY_SOURCE_KIND = "desperate_escape_battle_shock"


def begin_desperate_escape_battle_shock_continuation(
    *,
    state: GameState,
    continuation: PendingDesperateEscapeBattleShockContinuation,
) -> None:
    movement_state = _movement_state(state)
    if movement_state.pending_desperate_escape_battle_shock_continuation is not None:
        raise GameLifecycleError("A Desperate Escape Battle-shock continuation is already pending.")
    state.replace_movement_phase_state(
        movement_state.with_desperate_escape_battle_shock_continuation(continuation)
    )


def record_desperate_escape_battle_shock_resolution(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    resolution: BattleShockResolutionResult,
    reroll_result_id: str | None,
) -> LifecycleStatus | None:
    continuation = pending_desperate_escape_battle_shock_continuation(state)
    if resolution.resolved_payload is None:
        status = resolution.pending_status
        if status is None or status.decision_request is None:
            raise GameLifecycleError(
                "Unresolved Desperate Escape Battle-shock requires its reroll queue head."
            )
        if reroll_result_id is not None:
            raise GameLifecycleError("Desperate Escape Battle-shock reroll did not resolve.")
        _validate_pending_status_queue_head(decisions=decisions, status=status)
        pending_authority = parse_pending_battle_shock_reroll_authority(status.decision_request)
        _validate_pending_reroll_matches_continuation(
            continuation=continuation,
            pending_authority=pending_authority,
        )
        _replace_continuation(
            state,
            continuation.awaiting_reroll(status.decision_request.request_id),
        )
        return status

    battle_shock_result = _battle_shock_result_from_resolved_payload(resolution.resolved_payload)
    updated = continuation.awaiting_outcome(
        battle_shock_result_id=battle_shock_result.result_id,
        battle_shock_reroll_result_id=reroll_result_id,
    )
    authority = _validate_resolved_continuation_authority(
        continuation=updated,
        decisions=decisions,
    )
    status = resolution.pending_status
    if status is not None:
        _validate_pending_status_queue_head(decisions=decisions, status=status)
        _validate_pending_outcome_authority(
            state=state,
            decisions=decisions,
            battle_shock_hooks=battle_shock_hooks,
            status=status,
            authority=authority,
        )
        _replace_continuation(state, updated)
        return status
    if decisions.queue.pending_requests:
        raise GameLifecycleError(
            "Resolved Desperate Escape Battle-shock hid an outcome decision queue head."
        )
    battle_shock_hooks.validate_completed_outcome_authority(
        BattleShockCompletedOutcomeAuthorityContext(state=state, decisions=decisions)
    )
    _clear_continuation(state)
    return None


def validate_pending_desperate_escape_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    require_pending_request: bool,
) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None:
        return
    continuation = movement_state.pending_desperate_escape_battle_shock_continuation
    if continuation is None:
        return
    pending_requests = decisions.queue.pending_requests
    if continuation.continuation_phase is (
        DesperateEscapeBattleShockContinuationPhase.AWAITING_BATTLE_SHOCK
    ):
        if len(pending_requests) != 1:
            raise GameLifecycleError(
                "Pending Desperate Escape Battle-shock reroll must be the sole queue head."
            )
        pending_reroll_authority = parse_pending_battle_shock_reroll_authority(pending_requests[0])
        _validate_pending_reroll_matches_continuation(
            continuation=continuation,
            pending_authority=pending_reroll_authority,
        )
        return
    resolved_authority = _validate_resolved_continuation_authority(
        continuation=continuation,
        decisions=decisions,
    )
    if pending_requests:
        if len(pending_requests) != 1:
            raise GameLifecycleError(
                "Pending Desperate Escape Battle-shock outcome must be the sole queue head."
            )
        _validate_pending_outcome_authority(
            state=state,
            decisions=decisions,
            battle_shock_hooks=battle_shock_hooks,
            status=LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=pending_requests[0],
                payload={"continuation_phase": continuation.continuation_phase.value},
            ),
            authority=resolved_authority,
        )
        return
    if require_pending_request:
        raise GameLifecycleError(
            "Restored Desperate Escape Battle-shock continuation lacks its outcome request."
        )
    battle_shock_hooks.validate_completed_outcome_authority(
        BattleShockCompletedOutcomeAuthorityContext(state=state, decisions=decisions)
    )


def validate_restored_desperate_escape_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    movement_state = state.movement_phase_state
    if (
        movement_state is None
        or movement_state.pending_desperate_escape_battle_shock_continuation is None
    ):
        return
    if runtime_content_bundle is None:
        raise GameLifecycleError(
            "Desperate Escape Battle-shock restoration requires runtime content."
        )
    validate_pending_desperate_escape_battle_shock_continuation(
        state=state,
        decisions=decisions,
        battle_shock_hooks=runtime_content_bundle.battle_shock_hook_registry,
        require_pending_request=True,
    )


def pending_desperate_escape_battle_shock_continuation(
    state: GameState,
) -> PendingDesperateEscapeBattleShockContinuation:
    continuation = _movement_state(state).pending_desperate_escape_battle_shock_continuation
    if continuation is None:
        raise GameLifecycleError("Desperate Escape Battle-shock continuation is missing.")
    return continuation


def complete_desperate_escape_battle_shock_continuation(*, state: GameState) -> None:
    continuation = pending_desperate_escape_battle_shock_continuation(state)
    if continuation.continuation_phase is not (
        DesperateEscapeBattleShockContinuationPhase.AWAITING_OUTCOME
    ):
        raise GameLifecycleError("Desperate Escape Battle-shock outcome is not complete.")
    _clear_continuation(state)


def _validate_pending_status_queue_head(
    *,
    decisions: DecisionController,
    status: LifecycleStatus,
) -> None:
    pending_requests = decisions.queue.pending_requests
    if (
        len(pending_requests) != 1
        or status.decision_request is None
        or status.decision_request != pending_requests[0]
    ):
        raise GameLifecycleError(
            "Desperate Escape Battle-shock status must identify the actual queue head."
        )


def _validate_pending_outcome_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    status: LifecycleStatus,
    authority: BattleShockResolutionAuthority,
) -> None:
    request = status.decision_request
    if request is None:
        raise GameLifecycleError("Desperate Escape outcome status requires a request.")
    claim = battle_shock_hooks.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=state,
            decisions=decisions,
            request=request,
        )
    )
    if (
        claim is None
        or claim.result != authority.result
        or claim.resolved_event_index != authority.resolved_event_index
    ):
        raise GameLifecycleError(
            "Desperate Escape continuation lacks exact provider outcome authority."
        )


def _validate_resolved_continuation_authority(
    *,
    continuation: PendingDesperateEscapeBattleShockContinuation,
    decisions: DecisionController,
) -> BattleShockResolutionAuthority:
    result_id = continuation.battle_shock_result_id
    if result_id is None:
        raise GameLifecycleError("Desperate Escape continuation lacks Battle-shock result ID.")
    matches: list[tuple[int, dict[str, JsonValue], BattleShockResult]] = []
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type != "battle_shock_test_resolved" or not isinstance(event.payload, dict):
            continue
        raw_result = event.payload.get("battle_shock_result")
        if not isinstance(raw_result, dict) or raw_result.get("result_id") != result_id:
            continue
        matches.append(
            (
                index,
                event.payload,
                BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result)),
            )
        )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Desperate Escape continuation requires one exact Battle-shock result occurrence."
        )
    resolved_index, resolved_payload, result = matches[0]
    authority = parse_battle_shock_resolution_authority(
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        resolved_index=resolved_index,
        resolved_payload=resolved_payload,
        result=result,
    )
    validate_battle_shock_source_family_authority(
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        resolved_index=resolved_index,
        request_payload=cast(
            dict[str, JsonValue], validate_json_value(result.request.to_payload())
        ),
        request_context=authority.request_context,
        request_base=authority.base_payload,
        result=result,
    )
    _validate_resolution_matches_continuation(
        continuation=continuation,
        authority=authority,
    )
    return authority


def _validate_resolution_matches_continuation(
    *,
    continuation: PendingDesperateEscapeBattleShockContinuation,
    authority: BattleShockResolutionAuthority,
) -> None:
    result = authority.result
    if (
        result.request.request_id != continuation.battle_shock_request_id
        or result.request.unit_instance_id != continuation.canonical_unit_instance_id
        or authority.base_payload.get("unit_instance_id") != continuation.canonical_unit_instance_id
        or authority.base_payload.get("fall_back_result")
        != continuation.fall_back_result.to_payload()
        or authority.base_payload.get("action_result") != continuation.action_result.to_payload()
        or authority.base_payload.get("movement_proposal_request_id")
        != continuation.movement_proposal_request_id
        or authority.base_payload.get("source_kind") != _source_kind(continuation)
    ):
        raise GameLifecycleError("Desperate Escape continuation source occurrence drifted.")
    if continuation.source_kind is (
        DesperateEscapeBattleShockContinuationSourceKind.VOLUNTARY_POST_MOVE
    ):
        transition = continuation.transition_batch
        if (
            authority.base_payload.get("fall_back_applied_event_id")
            != continuation.fall_back_applied_event_id
            or authority.base_payload.get("movement_payload") != continuation.movement_payload
            or transition is None
            or authority.base_payload.get("transition_batch") != transition.to_payload()
        ):
            raise GameLifecycleError("Desperate Escape continuation applied movement drifted.")
    reroll = authority.reroll
    if reroll is None:
        if (
            continuation.battle_shock_reroll_request_id is not None
            or continuation.battle_shock_reroll_result_id is not None
        ):
            raise GameLifecycleError("Desperate Escape continuation reroll authority drifted.")
    elif (
        reroll.decision_record.request.request_id != continuation.battle_shock_reroll_request_id
        or reroll.decision_record.result.result_id != continuation.battle_shock_reroll_result_id
    ):
        raise GameLifecycleError("Desperate Escape continuation reroll authority drifted.")


def _validate_pending_reroll_matches_continuation(
    *,
    continuation: PendingDesperateEscapeBattleShockContinuation,
    pending_authority: object,
) -> None:
    from warhammer40k_core.engine.battle_shock_resolution_authority import (
        PendingBattleShockRerollAuthority,
    )

    if type(pending_authority) is not PendingBattleShockRerollAuthority:
        raise GameLifecycleError("Desperate Escape pending reroll authority must be typed.")
    authority = pending_authority
    base = authority.base_payload
    if (
        authority.source_kind != _source_kind(continuation)
        or authority.test_request.request_id != continuation.battle_shock_request_id
        or authority.test_request.unit_instance_id != continuation.canonical_unit_instance_id
        or base.get("unit_instance_id") != continuation.canonical_unit_instance_id
        or base.get("fall_back_result") != continuation.fall_back_result.to_payload()
        or base.get("action_result") != continuation.action_result.to_payload()
        or base.get("movement_proposal_request_id") != continuation.movement_proposal_request_id
    ):
        raise GameLifecycleError("Desperate Escape pending reroll occurrence drifted.")
    if continuation.battle_shock_reroll_request_id not in (
        None,
        authority.decision_request.request_id,
    ):
        raise GameLifecycleError("Desperate Escape pending reroll request ID drifted.")
    if continuation.source_kind is (
        DesperateEscapeBattleShockContinuationSourceKind.VOLUNTARY_POST_MOVE
    ):
        transition = continuation.transition_batch
        if (
            base.get("fall_back_applied_event_id") != continuation.fall_back_applied_event_id
            or base.get("movement_payload") != continuation.movement_payload
            or transition is None
            or base.get("transition_batch") != transition.to_payload()
        ):
            raise GameLifecycleError("Desperate Escape pending reroll movement drifted.")


def _battle_shock_result_from_resolved_payload(
    payload: dict[str, JsonValue],
) -> BattleShockResult:
    raw_result = payload.get("battle_shock_result")
    if not isinstance(raw_result, dict):
        raise GameLifecycleError("Desperate Escape Battle-shock result payload is missing.")
    return BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result))


def _source_kind(continuation: PendingDesperateEscapeBattleShockContinuation) -> str:
    if continuation.source_kind is (
        DesperateEscapeBattleShockContinuationSourceKind.FORCED_PRE_MOVE
    ):
        return _FORCED_SOURCE_KIND
    return _VOLUNTARY_SOURCE_KIND


def _movement_state(state: GameState) -> MovementPhaseState:
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Desperate Escape continuation requires movement phase state.")
    return movement_state


def _replace_continuation(
    state: GameState,
    continuation: PendingDesperateEscapeBattleShockContinuation,
) -> None:
    state.replace_movement_phase_state(
        _movement_state(state).with_desperate_escape_battle_shock_continuation(continuation)
    )


def _clear_continuation(state: GameState) -> None:
    state.replace_movement_phase_state(
        _movement_state(state).without_desperate_escape_battle_shock_continuation()
    )


__all__ = (
    "begin_desperate_escape_battle_shock_continuation",
    "complete_desperate_escape_battle_shock_continuation",
    "pending_desperate_escape_battle_shock_continuation",
    "record_desperate_escape_battle_shock_resolution",
    "validate_pending_desperate_escape_battle_shock_continuation",
    "validate_restored_desperate_escape_battle_shock_continuation",
)
