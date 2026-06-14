from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
)
from warhammer40k_core.rules.html_sanitizer import sanitize_source_html
from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.text_normalization import (
    TextNormalizationError,
    normalize_structured_source_text,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
    SourceTextField,
    WahapediaJsonArtifact,
)


class SourcePatchError(ValueError):
    """Raised when transition patch data violates Phase 17A.1 invariants."""


class SourceTransitionPatchOperationFamily(StrEnum):
    APPEND_RULE_TEXT = "append_rule_text"
    REPLACE_RULE_TEXT = "replace_rule_text"
    ADD_KEYWORD = "add_keyword"
    REMOVE_KEYWORD = "remove_keyword"
    REPLACE_PROFILE_CHARACTERISTIC = "replace_profile_characteristic"
    REPLACE_WEAPON_CHARACTERISTIC = "replace_weapon_characteristic"
    REPLACE_DATASHEET_ABILITY = "replace_datasheet_ability"
    REPLACE_ENHANCEMENT_TEXT = "replace_enhancement_text"
    REPLACE_STRATAGEM_TEXT = "replace_stratagem_text"
    RECORD_FAQ_ANSWER = "record_faq_answer"
    MARK_UNSUPPORTED = "mark_unsupported"


class SourceFaqClassification(StrEnum):
    ADVISORY_ONLY = "advisory_only"
    EXECUTABLE_PATCH = "executable_patch"
    UNSUPPORTED_EXECUTABLE_CHANGE = "unsupported_executable_change"


class SourcePatchDiagnosticReason(StrEnum):
    ADVISORY_ONLY_FAQ = "advisory_only_faq"
    AMBIGUOUS_TARGET = "ambiguous_target"
    FAQ_CLASSIFICATION_ERROR = "faq_classification_error"
    MALFORMED_OPERATION = "malformed_operation"
    MALFORMED_TARGET = "malformed_target"
    MISSING_SOURCE_TABLE = "missing_source_table"
    TARGET_DRIFT = "target_drift"
    UNSUPPORTED_EXECUTABLE_CHANGE = "unsupported_executable_change"
    UNRESOLVED_TARGET = "unresolved_target"


class SourcePatchTargetPayload(TypedDict):
    source_table: str
    source_row_ids: list[str]
    field_selectors: dict[str, str]
    allow_multi_row: bool
    expected_row_hashes: dict[str, str]


class SourcePatchDiagnosticPayload(TypedDict):
    operation_id: str
    source_table: str
    source_row_id: str | None
    reason: str
    message: str
    blocking: bool


class SourceTransitionPatchOperationPayload(TypedDict):
    operation_id: str
    order_index: int
    operation_family: str
    target: SourcePatchTargetPayload
    instruction_text: str
    normalized_instruction_text: str
    parsed_instruction_tokens: ParsedRuleTextPayload
    source_ids: list[str]
    payload: dict[str, str]
    faq_classification: str | None


class SourceTransitionPatchPackagePayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    official_source_package_id: DataPackageIdPayload
    source_date: str
    source_edition: str
    faction_id: str
    operations: list[SourceTransitionPatchOperationPayload]
    schema_version: str
    package_hash: str


class SourceTransitionPatchPackageDraftPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    official_source_package_id: DataPackageIdPayload
    source_date: str
    source_edition: str
    faction_id: str
    operations: list[SourceTransitionPatchOperationPayload]
    schema_version: str


class PatchedSourceArtifactPayload(TypedDict):
    source_package_id: DataPackageIdPayload
    source_table: str
    source_artifact_hash: str
    patch_package_hash: str
    source_edition: str
    rows: list[NormalizedSourceRowPayload]
    diagnostics: list[SourcePatchDiagnosticPayload]
    artifact_hash: str


@dataclass(frozen=True, slots=True)
class SourcePatchTarget:
    source_table: str
    source_row_ids: tuple[str, ...] = ()
    field_selectors: tuple[tuple[str, str], ...] = ()
    allow_multi_row: bool = False
    expected_row_hashes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourcePatchTarget source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_row_ids",
            _validate_identifier_tuple(
                "SourcePatchTarget source_row_ids",
                self.source_row_ids,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "field_selectors",
            _validate_string_pair_tuple(
                "SourcePatchTarget field_selectors",
                self.field_selectors,
                allow_empty=True,
            ),
        )
        if type(self.allow_multi_row) is not bool:
            raise SourcePatchError("SourcePatchTarget allow_multi_row must be a boolean.")
        object.__setattr__(
            self,
            "expected_row_hashes",
            _validate_string_pair_tuple(
                "SourcePatchTarget expected_row_hashes",
                self.expected_row_hashes,
                allow_empty=True,
            ),
        )

    @classmethod
    def from_rows(
        cls,
        *,
        source_table: object,
        rows: tuple[NormalizedSourceRow, ...],
        allow_multi_row: bool = False,
    ) -> Self:
        table = _validate_identifier("source_table", source_table)
        if type(rows) is not tuple:
            raise SourcePatchError("SourcePatchTarget rows must be a tuple.")
        if not rows:
            raise SourcePatchError("SourcePatchTarget rows must not be empty.")
        row_ids: list[str] = []
        expected_hashes: list[tuple[str, str]] = []
        for row in rows:
            if type(row) is not NormalizedSourceRow:
                raise SourcePatchError("SourcePatchTarget rows must contain source rows.")
            if row.source_table != table:
                raise SourcePatchError("SourcePatchTarget row table must match source_table.")
            row_ids.append(row.source_row_id)
            expected_hashes.append((row.source_row_id, source_row_hash(row)))
        return cls(
            source_table=table,
            source_row_ids=tuple(row_ids),
            allow_multi_row=allow_multi_row,
            expected_row_hashes=tuple(expected_hashes),
        )

    def to_payload(self) -> SourcePatchTargetPayload:
        return {
            "source_table": self.source_table,
            "source_row_ids": list(self.source_row_ids),
            "field_selectors": dict(self.field_selectors),
            "allow_multi_row": self.allow_multi_row,
            "expected_row_hashes": dict(self.expected_row_hashes),
        }

    @classmethod
    def from_payload(cls, payload: SourcePatchTargetPayload) -> Self:
        return cls(
            source_table=payload["source_table"],
            source_row_ids=tuple(payload["source_row_ids"]),
            field_selectors=tuple(payload["field_selectors"].items()),
            allow_multi_row=payload["allow_multi_row"],
            expected_row_hashes=tuple(payload["expected_row_hashes"].items()),
        )


