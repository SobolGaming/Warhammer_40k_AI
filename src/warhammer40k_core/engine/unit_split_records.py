"""Persistent, closed membership records for the once-only unit split operation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attached_unit_formation import (
    AttachedUnitFormation,
    AttachedUnitFormationPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance, UnitInstancePayload
from warhammer40k_core.engine.unit_ownership import SplitUnitOrigin


class UnitSplitRecordPayload(TypedDict):
    request_id: str
    source_id: str
    source_unit_instance_id: str
    source_units: list[UnitInstancePayload]
    source_formation: AttachedUnitFormationPayload | None
    first_model_ids: list[str]
    specified_strengths: list[int] | None


@dataclass(frozen=True, slots=True)
class UnitSplitRecord:
    request_id: str
    source_id: str
    source_unit_instance_id: str
    source_units: tuple[UnitInstance, ...]
    source_formation: AttachedUnitFormation | None
    first_model_ids: tuple[str, ...]
    specified_strengths: tuple[int, int] | None

    def __post_init__(self) -> None:
        validate = IdentifierValidator(GameLifecycleError)
        for name in ("request_id", "source_id", "source_unit_instance_id"):
            # These identifiers are explicit inputs, never inferred from display text.
            validate(
                name,
                {
                    "request_id": self.request_id,
                    "source_id": self.source_id,
                    "source_unit_instance_id": self.source_unit_instance_id,
                }[name],
            )
        if type(self.source_units) is not tuple or not self.source_units:
            raise GameLifecycleError("Unit split requires source components.")
        if any(type(unit) is not UnitInstance for unit in self.source_units):
            raise GameLifecycleError("Unit split requires typed source components.")
        if any(unit.split_origin is not None for unit in self.source_units):
            raise GameLifecycleError("These models have already been split.")
        component_ids = tuple(unit.unit_instance_id for unit in self.source_units)
        if len(set(component_ids)) != len(component_ids):
            raise GameLifecycleError("Unit split source components must be unique.")
        if self.source_formation is None:
            if component_ids != (self.source_unit_instance_id,):
                raise GameLifecycleError("Single-unit split source identity drift.")
        elif type(self.source_formation) is not AttachedUnitFormation or (
            self.source_formation.attached_unit_instance_id != self.source_unit_instance_id
            or set(self.source_formation.component_unit_instance_ids) != set(component_ids)
        ):
            raise GameLifecycleError("Attached-unit split source lineage drift.")
        model_ids = tuple(model for unit in self.source_units for model in unit.own_model_ids())
        if len(set(model_ids)) != len(model_ids):
            raise GameLifecycleError("Unit split source model identities overlap.")
        if type(self.first_model_ids) is not tuple or any(
            type(value) is not str for value in self.first_model_ids
        ):
            raise GameLifecycleError("Unit split membership must contain model identifiers.")
        if len(set(self.first_model_ids)) != len(self.first_model_ids):
            raise GameLifecycleError("Unit split membership repeats a model.")
        if not set(self.first_model_ids).issubset(model_ids):
            raise GameLifecycleError("Unit split membership contains a foreign model.")
        if not self.first_model_ids or len(self.first_model_ids) == len(model_ids):
            raise GameLifecycleError("Unit split requires two nonempty successors.")
        object.__setattr__(self, "first_model_ids", tuple(sorted(self.first_model_ids)))
        if self.specified_strengths is not None and (
            type(self.specified_strengths) is not tuple
            or len(self.specified_strengths) != 2
            or any(type(value) is not int or value < 1 for value in self.specified_strengths)
        ):
            raise GameLifecycleError(
                "Unit split specified strengths require two positive integers."
            )
        counts = (len(self.first_model_ids), len(model_ids) - len(self.first_model_ids))
        feasible = self.specified_strengths is not None and sum(self.specified_strengths) == len(
            model_ids
        )
        if feasible:
            if counts != self.specified_strengths:
                raise GameLifecycleError("Unit split membership violates specified strengths.")
        elif abs(counts[0] - counts[1]) > 1:
            raise GameLifecycleError("Unit split membership must be as equal as possible.")

    @property
    def split_id(self) -> str:
        digest = hashlib.sha256(self.request_id.encode()).hexdigest()
        return f"unit-split:{digest}"

    @property
    def used_balanced_fallback(self) -> bool:
        return self.specified_strengths is not None and sum(self.specified_strengths) != sum(
            len(unit.own_models) for unit in self.source_units
        )

    def model_ids(self, successor_index: int) -> tuple[str, ...]:
        if type(successor_index) is not int or successor_index not in (0, 1):
            raise GameLifecycleError("Unit split successor must be 0 or 1.")
        if successor_index == 0:
            return self.first_model_ids
        return tuple(
            sorted(
                model_id
                for unit in self.source_units
                for model_id in unit.own_model_ids()
                if model_id not in self.first_model_ids
            )
        )

    def component_origins(self, successor_index: int) -> tuple[SplitUnitOrigin, ...]:
        models = set(self.model_ids(successor_index))
        return tuple(
            SplitUnitOrigin(unit.unit_instance_id, self.split_id, successor_index)
            for unit in self.source_units
            if models.intersection(unit.own_model_ids())
        )

    def successor_id(self, successor_index: int) -> str:
        origins = self.component_origins(successor_index)
        if len(origins) == 1:
            return origins[0].unit_instance_id
        digest = self.split_id.removeprefix("unit-split:")
        return f"{self.source_unit_instance_id}:split:{digest}:{successor_index}"

    def to_payload(self) -> UnitSplitRecordPayload:
        return {
            "request_id": self.request_id,
            "source_id": self.source_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "source_units": [unit.to_payload() for unit in self.source_units],
            "source_formation": None
            if self.source_formation is None
            else self.source_formation.to_payload(),
            "first_model_ids": list(self.first_model_ids),
            "specified_strengths": None
            if self.specified_strengths is None
            else list(self.specified_strengths),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict or set(cast(dict[str, object], payload)) != {
            "request_id",
            "source_id",
            "source_unit_instance_id",
            "source_units",
            "source_formation",
            "first_model_ids",
            "specified_strengths",
        }:
            raise GameLifecycleError("Unit split requires its exact closed payload.")
        raw = cast(UnitSplitRecordPayload, payload)
        if type(raw["source_units"]) is not list or type(raw["first_model_ids"]) is not list:
            raise GameLifecycleError("Unit split payload membership must use arrays.")
        strengths = raw["specified_strengths"]
        if strengths is not None and (type(strengths) is not list or len(strengths) != 2):
            raise GameLifecycleError("Unit split strength payload requires two values.")
        return cls(
            request_id=raw["request_id"],
            source_id=raw["source_id"],
            source_unit_instance_id=raw["source_unit_instance_id"],
            source_units=tuple(UnitInstance.from_payload(unit) for unit in raw["source_units"]),
            source_formation=(
                None
                if raw["source_formation"] is None
                else AttachedUnitFormation.from_payload(raw["source_formation"])
            ),
            first_model_ids=tuple(raw["first_model_ids"]),
            specified_strengths=None if strengths is None else (strengths[0], strengths[1]),
        )


def validate_army_split_lineage(
    *, units: tuple[UnitInstance, ...], records: tuple[UnitSplitRecord, ...]
) -> None:
    if type(records) is not tuple or any(type(row) is not UnitSplitRecord for row in records):
        raise GameLifecycleError("Army unit split lineage must contain typed records.")
    origins: dict[str, tuple[UnitSplitRecord, SplitUnitOrigin]] = {}
    source_model_ids: set[str] = set()
    split_ids: set[str] = set()
    for record in records:
        if record.split_id in split_ids:
            raise GameLifecycleError("Army unit split lineage repeats a decision.")
        split_ids.add(record.split_id)
        for unit in record.source_units:
            if source_model_ids.intersection(unit.own_model_ids()):
                raise GameLifecycleError("Army unit split lineage subdivides models again.")
            source_model_ids.update(unit.own_model_ids())
        for index in (0, 1):
            for origin in record.component_origins(index):
                origins[origin.unit_instance_id] = (record, origin)
    observed: set[str] = set()
    models: set[str] = set()
    for unit in units:
        if models.intersection(unit.own_model_ids()):
            raise GameLifecycleError("Army physical model membership overlaps.")
        models.update(unit.own_model_ids())
        if unit.split_origin is None:
            if source_model_ids.intersection(unit.own_model_ids()):
                raise GameLifecycleError("Retired split models still have their original owner.")
            continue
        evidence = origins.get(unit.unit_instance_id)
        if evidence is None or evidence[1] != unit.split_origin:
            raise GameLifecycleError("Physical split component lacks exact split lineage.")
        record, origin = evidence
        source = next(
            row
            for row in record.source_units
            if row.unit_instance_id == origin.source_unit_instance_id
        )
        expected_ids = set(source.own_model_ids()).intersection(
            record.model_ids(origin.successor_index)
        )
        if set(unit.own_model_ids()) != expected_ids:
            raise GameLifecycleError("Physical split membership drifted from the recorded choice.")
        if unit.datasheet_id != source.datasheet_id:
            raise GameLifecycleError("Physical split component datasheet drift.")
        observed.add(unit.unit_instance_id)
    if observed != set(origins):
        raise GameLifecycleError("Army is missing a recorded split successor component.")
