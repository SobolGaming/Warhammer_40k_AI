from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

_validate_identifier = IdentifierValidator(GameLifecycleError)


class SecondaryMissionSelectionPayload(TypedDict):
    tempting_objective_id: str | None
    beacon_unit_instance_id: str | None
    guarded_objective_unit_ids: list[list[str]]
    resolved_guard_objective_ids: list[str]
    when_drawn_resolved: bool
    guard_selection_battle_round: int | None
    resolved_objective_control_record_ids: list[str]


@dataclass(frozen=True, slots=True)
class SecondaryMissionSelection:
    tempting_objective_id: str | None = None
    beacon_unit_instance_id: str | None = None
    guarded_objective_unit_ids: tuple[tuple[str, str], ...] = ()
    resolved_guard_objective_ids: tuple[str, ...] = ()
    when_drawn_resolved: bool = False
    guard_selection_battle_round: int | None = None
    resolved_objective_control_record_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tempting_objective_id",
            _validate_optional_identifier("tempting_objective_id", self.tempting_objective_id),
        )
        object.__setattr__(
            self,
            "beacon_unit_instance_id",
            _validate_optional_identifier(
                "beacon_unit_instance_id",
                self.beacon_unit_instance_id,
            ),
        )
        bindings = _validate_guard_bindings(self.guarded_objective_unit_ids)
        object.__setattr__(self, "guarded_objective_unit_ids", bindings)
        object.__setattr__(
            self,
            "resolved_guard_objective_ids",
            _validate_identifier_tuple(
                "resolved_guard_objective_ids",
                self.resolved_guard_objective_ids,
            ),
        )
        if type(self.when_drawn_resolved) is not bool:
            raise GameLifecycleError("when_drawn_resolved must be a bool.")
        if self.guard_selection_battle_round is not None and (
            type(self.guard_selection_battle_round) is not int
            or self.guard_selection_battle_round <= 0
        ):
            raise GameLifecycleError("guard_selection_battle_round must be a positive int.")
        object.__setattr__(
            self,
            "resolved_objective_control_record_ids",
            _validate_identifier_tuple(
                "resolved_objective_control_record_ids",
                self.resolved_objective_control_record_ids,
            ),
        )

    def to_payload(self) -> SecondaryMissionSelectionPayload:
        return {
            "tempting_objective_id": self.tempting_objective_id,
            "beacon_unit_instance_id": self.beacon_unit_instance_id,
            "guarded_objective_unit_ids": [
                [objective_id, unit_id] for objective_id, unit_id in self.guarded_objective_unit_ids
            ],
            "resolved_guard_objective_ids": list(self.resolved_guard_objective_ids),
            "when_drawn_resolved": self.when_drawn_resolved,
            "guard_selection_battle_round": self.guard_selection_battle_round,
            "resolved_objective_control_record_ids": list(
                self.resolved_objective_control_record_ids
            ),
        }

    def to_json_value(self) -> JsonValue:
        return validate_json_value(self.to_payload())

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise GameLifecycleError("SecondaryMissionSelection payload must be an object.")
        raw = cast(dict[str, object], payload)
        required = (
            "tempting_objective_id",
            "beacon_unit_instance_id",
            "guarded_objective_unit_ids",
            "resolved_guard_objective_ids",
            "when_drawn_resolved",
            "guard_selection_battle_round",
            "resolved_objective_control_record_ids",
        )
        missing = tuple(key for key in required if key not in raw)
        if missing:
            raise GameLifecycleError("SecondaryMissionSelection payload is missing required keys.")
        raw_bindings = raw["guarded_objective_unit_ids"]
        if type(raw_bindings) is not list:
            raise GameLifecycleError("guarded_objective_unit_ids must be a list.")
        bindings: list[tuple[str, str]] = []
        for row in cast(list[object], raw_bindings):
            if type(row) is not list or len(cast(list[object], row)) != 2:
                raise GameLifecycleError("guarded_objective_unit_ids rows must be pairs.")
            pair = cast(list[object], row)
            bindings.append(
                (
                    _validate_identifier("objective_id", pair[0]),
                    _validate_identifier("unit_id", pair[1]),
                )
            )
        raw_resolved_guards = raw["resolved_guard_objective_ids"]
        if type(raw_resolved_guards) is not list:
            raise GameLifecycleError("resolved_guard_objective_ids must be a list.")
        raw_record_ids = raw["resolved_objective_control_record_ids"]
        if type(raw_record_ids) is not list:
            raise GameLifecycleError("resolved_objective_control_record_ids must be a list.")
        return cls(
            tempting_objective_id=_optional_identifier(raw["tempting_objective_id"]),
            beacon_unit_instance_id=_optional_identifier(raw["beacon_unit_instance_id"]),
            guarded_objective_unit_ids=tuple(bindings),
            resolved_guard_objective_ids=tuple(
                _validate_identifier("resolved_guard_objective_id", objective_id)
                for objective_id in cast(list[object], raw_resolved_guards)
            ),
            when_drawn_resolved=_validate_bool(raw["when_drawn_resolved"]),
            guard_selection_battle_round=_optional_positive_int(
                raw["guard_selection_battle_round"]
            ),
            resolved_objective_control_record_ids=tuple(
                _validate_identifier("resolved record_id", record_id)
                for record_id in cast(list[object], raw_record_ids)
            ),
        )

    def with_when_drawn_resolved(self) -> Self:
        return type(self)(
            tempting_objective_id=self.tempting_objective_id,
            beacon_unit_instance_id=self.beacon_unit_instance_id,
            guarded_objective_unit_ids=self.guarded_objective_unit_ids,
            resolved_guard_objective_ids=self.resolved_guard_objective_ids,
            when_drawn_resolved=True,
            guard_selection_battle_round=self.guard_selection_battle_round,
            resolved_objective_control_record_ids=self.resolved_objective_control_record_ids,
        )

    def with_tempting_objective(self, objective_id: str) -> Self:
        return type(self)(
            tempting_objective_id=_validate_identifier("tempting_objective_id", objective_id),
            beacon_unit_instance_id=self.beacon_unit_instance_id,
            guarded_objective_unit_ids=self.guarded_objective_unit_ids,
            resolved_guard_objective_ids=self.resolved_guard_objective_ids,
            when_drawn_resolved=True,
            guard_selection_battle_round=self.guard_selection_battle_round,
            resolved_objective_control_record_ids=self.resolved_objective_control_record_ids,
        )

    def with_beacon_unit(self, unit_instance_id: str) -> Self:
        return type(self)(
            tempting_objective_id=self.tempting_objective_id,
            beacon_unit_instance_id=_validate_identifier(
                "beacon_unit_instance_id",
                unit_instance_id,
            ),
            guarded_objective_unit_ids=self.guarded_objective_unit_ids,
            resolved_guard_objective_ids=self.resolved_guard_objective_ids,
            when_drawn_resolved=True,
            guard_selection_battle_round=self.guard_selection_battle_round,
            resolved_objective_control_record_ids=self.resolved_objective_control_record_ids,
        )

    def with_guards(
        self,
        *,
        guarded_objective_unit_ids: tuple[tuple[str, str], ...],
        resolved_guard_objective_ids: tuple[str, ...],
        battle_round: int,
    ) -> Self:
        return type(self)(
            tempting_objective_id=self.tempting_objective_id,
            beacon_unit_instance_id=self.beacon_unit_instance_id,
            guarded_objective_unit_ids=guarded_objective_unit_ids,
            resolved_guard_objective_ids=resolved_guard_objective_ids,
            when_drawn_resolved=True,
            guard_selection_battle_round=battle_round,
            resolved_objective_control_record_ids=self.resolved_objective_control_record_ids,
        )

    def with_resolved_record(self, record_id: str) -> Self:
        requested = _validate_identifier("objective_control_record_id", record_id)
        if requested in self.resolved_objective_control_record_ids:
            return self
        return type(self)(
            tempting_objective_id=self.tempting_objective_id,
            beacon_unit_instance_id=self.beacon_unit_instance_id,
            guarded_objective_unit_ids=self.guarded_objective_unit_ids,
            resolved_guard_objective_ids=self.resolved_guard_objective_ids,
            when_drawn_resolved=self.when_drawn_resolved,
            guard_selection_battle_round=self.guard_selection_battle_round,
            resolved_objective_control_record_ids=(
                *self.resolved_objective_control_record_ids,
                requested,
            ),
        )