@dataclass(frozen=True, slots=True)
class SourcePatchDiagnostic:
    operation_id: str
    source_table: str
    source_row_id: str | None
    reason: SourcePatchDiagnosticReason
    message: str
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _validate_identifier("SourcePatchDiagnostic operation_id", self.operation_id),
        )
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourcePatchDiagnostic source_table", self.source_table),
        )
        if self.source_row_id is not None:
            object.__setattr__(
                self,
                "source_row_id",
                _validate_identifier(
                    "SourcePatchDiagnostic source_row_id",
                    self.source_row_id,
                ),
            )
        if type(self.reason) is not SourcePatchDiagnosticReason:
            raise SourcePatchError(
                "SourcePatchDiagnostic reason must be SourcePatchDiagnosticReason."
            )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("SourcePatchDiagnostic message", self.message),
        )
        if type(self.blocking) is not bool:
            raise SourcePatchError("SourcePatchDiagnostic blocking must be a boolean.")

    def to_payload(self) -> SourcePatchDiagnosticPayload:
        return {
            "operation_id": self.operation_id,
            "source_table": self.source_table,
            "source_row_id": self.source_row_id,
            "reason": self.reason.value,
            "message": self.message,
            "blocking": self.blocking,
        }

    @classmethod
    def from_payload(cls, payload: SourcePatchDiagnosticPayload) -> Self:
        return cls(
            operation_id=payload["operation_id"],
            source_table=payload["source_table"],
            source_row_id=payload["source_row_id"],
            reason=_diagnostic_reason_from_token(payload["reason"]),
            message=payload["message"],
            blocking=payload["blocking"],
        )


