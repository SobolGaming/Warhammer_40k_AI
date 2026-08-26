from __future__ import annotations

import hashlib
import json
from dataclasses import InitVar, dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal, Self, TypedDict, cast
from urllib.parse import urlsplit

RuleEvidenceKind = Literal[
    "official_app_capture",
    "owner_supplied_app_transcription",
    "third_party_mirror",
]
RuleEvidenceAuthority = Literal[
    "official_primary",
    "unverified_transcription_only",
    "secondary_mirror_only",
]
RuleVerificationStatus = Literal[
    "official_corroborated",
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


class RuleEvidenceError(ValueError):
    """Raised when rule-evidence data overstates or corrupts its provenance."""


class RuleEvidencePayload(TypedDict):
    evidence_id: str
    rule_source_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str
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
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str
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
                "third_party_mirror",
            },
        )
        _validate_literal(
            "authority",
            self.authority,
            {
                "official_primary",
                "unverified_transcription_only",
                "secondary_mirror_only",
            },
        )
        _validate_literal(
            "verification_status",
            self.verification_status,
            {
                "official_corroborated",
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
        _validate_observed_at(self.observed_at)
        _validate_optional_text("source_url", self.source_url)
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
                or self.app_version is None
                or self.app_build is None
                or self.capture_artifact_path is None
                or self.capture_sha256 is None
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
        if self.evidence_kind == "owner_supplied_app_transcription":
            if (
                self.authority != "unverified_transcription_only"
                or self.verification_status != "unverified"
                or self.official_corroborating_source_ids
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
                    "An owner-supplied App transcription must remain unverified and uncaptured."
                )
            return
        if (
            self.authority != "secondary_mirror_only"
            or self.verification_status not in {"mirror_only", "not_observed_on_mirror", "conflict"}
            or self.provider_name != "40k.app"
            or self.source_platform != "Web"
            or self.source_url is None
            or any(
                value is not None
                for value in (
                    self.app_version,
                    self.app_build,
                    self.capture_artifact_path,
                    self.capture_sha256,
                )
            )
            or self.official_corroborating_source_ids
            or not self.provider_non_affiliation_recorded
        ):
            raise RuleEvidenceError(
                "A third-party mirror must retain secondary mirror authority without official "
                "corroboration or capture claims."
            )
        split = urlsplit(self.source_url)
        if (
            split.scheme != "https"
            or split.hostname != "www.40k.app"
            or split.username is not None
            or split.password is not None
            or split.port is not None
            or split.query
            or split.fragment
            or (split.path != "/rules" and not split.path.startswith("/rules/"))
        ):
            raise RuleEvidenceError("A 40k.app mirror record must use a canonical HTTPS rules URL.")

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
        if (self.verification_status == "conflict") != (
            self.semantic_execution_status == "blocked_by_source_conflict"
        ):
            raise RuleEvidenceError(
                "Conflicting source evidence and blocked semantic certification must coincide."
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


def _validate_observed_at(value: object) -> str:
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


__all__ = (
    "LoadSupportStatus",
    "RuleEvidenceAuthority",
    "RuleEvidenceError",
    "RuleEvidenceKind",
    "RuleEvidencePayload",
    "RuleEvidenceRecord",
    "RuleVerificationStatus",
    "SemanticExecutionStatus",
)
