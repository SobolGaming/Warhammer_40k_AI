from __future__ import annotations

import hashlib
import json
from dataclasses import InitVar, dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal, Self, TypedDict, cast
from urllib.parse import urlsplit

from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceCatalogError

RuleEvidenceKind = Literal[
    "official_app_capture",
    "owner_supplied_app_transcription",
    "project_reviewed_app_transcription",
    "third_party_mirror",
]
RuleEvidenceAuthority = Literal[
    "official_primary",
    "project_authoritative_app_mirror",
    "unverified_transcription_only",
    "secondary_mirror_only",
]
RuleVerificationStatus = Literal[
    "authoritative_app_mirror",
    "official_app_captured",
    "mirror_only",
    "not_observed_on_mirror",
    "conflict",
    "unverified",
]
LoadSupportStatus = Literal["loaded", "not_loaded"]
SemanticExecutionStatus = Literal[
    "not_certified",
    "partial_engine_runtime",
    "executable_engine_runtime",
    "blocked_by_source_conflict",
    "unsupported",
]

CORE_RULES_MAINTAINED_MIRROR_POLICY_ID = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
_MAINTAINED_APP_MIRROR_PROVIDERS = frozenset({"40k.app", "Game Datamissions"})


class RuleEvidenceError(ValueError):
    """Raised when rule-evidence data overstates or corrupts its provenance."""


class RuleEvidencePayload(TypedDict):
    evidence_id: str
    rule_source_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    project_authority_policy_id: str | None
    review_audit_id: str | None
    review_audit_row_id: str | None
    review_audit_source_observation_sha256: str | None
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str | None
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    transcription_sha256: str
    official_corroborating_source_ids: list[str]
    verification_status: RuleVerificationStatus
    provider_non_affiliation_recorded: bool
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: list[str]


_RULE_EVIDENCE_PAYLOAD_FIELDS = frozenset(RuleEvidencePayload.__annotations__)