@dataclass(frozen=True, slots=True)
class SourceTransitionPatchOperation:
    operation_id: str
    order_index: int
    operation_family: SourceTransitionPatchOperationFamily
    target: SourcePatchTarget
    instruction_text: str
    normalized_instruction_text: str
    parsed_instruction_tokens: ParsedRuleText
    source_ids: tuple[str, ...]
    payload: tuple[tuple[str, str], ...]
    faq_classification: SourceFaqClassification | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _validate_identifier(
                "SourceTransitionPatchOperation operation_id",
                self.operation_id,
            ),
        )
        if type(self.order_index) is not int:
            raise SourcePatchError("SourceTransitionPatchOperation order_index must be an integer.")
        if self.order_index < 0:
            raise SourcePatchError(
                "SourceTransitionPatchOperation order_index must not be negative."
            )
        if type(self.operation_family) is not SourceTransitionPatchOperationFamily:
            raise SourcePatchError(
                "SourceTransitionPatchOperation operation_family must be "
                "SourceTransitionPatchOperationFamily."
            )
        if type(self.target) is not SourcePatchTarget:
            raise SourcePatchError(
                "SourceTransitionPatchOperation target must be SourcePatchTarget."
            )
        if type(self.instruction_text) is not str:
            raise SourcePatchError(
                "SourceTransitionPatchOperation instruction_text must be a string."
            )
        try:
            expected_normalized = normalize_structured_source_text(self.instruction_text)
        except TextNormalizationError as exc:
            raise SourcePatchError(
                "SourceTransitionPatchOperation instruction_text cannot be normalized."
            ) from exc
        if self.normalized_instruction_text != expected_normalized:
            raise SourcePatchError(
                "SourceTransitionPatchOperation normalized_instruction_text is stale."
            )
        if type(self.parsed_instruction_tokens) is not ParsedRuleText:
            raise SourcePatchError(
                "SourceTransitionPatchOperation parsed_instruction_tokens must be ParsedRuleText."
            )
        if self.parsed_instruction_tokens.normalized_text != self.normalized_instruction_text:
            raise SourcePatchError(
                "SourceTransitionPatchOperation parsed tokens must match instruction text."
            )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple(
                "SourceTransitionPatchOperation source_ids",
                self.source_ids,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "payload",
            _validate_string_pair_tuple(
                "SourceTransitionPatchOperation payload",
                self.payload,
                allow_empty=True,
            ),
        )
        if self.faq_classification is not None and type(self.faq_classification) is not (
            SourceFaqClassification
        ):
            raise SourcePatchError(
                "SourceTransitionPatchOperation faq_classification must be SourceFaqClassification."
            )
        _validate_operation_payload(self)

    @classmethod
    def from_instruction(
        cls,
        *,
        operation_id: str,
        order_index: int,
        operation_family: SourceTransitionPatchOperationFamily,
        target: SourcePatchTarget,
        instruction_text: str,
        source_ids: tuple[str, ...],
        payload: tuple[tuple[str, str], ...],
        faq_classification: SourceFaqClassification | None = None,
    ) -> Self:
        normalized_instruction_text = normalize_structured_source_text(instruction_text)
        return cls(
            operation_id=operation_id,
            order_index=order_index,
            operation_family=operation_family,
            target=target,
            instruction_text=instruction_text,
            normalized_instruction_text=normalized_instruction_text,
            parsed_instruction_tokens=parse_normalized_tokens(normalized_instruction_text),
            source_ids=source_ids,
            payload=payload,
            faq_classification=faq_classification,
        )

    def payload_value(self, key: str) -> str:
        requested_key = _validate_identifier("payload key", key)
        for existing_key, value in self.payload:
            if existing_key == requested_key:
                return value
        raise SourcePatchError("SourceTransitionPatchOperation payload key is missing.")

    def to_payload(self) -> SourceTransitionPatchOperationPayload:
        return {
            "operation_id": self.operation_id,
            "order_index": self.order_index,
            "operation_family": self.operation_family.value,
            "target": self.target.to_payload(),
            "instruction_text": self.instruction_text,
            "normalized_instruction_text": self.normalized_instruction_text,
            "parsed_instruction_tokens": self.parsed_instruction_tokens.to_payload(),
            "source_ids": list(self.source_ids),
            "payload": dict(self.payload),
            "faq_classification": None
            if self.faq_classification is None
            else self.faq_classification.value,
        }

    @classmethod
    def from_payload(cls, payload: SourceTransitionPatchOperationPayload) -> Self:
        return cls(
            operation_id=payload["operation_id"],
            order_index=payload["order_index"],
            operation_family=_operation_family_from_token(payload["operation_family"]),
            target=SourcePatchTarget.from_payload(payload["target"]),
            instruction_text=payload["instruction_text"],
            normalized_instruction_text=payload["normalized_instruction_text"],
            parsed_instruction_tokens=ParsedRuleText.from_payload(
                payload["parsed_instruction_tokens"]
            ),
            source_ids=tuple(payload["source_ids"]),
            payload=tuple(payload["payload"].items()),
            faq_classification=(
                None
                if payload["faq_classification"] is None
                else _faq_classification_from_token(payload["faq_classification"])
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceTransitionPatchPackage:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    official_source_package_id: DataPackageId
    source_date: str
    source_edition: str
    faction_id: str
    operations: tuple[SourceTransitionPatchOperation, ...]
    schema_version: str = "phase17a1-transition-patch-v1"

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise SourcePatchError("SourceTransitionPatchPackage package_id must be DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise SourcePatchError(
                "SourceTransitionPatchPackage catalog_version must be CatalogVersion."
            )
        if type(self.official_source_package_id) is not DataPackageId:
            raise SourcePatchError(
                "SourceTransitionPatchPackage official_source_package_id must be DataPackageId."
            )
        object.__setattr__(
            self,
            "source_date",
            _validate_source_date("SourceTransitionPatchPackage source_date", self.source_date),
        )
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier(
                "SourceTransitionPatchPackage source_edition",
                self.source_edition,
            ),
        )
        if self.source_edition != "warhammer-40000-11th":
            raise SourcePatchError(
                "SourceTransitionPatchPackage source_edition must be warhammer-40000-11th."
            )
        if "11" not in self.package_id.version:
            raise SourcePatchError(
                "SourceTransitionPatchPackage package_id version must identify 11th Edition."
            )
        object.__setattr__(
            self,
            "faction_id",
            _validate_identifier("SourceTransitionPatchPackage faction_id", self.faction_id),
        )
        object.__setattr__(
            self,
            "operations",
            _validate_operation_tuple(self.operations),
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier(
                "SourceTransitionPatchPackage schema_version",
                self.schema_version,
            ),
        )

    def package_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_payload(self) -> SourceTransitionPatchPackagePayload:
        payload = self._payload_without_hash()
        payload["package_hash"] = self.package_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: SourceTransitionPatchPackagePayload) -> Self:
        package = cls.from_unhashed_payload(payload)
        if payload["package_hash"] != package.package_hash():
            raise SourcePatchError("SourceTransitionPatchPackage package_hash is stale.")
        return package

    @classmethod
    def from_unhashed_payload(
        cls,
        payload: SourceTransitionPatchPackageDraftPayload,
    ) -> Self:
        return cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            official_source_package_id=_data_package_id_from_payload(
                payload["official_source_package_id"]
            ),
            source_date=payload["source_date"],
            source_edition=payload["source_edition"],
            faction_id=payload["faction_id"],
            operations=tuple(
                SourceTransitionPatchOperation.from_payload(operation)
                for operation in payload["operations"]
            ),
            schema_version=payload["schema_version"],
        )

    def _payload_without_hash(self) -> SourceTransitionPatchPackagePayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "official_source_package_id": self.official_source_package_id.to_payload(),
            "source_date": self.source_date,
            "source_edition": self.source_edition,
            "faction_id": self.faction_id,
            "operations": [operation.to_payload() for operation in self.operations],
            "schema_version": self.schema_version,
            "package_hash": "",
        }


