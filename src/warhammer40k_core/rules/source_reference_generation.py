from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
)
from warhammer40k_core.rules.parsed_tokens import ParsedRuleText, ParsedRuleTextPayload
from warhammer40k_core.rules.source_catalog import SourceArtifactHash, SourceArtifactHashPayload
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    SourceTextRef,
    SourceTextRefPayload,
)
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow, WahapediaJsonArtifact


class SourceReferenceError(ValueError):
    """Raised when generated source references violate CORE V2 invariants."""


class SourceTextReferencePayload(TypedDict):
    source_text_id: str
    source_ref: SourceTextRefPayload
    raw_text: str
    sanitized_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleTextPayload


class SourceReferenceCatalogPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    target_edition: str
    source_artifacts: list[SourceArtifactHashPayload]
    source_texts: list[SourceTextReferencePayload]
    schema_version: str
    catalog_hash: str


SourceArtifact = WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact


@dataclass(frozen=True, slots=True)
class SourceTextReference:
    source_ref: SourceTextRef
    raw_text: str
    sanitized_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleText

    def __post_init__(self) -> None:
        if type(self.source_ref) is not SourceTextRef:
            raise SourceReferenceError("SourceTextReference source_ref must be SourceTextRef.")
        if type(self.raw_text) is not str:
            raise SourceReferenceError("SourceTextReference raw_text must be a string.")
        if type(self.sanitized_text) is not str:
            raise SourceReferenceError("SourceTextReference sanitized_text must be a string.")
        if type(self.normalized_text) is not str:
            raise SourceReferenceError("SourceTextReference normalized_text must be a string.")
        if type(self.parsed_tokens) is not ParsedRuleText:
            raise SourceReferenceError("SourceTextReference parsed_tokens must be ParsedRuleText.")
        if self.parsed_tokens.normalized_text != self.normalized_text:
            raise SourceReferenceError(
                "SourceTextReference parsed tokens must match normalized_text."
            )

    @property
    def source_text_id(self) -> str:
        return self.source_ref.source_text_id

    def to_payload(self) -> SourceTextReferencePayload:
        return {
            "source_text_id": self.source_text_id,
            "source_ref": self.source_ref.to_payload(),
            "raw_text": self.raw_text,
            "sanitized_text": self.sanitized_text,
            "normalized_text": self.normalized_text,
            "parsed_tokens": self.parsed_tokens.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: SourceTextReferencePayload) -> Self:
        return cls(
            source_ref=SourceTextRef.from_payload(payload["source_ref"]),
            raw_text=payload["raw_text"],
            sanitized_text=payload["sanitized_text"],
            normalized_text=payload["normalized_text"],
            parsed_tokens=ParsedRuleText.from_payload(payload["parsed_tokens"]),
        )


@dataclass(frozen=True, slots=True)
class SourceReferenceCatalog:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    target_edition: str
    source_artifacts: tuple[SourceArtifactHash, ...]
    source_texts: tuple[SourceTextReference, ...]
    schema_version: str = "phase17-source-reference-v1"

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise SourceReferenceError("SourceReferenceCatalog package_id must be DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise SourceReferenceError(
                "SourceReferenceCatalog catalog_version must be CatalogVersion."
            )
        object.__setattr__(
            self,
            "target_edition",
            _validate_identifier("SourceReferenceCatalog target_edition", self.target_edition),
        )
        object.__setattr__(
            self,
            "source_artifacts",
            _validate_source_artifact_hash_tuple(self.source_artifacts),
        )
        object.__setattr__(
            self,
            "source_texts",
            _validate_source_text_reference_tuple(self.source_texts),
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("SourceReferenceCatalog schema_version", self.schema_version),
        )

    def source_text_by_id(self, source_text_id: str) -> SourceTextReference:
        requested_id = _validate_identifier("source_text_id", source_text_id)
        for source_text in self.source_texts:
            if source_text.source_text_id == requested_id:
                return source_text
        raise SourceReferenceError("SourceReferenceCatalog source_text_id was not found.")

    def catalog_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()

    def to_payload(self) -> SourceReferenceCatalogPayload:
        payload = self._payload_without_hash()
        payload["catalog_hash"] = self.catalog_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: SourceReferenceCatalogPayload) -> Self:
        catalog = cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            target_edition=payload["target_edition"],
            source_artifacts=tuple(
                SourceArtifactHash(
                    artifact_name=artifact["artifact_name"],
                    artifact_hash=artifact["artifact_hash"],
                )
                for artifact in payload["source_artifacts"]
            ),
            source_texts=tuple(
                SourceTextReference.from_payload(source_text)
                for source_text in payload["source_texts"]
            ),
            schema_version=payload["schema_version"],
        )
        if payload["catalog_hash"] != catalog.catalog_hash():
            raise SourceReferenceError("SourceReferenceCatalog catalog_hash is stale.")
        return catalog

    def _payload_without_hash(self) -> SourceReferenceCatalogPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "target_edition": self.target_edition,
            "source_artifacts": [artifact.to_payload() for artifact in self.source_artifacts],
            "source_texts": [source_text.to_payload() for source_text in self.source_texts],
            "schema_version": self.schema_version,
            "catalog_hash": "",
        }


