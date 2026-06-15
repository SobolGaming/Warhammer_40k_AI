from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
)
from warhammer40k_core.rules.html_sanitizer import (
    SourceHtmlSanitizationError,
    SourceHtmlSanitizationReport,
    SourceHtmlSanitizationReportPayload,
    contains_html_markup,
    sanitize_source_html,
)
from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    RuleTokenError,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.source_catalog import (
    SourceArtifactHash,
    SourceFileChecksum,
    SourceFileChecksumPayload,
    SourcePackageManifest,
)
from warhammer40k_core.rules.text_normalization import (
    TextNormalizationError,
    normalize_structured_source_text,
)


class WahapediaSchemaError(ValueError):
    """Raised when Wahapedia source mirror data violates Phase 17A invariants."""


_SOURCE_ROW_NUMBER_ID_COLUMN = "__source_row_number__"


class SourceRowDiagnosticReason(StrEnum):
    DUPLICATE_SOURCE_ROW_ID = "duplicate_source_row_id"
    EMPTY_TABLE = "empty_table"
    HTML_TAG_IN_RUNTIME_FIELD = "html_tag_in_runtime_field"
    MALFORMED_CSV_ROW = "malformed_csv_row"
    MISSING_COLUMN = "missing_column"
    MISSING_SOURCE_ROW_ID = "missing_source_row_id"
    NORMALIZATION_FAILED = "normalization_failed"
    UNSUPPORTED_TABLE = "unsupported_table"


class WahapediaCsvRowPayload(TypedDict):
    row_number: int
    values: dict[str, str]


class WahapediaCsvTablePayload(TypedDict):
    table_name: str
    columns: list[str]
    rows: list[WahapediaCsvRowPayload]
    checksum_sha256: str
    delimiter: str


class SourceTextFieldPayload(TypedDict):
    source_text_id: str
    column_name: str
    raw_text: str
    sanitized_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleTextPayload
    html_sanitization: SourceHtmlSanitizationReportPayload


class NormalizedSourceRowPayload(TypedDict):
    source_package_id: DataPackageIdPayload
    source_table: str
    source_row_id: str
    source_row_number: int
    fields: dict[str, str]
    text_fields: list[SourceTextFieldPayload]


class SourceRowDiagnosticPayload(TypedDict):
    source_table: str
    source_row_number: int
    source_row_id: str | None
    reason: str
    message: str


class WahapediaArtifactBuildReportPayload(TypedDict):
    source_table: str
    rows: list[NormalizedSourceRowPayload]
    diagnostics: list[SourceRowDiagnosticPayload]


class WahapediaJsonArtifactPayload(TypedDict):
    source_package_id: DataPackageIdPayload
    source_table: str
    source_checksum_sha256: str
    rows: list[NormalizedSourceRowPayload]
    artifact_hash: str


class WahapediaSourceSnapshotPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    upstream_identity: str
    source_edition: str
    source_files: list[SourceFileChecksumPayload]


class EditionSourceConfigPayload(TypedDict):
    source_edition: str
    wahapedia_edition_slug: str
    export_specs_url: str
    csv_delimiter: str


