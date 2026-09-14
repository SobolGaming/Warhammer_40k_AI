from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Self, TypedDict, cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_MOVE_PENDING_STATUS,
    ChargeDistanceState,
    ChargeDistanceStatePayload,
    ChargeRollResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError

_validate_identifier = IdentifierValidator(GameLifecycleError)


def _empty_declared_charge_targets() -> dict[str, tuple[str, ...]]:
    return {}


class ChargingUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class ChargeTargetSelection(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    request_id: str
    result_id: str
    unit_instance_id: str
    target_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("request_id", "result_id", "unit_instance_id"):
            _validate_identifier(field_name, getattr(self, field_name))
        targets = _validate_identifier_tuple("target_ids", self.target_ids)
        if not targets or targets != tuple(sorted(targets)):
            raise GameLifecycleError("Charge targets must be a nonempty canonical rules-unit set.")

    def to_payload(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "unit_instance_id": self.unit_instance_id,
            "target_ids": list(self.target_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> ChargeTargetSelection:
        try:
            return msgspec.convert(payload, type=cls, strict=True)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Charge target selection payload is invalid.") from exc


class ChargePhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    phase_complete: bool
    selected_unit_ids: list[str]
    active_selection: ChargingUnitSelectionPayload | None
    distance_states: list[ChargeDistanceStatePayload]
    target_selection: dict[str, object] | None
    declared_target_unit_instance_ids_by_unit: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class ChargingUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargingUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargingUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargingUnitSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ChargingUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ChargingUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> ChargingUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ChargingUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseState:
    battle_round: int
    active_player_id: str
    phase_complete: bool = False
    selected_unit_ids: tuple[str, ...] = ()
    active_selection: ChargingUnitSelection | None = None
    distance_states: tuple[ChargeDistanceState, ...] = ()
    target_selection: ChargeTargetSelection | None = None
    declared_target_unit_instance_ids_by_unit: dict[str, tuple[str, ...]] = field(
        default_factory=_empty_declared_charge_targets
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargePhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("ChargePhaseState active_player_id", self.active_player_id),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("ChargePhaseState phase_complete must be a bool.")
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "ChargePhaseState selected_unit_ids", self.selected_unit_ids
            ),
        )
        if self.active_selection is not None:
            if type(self.active_selection) is not ChargingUnitSelection:
                raise GameLifecycleError(
                    "ChargePhaseState active_selection must be ChargingUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError("Charge active_selection active player drift.")
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError("Charge active_selection battle round drift.")
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError("Charge active_selection must be selected.")
        object.__setattr__(
            self,
            "distance_states",
            _validate_charge_distance_states(self.distance_states),
        )
        object.__setattr__(
            self,
            "declared_target_unit_instance_ids_by_unit",
            _validate_charge_declared_target_map(self.declared_target_unit_instance_ids_by_unit),
        )
        if self.target_selection is not None and (
            type(self.target_selection) is not ChargeTargetSelection
            or self.active_selection is None
            or self.target_selection.unit_instance_id != self.active_selection.unit_instance_id
            or self.move_pending_distance_state() is None
        ):
            raise GameLifecycleError("Charge target selection requires its pending rolled action.")
        if self.phase_complete and self.active_selection is not None:
            raise GameLifecycleError("Completed Charge phase cannot have active_selection.")
        if self.phase_complete and self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Completed Charge phase cannot have pending charge movement.")

    def with_unit_selection(self, selection: ChargingUnitSelection) -> Self:
        if type(selection) is not ChargingUnitSelection:
            raise GameLifecycleError("Charge selection must be ChargingUnitSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a charging unit after phase completion.")
        if self.active_selection is not None:
            raise GameLifecycleError("Charge unit selection requires no active selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Charge selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Charge selection battle round drift.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Charge unit was already selected.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            active_selection=selection,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def with_charge_roll_result(self, roll_result: ChargeRollResult) -> Self:
        if type(roll_result) is not ChargeRollResult:
            raise GameLifecycleError("Charge roll result must be ChargeRollResult.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot record a charge roll after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Charge roll requires active_selection.")
        if roll_result.request.player_id != self.active_player_id:
            raise GameLifecycleError("Charge roll player drift.")
        if roll_result.request.battle_round != self.battle_round:
            raise GameLifecycleError("Charge roll battle round drift.")
        if roll_result.request.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Charge roll unit drift.")
        distance_state = ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id=roll_result.request.source_decision_request_id,
            source_decision_result_id=roll_result.request.source_decision_result_id,
        )
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            active_selection=self.active_selection if roll_result.move_available else None,
            distance_states=(*self.distance_states, distance_state),
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def with_target_selection(self, selection: ChargeTargetSelection) -> Self:
        return replace(self, target_selection=selection)

    def with_charge_move_resolved(
        self,
        unit_instance_id: str,
        *,
        selected_target_unit_instance_ids: tuple[str, ...] = (),
    ) -> Self:
        resolved_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        target_ids = _validate_identifier_tuple(
            "selected_target_unit_instance_ids",
            selected_target_unit_instance_ids,
        )
        if self.phase_complete:
            raise GameLifecycleError("Cannot resolve a charge move after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Charge move resolution requires active_selection.")
        if self.active_selection.unit_instance_id != resolved_unit_id:
            raise GameLifecycleError("Charge move resolution unit drift.")
        if self.move_pending_distance_state() is None:
            raise GameLifecycleError("Charge move resolution requires pending distance state.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            active_selection=None,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit={
                **self.declared_target_unit_instance_ids_by_unit,
                resolved_unit_id: target_ids,
            },
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Charge completion requires no active selection.")
        if self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Charge completion requires no pending charge movement.")
        skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=True,
            selected_unit_ids=tuple(sorted({*self.selected_unit_ids, *skipped_ids})),
            active_selection=None,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def move_pending_distance_state(self) -> ChargeDistanceState | None:
        if self.active_selection is None:
            return None
        for distance_state in reversed(self.distance_states):
            if (
                distance_state.roll_result.request.unit_instance_id
                == self.active_selection.unit_instance_id
                and distance_state.roll_result.status == CHARGE_MOVE_PENDING_STATUS
            ):
                return distance_state
        return None

    def to_payload(self) -> ChargePhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase_complete": self.phase_complete,
            "selected_unit_ids": list(self.selected_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "distance_states": [distance.to_payload() for distance in self.distance_states],
            "target_selection": None
            if self.target_selection is None
            else self.target_selection.to_payload(),
            "declared_target_unit_instance_ids_by_unit": {
                unit_id: list(target_ids)
                for unit_id, target_ids in sorted(
                    self.declared_target_unit_instance_ids_by_unit.items()
                )
            },
        }

    @classmethod
    def from_payload(cls, payload: ChargePhaseStatePayload) -> Self:
        selection_payload = payload["active_selection"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase_complete=payload["phase_complete"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            active_selection=(
                None
                if selection_payload is None
                else ChargingUnitSelection.from_payload(selection_payload)
            ),
            target_selection=None
            if payload["target_selection"] is None
            else ChargeTargetSelection.from_payload(payload["target_selection"]),
            distance_states=tuple(
                ChargeDistanceState.from_payload(distance)
                for distance in payload["distance_states"]
            ),
            declared_target_unit_instance_ids_by_unit={
                unit_id: tuple(target_ids)
                for unit_id, target_ids in payload[
                    "declared_target_unit_instance_ids_by_unit"
                ].items()
            },
        )


def _validate_charge_distance_states(values: object) -> tuple[ChargeDistanceState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ChargePhaseState distance_states must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    states: list[ChargeDistanceState] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ChargeDistanceState:
            raise GameLifecycleError(
                "ChargePhaseState distance_states must contain ChargeDistanceState."
            )
        result_id = value.source_decision_result_id
        if result_id in seen:
            raise GameLifecycleError("ChargePhaseState distance_states duplicate result_id.")
        seen.add(result_id)
        states.append(value)
    return tuple(states)


def _validate_charge_declared_target_map(values: object) -> dict[str, tuple[str, ...]]:
    if type(values) is not dict:
        raise GameLifecycleError(
            "ChargePhaseState declared_target_unit_instance_ids_by_unit must be a dict."
        )
    validated: dict[str, tuple[str, ...]] = {}
    for raw_unit_id, raw_target_ids in cast(dict[object, object], values).items():
        unit_id = _validate_identifier("declared target unit id", raw_unit_id)
        if unit_id in validated:
            raise GameLifecycleError("ChargePhaseState declared target map duplicates unit IDs.")
        if type(raw_target_ids) is not tuple:
            raise GameLifecycleError("ChargePhaseState declared target map values must be tuples.")
        validated[unit_id] = _validate_identifier_tuple(
            "declared target unit ids",
            cast(tuple[object, ...], raw_target_ids),
        )
    return dict(sorted(validated.items()))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value
