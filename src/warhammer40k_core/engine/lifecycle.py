from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.mission_decisions import (
    MISSION_DECISION_TYPES,
    START_MISSION_ACTION_DECISION_TYPE,
    apply_mission_decision,
    invalid_mission_decision_status,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
    SetupStep,
    UnsupportedPhaseHandler,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    PLACE_DISEMBARK_UNIT_DECISION_TYPE,
    PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_DISEMBARK_UNIT_DECISION_TYPE,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    MovementPhaseHandler,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueuePayload,
)
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingDecision,
    apply_sequencing_decision_from_request,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    STRATAGEM_WINDOW_DECLINED_EVENT_TYPE,
    apply_grenade_mortal_wound_feel_no_pain_decision,
    apply_stratagem_decision,
    apply_stratagem_placement_proposal,
    apply_stratagem_target_proposal,
    invalid_stratagem_placement_proposal_status,
    invalid_stratagem_target_proposal_status,
    invalid_stratagem_use_status,
    is_stratagem_placement_proposal_request,
    is_stratagem_window_decline_result,
    stratagem_window_decline_allowed,
    stratagem_window_decline_event_payload,
)
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TriggeredMovementHandler,
)
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency


class GameLifecyclePayload(TypedDict):
    config: GameConfigPayload | None
    parameterized_movement_proposals: bool
    state: GameStatePayload
    decisions: DecisionControllerPayload
    reaction_queue: ReactionQueuePayload