@dataclass(frozen=True, slots=True)
class WahapediaTableSchema:
    table_name: str
    source_row_id_columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    required_columns: tuple[str, ...]
    optional_text_columns: tuple[str, ...] = ()
    source_row_id_empty_tokens: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "table_name",
            _validate_identifier("WahapediaTableSchema table_name", self.table_name),
        )
        object.__setattr__(
            self,
            "source_row_id_columns",
            _validate_identifier_tuple(
                "WahapediaTableSchema source_row_id_columns",
                self.source_row_id_columns,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "text_columns",
            _validate_identifier_tuple(
                "WahapediaTableSchema text_columns",
                self.text_columns,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "optional_text_columns",
            _validate_identifier_tuple(
                "WahapediaTableSchema optional_text_columns",
                self.optional_text_columns,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "required_columns",
            _validate_identifier_tuple(
                "WahapediaTableSchema required_columns",
                self.required_columns,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "source_row_id_empty_tokens",
            _validate_source_row_id_empty_tokens(self.source_row_id_empty_tokens),
        )
        required = set(self.required_columns)
        for column_name in (*self.source_row_id_columns, *self.text_columns):
            if column_name == _SOURCE_ROW_NUMBER_ID_COLUMN:
                continue
            if column_name not in required:
                raise WahapediaSchemaError(
                    "WahapediaTableSchema required_columns must include ID and text columns."
                )
        overlap = set(self.text_columns) & set(self.optional_text_columns)
        if overlap:
            raise WahapediaSchemaError(
                "WahapediaTableSchema required and optional text columns must not overlap."
            )

    @property
    def required_text_columns(self) -> tuple[str, ...]:
        return self.text_columns

    @property
    def all_text_columns(self) -> tuple[str, ...]:
        return (*self.text_columns, *self.optional_text_columns)

    def source_row_id(self, row: WahapediaCsvRow) -> str:
        parts: list[str] = []
        empty_tokens = dict(self.source_row_id_empty_tokens)
        for column_name in self.source_row_id_columns:
            if column_name == _SOURCE_ROW_NUMBER_ID_COLUMN:
                parts.append(str(row.row_number))
                continue
            value = row.value_by_column(column_name).strip()
            if not value:
                replacement = empty_tokens.get(column_name)
                if replacement is None:
                    raise WahapediaSchemaError("source row ID column must not be empty.")
                value = replacement
            parts.append(value)
        return ":".join(parts)


@dataclass(frozen=True, slots=True)
class WahapediaCsvRow:
    row_number: int
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if type(self.row_number) is not int:
            raise WahapediaSchemaError("WahapediaCsvRow row_number must be an integer.")
        if self.row_number < 2:
            raise WahapediaSchemaError("WahapediaCsvRow row_number must reference a CSV row.")
        if type(self.values) is not tuple:
            raise WahapediaSchemaError("WahapediaCsvRow values must be a tuple.")
        seen: set[str] = set()
        validated: list[tuple[str, str]] = []
        for column_name, value in self.values:
            column = _validate_identifier("WahapediaCsvRow column", column_name)
            if column in seen:
                raise WahapediaSchemaError("WahapediaCsvRow values must not duplicate columns.")
            if type(value) is not str:
                raise WahapediaSchemaError("WahapediaCsvRow values must be strings.")
            seen.add(column)
            validated.append((column, value))
        object.__setattr__(self, "values", tuple(validated))

    def value_by_column(self, column_name: str) -> str:
        column = _validate_identifier("column_name", column_name)
        for existing_column, value in self.values:
            if existing_column == column:
                return value
        raise WahapediaSchemaError("WahapediaCsvRow column is missing.")

    def has_column(self, column_name: str) -> bool:
        column = _validate_identifier("column_name", column_name)
        return any(existing_column == column for existing_column, _value in self.values)

    def to_payload(self) -> WahapediaCsvRowPayload:
        return {
            "row_number": self.row_number,
            "values": dict(self.values),
        }

    @classmethod
    def from_payload(cls, payload: WahapediaCsvRowPayload) -> Self:
        return cls(
            row_number=payload["row_number"],
            values=tuple(payload["values"].items()),
        )


@dataclass(frozen=True, slots=True)
class WahapediaCsvTable:
    table_name: str
    columns: tuple[str, ...]
    rows: tuple[WahapediaCsvRow, ...]
    checksum_sha256: str
    delimiter: str = ","

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "table_name",
            _validate_identifier("WahapediaCsvTable table_name", self.table_name),
        )
        object.__setattr__(
            self,
            "columns",
            _validate_identifier_tuple(
                "WahapediaCsvTable columns",
                self.columns,
                allow_empty=False,
            ),
        )
        if type(self.rows) is not tuple:
            raise WahapediaSchemaError("WahapediaCsvTable rows must be a tuple.")
        for row in self.rows:
            if type(row) is not WahapediaCsvRow:
                raise WahapediaSchemaError("WahapediaCsvTable rows must contain CSV rows.")
            if tuple(column for column, _value in row.values) != self.columns:
                raise WahapediaSchemaError("WahapediaCsvTable row columns must match header.")
        object.__setattr__(
            self,
            "checksum_sha256",
            _validate_sha256("WahapediaCsvTable checksum_sha256", self.checksum_sha256),
        )
        object.__setattr__(
            self,
            "delimiter",
            _validate_csv_delimiter("WahapediaCsvTable delimiter", self.delimiter),
        )

    @classmethod
    def from_csv_text(cls, *, table_name: object, csv_text: object, delimiter: str = ",") -> Self:
        table = _validate_identifier("table_name", table_name)
        if type(csv_text) is not str:
            raise WahapediaSchemaError("csv_text must be a string.")
        csv_delimiter = _validate_csv_delimiter("delimiter", delimiter)
        checksum = hashlib.sha256(csv_text.encode()).hexdigest()
        rows = tuple(csv.reader(io.StringIO(csv_text), delimiter=csv_delimiter))
        if not rows:
            raise WahapediaSchemaError("CSV input must include a header.")
        rows = _with_repaired_unquoted_newline_rows(rows)
        rows = _without_trailing_empty_export_column(rows)
        columns = tuple(cell.strip() for cell in rows[0])
        _validate_identifier_tuple("CSV header", columns, allow_empty=False)
        csv_rows: list[WahapediaCsvRow] = []
        for index, values in enumerate(rows[1:], start=2):
            if len(values) != len(columns):
                raise WahapediaSchemaError(f"CSV row {index} does not match header width.")
            csv_rows.append(
                WahapediaCsvRow(
                    row_number=index,
                    values=tuple(
                        (column, value) for column, value in zip(columns, values, strict=True)
                    ),
                )
            )
        return cls(
            table_name=table,
            columns=columns,
            rows=tuple(csv_rows),
            checksum_sha256=checksum,
            delimiter=csv_delimiter,
        )

    def to_payload(self) -> WahapediaCsvTablePayload:
        return {
            "table_name": self.table_name,
            "columns": list(self.columns),
            "rows": [row.to_payload() for row in self.rows],
            "checksum_sha256": self.checksum_sha256,
            "delimiter": self.delimiter,
        }

    @classmethod
    def from_payload(cls, payload: WahapediaCsvTablePayload) -> Self:
        return cls(
            table_name=payload["table_name"],
            columns=tuple(payload["columns"]),
            rows=tuple(
                WahapediaCsvRow(
                    row_number=row["row_number"],
                    values=tuple((column, row["values"][column]) for column in payload["columns"]),
                )
                for row in payload["rows"]
            ),
            checksum_sha256=payload["checksum_sha256"],
            delimiter=payload["delimiter"],
        )


@dataclass(frozen=True, slots=True)
class SourceTextField:
    source_text_id: str
    column_name: str
    raw_text: str
    sanitized_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleText
    html_sanitization: SourceHtmlSanitizationReport

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_text_id",
            _validate_identifier("SourceTextField source_text_id", self.source_text_id),
        )
        object.__setattr__(
            self,
            "column_name",
            _validate_identifier("SourceTextField column_name", self.column_name),
        )
        if type(self.raw_text) is not str:
            raise WahapediaSchemaError("SourceTextField raw_text must be a string.")
        if type(self.sanitized_text) is not str:
            raise WahapediaSchemaError("SourceTextField sanitized_text must be a string.")
        if type(self.normalized_text) is not str:
            raise WahapediaSchemaError("SourceTextField normalized_text must be a string.")
        if type(self.parsed_tokens) is not ParsedRuleText:
            raise WahapediaSchemaError("SourceTextField parsed_tokens must be ParsedRuleText.")
        if type(self.html_sanitization) is not SourceHtmlSanitizationReport:
            raise WahapediaSchemaError(
                "SourceTextField html_sanitization must be SourceHtmlSanitizationReport."
            )
        if self.html_sanitization.raw_html != self.raw_text:
            raise WahapediaSchemaError("SourceTextField raw_text must match sanitization report.")
        if self.html_sanitization.sanitized_text != self.sanitized_text:
            raise WahapediaSchemaError(
                "SourceTextField sanitized_text must match sanitization report."
            )
        try:
            expected_normalized = normalize_structured_source_text(self.sanitized_text)
        except TextNormalizationError as exc:
            raise WahapediaSchemaError("SourceTextField sanitized_text is invalid.") from exc
        if expected_normalized != self.normalized_text:
            raise WahapediaSchemaError("SourceTextField normalized_text is stale.")
        if self.parsed_tokens.normalized_text != self.normalized_text:
            raise WahapediaSchemaError("SourceTextField parsed tokens must match normalized_text.")

    def to_payload(self) -> SourceTextFieldPayload:
        return {
            "source_text_id": self.source_text_id,
            "column_name": self.column_name,
            "raw_text": self.raw_text,
            "sanitized_text": self.sanitized_text,
            "normalized_text": self.normalized_text,
            "parsed_tokens": self.parsed_tokens.to_payload(),
            "html_sanitization": self.html_sanitization.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: SourceTextFieldPayload) -> Self:
        return cls(
            source_text_id=payload["source_text_id"],
            column_name=payload["column_name"],
            raw_text=payload["raw_text"],
            sanitized_text=payload["sanitized_text"],
            normalized_text=payload["normalized_text"],
            parsed_tokens=ParsedRuleText.from_payload(payload["parsed_tokens"]),
            html_sanitization=SourceHtmlSanitizationReport.from_payload(
                payload["html_sanitization"]
            ),
        )


@dataclass(frozen=True, slots=True)
class NormalizedSourceRow:
    source_package_id: DataPackageId
    source_table: str
    source_row_id: str
    source_row_number: int
    fields: tuple[tuple[str, str], ...]
    text_fields: tuple[SourceTextField, ...]

    def __post_init__(self) -> None:
        if type(self.source_package_id) is not DataPackageId:
            raise WahapediaSchemaError(
                "NormalizedSourceRow source_package_id must be a DataPackageId."
            )
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("NormalizedSourceRow source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_row_id",
            _validate_identifier("NormalizedSourceRow source_row_id", self.source_row_id),
        )
        if type(self.source_row_number) is not int:
            raise WahapediaSchemaError("NormalizedSourceRow source_row_number must be an integer.")
        if self.source_row_number < 2:
            raise WahapediaSchemaError(
                "NormalizedSourceRow source_row_number must reference a CSV row."
            )
        object.__setattr__(self, "fields", _validate_field_tuple(self.fields))
        object.__setattr__(
            self,
            "text_fields",
            _validate_text_field_tuple(self.text_fields),
        )
        field_names = {column_name for column_name, _value in self.fields}
        for text_field in self.text_fields:
            if text_field.column_name not in field_names:
                raise WahapediaSchemaError(
                    "NormalizedSourceRow text_fields must reference runtime fields."
                )

    @classmethod
    def from_csv_row(
        cls,
        *,
        source_package_id: DataPackageId,
        schema: WahapediaTableSchema,
        row: WahapediaCsvRow,
    ) -> Self:
        _validate_required_columns(schema=schema, row=row)
        source_row_id = schema.source_row_id(row)
        fields: list[tuple[str, str]] = []
        for column_name, value in row.values:
            report = sanitize_source_html(
                source_id=f"{schema.table_name}:{source_row_id}:{column_name}",
                raw_html=value,
            )
            if contains_html_markup(report.sanitized_text):
                raise WahapediaSchemaError("Runtime source field still contains HTML markup.")
            fields.append((column_name, report.sanitized_text))

        text_fields: list[SourceTextField] = []
        for column_name in schema.all_text_columns:
            if column_name in schema.optional_text_columns and not row.has_column(column_name):
                continue
            raw_text = row.value_by_column(column_name)
            source_text_id = _source_text_id(
                source_package_id=source_package_id,
                table_name=schema.table_name,
                source_row_id=source_row_id,
                column_name=column_name,
            )
            report = sanitize_source_html(
                source_id=source_text_id,
                raw_html=raw_text,
            )
            if not report.sanitized_text.strip():
                if column_name in schema.optional_text_columns:
                    continue
                raise WahapediaSchemaError("source text column must not be empty.")
            normalized_text = normalize_structured_source_text(report.sanitized_text)
            text_fields.append(
                SourceTextField(
                    source_text_id=source_text_id,
                    column_name=column_name,
                    raw_text=raw_text,
                    sanitized_text=report.sanitized_text,
                    normalized_text=normalized_text,
                    parsed_tokens=parse_normalized_tokens(normalized_text),
                    html_sanitization=report,
                )
            )

        return cls(
            source_package_id=source_package_id,
            source_table=schema.table_name,
            source_row_id=source_row_id,
            source_row_number=row.row_number,
            fields=tuple(fields),
            text_fields=tuple(text_fields),
        )

    def stable_source_id(self) -> str:
        return (
            f"{self.source_package_id.stable_identity()}:{self.source_table}:{self.source_row_id}"
        )

    def runtime_fields_payload(self) -> dict[str, str]:
        return dict(self.fields)

    def to_payload(self) -> NormalizedSourceRowPayload:
        return {
            "source_package_id": self.source_package_id.to_payload(),
            "source_table": self.source_table,
            "source_row_id": self.source_row_id,
            "source_row_number": self.source_row_number,
            "fields": dict(self.fields),
            "text_fields": [text_field.to_payload() for text_field in self.text_fields],
        }

    @classmethod
    def from_payload(cls, payload: NormalizedSourceRowPayload) -> Self:
        return cls(
            source_package_id=_data_package_id_from_payload(payload["source_package_id"]),
            source_table=payload["source_table"],
            source_row_id=payload["source_row_id"],
            source_row_number=payload["source_row_number"],
            fields=tuple(payload["fields"].items()),
            text_fields=tuple(
                SourceTextField.from_payload(text_field) for text_field in payload["text_fields"]
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceRowDiagnostic:
    source_table: str
    source_row_number: int
    source_row_id: str | None
    reason: SourceRowDiagnosticReason
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourceRowDiagnostic source_table", self.source_table),
        )
        if type(self.source_row_number) is not int:
            raise WahapediaSchemaError("SourceRowDiagnostic source_row_number must be an integer.")
        if self.source_row_id is not None:
            object.__setattr__(
                self,
                "source_row_id",
                _validate_identifier(
                    "SourceRowDiagnostic source_row_id",
                    self.source_row_id,
                ),
            )
        if type(self.reason) is not SourceRowDiagnosticReason:
            raise WahapediaSchemaError(
                "SourceRowDiagnostic reason must be SourceRowDiagnosticReason."
            )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("SourceRowDiagnostic message", self.message),
        )

    def to_payload(self) -> SourceRowDiagnosticPayload:
        return {
            "source_table": self.source_table,
            "source_row_number": self.source_row_number,
            "source_row_id": self.source_row_id,
            "reason": self.reason.value,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class WahapediaArtifactBuildReport:
    source_table: str
    rows: tuple[NormalizedSourceRow, ...]
    diagnostics: tuple[SourceRowDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier(
                "WahapediaArtifactBuildReport source_table",
                self.source_table,
            ),
        )
        if type(self.rows) is not tuple:
            raise WahapediaSchemaError("WahapediaArtifactBuildReport rows must be a tuple.")
        if type(self.diagnostics) is not tuple:
            raise WahapediaSchemaError("WahapediaArtifactBuildReport diagnostics must be a tuple.")
        for row in self.rows:
            if type(row) is not NormalizedSourceRow:
                raise WahapediaSchemaError(
                    "WahapediaArtifactBuildReport rows must contain NormalizedSourceRow values."
                )
        for diagnostic in self.diagnostics:
            if type(diagnostic) is not SourceRowDiagnostic:
                raise WahapediaSchemaError(
                    "WahapediaArtifactBuildReport diagnostics must contain diagnostics."
                )

    def diagnostics_by_reason(self) -> dict[str, tuple[SourceRowDiagnostic, ...]]:
        grouped: dict[str, list[SourceRowDiagnostic]] = {}
        for diagnostic in self.diagnostics:
            key = diagnostic.reason.value
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(diagnostic)
        return {
            reason: tuple(
                sorted(
                    diagnostics,
                    key=lambda value: (value.source_row_number, value.source_row_id or ""),
                )
            )
            for reason, diagnostics in sorted(grouped.items())
        }

    def require_success(self) -> None:
        if self.diagnostics:
            reasons = ", ".join(self.diagnostics_by_reason())
            raise WahapediaSchemaError(
                f"Wahapedia artifact build failed with diagnostics: {reasons}."
            )

    def to_payload(self) -> WahapediaArtifactBuildReportPayload:
        return {
            "source_table": self.source_table,
            "rows": [row.to_payload() for row in self.rows],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class WahapediaJsonArtifact:
    source_package_id: DataPackageId
    source_table: str
    source_checksum_sha256: str
    rows: tuple[NormalizedSourceRow, ...]

    def __post_init__(self) -> None:
        if type(self.source_package_id) is not DataPackageId:
            raise WahapediaSchemaError(
                "WahapediaJsonArtifact source_package_id must be a DataPackageId."
            )
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("WahapediaJsonArtifact source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_checksum_sha256",
            _validate_sha256(
                "WahapediaJsonArtifact source_checksum_sha256",
                self.source_checksum_sha256,
            ),
        )
        if type(self.rows) is not tuple:
            raise WahapediaSchemaError("WahapediaJsonArtifact rows must be a tuple.")
        seen: set[str] = set()
        rows: list[NormalizedSourceRow] = []
        for row in self.rows:
            if type(row) is not NormalizedSourceRow:
                raise WahapediaSchemaError(
                    "WahapediaJsonArtifact rows must contain NormalizedSourceRow values."
                )
            if row.source_package_id != self.source_package_id:
                raise WahapediaSchemaError("WahapediaJsonArtifact row package IDs must match.")
            if row.source_table != self.source_table:
                raise WahapediaSchemaError("WahapediaJsonArtifact row tables must match.")
            if row.source_row_id in seen:
                raise WahapediaSchemaError(
                    "WahapediaJsonArtifact rows must not duplicate source row IDs."
                )
            seen.add(row.source_row_id)
            rows.append(row)
        object.__setattr__(self, "rows", tuple(sorted(rows, key=lambda row: row.source_row_id)))

    @classmethod
    def from_csv_table(
        cls,
        *,
        source_package_id: DataPackageId,
        table: WahapediaCsvTable,
        source_checksum_sha256: str | None = None,
        schema: WahapediaTableSchema | None = None,
    ) -> Self:
        selected_schema = schema_for_table(table.table_name) if schema is None else schema
        report = build_wahapedia_artifact_report(
            source_package_id=source_package_id,
            table=table,
            schema=selected_schema,
        )
        report.require_success()
        return cls(
            source_package_id=source_package_id,
            source_table=selected_schema.table_name,
            source_checksum_sha256=(
                table.checksum_sha256
                if source_checksum_sha256 is None
                else _validate_sha256(
                    "WahapediaJsonArtifact source_checksum_sha256",
                    source_checksum_sha256,
                )
            ),
            rows=report.rows,
        )

    def artifact_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def source_artifact_hash(self) -> SourceArtifactHash:
        return SourceArtifactHash(
            artifact_name=f"{self.source_table}.json",
            artifact_hash=self.artifact_hash(),
        )

    def to_json_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def to_payload(self) -> WahapediaJsonArtifactPayload:
        payload = self._payload_without_hash()
        payload["artifact_hash"] = self.artifact_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: WahapediaJsonArtifactPayload) -> Self:
        artifact = cls(
            source_package_id=_data_package_id_from_payload(payload["source_package_id"]),
            source_table=payload["source_table"],
            source_checksum_sha256=payload["source_checksum_sha256"],
            rows=tuple(NormalizedSourceRow.from_payload(row) for row in payload["rows"]),
        )
        if payload["artifact_hash"] != artifact.artifact_hash():
            raise WahapediaSchemaError("WahapediaJsonArtifact artifact_hash is stale.")
        return artifact

    def _payload_without_hash(self) -> WahapediaJsonArtifactPayload:
        return {
            "source_package_id": self.source_package_id.to_payload(),
            "source_table": self.source_table,
            "source_checksum_sha256": self.source_checksum_sha256,
            "rows": [row.to_payload() for row in self.rows],
            "artifact_hash": "",
        }


@dataclass(frozen=True, slots=True)
class WahapediaSourceSnapshot:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    upstream_identity: str
    source_edition: str
    source_files: tuple[SourceFileChecksum, ...]

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise WahapediaSchemaError("WahapediaSourceSnapshot package_id must be DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise WahapediaSchemaError(
                "WahapediaSourceSnapshot catalog_version must be CatalogVersion."
            )
        object.__setattr__(
            self,
            "upstream_identity",
            _validate_identifier(
                "WahapediaSourceSnapshot upstream_identity",
                self.upstream_identity,
            ),
        )
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier("WahapediaSourceSnapshot source_edition", self.source_edition),
        )
        object.__setattr__(
            self,
            "source_files",
            _validate_source_file_tuple(self.source_files),
        )

    def manifest(
        self,
        *,
        artifacts: tuple[SourceArtifactHash, ...] = (),
    ) -> SourcePackageManifest:
        return SourcePackageManifest(
            package_id=self.package_id,
            catalog_version=self.catalog_version,
            upstream_identity=self.upstream_identity,
            source_edition=self.source_edition,
            source_files=self.source_files,
            artifacts=artifacts,
        )

    def to_payload(self) -> WahapediaSourceSnapshotPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "upstream_identity": self.upstream_identity,
            "source_edition": self.source_edition,
            "source_files": [source_file.to_payload() for source_file in self.source_files],
        }

    @classmethod
    def from_payload(cls, payload: WahapediaSourceSnapshotPayload) -> Self:
        return cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            upstream_identity=payload["upstream_identity"],
            source_edition=payload["source_edition"],
            source_files=tuple(
                SourceFileChecksum.from_payload(source_file)
                for source_file in payload["source_files"]
            ),
        )


