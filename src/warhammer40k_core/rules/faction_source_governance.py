"""Offline, fail-closed authority for reviewed faction App observations (F00)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

import msgspec

FACTION_SOURCE_POLICY_ID = "faction-source-policy:maintained-direct-app-data-mirror:2026-09-05"
FACTION_SOURCE_AUTHORITY_SCOPE = "warhammer_40000_11th_factions"
FACTION_SOURCE_PACKAGE_NAME = "reviewed-faction-app-observations"
EXPECTED_FACTION_AUDIT_SHA256 = "b24acc551927200dfc5562b509ce5138dddf7841dd2b5eb394ff4e2528f010b5"
FACTION_AUDIT_PATH = Path(__file__).with_name("faction_source_observations.json")

ContentKind = Literal["faction", "detachment", "datasheet"]
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_FACTION_PATH = re.compile(
    rf"/factions/(?P<faction>{_SLUG})/(?P<kind>army-rules|detachments|units)"
    rf"(?:/(?P<item>{_SLUG}))?"
)


class FactionSourceError(ValueError):
    """Faction source authority is incomplete, conflicting, or outside reviewed scope."""


class FactionGeometryObligation(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    model_role: str
    base_statement: str | None
    base_status: Literal["observed", "not_observed"]
    height_status: Literal["not_observed"]
    volume_authority: Literal["accepted_model_geometry_catalog_evidence_required"]
    fieldability_certified: bool


class FactionGeometryAuthority(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    base_authority: Literal["explicit_maintained_app_or_official_model_evidence"]
    volume_authority: Literal["accepted_model_geometry_catalog_evidence_required"]
    missing_data: Literal["blocks_fieldability"]
    variants: Literal["exact_model_profile_and_variant_required"]


class FactionVersionEvidence(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_url: str
    observed_at: str
    statement: str
    transcription_sha256: str


class FactionOfficialSource(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    provider_name: Literal["Games Workshop"]
    source_url: str
    source_date: str
    artifact_path: str
    sha256: str
    relationship: Literal["historical_primary_not_current_corroboration"]


class FactionSourceObservation(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    observation_id: str
    source_id: str
    content_kind: ContentKind
    owning_faction_source_id: str
    provider_name: Literal["40k.app"]
    provider_non_affiliation_recorded: bool
    source_url: str
    source_title: str
    app_version: str
    observed_at: str
    locale: Literal["en"]
    scope_classification: Literal["matched_play"]
    identity_status: Literal["resolved"]
    scope_review: str
    completeness: Literal["complete_page"]
    capture_method: Literal["main.innerText"]
    captured_text: str
    capture_sha256: str
    operative_start: str
    operative_text: str
    transcription_sha256: str
    objective_scope: Literal["non_core_rules"]
    official_source_ids: tuple[str, ...]
    geometry: tuple[FactionGeometryObligation, ...]
    source_observation_sha256: str


class FactionSourceAudit(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    audit_schema: Literal["core-v2-faction-source-audit-v1"]
    audit_id: str
    policy_id: str
    edition: Literal["warhammer_40000_11th"]
    app_version: str
    locale: Literal["en"]
    selected_source_ids: tuple[str, ...]
    version_evidence: FactionVersionEvidence
    official_sources: tuple[FactionOfficialSource, ...]
    geometry_authority: FactionGeometryAuthority
    observations: tuple[FactionSourceObservation, ...]

    def observation_date(self) -> date:
        """The latest UTC observation date identifies completion of the selected batch."""
        return max(
            datetime.fromisoformat(timestamp).astimezone(UTC).date()
            for timestamp in (
                self.version_evidence.observed_at,
                *(row.observed_at for row in self.observations),
            )
        )

    def package_version(self) -> str:
        return f"app-data-{self.app_version}-observed-{self.observation_date().isoformat()}"


def observation_fingerprint(payload: dict[str, object]) -> str:
    """Hash retained provenance and text; implementation status belongs elsewhere."""
    content = {key: value for key, value in payload.items() if key != "source_observation_sha256"}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_faction_source_audit_bytes(raw: bytes) -> FactionSourceAudit:
    """Validate a review candidate; only the pinned loader grants authority."""
    try:
        audit = msgspec.json.decode(raw, type=FactionSourceAudit)
    except msgspec.DecodeError as exc:
        raise FactionSourceError("Faction source audit schema is invalid.") from exc
    if audit.policy_id != FACTION_SOURCE_POLICY_ID:
        raise FactionSourceError("Faction source policy is unsupported.")
    _text(audit.audit_id)
    if not re.fullmatch(r"[1-9][0-9]*", audit.app_version):
        raise FactionSourceError("Faction source audit requires a selected App-data version.")
    _unique(audit.selected_source_ids, "selected source IDs")
    version = audit.version_evidence
    if version.source_url != "https://www.40k.app/factions/updates":
        raise FactionSourceError("Faction source version requires the retained update feed.")
    _timestamp(version.observed_at)
    _hash_matches(version.statement, version.transcription_sha256)
    if not version.statement.startswith(f"Version {audit.app_version}\nReleased "):
        raise FactionSourceError("Faction source selected version disagrees with its observation.")
    official_ids = tuple(row.source_id for row in audit.official_sources)
    _unique(official_ids, "official sources")
    for official in audit.official_sources:
        _sha256(official.sha256)
        _timestamp(f"{official.source_date}T00:00:00+00:00")
        split = urlsplit(official.source_url)
        if (
            split.scheme != "https"
            or split.netloc != "assets.warhammer-community.com"
            or split.query
            or split.fragment
            or not split.path.endswith(".pdf")
            or official.artifact_path != f"data/raw/faction_packs/{split.path.removeprefix('/')}"
            or any(
                ord(character) < 32 or ord(character) == 127 for character in official.source_url
            )
        ):
            raise FactionSourceError("Faction historical primary provenance is invalid.")
        _validate_relative_artifact_path(split.path.removeprefix("/"))
        _validate_relative_artifact_path(official.artifact_path)
    for observation in audit.observations:
        _validate_observation(observation, audit)
    _validate_agreement(audit.observations)
    _unique(tuple(row.observation_id for row in audit.observations), "observations")
    _unique(tuple(row.source_id for row in audit.observations), "owned source IDs")
    _unique(tuple(row.source_url for row in audit.observations), "owned source URLs")
    if set(audit.selected_source_ids) != {row.source_id for row in audit.observations}:
        raise FactionSourceError("Faction source observations must cover the selected inventory.")
    if {row.content_kind for row in audit.observations} != {"faction", "detachment", "datasheet"}:
        raise FactionSourceError("F00 source review must exercise every admitted package kind.")
    return audit


def load_faction_source_audit_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_FACTION_AUDIT_SHA256:
        raise FactionSourceError("Faction source artifact bytes drifted from their reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def faction_source_audit() -> FactionSourceAudit:
    try:
        raw = FACTION_AUDIT_PATH.read_bytes()
    except OSError as exc:
        raise FactionSourceError("Packaged faction source observations could not be read.") from exc
    return load_faction_source_audit_bytes(raw)


def authorize_faction_observation(
    *,
    audit_id: str,
    row_id: str,
    source_id: str,
    transcription_sha256: str,
    source_title: str,
    observed_at: str | None,
    app_version: str | None,
) -> None:
    """Prevent a registered page fingerprint from authorizing unrelated rule text."""
    audit = faction_source_audit()
    if audit.audit_id != audit_id:
        raise FactionSourceError("Faction source audit identity is unregistered.")
    for row in audit.observations:
        if row.observation_id == row_id:
            if (
                row.source_id != source_id
                or row.transcription_sha256 != transcription_sha256
                or row.source_title != source_title
                or row.observed_at != observed_at
                or row.app_version != app_version
            ):
                raise FactionSourceError(
                    "Faction evidence does not match its retained observation."
                )
            return
    raise FactionSourceError("Faction source observation is unregistered.")


def faction_source_url_identity(source_url: str) -> tuple[ContentKind, str, str]:
    """Canonical provider navigation is metadata, never a catalog identity join."""
    split = urlsplit(source_url)
    match = _FACTION_PATH.fullmatch(split.path)
    if (
        split.scheme != "https"
        or split.netloc != "www.40k.app"
        or split.query
        or split.fragment
        or any(ord(character) < 33 for character in source_url)
        or match is None
    ):
        raise FactionSourceError("Faction mirror requires a canonical HTTPS faction URL.")
    faction, path_kind, item = match.group("faction", "kind", "item")
    owner = f"faction-app:{faction}"
    if path_kind == "army-rules" and item is None:
        return "faction", owner, f"{owner}:army-rules"
    if path_kind == "detachments" and item is not None:
        return "detachment", owner, f"{owner}:detachment:{item}"
    if path_kind == "units" and item is not None:
        return "datasheet", owner, f"{owner}:datasheet:{item}"
    raise FactionSourceError("Faction source page kind does not match its URL.")


def _validate_observation(row: FactionSourceObservation, audit: FactionSourceAudit) -> None:
    for value in (row.observation_id, row.source_title, row.scope_review, row.operative_start):
        _text(value)
    if not row.provider_non_affiliation_recorded:
        raise FactionSourceError("Faction mirror must preserve provider non-affiliation.")
    if row.app_version != audit.app_version or row.locale != audit.locale:
        raise FactionSourceError("Faction source versions and locales cannot be mixed.")
    _timestamp(row.observed_at)
    if faction_source_url_identity(row.source_url) != (
        row.content_kind,
        row.owning_faction_source_id,
        row.source_id,
    ):
        raise FactionSourceError("Faction source ownership or page identity drifted.")
    _hash_matches(row.captured_text, row.capture_sha256)
    _hash_matches(row.operative_text, row.transcription_sha256)
    if (
        row.captured_text.count(row.operative_start) != 1
        or row.operative_text != row.captured_text[row.captured_text.index(row.operative_start) :]
    ):
        raise FactionSourceError("Faction operative text must retain its complete reviewed scope.")
    _unique(row.official_source_ids, "historical primary links")
    if not set(row.official_source_ids).issubset(
        source.source_id for source in audit.official_sources
    ):
        raise FactionSourceError("Faction observation references missing official provenance.")
    if (row.content_kind == "datasheet") != bool(row.geometry):
        raise FactionSourceError("Every datasheet requires explicit geometry obligations.")
    if row.geometry:
        _unique(tuple(geometry.model_role for geometry in row.geometry), "geometry model roles")
    for geometry in row.geometry:
        if geometry.model_role not in row.operative_text or geometry.fieldability_certified:
            raise FactionSourceError(
                "Source presence cannot certify model geometry or fieldability."
            )
        if (geometry.base_status == "observed") != (geometry.base_statement is not None):
            raise FactionSourceError("Missing base data must remain explicitly unresolved.")
        if geometry.base_statement is not None:
            _text(geometry.base_statement)
            if geometry.base_statement not in row.operative_text:
                raise FactionSourceError("Base statement must be retained in the observation.")
    if row.source_observation_sha256 != observation_fingerprint(msgspec.to_builtins(row)):
        raise FactionSourceError("Faction source observation fingerprint drifted.")


def _validate_agreement(rows: tuple[FactionSourceObservation, ...]) -> None:
    hashes: dict[tuple[str, str, str], str] = {}
    for row in rows:
        identity = (row.source_id, row.app_version, row.locale)
        if identity in hashes and hashes[identity] != row.transcription_sha256:
            raise FactionSourceError(
                "Co-versioned faction observations disagree; official-App comparison required."
            )
        hashes[identity] = row.transcription_sha256


def _text(value: str) -> None:
    if not value or value != value.strip():
        raise FactionSourceError("Faction evidence requires non-empty stripped identifiers.")


def _unique(values: tuple[str, ...], context: str) -> None:
    if not values or len(values) != len(set(values)):
        raise FactionSourceError(f"Faction {context} must be non-empty and unique.")
    for value in values:
        _text(value)


def _timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FactionSourceError("Faction observation timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FactionSourceError("Faction observation timestamp requires a UTC offset.")


def _sha256(value: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FactionSourceError("Faction evidence requires lowercase SHA-256.")


def _hash_matches(text: str, expected: str) -> None:
    _sha256(expected)
    if not text or hashlib.sha256(text.encode()).hexdigest() != expected:
        raise FactionSourceError("Faction retained text hash drifted.")


def _validate_relative_artifact_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {".", ".."} for part in value.split("/"))
        or any(character in value for character in ("\\", ":", "%"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FactionSourceError("Official artifact path must be normalized relative POSIX text.")
