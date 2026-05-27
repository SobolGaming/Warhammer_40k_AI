from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Self, TypedDict

from warhammer40k_core.core.ruleset import RulesetId, RulesetIdPayload


class DataPackageError(ValueError):
    """Raised when source package identity data violates CORE V2 invariants."""


class DataPackageIdPayload(TypedDict):
    namespace: str
    package_name: str
    version: str


class CatalogVersionPayload(TypedDict):
    version_id: str
    source_date: str


class SourceDocumentIdPayload(TypedDict):
    package_id: DataPackageIdPayload
    document_id: str


class RulesetBundlePayload(TypedDict):
    bundle_id: str
    ruleset_id: RulesetIdPayload
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    source_document_ids: list[SourceDocumentIdPayload]


@dataclass(frozen=True, slots=True)
class DataPackageId:
    namespace: str
    package_name: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "namespace",
            _validate_identifier("DataPackageId namespace", self.namespace),
        )
        object.__setattr__(
            self,
            "package_name",
            _validate_identifier("DataPackageId package_name", self.package_name),
        )
        object.__setattr__(
            self,
            "version",
            _validate_identifier("DataPackageId version", self.version),
        )

    def stable_identity(self) -> str:
        return f"data-package:{self.namespace}:{self.package_name}:{self.version}"

    def to_payload(self) -> DataPackageIdPayload:
        return {
            "namespace": self.namespace,
            "package_name": self.package_name,
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: DataPackageIdPayload) -> Self:
        return cls(
            namespace=payload["namespace"],
            package_name=payload["package_name"],
            version=payload["version"],
        )


@dataclass(frozen=True, slots=True)
class CatalogVersion:
    version_id: str
    source_date: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "version_id",
            _validate_identifier("CatalogVersion version_id", self.version_id),
        )
        object.__setattr__(
            self,
            "source_date",
            _validate_source_date("CatalogVersion source_date", self.source_date),
        )

    @classmethod
    def dated(cls, *, version_id: str, source_date: date) -> Self:
        return cls(version_id=version_id, source_date=source_date.isoformat())

    def stable_identity(self) -> str:
        return f"catalog-version:{self.version_id}:{self.source_date}"

    def to_payload(self) -> CatalogVersionPayload:
        return {
            "version_id": self.version_id,
            "source_date": self.source_date,
        }

    @classmethod
    def from_payload(cls, payload: CatalogVersionPayload) -> Self:
        return cls(version_id=payload["version_id"], source_date=payload["source_date"])


@dataclass(frozen=True, slots=True)
class SourceDocumentId:
    package_id: DataPackageId
    document_id: str

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise DataPackageError("SourceDocumentId package_id must be a DataPackageId.")
        object.__setattr__(
            self,
            "document_id",
            _validate_identifier("SourceDocumentId document_id", self.document_id),
        )

    def stable_identity(self) -> str:
        return f"source-document:{self.package_id.stable_identity()}:{self.document_id}"

    def to_payload(self) -> SourceDocumentIdPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "document_id": self.document_id,
        }

    @classmethod
    def from_payload(cls, payload: SourceDocumentIdPayload) -> Self:
        return cls(
            package_id=DataPackageId.from_payload(payload["package_id"]),
            document_id=payload["document_id"],
        )


@dataclass(frozen=True, slots=True)
class RulesetBundle:
    bundle_id: str
    ruleset_id: RulesetId
    package_id: DataPackageId
    catalog_version: CatalogVersion
    source_document_ids: tuple[SourceDocumentId, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bundle_id",
            _validate_identifier("RulesetBundle bundle_id", self.bundle_id),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise DataPackageError("RulesetBundle ruleset_id must be a RulesetId.")
        if type(self.package_id) is not DataPackageId:
            raise DataPackageError("RulesetBundle package_id must be a DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise DataPackageError("RulesetBundle catalog_version must be a CatalogVersion.")
        source_document_ids = _validate_source_document_id_tuple(
            "RulesetBundle source_document_ids",
            self.source_document_ids,
        )
        for source_document_id in source_document_ids:
            if source_document_id.package_id != self.package_id:
                raise DataPackageError(
                    "RulesetBundle source document packages must match package_id."
                )
        object.__setattr__(
            self,
            "source_document_ids",
            tuple(sorted(source_document_ids, key=lambda value: value.stable_identity())),
        )

    def stable_identity(self) -> str:
        return f"ruleset-bundle:{self.bundle_id}"

    def to_payload(self) -> RulesetBundlePayload:
        return {
            "bundle_id": self.bundle_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "source_document_ids": [
                source_document_id.to_payload() for source_document_id in self.source_document_ids
            ],
        }

    @classmethod
    def from_payload(cls, payload: RulesetBundlePayload) -> Self:
        return cls(
            bundle_id=payload["bundle_id"],
            ruleset_id=RulesetId.from_payload(payload["ruleset_id"]),
            package_id=DataPackageId.from_payload(payload["package_id"]),
            catalog_version=CatalogVersion.from_payload(payload["catalog_version"]),
            source_document_ids=tuple(
                SourceDocumentId.from_payload(source_document_id)
                for source_document_id in payload["source_document_ids"]
            ),
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DataPackageError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DataPackageError(f"{field_name} must not be empty.")
    return stripped


def _validate_source_date(field_name: str, value: object) -> str:
    if type(value) is date:
        return value.isoformat()
    source_date = _validate_identifier(field_name, value)
    try:
        date.fromisoformat(source_date)
    except ValueError as exc:
        raise DataPackageError(f"{field_name} must be an ISO date.") from exc
    return source_date


def _validate_source_document_id_tuple(
    field_name: str,
    values: tuple[SourceDocumentId, ...],
) -> tuple[SourceDocumentId, ...]:
    if type(values) is not tuple:
        raise DataPackageError(f"{field_name} must be a tuple.")
    if not values:
        raise DataPackageError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[SourceDocumentId] = []
    for value in values:
        if type(value) is not SourceDocumentId:
            raise DataPackageError(f"{field_name} must contain SourceDocumentId values.")
        stable_identity = value.stable_identity()
        if stable_identity in seen:
            raise DataPackageError(f"{field_name} must not contain duplicates.")
        seen.add(stable_identity)
        validated.append(value)
    return tuple(validated)