@dataclass(frozen=True, slots=True)
class RuleEvidenceRecord:
    """Typed provenance and execution status for one stable source-rule identity."""

    evidence_id: str
    rule_source_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    project_authority_policy_id: str | None
    review_audit_id: str | None
    review_audit_row_id: str | None
    review_audit_source_observation_sha256: str | None
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str | None
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    transcription_sha256: str
    official_corroborating_source_ids: tuple[str, ...]
    verification_status: RuleVerificationStatus
    provider_non_affiliation_recorded: bool
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]
    capture_content: InitVar[bytes | None] = None

    def __post_init__(self, capture_content: bytes | None) -> None:
        for field_name in (
            "evidence_id",
            "rule_source_id",
            "provider_name",
            "source_title",
            "source_platform",
        ):
            _validate_text(field_name, getattr(self, field_name))
        _validate_literal(
            "evidence_kind",
            self.evidence_kind,
            {
                "official_app_capture",
                "owner_supplied_app_transcription",
                "project_reviewed_app_transcription",
                "third_party_mirror",
            },
        )
        _validate_literal(
            "authority",
            self.authority,
            {
                "official_primary",
                "project_authoritative_app_mirror",
                "unverified_transcription_only",
                "secondary_mirror_only",
            },
        )
        _validate_literal(
            "verification_status",
            self.verification_status,
            {
                "authoritative_app_mirror",
                "official_app_captured",
                "mirror_only",
                "not_observed_on_mirror",
                "conflict",
                "unverified",
            },
        )
        _validate_literal(
            "load_support_status",
            self.load_support_status,
            {"loaded", "not_loaded"},
        )
        _validate_literal(
            "semantic_execution_status",
            self.semantic_execution_status,
            {
                "not_certified",
                "partial_engine_runtime",
                "executable_engine_runtime",
                "blocked_by_source_conflict",
                "unsupported",
            },
        )
        _validate_optional_observed_at(self.observed_at)
        _validate_optional_text("source_url", self.source_url)
        _validate_optional_text(
            "project_authority_policy_id",
            self.project_authority_policy_id,
        )
        _validate_optional_text("review_audit_id", self.review_audit_id)
        _validate_optional_text("review_audit_row_id", self.review_audit_row_id)
        _validate_optional_sha256(
            "review_audit_source_observation_sha256",
            self.review_audit_source_observation_sha256,
        )
        _validate_optional_text("app_version", self.app_version)
        _validate_optional_text("app_build", self.app_build)
        _validate_optional_text("capture_artifact_path", self.capture_artifact_path)
        _validate_optional_sha256("capture_sha256", self.capture_sha256)
        _validate_sha256("transcription_sha256", self.transcription_sha256)
        _validate_sha256("observation_sha256", self.observation_sha256)
        _validate_text_tuple(
            "official_corroborating_source_ids",
            self.official_corroborating_source_ids,
        )
        _validate_text_tuple("runtime_consumer_ids", self.runtime_consumer_ids)
        if type(self.provider_non_affiliation_recorded) is not bool:
            raise RuleEvidenceError(
                "RuleEvidenceRecord provider_non_affiliation_recorded must be a boolean."
            )
        self._validate_evidence_authority(capture_content)
        self._validate_execution_status()
        if self.observation_sha256 != self.computed_observation_sha256():
            raise RuleEvidenceError("RuleEvidenceRecord observation hash is stale.")

    def _validate_evidence_authority(self, capture_content: bytes | None) -> None:
        if self.evidence_kind == "official_app_capture":
            if (
                self.authority != "official_primary"
                or self.verification_status != "official_app_captured"
                or self.provider_name != "Games Workshop"
                or self.source_platform != "Warhammer 40,000 App"
                or self.source_url is not None
                or self.observed_at is None
                or self.app_version is None
                or self.app_build is None
                or self.capture_artifact_path is None
                or self.capture_sha256 is None
                or self.project_authority_policy_id is not None
                or self.review_audit_id is not None
                or self.review_audit_row_id is not None
                or self.review_audit_source_observation_sha256 is not None
            ):
                raise RuleEvidenceError(
                    "An official App capture requires the Games Workshop App, official authority, "
                    "version, build, and a hashed retained capture."
                )
            if self.provider_non_affiliation_recorded:
                raise RuleEvidenceError(
                    "Official App evidence cannot carry a third-party non-affiliation marker."
                )
            _validate_capture_artifact_path(self.capture_artifact_path)
            if (
                type(capture_content) is not bytes
                or not capture_content
                or hashlib.sha256(capture_content).hexdigest() != self.capture_sha256
            ):
                raise RuleEvidenceError(
                    "Official App evidence requires retained capture bytes matching capture_sha256."
                )
            return
        if capture_content is not None:
            raise RuleEvidenceError(
                "Only official App capture evidence may receive retained capture bytes."
            )
        if self.evidence_kind in {
            "owner_supplied_app_transcription",
            "project_reviewed_app_transcription",
        }:
            if (
                self.authority != "unverified_transcription_only"
                or self.verification_status != "unverified"
                or self.official_corroborating_source_ids
                or self.project_authority_policy_id is not None
                or self.review_audit_id is not None
                or self.review_audit_row_id is not None
                or self.review_audit_source_observation_sha256 is not None
                or any(
                    value is not None
                    for value in (
                        self.source_url,
                        self.app_version,
                        self.app_build,
                        self.capture_artifact_path,
                        self.capture_sha256,
                    )
                )
            ):
                raise RuleEvidenceError(
                    "An App transcription must remain unverified and uncaptured on its own."
                )
            if self.evidence_kind == "project_reviewed_app_transcription" and (
                self.provider_name != "CORE V2 Source Review"
                or self.source_platform != "Repository"
                or self.provider_non_affiliation_recorded
            ):
                raise RuleEvidenceError(
                    "A project-reviewed App transcription must retain repository-review "
                    "provenance without a provider-affiliation claim."
                )
            return
        if self.authority == "project_authoritative_app_mirror":
            allowed_verification_statuses = {
                "authoritative_app_mirror",
                "not_observed_on_mirror",
                "conflict",
            }
            if self.project_authority_policy_id is None:
                raise RuleEvidenceError(
                    "A project-authoritative App mirror requires its authority policy ID."
                )
        else:
            allowed_verification_statuses = {
                "mirror_only",
                "not_observed_on_mirror",
                "conflict",
            }
            if (
                self.authority != "secondary_mirror_only"
                or self.project_authority_policy_id is not None
            ):
                raise RuleEvidenceError("A third-party mirror authority classification is invalid.")
        if (
            self.verification_status not in allowed_verification_statuses
            or self.source_platform != "Web"
            or self.source_url is None
            or (self.observed_at is None and self.app_version is None)
            or self.review_audit_id is None
            or self.review_audit_row_id is None
            or self.review_audit_source_observation_sha256 is None
            or any(
                value is not None
                for value in (
                    self.capture_artifact_path,
                    self.capture_sha256,
                )
            )
            or (self.app_build is not None and self.app_version is None)
            or self.official_corroborating_source_ids
            or not self.provider_non_affiliation_recorded
        ):
            raise RuleEvidenceError(
                "A maintained App-mirror record must retain its provider, URL, App-data version "
                "or observation timestamp, audit fingerprint, declared authority, and "
                "non-affiliation without official-provider, corroboration, or capture claims."
            )
        _validate_mirror_provider(
            provider_name=self.provider_name,
            source_url=self.source_url,
            authority=self.authority,
            project_authority_policy_id=self.project_authority_policy_id,
        )

    def _validate_execution_status(self) -> None:
        has_consumers = bool(self.runtime_consumer_ids)
        if (
            self.semantic_execution_status
            in {"partial_engine_runtime", "executable_engine_runtime"}
        ) != has_consumers:
            raise RuleEvidenceError(
                "Executable or partial rule evidence must name runtime consumers, and other "
                "execution statuses must not."
            )
        if self.load_support_status == "not_loaded" and has_consumers:
            raise RuleEvidenceError(
                "Rule evidence cannot name runtime consumers when the source row is not loaded."
            )
        if self.verification_status == "conflict" and (
            self.semantic_execution_status != "blocked_by_source_conflict"
        ):
            raise RuleEvidenceError(
                "Conflicting source evidence must block semantic certification."
            )

    def computed_observation_sha256(self) -> str:
        payload = self.to_payload()
        payload["observation_sha256"] = ""
        payload["load_support_status"] = "not_loaded"
        payload["semantic_execution_status"] = "not_certified"
        payload["runtime_consumer_ids"] = []
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_payload(self) -> RuleEvidencePayload:
        return {
            "evidence_id": self.evidence_id,
            "rule_source_id": self.rule_source_id,
            "evidence_kind": self.evidence_kind,
            "authority": self.authority,
            "project_authority_policy_id": self.project_authority_policy_id,
            "review_audit_id": self.review_audit_id,
            "review_audit_row_id": self.review_audit_row_id,
            "review_audit_source_observation_sha256": self.review_audit_source_observation_sha256,
            "provider_name": self.provider_name,
            "source_title": self.source_title,
            "source_platform": self.source_platform,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "app_version": self.app_version,
            "app_build": self.app_build,
            "capture_artifact_path": self.capture_artifact_path,
            "capture_sha256": self.capture_sha256,
            "transcription_sha256": self.transcription_sha256,
            "official_corroborating_source_ids": list(self.official_corroborating_source_ids),
            "verification_status": self.verification_status,
            "provider_non_affiliation_recorded": self.provider_non_affiliation_recorded,
            "observation_sha256": self.observation_sha256,
            "load_support_status": self.load_support_status,
            "semantic_execution_status": self.semantic_execution_status,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
        }

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        capture_content: bytes | None = None,
    ) -> Self:
        if type(payload) is not dict:
            raise RuleEvidenceError("RuleEvidenceRecord payload fields drifted.")
        raw_payload = cast(dict[str, object], payload)
        if set(raw_payload) != set(_RULE_EVIDENCE_PAYLOAD_FIELDS):
            raise RuleEvidenceError("RuleEvidenceRecord payload fields drifted.")
        for field_name in (
            "official_corroborating_source_ids",
            "runtime_consumer_ids",
        ):
            if type(raw_payload[field_name]) is not list:
                raise RuleEvidenceError(f"RuleEvidenceRecord payload {field_name} must be a list.")
        typed_payload = cast(RuleEvidencePayload, raw_payload)
        return cls(
            evidence_id=typed_payload["evidence_id"],
            rule_source_id=typed_payload["rule_source_id"],
            evidence_kind=typed_payload["evidence_kind"],
            authority=typed_payload["authority"],
            project_authority_policy_id=typed_payload["project_authority_policy_id"],
            review_audit_id=typed_payload["review_audit_id"],
            review_audit_row_id=typed_payload["review_audit_row_id"],
            review_audit_source_observation_sha256=typed_payload[
                "review_audit_source_observation_sha256"
            ],
            provider_name=typed_payload["provider_name"],
            source_title=typed_payload["source_title"],
            source_platform=typed_payload["source_platform"],
            source_url=typed_payload["source_url"],
            observed_at=typed_payload["observed_at"],
            app_version=typed_payload["app_version"],
            app_build=typed_payload["app_build"],
            capture_artifact_path=typed_payload["capture_artifact_path"],
            capture_sha256=typed_payload["capture_sha256"],
            transcription_sha256=typed_payload["transcription_sha256"],
            official_corroborating_source_ids=tuple(
                typed_payload["official_corroborating_source_ids"]
            ),
            verification_status=typed_payload["verification_status"],
            provider_non_affiliation_recorded=typed_payload["provider_non_affiliation_recorded"],
            observation_sha256=typed_payload["observation_sha256"],
            load_support_status=typed_payload["load_support_status"],
            semantic_execution_status=typed_payload["semantic_execution_status"],
            runtime_consumer_ids=tuple(typed_payload["runtime_consumer_ids"]),
            capture_content=capture_content,
        )


