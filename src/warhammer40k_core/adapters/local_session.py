from __future__ import annotations

from dataclasses import dataclass, field

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.decisions import submit_option, submit_parameterized_payload
from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.projection import (
    GameViewPayload,
    RulesCatalogViewPayload,
    project_game_view,
    project_rules_catalog_view,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


def _new_parameterized_lifecycle() -> GameLifecycle:
    return GameLifecycle(parameterized_movement_proposals=True)


@dataclass(slots=True)
class LocalGameSession(AdapterGameSession):
    lifecycle: GameLifecycle = field(default_factory=_new_parameterized_lifecycle)

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("LocalGameSession config must be a GameConfig.")
        return self.lifecycle.start(config)

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        return self.lifecycle.advance_until_decision_or_terminal()

    def submit_option(self, *, request_id: str, option_id: str, result_id: str) -> LifecycleStatus:
        return submit_option(
            lifecycle=self.lifecycle,
            request_id=request_id,
            option_id=option_id,
            result_id=result_id,
        )

    def submit_parameterized_payload(
        self,
        *,
        request_id: str,
        payload: JsonValue,
        result_id: str,
    ) -> LifecycleStatus:
        return submit_parameterized_payload(
            lifecycle=self.lifecycle,
            request_id=request_id,
            payload=payload,
            result_id=result_id,
        )

    def view(self, *, viewer_player_id: str) -> GameViewPayload:
        return project_game_view(
            lifecycle=self.lifecycle,
            viewer_player_id=viewer_player_id,
        )

    def rules_catalog_view(self) -> RulesCatalogViewPayload:
        return project_rules_catalog_view(catalog=self.lifecycle.config.army_catalog)

    def events_since(
        self,
        cursor: EventStreamCursor,
        *,
        viewer_player_id: str,
    ) -> EventStreamDeltaPayload:
        if type(cursor) is not EventStreamCursor:
            raise GameLifecycleError("LocalGameSession events_since requires EventStreamCursor.")
        viewer = _validate_viewer_player_id(
            lifecycle=self.lifecycle,
            viewer_player_id=viewer_player_id,
        )
        return cursor.events_since(
            self.lifecycle.decision_controller.event_log,
            viewer_player_id=viewer,
        )


def _validate_viewer_player_id(
    *,
    lifecycle: GameLifecycle,
    viewer_player_id: object,
) -> str:
    state = lifecycle.state
    if state is None:
        raise GameLifecycleError("LocalGameSession event stream requires a started lifecycle.")
    if type(viewer_player_id) is not str:
        raise GameLifecycleError("viewer_player_id must be a string.")
    viewer = viewer_player_id.strip()
    if not viewer:
        raise GameLifecycleError("viewer_player_id must not be empty.")
    if viewer not in state.player_ids:
        raise GameLifecycleError("viewer_player_id must be a player in this game.")
    return viewer
