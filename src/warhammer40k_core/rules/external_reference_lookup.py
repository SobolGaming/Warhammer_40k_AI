from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, TypedDict
from urllib.parse import quote, urlsplit

from warhammer40k_core.core.validation import IdentifierValidator

THIRTY_NINE_K_PRO_BASE_URL = "https://39k.pro"
THIRTY_NINE_K_PRO_TARGET_EDITION = "warhammer-40000-11th"

_REFERENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


class ExternalReferenceLookupError(ValueError):
    """Raised when an external reference lookup violates CORE V2 invariants."""


class ExternalReferenceKind(StrEnum):
    FACTION = "faction"
    DETACHMENT = "detachment"
    DATASHEET = "datasheet"


class ExternalReferenceDiscoveryMethod(StrEnum):
    FACTION_NAVIGATION = "faction-navigation"
    FACTION_DETACHMENT_NAVIGATION = "faction-detachment-navigation"
    DATASHEET_SEARCH = "datasheet-search"


class ExternalReferenceLookupPayload(TypedDict):
    provider: str
    target_edition: str
    reference_kind: str
    query: str
    discovery_method: str
    discovery_url: str
    reference_verification_required: bool
    parent_faction_url: NotRequired[str]


class ExternalReferencePayload(TypedDict):
    provider: str
    target_edition: str
    reference_kind: str
    reference_id: str
    reference_url: str
    is_verified: bool


@dataclass(frozen=True, slots=True)
class ThirtyNineKProReference:
    target_edition: str
    reference_kind: ExternalReferenceKind
    reference_id: str
    reference_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_edition", _validate_target_edition(self.target_edition))
        _validate_reference_kind(self.reference_kind)
        reference_id = _validate_reference_id("reference_id", self.reference_id)
        parsed_kind, parsed_id, canonical_url = _parse_reference_url(self.reference_url)
        if parsed_kind is not self.reference_kind:
            raise ExternalReferenceLookupError(
                "39k PRO reference URL kind does not match reference_kind."
            )
        if parsed_id != reference_id:
            raise ExternalReferenceLookupError(
                "39k PRO reference URL ID does not match reference_id."
            )
        object.__setattr__(self, "reference_id", reference_id)
        object.__setattr__(self, "reference_url", canonical_url)

    def to_payload(self) -> ExternalReferencePayload:
        return {
            "provider": "39k-pro",
            "target_edition": self.target_edition,
            "reference_kind": self.reference_kind.value,
            "reference_id": self.reference_id,
            "reference_url": self.reference_url,
            "is_verified": True,
        }


@dataclass(frozen=True, slots=True)
class ThirtyNineKProReferenceLookup:
    target_edition: str
    reference_kind: ExternalReferenceKind
    query: str
    parent_faction_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_edition", _validate_target_edition(self.target_edition))
        _validate_reference_kind(self.reference_kind)
        query = _validate_identifier("query", self.query)
        if not query.isprintable():
            raise ExternalReferenceLookupError("query must contain only printable characters.")
        object.__setattr__(self, "query", query)
        if self.reference_kind is ExternalReferenceKind.DETACHMENT:
            if self.parent_faction_url is None:
                raise ExternalReferenceLookupError(
                    "Detachment discovery requires a verified parent_faction_url."
                )
            parent = verify_thirty_nine_k_pro_reference_url(
                target_edition=self.target_edition,
                expected_kind=ExternalReferenceKind.FACTION,
                reference_url=self.parent_faction_url,
            )
            object.__setattr__(self, "parent_faction_url", parent.reference_url)
        elif self.parent_faction_url is not None:
            raise ExternalReferenceLookupError(
                "parent_faction_url is supported only for detachment discovery."
            )

    @property
    def discovery_method(self) -> ExternalReferenceDiscoveryMethod:
        if self.reference_kind is ExternalReferenceKind.FACTION:
            return ExternalReferenceDiscoveryMethod.FACTION_NAVIGATION
        if self.reference_kind is ExternalReferenceKind.DETACHMENT:
            return ExternalReferenceDiscoveryMethod.FACTION_DETACHMENT_NAVIGATION
        return ExternalReferenceDiscoveryMethod.DATASHEET_SEARCH

    @property
    def discovery_url(self) -> str:
        if self.reference_kind is ExternalReferenceKind.FACTION:
            return f"{THIRTY_NINE_K_PRO_BASE_URL}/"
        if self.reference_kind is ExternalReferenceKind.DETACHMENT:
            if type(self.parent_faction_url) is not str:
                raise ExternalReferenceLookupError(
                    "Detachment discovery requires a verified parent_faction_url."
                )
            return self.parent_faction_url
        return f"{THIRTY_NINE_K_PRO_BASE_URL}/search?q={quote(self.query, safe='')}"

    def verify_reference_url(self, reference_url: str) -> ThirtyNineKProReference:
        return verify_thirty_nine_k_pro_reference_url(
            target_edition=self.target_edition,
            expected_kind=self.reference_kind,
            reference_url=reference_url,
        )

    def to_payload(self) -> ExternalReferenceLookupPayload:
        payload: ExternalReferenceLookupPayload = {
            "provider": "39k-pro",
            "target_edition": self.target_edition,
            "reference_kind": self.reference_kind.value,
            "query": self.query,
            "discovery_method": self.discovery_method.value,
            "discovery_url": self.discovery_url,
            "reference_verification_required": True,
        }
        if self.parent_faction_url is not None:
            payload["parent_faction_url"] = self.parent_faction_url
        return payload


