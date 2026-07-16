from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.list_validation_errors import ListValidationError


class ModelProfileSelectionPayload(TypedDict):
    model_profile_id: str
    model_count: int


class WargearSelectionPayload(TypedDict):
    option_id: str
    model_profile_id: str
    wargear_ids: list[str]
    selection_count: NotRequired[int]


@dataclass(frozen=True, slots=True)
class ModelProfileSelection:
    model_profile_id: str
    model_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("ModelProfileSelection model_profile_id", self.model_profile_id),
        )
        object.__setattr__(
            self,
            "model_count",
            _validate_positive_int("ModelProfileSelection model_count", self.model_count),
        )

    def to_payload(self) -> ModelProfileSelectionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "model_count": self.model_count,
        }

    @classmethod
    def from_payload(cls, payload: ModelProfileSelectionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            model_count=payload["model_count"],
        )


@dataclass(frozen=True, slots=True)
class WargearSelection:
    option_id: str
    model_profile_id: str
    wargear_ids: tuple[str, ...]
    selection_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_unprefixed_identifier(
                "WargearSelection option_id",
                self.option_id,
                "wargear-option:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("WargearSelection model_profile_id", self.model_profile_id),
        )
        object.__setattr__(
            self,
            "wargear_ids",
            _validate_identifier_tuple(
                "WargearSelection wargear_ids",
                self.wargear_ids,
                min_length=0,
            ),
        )
        if self.selection_count is not None:
            if type(self.selection_count) is not int or self.selection_count < 0:
                raise ListValidationError(
                    "WargearSelection selection_count must be a non-negative integer."
                )
            if self.wargear_ids and self.selection_count == 0:
                raise ListValidationError(
                    "WargearSelection selection_count must be positive when wargear is selected."
                )
            if not self.wargear_ids and self.selection_count != 0:
                raise ListValidationError(
                    "WargearSelection selection_count must be zero when no wargear is selected."
                )

    @property
    def resolved_selection_count(self) -> int:
        if self.selection_count is not None:
            return self.selection_count
        return 1 if self.wargear_ids else 0

    def to_payload(self) -> WargearSelectionPayload:
        payload: WargearSelectionPayload = {
            "option_id": self.option_id,
            "model_profile_id": self.model_profile_id,
            "wargear_ids": list(self.wargear_ids),
        }
        if self.selection_count is not None:
            payload["selection_count"] = self.selection_count
        return payload

    @classmethod
    def from_payload(cls, payload: WargearSelectionPayload) -> Self:
        return cls(
            option_id=payload["option_id"],
            model_profile_id=payload["model_profile_id"],
            wargear_ids=tuple(payload["wargear_ids"]),
            selection_count=payload.get("selection_count"),
        )


_validate_identifier = IdentifierValidator(ListValidationError)


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ListValidationError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ListValidationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ListValidationError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ListValidationError(f"{field_name} must be an integer.")
    if value < 1:
        raise ListValidationError(f"{field_name} must be at least 1.")
    return value
