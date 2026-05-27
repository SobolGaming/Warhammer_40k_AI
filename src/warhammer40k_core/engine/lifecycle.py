from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    PhaseHandler,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow


class GameLifecyclePayload(TypedDict):
    config: GameConfigPayload | None
    state: GameStatePayload
    decisions: DecisionControllerPayload


def _new_decision_controller() -> DecisionController:
    return DecisionController()


@dataclass(slots=True)
class GameLifecycle:
    decision_controller: DecisionController = field(default_factory=_new_decision_controller)
    state: GameState | None = None
    _config: GameConfig | None = None
    _setup_flow: SetupFlow = field(default_factory=SetupFlow)
    _command_phase_handler: CommandPhaseHandler = field(default_factory=CommandPhaseHandler)
    _battle_round_flow: BattleRoundFlow | None = None

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("GameLifecycle config must be a GameConfig.")
        if self.state is not None:
            raise GameLifecycleError("GameLifecycle has already started.")
        self._config = config
        self.state = GameState.from_config(config)
        self._battle_round_flow = BattleRoundFlow(phase_handlers=self._phase_handlers())
        current_setup_step = self.state.current_setup_step
        if current_setup_step is None:
            raise GameLifecycleError("GameLifecycle start requires an initial setup step.")
        self.decision_controller.event_log.append(
            "lifecycle_started",
            {
                "game_id": self.state.game_id,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
                "setup_sequence": [step.value for step in self.state.setup_sequence],
                "battle_phase_sequence": [
                    phase.value for phase in self.state.battle_phase_sequence
                ],
            },
        )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.SETUP,
            payload={
                "game_id": self.state.game_id,
                "current_setup_step": current_setup_step.value,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
            },
        )

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        if pending_request is not None:
            return LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=pending_request,
                payload={
                    "game_id": state.game_id,
                    "pending_request_id": pending_request.request_id,
                },
            )
        if state.stage is GameLifecycleStage.COMPLETE:
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game lifecycle is complete.",
                payload={"game_id": state.game_id},
            )
        if state.stage is GameLifecycleStage.SETUP:
            return self._setup_flow.advance(
                state=state,
                decisions=self.decision_controller,
                config=self._require_config(),
            )
        return self._require_battle_round_flow().advance(
            state=state,
            decisions=self.decision_controller,
        )

    def submit_decision(self, result: DecisionResult) -> LifecycleStatus:
        state = self._require_state()
        record = self.decision_controller.submit_result(result)
        if record.request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            self._setup_flow.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE:
            self._command_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")

    def to_payload(self) -> GameLifecyclePayload:
        state = self._require_state()
        return {
            "config": None if self._config is None else self._config.to_payload(),
            "state": state.to_payload(),
            "decisions": self.decision_controller.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: GameLifecyclePayload) -> Self:
        config_payload = payload["config"]
        lifecycle = cls(
            decision_controller=DecisionController.from_payload(payload["decisions"]),
            state=GameState.from_payload(payload["state"]),
            _config=None if config_payload is None else GameConfig.from_payload(config_payload),
        )
        lifecycle._battle_round_flow = BattleRoundFlow(phase_handlers=lifecycle._phase_handlers())
        return lifecycle

    def _phase_handlers(self) -> Mapping[BattlePhase, PhaseHandler]:
        return {BattlePhase.COMMAND: self._command_phase_handler}

    def _pending_decision_request(self) -> DecisionRequest | None:
        pending_requests = self.decision_controller.queue.pending_requests
        if not pending_requests:
            return None
        return pending_requests[0]

    def _require_state(self) -> GameState:
        if self.state is None:
            raise GameLifecycleError("GameLifecycle has not started.")
        return self.state

    def _require_config(self) -> GameConfig:
        if self._config is None:
            raise GameLifecycleError("GameLifecycle config is unavailable.")
        return self._config

    def _require_battle_round_flow(self) -> BattleRoundFlow:
        if self._battle_round_flow is None:
            raise GameLifecycleError("GameLifecycle battle round flow is unavailable.")
        return self._battle_round_flow
