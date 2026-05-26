from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
)
from warhammer40k_core.core.rng import RandomSource
from warhammer40k_core.engine.event_log import (
    EventLog,
    JsonValue,
    canonical_json,
    validate_json_value,
)


class DecisionError(ValueError):
    """Raised when a decision request/result is invalid."""


class DecisionRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue


class DecisionResultPayload(TypedDict):
    result_id: str
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue


def _new_injected_results() -> deque[DiceRollResult]:
    return deque()


def _new_decision_records() -> list[DecisionResult]:
    return []


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise DecisionError("DecisionRequest request_id must not be empty.")
        if not self.decision_type.strip():
            raise DecisionError("DecisionRequest decision_type must not be empty.")
        if self.actor_id is not None and not self.actor_id.strip():
            raise DecisionError("DecisionRequest actor_id must not be empty when supplied.")
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def to_payload(self) -> DecisionRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: DecisionRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class DecisionResult:
    result_id: str
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue

    def __post_init__(self) -> None:
        if not self.result_id.strip():
            raise DecisionError("DecisionResult result_id must not be empty.")
        if not self.request_id.strip():
            raise DecisionError("DecisionResult request_id must not be empty.")
        if not self.decision_type.strip():
            raise DecisionError("DecisionResult decision_type must not be empty.")
        if self.actor_id is not None and not self.actor_id.strip():
            raise DecisionError("DecisionResult actor_id must not be empty when supplied.")
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def to_payload(self) -> DecisionResultPayload:
        return {
            "result_id": self.result_id,
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: DecisionResultPayload) -> Self:
        return cls(
            result_id=payload["result_id"],
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            payload=payload["payload"],
        )


