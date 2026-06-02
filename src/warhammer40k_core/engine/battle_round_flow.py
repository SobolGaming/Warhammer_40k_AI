from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


_LIFECYCLE_TIMING_RULE_ID = "core-rules-lifecycle-timing"
_END_WINDOW_RESOLUTION_ORDER = ("non_mission_rules", "mission_rules")


class BattleRoundFlow:
    def __init__(self, *, phase_handlers: Mapping[BattlePhase, PhaseHandler]) -> None:
        self._phase_handlers = dict(phase_handlers)

    def advance(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("BattleRoundFlow can advance only during battle.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("BattleRoundFlow requires a current battle phase.")

        handler = self._phase_handlers.get(current_phase)
        if handler is None:
            raise GameLifecycleError("BattleRoundFlow missing handler for current battle phase.")
        _emit_start_timing_windows(state=state, decisions=decisions)
        status = handler.begin_phase(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
        )
        if status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
            return status
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return status
        if status.status_kind is LifecycleStatusKind.INVALID:
            return status
        if (
            status.status_kind is LifecycleStatusKind.UNSUPPORTED
            and not _is_placeholder_noop_status(status)
        ):
            return status

        _emit_end_timing_windows(state=state, decisions=decisions)
        completed_phase = state.advance_to_next_battle_phase()
        decisions.event_log.append(
            "battle_phase_completed",
            {
                "game_id": state.game_id,
                "completed_phase": completed_phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "next_phase": _current_battle_phase_payload(state),
                "phase_body_status": _phase_body_status(status),
            },
        )
        if _state_is_complete(state):
            decisions.event_log.append(
                "game_completed",
                state.game_result_payload(),
            )
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game ended after configured battle rounds.",
                payload=state.game_result_payload(),
            )
        if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
            return LifecycleStatus.unsupported(
                stage=GameLifecycleStage.BATTLE,
                message="Phase body is a Phase 9B placeholder.",
                payload={
                    "completed_phase": completed_phase.value,
                    "phase_body_status": _phase_body_status(status),
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "current_phase": _current_battle_phase_payload(state),
                },
            )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "completed_phase": completed_phase.value,
                "phase_body_status": _phase_body_status(status),
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "current_phase": _current_battle_phase_payload(state),
            },
        )


def _current_battle_phase_payload(state: GameState) -> str | None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        return None
    return current_phase.value


def _state_is_complete(state: GameState) -> bool:
    return state.stage is GameLifecycleStage.COMPLETE


def _is_placeholder_noop_status(status: LifecycleStatus) -> bool:
    return _phase_body_status(status) == "placeholder_noop"


def _phase_body_status(status: LifecycleStatus) -> str:
    payload = status.payload
    if isinstance(payload, dict):
        value = payload.get("phase_body_status")
        if type(value) is str:
            return value
    return "complete"


def _emit_start_timing_windows(*, state: GameState, decisions: DecisionController) -> None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Start timing windows require a current battle phase.")
    battle_phase_index = state.battle_phase_index
    if battle_phase_index is None:
        raise GameLifecycleError("Start timing windows require a battle phase index.")
    active_player_id = _active_player_id(state)
    if battle_phase_index == 0 and active_player_id == state.turn_order[0]:
        _emit_timing_window_if_missing(
            state=state,
            decisions=decisions,
            trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
            active_player_id=None,
            phase=None,
            source_step="battle_round",
            window_id=(
                f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:start"
            ),
        )
    if battle_phase_index == 0:
        _emit_timing_window_if_missing(
            state=state,
            decisions=decisions,
            trigger_kind=TimingTriggerKind.START_TURN,
            active_player_id=active_player_id,
            phase=None,
            source_step="player_turn",
            window_id=(
                f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
                f"turn:{active_player_id}:start"
            ),
        )
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=active_player_id,
        phase=current_phase,
        source_step=current_phase.value,
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{current_phase.value}:start"
        ),
    )


def _emit_end_timing_windows(*, state: GameState, decisions: DecisionController) -> None:
    completed_phase = state.current_battle_phase
    if completed_phase is None:
        raise GameLifecycleError("End timing windows require a current battle phase.")
    battle_phase_index = state.battle_phase_index
    if battle_phase_index is None:
        raise GameLifecycleError("End timing windows require a battle phase index.")
    active_player_id = _active_player_id(state)
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_PHASE,
        active_player_id=active_player_id,
        phase=completed_phase,
        source_step=completed_phase.value,
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{completed_phase.value}:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
    )
    if battle_phase_index + 1 < len(state.battle_phase_sequence):
        return
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_TURN,
        active_player_id=active_player_id,
        phase=None,
        source_step="player_turn",
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
    )
    if state.turn_order.index(active_player_id) + 1 < len(state.turn_order):
        return
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
        active_player_id=None,
        phase=None,
        source_step="battle_round",
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
    )


def _emit_timing_window_if_missing(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger_kind: TimingTriggerKind,
    active_player_id: str | None,
    phase: BattlePhase | None,
    source_step: str,
    window_id: str,
    resolution_order: tuple[str, ...] = (),
) -> None:
    if _timing_window_event_exists(
        decisions=decisions,
        event_type="timing_window_resolved",
        window_id=window_id,
    ):
        return
    window = TimingWindow(
        window_id=window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{window_id}:descriptor",
            trigger_kind=trigger_kind,
            source_rule_id=_LIFECYCLE_TIMING_RULE_ID,
            phase=phase,
            source_step=source_step,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=phase,
    )
    payload = {
        "timing_window": window.to_payload(),
        "resolution_order": list(resolution_order),
    }
    decisions.event_log.append("timing_window_opened", payload)
    decisions.event_log.append("timing_window_resolved", payload)


def _timing_window_event_exists(
    *,
    decisions: DecisionController,
    event_type: str,
    window_id: str,
) -> bool:
    for record in decisions.event_log.records:
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        timing_window_payload = payload.get("timing_window")
        if not isinstance(timing_window_payload, dict):
            continue
        if timing_window_payload.get("window_id") == window_id:
            return True
    return False


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("BattleRoundFlow requires an active player.")
    return state.active_player_id