@dataclass(frozen=True, slots=True)
class PatchedSourceArtifact:
    source_package_id: DataPackageId
    source_table: str
    source_artifact_hash: str
    patch_package_hash: str
    source_edition: str
    rows: tuple[NormalizedSourceRow, ...]
    diagnostics: tuple[SourcePatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.source_package_id) is not DataPackageId:
            raise SourcePatchError("PatchedSourceArtifact source_package_id must be DataPackageId.")
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("PatchedSourceArtifact source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_artifact_hash",
            _validate_sha256(
                "PatchedSourceArtifact source_artifact_hash",
                self.source_artifact_hash,
            ),
        )
        object.__setattr__(
            self,
            "patch_package_hash",
            _validate_sha256(
                "PatchedSourceArtifact patch_package_hash",
                self.patch_package_hash,
            ),
        )
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier("PatchedSourceArtifact source_edition", self.source_edition),
        )
        if self.source_edition != "warhammer-40000-11th":
            raise SourcePatchError(
                "PatchedSourceArtifact source_edition must be warhammer-40000-11th."
            )
        object.__setattr__(self, "rows", _validate_patched_rows(self))
        object.__setattr__(
            self,
            "diagnostics",
            _validate_diagnostic_tuple(self.diagnostics),
        )

    def blocking_diagnostics(self) -> tuple[SourcePatchDiagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.blocking)

    def require_success(self) -> None:
        blocking = self.blocking_diagnostics()
        if blocking:
            reasons = ", ".join(sorted({diagnostic.reason.value for diagnostic in blocking}))
            raise SourcePatchError(
                f"Transition patch application failed with diagnostics: {reasons}."
            )

    def artifact_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def source_artifact_hash_record(self) -> SourceArtifactHash:
        return SourceArtifactHash(
            artifact_name=f"{self.source_table}.patched.json",
            artifact_hash=self.artifact_hash(),
        )

    def to_json_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def to_payload(self) -> PatchedSourceArtifactPayload:
        payload = self._payload_without_hash()
        payload["artifact_hash"] = self.artifact_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: PatchedSourceArtifactPayload) -> Self:
        artifact = cls(
            source_package_id=_data_package_id_from_payload(payload["source_package_id"]),
            source_table=payload["source_table"],
            source_artifact_hash=payload["source_artifact_hash"],
            patch_package_hash=payload["patch_package_hash"],
            source_edition=payload["source_edition"],
            rows=tuple(NormalizedSourceRow.from_payload(row) for row in payload["rows"]),
            diagnostics=tuple(
                SourcePatchDiagnostic.from_payload(diagnostic)
                for diagnostic in payload["diagnostics"]
            ),
        )
        if payload["artifact_hash"] != artifact.artifact_hash():
            raise SourcePatchError("PatchedSourceArtifact artifact_hash is stale.")
        return artifact

    def _payload_without_hash(self) -> PatchedSourceArtifactPayload:
        return {
            "source_package_id": self.source_package_id.to_payload(),
            "source_table": self.source_table,
            "source_artifact_hash": self.source_artifact_hash,
            "patch_package_hash": self.patch_package_hash,
            "source_edition": self.source_edition,
            "rows": [row.to_payload() for row in self.rows],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "artifact_hash": "",
        }


def source_row_hash(row: NormalizedSourceRow) -> str:
    if type(row) is not NormalizedSourceRow:
        raise SourcePatchError("source_row_hash row must be NormalizedSourceRow.")
    return _sha256_payload(row.to_payload())


