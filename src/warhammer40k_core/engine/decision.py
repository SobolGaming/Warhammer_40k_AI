from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceExpressionPayload,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSource,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollSpecPayload,
    DiceRollState,
)
from warhammer40k_core.core.rng import RandomSource
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue

__all__ = [
    "DecisionError",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResult",
    "DiceRollManager",
]


def _new_injected_results() -> deque[DiceRollResult]:
    return deque()


def _new_decision_records() -> list[DecisionRecord]:
    return []


@dataclass(slots=True)
class DiceRollManager:
    rng: RandomSource
    event_log: EventLog
    _injected_results: deque[DiceRollResult] = field(default_factory=_new_injected_results)
    _decision_records: list[DecisionRecord] = field(default_factory=_new_decision_records)
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
    def decision_records(self) -> tuple[DecisionRecord, ...]:
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

    def record_decision(
        self,
        *,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> DecisionRecord:
        record = DecisionRecord(
            record_id=f"decision-record-{len(self._decision_records) + 1:06d}",
            request=request,
            result=result,
        )
        self._decision_records.append(record)
        self.rng.append_history(record.history_token())
        event = self.event_log.append("decision_recorded", record.to_payload())
        self.rng.append_history(event.history_token())
        return record

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
            options=_reroll_options(indices),
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
        self.record_decision(request=request, result=result)
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
                self.rng.draw_count += _restored_rng_draw_count(record.payload)
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
        result.validate_for_request(request)
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


def _reroll_options(indices: tuple[int, ...]) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = [
        DecisionOption(
            option_id="decline",
            label="Decline reroll",
            payload={"selected_indices": []},
        )
    ]
    for size in range(1, len(indices) + 1):
        for selected in combinations(indices, size):
            selected_label = ",".join(str(index) for index in selected)
            options.append(
                DecisionOption(
                    option_id=f"reroll:{selected_label}",
                    label=f"Reroll dice {selected_label}",
                    payload={"selected_indices": list(selected)},
                )
            )
    return tuple(options)


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


def _extract_object(payload: JsonValue, *, key: str) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise DecisionError(f"Decision payload key must be an object: {key}.")
    return value


def _extract_int(payload: JsonValue, *, key: str) -> int:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise DecisionError(f"Decision payload key must be an integer: {key}.")
    return value


def _extract_int_list(payload: JsonValue, *, key: str) -> tuple[int, ...]:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise DecisionError(f"Decision payload key must be an integer list: {key}.")

    validated: list[int] = []
    for item in value:
        if type(item) is not int:
            raise DecisionError(f"Decision payload key must contain integers: {key}.")
        validated.append(item)
    return tuple(validated)


def _dice_expression_payload(payload: JsonValue) -> DiceExpressionPayload:
    return {
        "quantity": _extract_int(payload, key="quantity"),
        "sides": _extract_int(payload, key="sides"),
        "modifier": _extract_int(payload, key="modifier"),
    }


def _dice_roll_spec_payload(payload: JsonValue) -> DiceRollSpecPayload:
    return {
        "expression": _dice_expression_payload(_extract_object(payload, key="expression")),
        "reason": _extract_string(payload, key="reason"),
        "roll_type": _extract_string(payload, key="roll_type"),
        "actor_id": _extract_optional_string(payload, key="actor_id"),
    }


def _dice_roll_result_from_payload(payload: JsonValue) -> DiceRollResult:
    return DiceRollResult.from_payload(
        {
            "roll_id": _extract_string(payload, key="roll_id"),
            "spec": _dice_roll_spec_payload(_extract_object(payload, key="spec")),
            "values": list(_extract_int_list(payload, key="values")),
            "total": _extract_int(payload, key="total"),
            "source": _dice_roll_source(payload),
        }
    )


def _dice_roll_source(payload: JsonValue) -> DiceRollSource:
    source = _extract_string(payload, key="source")
    if source == "rng":
        return "rng"
    if source == "fixed":
        return "fixed"
    if source == "injected":
        return "injected"
    raise DecisionError("dice_rolled event source must be rng, fixed, or injected.")


def _extract_optional_string(payload: JsonValue, *, key: str) -> str | None:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise DecisionError(f"Decision payload key must be a string or null: {key}.")
    return value


def _restored_rng_draw_count(payload: JsonValue) -> int:
    result = _dice_roll_result_from_payload(payload)
    return len(result.values) if result.source == "rng" else 0


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