@dataclass(frozen=True, slots=True)
class EditionSourceConfig:
    source_edition: str
    wahapedia_edition_slug: str
    export_specs_url: str
    csv_delimiter: str = "|"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier("EditionSourceConfig source_edition", self.source_edition),
        )
        object.__setattr__(
            self,
            "wahapedia_edition_slug",
            _validate_identifier(
                "EditionSourceConfig wahapedia_edition_slug",
                self.wahapedia_edition_slug,
            ),
        )
        object.__setattr__(
            self,
            "export_specs_url",
            _validate_url("EditionSourceConfig export_specs_url", self.export_specs_url),
        )
        object.__setattr__(
            self,
            "csv_delimiter",
            _validate_csv_delimiter("EditionSourceConfig csv_delimiter", self.csv_delimiter),
        )

    @classmethod
    def wahapedia_previous_edition_bridge(cls) -> Self:
        previous_edition_number = "1" + "0"
        previous_edition_slug = f"wh40k{previous_edition_number}ed"
        return cls(
            source_edition=f"warhammer-40000-{previous_edition_number}th",
            wahapedia_edition_slug=previous_edition_slug,
            export_specs_url=(
                f"https://wahapedia.ru/{previous_edition_slug}/Export%20Data%20Specs.xlsx"
            ),
        )

    @classmethod
    def wahapedia_11th(cls) -> Self:
        return cls(
            source_edition="warhammer-40000-11th",
            wahapedia_edition_slug="wh40k11ed",
            export_specs_url="https://wahapedia.ru/wh40k11ed/Export%20Data%20Specs.xlsx",
        )

    def to_payload(self) -> EditionSourceConfigPayload:
        return {
            "source_edition": self.source_edition,
            "wahapedia_edition_slug": self.wahapedia_edition_slug,
            "export_specs_url": self.export_specs_url,
            "csv_delimiter": self.csv_delimiter,
        }

    @classmethod
    def from_payload(cls, payload: EditionSourceConfigPayload) -> Self:
        return cls(
            source_edition=payload["source_edition"],
            wahapedia_edition_slug=payload["wahapedia_edition_slug"],
            export_specs_url=payload["export_specs_url"],
            csv_delimiter=payload["csv_delimiter"],
        )