def build_thirty_nine_k_pro_reference_lookup(
    *,
    target_edition: str,
    reference_kind: ExternalReferenceKind,
    query: str,
    parent_faction_url: str | None = None,
) -> ThirtyNineKProReferenceLookup:
    return ThirtyNineKProReferenceLookup(
        target_edition=target_edition,
        reference_kind=reference_kind,
        query=query,
        parent_faction_url=parent_faction_url,
    )


def verify_thirty_nine_k_pro_reference_url(
    *,
    target_edition: str,
    expected_kind: ExternalReferenceKind,
    reference_url: str,
) -> ThirtyNineKProReference:
    validated_edition = _validate_target_edition(target_edition)
    _validate_reference_kind(expected_kind)
    parsed_kind, reference_id, canonical_url = _parse_reference_url(reference_url)
    if parsed_kind is not expected_kind:
        raise ExternalReferenceLookupError(
            "39k PRO reference URL kind does not match expected_kind."
        )
    return ThirtyNineKProReference(
        target_edition=validated_edition,
        reference_kind=parsed_kind,
        reference_id=reference_id,
        reference_url=canonical_url,
    )


def _parse_reference_url(reference_url: str) -> tuple[ExternalReferenceKind, str, str]:
    validated_url = _validate_identifier("reference_url", reference_url)
    try:
        parsed = urlsplit(validated_url)
    except ValueError as exc:
        raise ExternalReferenceLookupError("reference_url must be a valid URL.") from exc
    if parsed.scheme != "https" or parsed.netloc != "39k.pro":
        raise ExternalReferenceLookupError("reference_url must use HTTPS and the 39k.pro host.")
    if parsed.query or parsed.fragment:
        raise ExternalReferenceLookupError(
            "reference_url must not contain a query string or fragment."
        )
    path_parts = parsed.path.split("/")
    if len(path_parts) != 3 or path_parts[0] or not path_parts[1] or not path_parts[2]:
        raise ExternalReferenceLookupError(
            "reference_url path must contain exactly one supported kind and one reference ID."
        )
    try:
        reference_kind = ExternalReferenceKind(path_parts[1])
    except ValueError as exc:
        raise ExternalReferenceLookupError(
            "reference_url path must use faction, detachment, or datasheet."
        ) from exc
    reference_id = _validate_reference_id("reference_id", path_parts[2])
    canonical_url = f"{THIRTY_NINE_K_PRO_BASE_URL}/{reference_kind.value}/{reference_id}"
    if validated_url != canonical_url:
        raise ExternalReferenceLookupError("reference_url must use the canonical 39k PRO form.")
    return reference_kind, reference_id, canonical_url


def _validate_target_edition(target_edition: object) -> str:
    validated_edition = _validate_identifier("target_edition", target_edition)
    if validated_edition != THIRTY_NINE_K_PRO_TARGET_EDITION:
        raise ExternalReferenceLookupError(
            "39k PRO reference lookups are supported only for Warhammer 40,000 11th Edition."
        )
    return validated_edition


def _validate_reference_kind(reference_kind: object) -> None:
    if type(reference_kind) is not ExternalReferenceKind:
        raise ExternalReferenceLookupError("reference_kind must be an ExternalReferenceKind value.")


_validate_identifier = IdentifierValidator(ExternalReferenceLookupError)
_validate_reference_id = IdentifierValidator(
    ExternalReferenceLookupError,
    pattern=_REFERENCE_ID_PATTERN,
    pattern_message="reference_id must be a 39k PRO URL-safe identifier.",
)