@dataclass(frozen=True, slots=True)
class SourceEvidenceCatalog:
    """Fail-closed evidence inventory keyed by stable rule-source identity."""

    records: tuple[RuleEvidenceRecord, ...]

    def __post_init__(self) -> None:
        if type(self.records) is not tuple or not self.records:
            raise RuleEvidenceError("SourceEvidenceCatalog records must be a non-empty tuple.")
        if any(type(record) is not RuleEvidenceRecord for record in self.records):
            raise RuleEvidenceError(
                "SourceEvidenceCatalog records must contain RuleEvidenceRecord values."
            )
        evidence_ids = tuple(record.evidence_id for record in self.records)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise RuleEvidenceError("SourceEvidenceCatalog evidence IDs must be unique.")
        _validate_co_versioned_mirror_agreement(self.records)
        object.__setattr__(
            self,
            "records",
            tuple(sorted(self.records, key=lambda record: record.evidence_id)),
        )

    def records_for_source_id(self, source_id: str) -> tuple[RuleEvidenceRecord, ...]:
        requested_source_id = _validate_text("source_id", source_id)
        records = tuple(
            record for record in self.records if record.rule_source_id == requested_source_id
        )
        if not records:
            raise RuleEvidenceError("SourceEvidenceCatalog source_id was not found.")
        return records


