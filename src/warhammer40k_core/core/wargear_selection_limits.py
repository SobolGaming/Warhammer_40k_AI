from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class WargearSelectionLimitError(ValueError):
    """Raised when a model-count-scaled wargear limit is invalid."""


class DatasheetWargearSelectionLimitPayload(TypedDict):
    selection_group_id: str
    models_per_increment: int
    max_group_selections_per_increment: int
    max_option_selections_per_increment: int
    unit_resource_kind: NotRequired[str]
    unit_resource_amount_per_selection: NotRequired[int]


@dataclass(frozen=True, slots=True)
class DatasheetWargearSelectionLimit:
    selection_group_id: str
    models_per_increment: int
    max_group_selections_per_increment: int
    max_option_selections_per_increment: int
    unit_resource_kind: str | None = None
    unit_resource_amount_per_selection: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selection_group_id",
            _validate_identifier("selection_group_id", self.selection_group_id),
        )
        for field_name in (
            "models_per_increment",
            "max_group_selections_per_increment",
            "max_option_selections_per_increment",
        ):
            object.__setattr__(
                self, field_name, _positive_int(field_name, getattr(self, field_name))
            )
        if self.max_option_selections_per_increment > self.max_group_selections_per_increment:
            raise WargearSelectionLimitError(
                "Wargear option increment limit cannot exceed its group limit."
            )
        resource_kind = self.unit_resource_kind
        resource_amount = self.unit_resource_amount_per_selection
        if (resource_kind is None) != (resource_amount is None):
            raise WargearSelectionLimitError(
                "Wargear selection limit unit resource fields must be provided together."
            )
        if resource_kind is not None:
            object.__setattr__(
                self,
                "unit_resource_kind",
                _validate_identifier("unit_resource_kind", resource_kind),
            )
            object.__setattr__(
                self,
                "unit_resource_amount_per_selection",
                _positive_int("unit_resource_amount_per_selection", resource_amount),
            )

    def to_payload(self) -> DatasheetWargearSelectionLimitPayload:
        payload: DatasheetWargearSelectionLimitPayload = {
            "selection_group_id": self.selection_group_id,
            "models_per_increment": self.models_per_increment,
            "max_group_selections_per_increment": self.max_group_selections_per_increment,
            "max_option_selections_per_increment": self.max_option_selections_per_increment,
        }
        if self.unit_resource_kind is not None:
            payload["unit_resource_kind"] = self.unit_resource_kind
            resource_amount = self.unit_resource_amount_per_selection
            if resource_amount is None:
                raise WargearSelectionLimitError("Unit resource amount is missing.")
            payload["unit_resource_amount_per_selection"] = resource_amount
        return payload

    @classmethod
    def from_payload(cls, payload: DatasheetWargearSelectionLimitPayload) -> Self:
        return cls(
            selection_group_id=payload["selection_group_id"],
            models_per_increment=payload["models_per_increment"],
            max_group_selections_per_increment=payload["max_group_selections_per_increment"],
            max_option_selections_per_increment=payload["max_option_selections_per_increment"],
            unit_resource_kind=payload.get("unit_resource_kind"),
            unit_resource_amount_per_selection=payload.get("unit_resource_amount_per_selection"),
        )


def _positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise WargearSelectionLimitError(f"{field_name} must be a positive integer.")
    return value


_validate_identifier = IdentifierValidator(WargearSelectionLimitError)
