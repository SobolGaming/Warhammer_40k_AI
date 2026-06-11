from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self, TypedDict

from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
    RulesetBundle,
    RulesetBundlePayload,
    SourceDocumentId,
    SourceDocumentIdPayload,
)
from warhammer40k_core.rules.source_data import (
    RuleSourceText,
    RuleSourceTextPayload,
    SourceDataError,
)


class SourceCatalogError(ValueError):
    """Raised when source catalog data violates CORE V2 invariants."""


class SourceDocumentPayload(TypedDict):
    document_id: SourceDocumentIdPayload
    title: str
    source_texts: list[RuleSourceTextPayload]


class SourceFileChecksumPayload(TypedDict):
    path: str
    checksum_sha256: str
    size_bytes: int


class SourceArtifactHashPayload(TypedDict):
    artifact_name: str
    artifact_hash: str


class SourcePackageManifestPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    upstream_identity: str
    source_edition: str
    source_files: list[SourceFileChecksumPayload]
    artifacts: list[SourceArtifactHashPayload]
    schema_version: str
    package_hash: str


class SourceCatalogPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    documents: list[SourceDocumentPayload]
    ruleset_bundles: list[RulesetBundlePayload]


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: SourceDocumentId
    title: str
    source_texts: tuple[RuleSourceText, ...]

    def __post_init__(self) -> None:
        if type(self.document_id) is not SourceDocumentId:
            raise SourceCatalogError("SourceDocument document_id must be a SourceDocumentId.")
        object.__setattr__(
            self,
            "title",
            _validate_identifier("SourceDocument title", self.title),
        )
        source_texts = _validate_rule_source_text_tuple(
            "SourceDocument source_texts",
            self.source_texts,
        )
        object.__setattr__(
            self,
            "source_texts",
            tuple(sorted(source_texts, key=lambda source_text: source_text.source_id)),
        )

    def source_text_by_id(self, source_id: str) -> RuleSourceText:
        requested_source_id = _validate_identifier("source_id", source_id)
        for source_text in self.source_texts:
            if source_text.source_id == requested_source_id:
                return source_text
        raise SourceCatalogError("SourceDocument source_id was not found.")

    def to_payload(self) -> SourceDocumentPayload:
        return {
            "document_id": self.document_id.to_payload(),
            "title": self.title,
            "source_texts": [source_text.to_payload() for source_text in self.source_texts],
        }

    @classmethod
    def from_payload(cls, payload: SourceDocumentPayload) -> Self:
        return cls(
            document_id=_source_document_id_from_payload(payload["document_id"]),
            title=payload["title"],
            source_texts=tuple(
                _rule_source_text_from_payload(source_text)
                for source_text in payload["source_texts"]
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceFileChecksum:
    path: str
    checksum_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "path",
            _validate_identifier("SourceFileChecksum path", self.path),
        )
        object.__setattr__(
            self,
            "checksum_sha256",
            _validate_sha256("SourceFileChecksum checksum_sha256", self.checksum_sha256),
        )
        if type(self.size_bytes) is not int:
            raise SourceCatalogError("SourceFileChecksum size_bytes must be an integer.")
        if self.size_bytes < 0:
            raise SourceCatalogError("SourceFileChecksum size_bytes must not be negative.")

    @classmethod
    def from_path(cls, *, root: object, path: object) -> Self:
        if not isinstance(root, Path):
            raise SourceCatalogError("SourceFileChecksum root must be a Path.")
        if not isinstance(path, Path):
            raise SourceCatalogError("SourceFileChecksum path must be a Path.")
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
            raise SourceCatalogError("SourceFileChecksum path must be inside root.")
        data = resolved_path.read_bytes()
        return cls(
            path=resolved_path.relative_to(resolved_root).as_posix(),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def stable_identity(self) -> str:
        return f"source-file:{self.path}:{self.checksum_sha256}:{self.size_bytes}"

    def to_payload(self) -> SourceFileChecksumPayload:
        return {
            "path": self.path,
            "checksum_sha256": self.checksum_sha256,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_payload(cls, payload: SourceFileChecksumPayload) -> Self:
        return cls(
            path=payload["path"],
            checksum_sha256=payload["checksum_sha256"],
            size_bytes=payload["size_bytes"],
        )


@dataclass(frozen=True, slots=True)
class SourceArtifactHash:
    artifact_name: str
    artifact_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_name",
            _validate_identifier("SourceArtifactHash artifact_name", self.artifact_name),
        )
        object.__setattr__(
            self,
            "artifact_hash",
            _validate_sha256("SourceArtifactHash artifact_hash", self.artifact_hash),
        )

    def stable_identity(self) -> str:
        return f"source-artifact:{self.artifact_name}:{self.artifact_hash}"

    def to_payload(self) -> SourceArtifactHashPayload:
        return {
            "artifact_name": self.artifact_name,
            "artifact_hash": self.artifact_hash,
        }

    @classmethod
    def from_payload(cls, payload: SourceArtifactHashPayload) -> Self:
        return cls(
            artifact_name=payload["artifact_name"],
            artifact_hash=payload["artifact_hash"],
        )


@dataclass(frozen=True, slots=True)
class SourcePackageManifest:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    upstream_identity: str
    source_edition: str
    source_files: tuple[SourceFileChecksum, ...]
    artifacts: tuple[SourceArtifactHash, ...] = ()
    schema_version: str = "phase17a-source-mirror-v1"

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise SourceCatalogError("SourcePackageManifest package_id must be a DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise SourceCatalogError(
                "SourcePackageManifest catalog_version must be a CatalogVersion."
            )
        object.__setattr__(
            self,
            "upstream_identity",
            _validate_identifier("SourcePackageManifest upstream_identity", self.upstream_identity),
        )
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier("SourcePackageManifest source_edition", self.source_edition),
        )
        object.__setattr__(
            self,
            "source_files",
            _validate_source_file_checksums(self.source_files),
        )
        object.__setattr__(
            self,
            "artifacts",
            _validate_source_artifact_hashes(self.artifacts),
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("SourcePackageManifest schema_version", self.schema_version),
        )

    def package_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_payload(self) -> SourcePackageManifestPayload:
        payload = self._payload_without_hash()
        payload["package_hash"] = self.package_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: SourcePackageManifestPayload) -> Self:
        manifest = cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            upstream_identity=payload["upstream_identity"],
            source_edition=payload["source_edition"],
            source_files=tuple(
                SourceFileChecksum.from_payload(source_file)
                for source_file in payload["source_files"]
            ),
            artifacts=tuple(
                SourceArtifactHash.from_payload(artifact) for artifact in payload["artifacts"]
            ),
            schema_version=payload["schema_version"],
        )
        if payload["package_hash"] != manifest.package_hash():
            raise SourceCatalogError("SourcePackageManifest package_hash is stale.")
        return manifest

    def _payload_without_hash(self) -> SourcePackageManifestPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "upstream_identity": self.upstream_identity,
            "source_edition": self.source_edition,
            "source_files": [source_file.to_payload() for source_file in self.source_files],
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "schema_version": self.schema_version,
            "package_hash": "",
        }


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    documents: tuple[SourceDocument, ...]
    ruleset_bundles: tuple[RulesetBundle, ...] = ()

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise SourceCatalogError("SourceCatalog package_id must be a DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise SourceCatalogError("SourceCatalog catalog_version must be a CatalogVersion.")
        documents = _validate_source_document_tuple("SourceCatalog documents", self.documents)
        ruleset_bundles = _validate_ruleset_bundle_tuple(
            "SourceCatalog ruleset_bundles",
            self.ruleset_bundles,
        )
        document_ids = {document.document_id.stable_identity() for document in documents}
        for document in documents:
            if document.document_id.package_id != self.package_id:
                raise SourceCatalogError("SourceCatalog document packages must match package_id.")
        for ruleset_bundle in ruleset_bundles:
            if ruleset_bundle.package_id != self.package_id:
                raise SourceCatalogError(
                    "SourceCatalog ruleset bundle packages must match package_id."
                )
            if ruleset_bundle.catalog_version != self.catalog_version:
                raise SourceCatalogError(
                    "SourceCatalog ruleset bundle versions must match catalog_version."
                )
            for source_document_id in ruleset_bundle.source_document_ids:
                if source_document_id.stable_identity() not in document_ids:
                    raise SourceCatalogError(
                        "SourceCatalog ruleset bundle references an unknown document."
                    )
        object.__setattr__(
            self,
            "documents",
            tuple(sorted(documents, key=lambda document: document.document_id.stable_identity())),
        )
        object.__setattr__(
            self,
            "ruleset_bundles",
            tuple(sorted(ruleset_bundles, key=lambda bundle: bundle.stable_identity())),
        )

    def source_text_by_id(self, source_id: str) -> RuleSourceText:
        requested_source_id = _validate_identifier("source_id", source_id)
        for document in self.documents:
            for source_text in document.source_texts:
                if source_text.source_id == requested_source_id:
                    return source_text
        raise SourceCatalogError("SourceCatalog source_id was not found.")

    def to_payload(self) -> SourceCatalogPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "documents": [document.to_payload() for document in self.documents],
            "ruleset_bundles": [bundle.to_payload() for bundle in self.ruleset_bundles],
        }

    @classmethod
    def from_payload(cls, payload: SourceCatalogPayload) -> Self:
        return cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            documents=tuple(
                SourceDocument.from_payload(document) for document in payload["documents"]
            ),
            ruleset_bundles=tuple(
                _ruleset_bundle_from_payload(bundle) for bundle in payload["ruleset_bundles"]
            ),
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise SourceCatalogError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise SourceCatalogError(f"{field_name} must not be empty.")
    return stripped


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise SourceCatalogError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise SourceCatalogError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return digest