@dataclass(frozen=True, slots=True)
class RuleSourcePackage:
    """A source catalog that cannot be returned without its required provenance."""

    source_catalog: SourceCatalog
    source_evidence_catalog: SourceEvidenceCatalog
    evidence_required_source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.source_catalog) is not SourceCatalog:
            raise RuleEvidenceError("RuleSourcePackage source_catalog must be a SourceCatalog.")
        if type(self.source_evidence_catalog) is not SourceEvidenceCatalog:
            raise RuleEvidenceError(
                "RuleSourcePackage source_evidence_catalog must be a SourceEvidenceCatalog."
            )
        required_source_ids = _validate_text_tuple(
            "evidence_required_source_ids",
            self.evidence_required_source_ids,
        )
        if not required_source_ids:
            raise RuleEvidenceError(
                "RuleSourcePackage evidence_required_source_ids must not be empty."
            )
        if tuple(sorted(required_source_ids)) != required_source_ids:
            raise RuleEvidenceError(
                "RuleSourcePackage evidence_required_source_ids must be sorted."
            )
        required_source_id_set = set(required_source_ids)
        evidenced_source_ids = {
            record.rule_source_id for record in self.source_evidence_catalog.records
        }
        if evidenced_source_ids != required_source_id_set:
            raise RuleEvidenceError(
                "RuleSourcePackage evidence inventory must exactly cover required source IDs."
            )
        for source_id in required_source_ids:
            try:
                source_text = self.source_catalog.source_text_by_id(source_id)
            except SourceCatalogError as exc:
                raise RuleEvidenceError(
                    "RuleSourcePackage required evidence source ID is absent from its catalog."
                ) from exc
            records = self.source_evidence_catalog.records_for_source_id(source_id)
            if not any(
                record.evidence_kind
                in {
                    "owner_supplied_app_transcription",
                    "project_reviewed_app_transcription",
                    "official_app_capture",
                }
                for record in records
            ):
                raise RuleEvidenceError(
                    "RuleSourcePackage source rows require transcription or official-capture "
                    "provenance; mirror comparison alone is insufficient."
                )
            expected_transcription_sha256 = hashlib.sha256(
                source_text.raw_text.encode()
            ).hexdigest()
            if any(
                record.transcription_sha256 != expected_transcription_sha256 for record in records
            ):
                raise RuleEvidenceError(
                    "RuleSourcePackage evidence transcription hash does not match its source row."
                )
            support_states = {
                (
                    record.load_support_status,
                    record.semantic_execution_status,
                    record.runtime_consumer_ids,
                )
                for record in records
            }
            if len(support_states) != 1:
                raise RuleEvidenceError(
                    "RuleSourcePackage evidence for one source row must agree on load and "
                    "semantic execution status."
                )
            semantic_execution_status = next(iter(support_states))[1]
            if semantic_execution_status in {
                "partial_engine_runtime",
                "executable_engine_runtime",
            } and not any(
                record.verification_status == "official_app_captured"
                or (
                    record.authority == "project_authoritative_app_mirror"
                    and record.verification_status == "authoritative_app_mirror"
                )
                for record in records
            ):
                raise RuleEvidenceError(
                    "RuleSourcePackage executable or partial semantics require an official App "
                    "capture or project-authoritative App-mirror observation."
                )
            has_conflict_evidence = any(
                record.verification_status == "conflict" for record in records
            )
            if (semantic_execution_status == "blocked_by_source_conflict") != (
                has_conflict_evidence
            ):
                raise RuleEvidenceError(
                    "RuleSourcePackage source-conflict evidence and blocked semantic status "
                    "must coincide."
                )


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RuleEvidenceError(f"RuleEvidenceRecord {field_name} must be non-empty stripped text.")
    return value