def build_source_reference_catalog(
    *,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    target_edition: str,
    source_artifacts: tuple[SourceArtifact, ...],
) -> SourceReferenceCatalog:
    if type(package_id) is not DataPackageId:
        raise SourceReferenceError("package_id must be DataPackageId.")
    if type(catalog_version) is not CatalogVersion:
        raise SourceReferenceError("catalog_version must be CatalogVersion.")
    if type(source_artifacts) is not tuple:
        raise SourceReferenceError("source_artifacts must be a tuple.")
    if not source_artifacts:
        raise SourceReferenceError("source_artifacts must not be empty.")
    references: list[SourceTextReference] = []
    for artifact in source_artifacts:
        if type(artifact) not in {
            WahapediaJsonArtifact,
            PatchedSourceArtifact,
            OverlaySourceArtifact,
        }:
            raise SourceReferenceError("source_artifacts must contain source artifacts.")
        for row in artifact.rows:
            references.extend(_source_text_references_from_row(row))
    if not references:
        raise SourceReferenceError("source_artifacts must include source text fields.")
    return SourceReferenceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        target_edition=target_edition,
        source_artifacts=_source_artifact_hashes(source_artifacts),
        source_texts=tuple(references),
    )


def _source_text_references_from_row(row: NormalizedSourceRow) -> tuple[SourceTextReference, ...]:
    return tuple(
        SourceTextReference(
            source_ref=SourceTextRef.from_text_field(row=row, text_field=text_field),
            raw_text=text_field.raw_text,
            sanitized_text=text_field.sanitized_text,
            normalized_text=text_field.normalized_text,
            parsed_tokens=text_field.parsed_tokens,
        )
        for text_field in row.text_fields
    )


def _source_artifact_hashes(
    source_artifacts: tuple[SourceArtifact, ...],
) -> tuple[SourceArtifactHash, ...]:
    hashes: list[SourceArtifactHash] = []
    for artifact in source_artifacts:
        if type(artifact) is WahapediaJsonArtifact:
            hashes.append(artifact.source_artifact_hash())
        elif type(artifact) is PatchedSourceArtifact or type(artifact) is OverlaySourceArtifact:
            hashes.append(artifact.source_artifact_hash_record())
        else:
            raise SourceReferenceError("Unsupported source artifact type.")
    return tuple(sorted(hashes, key=lambda item: item.artifact_name))


def _validate_source_text_reference_tuple(
    values: tuple[SourceTextReference, ...],
) -> tuple[SourceTextReference, ...]:
    if type(values) is not tuple:
        raise SourceReferenceError("SourceReferenceCatalog source_texts must be a tuple.")
    if not values:
        raise SourceReferenceError("SourceReferenceCatalog source_texts must not be empty.")
    seen: set[str] = set()
    references: list[SourceTextReference] = []
    for value in values:
        if type(value) is not SourceTextReference:
            raise SourceReferenceError(
                "SourceReferenceCatalog source_texts must contain SourceTextReference values."
            )
        if value.source_text_id in seen:
            raise SourceReferenceError(
                "SourceReferenceCatalog source_texts must not duplicate source_text_id."
            )
        seen.add(value.source_text_id)
        references.append(value)
    return tuple(sorted(references, key=lambda item: item.source_text_id))


def _validate_source_artifact_hash_tuple(
    values: tuple[SourceArtifactHash, ...],
) -> tuple[SourceArtifactHash, ...]:
    if type(values) is not tuple:
        raise SourceReferenceError("SourceReferenceCatalog source_artifacts must be a tuple.")
    if not values:
        raise SourceReferenceError("SourceReferenceCatalog source_artifacts must not be empty.")
    seen: set[str] = set()
    hashes: list[SourceArtifactHash] = []
    for value in values:
        if type(value) is not SourceArtifactHash:
            raise SourceReferenceError(
                "SourceReferenceCatalog source_artifacts must contain SourceArtifactHash values."
            )
        if value.artifact_name in seen:
            raise SourceReferenceError(
                "SourceReferenceCatalog source_artifacts must not duplicate artifact names."
            )
        seen.add(value.artifact_name)
        hashes.append(value)
    return tuple(sorted(hashes, key=lambda item: item.artifact_name))


_validate_identifier = IdentifierValidator(SourceReferenceError)


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise SourceReferenceError("DataPackageId payload is invalid.") from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise SourceReferenceError("CatalogVersion payload is invalid.") from exc


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
