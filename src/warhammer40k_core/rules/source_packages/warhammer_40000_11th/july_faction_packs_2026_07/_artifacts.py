from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Set
from typing import Final, cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator

JULY_FACTION_PACK_PACKAGE_SCHEMA: Final = "core-v2-july-faction-pack-staging-package-v1"
JULY_FACTION_PACK_LEDGER_SCHEMA: Final = "core-v2-july-faction-pack-delta-ledger-v1"
JULY_FACTION_PACK_SOURCE_PACKAGE_ID: Final = "gw-11e-staged-faction-packs-2026-07"
JULY_FACTION_PACK_SOURCE_DATE: Final = "2026-07-22"
JULY_FACTION_PACK_ACTIVATION_STATUS: Final = "staged"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[-:._][a-z0-9]+)*$")
_ARTIFACT_PATH_RE = re.compile(r"^artifacts/[a-z0-9][a-z0-9._/-]*\.json$")
_SUCCESSOR_PACKAGE_SUFFIX = "-faction-pack-2026-07"
_PREDECESSOR_PACKAGE_SUFFIX = "-faction-pack-2026-06"
_APPROVED_DISPOSITIONS = frozenset(
    {
        "rules_updates_already_applied",
        "in_scope_source_only",
        "in_scope_runtime_affected",
        "excluded_imperial_armour",
        "excluded_legends",
    }
)
_APPROVED_REFERENCE_KINDS = frozenset(
    {
        "phase17e_descriptor_id",
        "source_row_id",
        "datasheet_id",
        "datasheet_ability_id",
    }
)
_EXPECTED_FACTION_IDS = frozenset(
    {
        "adepta-sororitas",
        "adeptus-custodes",
        "adeptus-mechanicus",
        "aeldari",
        "astra-militarum",
        "black-templars",
        "blood-angels",
        "chaos-daemons",
        "chaos-knights",
        "chaos-space-marines",
        "dark-angels",
        "death-guard",
        "drukhari",
        "emperors-children",
        "genestealer-cults",
        "grey-knights",
        "imperial-agents",
        "imperial-knights",
        "leagues-of-votann",
        "necrons",
        "orks",
        "space-marines",
        "space-wolves",
        "tau-empire",
        "thousand-sons",
        "tyranids",
        "world-eaters",
    }
)


class JulyFactionPackStagingError(ValueError):
    """Raised when staged July faction-pack data violates CORE V2 invariants."""


class StagedPredecessorArtifact(msgspec.Struct, frozen=True):
    source_package_id: str
    source_date: str
    source_payload_checksum_sha256: str

    def validate(self) -> None:
        _validate_identifier("predecessor source_package_id", self.source_package_id)
        if self.source_date != "2026-06-11" and not (
            self.source_package_id == "gw-11e-phase17e-exact-faction-subrules-2026-27"
            and self.source_date == "2026-06-21"
        ):
            raise JulyFactionPackStagingError(
                "Staged predecessor source_date does not match the active June package."
            )
        _validate_sha256(
            "predecessor source_payload_checksum_sha256",
            self.source_payload_checksum_sha256,
        )


class StagedArtifactReference(msgspec.Struct, frozen=True):
    artifact_id: str
    artifact_path: str
    artifact_sha256: str

    def validate(self) -> None:
        _validate_identifier("staged artifact_id", self.artifact_id)
        _validate_artifact_path(self.artifact_path)
        _validate_sha256("staged artifact_sha256", self.artifact_sha256)


class StablePredecessorReference(msgspec.Struct, frozen=True):
    reference_kind: str
    reference_id: str

    def validate(self) -> None:
        if self.reference_kind not in _APPROVED_REFERENCE_KINDS:
            raise JulyFactionPackStagingError(
                "July faction-pack predecessor reference kind is unsupported."
            )
        _validate_identifier("predecessor reference_id", self.reference_id)


