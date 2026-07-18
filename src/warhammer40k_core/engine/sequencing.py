from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSpecError,
    RollOffRequest,
    RollOffResult,
    RollOffResultPayload,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import (
    EventLogError,
    EventRecord,
    JsonValue,
    validate_json_value,
)
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


@dataclass(frozen=True, slots=True)
class SequencingRollOffRewind:
    decisions: DecisionController
    removed_events: tuple[EventRecord, ...]


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
    return _sequencing_decision_request(
        request_id=request_identifier,
        context=context,
        participants=participant_values,
        roll_off_result=roll_off_result,
    )


def decision_controller_before_pending_sequencing_roll_off(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
) -> SequencingRollOffRewind | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Sequencing roll-off rewind requires a DecisionController.")
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Sequencing roll-off rewind requires a DecisionRequest.")
    events = decisions.event_log.records
    if len(events) < 2:
        return None
    issued_event = events[-1]
    roll_off_event = events[-2]
    if (
        issued_event.event_type != "decision_requested"
        or roll_off_event.event_type != "roll_off_resolved"
    ):
        return None
    if not isinstance(issued_event.payload, dict):
        raise GameLifecycleError("Sequencing decision_requested payload must be an object.")
    try:
        issued_request = DecisionRequest.from_payload(
            cast(DecisionRequestPayload, issued_event.payload)
        )
    except (KeyError, TypeError, DecisionError) as exc:
        raise GameLifecycleError("Sequencing decision_requested payload is invalid.") from exc
    if issued_request != request:
        raise GameLifecycleError("Sequencing decision_requested event drifted from the queue.")
    if not isinstance(roll_off_event.payload, dict):
        raise GameLifecycleError("Sequencing roll_off_resolved payload must be an object.")
    try:
        roll_off_result = RollOffResult.from_payload(
            cast(RollOffResultPayload, roll_off_event.payload)
        )
    except (KeyError, TypeError, DiceRollSpecError) as exc:
        raise GameLifecycleError("Sequencing roll_off_resolved payload is invalid.") from exc
    expected_roll_off_request = RollOffRequest(
        request_id=f"{request.request_id}:roll-off",
        purpose="sequencing_conflict",
        player_ids=roll_off_result.request.player_ids,
        resolving_decision_id=request.request_id,
    )
    if roll_off_result.request != expected_roll_off_request:
        raise GameLifecycleError("Sequencing roll-off request provenance drifted.")
    suffix_start = _contiguous_roll_off_suffix_start(events, roll_off_index=len(events) - 2)
    dice_events = events[suffix_start:-2]
    historical_rolls = _historical_rolls_for_roll_off(roll_off_result)
    if len(dice_events) != len(historical_rolls):
        raise GameLifecycleError("Sequencing roll-off dice event count drifted.")
    for event, historical_roll in zip(dice_events, historical_rolls, strict=True):
        if event.event_type != "dice_rolled" or event.payload != historical_roll.to_payload():
            raise GameLifecycleError("Sequencing roll-off dice event provenance drifted.")
    payload = decisions.to_payload()
    payload["event_log"] = payload["event_log"][:suffix_start]
    try:
        prefix_decisions = DecisionController.from_payload(payload)
    except (KeyError, TypeError, DecisionError, EventLogError) as exc:
        raise GameLifecycleError("Sequencing roll-off event prefix is invalid.") from exc
    return SequencingRollOffRewind(
        decisions=prefix_decisions,
        removed_events=events[suffix_start:],
    )


def _contiguous_roll_off_suffix_start(
    events: tuple[EventRecord, ...],
    *,
    roll_off_index: int,
) -> int:
    suffix_start = roll_off_index
    while suffix_start > 0:
        candidate = events[suffix_start - 1]
        if candidate.event_type != "dice_rolled":
            break
        if not isinstance(candidate.payload, dict):
            raise GameLifecycleError("Sequencing dice_rolled payload must be an object.")
        try:
            roll = DiceRollResult.from_payload(cast(DiceRollResultPayload, candidate.payload))
        except (KeyError, TypeError, DiceRollSpecError) as exc:
            raise GameLifecycleError("Sequencing dice_rolled payload is invalid.") from exc
        if roll.spec.roll_type != "roll_off":
            break
        suffix_start -= 1
    if suffix_start == roll_off_index:
        raise GameLifecycleError("Sequencing roll-off event suffix has no dice events.")
    return suffix_start


def _historical_rolls_for_roll_off(
    roll_off_result: RollOffResult,
) -> tuple[DiceRollResult, ...]:
    historical_rolls: list[DiceRollResult] = []
    for round_result in roll_off_result.rounds:
        if tuple(roll.player_id for roll in round_result.player_rolls) != (
            roll_off_result.request.player_ids
        ):
            raise GameLifecycleError("Sequencing roll-off player order drifted.")
        historical_rolls.extend(roll.roll_result for roll in round_result.player_rolls)
    return tuple(historical_rolls)


def _sequencing_decision_request(
    *,
    request_id: str,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
    roll_off_result: RollOffResult | None,
) -> DecisionRequest:
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
            tuple(participant.participant_id for participant in participants)
        )
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SEQUENCING_DECISION_TYPE,
        actor_id=deciding_player_id,
        payload=validate_json_value(
            {
                "sequencing_conflict": context.to_payload(),
                "participants": [participant.to_payload() for participant in participants],
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
    _validate_sequencing_decision_request(
        request=request,
        context=context,
        participants=participants,
    )
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


def apply_sequencing_decision_from_request(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> SequencingDecision:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Sequencing request must be a DecisionRequest.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Sequencing request payload must be an object.")
    context_payload = payload.get("sequencing_conflict")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Sequencing request payload requires sequencing_conflict.")
    participant_payloads = payload.get("participants")
    if not isinstance(participant_payloads, list):
        raise GameLifecycleError("Sequencing request payload requires participants.")
    participants: list[SequencingParticipant] = []
    for participant_payload in participant_payloads:
        if not isinstance(participant_payload, dict):
            raise GameLifecycleError("Sequencing request participants must be objects.")
        participants.append(
            SequencingParticipant.from_payload(
                cast(SequencingParticipantPayload, participant_payload)
            )
        )
    return apply_sequencing_decision(
        request=request,
        result=result,
        context=SequencingConflictContext.from_payload(
            cast(SequencingConflictContextPayload, context_payload)
        ),
        participants=tuple(participants),
    )


def _validate_sequencing_decision_request(
    *,
    request: DecisionRequest,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
) -> None:
    participant_values = _validate_participants(participants, player_ids=context.player_ids)
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Sequencing request payload must be an object.")
    roll_off_result = _roll_off_from_payload(payload.get("roll_off_result"))
    if context.requires_roll_off():
        if roll_off_result is None:
            raise GameLifecycleError("Sequencing request requires an engine roll-off result.")
        expected_roll_off_request = RollOffRequest(
            request_id=f"{request.request_id}:roll-off",
            purpose="sequencing_conflict",
            player_ids=context.player_ids,
            resolving_decision_id=request.request_id,
        )
        if roll_off_result.request != expected_roll_off_request:
            raise GameLifecycleError("Sequencing request roll-off provenance drifted.")
    elif roll_off_result is not None:
        raise GameLifecycleError("Sequencing request has an unexpected roll-off result.")
    expected_request = _sequencing_decision_request(
        request_id=request.request_id,
        context=context,
        participants=participant_values,
        roll_off_result=roll_off_result,
    )
    if request != expected_request:
        raise GameLifecycleError("Sequencing request does not match its authoritative context.")


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


_validate_identifier = IdentifierValidator(GameLifecycleError)


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
