from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
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