MAX_LIFECYCLE_TRANSITIONS = 128
_MOVEMENT_PROPOSAL_DECISION_TYPES = frozenset(
    (
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
    )
)
_MOVEMENT_DECISION_TYPES = frozenset(
    (
        SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
        PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
        SELECT_DISEMBARK_UNIT_DECISION_TYPE,
        PLACE_DISEMBARK_UNIT_DECISION_TYPE,
        SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
    )
)
_TRIGGERED_MOVEMENT_DECISION_TYPES = frozenset((SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,))
_SHOOTING_DECISION_TYPES = frozenset(
    (
        SELECT_SHOOTING_UNIT_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
)
_REACTION_FRAME_DECISION_TYPES = frozenset(
    (
        REACTION_DECISION_TYPE,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        PLACEMENT_PROPOSAL_DECISION_TYPE,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
)


def _new_decision_controller() -> DecisionController:
    return DecisionController()


@dataclass(slots=True)
class GameLifecycle:
    decision_controller: DecisionController = field(default_factory=_new_decision_controller)
    reaction_queue: ReactionQueue = field(default_factory=ReactionQueue)
    state: GameState | None = None
    parameterized_movement_proposals: bool = False
    _config: GameConfig | None = None
    _setup_flow: SetupFlow = field(default_factory=SetupFlow)
    _command_phase_handler: CommandPhaseHandler = field(default_factory=CommandPhaseHandler)
    _movement_phase_handler: MovementPhaseHandler = field(default_factory=MovementPhaseHandler)
    _shooting_phase_handler: ShootingPhaseHandler = field(default_factory=ShootingPhaseHandler)
    _triggered_movement_handler: TriggeredMovementHandler = field(
        default_factory=TriggeredMovementHandler
    )
    _battle_round_flow: BattleRoundFlow | None = None

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("GameLifecycle config must be a GameConfig.")
        if self.state is not None:
            raise GameLifecycleError("GameLifecycle has already started.")
        self._config = config
        self._movement_phase_handler = MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            parameterized_proposals=self.parameterized_movement_proposals,
        )
        self._shooting_phase_handler = ShootingPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        self._triggered_movement_handler = TriggeredMovementHandler(
            ruleset_descriptor=config.ruleset_descriptor
        )
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
        for _transition_index in range(MAX_LIFECYCLE_TRANSITIONS):
            status = self._advance_once()
            if status.status_kind in (
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            ):
                return status
        raise GameLifecycleError("GameLifecycle exceeded deterministic transition guard.")

    def _advance_once(self) -> LifecycleStatus:
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
        out_of_phase_status = self._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
            state=state,
            decisions=self.decision_controller,
        )
        if out_of_phase_status is not None:
            return out_of_phase_status
        if state.stage is GameLifecycleStage.COMPLETE:
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game lifecycle is complete.",
                payload=state.game_result_payload(),
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
            reaction_queue=self.reaction_queue,
        )

    def submit_decision(self, result: DecisionResult) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        sequencing_decision: SequencingDecision | None = None
        stratagem_placement_request: DecisionRequest | None = None
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and is_stratagem_placement_proposal_request(pending_request)
        ):
            stratagem_placement_request = pending_request
        if stratagem_placement_request is not None:
            result.validate_for_request(stratagem_placement_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = invalid_stratagem_placement_proposal_status(
                state=state,
                request=stratagem_placement_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type in _MOVEMENT_PROPOSAL_DECISION_TYPES
            and stratagem_placement_request is None
        ):
            result.validate_for_request(pending_request)
            malformed_status = self._movement_phase_handler.invalid_proposal_submission_status(
                state=state,
                request=pending_request,
                result=result,
                decisions=self.decision_controller,
            )
            if malformed_status is not None:
                return malformed_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            invalid_status = self._shooting_phase_handler.invalid_declaration_submission_status(
                state=state,
                request=pending_request,
                result=result,
                decisions=self.decision_controller,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            and is_mortal_wound_feel_no_pain_request(pending_request)
        ):
            invalid_status = _invalid_finite_decision_status(
                state=state,
                request=pending_request,
                result=result,
                invalid_reason="invalid_mortal_wound_feel_no_pain_result",
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        ):
            invalid_status = _invalid_destruction_reaction_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type in MISSION_DECISION_TYPES
        ):
            result.validate_for_request(pending_request)
            invalid_status = invalid_mission_decision_status(
                state=state,
                request=pending_request,
                result=result,
            )
            if invalid_status is not None:
                return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == REACTION_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            self.reaction_queue.validate_result(result)
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == STRATAGEM_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            if is_stratagem_window_decline_result(result) and not stratagem_window_decline_allowed(
                request=pending_request,
                result=result,
            ):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Stratagem window decline is not allowed for this request.",
                    payload={"invalid_reason": "decline_not_allowed"},
                )
            if not is_stratagem_window_decline_result(result):
                invalid_status = invalid_stratagem_use_status(
                    state=state,
                    request=pending_request,
                    result=result,
                )
                if invalid_status is not None:
                    return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.validate_result(result)
            if is_stratagem_window_decline_result(result) and not stratagem_window_decline_allowed(
                request=pending_request,
                result=result,
            ):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Stratagem window decline is not allowed for this request.",
                    payload={"invalid_reason": "decline_not_allowed"},
                )
            if not is_stratagem_window_decline_result(result):
                invalid_status = invalid_stratagem_target_proposal_status(
                    state=state,
                    request=pending_request,
                    result=result,
                    ruleset_descriptor=self._require_config().ruleset_descriptor,
                    army_catalog=self._require_config().army_catalog,
                )
                if invalid_status is not None:
                    return invalid_status
        if (
            type(result) is DecisionResult
            and pending_request is not None
            and pending_request.decision_type == SEQUENCING_DECISION_TYPE
        ):
            result.validate_for_request(pending_request)
            sequencing_decision = apply_sequencing_decision_from_request(
                request=pending_request,
                result=result,
            )
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
        if record.request.decision_type in MISSION_DECISION_TYPES:
            apply_mission_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if record.request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
                return LifecycleStatus.advanced(
                    stage=state.stage,
                    payload={
                        "decision_type": START_MISSION_ACTION_DECISION_TYPE,
                        "result_id": result.result_id,
                    },
                )
            return self.advance_until_decision_or_terminal()
        if is_stratagem_placement_proposal_request(record.request):
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            placement_status = apply_stratagem_placement_proposal(
                state=state,
                request=record.request,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
            )
            if placement_status is not None:
                if resolves_reaction_frame:
                    retry_request = self._pending_decision_request()
                    if retry_request is not None and is_stratagem_placement_proposal_request(
                        retry_request
                    ):
                        self.reaction_queue.continue_reaction(
                            result=result,
                            next_request_id=retry_request.request_id,
                            decisions=self.decision_controller,
                        )
                return placement_status
            if resolves_reaction_frame:
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _MOVEMENT_DECISION_TYPES:
            movement_status = self._movement_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                reaction_queue=self.reaction_queue,
            )
            if movement_status is not None:
                return movement_status
            return self.advance_until_decision_or_terminal()
        if (
            record.request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            and is_mortal_wound_feel_no_pain_request(record.request)
        ):
            source_context = mortal_wound_feel_no_pain_source_context(record.request)
            if isinstance(source_context, dict) and source_context.get("source_kind") == "grenade":
                grenade_status = apply_grenade_mortal_wound_feel_no_pain_decision(
                    state=state,
                    result=result,
                    decisions=self.decision_controller,
                )
                if grenade_status is not None:
                    return grenade_status
                return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _SHOOTING_DECISION_TYPES:
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            shooting_status = self._shooting_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if resolves_reaction_frame:
                handled_status = self._continue_or_resolve_out_of_phase_reaction(
                    result=result,
                    status=shooting_status,
                )
                if handled_status is not None:
                    return handled_status
            if shooting_status is not None:
                return shooting_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _TRIGGERED_MOVEMENT_DECISION_TYPES:
            triggered_status = self._triggered_movement_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if triggered_status is not None:
                return triggered_status
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == REACTION_DECISION_TYPE:
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == STRATAGEM_DECISION_TYPE:
            if is_stratagem_window_decline_result(result):
                self._record_stratagem_window_declined(result)
                if self._result_resolves_active_reaction_frame(result):
                    self.reaction_queue.resolve_reaction(
                        result=result,
                        decisions=self.decision_controller,
                    )
                return self.advance_until_decision_or_terminal()
            apply_stratagem_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
            )
            if self._result_resolves_active_reaction_frame(result):
                self.reaction_queue.resolve_reaction(
                    result=result,
                    decisions=self.decision_controller,
                )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
            resolves_reaction_frame = self._result_resolves_active_reaction_frame(result)
            if is_stratagem_window_decline_result(result):
                self._record_stratagem_window_declined(result)
                if resolves_reaction_frame:
                    self.reaction_queue.resolve_reaction(
                        result=result,
                        decisions=self.decision_controller,
                    )
                return self.advance_until_decision_or_terminal()
            apply_stratagem_target_proposal(
                state=state,
                result=result,
                decisions=self.decision_controller,
                ruleset_descriptor=self._require_config().ruleset_descriptor,
                army_catalog=self._require_config().army_catalog,
            )
            if resolves_reaction_frame:
                follow_up_request = self._pending_decision_request()
                if follow_up_request is not None:
                    self.reaction_queue.continue_reaction(
                        result=result,
                        next_request_id=follow_up_request.request_id,
                        decisions=self.decision_controller,
                    )
                else:
                    self.reaction_queue.resolve_reaction(
                        result=result,
                        decisions=self.decision_controller,
                    )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == SEQUENCING_DECISION_TYPE:
            if sequencing_decision is None:
                sequencing_decision = apply_sequencing_decision_from_request(
                    request=record.request,
                    result=result,
                )
            self.decision_controller.event_log.append(
                "sequencing_order_resolved",
                sequencing_decision.to_payload(),
            )
            return self.advance_until_decision_or_terminal()
        raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")

    def to_payload(self) -> GameLifecyclePayload:
        state = self._require_state()
        return {
            "config": None if self._config is None else self._config.to_payload(),
            "parameterized_movement_proposals": self.parameterized_movement_proposals,
            "state": state.to_payload(),
            "decisions": self.decision_controller.to_payload(),
            "reaction_queue": self.reaction_queue.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: GameLifecyclePayload) -> Self:
        config_payload = payload["config"]
        config = None if config_payload is None else GameConfig.from_payload(config_payload)
        parameterized_movement_proposals = _payload_bool(
            "GameLifecycle parameterized_movement_proposals",
            payload["parameterized_movement_proposals"],
        )
        lifecycle = cls(
            decision_controller=DecisionController.from_payload(payload["decisions"]),
            reaction_queue=ReactionQueue.from_payload(payload["reaction_queue"]),
            state=GameState.from_payload(payload["state"]),
            parameterized_movement_proposals=parameterized_movement_proposals,
            _config=config,
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
                parameterized_proposals=parameterized_movement_proposals,
            ),
            _shooting_phase_handler=ShootingPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor,
                army_catalog=None if config is None else config.army_catalog,
            ),
            _triggered_movement_handler=TriggeredMovementHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor
            ),
        )
        _validate_payload_consistency(state=lifecycle._require_state(), config=lifecycle._config)
        _validate_reaction_queue_consistency(
            state=lifecycle._require_state(),
            reaction_queue=lifecycle.reaction_queue,
            pending_request=lifecycle._pending_decision_request(),
        )
        lifecycle._battle_round_flow = BattleRoundFlow(phase_handlers=lifecycle._phase_handlers())
        return lifecycle

    def _phase_handlers(self) -> Mapping[BattlePhase, PhaseHandler]:
        return {
            BattlePhase.COMMAND: self._command_phase_handler,
            BattlePhase.MOVEMENT: self._movement_phase_handler,
            BattlePhase.SHOOTING: self._shooting_phase_handler,
            BattlePhase.CHARGE: UnsupportedPhaseHandler(BattlePhase.CHARGE),
            BattlePhase.FIGHT: UnsupportedPhaseHandler(BattlePhase.FIGHT),
        }

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

    def _result_resolves_active_reaction_frame(self, result: DecisionResult) -> bool:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("Reaction frame check requires a DecisionResult.")
        frames = self.reaction_queue.frames
        return bool(frames and frames[-1].request_id == result.request_id)

    def _record_stratagem_window_declined(self, result: DecisionResult) -> None:
        record = self.decision_controller.record_for_result(result)
        self.decision_controller.event_log.append(
            STRATAGEM_WINDOW_DECLINED_EVENT_TYPE,
            stratagem_window_decline_event_payload(request=record.request, result=result),
        )

    def _continue_or_resolve_out_of_phase_reaction(
        self,
        *,
        result: DecisionResult,
        status: LifecycleStatus | None,
    ) -> LifecycleStatus | None:
        state = self._require_state()
        if status is not None and status.decision_request is not None:
            self.reaction_queue.continue_reaction(
                result=result,
                next_request_id=status.decision_request.request_id,
                decisions=self.decision_controller,
            )
            return status
        if status is None and state.out_of_phase_shooting_state is not None:
            advanced_status = self._shooting_phase_handler.advance_out_of_phase_shooting_if_needed(
                state=state,
                decisions=self.decision_controller,
            )
            if advanced_status is not None and advanced_status.decision_request is not None:
                self.reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=advanced_status.decision_request.request_id,
                    decisions=self.decision_controller,
                )
                return advanced_status
            self.reaction_queue.resolve_reaction(
                result=result,
                decisions=self.decision_controller,
            )
            return advanced_status
        self.reaction_queue.resolve_reaction(
            result=result,
            decisions=self.decision_controller,
        )
        return status