def build_wahapedia_artifact_report(
    *,
    source_package_id: DataPackageId,
    table: WahapediaCsvTable,
    schema: WahapediaTableSchema | None = None,
) -> WahapediaArtifactBuildReport:
    if type(source_package_id) is not DataPackageId:
        raise WahapediaSchemaError("source_package_id must be a DataPackageId.")
    selected_schema = schema_for_table(table.table_name) if schema is None else schema
    if selected_schema.table_name != table.table_name:
        raise WahapediaSchemaError("schema table_name must match CSV table.")

    diagnostics: list[SourceRowDiagnostic] = []
    rows: list[NormalizedSourceRow] = []
    seen_source_ids: set[str] = set()
    if not table.rows:
        diagnostics.append(
            SourceRowDiagnostic(
                source_table=table.table_name,
                source_row_number=1,
                source_row_id=None,
                reason=SourceRowDiagnosticReason.EMPTY_TABLE,
                message="CSV table must contain at least one source row.",
            )
        )
    for row in table.rows:
        try:
            normalized_row = NormalizedSourceRow.from_csv_row(
                source_package_id=source_package_id,
                schema=selected_schema,
                row=row,
            )
        except WahapediaSchemaError as exc:
            diagnostics.append(
                _diagnostic_for_row(
                    table_name=table.table_name,
                    row=row,
                    schema=selected_schema,
                    reason=_reason_from_schema_error_message(str(exc)),
                    message=str(exc),
                )
            )
            continue
        except SourceHtmlSanitizationError as exc:
            diagnostics.append(
                _diagnostic_for_row(
                    table_name=table.table_name,
                    row=row,
                    schema=selected_schema,
                    reason=SourceRowDiagnosticReason.HTML_TAG_IN_RUNTIME_FIELD,
                    message=str(exc),
                )
            )
            continue
        except (TextNormalizationError, RuleTokenError) as exc:
            diagnostics.append(
                _diagnostic_for_row(
                    table_name=table.table_name,
                    row=row,
                    schema=selected_schema,
                    reason=SourceRowDiagnosticReason.NORMALIZATION_FAILED,
                    message=str(exc),
                )
            )
            continue

        if normalized_row.source_row_id in seen_source_ids:
            diagnostics.append(
                SourceRowDiagnostic(
                    source_table=table.table_name,
                    source_row_number=row.row_number,
                    source_row_id=normalized_row.source_row_id,
                    reason=SourceRowDiagnosticReason.DUPLICATE_SOURCE_ROW_ID,
                    message="Source row ID is duplicated in CSV table.",
                )
            )
            continue
        seen_source_ids.add(normalized_row.source_row_id)
        rows.append(normalized_row)

    return WahapediaArtifactBuildReport(
        source_table=table.table_name,
        rows=tuple(rows),
        diagnostics=tuple(diagnostics),
    )