def secondary_mission_selection_from_json(
    value: JsonValue | None,
) -> SecondaryMissionSelection | None:
    if value is None:
        return None
    return SecondaryMissionSelection.from_payload(value)


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _optional_identifier(value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier("optional identifier", value)


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise GameLifecycleError("optional positive int is invalid.")
    return value


def _validate_bool(value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError("SecondaryMissionSelection bool field is invalid.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


def _validate_guard_bindings(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("guarded_objective_unit_ids must be a tuple.")
    seen_objectives: set[str] = set()
    seen_units: set[str] = set()
    bindings: list[tuple[str, str]] = []
    for row in values:
        if type(row) is not tuple or len(row) != 2:
            raise GameLifecycleError("guarded_objective_unit_ids rows must be pairs.")
        objective_id = _validate_identifier("guarded objective_id", row[0])
        unit_id = _validate_identifier("guarded unit_id", row[1])
        if objective_id in seen_objectives:
            raise GameLifecycleError("A unit may guard only one binding per objective.")
        if unit_id in seen_units:
            raise GameLifecycleError("A unit may guard only one objective.")
        seen_objectives.add(objective_id)
        seen_units.add(unit_id)
        bindings.append((objective_id, unit_id))
    return tuple(sorted(bindings, key=lambda binding: (binding[0], binding[1])))