def _validate_source_file_checksums(
    values: tuple[SourceFileChecksum, ...],
) -> tuple[SourceFileChecksum, ...]:
    if type(values) is not tuple:
        raise SourceCatalogError("SourcePackageManifest source_files must be a tuple.")
    if not values:
        raise SourceCatalogError("SourcePackageManifest source_files must not be empty.")
    seen: set[str] = set()
    validated: list[SourceFileChecksum] = []
    for value in values:
        if type(value) is not SourceFileChecksum:
            raise SourceCatalogError(
                "SourcePackageManifest source_files must contain SourceFileChecksum values."
            )
        if value.path in seen:
            raise SourceCatalogError("SourcePackageManifest source_files must be unique.")
        seen.add(value.path)
        validated.append(value)
    return tuple(sorted(validated, key=lambda source_file: source_file.path))


def _validate_source_artifact_hashes(
    values: tuple[SourceArtifactHash, ...],
) -> tuple[SourceArtifactHash, ...]:
    if type(values) is not tuple:
        raise SourceCatalogError("SourcePackageManifest artifacts must be a tuple.")
    seen: set[str] = set()
    validated: list[SourceArtifactHash] = []
    for value in values:
        if type(value) is not SourceArtifactHash:
            raise SourceCatalogError(
                "SourcePackageManifest artifacts must contain SourceArtifactHash values."
            )
        if value.artifact_name in seen:
            raise SourceCatalogError("SourcePackageManifest artifacts must be unique.")
        seen.add(value.artifact_name)
        validated.append(value)
    return tuple(sorted(validated, key=lambda artifact: artifact.artifact_name))


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validate_rule_source_text_tuple(
    field_name: str,
    values: tuple[RuleSourceText, ...],
) -> tuple[RuleSourceText, ...]:
    if type(values) is not tuple:
        raise SourceCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise SourceCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[RuleSourceText] = []
    for value in values:
        if type(value) is not RuleSourceText:
            raise SourceCatalogError(f"{field_name} must contain RuleSourceText values.")
        if value.source_id in seen:
            raise SourceCatalogError(f"{field_name} must not contain duplicate source IDs.")
        seen.add(value.source_id)
        validated.append(value)
    return tuple(validated)


