"""Source-bound ability damage classification; providers own activation authority."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_data import RuleSourceText


class AbilityDamageSourceError(ValueError):
    """An ability damage descriptor is malformed or lacks its source identity."""


class AbilityDamageClassification(StrEnum):
    PSYCHIC_ATTACK = "psychic_attack"
    OTHER = "other"


class AbilityDamageSourcePayload(TypedDict):
    source_rule_id: str
    normalized_text_sha256: str
    classification: str


@dataclass(frozen=True, slots=True)
class AbilityDamageSource:
    source_rule_id: str
    normalized_text_sha256: str
    classification: AbilityDamageClassification

    def __post_init__(self) -> None:
        IdentifierValidator(AbilityDamageSourceError)("source_rule_id", self.source_rule_id)
        if (
            type(self.normalized_text_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.normalized_text_sha256) is None
            or type(self.classification) is not AbilityDamageClassification
        ):
            raise AbilityDamageSourceError("Ability damage source descriptor is malformed.")

    def to_payload(self) -> AbilityDamageSourcePayload:
        return {
            "source_rule_id": self.source_rule_id,
            "normalized_text_sha256": self.normalized_text_sha256,
            "classification": self.classification.value,
        }

    @classmethod
    def from_payload(cls, payload: AbilityDamageSourcePayload) -> Self:
        if set(payload) != {"source_rule_id", "normalized_text_sha256", "classification"}:
            raise AbilityDamageSourceError("Ability damage source fields are invalid.")
        try:
            classification = AbilityDamageClassification(payload["classification"])
        except (ValueError, TypeError) as exc:
            raise AbilityDamageSourceError("Ability damage classification is invalid.") from exc
        return cls(
            source_rule_id=payload["source_rule_id"],
            normalized_text_sha256=payload["normalized_text_sha256"],
            classification=classification,
        )


def ability_damage_source_at_data_boundary(source_text: RuleSourceText) -> AbilityDamageSource:
    """Classify the explicit title tag once, without granting the ability's use."""
    if type(source_text) is not RuleSourceText:
        raise AbilityDamageSourceError("Ability damage classification requires RuleSourceText.")
    title = re.match(r"^[^:\n]*\(([^)]*)\)\s*:", source_text.normalized_text)
    tags = () if title is None else tuple(tag.strip() for tag in title[1].split(","))
    psychic = any(re.fullmatch(r"psychic(?: level [1-9][0-9]*)?", tag, re.I) for tag in tags)
    return AbilityDamageSource(
        source_rule_id=source_text.source_id,
        normalized_text_sha256=hashlib.sha256(source_text.normalized_text.encode()).hexdigest(),
        classification=(
            AbilityDamageClassification.PSYCHIC_ATTACK
            if psychic
            else AbilityDamageClassification.OTHER
        ),
    )