def _payload_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _invalid_destruction_reaction_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_destruction_reaction_result",
    )
    if invalid_status is not None:
        return invalid_status
    request_payload = request.payload
    if not isinstance(request_payload, Mapping):
        raise GameLifecycleError("Destruction reaction request payload must be an object.")
    destruction_context = request_payload.get("destruction_context")
    if not isinstance(destruction_context, Mapping):
        raise GameLifecycleError("Destruction reaction context must be an object.")
    attack_context = destruction_context.get("attack_context")
    if not isinstance(attack_context, Mapping):
        raise GameLifecycleError("Destruction reaction attack context must be an object.")
    attack_sequence = _active_attack_sequence_for_state(state)
    if attack_sequence is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Destruction reaction has no active attack sequence.",
            payload={
                "invalid_reason": "invalid_destruction_reaction_result",
                "field": "attack_sequence",
            },
        )
    expected_fields: tuple[tuple[str, object], ...] = (
        ("sequence_id", attack_sequence.sequence_id),
        ("attack_context_id", attack_sequence.attack_context_id()),
        ("pool_index", attack_sequence.pool_index),
        ("attack_index", attack_sequence.attack_index),
        ("generated_hit_index", attack_sequence.generated_hit_index),
    )
    for field_name, expected_value in expected_fields:
        if attack_context.get(field_name) != expected_value:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Destruction reaction attack context no longer matches state.",
                payload={
                    "invalid_reason": "invalid_destruction_reaction_result",
                    "field": field_name,
                },
            )
    return None