def apply_transition_patch_package(
    *,
    artifact: WahapediaJsonArtifact,
    patch_package: SourceTransitionPatchPackage,
    raise_on_blocking: bool = True,
) -> PatchedSourceArtifact:
    if type(artifact) is not WahapediaJsonArtifact:
        raise SourcePatchError("artifact must be WahapediaJsonArtifact.")
    if type(patch_package) is not SourceTransitionPatchPackage:
        raise SourcePatchError("patch_package must be SourceTransitionPatchPackage.")
    if type(raise_on_blocking) is not bool:
        raise SourcePatchError("raise_on_blocking must be a boolean.")

    rows_by_id = {
        row.source_row_id: _repackage_row(row, patch_package.package_id) for row in artifact.rows
    }
    diagnostics: list[SourcePatchDiagnostic] = []
    source_rows_by_id = {row.source_row_id: row for row in artifact.rows}

    for operation in patch_package.operations:
        if operation.target.source_table != artifact.source_table:
            continue
        resolved_rows, target_diagnostics = _resolve_target(
            operation=operation,
            source_rows_by_id=source_rows_by_id,
        )
        diagnostics.extend(target_diagnostics)
        if any(diagnostic.blocking for diagnostic in target_diagnostics):
            continue
        if operation.operation_family is SourceTransitionPatchOperationFamily.MARK_UNSUPPORTED:
            diagnostics.append(
                SourcePatchDiagnostic(
                    operation_id=operation.operation_id,
                    source_table=operation.target.source_table,
                    source_row_id=None,
                    reason=SourcePatchDiagnosticReason.UNSUPPORTED_EXECUTABLE_CHANGE,
                    message=operation.payload_value("reason"),
                    blocking=False,
                )
            )
            continue
        if operation.operation_family is SourceTransitionPatchOperationFamily.RECORD_FAQ_ANSWER:
            diagnostics.append(_faq_diagnostic(operation))
            continue

        for source_row in resolved_rows:
            patched_row = _apply_operation_to_row(
                operation=operation,
                row=rows_by_id[source_row.source_row_id],
            )
            rows_by_id[source_row.source_row_id] = patched_row

    artifact_result = PatchedSourceArtifact(
        source_package_id=patch_package.package_id,
        source_table=artifact.source_table,
        source_artifact_hash=artifact.artifact_hash(),
        patch_package_hash=patch_package.package_hash(),
        source_edition=patch_package.source_edition,
        rows=tuple(rows_by_id.values()),
        diagnostics=tuple(diagnostics),
    )
    if raise_on_blocking:
        artifact_result.require_success()
    return artifact_result


def _resolve_target(
    *,
    operation: SourceTransitionPatchOperation,
    source_rows_by_id: dict[str, NormalizedSourceRow],
) -> tuple[tuple[NormalizedSourceRow, ...], tuple[SourcePatchDiagnostic, ...]]:
    target = operation.target
    diagnostics: list[SourcePatchDiagnostic] = []
    if target.source_row_ids and target.field_selectors:
        return (), (
            _target_diagnostic(
                operation=operation,
                source_row_id=None,
                reason=SourcePatchDiagnosticReason.MALFORMED_TARGET,
                message="Patch target must use source_row_ids or field_selectors, not both.",
            ),
        )
    if not target.source_row_ids and not target.field_selectors:
        return (), (
            _target_diagnostic(
                operation=operation,
                source_row_id=None,
                reason=SourcePatchDiagnosticReason.MALFORMED_TARGET,
                message="Patch target must declare source_row_ids or field_selectors.",
            ),
        )

    if target.source_row_ids:
        rows: list[NormalizedSourceRow] = []
        for source_row_id in target.source_row_ids:
            row = source_rows_by_id.get(source_row_id)
            if row is None:
                diagnostics.append(
                    _target_diagnostic(
                        operation=operation,
                        source_row_id=source_row_id,
                        reason=SourcePatchDiagnosticReason.UNRESOLVED_TARGET,
                        message="Patch target source row ID was not found.",
                    )
                )
                continue
            rows.append(row)
    else:
        selector_map = dict(target.field_selectors)
        rows = [
            row
            for row in source_rows_by_id.values()
            if all(
                row.runtime_fields_payload().get(key) == value
                for key, value in selector_map.items()
            )
        ]
        if not rows:
            diagnostics.append(
                _target_diagnostic(
                    operation=operation,
                    source_row_id=None,
                    reason=SourcePatchDiagnosticReason.UNRESOLVED_TARGET,
                    message="Patch target field selectors matched no source rows.",
                )
            )

    if diagnostics:
        return (), tuple(diagnostics)

    if len(rows) > 1 and not target.allow_multi_row:
        return (), (
            _target_diagnostic(
                operation=operation,
                source_row_id=None,
                reason=(
                    SourcePatchDiagnosticReason.MALFORMED_TARGET
                    if target.source_row_ids
                    else SourcePatchDiagnosticReason.AMBIGUOUS_TARGET
                ),
                message="Patch target resolved multiple rows without allow_multi_row.",
            ),
        )

    hash_map = dict(target.expected_row_hashes)
    row_ids = {row.source_row_id for row in rows}
    if set(hash_map) != row_ids:
        return (), (
            _target_diagnostic(
                operation=operation,
                source_row_id=None,
                reason=SourcePatchDiagnosticReason.MALFORMED_TARGET,
                message="Patch target expected_row_hashes must match resolved rows.",
            ),
        )
    for row in rows:
        if hash_map[row.source_row_id] != source_row_hash(row):
            return (), (
                _target_diagnostic(
                    operation=operation,
                    source_row_id=row.source_row_id,
                    reason=SourcePatchDiagnosticReason.TARGET_DRIFT,
                    message="Patch target source row hash is stale.",
                ),
            )

    return tuple(sorted(rows, key=lambda row: row.source_row_id)), ()


def _target_diagnostic(
    *,
    operation: SourceTransitionPatchOperation,
    source_row_id: str | None,
    reason: SourcePatchDiagnosticReason,
    message: str,
) -> SourcePatchDiagnostic:
    return SourcePatchDiagnostic(
        operation_id=operation.operation_id,
        source_table=operation.target.source_table,
        source_row_id=source_row_id,
        reason=reason,
        message=message,
        blocking=operation.operation_family
        is not SourceTransitionPatchOperationFamily.MARK_UNSUPPORTED,
    )


