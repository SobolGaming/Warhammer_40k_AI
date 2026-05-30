from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance


class StartingStrengthRecordPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    starting_model_count: int
    single_model_starting_wounds: int | None
    source_id: str


class BelowHalfStrengthContextPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    starting_model_count: int
    current_model_count: int
    single_model_starting_wounds: int | None
    single_model_wounds_remaining: int | None
    is_below_starting_strength: bool
    is_below_half_strength: bool


@dataclass(frozen=True, slots=True)
class StartingStrengthRecord:
    player_id: str
    unit_instance_id: str
    starting_model_count: int
    single_model_starting_wounds: int | None
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StartingStrengthRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("StartingStrengthRecord unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "starting_model_count",
            _validate_positive_int(
                "StartingStrengthRecord starting_model_count",
                self.starting_model_count,
            ),
        )
        object.__setattr__(
            self,
            "single_model_starting_wounds",
            _validate_optional_positive_int(
                "StartingStrengthRecord single_model_starting_wounds",
                self.single_model_starting_wounds,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StartingStrengthRecord source_id", self.source_id),
        )
        if self.starting_model_count == 1 and self.single_model_starting_wounds is None:
            raise GameLifecycleError(
                "Single-model StartingStrengthRecord requires starting wounds."
            )
        if self.starting_model_count > 1 and self.single_model_starting_wounds is not None:
            raise GameLifecycleError(
                "Multi-model StartingStrengthRecord must not include single-model wounds."
            )

    @classmethod
    def from_unit(cls, *, player_id: str, unit: UnitInstance) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("StartingStrengthRecord requires a UnitInstance.")
        starting_model_count = len(unit.own_models)
        single_model_wounds = None
        if starting_model_count == 1:
            single_model_wounds = unit.own_models[0].starting_wounds
        return cls(
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            starting_model_count=starting_model_count,
            single_model_starting_wounds=single_model_wounds,
            source_id=f"army-muster:{unit.unit_instance_id}",
        )

    def to_payload(self) -> StartingStrengthRecordPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "starting_model_count": self.starting_model_count,
            "single_model_starting_wounds": self.single_model_starting_wounds,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: StartingStrengthRecordPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            starting_model_count=payload["starting_model_count"],
            single_model_starting_wounds=payload["single_model_starting_wounds"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class BelowHalfStrengthContext:
    player_id: str
    unit_instance_id: str
    starting_model_count: int
    current_model_count: int
    single_model_starting_wounds: int | None
    single_model_wounds_remaining: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("BelowHalfStrengthContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "BelowHalfStrengthContext unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "starting_model_count",
            _validate_positive_int(
                "BelowHalfStrengthContext starting_model_count",
                self.starting_model_count,
            ),
        )
        object.__setattr__(
            self,
            "current_model_count",
            _validate_non_negative_int(
                "BelowHalfStrengthContext current_model_count",
                self.current_model_count,
            ),
        )
        if self.current_model_count > self.starting_model_count:
            raise GameLifecycleError(
                "BelowHalfStrengthContext current_model_count exceeds starting strength."
            )
        object.__setattr__(
            self,
            "single_model_starting_wounds",
            _validate_optional_positive_int(
                "BelowHalfStrengthContext single_model_starting_wounds",
                self.single_model_starting_wounds,
            ),
        )
        object.__setattr__(
            self,
            "single_model_wounds_remaining",
            _validate_optional_non_negative_int(
                "BelowHalfStrengthContext single_model_wounds_remaining",
                self.single_model_wounds_remaining,
            ),
        )
        if self.starting_model_count == 1:
            if self.single_model_starting_wounds is None:
                raise GameLifecycleError(
                    "Single-model BelowHalfStrengthContext requires starting wounds."
                )
            if self.single_model_wounds_remaining is None:
                raise GameLifecycleError(
                    "Single-model BelowHalfStrengthContext requires remaining wounds."
                )
            if self.single_model_wounds_remaining > self.single_model_starting_wounds:
                raise GameLifecycleError(
                    "BelowHalfStrengthContext remaining wounds exceed starting wounds."
                )
            return
        if self.single_model_starting_wounds is not None:
            raise GameLifecycleError(
                "Multi-model BelowHalfStrengthContext must not include single-model wounds."
            )
        if self.single_model_wounds_remaining is not None:
            raise GameLifecycleError(
                "Multi-model BelowHalfStrengthContext must not include remaining wounds."
            )

    @classmethod
    def from_unit(
        cls,
        *,
        player_id: str,
        unit: UnitInstance,
        starting_strength: StartingStrengthRecord,
        current_model_ids: tuple[str, ...],
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("BelowHalfStrengthContext requires a UnitInstance.")
        if type(starting_strength) is not StartingStrengthRecord:
            raise GameLifecycleError("BelowHalfStrengthContext requires a StartingStrengthRecord.")
        if starting_strength.player_id != player_id:
            raise GameLifecycleError("BelowHalfStrengthContext player_id drift.")
        if starting_strength.unit_instance_id != unit.unit_instance_id:
            raise GameLifecycleError("BelowHalfStrengthContext unit drift.")
        model_ids = _validate_identifier_tuple("current_model_ids", current_model_ids)
        unit_model_ids = {model.model_instance_id for model in unit.own_models}
        if not set(model_ids) <= unit_model_ids:
            raise GameLifecycleError("BelowHalfStrengthContext current model is not in unit.")
        single_model_wounds_remaining = None
        if starting_strength.starting_model_count == 1:
            model = unit.own_models[0]
            single_model_wounds_remaining = model.wounds_remaining if model_ids else 0
        return cls(
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            starting_model_count=starting_strength.starting_model_count,
            current_model_count=len(model_ids),
            single_model_starting_wounds=starting_strength.single_model_starting_wounds,
            single_model_wounds_remaining=single_model_wounds_remaining,
        )

    @property
    def is_below_starting_strength(self) -> bool:
        if self.starting_model_count == 1:
            remaining = self.single_model_wounds_remaining
            starting = self.single_model_starting_wounds
            if remaining is None or starting is None:
                raise GameLifecycleError("Single-model wound context is incomplete.")
            return remaining < starting
        return self.current_model_count < self.starting_model_count

    @property
    def is_below_half_strength(self) -> bool:
        if self.starting_model_count == 1:
            remaining = self.single_model_wounds_remaining
            starting = self.single_model_starting_wounds
            if remaining is None or starting is None:
                raise GameLifecycleError("Single-model wound context is incomplete.")
            return remaining < (starting / 2)
        return self.current_model_count < (self.starting_model_count / 2)

    def to_payload(self) -> BelowHalfStrengthContextPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "starting_model_count": self.starting_model_count,
            "current_model_count": self.current_model_count,
            "single_model_starting_wounds": self.single_model_starting_wounds,
            "single_model_wounds_remaining": self.single_model_wounds_remaining,
            "is_below_starting_strength": self.is_below_starting_strength,
            "is_below_half_strength": self.is_below_half_strength,
        }

    @classmethod
    def from_payload(cls, payload: BelowHalfStrengthContextPayload) -> Self:
        context = cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            starting_model_count=payload["starting_model_count"],
            current_model_count=payload["current_model_count"],
            single_model_starting_wounds=payload["single_model_starting_wounds"],
            single_model_wounds_remaining=payload["single_model_wounds_remaining"],
        )
        if context.is_below_starting_strength != payload["is_below_starting_strength"]:
            raise GameLifecycleError("BelowHalfStrengthContext below-starting payload drift.")
        if context.is_below_half_strength != payload["is_below_half_strength"]:
            raise GameLifecycleError("BelowHalfStrengthContext below-half payload drift.")
        return context


def starting_strength_records_for_units(
    *,
    player_id: str,
    units: tuple[UnitInstance, ...],
) -> tuple[StartingStrengthRecord, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(units) is not tuple:
        raise GameLifecycleError("starting strength units must be a tuple.")
    return tuple(
        StartingStrengthRecord.from_unit(player_id=requested_player_id, unit=unit) for unit in units
    )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)


def _validate_optional_non_negative_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int(field_name, value)