@dataclass(slots=True)
class DiceRollManager:
    rng: RandomSource
    event_log: EventLog
    _injected_results: deque[DiceRollResult] = field(default_factory=_new_injected_results)
    _decision_records: list[DecisionResult] = field(default_factory=_new_decision_records)
    _roll_counter: int = 0
    _decision_request_counter: int = 0

    def __init__(
        self,
        random_source: RandomSource | int | str,
        *,
        event_log: EventLog | None = None,
        injected_results: Sequence[DiceRollResult | DiceRollResultPayload] = (),
    ) -> None:
        if isinstance(random_source, RandomSource):
            self.rng = random_source
        else:
            self.rng = RandomSource(random_source)
        self.event_log = EventLog() if event_log is None else event_log
        self._injected_results = deque(_coerce_result(result) for result in injected_results)
        self._decision_records = []
        self._roll_counter = 0
        self._decision_request_counter = 0
        self._seed_existing_event_history()

    @property
    def decision_records(self) -> tuple[DecisionResult, ...]:
        return tuple(self._decision_records)

    def roll(self, spec: DiceRollSpec) -> DiceRollState:
        result = self._produce_result(spec)
        self._record_roll(result)
        return DiceRollState.from_result(result)

    def roll_fixed(self, spec: DiceRollSpec, values: Iterable[int]) -> DiceRollState:
        result = DiceRollResult.from_values(
            roll_id=self._next_roll_id(),
            spec=spec,
            values=values,
            source="fixed",
        )
        self._record_roll(result)
        return DiceRollState.from_result(result)

    def record_decision(self, result: DecisionResult) -> None:
        self._decision_records.append(result)
        self.rng.append_history(result.history_token())
        event = self.event_log.append("decision_recorded", result.to_payload())
        self.rng.append_history(event.history_token())

    def request_reroll(
        self,
        state: DiceRollState,
        *,
        allowed_indices: Iterable[int],
    ) -> DecisionRequest:
        indices = _validate_index_list(tuple(allowed_indices), field_name="allowed_indices")
        for index in indices:
            if index >= len(state.current_values):
                raise DecisionError("Reroll allowed index is outside the current dice.")

        self._decision_request_counter += 1
        request = DecisionRequest(
            request_id=f"decision-request-{self._decision_request_counter:06d}",
            decision_type="select_dice_reroll",
            actor_id=state.original_result.spec.actor_id,
            payload={
                "roll_id": state.original_result.roll_id,
                "roll_type": state.original_result.spec.roll_type,
                "allowed_indices": list(indices),
                "current_values": list(state.current_values),
            },
        )
        event = self.event_log.append("decision_requested", request.to_payload())
        self.rng.append_history(request.history_token())
        self.rng.append_history(event.history_token())
        return request

    def resolve_reroll(
        self,
        state: DiceRollState,
        *,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> DiceRollState:
        self._validate_reroll_decision(state, request, result)
        self.record_decision(result)
        selected_indices = _extract_index_list(result.payload, key="selected_indices")
        if not selected_indices:
            event = self.event_log.append(
                "dice_reroll_declined",
                {
                    "roll_id": state.original_result.roll_id,
                    "decision_id": result.result_id,
                    "request_id": request.request_id,
                },
            )
            self.rng.append_history(event.history_token())
            return state

        replacement_spec = DiceRollSpec(
            expression=DiceExpression(
                quantity=len(selected_indices),
                sides=state.original_result.spec.expression.sides,
            ),
            reason=f"Reroll selected dice for {state.original_result.spec.reason}",
            roll_type=f"{state.original_result.spec.roll_type}.reroll",
            actor_id=state.original_result.spec.actor_id,
        )
        replacement_result = self._produce_result(replacement_spec)
        self._record_roll(replacement_result)
        updated_state = state.with_reroll(
            decision_id=result.result_id,
            request_id=request.request_id,
            selected_indices=selected_indices,
            replacement_result=replacement_result,
        )
        event = self.event_log.append("dice_reroll_resolved", updated_state.to_payload())
        self.rng.append_history(event.history_token())
        return updated_state

    def _produce_result(self, spec: DiceRollSpec) -> DiceRollResult:
        if self._injected_results:
            result = self._injected_results[0]
            if result.spec != spec:
                raise DiceRollSpecError("Injected dice result does not match requested spec.")
            self._injected_results.popleft()
            self._roll_counter += 1
            return result

        roll_id = self._next_roll_id()
        values = [
            self.rng.randint_inclusive(
                1,
                spec.expression.sides,
                stream_label=f"{roll_id}:{spec.roll_type}:{spec.reason}:die-{die_index}",
            )
            for die_index in range(spec.expression.quantity)
        ]
        return DiceRollResult.from_values(
            roll_id=roll_id,
            spec=spec,
            values=values,
            source="rng",
        )

    def _record_roll(self, result: DiceRollResult) -> None:
        event = self.event_log.append("dice_rolled", result.to_payload())
        self.rng.append_history(event.history_token())

    def _next_roll_id(self) -> str:
        self._roll_counter += 1
        return f"roll-{self._roll_counter:06d}"

    def _seed_existing_event_history(self) -> None:
        for record in self.event_log.records:
            self.rng.append_history(record.history_token())
            if record.event_type == "dice_rolled":
                self._roll_counter += 1
            elif record.event_type == "decision_requested":
                self._decision_request_counter += 1

    def _validate_reroll_decision(
        self,
        state: DiceRollState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> None:
        if request.decision_type != "select_dice_reroll":
            raise DecisionError("Reroll request has the wrong decision_type.")
        if result.decision_type != request.decision_type:
            raise DecisionError("Reroll result decision_type does not match request.")
        if result.request_id != request.request_id:
            raise DecisionError("Reroll result request_id does not match request.")
        if result.actor_id != request.actor_id:
            raise DecisionError("Reroll result actor_id does not match request.")
        request_roll_id = _extract_string(request.payload, key="roll_id")
        if request_roll_id != state.original_result.roll_id:
            raise DecisionError("Reroll request does not target this dice roll.")
        allowed_indices = set(_extract_index_list(request.payload, key="allowed_indices"))
        selected_indices = _extract_index_list(result.payload, key="selected_indices")
        if not set(selected_indices).issubset(allowed_indices):
            raise DecisionError("Reroll selected_indices must be allowed by the request.")


def _coerce_result(result: DiceRollResult | DiceRollResultPayload) -> DiceRollResult:
    if isinstance(result, DiceRollResult):
        return result
    return DiceRollResult.from_payload(result)


def _extract_string(payload: JsonValue, *, key: str) -> str:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, str):
        raise DecisionError(f"Decision payload key must be a string: {key}.")
    return value


def _extract_index_list(payload: JsonValue, *, key: str) -> tuple[int, ...]:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise DecisionError(f"Decision payload key must be an index list: {key}.")
    return _validate_index_list(tuple(value), field_name=key)


def _validate_index_list(indices: tuple[object, ...], *, field_name: str) -> tuple[int, ...]:
    validated: list[int] = []
    previous = -1
    for index in indices:
        if type(index) is not int:
            raise DecisionError(f"Decision {field_name} must contain integers.")
        if index < 0:
            raise DecisionError(f"Decision {field_name} must not contain negative indices.")
        if index <= previous:
            raise DecisionError(f"Decision {field_name} must be unique and ascending.")
        previous = index
        validated.append(index)
    return tuple(validated)