def _faq_diagnostic(operation: SourceTransitionPatchOperation) -> SourcePatchDiagnostic:
    classification = operation.faq_classification
    if classification is SourceFaqClassification.ADVISORY_ONLY:
        return SourcePatchDiagnostic(
            operation_id=operation.operation_id,
            source_table=operation.target.source_table,
            source_row_id=None,
            reason=SourcePatchDiagnosticReason.ADVISORY_ONLY_FAQ,
            message=operation.payload_value("answer_text"),
            blocking=False,
        )
    if classification is SourceFaqClassification.UNSUPPORTED_EXECUTABLE_CHANGE:
        return SourcePatchDiagnostic(
            operation_id=operation.operation_id,
            source_table=operation.target.source_table,
            source_row_id=None,
            reason=SourcePatchDiagnosticReason.UNSUPPORTED_EXECUTABLE_CHANGE,
            message=operation.payload_value("answer_text"),
            blocking=False,
        )
    return SourcePatchDiagnostic(
        operation_id=operation.operation_id,
        source_table=operation.target.source_table,
        source_row_id=None,
        reason=SourcePatchDiagnosticReason.FAQ_CLASSIFICATION_ERROR,
        message="FAQ answer classification is not catalog-emittable.",
        blocking=True,
    )


def _apply_operation_to_row(
    *,
    operation: SourceTransitionPatchOperation,
    row: NormalizedSourceRow,
) -> NormalizedSourceRow:
    family = operation.operation_family
    if family in {
        SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
        SourceTransitionPatchOperationFamily.REPLACE_DATASHEET_ABILITY,
        SourceTransitionPatchOperationFamily.REPLACE_ENHANCEMENT_TEXT,
        SourceTransitionPatchOperationFamily.REPLACE_STRATAGEM_TEXT,
    }:
        return _replace_text_field(
            row=row,
            column_name=operation.payload_value("column_name"),
            raw_text=operation.payload_value("text"),
        )
    if family is SourceTransitionPatchOperationFamily.APPEND_RULE_TEXT:
        return _append_text_field(
            row=row,
            column_name=operation.payload_value("column_name"),
            raw_text=operation.payload_value("text"),
        )
    if family is SourceTransitionPatchOperationFamily.ADD_KEYWORD:
        return _add_keyword(
            row=row,
            column_name=operation.payload_value("column_name"),
            keyword=operation.payload_value("keyword"),
        )
    if family is SourceTransitionPatchOperationFamily.REMOVE_KEYWORD:
        return _remove_keyword(
            row=row,
            column_name=operation.payload_value("column_name"),
            keyword=operation.payload_value("keyword"),
        )
    if family in {
        SourceTransitionPatchOperationFamily.REPLACE_PROFILE_CHARACTERISTIC,
        SourceTransitionPatchOperationFamily.REPLACE_WEAPON_CHARACTERISTIC,
    }:
        return _replace_runtime_field(
            row=row,
            column_name=operation.payload_value("column_name"),
            value=operation.payload_value("value"),
        )
    raise SourcePatchError("SourceTransitionPatchOperation family cannot mutate a source row.")


def _append_text_field(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    raw_text: str,
) -> NormalizedSourceRow:
    text_field = _text_field_by_column(row, column_name)
    combined_raw = f"{text_field.sanitized_text}\n{raw_text}"
    return _replace_text_field(row=row, column_name=column_name, raw_text=combined_raw)


def _replace_text_field(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    raw_text: str,
) -> NormalizedSourceRow:
    column = _validate_identifier("column_name", column_name)
    report = sanitize_source_html(
        source_id=f"{row.stable_source_id()}:{column}:patched",
        raw_html=raw_text,
    )
    normalized_text = normalize_structured_source_text(report.sanitized_text)
    text_field = _text_field_by_column(row, column)
    replacement = SourceTextField(
        source_text_id=text_field.source_text_id,
        column_name=column,
        raw_text=raw_text,
        sanitized_text=report.sanitized_text,
        normalized_text=normalized_text,
        parsed_tokens=parse_normalized_tokens(normalized_text),
        html_sanitization=report,
    )
    text_fields = tuple(
        replacement if existing.column_name == column else existing for existing in row.text_fields
    )
    if all(existing.column_name != column for existing in row.text_fields):
        raise SourcePatchError("Text patch column must already be a source text field.")
    return _row_with_fields_and_text_fields(
        row=row,
        fields=_replaced_field_tuple(
            row=row,
            column_name=column,
            value=report.sanitized_text,
        ),
        text_fields=text_fields,
    )


def _replace_runtime_field(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    value: str,
) -> NormalizedSourceRow:
    column = _validate_identifier("column_name", column_name)
    if type(value) is not str:
        raise SourcePatchError("runtime field replacement value must be a string.")
    fields = _replaced_field_tuple(
        row=row,
        column_name=column,
        value=sanitize_source_html(
            source_id=f"{row.stable_source_id()}:{column}:field",
            raw_html=value,
        ).sanitized_text,
    )
    return _row_with_fields_and_text_fields(
        row=row,
        fields=fields,
        text_fields=row.text_fields,
    )


