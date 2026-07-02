from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Self, TypedDict

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecordPayload
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import ReactionWindow, ReactionWindowPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


REACTION_DECISION_TYPE = "resolve_reaction_window"


class ReactionQueuePayload(TypedDict):
    frames: list[ReactionQueueFramePayload]


class ReactionQueueFramePayload(TypedDict):
    reaction_window: ReactionWindowPayload
    parent_phase: str
    parent_step: str
    resume_token: str
    request_id: str | None


class TriggeredDecisionRequestPayload(TypedDict):
    reaction_window: ReactionWindowPayload
    decision_request: DecisionRequestPayload


class ReactionResumePayload(TypedDict):
    reaction_window: ReactionWindowPayload
    parent_phase: str
    parent_step: str
    resume_token: str
    decision_record: DecisionRecordPayload


def _new_frames() -> list[ReactionQueueFrame]:
    return []


@dataclass(frozen=True, slots=True)
class ReactionQueueFrame:
    reaction_window: ReactionWindow
    parent_phase: BattlePhaseKind
    parent_step: str
    resume_token: str
    request_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.reaction_window) is not ReactionWindow:
            raise GameLifecycleError("ReactionQueueFrame requires a ReactionWindow.")
        object.__setattr__(
            self,
            "parent_phase",
            battle_phase_kind_from_token(self.parent_phase),
        )
        object.__setattr__(
            self,
            "parent_step",
            _validate_identifier("ReactionQueueFrame parent_step", self.parent_step),
        )
        object.__setattr__(
            self,
            "resume_token",
            _validate_identifier("ReactionQueueFrame resume_token", self.resume_token),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_optional_identifier("ReactionQueueFrame request_id", self.request_id),
        )
        window_phase = self.reaction_window.timing_window.phase
        if window_phase is not None and window_phase is not self.parent_phase:
            raise GameLifecycleError("ReactionQueueFrame parent phase must match reaction window.")

    def with_request_id(self, request_id: str) -> Self:
        return replace(self, request_id=_validate_identifier("request_id", request_id))

    def to_payload(self) -> ReactionQueueFramePayload:
        return {
            "reaction_window": self.reaction_window.to_payload(),
            "parent_phase": self.parent_phase.value,
            "parent_step": self.parent_step,
            "resume_token": self.resume_token,
            "request_id": self.request_id,
        }

    @classmethod
    def from_payload(cls, payload: ReactionQueueFramePayload) -> Self:
        return cls(
            reaction_window=ReactionWindow.from_payload(payload["reaction_window"]),
            parent_phase=battle_phase_kind_from_token(payload["parent_phase"]),
            parent_step=payload["parent_step"],
            resume_token=payload["resume_token"],
            request_id=payload["request_id"],
        )


@dataclass(frozen=True, slots=True)
class TriggeredDecisionRequest:
    reaction_window: ReactionWindow
    decision_request: DecisionRequest

    def __post_init__(self) -> None:
        if type(self.reaction_window) is not ReactionWindow:
            raise GameLifecycleError("TriggeredDecisionRequest requires a ReactionWindow.")
        if type(self.decision_request) is not DecisionRequest:
            raise GameLifecycleError("TriggeredDecisionRequest requires a DecisionRequest.")

    def to_payload(self) -> TriggeredDecisionRequestPayload:
        return {
            "reaction_window": self.reaction_window.to_payload(),
            "decision_request": self.decision_request.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: TriggeredDecisionRequestPayload) -> Self:
        return cls(
            reaction_window=ReactionWindow.from_payload(payload["reaction_window"]),
            decision_request=DecisionRequest.from_payload(payload["decision_request"]),
        )


@dataclass(frozen=True, slots=True)
class ReactionResume:
    reaction_window: ReactionWindow
    parent_phase: BattlePhaseKind
    parent_step: str
    resume_token: str
    decision_record: DecisionRecordPayload

    def __post_init__(self) -> None:
        if type(self.reaction_window) is not ReactionWindow:
            raise GameLifecycleError("ReactionResume requires a ReactionWindow.")
        object.__setattr__(
            self,
            "parent_phase",
            battle_phase_kind_from_token(self.parent_phase),
        )
        object.__setattr__(
            self,
            "parent_step",
            _validate_identifier("ReactionResume parent_step", self.parent_step),
        )
        object.__setattr__(
            self,
            "resume_token",
            _validate_identifier("ReactionResume resume_token", self.resume_token),
        )
        object.__setattr__(
            self,
            "decision_record",
            validate_json_value(self.decision_record),
        )

    def to_payload(self) -> ReactionResumePayload:
        return {
            "reaction_window": self.reaction_window.to_payload(),
            "parent_phase": self.parent_phase.value,
            "parent_step": self.parent_step,
            "resume_token": self.resume_token,
            "decision_record": self.decision_record,
        }


