from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    D3RollResult,
    DiceExpression,
    DiceExpressionPayload,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSource,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollSpecPayload,
    DiceRollState,
    RandomCharacteristicRoll,
    RandomCharacteristicTiming,
    RerollDecisionRequest,
    RerollPermission,
    RerollPermissionPayload,
    RerollSelection,
    RollOffPlayerRoll,
    RollOffRequest,
    RollOffResult,
    RollOffRound,
)
from warhammer40k_core.core.rng import RandomSource
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value

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


def _new_random_move_characteristic_rolls() -> dict[
    tuple[str, Characteristic],
    RandomCharacteristicRoll,
]:
    return {}


@dataclass(slots=True)
class DiceRollManager:
    rng: RandomSource
    event_log: EventLog
    _injected_results: deque[DiceRollResult] = field(default_factory=_new_injected_results)
    _decision_records: list[DecisionRecord] = field(default_factory=_new_decision_records)
    _random_move_characteristic_rolls: dict[
        tuple[str, Characteristic],
        RandomCharacteristicRoll,
    ] = field(default_factory=_new_random_move_characteristic_rolls)
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
        self._random_move_characteristic_rolls = {}
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

    def roll_d3(self, *, reason: str, roll_type: str, actor_id: str | None = None) -> D3RollResult:
        state = self.roll(
            self.d3_source_spec(reason=reason, roll_type=roll_type, actor_id=actor_id)
        )
        result = D3RollResult.from_source_d6_result(state.original_result)
        self._record_d3_result(result)
        return result

    def roll_d3_fixed(
        self,
        *,
        reason: str,
        roll_type: str,
        source_d6_value: int,
        actor_id: str | None = None,
    ) -> D3RollResult:
        state = self.roll_fixed(
            self.d3_source_spec(reason=reason, roll_type=roll_type, actor_id=actor_id),
            [source_d6_value],
        )
        result = D3RollResult.from_source_d6_result(state.original_result)
        self._record_d3_result(result)
        return result

    @staticmethod
    def d3_source_spec(
        *,
        reason: str,
        roll_type: str,
        actor_id: str | None = None,
    ) -> DiceRollSpec:
        return DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"D3 source D6 for {reason}",
            roll_type=f"{roll_type}.d3_source",
            actor_id=actor_id,
        )

    def roll_off(self, request: RollOffRequest) -> RollOffResult:
        if type(request) is not RollOffRequest:
            raise DiceRollSpecError("Roll-off requires a RollOffRequest.")
        rounds: list[RollOffRound] = []
        while True:
            round_number = len(rounds) + 1
            player_rolls: list[RollOffPlayerRoll] = []
            for player_id in request.player_ids:
                state = self.roll(
                    self.roll_off_spec(
                        request,
                        round_number=round_number,
                        player_id=player_id,
                    )
                )
                player_rolls.append(
                    RollOffPlayerRoll(
                        player_id=player_id,
                        roll_result=state.original_result,
                        value=state.current_total,
                    )
                )
            round_result = RollOffRound(
                round_number=round_number,
                player_rolls=tuple(player_rolls),
            )
            rounds.append(round_result)
            if not round_result.is_tie:
                winner = round_result.winner_player_id
                if winner is None:
                    raise DiceRollSpecError("Roll-off winner could not be resolved.")
                result = RollOffResult(
                    request=request,
                    rounds=tuple(rounds),
                    winner_player_id=winner,
                )
                event = self.event_log.append("roll_off_resolved", result.to_payload())
                self.rng.append_history(event.history_token())
                return result

    @staticmethod
    def roll_off_spec(
        request: RollOffRequest,
        *,
        round_number: int,
        player_id: str,
    ) -> DiceRollSpec:
        if type(request) is not RollOffRequest:
            raise DiceRollSpecError("Roll-off spec requires a RollOffRequest.")
        if player_id not in request.player_ids:
            raise DiceRollSpecError("Roll-off spec player_id must be in the request.")
        if type(round_number) is not int:
            raise DiceRollSpecError("Roll-off round_number must be an integer.")
        if round_number < 1:
            raise DiceRollSpecError("Roll-off round_number must be at least 1.")
        return DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Roll-off {request.purpose} round {round_number} for {player_id}",
            roll_type="roll_off",
            actor_id=player_id,
        )

    def roll_random_characteristic(
        self,
        *,
        characteristic: Characteristic,
        timing: RandomCharacteristicTiming,
        scope_id: str,
        expression: DiceExpression,
        reason: str,
        actor_id: str | None = None,
    ) -> RandomCharacteristicRoll:
        timing = _random_characteristic_timing(timing)
        cached = self._random_move_characteristic_roll(characteristic, timing, scope_id)
        if cached is not None:
            return cached
        state = self.roll(
            _random_characteristic_spec(
                characteristic=characteristic,
                timing=timing,
                scope_id=scope_id,
                expression=expression,
                reason=reason,
                actor_id=actor_id,
            )
        )
        return self._record_random_characteristic_roll(
            characteristic=characteristic,
            timing=timing,
            scope_id=scope_id,
            roll_state=state,
        )

    def roll_random_characteristic_fixed(
        self,
        *,
        characteristic: Characteristic,
        timing: RandomCharacteristicTiming,
        scope_id: str,
        expression: DiceExpression,
        reason: str,
        values: Iterable[int],
        actor_id: str | None = None,
    ) -> RandomCharacteristicRoll:
        timing = _random_characteristic_timing(timing)
        cached = self._random_move_characteristic_roll(characteristic, timing, scope_id)
        if cached is not None:
            return cached
        state = self.roll_fixed(
            _random_characteristic_spec(
                characteristic=characteristic,
                timing=timing,
                scope_id=scope_id,
                expression=expression,
                reason=reason,
                actor_id=actor_id,
            ),
            values,
        )
        return self._record_random_characteristic_roll(
            characteristic=characteristic,
            timing=timing,
            scope_id=scope_id,
            roll_state=state,
        )

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
        allowed_selections: Iterable[Iterable[int]] | None = None,
        permission: RerollPermission | None = None,
    ) -> DecisionRequest:
        if state.original_result.spec.roll_type == "roll_off":
            raise DecisionError("Roll-off dice cannot be rerolled.")
        if permission is not None:
            if allowed_selections is not None:
                raise DecisionError("Reroll request must use permission or selections, not both.")
            reroll_request = RerollDecisionRequest.from_state(state, permission)
            selections = reroll_request.allowed_selections
            permission_payload: JsonValue = validate_json_value(permission.to_payload())
        else:
            if allowed_selections is None:
                raise DecisionError("Reroll request requires allowed selections or permission.")
            selections = _validate_index_selections(allowed_selections, state=state)
            permission_payload = None

        self._decision_request_counter += 1
        payload: dict[str, JsonValue] = {
            "roll_id": state.original_result.roll_id,
            "roll_type": state.original_result.spec.roll_type,
            "allowed_selections": [list(selection) for selection in selections],
            "current_values": list(state.current_values),
        }
        if permission_payload is not None:
            payload["permission"] = permission_payload
        request = DecisionRequest(
            request_id=f"decision-request-{self._decision_request_counter:06d}",
            decision_type="select_dice_reroll",
            actor_id=state.original_result.spec.actor_id,
            payload=payload,
            options=_reroll_options(selections),
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

    def _record_d3_result(self, result: D3RollResult) -> None:
        event = self.event_log.append("d3_roll_resolved", result.to_payload())
        self.rng.append_history(event.history_token())

    def _random_move_characteristic_roll(
        self,
        characteristic: Characteristic,
        timing: RandomCharacteristicTiming,
        scope_id: str,
    ) -> RandomCharacteristicRoll | None:
        if (
            characteristic is not Characteristic.MOVEMENT
            or timing is not RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
        ):
            return None
        return self._random_move_characteristic_rolls.get((scope_id, characteristic))

    def _record_random_characteristic_roll(
        self,
        *,
        characteristic: Characteristic,
        timing: RandomCharacteristicTiming,
        scope_id: str,
        roll_state: DiceRollState,
    ) -> RandomCharacteristicRoll:
        result = RandomCharacteristicRoll(
            characteristic=characteristic,
            timing=timing,
            scope_id=scope_id,
            roll_state=roll_state,
            value=roll_state.current_total,
        )
        if (
            characteristic is Characteristic.MOVEMENT
            and timing is RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
        ):
            self._random_move_characteristic_rolls[(scope_id, characteristic)] = result
        event = self.event_log.append("random_characteristic_rolled", result.to_payload())
        self.rng.append_history(event.history_token())
        return result

    def _next_roll_id(self) -> str:
        self._roll_counter += 1
        return f"roll-{self._roll_counter:06d}"

    def _seed_existing_event_history(self) -> None:
        for event in self.event_log.records:
            if event.event_type == "decision_requested":
                request = DecisionRequest.from_payload(cast(DecisionRequestPayload, event.payload))
                self._decision_request_counter += 1
                self.rng.append_history(request.history_token())
                self.rng.append_history(event.history_token())
                continue

            if event.event_type == "decision_recorded":
                record = DecisionRecord.from_payload(cast(DecisionRecordPayload, event.payload))
                expected_record_id = f"decision-record-{len(self._decision_records) + 1:06d}"
                if record.record_id != expected_record_id:
                    raise DecisionError("Decision records must be sequential.")
                self._decision_records.append(record)
                self.rng.append_history(record.history_token())
                self.rng.append_history(event.history_token())
                continue

            self.rng.append_history(event.history_token())
            if event.event_type == "dice_rolled":
                self._roll_counter += 1
                self.rng.draw_count += _restored_rng_draw_count(event.payload)

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
        allowed_selections = set(
            _extract_index_selections(request.payload, key="allowed_selections")
        )
        selected_indices = _extract_index_list(result.payload, key="selected_indices")
        if selected_indices and selected_indices not in allowed_selections:
            raise DecisionError("Reroll selected_indices must match an allowed selection.")
        permission_payload = _extract_optional_object(request.payload, key="permission")
        if permission_payload is not None and selected_indices:
            permission = RerollPermission.from_payload(
                _reroll_permission_payload(permission_payload)
            )
            try:
                permission.validate_selection(state, RerollSelection(indices=selected_indices))
            except DiceRollSpecError as exc:
                raise DecisionError("Reroll selected_indices violate permission.") from exc


def _coerce_result(result: DiceRollResult | DiceRollResultPayload) -> DiceRollResult:
    if isinstance(result, DiceRollResult):
        return result
    return DiceRollResult.from_payload(result)


def _random_characteristic_timing(timing: object) -> RandomCharacteristicTiming:
    if type(timing) is RandomCharacteristicTiming:
        return timing
    if type(timing) is not str:
        raise DiceRollSpecError("Random characteristic timing must be a token.")
    try:
        return RandomCharacteristicTiming(timing)
    except ValueError as exc:
        raise DiceRollSpecError(f"Unsupported random characteristic timing: {timing}.") from exc


def _random_characteristic_spec(
    *,
    characteristic: Characteristic,
    timing: RandomCharacteristicTiming,
    scope_id: str,
    expression: DiceExpression,
    reason: str,
    actor_id: str | None,
) -> DiceRollSpec:
    if type(characteristic) is not Characteristic:
        raise DiceRollSpecError("Random characteristic requires a Characteristic.")
    if type(timing) is not RandomCharacteristicTiming:
        raise DiceRollSpecError("Random characteristic requires a RandomCharacteristicTiming.")
    if type(expression) is not DiceExpression:
        raise DiceRollSpecError("Random characteristic requires a DiceExpression.")
    if type(scope_id) is not str or not scope_id.strip():
        raise DiceRollSpecError("Random characteristic scope_id must not be empty.")
    return DiceRollSpec(
        expression=expression,
        reason=reason,
        roll_type=f"random_characteristic.{characteristic.value}.{timing.value}.{scope_id}",
        actor_id=actor_id,
    )


def _reroll_options(selections: tuple[tuple[int, ...], ...]) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = [
        DecisionOption(
            option_id="decline",
            label="Decline reroll",
            payload={"selected_indices": []},
        )
    ]
    for selection in selections:
        selected_label = ",".join(str(index) for index in selection)
        options.append(
            DecisionOption(
                option_id=f"reroll:{selected_label}",
                label=f"Reroll dice {selected_label}",
                payload={"selected_indices": list(selection)},
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


def _extract_index_selections(payload: JsonValue, *, key: str) -> tuple[tuple[int, ...], ...]:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise DecisionError(f"Decision payload key must be an index selection list: {key}.")

    selections: list[tuple[int, ...]] = []
    for selection in value:
        if not isinstance(selection, list):
            raise DecisionError(f"Decision payload key must contain index lists: {key}.")
        selections.append(_validate_index_list(tuple(selection), field_name=key))
    return _validate_unique_index_selections(tuple(selections), field_name=key)


def _reroll_permission_payload(payload: dict[str, JsonValue]) -> RerollPermissionPayload:
    return {
        "source_id": _extract_string(payload, key="source_id"),
        "timing_window": _extract_string(payload, key="timing_window"),
        "owning_player_id": _extract_string(payload, key="owning_player_id"),
        "eligible_roll_type": _extract_string(payload, key="eligible_roll_type"),
        "component_selection_policy": _extract_string(payload, key="component_selection_policy"),
        "allowed_component_selections": _optional_index_selection_payload(
            payload,
            key="allowed_component_selections",
        ),
    }


def _optional_index_selection_payload(
    payload: JsonValue,
    *,
    key: str,
) -> list[list[int]] | None:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, list):
        raise DecisionError(f"Decision payload key must be an index selection list: {key}.")
    selections: list[list[int]] = []
    for selection in value:
        if not isinstance(selection, list):
            raise DecisionError(f"Decision payload key must contain index lists: {key}.")
        selections.append(list(_validate_index_list(tuple(selection), field_name=key)))
    return selections


def _extract_object(payload: JsonValue, *, key: str) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        raise DecisionError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise DecisionError(f"Decision payload key must be an object: {key}.")
    return value


def _extract_optional_object(payload: JsonValue, *, key: str) -> dict[str, JsonValue] | None:
    if not isinstance(payload, dict):
        raise DecisionError("Decision payload must be an object.")
    if key not in payload:
        return None
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DecisionError(f"Decision payload key must be an object or null: {key}.")
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


def _validate_index_selections(
    selections: Iterable[Iterable[int]],
    *,
    state: DiceRollState,
) -> tuple[tuple[int, ...], ...]:
    selection_values = cast(object, selections)
    if not isinstance(selection_values, Iterable):
        raise DecisionError("Reroll allowed_selections must be iterable.")

    validated: list[tuple[int, ...]] = []
    for selection in cast(Iterable[object], selection_values):
        if not isinstance(selection, Iterable):
            raise DecisionError("Reroll allowed_selections must contain iterable selections.")
        index_selection = _validate_index_list(
            tuple(cast(Iterable[object], selection)),
            field_name="allowed_selections",
        )
        for index in index_selection:
            if index >= len(state.current_values):
                raise DecisionError("Reroll allowed selection index is outside the current dice.")
        validated.append(index_selection)
    return _validate_unique_index_selections(tuple(validated), field_name="allowed_selections")


def _validate_unique_index_selections(
    selections: tuple[tuple[int, ...], ...],
    *,
    field_name: str,
) -> tuple[tuple[int, ...], ...]:
    if not selections:
        raise DecisionError(f"Decision {field_name} must not be empty.")

    seen: set[tuple[int, ...]] = set()
    for selection in selections:
        if not selection:
            raise DecisionError(f"Decision {field_name} must not contain empty selections.")
        if selection in seen:
            raise DecisionError(f"Decision {field_name} must not contain duplicate selections.")
        seen.add(selection)
    return tuple(sorted(selections))


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