def _replaced_field_tuple(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    value: str,
) -> tuple[tuple[str, str], ...]:
    field_map = dict(row.fields)
    if column_name not in field_map:
        raise SourcePatchError("Runtime field patch column was not found.")
    field_map[column_name] = value
    return tuple((key, field_map[key]) for key, _value in row.fields)


def _row_with_fields_and_text_fields(
    *,
    row: NormalizedSourceRow,
    fields: tuple[tuple[str, str], ...],
    text_fields: tuple[SourceTextField, ...],
) -> NormalizedSourceRow:
    return NormalizedSourceRow(
        source_package_id=row.source_package_id,
        source_table=row.source_table,
        source_row_id=row.source_row_id,
        source_row_number=row.source_row_number,
        fields=fields,
        text_fields=text_fields,
    )


def _add_keyword(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    keyword: str,
) -> NormalizedSourceRow:
    column = _validate_identifier("column_name", column_name)
    token = _validate_identifier("keyword", keyword)
    values = _keyword_values(row=row, column_name=column)
    if token not in values:
        values = (*values, token)
    return _replace_runtime_field(row=row, column_name=column, value=", ".join(values))


def _remove_keyword(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    keyword: str,
) -> NormalizedSourceRow:
    column = _validate_identifier("column_name", column_name)
    token = _validate_identifier("keyword", keyword)
    values = tuple(
        value for value in _keyword_values(row=row, column_name=column) if value != token
    )
    return _replace_runtime_field(row=row, column_name=column, value=", ".join(values))


def _keyword_values(*, row: NormalizedSourceRow, column_name: str) -> tuple[str, ...]:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise SourcePatchError("Keyword patch column was not found.")
    return tuple(value.strip() for value in fields[column_name].split(",") if value.strip())


def _text_field_by_column(row: NormalizedSourceRow, column_name: str) -> SourceTextField:
    column = _validate_identifier("column_name", column_name)
    for text_field in row.text_fields:
        if text_field.column_name == column:
            return text_field
    raise SourcePatchError("Text patch column was not found.")


def _repackage_row(row: NormalizedSourceRow, package_id: DataPackageId) -> NormalizedSourceRow:
    return NormalizedSourceRow(
        source_package_id=package_id,
        source_table=row.source_table,
        source_row_id=row.source_row_id,
        source_row_number=row.source_row_number,
        fields=row.fields,
        text_fields=row.text_fields,
    )


def _validate_operation_payload(operation: SourceTransitionPatchOperation) -> None:
    required_keys = _required_payload_keys(operation.operation_family)
    payload_keys = {key for key, _value in operation.payload}
    missing = tuple(key for key in required_keys if key not in payload_keys)
    if missing:
        raise SourcePatchError(
            "SourceTransitionPatchOperation payload is missing required keys: "
            + ", ".join(missing)
            + "."
        )
    if operation.operation_family is SourceTransitionPatchOperationFamily.RECORD_FAQ_ANSWER:
        if operation.faq_classification is None:
            raise SourcePatchError("FAQ answers must be classified before catalog emission.")
        if (
            operation.faq_classification is SourceFaqClassification.ADVISORY_ONLY
            and dict(operation.payload).get("changes_executable_behavior") == "true"
        ):
            raise SourcePatchError(
                "Executable FAQ changes must not be stored as advisory-only records."
            )
        return
    if operation.faq_classification is SourceFaqClassification.ADVISORY_ONLY:
        raise SourcePatchError("Executable patch operations must not be advisory-only FAQs.")


def _required_payload_keys(
    family: SourceTransitionPatchOperationFamily,
) -> tuple[str, ...]:
    match family:
        case SourceTransitionPatchOperationFamily.APPEND_RULE_TEXT:
            return ("column_name", "text")
        case SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT:
            return ("column_name", "text")
        case SourceTransitionPatchOperationFamily.ADD_KEYWORD:
            return ("column_name", "keyword")
        case SourceTransitionPatchOperationFamily.REMOVE_KEYWORD:
            return ("column_name", "keyword")
        case SourceTransitionPatchOperationFamily.REPLACE_PROFILE_CHARACTERISTIC:
            return ("column_name", "value")
        case SourceTransitionPatchOperationFamily.REPLACE_WEAPON_CHARACTERISTIC:
            return ("column_name", "value")
        case SourceTransitionPatchOperationFamily.REPLACE_DATASHEET_ABILITY:
            return ("column_name", "text")
        case SourceTransitionPatchOperationFamily.REPLACE_ENHANCEMENT_TEXT:
            return ("column_name", "text")
        case SourceTransitionPatchOperationFamily.REPLACE_STRATAGEM_TEXT:
            return ("column_name", "text")
        case SourceTransitionPatchOperationFamily.RECORD_FAQ_ANSWER:
            return ("answer_text", "changes_executable_behavior")
        case SourceTransitionPatchOperationFamily.MARK_UNSUPPORTED:
            return ("reason",)


