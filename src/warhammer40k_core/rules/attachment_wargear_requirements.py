from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.validation import IdentifierValidator


class AttachmentWargearRequirementError(ValueError):
    """Raised when source-backed attachment wargear metadata is invalid."""


@dataclass(frozen=True, slots=True)
class AttachmentWargearRequirement:
    leader_datasheet_id: str
    bodyguard_datasheet_id: str
    required_wargear_ids: tuple[str, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "leader_datasheet_id",
            _validate_identifier("leader_datasheet_id", self.leader_datasheet_id),
        )
        object.__setattr__(
            self,
            "bodyguard_datasheet_id",
            _validate_identifier("bodyguard_datasheet_id", self.bodyguard_datasheet_id),
        )
        object.__setattr__(
            self,
            "required_wargear_ids",
            _validate_identifier_tuple(
                "required_wargear_ids",
                self.required_wargear_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids, min_length=1),
        )


_validate_identifier = IdentifierValidator(AttachmentWargearRequirementError)


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise AttachmentWargearRequirementError(f"{field_name} must be a tuple.")
    if len(values) < min_length:
        raise AttachmentWargearRequirementError(
            f"{field_name} must contain at least {min_length} values."
        )
    validated = tuple(_validate_identifier(f"{field_name} value", value) for value in values)
    if len(set(validated)) != len(validated):
        raise AttachmentWargearRequirementError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))