def _validate_optional_text(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_text(field_name, value)


def _validate_text_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise RuleEvidenceError(f"RuleEvidenceRecord {field_name} must be a tuple.")
    values = tuple(_validate_text(field_name, item) for item in cast(tuple[object, ...], value))
    if len(values) != len(set(values)):
        raise RuleEvidenceError(f"RuleEvidenceRecord {field_name} must be unique.")
    return values


def _validate_literal(field_name: str, value: object, allowed: set[str]) -> str:
    if type(value) is not str or value not in allowed:
        raise RuleEvidenceError(f"RuleEvidenceRecord {field_name} is unsupported.")
    return value


def _validate_optional_observed_at(value: object) -> str | None:
    if value is None:
        return None
    observed_at = _validate_text("observed_at", value)
    try:
        parsed = datetime.fromisoformat(observed_at)
    except ValueError as exc:
        raise RuleEvidenceError(
            "RuleEvidenceRecord observed_at must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuleEvidenceError("RuleEvidenceRecord observed_at must include a UTC offset.")
    return observed_at


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RuleEvidenceError(
            f"RuleEvidenceRecord {field_name} must be a lowercase SHA-256 digest."
        )
    return value


def _validate_optional_sha256(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_sha256(field_name, value)


def _validate_capture_artifact_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or not path.parts
        or ":" in value
        or "\\" in value
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise RuleEvidenceError(
            "Official App capture_artifact_path must be a normalized relative POSIX path."
        )
    return value


def _validate_mirror_provider(
    *,
    provider_name: str,
    source_url: str,
    authority: RuleEvidenceAuthority,
    project_authority_policy_id: str | None,
) -> None:
    if provider_name not in _MAINTAINED_APP_MIRROR_PROVIDERS:
        raise RuleEvidenceError("A maintained App-mirror provider is unsupported.")
    if authority == "project_authoritative_app_mirror":
        if project_authority_policy_id == CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID:
            if provider_name != "40k.app":
                raise RuleEvidenceError(
                    "The historical 40k.app-only policy cannot authorize another provider."
                )
        elif project_authority_policy_id != CORE_RULES_MAINTAINED_MIRROR_POLICY_ID:
            raise RuleEvidenceError("A maintained App-mirror authority policy ID is unsupported.")
    _validate_mirror_url(provider_name=provider_name, source_url=source_url)


def _validate_mirror_url(*, provider_name: str, source_url: str) -> None:
    has_ascii_control = any(
        ord(character) < 32 or ord(character) == 127 for character in source_url
    )
    split = urlsplit(source_url)
    common_invalid = (
        has_ascii_control
        or split.scheme != "https"
        or split.username is not None
        or split.password is not None
        or split.port is not None
        or bool(split.query)
        or bool(split.fragment)
    )
    if provider_name == "40k.app":
        rule_slug = split.path.removeprefix("/rules/")
        valid_path = split.path == "/rules" or (
            split.path == f"/rules/{rule_slug}"
            and bool(rule_slug)
            and rule_slug[0] != "-"
            and rule_slug[-1] != "-"
            and "--" not in rule_slug
            and all(character in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in rule_slug)
        )
        if common_invalid or split.hostname != "www.40k.app" or not valid_path:
            raise RuleEvidenceError("A 40k.app mirror record must use a canonical HTTPS rules URL.")
        return
    if (
        common_invalid
        or split.hostname != "game-datamissions.com"
        or split.path != "/11th/rules/changelog"
    ):
        raise RuleEvidenceError(
            "A Game Datamissions mirror record must use its canonical HTTPS Core Rules "
            "changelog URL."
        )


def _validate_co_versioned_mirror_agreement(
    records: tuple[RuleEvidenceRecord, ...],
) -> None:
    groups: dict[tuple[str, str], list[RuleEvidenceRecord]] = {}
    for record in records:
        if (
            record.evidence_kind != "third_party_mirror"
            or record.authority != "project_authoritative_app_mirror"
            or record.app_version is None
        ):
            continue
        groups.setdefault((record.rule_source_id, record.app_version), []).append(record)
    for version_records in groups.values():
        if len({record.provider_name for record in version_records}) < 2:
            continue
        if len({record.transcription_sha256 for record in version_records}) != 1:
            raise RuleEvidenceError(
                "Co-versioned maintained App mirrors disagree; official-App comparison is "
                "required before source certification."
            )


__all__ = (
    "CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID",
    "CORE_RULES_MAINTAINED_MIRROR_POLICY_ID",
    "LoadSupportStatus",
    "RuleEvidenceAuthority",
    "RuleEvidenceError",
    "RuleEvidenceKind",
    "RuleEvidencePayload",
    "RuleEvidenceRecord",
    "RuleSourcePackage",
    "RuleVerificationStatus",
    "SemanticExecutionStatus",
    "SourceEvidenceCatalog",
)
