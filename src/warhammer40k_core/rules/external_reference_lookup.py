from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict
from urllib.parse import quote

from warhammer40k_core.core.validation import IdentifierValidator

THIRTY_NINE_K_PRO_BASE_URL = "http://39k.pro"
THIRTY_NINE_K_PRO_TARGET_EDITION = "warhammer-40000-11th"

_REFERENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


class ExternalReferenceLookupError(ValueError):
    """Raised when an external reference lookup violates CORE V2 invariants."""


class ExternalReferenceKind(StrEnum):
    FACTION = "faction"
    DETACHMENT = "detachment"
    DATASHEET = "datasheet"


class ExternalReferenceLookupPayload(TypedDict):
    provider: str
    target_edition: str
    reference_kind: str
    query: str
    lookup_url: str
    expected_result_url_prefix: str


@dataclass(frozen=True, slots=True)
class ThirtyNineKProReferenceLookup:
    target_edition: str
    reference_kind: ExternalReferenceKind
    query: str

    def __post_init__(self) -> None:
        target_edition = _validate_identifier("target_edition", self.target_edition)
        if target_edition != THIRTY_NINE_K_PRO_TARGET_EDITION:
            raise ExternalReferenceLookupError(
                "39k PRO reference lookups are supported only for Warhammer 40,000 11th Edition."
            )
        object.__setattr__(self, "target_edition", target_edition)
        if type(self.reference_kind) is not ExternalReferenceKind:
            raise ExternalReferenceLookupError(
                "reference_kind must be an ExternalReferenceKind value."
            )
        query = _validate_identifier("query", self.query)
        if not query.isprintable():
            raise ExternalReferenceLookupError("query must contain only printable characters.")
        object.__setattr__(self, "query", query)

    @property
    def lookup_url(self) -> str:
        return f"{THIRTY_NINE_K_PRO_BASE_URL}/search?q={quote(self.query, safe='')}"

    @property
    def expected_result_url_prefix(self) -> str:
        return f"{THIRTY_NINE_K_PRO_BASE_URL}/{self.reference_kind.value}/"

    def reference_url(self, reference_id: str) -> str:
        validated_id = _validate_reference_id("reference_id", reference_id)
        return f"{self.expected_result_url_prefix}{validated_id}"

    def to_payload(self) -> ExternalReferenceLookupPayload:
        return {
            "provider": "39k-pro",
            "target_edition": self.target_edition,
            "reference_kind": self.reference_kind.value,
            "query": self.query,
            "lookup_url": self.lookup_url,
            "expected_result_url_prefix": self.expected_result_url_prefix,
        }


def build_thirty_nine_k_pro_reference_lookup(
    *,
    target_edition: str,
    reference_kind: ExternalReferenceKind,
    query: str,
) -> ThirtyNineKProReferenceLookup:
    return ThirtyNineKProReferenceLookup(
        target_edition=target_edition,
        reference_kind=reference_kind,
        query=query,
    )


_validate_identifier = IdentifierValidator(ExternalReferenceLookupError)
_validate_reference_id = IdentifierValidator(
    ExternalReferenceLookupError,
    pattern=_REFERENCE_ID_PATTERN,
    pattern_message="reference_id must be a 39k PRO URL-safe identifier.",
)