def _validate_operation_tuple(
    values: tuple[SourceTransitionPatchOperation, ...],
) -> tuple[SourceTransitionPatchOperation, ...]:
    if type(values) is not tuple:
        raise SourcePatchError("SourceTransitionPatchPackage operations must be a tuple.")
    if not values:
        raise SourcePatchError("SourceTransitionPatchPackage operations must not be empty.")
    seen: set[str] = set()
    validated: list[SourceTransitionPatchOperation] = []
    for value in values:
        if type(value) is not SourceTransitionPatchOperation:
            raise SourcePatchError(
                "SourceTransitionPatchPackage operations must contain patch operations."
            )
        if value.operation_id in seen:
            raise SourcePatchError("SourceTransitionPatchPackage operations must be unique.")
        seen.add(value.operation_id)
        validated.append(value)
    return tuple(
        sorted(validated, key=lambda operation: (operation.order_index, operation.operation_id))
    )


def _validate_patched_rows(artifact: PatchedSourceArtifact) -> tuple[NormalizedSourceRow, ...]:
    if type(artifact.rows) is not tuple:
        raise SourcePatchError("PatchedSourceArtifact rows must be a tuple.")
    if not artifact.rows:
        raise SourcePatchError("PatchedSourceArtifact rows must not be empty.")
    seen: set[str] = set()
    rows: list[NormalizedSourceRow] = []
    for row in artifact.rows:
        if type(row) is not NormalizedSourceRow:
            raise SourcePatchError("PatchedSourceArtifact rows must contain source rows.")
        if row.source_package_id != artifact.source_package_id:
            raise SourcePatchError("PatchedSourceArtifact row package IDs must match.")
        if row.source_table != artifact.source_table:
            raise SourcePatchError("PatchedSourceArtifact row tables must match.")
        if row.source_row_id in seen:
            raise SourcePatchError("PatchedSourceArtifact rows must not duplicate IDs.")
        seen.add(row.source_row_id)
        rows.append(row)
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_diagnostic_tuple(
    values: tuple[SourcePatchDiagnostic, ...],
) -> tuple[SourcePatchDiagnostic, ...]:
    if type(values) is not tuple:
        raise SourcePatchError("PatchedSourceArtifact diagnostics must be a tuple.")
    validated: list[SourcePatchDiagnostic] = []
    for value in values:
        if type(value) is not SourcePatchDiagnostic:
            raise SourcePatchError(
                "PatchedSourceArtifact diagnostics must contain SourcePatchDiagnostic values."
            )
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda diagnostic: (
                diagnostic.operation_id,
                diagnostic.source_table,
                diagnostic.source_row_id or "",
                diagnostic.reason.value,
            ),
        )
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise SourcePatchError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise SourcePatchError(f"{field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise SourcePatchError(f"{field_name} must be a tuple.")
    if not values and not allow_empty:
        raise SourcePatchError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise SourcePatchError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_string_pair_tuple(
    field_name: str,
    values: tuple[tuple[str, str], ...],
    *,
    allow_empty: bool,
) -> tuple[tuple[str, str], ...]:
    if type(values) is not tuple:
        raise SourcePatchError(f"{field_name} must be a tuple.")
    if not values and not allow_empty:
        raise SourcePatchError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[tuple[str, str]] = []
    for key, value in values:
        identifier = _validate_identifier(f"{field_name} key", key)
        if identifier in seen:
            raise SourcePatchError(f"{field_name} must not contain duplicate keys.")
        if type(value) is not str:
            raise SourcePatchError(f"{field_name} values must be strings.")
        seen.add(identifier)
        validated.append((identifier, value))
    return tuple(validated)


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise SourcePatchError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise SourcePatchError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return digest


def _validate_source_date(field_name: str, value: object) -> str:
    source_date = _validate_identifier(field_name, value)
    try:
        date.fromisoformat(source_date)
    except ValueError as exc:
        raise SourcePatchError(f"{field_name} must be an ISO date.") from exc
    return source_date


def _operation_family_from_token(token: object) -> SourceTransitionPatchOperationFamily:
    if type(token) is SourceTransitionPatchOperationFamily:
        return token
    if type(token) is not str:
        raise SourcePatchError("operation_family token must be a string.")
    try:
        return SourceTransitionPatchOperationFamily(token)
    except ValueError as exc:
        raise SourcePatchError(f"Unsupported patch operation family: {token}.") from exc


def _faq_classification_from_token(token: object) -> SourceFaqClassification:
    if type(token) is SourceFaqClassification:
        return token
    if type(token) is not str:
        raise SourcePatchError("faq_classification token must be a string.")
    try:
        return SourceFaqClassification(token)
    except ValueError as exc:
        raise SourcePatchError(f"Unsupported FAQ classification: {token}.") from exc


def _diagnostic_reason_from_token(token: object) -> SourcePatchDiagnosticReason:
    if type(token) is SourcePatchDiagnosticReason:
        return token
    if type(token) is not str:
        raise SourcePatchError("diagnostic reason token must be a string.")
    try:
        return SourcePatchDiagnosticReason(token)
    except ValueError as exc:
        raise SourcePatchError(f"Unsupported source patch diagnostic reason: {token}.") from exc


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise SourcePatchError("DataPackageId payload is invalid.") from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise SourcePatchError("CatalogVersion payload is invalid.") from exc


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
