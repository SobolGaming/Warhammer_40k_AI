from __future__ import annotations

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.prebattle_records import (
    PreBattleAlternationCursor,
)

SELECT_PREBATTLE_ACTION_DECISION_TYPE = "select_prebattle_action"
SUBMIT_SCOUT_MOVE_DECISION_TYPE = "submit_scout_move"
SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE = "submit_scout_reserve_setup"
PREBATTLE_ALTERNATION_DECISION_TYPES = frozenset(
    {
        SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    }
)


def align_prebattle_alternation_cursor(
    *,
    state: GameState,
    action_counts: dict[str, int],
    completed_player_ids: tuple[str, ...],
) -> PreBattleAlternationCursor:
    cursor = state.prebattle_alternation_cursor
    if cursor is None:
        cursor = PreBattleAlternationCursor.start(
            game_id=state.game_id,
            ordered_player_ids=state.turn_order,
        )
    next_player_id = _next_player_id(
        cursor=cursor,
        action_counts=action_counts,
        completed_player_ids=completed_player_ids,
    )
    aligned = cursor.aligned_to(next_player_id)
    state.set_prebattle_alternation_cursor(aligned)
    return aligned


def validate_prebattle_alternation_restore(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    cursor = state.prebattle_alternation_cursor
    prebattle_records = tuple(
        record
        for record in state.prebattle_action_records
        if record.setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    )
    alternation_pending_requests = tuple(
        request
        for request in pending_decision_requests
        if request.decision_type in PREBATTLE_ALTERNATION_DECISION_TYPES
    )
    if cursor is None:
        if prebattle_records or (
            state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
            and alternation_pending_requests
        ):
            raise GameLifecycleError("Restored pre-battle state requires an alternation cursor.")
        return
    decision_by_result_id = {record.result.result_id: record for record in decision_records}
    for action_record in prebattle_records:
        decision_record = decision_by_result_id.get(action_record.result_id)
        if decision_record is None:
            raise GameLifecycleError(
                "Restored pre-battle action is missing its authoritative decision record."
            )
        if (
            decision_record.request.request_id != action_record.request_id
            or decision_record.request.actor_id != action_record.player_id
            or decision_record.result.actor_id != action_record.player_id
        ):
            raise GameLifecycleError(
                "Restored pre-battle action drifted from its authoritative decision."
            )
    if state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS:
        if (
            alternation_pending_requests
            and alternation_pending_requests[0].actor_id != cursor.next_player_id
        ):
            raise GameLifecycleError(
                "Restored pending decision actor drifted from the pre-battle alternation cursor."
            )
    elif cursor.next_player_id is not None:
        raise GameLifecycleError(
            "Completed pre-battle alternation cursor must not retain a next player."
        )


def _next_player_id(
    *,
    cursor: PreBattleAlternationCursor,
    action_counts: dict[str, int],
    completed_player_ids: tuple[str, ...],
) -> str | None:
    if set(action_counts) != set(cursor.ordered_player_ids):
        raise GameLifecycleError("Pre-battle action counts drifted from the turn order.")
    if cursor.next_player_id is None:
        return None
    start_index = cursor.ordered_player_ids.index(cursor.next_player_id)
    for offset in range(len(cursor.ordered_player_ids)):
        player_id = cursor.ordered_player_ids[
            (start_index + offset) % len(cursor.ordered_player_ids)
        ]
        if player_id in completed_player_ids:
            continue
        if action_counts[player_id] > 0:
            return player_id
    return None