def _validate_source_document_tuple(
    field_name: str,
    values: tuple[SourceDocument, ...],
) -> tuple[SourceDocument, ...]:
    if type(values) is not tuple:
        raise SourceCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise SourceCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[SourceDocument] = []
    for value in values:
        if type(value) is not SourceDocument:
            raise SourceCatalogError(f"{field_name} must contain SourceDocument values.")
        stable_identity = value.document_id.stable_identity()
        if stable_identity in seen:
            raise SourceCatalogError(f"{field_name} must not contain duplicate documents.")
        seen.add(stable_identity)
        validated.append(value)
    return tuple(validated)


def _validate_ruleset_bundle_tuple(
    field_name: str,
    values: tuple[RulesetBundle, ...],
) -> tuple[RulesetBundle, ...]:
    if type(values) is not tuple:
        raise SourceCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[RulesetBundle] = []
    for value in values:
        if type(value) is not RulesetBundle:
            raise SourceCatalogError(f"{field_name} must contain RulesetBundle values.")
        stable_identity = value.stable_identity()
        if stable_identity in seen:
            raise SourceCatalogError(f"{field_name} must not contain duplicate bundles.")
        seen.add(stable_identity)
        validated.append(value)
    return tuple(validated)


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise SourceCatalogError("SourceCatalog package_id payload is invalid.") from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise SourceCatalogError("SourceCatalog catalog_version payload is invalid.") from exc


def _source_document_id_from_payload(payload: SourceDocumentIdPayload) -> SourceDocumentId:
    try:
        return SourceDocumentId.from_payload(payload)
    except DataPackageError as exc:
        raise SourceCatalogError("SourceDocument document_id payload is invalid.") from exc


def _ruleset_bundle_from_payload(payload: RulesetBundlePayload) -> RulesetBundle:
    try:
        return RulesetBundle.from_payload(payload)
    except DataPackageError as exc:
        raise SourceCatalogError("SourceCatalog ruleset bundle payload is invalid.") from exc


def _rule_source_text_from_payload(payload: RuleSourceTextPayload) -> RuleSourceText:
    try:
        return RuleSourceText.from_payload(payload)
    except SourceDataError as exc:
        raise SourceCatalogError("SourceDocument source_text payload is invalid.") from exc