def schema_for_table(table_name: object) -> WahapediaTableSchema:
    table = _validate_identifier("table_name", table_name)
    for schema in WAHAPEDIA_TABLE_SCHEMAS:
        if schema.table_name == table:
            return schema
    raise WahapediaSchemaError(f"Unsupported Wahapedia source table: {table}.")


def _validate_required_columns(*, schema: WahapediaTableSchema, row: WahapediaCsvRow) -> None:
    row_columns = {column_name for column_name, _value in row.values}
    missing = tuple(column for column in schema.required_columns if column not in row_columns)
    if missing:
        raise WahapediaSchemaError(f"required source columns are missing: {', '.join(missing)}.")


def _diagnostic_for_row(
    *,
    table_name: str,
    row: WahapediaCsvRow,
    schema: WahapediaTableSchema,
    reason: SourceRowDiagnosticReason,
    message: str,
) -> SourceRowDiagnostic:
    source_row_id: str | None
    try:
        source_row_id = schema.source_row_id(row)
    except WahapediaSchemaError:
        source_row_id = None
    return SourceRowDiagnostic(
        source_table=table_name,
        source_row_number=row.row_number,
        source_row_id=source_row_id,
        reason=reason,
        message=message,
    )


def _reason_from_schema_error_message(message: str) -> SourceRowDiagnosticReason:
    if "column" in message and "missing" in message:
        return SourceRowDiagnosticReason.MISSING_COLUMN
    if "source row ID" in message:
        return SourceRowDiagnosticReason.MISSING_SOURCE_ROW_ID
    if "HTML" in message:
        return SourceRowDiagnosticReason.HTML_TAG_IN_RUNTIME_FIELD
    return SourceRowDiagnosticReason.MALFORMED_CSV_ROW


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise WahapediaSchemaError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise WahapediaSchemaError(f"{field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WahapediaSchemaError(f"{field_name} must be a tuple.")
    if not values and not allow_empty:
        raise WahapediaSchemaError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise WahapediaSchemaError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_source_row_id_empty_tokens(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if type(values) is not tuple:
        raise WahapediaSchemaError(
            "WahapediaTableSchema source_row_id_empty_tokens must be a tuple."
        )
    seen: set[str] = set()
    validated: list[tuple[str, str]] = []
    for column_name, token in values:
        column = _validate_identifier("source_row_id_empty_tokens column", column_name)
        replacement = _validate_identifier("source_row_id_empty_tokens token", token)
        if column in seen:
            raise WahapediaSchemaError(
                "WahapediaTableSchema source_row_id_empty_tokens must not duplicate columns."
            )
        seen.add(column)
        validated.append((column, replacement))
    return tuple(validated)


def _with_repaired_unquoted_newline_rows(
    rows: tuple[list[str], ...],
) -> tuple[list[str], ...]:
    header_width = len(rows[0])
    repaired: list[list[str]] = [rows[0]]
    index = 1
    while index < len(rows):
        row = rows[index]
        physical_row_number = index + 1
        index += 1
        if len(row) >= header_width:
            repaired.append(row)
            continue
        current = row
        while len(current) < header_width:
            if index >= len(rows):
                raise WahapediaSchemaError(
                    f"CSV row {physical_row_number} has an unterminated multiline field."
                )
            continuation = rows[index]
            index += 1
            if not current or not continuation:
                raise WahapediaSchemaError(
                    f"CSV row {physical_row_number} has an invalid multiline field."
                )
            current = [
                *current[:-1],
                f"{current[-1]}\n{continuation[0]}",
                *continuation[1:],
            ]
            if len(current) > header_width:
                raise WahapediaSchemaError(
                    f"CSV row {physical_row_number} multiline field exceeds header width."
                )
        repaired.append(current)
    return tuple(repaired)


def _without_trailing_empty_export_column(
    rows: tuple[list[str], ...],
) -> tuple[list[str], ...]:
    header = rows[0]
    if not header or header[-1].strip():
        return rows
    normalized: list[list[str]] = []
    expected_width = len(header)
    for index, row in enumerate(rows, start=1):
        if len(row) != expected_width:
            raise WahapediaSchemaError(
                f"CSV row {index} does not match trailing-delimiter export width."
            )
        if row[-1].strip():
            raise WahapediaSchemaError(f"CSV row {index} trailing export column must be empty.")
        normalized.append(row[:-1])
    return tuple(normalized)


def _validate_field_tuple(values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if type(values) is not tuple:
        raise WahapediaSchemaError("NormalizedSourceRow fields must be a tuple.")
    seen: set[str] = set()
    validated: list[tuple[str, str]] = []
    for column_name, value in values:
        column = _validate_identifier("NormalizedSourceRow field column", column_name)
        if column in seen:
            raise WahapediaSchemaError("NormalizedSourceRow fields must not duplicate columns.")
        if type(value) is not str:
            raise WahapediaSchemaError("NormalizedSourceRow field values must be strings.")
        if contains_html_markup(value):
            raise WahapediaSchemaError("NormalizedSourceRow field value contains HTML markup.")
        seen.add(column)
        validated.append((column, value))
    return tuple(validated)


def _validate_text_field_tuple(
    values: tuple[SourceTextField, ...],
) -> tuple[SourceTextField, ...]:
    if type(values) is not tuple:
        raise WahapediaSchemaError("NormalizedSourceRow text_fields must be a tuple.")
    seen: set[str] = set()
    validated: list[SourceTextField] = []
    for value in values:
        if type(value) is not SourceTextField:
            raise WahapediaSchemaError(
                "NormalizedSourceRow text_fields must contain SourceTextField values."
            )
        if value.column_name in seen:
            raise WahapediaSchemaError(
                "NormalizedSourceRow text_fields must not duplicate columns."
            )
        seen.add(value.column_name)
        validated.append(value)
    return tuple(validated)


def _validate_source_file_tuple(
    values: tuple[SourceFileChecksum, ...],
) -> tuple[SourceFileChecksum, ...]:
    if type(values) is not tuple:
        raise WahapediaSchemaError("WahapediaSourceSnapshot source_files must be a tuple.")
    if not values:
        raise WahapediaSchemaError("WahapediaSourceSnapshot source_files must not be empty.")
    seen: set[str] = set()
    validated: list[SourceFileChecksum] = []
    for value in values:
        if type(value) is not SourceFileChecksum:
            raise WahapediaSchemaError(
                "WahapediaSourceSnapshot source_files must contain SourceFileChecksum values."
            )
        if value.path in seen:
            raise WahapediaSchemaError("WahapediaSourceSnapshot source_files must be unique.")
        seen.add(value.path)
        validated.append(value)
    return tuple(sorted(validated, key=lambda source_file: source_file.path))


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise WahapediaSchemaError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise WahapediaSchemaError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return digest


def _validate_csv_delimiter(field_name: str, value: object) -> str:
    delimiter = _validate_identifier(field_name, value)
    if len(delimiter) != 1:
        raise WahapediaSchemaError(f"{field_name} must be a single-character delimiter.")
    if delimiter in {"\r", "\n", '"'}:
        raise WahapediaSchemaError(f"{field_name} cannot be a CSV control character.")
    return delimiter


def _validate_url(field_name: str, value: object) -> str:
    url = _validate_identifier(field_name, value)
    if not url.startswith(("https://", "http://")):
        raise WahapediaSchemaError(f"{field_name} must be an HTTP(S) URL.")
    return url


def _source_text_id(
    *,
    source_package_id: DataPackageId,
    table_name: str,
    source_row_id: str,
    column_name: str,
) -> str:
    return f"{source_package_id.stable_identity()}:{table_name}:{source_row_id}:{column_name}"


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise WahapediaSchemaError("DataPackageId payload is invalid.") from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise WahapediaSchemaError("CatalogVersion payload is invalid.") from exc


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


WAHAPEDIA_TABLE_SCHEMAS = (
    WahapediaTableSchema(
        table_name="Abilities",
        source_row_id_columns=("id", "faction_id"),
        text_columns=("name", "description"),
        required_columns=("id", "faction_id", "name", "description"),
        optional_text_columns=("legend",),
        source_row_id_empty_tokens=(("faction_id", "global"),),
    ),
    WahapediaTableSchema(
        table_name="Datasheets",
        source_row_id_columns=("id",),
        text_columns=("name",),
        required_columns=("id", "name"),
        optional_text_columns=(
            "legend",
            "loadout",
            "transport",
            "leader_head",
            "leader_footer",
            "damaged_description",
        ),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_abilities",
        source_row_id_columns=("datasheet_id", "line"),
        text_columns=(),
        required_columns=("datasheet_id", "line"),
        optional_text_columns=("name", "description", "parameter"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_detachment_abilities",
        source_row_id_columns=("datasheet_id", "detachment_ability_id"),
        text_columns=(),
        required_columns=("datasheet_id", "detachment_ability_id"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_enhancements",
        source_row_id_columns=("datasheet_id", "enhancement_id"),
        text_columns=(),
        required_columns=("datasheet_id", "enhancement_id"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_keywords",
        source_row_id_columns=(
            "datasheet_id",
            "keyword",
            "model",
            "is_faction_keyword",
            _SOURCE_ROW_NUMBER_ID_COLUMN,
        ),
        text_columns=(),
        required_columns=("datasheet_id", "keyword", "model", "is_faction_keyword"),
        optional_text_columns=("keyword", "model"),
        source_row_id_empty_tokens=(
            ("keyword", "blank-keyword"),
            ("model", "global"),
        ),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_leader",
        source_row_id_columns=("leader_id", "attached_id", _SOURCE_ROW_NUMBER_ID_COLUMN),
        text_columns=(),
        required_columns=("leader_id", "attached_id"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_models",
        source_row_id_columns=("datasheet_id", "line"),
        text_columns=(),
        required_columns=("datasheet_id", "line"),
        optional_text_columns=("name", "inv_sv_descr", "base_size_descr"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_models_cost",
        source_row_id_columns=("datasheet_id", "line"),
        text_columns=("description",),
        required_columns=("datasheet_id", "line", "description"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_options",
        source_row_id_columns=("datasheet_id", "line"),
        text_columns=("description",),
        required_columns=("datasheet_id", "line", "description"),
        optional_text_columns=("button",),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_stratagems",
        source_row_id_columns=("datasheet_id", "stratagem_id"),
        text_columns=(),
        required_columns=("datasheet_id", "stratagem_id"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_unit_composition",
        source_row_id_columns=("datasheet_id", "line"),
        text_columns=("description",),
        required_columns=("datasheet_id", "line", "description"),
    ),
    WahapediaTableSchema(
        table_name="Datasheets_wargear",
        source_row_id_columns=(
            "datasheet_id",
            "line",
            "line_in_wargear",
            _SOURCE_ROW_NUMBER_ID_COLUMN,
        ),
        text_columns=(),
        required_columns=("datasheet_id", "line", "line_in_wargear"),
        optional_text_columns=("name", "description"),
        source_row_id_empty_tokens=(("line", "blank-line"),),
    ),
    WahapediaTableSchema(
        table_name="Detachment_abilities",
        source_row_id_columns=("id",),
        text_columns=("name", "description"),
        required_columns=("id", "name", "description"),
        optional_text_columns=("legend", "detachment"),
    ),
    WahapediaTableSchema(
        table_name="Factions",
        source_row_id_columns=("id",),
        text_columns=("name",),
        required_columns=("id", "name"),
    ),
    WahapediaTableSchema(
        table_name="Last_update",
        source_row_id_columns=("last_update",),
        text_columns=(),
        required_columns=("last_update",),
    ),
    WahapediaTableSchema(
        table_name="Source",
        source_row_id_columns=("id",),
        text_columns=("name",),
        required_columns=("id", "name"),
        optional_text_columns=("type", "edition", "version"),
    ),
    WahapediaTableSchema(
        table_name="Detachments",
        source_row_id_columns=("id",),
        text_columns=("name",),
        required_columns=("id", "name"),
        optional_text_columns=("legend", "type"),
    ),
    WahapediaTableSchema(
        table_name="Enhancements",
        source_row_id_columns=("id",),
        text_columns=("name", "description"),
        required_columns=("id", "name", "description"),
        optional_text_columns=("legend", "detachment"),
    ),
    WahapediaTableSchema(
        table_name="Stratagems",
        source_row_id_columns=("id",),
        text_columns=("name", "description"),
        required_columns=("id", "name", "description"),
        optional_text_columns=("legend", "type", "turn", "phase", "detachment"),
    ),
)
