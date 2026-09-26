"""Typed melee, fixed and source-random weapon Range profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.core.weapon_profile_errors import WeaponProfileError


class RangeProfileKind(StrEnum):
    DISTANCE = "distance"
    MELEE = "melee"


class RangeProfilePayload(TypedDict):
    kind: str
    distance_inches: int | None
    random_value: NotRequired[RandomProfileValuePayload]


@dataclass(frozen=True, slots=True)
class RangeProfile:
    kind: RangeProfileKind
    distance_inches: int | None = None
    random_value: RandomProfileValue | None = None

    def __post_init__(self) -> None:
        kind = _validate_range_kind(self.kind)
        if kind != self.kind:
            object.__setattr__(self, "kind", kind)

        if self.random_value is not None:
            if (
                kind is not RangeProfileKind.DISTANCE
                or type(self.random_value) is not RandomProfileValue
                or self.random_value.characteristic is not Characteristic.RANGE
            ):
                raise WeaponProfileError("Random Range requires a source-linked Range descriptor.")
            expected = None if self.random_value.evaluation is None else self.random_value.final
            if self.distance_inches != expected:
                raise WeaponProfileError(
                    "Random Range distance must match its evaluated descriptor."
                )
            return

        if kind is RangeProfileKind.DISTANCE:
            if type(self.distance_inches) is not int:
                raise WeaponProfileError("RangeProfile distance_inches must be an integer.")
            if self.distance_inches < 1:
                raise WeaponProfileError("RangeProfile distance_inches must be at least 1.")
            return

        if self.distance_inches is not None:
            raise WeaponProfileError("Melee RangeProfile must not include distance_inches.")

    @classmethod
    def distance(cls, distance_inches: int) -> Self:
        return cls(kind=RangeProfileKind.DISTANCE, distance_inches=distance_inches)

    @classmethod
    def melee(cls) -> Self:
        return cls(kind=RangeProfileKind.MELEE)

    @classmethod
    def random(cls, value: RandomProfileValue) -> Self:
        return cls(
            kind=RangeProfileKind.DISTANCE,
            random_value=value,
            distance_inches=None if value.evaluation is None else value.final,
        )

    def to_payload(self) -> RangeProfilePayload:
        payload: RangeProfilePayload = {
            "kind": self.kind.value,
            "distance_inches": self.distance_inches,
        }
        if self.random_value is not None:
            payload["random_value"] = self.random_value.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: RangeProfilePayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) not in (
            {"kind", "distance_inches"},
            {"kind", "distance_inches", "random_value"},
        ):
            raise WeaponProfileError("Range profile payload fields are invalid.")
        return cls(
            kind=range_profile_kind_from_token(payload["kind"]),
            distance_inches=payload["distance_inches"],
            random_value=RandomProfileValue.from_payload(payload["random_value"])
            if "random_value" in payload
            else None,
        )


def range_profile_kind_from_token(token: object) -> RangeProfileKind:
    if type(token) is not str:
        raise WeaponProfileError("RangeProfile kind token must be a string.")
    try:
        return RangeProfileKind(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported range profile kind token: {token}.") from exc


def _validate_range_kind(kind: object) -> RangeProfileKind:
    if type(kind) is not RangeProfileKind:
        raise WeaponProfileError("RangeProfile kind must be a RangeProfileKind.")
    return kind