def _active_attack_sequence_for_state(state: GameState) -> AttackSequence | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        return out_of_phase_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and shooting_state.attack_sequence is not None:
        return shooting_state.attack_sequence
    return None


def _validate_payload_consistency(*, state: GameState, config: GameConfig | None) -> None:
    _validate_reserve_state_consistency(state=state)
    _validate_transport_cargo_state_consistency(state=state)
    _validate_battlefield_state_consistency(state=state, config=config)
    _validate_movement_phase_state_consistency(state=state)
    _validate_shooting_phase_state_consistency(state=state)
    _validate_disembarked_unit_state_consistency(state=state)
    _validate_advanced_unit_state_consistency(state=state)
    _validate_fell_back_unit_state_consistency(state=state)
    _validate_surge_move_state_consistency(state=state)
    if config is None:
        return
    if state.game_id != config.game_id:
        raise GameLifecycleError("Lifecycle state game_id does not match config.")
    if state.player_ids != config.player_ids:
        raise GameLifecycleError("Lifecycle state player_ids do not match config.")
    if state.turn_order != config.turn_order:
        raise GameLifecycleError("Lifecycle state turn_order does not match config.")
    if state.tactical_secondary_draw_count != config.tactical_secondary_draw_count:
        raise GameLifecycleError(
            "Lifecycle state tactical secondary draw count does not match config."
        )
    expected_hash = config.ruleset_descriptor.descriptor_hash
    if state.ruleset_descriptor_hash != expected_hash:
        raise GameLifecycleError("Lifecycle state ruleset hash does not match config.")
    expected_setup = tuple(config.ruleset_descriptor.setup_sequence.steps)
    if state.setup_sequence != expected_setup:
        raise GameLifecycleError("Lifecycle state setup sequence does not match config.")
    expected_battle = tuple(config.ruleset_descriptor.battle_phase_sequence.phases)
    if state.battle_phase_sequence != expected_battle:
        raise GameLifecycleError("Lifecycle state battle phase sequence does not match config.")
    _validate_mustered_army_consistency(state=state, config=config)


