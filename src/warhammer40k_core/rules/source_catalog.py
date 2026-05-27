from __future__ import annotations

from dataclasses import dataclass
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