class JulyReviewItemArtifact(msgspec.Struct, frozen=True):
    item_id: str
    name: str
    disposition: str
    predecessor_references: list[StablePredecessorReference]

    def validate(self) -> None:
        _validate_identifier("review item_id", self.item_id)
        _validate_text("review item name", self.name)
        if self.disposition not in _APPROVED_DISPOSITIONS:
            raise JulyFactionPackStagingError(
                "July faction-pack review disposition is unsupported."
            )
        seen_references: set[tuple[str, str]] = set()
        for reference in self.predecessor_references:
            reference.validate()
            key = (reference.reference_kind, reference.reference_id)
            if key in seen_references:
                raise JulyFactionPackStagingError(
                    "July faction-pack review item repeats a predecessor reference."
                )
            seen_references.add(key)
        if self.disposition == "in_scope_runtime_affected" and not self.predecessor_references:
            raise JulyFactionPackStagingError(
                "Runtime-affected July review items require a stable predecessor reference."
            )


class JulyPackReviewArtifact(msgspec.Struct, frozen=True):
    faction_id: str
    faction_name: str
    successor_package_id: str
    successor_pdf_sha256: str
    successor_pdf_path: str
    predecessor_package_id: str
    predecessor_pdf_sha256: str
    review_items: list[JulyReviewItemArtifact]

    def validate(self) -> None:
        _validate_identifier("review faction_id", self.faction_id)
        _validate_text("review faction_name", self.faction_name)
        _validate_identifier("successor_package_id", self.successor_package_id)
        _validate_identifier("predecessor_package_id", self.predecessor_package_id)
        _validate_sha256("successor_pdf_sha256", self.successor_pdf_sha256)
        _validate_sha256("predecessor_pdf_sha256", self.predecessor_pdf_sha256)
        _validate_pdf_path(self.successor_pdf_path)
        expected_successor_id = f"gw-11e-{self.faction_id}{_SUCCESSOR_PACKAGE_SUFFIX}"
        expected_predecessor_id = f"gw-11e-{self.faction_id}{_PREDECESSOR_PACKAGE_SUFFIX}"
        if self.successor_package_id != expected_successor_id:
            raise JulyFactionPackStagingError(
                "July faction-pack successor package does not match faction_id."
            )
        if self.predecessor_package_id != expected_predecessor_id:
            raise JulyFactionPackStagingError(
                "July faction-pack predecessor package does not match faction_id."
            )
        if not self.review_items:
            raise JulyFactionPackStagingError(
                "Every pending July faction pack requires one or more review items."
            )
        seen_item_ids: set[str] = set()
        for item in self.review_items:
            item.validate()
            if item.item_id in seen_item_ids:
                raise JulyFactionPackStagingError(
                    "July faction-pack review item IDs must be unique within a pack."
                )
            seen_item_ids.add(item.item_id)


class JulyDeltaLedgerArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    ledger_id: str
    source_package_id: str
    source_date: str
    pack_reviews: list[JulyPackReviewArtifact]

    def validate(self) -> None:
        if self.artifact_schema != JULY_FACTION_PACK_LEDGER_SCHEMA:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger artifact schema is unsupported."
            )
        _validate_identifier("ledger_id", self.ledger_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger source package identity is stale."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger source date is stale."
            )
        faction_ids: set[str] = set()
        successor_package_ids: set[str] = set()
        predecessor_package_ids: set[str] = set()
        for review in self.pack_reviews:
            review.validate()
            if review.faction_id in faction_ids:
                raise JulyFactionPackStagingError(
                    "Every pending July faction pack must have exactly one review row."
                )
            if review.successor_package_id in successor_package_ids:
                raise JulyFactionPackStagingError("July successor package IDs must be unique.")
            if review.predecessor_package_id in predecessor_package_ids:
                raise JulyFactionPackStagingError("June predecessor package IDs must be unique.")
            faction_ids.add(review.faction_id)
            successor_package_ids.add(review.successor_package_id)
            predecessor_package_ids.add(review.predecessor_package_id)
        if frozenset(faction_ids) != _EXPECTED_FACTION_IDS:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger must cover the exact 27-faction set."
            )


class JulyStagingPackageArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    activation_status: str
    predecessor_artifacts: list[StagedPredecessorArtifact]
    delta_ledger_artifact: str
    delta_ledger_sha256: str
    staged_data_artifacts: list[StagedArtifactReference]

    def validate(self) -> None:
        if self.artifact_schema != JULY_FACTION_PACK_PACKAGE_SCHEMA:
            raise JulyFactionPackStagingError(
                "July faction-pack staging package artifact schema is unsupported."
            )
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July faction-pack staging source package identity is stale."
            )
        _validate_text("source_title", self.source_title)
        _validate_identifier("source_version", self.source_version)
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July faction-pack staging source date is stale.")
        if self.activation_status != JULY_FACTION_PACK_ACTIVATION_STATUS:
            raise JulyFactionPackStagingError(
                "July faction-pack successor must remain staged before promotion."
            )
        if self.delta_ledger_artifact != "artifacts/delta-ledger.json":
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger artifact path is unexpected."
            )
        _validate_artifact_path(self.delta_ledger_artifact)
        _validate_sha256("delta_ledger_sha256", self.delta_ledger_sha256)
        predecessor_ids: set[str] = set()
        for predecessor in self.predecessor_artifacts:
            predecessor.validate()
            if predecessor.source_package_id in predecessor_ids:
                raise JulyFactionPackStagingError(
                    "July staging package repeats a predecessor package identity."
                )
            predecessor_ids.add(predecessor.source_package_id)
        expected_predecessors = {
            "gw-11e-faction-detachments-2026-27",
            "gw-11e-phase17e-exact-faction-subrules-2026-27",
            "gw-11e-phase17e-faction-coverage-2026-27",
            "gw-11e-phase17f-faction-execution-2026-27",
        }
        if predecessor_ids != expected_predecessors:
            raise JulyFactionPackStagingError(
                "July staging package must link the exact active June source packages."
            )
        seen_artifact_ids: set[str] = set()
        seen_artifact_paths: set[str] = set()
        for artifact in self.staged_data_artifacts:
            artifact.validate()
            if artifact.artifact_id in seen_artifact_ids:
                raise JulyFactionPackStagingError("July staged artifact IDs must be unique.")
            if artifact.artifact_path in seen_artifact_paths:
                raise JulyFactionPackStagingError("July staged artifact paths must be unique.")
            seen_artifact_ids.add(artifact.artifact_id)
            seen_artifact_paths.add(artifact.artifact_path)

    def source_payload_checksum_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(msgspec.to_builtins(self))).hexdigest()


def july_staging_package_from_json_bytes(raw: bytes) -> JulyStagingPackageArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyStagingPackageArtifact,
        artifact_description="staging package",
    )
    artifact.validate()
    return artifact


def july_delta_ledger_from_json_bytes(raw: bytes) -> JulyDeltaLedgerArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyDeltaLedgerArtifact,
        artifact_description="delta ledger",
    )
    artifact.validate()
    return artifact