def _validate_mustered_army_consistency(*, state: GameState, config: GameConfig) -> None:
    if not state.army_definitions and not _state_requires_mustered_armies(state):
        return
    try:
        expected_armies = tuple(
            sorted(
                (
                    muster_army(catalog=config.army_catalog, request=request)
                    for request in config.army_muster_requests
                ),
                key=lambda army: army.player_id,
            )
        )
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Lifecycle config army muster requests are invalid.") from exc
    expected_payloads = [army.to_payload() for army in expected_armies]
    state_payloads = [army.to_payload() for army in state.army_definitions]
    if _state_requires_mustered_armies(state) and not state_payloads:
        raise GameLifecycleError("Lifecycle state is missing mustered army definitions.")
    if state_payloads and state_payloads != expected_payloads:
        raise GameLifecycleError("Lifecycle state army definitions do not match config.")


def _validate_reaction_queue_consistency(
    *,
    state: GameState,
    reaction_queue: ReactionQueue,
    pending_request: DecisionRequest | None,
) -> None:
    frames = reaction_queue.frames
    if not frames:
        if pending_request is not None and pending_request.decision_type == REACTION_DECISION_TYPE:
            raise GameLifecycleError("Lifecycle pending reaction decision requires a frame.")
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Lifecycle reaction queue requires battle stage.")
    if state.current_battle_phase is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a current battle phase.")
    if pending_request is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a pending decision.")
    if pending_request.decision_type not in _REACTION_FRAME_DECISION_TYPES:
        raise GameLifecycleError("Lifecycle reaction queue pending decision_type drift.")
    if (
        pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and not is_stratagem_placement_proposal_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending placement decision drift.")
    seen_request_ids: set[str] = set()
    for frame in frames:
        if frame.request_id is None:
            raise GameLifecycleError("Lifecycle reaction queue frame requires request_id.")
        if frame.request_id in seen_request_ids:
            raise GameLifecycleError("Lifecycle reaction queue request_ids must be unique.")
        seen_request_ids.add(frame.request_id)
        if frame.reaction_window.timing_window.game_id != state.game_id:
            raise GameLifecycleError("Lifecycle reaction queue frame game_id drift.")
        if frame.parent_phase is not state.current_battle_phase:
            raise GameLifecycleError("Lifecycle reaction queue frame phase drift.")
    if frames[-1].request_id != pending_request.request_id:
        raise GameLifecycleError("Lifecycle reaction queue active frame request_id drift.")


def _validate_battlefield_state_consistency(
    *,
    state: GameState,
    config: GameConfig | None,
) -> None:
    if state.battlefield_state is None:
        if _state_requires_battlefield_state(state):
            raise GameLifecycleError("Lifecycle state is missing battlefield_state.")
        return
    if not _state_allows_battlefield_state(state):
        raise GameLifecycleError(
            "Lifecycle state battlefield_state must be absent before DEPLOY_ARMIES."
        )
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        if _state_requires_battlefield_state(state):
            scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
        if config is not None:
            assert_battlefield_units_in_coherency(
                scenario=scenario,
                ruleset_descriptor=config.ruleset_descriptor,
            )
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state battlefield_state is invalid.") from exc


def _validate_reserve_state_consistency(*, state: GameState) -> None:
    if not state.reserve_states:
        return
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    for reserve_state in state.reserve_states:
        owner = unit_owner_by_id.get(reserve_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("reserve_states unit is unknown.")
        if owner != reserve_state.player_id:
            raise GameLifecycleError("reserve_states player_id does not match unit owner.")
        for embarked_unit_id in reserve_state.embarked_unit_instance_ids:
            embarked_owner = unit_owner_by_id.get(embarked_unit_id)
            if embarked_owner is None:
                raise GameLifecycleError("reserve_states embarked unit is unknown.")
            if embarked_owner != reserve_state.player_id:
                raise GameLifecycleError("reserve_states embarked unit owner drift.")

    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for reserve_state in state.reserve_states:
        reserve_model_ids = set(model_ids_by_unit_id[reserve_state.unit_instance_id])
        embarked_model_ids = {
            model_id
            for embarked_unit_id in reserve_state.embarked_unit_instance_ids
            for model_id in model_ids_by_unit_id[embarked_unit_id]
        }
        if reserve_state.status is ReserveStatus.IN_RESERVES:
            if (reserve_model_ids | embarked_model_ids) & placed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be placed.")
            if (reserve_model_ids | embarked_model_ids) & removed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be removed.")
        if reserve_state.status is ReserveStatus.ARRIVED:
            if not reserve_model_ids <= placed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must be placed.")
            if reserve_model_ids & removed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must not be removed.")
        if (
            reserve_state.status is ReserveStatus.DESTROYED
            and not (reserve_model_ids | embarked_model_ids) <= removed_model_ids
        ):
            raise GameLifecycleError("destroyed reserve models must be removed.")


def _validate_transport_cargo_state_consistency(*, state: GameState) -> None:
    if not state.transport_cargo_states:
        return
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    embarked_unit_ids: set[str] = set()
    for cargo_state in state.transport_cargo_states:
        transport = unit_by_id.get(cargo_state.transport_unit_instance_id)
        if transport is None:
            raise GameLifecycleError("transport_cargo_states transport unit is unknown.")
        if owner_by_unit_id[cargo_state.transport_unit_instance_id] != cargo_state.player_id:
            raise GameLifecycleError("transport_cargo_states player_id does not match owner.")
        if transport.datasheet_id != cargo_state.capacity_profile.transport_datasheet_id:
            raise GameLifecycleError("transport_cargo_states transport datasheet drift.")
        cargo_model_count = 0
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            embarked_unit = unit_by_id.get(embarked_unit_id)
            if embarked_unit is None:
                raise GameLifecycleError("transport_cargo_states embarked unit is unknown.")
            if owner_by_unit_id[embarked_unit_id] != cargo_state.player_id:
                raise GameLifecycleError("transport_cargo_states embarked unit owner drift.")
            if embarked_unit_id in embarked_unit_ids:
                raise GameLifecycleError("unit cannot be embarked in more than one Transport.")
            embarked_unit_ids.add(embarked_unit_id)
            if not cargo_state.capacity_profile.allows_unit(embarked_unit):
                raise GameLifecycleError("transport_cargo_states capacity profile rejects cargo.")
            cargo_model_count += len(embarked_unit.own_models)
        if cargo_model_count > cargo_state.capacity_profile.max_model_count:
            raise GameLifecycleError("transport_cargo_states capacity is exceeded.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_unit_ids = {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for cargo_state in state.transport_cargo_states:
        if cargo_state.transport_unit_instance_id not in placed_unit_ids:
            raise GameLifecycleError("transport_cargo_states transport unit must be placed.")
        transport_model_ids = set(model_ids_by_unit_id[cargo_state.transport_unit_instance_id])
        if transport_model_ids & removed_model_ids:
            raise GameLifecycleError("transport_cargo_states transport models must not be removed.")
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            model_ids = set(model_ids_by_unit_id[embarked_unit_id])
            if model_ids & placed_model_ids:
                raise GameLifecycleError("embarked unit models must not be placed.")
            if model_ids & removed_model_ids:
                raise GameLifecycleError("embarked unit models must not be removed.")


def _validate_movement_phase_state_consistency(*, state: GameState) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("movement_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("movement_phase_state requires MOVEMENT phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("movement_phase_state requires active player.")
    if movement_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("movement_phase_state active player drift.")
    if movement_state.battle_round != state.battle_round:
        raise GameLifecycleError("movement_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("movement_phase_state requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state movement_phase_state is invalid.") from exc

    try:
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
        active_player_unit_ids: set[str] = {
            placement.unit_instance_id for placement in placed_army.unit_placements
        }
    except PlacementError:
        active_player_unit_ids = set()
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_reserve_unit_ids = _unarrived_reserve_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for unit_id in (*movement_state.selected_unit_ids, *movement_state.moved_unit_ids):
        if (
            unit_id not in active_player_unit_ids
            and unit_id not in fully_removed_active_player_unit_ids
            and unit_id not in active_player_embarked_unit_ids
            and unit_id not in active_player_reserve_unit_ids
        ):
            raise GameLifecycleError(
                "movement_phase_state selected unit is not active player's unit."
            )
    if movement_state.active_selection is None:
        return
    active_unit_id = movement_state.active_selection.unit_instance_id
    if active_unit_id not in movement_state.selected_unit_ids:
        raise GameLifecycleError("movement_phase_state active selection drift.")
    if active_unit_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "movement_phase_state active selection is not active player's unit."
        )


def _validate_shooting_phase_state_consistency(*, state: GameState) -> None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("shooting_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("shooting_phase_state requires SHOOTING phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("shooting_phase_state requires active player.")
    if shooting_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("shooting_phase_state active player drift.")
    if shooting_state.battle_round != state.battle_round:
        raise GameLifecycleError("shooting_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("shooting_phase_state requires battlefield_state.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_unit_ids = {
        unit_id
        for unit_id, player_id in unit_owner_by_id.items()
        if player_id == state.active_player_id
    }
    for unit_id in (
        *shooting_state.selected_unit_ids,
        *shooting_state.shot_unit_ids,
        *shooting_state.skipped_unit_ids,
    ):
        if unit_id not in active_player_unit_ids and unit_id not in active_player_embarked_unit_ids:
            raise GameLifecycleError(
                "shooting_phase_state selected unit is not active player's unit."
            )
    active_selection = shooting_state.active_selection
    if active_selection is None:
        return
    if active_selection.unit_instance_id not in shooting_state.selected_unit_ids:
        raise GameLifecycleError("shooting_phase_state active selection drift.")
    if active_selection.unit_instance_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "shooting_phase_state active selection is not active player's unit."
        )


def _validate_advanced_unit_state_consistency(*, state: GameState) -> None:
    if not state.advanced_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("advanced_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("advanced_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("advanced_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state advanced_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for advanced_state in state.advanced_unit_states:
        if advanced_state.player_id != state.active_player_id:
            raise GameLifecycleError("advanced_unit_states player drift.")
        if advanced_state.battle_round != state.battle_round:
            raise GameLifecycleError("advanced_unit_states battle round drift.")
        if (
            advanced_state.unit_instance_id not in active_player_unit_ids
            and advanced_state.unit_instance_id not in active_player_embarked_unit_ids
            and advanced_state.unit_instance_id not in fully_removed_active_player_unit_ids
        ):
            raise GameLifecycleError("advanced_unit_states unit is not active player's unit.")


def _validate_disembarked_unit_state_consistency(*, state: GameState) -> None:
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for disembarked_state in state.disembarked_unit_states:
        owner = unit_owner_by_id.get(disembarked_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("disembarked_unit_states unit is unknown.")
        if owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_owner = unit_owner_by_id.get(disembarked_state.transport_unit_instance_id)
        if transport_owner is None:
            raise GameLifecycleError("disembarked_unit_states transport unit is unknown.")
        if transport_owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")


def _validate_fell_back_unit_state_consistency(*, state: GameState) -> None:
    if not state.fell_back_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("fell_back_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("fell_back_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("fell_back_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state fell_back_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for fell_back_state in state.fell_back_unit_states:
        if fell_back_state.player_id != state.active_player_id:
            raise GameLifecycleError("fell_back_unit_states player drift.")
        if fell_back_state.battle_round != state.battle_round:
            raise GameLifecycleError("fell_back_unit_states battle round drift.")
        if (
            fell_back_state.unit_instance_id not in active_player_unit_ids
            and fell_back_state.unit_instance_id not in active_player_embarked_unit_ids
            and fell_back_state.unit_instance_id not in fully_removed_active_player_unit_ids
        ):
            raise GameLifecycleError("fell_back_unit_states unit is not active player's unit.")


def _validate_surge_move_state_consistency(*, state: GameState) -> None:
    if not state.surge_move_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("surge_move_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for surge_state in state.surge_move_states:
        owner = unit_owner_by_id.get(surge_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("surge_move_states unit is unknown.")
        if owner != surge_state.player_id:
            raise GameLifecycleError("surge_move_states player_id does not match unit owner.")


def _embarked_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        unit_id
        for cargo_state in state.transport_cargo_states
        if cargo_state.player_id == player_id
        for unit_id in cargo_state.embarked_unit_instance_ids
    }


def _unarrived_reserve_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        reserve_state.unit_instance_id
        for reserve_state in state.unarrived_reserve_states_for_player(player_id)
    }


def _fully_removed_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    if state.battlefield_state is None:
        raise GameLifecycleError("removed unit accounting requires battlefield_state.")
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    fully_removed_unit_ids: set[str] = set()
    for army_definition in state.army_definitions:
        if army_definition.player_id != player_id:
            continue
        for unit in army_definition.units:
            unit_model_ids = {model.model_instance_id for model in unit.own_models}
            if unit_model_ids and unit_model_ids <= removed_model_ids:
                fully_removed_unit_ids.add(unit.unit_instance_id)
    return fully_removed_unit_ids


def _state_requires_mustered_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        muster_step_index = state.setup_sequence.index(SetupStep.MUSTER_ARMIES)
    except ValueError as exc:
        raise GameLifecycleError(
            "Lifecycle state setup sequence must include MUSTER_ARMIES."
        ) from exc
    return state.setup_step_index > muster_step_index


def _state_requires_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index > deploy_step_index


def _state_allows_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index > deploy_step_index
