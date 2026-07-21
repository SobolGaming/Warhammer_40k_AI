from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class AttachmentEligibilityError(ValueError):
    """Raised when structured attachment eligibility data is invalid."""


class AttachmentRole(StrEnum):
    LEADER = "leader"
    SUPPORT = "support"


class AttachmentTargetEligibilityPayload(TypedDict):
    bodyguard_datasheet_id: str
    source_ids: list[str]
    required_wargear_ids: list[str]


class AttachmentEligibilityPayload(TypedDict):
    role: str
    targets: list[AttachmentTargetEligibilityPayload]


@dataclass(frozen=True, slots=True)
class AttachmentTargetEligibility:
    bodyguard_datasheet_id: str
    source_ids: tuple[str, ...]
    required_wargear_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bodyguard_datasheet_id",
            _validate_identifier(
                "AttachmentTargetEligibility bodyguard_datasheet_id",
                self.bodyguard_datasheet_id,
            ),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple(
                "AttachmentTargetEligibility source_ids",
                self.source_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "required_wargear_ids",
            _validate_identifier_tuple(
                "AttachmentTargetEligibility required_wargear_ids",
                self.required_wargear_ids,
                min_length=0,
            ),
        )

    def to_payload(self) -> AttachmentTargetEligibilityPayload:
        return {
            "bodyguard_datasheet_id": self.bodyguard_datasheet_id,
            "source_ids": list(self.source_ids),
            "required_wargear_ids": list(self.required_wargear_ids),
        }

    @classmethod
    def from_payload(cls, payload: AttachmentTargetEligibilityPayload) -> Self:
        return cls(
            bodyguard_datasheet_id=payload["bodyguard_datasheet_id"],
            source_ids=tuple(payload["source_ids"]),
            required_wargear_ids=tuple(payload["required_wargear_ids"]),
        )


@dataclass(frozen=True, slots=True)
class AttachmentEligibility:
    role: AttachmentRole
    targets: tuple[AttachmentTargetEligibility, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", attachment_role_from_token(self.role))
        if type(self.targets) is not tuple:
            raise AttachmentEligibilityError("AttachmentEligibility targets must be a tuple.")
        if not self.targets:
            raise AttachmentEligibilityError("AttachmentEligibility targets must not be empty.")
        seen_bodyguard_ids: set[str] = set()
        validated: list[AttachmentTargetEligibility] = []
        for target in self.targets:
            if type(target) is not AttachmentTargetEligibility:
                raise AttachmentEligibilityError(
                    "AttachmentEligibility targets must contain target eligibility values."
                )
            if target.bodyguard_datasheet_id in seen_bodyguard_ids:
                raise AttachmentEligibilityError(
                    "AttachmentEligibility targets must not duplicate bodyguard datasheet IDs."
                )
            seen_bodyguard_ids.add(target.bodyguard_datasheet_id)
            validated.append(target)
        object.__setattr__(
            self,
            "targets",
            tuple(sorted(validated, key=lambda target: target.bodyguard_datasheet_id)),
        )

    def target_for_bodyguard_datasheet_id(
        self,
        bodyguard_datasheet_id: str,
    ) -> AttachmentTargetEligibility | None:
        requested_id = _validate_identifier("bodyguard_datasheet_id", bodyguard_datasheet_id)
        for target in self.targets:
            if target.bodyguard_datasheet_id == requested_id:
                return target
        return None

    def to_payload(self) -> AttachmentEligibilityPayload:
        return {
            "role": self.role.value,
            "targets": [target.to_payload() for target in self.targets],
        }

    @classmethod
    def from_payload(cls, payload: AttachmentEligibilityPayload) -> Self:
        return cls(
            role=attachment_role_from_token(payload["role"]),
            targets=tuple(
                AttachmentTargetEligibility.from_payload(target) for target in payload["targets"]
            ),
        )


def attachment_role_from_token(token: object) -> AttachmentRole:
    if type(token) is AttachmentRole:
        return token
    if type(token) is not str:
        raise AttachmentEligibilityError("AttachmentRole token must be a string.")
    try:
        return AttachmentRole(token)
    except ValueError as exc:
        raise AttachmentEligibilityError(f"Unsupported AttachmentRole token: {token}.") from exc


_validate_identifier = IdentifierValidator(AttachmentEligibilityError)


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise AttachmentEligibilityError(f"{field_name} must be a tuple.")
    if len(values) < min_length:
        raise AttachmentEligibilityError(f"{field_name} must contain at least {min_length} values.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise AttachmentEligibilityError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))