def canonical_json_sha256_from_bytes(raw: bytes) -> str:
    try:
        payload = cast(object, json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JulyFactionPackStagingError(
            "July faction-pack artifact is not valid UTF-8 JSON."
        ) from exc
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def audit_manifest_links(
    *,
    ledger: JulyDeltaLedgerArtifact,
    pending_packages: Mapping[str, tuple[str, str]],
    current_packages: Mapping[str, tuple[str, str]],
) -> None:
    if type(ledger) is not JulyDeltaLedgerArtifact:
        raise JulyFactionPackStagingError(
            "July manifest-link audit requires a delta ledger artifact."
        )
    pending = _validate_manifest_mapping("pending_packages", pending_packages)
    current = _validate_manifest_mapping("current_packages", current_packages)
    ledger_successors = {review.successor_package_id for review in ledger.pack_reviews}
    if set(pending) != ledger_successors:
        raise JulyFactionPackStagingError(
            "Every pending July faction pack must have exactly one ledger review row."
        )
    expected_current_ids = {review.predecessor_package_id for review in ledger.pack_reviews}
    deathwatch_package_id = "gw-11e-deathwatch-faction-pack-2026-06"
    if set(current) != expected_current_ids | {deathwatch_package_id}:
        raise JulyFactionPackStagingError(
            "July predecessor audit requires the exact active June package set."
        )
    for review in ledger.pack_reviews:
        successor_sha256, successor_path = pending[review.successor_package_id]
        predecessor_sha256, _predecessor_path = current[review.predecessor_package_id]
        if (successor_sha256, successor_path) != (
            review.successor_pdf_sha256,
            review.successor_pdf_path,
        ):
            raise JulyFactionPackStagingError(
                "July successor package hash or path drifted from the pending manifest."
            )
        if predecessor_sha256 != review.predecessor_pdf_sha256:
            raise JulyFactionPackStagingError(
                "June predecessor package hash drifted from the current manifest."
            )


def audit_runtime_predecessor_references(
    *,
    ledger: JulyDeltaLedgerArtifact,
    stable_reference_ids_by_kind: Mapping[str, Set[str]],
) -> None:
    if type(ledger) is not JulyDeltaLedgerArtifact:
        raise JulyFactionPackStagingError(
            "July predecessor-reference audit requires a delta ledger artifact."
        )
    available: dict[str, Set[str]] = {}
    for kind, values in stable_reference_ids_by_kind.items():
        if kind not in _APPROVED_REFERENCE_KINDS:
            raise JulyFactionPackStagingError(
                "Stable predecessor reference audit received an unsupported kind."
            )
        available[kind] = values
    for review in ledger.pack_reviews:
        for item in review.review_items:
            if item.disposition != "in_scope_runtime_affected":
                continue
            for reference in item.predecessor_references:
                if reference.reference_id not in available.get(
                    reference.reference_kind, frozenset()
                ):
                    raise JulyFactionPackStagingError(
                        "Runtime-affected July review item has no stable predecessor row."
                    )


def _decode_json_artifact[ArtifactT](
    raw: bytes,
    artifact_type: type[ArtifactT],
    *,
    artifact_description: str,
) -> ArtifactT:
    try:
        return msgspec.json.decode(raw, type=artifact_type)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError(
            f"July faction-pack {artifact_description} artifact is invalid."
        ) from exc


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_manifest_mapping(
    field_name: str,
    value: object,
) -> dict[str, tuple[str, str]]:
    if not isinstance(value, Mapping):
        raise JulyFactionPackStagingError(f"{field_name} must be a mapping.")
    validated: dict[str, tuple[str, str]] = {}
    for raw_package_id, raw_identity in cast(Mapping[object, object], value).items():
        package_id = _validate_identifier("manifest package_id", raw_package_id)
        if type(raw_identity) is not tuple:
            raise JulyFactionPackStagingError(
                "Manifest identity values must be (sha256, local path) tuples."
            )
        identity = cast(tuple[object, ...], raw_identity)
        if len(identity) != 2 or type(identity[0]) is not str or type(identity[1]) is not str:
            raise JulyFactionPackStagingError(
                "Manifest identity values must be (sha256, local path) tuples."
            )
        sha256 = _validate_sha256("manifest sha256", identity[0])
        path = identity[1]
        _validate_pdf_path(path)
        validated[package_id] = (sha256, path)
    return validated


_validate_identifier = IdentifierValidator(
    JulyFactionPackStagingError,
    pattern=_IDENTIFIER_RE,
    pattern_message="July faction-pack {field_name} must be a stable identifier.",
)


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise JulyFactionPackStagingError(
            f"July faction-pack {field_name} must be non-empty normalized text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise JulyFactionPackStagingError(
            f"July faction-pack {field_name} must be a lowercase SHA-256."
        )
    return value


def _validate_artifact_path(value: object) -> str:
    if (
        type(value) is not str
        or "\\" in value
        or ".." in value.split("/")
        or _ARTIFACT_PATH_RE.fullmatch(value) is None
    ):
        raise JulyFactionPackStagingError(
            "July faction-pack artifact path must be normalized package JSON."
        )
    return value


def _validate_pdf_path(value: object) -> str:
    if (
        type(value) is not str
        or "\\" in value
        or ".." in value.split("/")
        or not value.startswith("data/raw/faction_packs/eng_")
        or not value.endswith(".pdf")
    ):
        raise JulyFactionPackStagingError(
            "July faction-pack PDF path must be a normalized raw source path."
        )
    return value
