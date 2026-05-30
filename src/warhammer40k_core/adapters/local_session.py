from __future__ import annotations

from dataclasses import dataclass, field

from warhammer40k_core.adapters.decisions import submit_option, submit_payload
from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.projection import GameViewPayload, project_game_view
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


def _new_parameterized_lifecycle() -> GameLifecycle:
    return GameLifecycle(parameterized_movement_proposals=True)


@dataclass(slots=True)
class LocalGameSession:
    lifecycle: GameLifecycle = field(default_factory=_new_parameterized_lifecycle)

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("LocalGameSession config must be a GameConfig.")
        return self.lifecycle.start(config)

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        return self.lifecycle.advance_until_decision_or_terminal()

    def submit_option(self, *, option_id: str, result_id: str) -> LifecycleStatus:
        return submit_option(
            lifecycle=self.lifecycle,
            option_id=option_id,
            result_id=result_id,
        )

    def submit_payload(self, *, payload: JsonValue, result_id: str) -> LifecycleStatus:
        return submit_payload(
            lifecycle=self.lifecycle,
            payload=payload,
            result_id=result_id,
        )

    def view(self, *, viewer_player_id: str) -> GameViewPayload:
        return project_game_view(
            lifecycle=self.lifecycle,
            viewer_player_id=viewer_player_id,
        )

    def events_since(self, cursor: EventStreamCursor) -> EventStreamDeltaPayload:
        if type(cursor) is not EventStreamCursor:
            raise GameLifecycleError("LocalGameSession events_since requires EventStreamCursor.")
        return cursor.events_since(self.lifecycle.decision_controller.event_log)