@dataclass(slots=True)
class ReactionQueue:
    _frames: list[ReactionQueueFrame] = field(default_factory=_new_frames)

    @property
    def frames(self) -> tuple[ReactionQueueFrame, ...]:
        return tuple(self._frames)

    @property
    def parent_is_blocked(self) -> bool:
        return any(frame.reaction_window.blocks_parent for frame in self._frames)

    def emit_decision_request(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_window: ReactionWindow,
        parent_phase: BattlePhaseKind,
        parent_step: str,
        resume_token: str,
        actor_id: str,
        decision_type: str = REACTION_DECISION_TYPE,
        options: tuple[DecisionOption, ...],
        payload: JsonValue = None,
        payload_factory: Callable[[str, str, str], JsonValue] | None = None,
    ) -> TriggeredDecisionRequest:
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("ReactionQueue requires a DecisionController.")
        if type(reaction_window) is not ReactionWindow:
            raise GameLifecycleError("ReactionQueue requires a ReactionWindow.")
        if payload is not None and payload_factory is not None:
            raise GameLifecycleError("ReactionQueue payload must not also use a payload factory.")
        parent = battle_phase_kind_from_token(parent_phase)
        current_phase = state.current_battle_phase
        if current_phase is not parent:
            raise GameLifecycleError("ReactionQueue parent phase must match current phase.")
        if actor_id not in reaction_window.eligible_player_ids:
            raise GameLifecycleError("ReactionQueue actor must be eligible for the window.")

        request_id = state.next_decision_request_id()
        validated_decision_type = _validate_identifier("decision_type", decision_type)
        validated_actor_id = _validate_identifier("actor_id", actor_id)
        frame = ReactionQueueFrame(
            reaction_window=reaction_window,
            parent_phase=parent,
            parent_step=parent_step,
            resume_token=resume_token,
            request_id=request_id,
        )
        handler_payload = validate_json_value(
            payload
            if payload_factory is None
            else payload_factory(request_id, validated_decision_type, validated_actor_id)
        )
        request_payload_base: dict[str, JsonValue] = {
            "reaction_window": validate_json_value(reaction_window.to_payload()),
            "interrupts_parent": True,
            "parent": validate_json_value(
                {
                    "phase": parent.value,
                    "step": frame.parent_step,
                    "resume_token": frame.resume_token,
                }
            ),
            "handler_payload": handler_payload,
        }
        if isinstance(handler_payload, dict):
            for key, value in handler_payload.items():
                if key not in request_payload_base:
                    request_payload_base[key] = value
        request_payload = validate_json_value(request_payload_base)
        request = DecisionRequest(
            request_id=request_id,
            decision_type=validated_decision_type,
            actor_id=validated_actor_id,
            payload=request_payload,
            options=options,
        )
        self._frames.append(frame)
        decisions.event_log.append("reaction_window_opened", frame.to_payload())
        queued = decisions.request_decision(request)
        return TriggeredDecisionRequest(
            reaction_window=reaction_window,
            decision_request=queued,
        )

    def continue_reaction(
        self,
        *,
        result: DecisionResult,
        next_request_id: str,
        decisions: DecisionController,
    ) -> ReactionQueueFrame:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("ReactionQueue result must be a DecisionResult.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("ReactionQueue requires a DecisionController.")
        self.validate_result(result)
        frame = self._frames[-1]
        continued = frame.with_request_id(next_request_id)
        self._frames[-1] = continued
        record = decisions.record_for_result(result)
        decisions.event_log.append(
            "reaction_window_continued",
            {
                "reaction_window": frame.reaction_window.to_payload(),
                "parent_phase": frame.parent_phase.value,
                "parent_step": frame.parent_step,
                "resume_token": frame.resume_token,
                "decision_record": record.to_payload(),
                "next_request_id": continued.request_id,
            },
        )
        return continued

    def resolve_reaction(
        self,
        *,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> ReactionResume:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("ReactionQueue result must be a DecisionResult.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("ReactionQueue requires a DecisionController.")
        self.validate_result(result)
        frame = self._frames[-1]
        record = decisions.record_for_result(result)
        self._frames.pop()
        resume = ReactionResume(
            reaction_window=frame.reaction_window,
            parent_phase=frame.parent_phase,
            parent_step=frame.parent_step,
            resume_token=frame.resume_token,
            decision_record=record.to_payload(),
        )
        decisions.event_log.append("reaction_window_resolved", resume.to_payload())
        decisions.event_log.append("reaction_parent_resumed", resume.to_payload())
        return resume

    def validate_result(self, result: DecisionResult) -> None:
        if type(result) is not DecisionResult:
            raise GameLifecycleError("ReactionQueue result must be a DecisionResult.")
        if not self._frames:
            raise GameLifecycleError("ReactionQueue has no open reaction window.")
        frame = self._frames[-1]
        if frame.request_id != result.request_id:
            raise GameLifecycleError("ReactionQueue result does not resolve the active frame.")

    def to_payload(self) -> ReactionQueuePayload:
        return {"frames": [frame.to_payload() for frame in self._frames]}

    @classmethod
    def from_payload(cls, payload: ReactionQueuePayload) -> Self:
        queue = cls()
        for frame_payload in payload["frames"]:
            queue._frames.append(ReactionQueueFrame.from_payload(frame_payload))
        return queue


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
