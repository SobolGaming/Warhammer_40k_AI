from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Self, TypedDict, cast

from warhammer40k_core.core.dice import RollOffRequest, RollOffResult, RollOffResultPayload
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowPayload,
)

SEQUENCING_DECISION_TYPE = "resolve_sequencing_order"


class SequencingParticipantPayload(TypedDict):
    participant_id: str
    player_id: str
    source_rule_id: str
    payload: JsonValue


class SequencingConflictContextPayload(TypedDict):
    conflict_id: str
    game_id: str
    timing_window: TimingWindowPayload
    player_ids: list[str]
    active_player_id: str | None


class SequencingDecisionPayload(TypedDict):
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    ordered_participant_ids: list[str]
    request_id: str
    result_id: str
    timing_window: TimingWindowPayload
    roll_off_result: RollOffResultPayload | None


_ROLL_OFF_TIMING_KINDS = frozenset(
    (
        TimingTriggerKind.BEFORE_BATTLE,
        TimingTriggerKind.AFTER_BATTLE,
        TimingTriggerKind.START_BATTLE_ROUND,
        TimingTriggerKind.END_BATTLE_ROUND,
    )
)


@dataclass(frozen=True, slots=True)
class SequencingParticipant:
    participant_id: str
    player_id: str
    source_rule_id: str
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "participant_id",
            _validate_identifier("SequencingParticipant participant_id", self.participant_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SequencingParticipant player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("SequencingParticipant source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> SequencingParticipantPayload:
        return {
            "participant_id": self.participant_id,
            "player_id": self.player_id,
            "source_rule_id": self.source_rule_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: SequencingParticipantPayload) -> Self:
        return cls(
            participant_id=payload["participant_id"],
            player_id=payload["player_id"],
            source_rule_id=payload["source_rule_id"],
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class SequencingConflictContext:
    conflict_id: str
    game_id: str
    timing_window: TimingWindow
    player_ids: tuple[str, ...]
    active_player_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conflict_id",
            _validate_identifier("SequencingConflictContext conflict_id", self.conflict_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("SequencingConflictContext game_id", self.game_id),
        )
        if type(self.timing_window) is not TimingWindow:
            raise GameLifecycleError(
                "SequencingConflictContext timing_window must be a TimingWindow."
            )
        object.__setattr__(
            self,
            "player_ids",
            _validate_identifier_tuple(
                "SequencingConflictContext player_ids",
                self.player_ids,
                min_length=2,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "SequencingConflictContext active_player_id",
                self.active_player_id,
            ),
        )
        if self.active_player_id is not None and self.active_player_id not in self.player_ids:
            raise GameLifecycleError("Sequencing active_player_id must be in player_ids.")
        if not self.requires_roll_off() and self.active_player_id is None:
            raise GameLifecycleError("During-battle sequencing requires an active player.")

    def requires_roll_off(self) -> bool:
        return self.timing_window.descriptor.trigger_kind in _ROLL_OFF_TIMING_KINDS

    def to_payload(self) -> SequencingConflictContextPayload:
        return {
            "conflict_id": self.conflict_id,
            "game_id": self.game_id,
            "timing_window": self.timing_window.to_payload(),
            "player_ids": list(self.player_ids),
            "active_player_id": self.active_player_id,
        }

    @classmethod
    def from_payload(cls, payload: SequencingConflictContextPayload) -> Self:
        return cls(
            conflict_id=payload["conflict_id"],
            game_id=payload["game_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
            player_ids=tuple(payload["player_ids"]),
            active_player_id=payload["active_player_id"],
        )


@dataclass(frozen=True, slots=True)
class SequencingDecision:
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    ordered_participant_ids: tuple[str, ...]
    request_id: str
    result_id: str
    timing_window: TimingWindow
    roll_off_result: RollOffResult | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _validate_identifier("SequencingDecision decision_id", self.decision_id),
        )
        object.__setattr__(
            self,
            "conflict_id",
            _validate_identifier("SequencingDecision conflict_id", self.conflict_id),
        )
        object.__setattr__(
            self,
            "deciding_player_id",
            _validate_identifier(
                "SequencingDecision deciding_player_id",
                self.deciding_player_id,
            ),
        )
        object.__setattr__(
            self,
            "ordered_participant_ids",
            _validate_identifier_tuple(
                "SequencingDecision ordered_participant_ids",
                self.ordered_participant_ids,
                min_length=2,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("SequencingDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("SequencingDecision result_id", self.result_id),
        )
        if type(self.timing_window) is not TimingWindow:
            raise GameLifecycleError("SequencingDecision timing_window must be a TimingWindow.")
        if self.roll_off_result is not None and type(self.roll_off_result) is not RollOffResult:
            raise GameLifecycleError("SequencingDecision roll_off_result must be RollOffResult.")

    def to_payload(self) -> SequencingDecisionPayload:
        return {
            "decision_id": self.decision_id,
            "conflict_id": self.conflict_id,
            "deciding_player_id": self.deciding_player_id,
            "ordered_participant_ids": list(self.ordered_participant_ids),
            "request_id": self.request_id,
            "result_id": self.result_id,
            "timing_window": self.timing_window.to_payload(),
            "roll_off_result": (
                None if self.roll_off_result is None else self.roll_off_result.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: SequencingDecisionPayload) -> Self:
        roll_off_payload = payload["roll_off_result"]
        return cls(
            decision_id=payload["decision_id"],
            conflict_id=payload["conflict_id"],
            deciding_player_id=payload["deciding_player_id"],
            ordered_participant_ids=tuple(payload["ordered_participant_ids"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
            roll_off_result=(
                None if roll_off_payload is None else RollOffResult.from_payload(roll_off_payload)
            ),
        )


def create_sequencing_decision_request(
    *,
    request_id: str,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
    dice_manager: DiceRollManager | None = None,
) -> DecisionRequest:
    request_identifier = _validate_identifier("request_id", request_id)
    participant_values = _validate_participants(participants, player_ids=context.player_ids)
    roll_off_result = _roll_off_result_for_context(
        request_id=request_identifier,
        context=context,
        dice_manager=dice_manager,
    )
    deciding_player_id = (
        roll_off_result.winner_player_id
        if roll_off_result is not None
        else _require_active_player(context)
    )
    options = tuple(
        DecisionOption(
            option_id=_order_option_id(ordered),
            label=_order_option_label(ordered),
            payload=validate_json_value(
                {
                    "sequencing_conflict_id": context.conflict_id,
                    "deciding_player_id": deciding_player_id,
                    "ordered_participant_ids": list(ordered),
                    "timing_window": context.timing_window.to_payload(),
                    "roll_off_result": (
                        None if roll_off_result is None else roll_off_result.to_payload()
                    ),
                }
            ),
        )
        for ordered in permutations(
            tuple(participant.participant_id for participant in participant_values)
        )
    )
    return DecisionRequest(
        request_id=request_identifier,
        decision_type=SEQUENCING_DECISION_TYPE,
        actor_id=deciding_player_id,
        payload=validate_json_value(
            {
                "sequencing_conflict": context.to_payload(),
                "participants": [participant.to_payload() for participant in participant_values],
                "requires_roll_off": context.requires_roll_off(),
                "roll_off_result": (
                    None if roll_off_result is None else roll_off_result.to_payload()
                ),
            }
        ),
        options=options,
    )


def request_sequencing_decision(
    *,
    request_id: str,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
    decisions: DecisionController,
    dice_manager: DiceRollManager | None = None,
) -> DecisionRequest:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Sequencing decisions require a DecisionController.")
    request = create_sequencing_decision_request(
        request_id=request_id,
        context=context,
        participants=participants,
        dice_manager=dice_manager,
    )
    return decisions.request_decision(request)


def apply_sequencing_decision(
    *,
    request: DecisionRequest,
    result: DecisionResult,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
) -> SequencingDecision:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Sequencing request must be a DecisionRequest.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Sequencing result must be a DecisionResult.")
    if request.decision_type != SEQUENCING_DECISION_TYPE:
        raise GameLifecycleError("Sequencing request has the wrong decision_type.")
    result.validate_for_request(request)
    participant_values = _validate_participants(participants, player_ids=context.player_ids)
    participant_ids = {participant.participant_id for participant in participant_values}
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Sequencing result payload must be an object.")
    ordered_values = payload.get("ordered_participant_ids")
    if not isinstance(ordered_values, list):
        raise GameLifecycleError("Sequencing result ordered_participant_ids must be a list.")
    ordered = tuple(
        _validate_identifier("ordered_participant_id", value) for value in ordered_values
    )
    if set(ordered) != participant_ids or len(ordered) != len(participant_ids):
        raise GameLifecycleError("Sequencing result must order every participant exactly once.")
    deciding_player_id = _validate_identifier(
        "deciding_player_id",
        payload.get("deciding_player_id"),
    )
    roll_off_payload = payload.get("roll_off_result")
    roll_off_result = _roll_off_from_payload(roll_off_payload)
    return SequencingDecision(
        decision_id=f"sequencing-decision:{context.conflict_id}:{result.result_id}",
        conflict_id=context.conflict_id,
        deciding_player_id=deciding_player_id,
        ordered_participant_ids=ordered,
        request_id=request.request_id,
        result_id=result.result_id,
        timing_window=context.timing_window,
        roll_off_result=roll_off_result,
    )


def _roll_off_result_for_context(
    *,
    request_id: str,
    context: SequencingConflictContext,
    dice_manager: DiceRollManager | None,
) -> RollOffResult | None:
    if not context.requires_roll_off():
        return None
    if dice_manager is None:
        raise GameLifecycleError("Sequencing roll-off requires a DiceRollManager.")
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Sequencing roll-off requires a DiceRollManager.")
    return dice_manager.roll_off(
        RollOffRequest(
            request_id=f"{request_id}:roll-off",
            purpose="sequencing_conflict",
            player_ids=context.player_ids,
            resolving_decision_id=request_id,
        )
    )


def _roll_off_from_payload(payload: object) -> RollOffResult | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise GameLifecycleError("Sequencing roll_off_result must be an object or null.")
    return RollOffResult.from_payload(cast(RollOffResultPayload, payload))


def _require_active_player(context: SequencingConflictContext) -> str:
    if context.active_player_id is None:
        raise GameLifecycleError("Sequencing conflict requires an active player.")
    return context.active_player_id


def _validate_participants(
    participants: object,
    *,
    player_ids: tuple[str, ...],
) -> tuple[SequencingParticipant, ...]:
    if type(participants) is not tuple:
        raise GameLifecycleError("Sequencing participants must be a tuple.")
    raw_values = cast(tuple[object, ...], participants)
    if len(raw_values) < 2:
        raise GameLifecycleError("Sequencing conflict requires at least two participants.")
    seen: set[str] = set()
    validated: list[SequencingParticipant] = []
    for value in raw_values:
        if type(value) is not SequencingParticipant:
            raise GameLifecycleError(
                "Sequencing participants must contain SequencingParticipant values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("Sequencing participant player_id is not in player_ids.")
        if value.participant_id in seen:
            raise GameLifecycleError("Sequencing participants must not contain duplicates.")
        seen.add(value.participant_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda participant: participant.participant_id))


def _order_option_id(ordered_participant_ids: tuple[str, ...]) -> str:
    return "order:" + ",".join(ordered_participant_ids)


def _order_option_label(ordered_participant_ids: tuple[str, ...]) -> str:
    return " > ".join(ordered_participant_ids)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)
