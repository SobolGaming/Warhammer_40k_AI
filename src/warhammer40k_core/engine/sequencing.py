from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from itertools import permutations
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import (
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowPayload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    END_ROUND_MISSION_ORDER_SOURCE_ID,
    END_TURN_MISSION_ORDER_SOURCE_ID,
    RULES_SEQUENCING_SOURCE_ID,
)

SEQUENCING_DECISION_TYPE = "resolve_sequencing_order"


class SequencingRequirement(StrEnum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


class SequencingRuleOrigin(StrEnum):
    PLAYER = "player"
    MISSION = "mission"


class SequencingParticipantPayload(TypedDict):
    participant_id: str
    player_id: str | None
    source_rule_id: str
    requirement: str
    origin: str
    label: str | None
    secret: bool
    payload: JsonValue


class SequencingConflictContextPayload(TypedDict):
    conflict_id: str
    game_id: str
    timing_window: TimingWindowPayload
    player_ids: list[str]
    active_player_id: str | None
    sequence_exception_source_id: str | None


class SequencingDecisionPayload(TypedDict):
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    ordered_participant_ids: list[str]
    request_id: str
    result_id: str
    timing_window: TimingWindowPayload


class SequencingNextParticipantDecisionPayload(TypedDict):
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    previously_selected_participant_ids: list[str]
    remaining_participant_ids: list[str]
    selected_participant_id: str
    request_id: str
    result_id: str
    timing_window: TimingWindowPayload


@dataclass(frozen=True, slots=True)
class SequencingParticipant:
    participant_id: str
    player_id: str | None
    source_rule_id: str
    requirement: SequencingRequirement
    origin: SequencingRuleOrigin = SequencingRuleOrigin.PLAYER
    payload: JsonValue = None
    label: str | None = field(default=None, compare=False)
    secret: bool = False

    def __post_init__(self) -> None:
        if type(self.requirement) is not SequencingRequirement:
            raise GameLifecycleError("Sequencing participant requires a typed requirement.")
        if type(self.origin) is not SequencingRuleOrigin:
            raise GameLifecycleError("Sequencing participant requires a typed rule origin.")
        if self.player_id is None and (
            self.origin is not SequencingRuleOrigin.MISSION
            or self.requirement is not SequencingRequirement.MANDATORY
        ):
            raise GameLifecycleError("Only automatic mandatory mission rules may have no owner.")
        object.__setattr__(
            self,
            "participant_id",
            _validate_identifier("SequencingParticipant participant_id", self.participant_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_optional_identifier("SequencingParticipant player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("SequencingParticipant source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))
        if self.label is not None:
            _validate_identifier("SequencingParticipant label", self.label)
        if type(self.secret) is not bool:
            raise GameLifecycleError("Sequencing participant secrecy must be a bool.")

    def to_payload(self) -> SequencingParticipantPayload:
        return {
            "participant_id": self.participant_id,
            "player_id": self.player_id,
            "source_rule_id": self.source_rule_id,
            "requirement": self.requirement.value,
            "origin": self.origin.value,
            "label": self.label,
            "secret": self.secret,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: SequencingParticipantPayload) -> Self:
        return cls(
            participant_id=payload["participant_id"],
            player_id=payload["player_id"],
            source_rule_id=payload["source_rule_id"],
            requirement=sequencing_requirement_from_token(payload["requirement"]),
            origin=sequencing_origin_from_token(payload["origin"]),
            label=payload["label"],
            secret=payload["secret"],
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class SequencingConflictContext:
    conflict_id: str
    game_id: str
    timing_window: TimingWindow
    player_ids: tuple[str, ...]
    active_player_id: str | None

    @property
    def sequence_exception_source_id(self) -> str | None:
        trigger = self.timing_window.descriptor.trigger_kind
        if trigger is TimingTriggerKind.END_TURN:
            return END_TURN_MISSION_ORDER_SOURCE_ID
        if trigger is TimingTriggerKind.END_BATTLE_ROUND:
            return END_ROUND_MISSION_ORDER_SOURCE_ID
        return None

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
        if self.active_player_id is None:
            raise GameLifecycleError("Sequencing requires an active player.")

    def to_payload(self) -> SequencingConflictContextPayload:
        return {
            "conflict_id": self.conflict_id,
            "game_id": self.game_id,
            "timing_window": self.timing_window.to_payload(),
            "player_ids": list(self.player_ids),
            "active_player_id": self.active_player_id,
            "sequence_exception_source_id": self.sequence_exception_source_id,
        }

    @classmethod
    def from_payload(cls, payload: SequencingConflictContextPayload) -> Self:
        context = cls(
            conflict_id=payload["conflict_id"],
            game_id=payload["game_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
            player_ids=tuple(payload["player_ids"]),
            active_player_id=payload["active_player_id"],
        )
        if payload["sequence_exception_source_id"] != context.sequence_exception_source_id:
            raise GameLifecycleError("Sequencing source exception authority drift.")
        return context


@dataclass(frozen=True, slots=True)
class SequencingDecision:
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    ordered_participant_ids: tuple[str, ...]
    request_id: str
    result_id: str
    timing_window: TimingWindow

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
                min_length=1,
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

    def to_payload(self) -> SequencingDecisionPayload:
        return {
            "decision_id": self.decision_id,
            "conflict_id": self.conflict_id,
            "deciding_player_id": self.deciding_player_id,
            "ordered_participant_ids": list(self.ordered_participant_ids),
            "request_id": self.request_id,
            "result_id": self.result_id,
            "timing_window": self.timing_window.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: SequencingDecisionPayload) -> Self:
        return cls(
            decision_id=payload["decision_id"],
            conflict_id=payload["conflict_id"],
            deciding_player_id=payload["deciding_player_id"],
            ordered_participant_ids=tuple(payload["ordered_participant_ids"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
        )


@dataclass(frozen=True, slots=True)
class SequencingNextParticipantDecision:
    decision_id: str
    conflict_id: str
    deciding_player_id: str
    previously_selected_participant_ids: tuple[str, ...]
    remaining_participant_ids: tuple[str, ...]
    selected_participant_id: str
    request_id: str
    result_id: str
    timing_window: TimingWindow

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _validate_identifier("Sequencing next decision_id", self.decision_id),
        )
        object.__setattr__(
            self,
            "conflict_id",
            _validate_identifier("Sequencing next conflict_id", self.conflict_id),
        )
        object.__setattr__(
            self,
            "deciding_player_id",
            _validate_identifier(
                "Sequencing next deciding_player_id",
                self.deciding_player_id,
            ),
        )
        previous = _validate_identifier_tuple(
            "Sequencing previously selected participant IDs",
            self.previously_selected_participant_ids,
            min_length=0,
            sort_values=False,
        )
        remaining = _validate_identifier_tuple(
            "Sequencing remaining participant IDs",
            self.remaining_participant_ids,
            min_length=1,
            sort_values=True,
        )
        selected = _validate_identifier(
            "Sequencing selected participant ID",
            self.selected_participant_id,
        )
        if set(previous).intersection(remaining):
            raise GameLifecycleError(
                "Sequencing previously selected and remaining participants overlap."
            )
        if selected not in remaining:
            raise GameLifecycleError("Sequencing selected participant is not remaining.")
        object.__setattr__(self, "previously_selected_participant_ids", previous)
        object.__setattr__(self, "remaining_participant_ids", remaining)
        object.__setattr__(self, "selected_participant_id", selected)
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("Sequencing next request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("Sequencing next result_id", self.result_id),
        )
        if type(self.timing_window) is not TimingWindow:
            raise GameLifecycleError(
                "Sequencing next participant decision timing_window must be a TimingWindow."
            )

    def to_payload(self) -> SequencingNextParticipantDecisionPayload:
        return {
            "decision_id": self.decision_id,
            "conflict_id": self.conflict_id,
            "deciding_player_id": self.deciding_player_id,
            "previously_selected_participant_ids": list(self.previously_selected_participant_ids),
            "remaining_participant_ids": list(self.remaining_participant_ids),
            "selected_participant_id": self.selected_participant_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "timing_window": self.timing_window.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: SequencingNextParticipantDecisionPayload) -> Self:
        return cls(
            decision_id=payload["decision_id"],
            conflict_id=payload["conflict_id"],
            deciding_player_id=payload["deciding_player_id"],
            previously_selected_participant_ids=tuple(
                payload["previously_selected_participant_ids"]
            ),
            remaining_participant_ids=tuple(payload["remaining_participant_ids"]),
            selected_participant_id=payload["selected_participant_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
        )


def create_sequencing_decision_request(
    *,
    request_id: str,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
) -> DecisionRequest:
    request_identifier = _validate_identifier("request_id", request_id)
    participant_values = _validate_participants(participants, player_ids=context.player_ids)
    return _sequencing_decision_request(
        request_id=request_identifier,
        context=context,
        participants=participant_values,
    )


def create_select_next_sequencing_participant_request(
    *,
    request_id: str,
    context: SequencingConflictContext,
    previously_selected_participant_ids: tuple[str, ...],
    remaining_participants: tuple[SequencingParticipant, ...],
) -> DecisionRequest:
    """Create a linear-size request selecting only the next participant."""

    request_identifier = _validate_identifier("request_id", request_id)
    previous = _validate_identifier_tuple(
        "previously_selected_participant_ids",
        previously_selected_participant_ids,
        min_length=0,
        sort_values=False,
    )
    participants = _validate_participants(
        remaining_participants,
        player_ids=context.player_ids,
    )
    participant_ids = tuple(participant.participant_id for participant in participants)
    if set(previous).intersection(participant_ids):
        raise GameLifecycleError(
            "Select-next sequencing previous and remaining participants overlap."
        )
    eligible = eligible_sequencing_participants(context=context, participants=participants)
    participant_ids = tuple(participant.participant_id for participant in eligible)
    deciding_player_id = sequencing_owner(eligible[0], context=context)
    return DecisionRequest(
        request_id=request_identifier,
        decision_type=SEQUENCING_DECISION_TYPE,
        actor_id=deciding_player_id,
        payload=validate_json_value(
            {
                "sequencing_model": "select_next_participant",
                "secret": any(participant.secret for participant in eligible),
                "sequencing_source_rule_id": RULES_SEQUENCING_SOURCE_ID,
                "eligible_tier": sequencing_tier(eligible[0], context=context),
                "sequencing_conflict": context.to_payload(),
                "previously_selected_participant_ids": list(previous),
                "participants": [participant.to_payload() for participant in eligible],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=f"next:{participant.participant_id}",
                label=participant.label or participant.participant_id,
                payload=validate_json_value(
                    {
                        "sequencing_conflict_id": context.conflict_id,
                        "deciding_player_id": deciding_player_id,
                        "previously_selected_participant_ids": list(previous),
                        "remaining_participant_ids": list(participant_ids),
                        "selected_participant_id": participant.participant_id,
                        "timing_window": context.timing_window.to_payload(),
                    }
                ),
            )
            for participant in eligible
        ),
    )


def is_select_next_sequencing_participant_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Select-next sequencing check requires a DecisionRequest.")
    return (
        request.decision_type == SEQUENCING_DECISION_TYPE
        and isinstance(request.payload, dict)
        and request.payload.get("sequencing_model") == "select_next_participant"
    )


def apply_select_next_sequencing_participant_from_request(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> SequencingNextParticipantDecision:
    if not is_select_next_sequencing_participant_request(request):
        raise GameLifecycleError("Sequencing request is not a select-next request.")
    payload = cast(dict[str, JsonValue], request.payload)
    context_payload = payload.get("sequencing_conflict")
    participant_payloads = payload.get("participants")
    previous_values = payload.get("previously_selected_participant_ids")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Select-next sequencing requires a conflict context.")
    if not isinstance(participant_payloads, list):
        raise GameLifecycleError("Select-next sequencing requires remaining participants.")
    if not isinstance(previous_values, list):
        raise GameLifecycleError("Select-next sequencing requires the selected prefix.")
    context = SequencingConflictContext.from_payload(
        cast(SequencingConflictContextPayload, context_payload)
    )
    participants = tuple(
        SequencingParticipant.from_payload(cast(SequencingParticipantPayload, value))
        for value in participant_payloads
        if isinstance(value, dict)
    )
    if len(participants) != len(participant_payloads):
        raise GameLifecycleError("Select-next sequencing participants must be objects.")
    previous = tuple(
        _validate_identifier("previously_selected_participant_id", value)
        for value in previous_values
    )
    expected = create_select_next_sequencing_participant_request(
        request_id=request.request_id,
        context=context,
        previously_selected_participant_ids=previous,
        remaining_participants=participants,
    )
    if request != expected:
        raise GameLifecycleError("Select-next sequencing request authority drifted.")
    result.validate_for_request(request)
    result_payload = result.payload
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Select-next sequencing result payload must be an object.")
    selected = _validate_identifier(
        "selected_participant_id",
        result_payload.get("selected_participant_id"),
    )
    participant_ids = tuple(participant.participant_id for participant in participants)
    return SequencingNextParticipantDecision(
        decision_id=f"sequencing-next-decision:{context.conflict_id}:{result.result_id}",
        conflict_id=context.conflict_id,
        deciding_player_id=_validate_identifier(
            "deciding_player_id",
            result_payload.get("deciding_player_id"),
        ),
        previously_selected_participant_ids=previous,
        remaining_participant_ids=participant_ids,
        selected_participant_id=selected,
        request_id=request.request_id,
        result_id=result.result_id,
        timing_window=context.timing_window,
    )


def validate_sequencing_result_from_request(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    if is_select_next_sequencing_participant_request(request):
        apply_select_next_sequencing_participant_from_request(
            request=request,
            result=result,
        )
        return
    apply_sequencing_decision_from_request(request=request, result=result)


def sequencing_decision_event_from_request(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> tuple[str, JsonValue]:
    if is_select_next_sequencing_participant_request(request):
        selection = apply_select_next_sequencing_participant_from_request(
            request=request,
            result=result,
        )
        return "sequencing_next_participant_selected", validate_json_value(selection.to_payload())
    decision = apply_sequencing_decision_from_request(request=request, result=result)
    return "sequencing_order_resolved", validate_json_value(decision.to_payload())


def _sequencing_decision_request(
    *,
    request_id: str,
    context: SequencingConflictContext,
    participants: tuple[SequencingParticipant, ...],
) -> DecisionRequest:
    eligible = eligible_sequencing_participants(context=context, participants=participants)
    deciding_player_id = sequencing_owner(eligible[0], context=context)
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
                }
            ),
        )
        for ordered in permutations(tuple(participant.participant_id for participant in eligible))
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SEQUENCING_DECISION_TYPE,
        actor_id=deciding_player_id,
        payload=validate_json_value(
            {
                "sequencing_conflict": context.to_payload(),
                "sequencing_source_rule_id": RULES_SEQUENCING_SOURCE_ID,
                "secret": any(participant.secret for participant in eligible),
                "participants": [participant.to_payload() for participant in eligible],
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
) -> DecisionRequest:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Sequencing decisions require a DecisionController.")
    request = create_sequencing_decision_request(
        request_id=request_id,
        context=context,
        participants=participants,
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
    eligible = eligible_sequencing_participants(context=context, participants=participant_values)
    participant_ids = {participant.participant_id for participant in eligible}
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
        raise GameLifecycleError("Sequencing result must order every eligible participant once.")
    deciding_player_id = _validate_identifier(
        "deciding_player_id",
        payload.get("deciding_player_id"),
    )
    return SequencingDecision(
        decision_id=f"sequencing-decision:{context.conflict_id}:{result.result_id}",
        conflict_id=context.conflict_id,
        deciding_player_id=deciding_player_id,
        ordered_participant_ids=ordered,
        request_id=request.request_id,
        result_id=result.result_id,
        timing_window=context.timing_window,
    )


def apply_sequencing_decision_from_request(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> SequencingDecision:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Sequencing request must be a DecisionRequest.")
    if is_select_next_sequencing_participant_request(request):
        raise GameLifecycleError("Select-next sequencing requires its bounded applier.")
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
    expected_request = _sequencing_decision_request(
        request_id=request.request_id,
        context=context,
        participants=participant_values,
    )
    if request != expected_request:
        raise GameLifecycleError("Sequencing request does not match its authoritative context.")


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
    if not raw_values:
        raise GameLifecycleError("Sequencing conflict requires at least one participant.")
    seen: set[str] = set()
    validated: list[SequencingParticipant] = []
    for value in raw_values:
        if type(value) is not SequencingParticipant:
            raise GameLifecycleError(
                "Sequencing participants must contain SequencingParticipant values."
            )
        if value.player_id is not None and value.player_id not in player_ids:
            raise GameLifecycleError("Sequencing participant player_id is not in player_ids.")
        if value.participant_id in seen:
            raise GameLifecycleError("Sequencing participants must not contain duplicates.")
        seen.add(value.participant_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda participant: participant.participant_id))


def _order_option_id(ordered_participant_ids: tuple[str, ...]) -> str:
    return "order:" + ",".join(ordered_participant_ids)


def sequencing_requirement_from_token(value: object) -> SequencingRequirement:
    if type(value) is not str:
        raise GameLifecycleError("Sequencing requirement token must be a string.")
    try:
        return SequencingRequirement(value)
    except ValueError as exc:
        raise GameLifecycleError("Unknown sequencing requirement.") from exc


def sequencing_origin_from_token(value: object) -> SequencingRuleOrigin:
    if type(value) is not str:
        raise GameLifecycleError("Sequencing origin token must be a string.")
    try:
        return SequencingRuleOrigin(value)
    except ValueError as exc:
        raise GameLifecycleError("Unknown sequencing rule origin.") from exc


def sequencing_owner(
    participant: SequencingParticipant, *, context: SequencingConflictContext
) -> str:
    return (
        _require_active_player(context) if participant.player_id is None else participant.player_id
    )


def sequencing_tier(
    participant: SequencingParticipant, *, context: SequencingConflictContext
) -> int:
    """01.03.02 authority; display labels and traversal order never decide priority."""
    if type(participant) is not SequencingParticipant:
        raise GameLifecycleError("Sequencing tier requires a participant.")
    if participant.player_id is not None and participant.player_id not in context.player_ids:
        raise GameLifecycleError("Sequencing participant owner is outside this conflict.")
    mission_after_players = (
        participant.origin is SequencingRuleOrigin.MISSION
        and context.sequence_exception_source_id is not None
    )
    if participant.player_id is None:
        return 4 if mission_after_players else -1
    owner_tier = 0 if participant.player_id == _require_active_player(context) else 2
    return (
        (5 if mission_after_players else 0)
        + owner_tier
        + (participant.requirement is SequencingRequirement.OPTIONAL)
    )


def eligible_sequencing_participants(
    *, context: SequencingConflictContext, participants: tuple[SequencingParticipant, ...]
) -> tuple[SequencingParticipant, ...]:
    values = _validate_participants(participants, player_ids=context.player_ids)
    tier = min(sequencing_tier(participant, context=context) for participant in values)
    return tuple(
        participant
        for participant in values
        if sequencing_tier(participant, context=context) == tier
    )


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
