from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageRow,
    Phase17ECoverageStatus,
)

EDITION_ID = "warhammer_40000_11th"
SOURCE_EDITION = "11th"
SOURCE_PACKAGE_ID = "gw-11e-phase17f-faction-execution-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Phase 17F Faction Execution"
SOURCE_VERSION = "2026-27"
SOURCE_DATE = "2026-06-11"
UPSTREAM_IDENTITY = faction_coverage_2026_27.SOURCE_PACKAGE_ID
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17f-faction-execution-v1"


class Phase17FFactionExecutionError(ValueError):
    """Raised when Phase 17F faction execution data violates CORE V2 invariants."""


class Phase17FExecutionStatus(StrEnum):
    EXECUTABLE_GENERIC_IR = "executable_generic_ir"
    EXECUTABLE_NAMED_HANDLER = "executable_named_handler"
    BLOCKED_STRUCTURED_SEMANTICS_REQUIRED = "blocked_structured_semantics_required"
    BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP = "blocked_approved_unsupported_source_gap"


class Phase17FExecutionBlockReason(StrEnum):
    STRUCTURED_RULE_SEMANTICS_REQUIRED = "structured_rule_semantics_required"
    APPROVED_PHASE17E_SOURCE_GAP = "approved_phase17e_source_gap"


APPROVED_EXECUTION_BLOCK_REASONS = frozenset(
    {
        Phase17FExecutionBlockReason.STRUCTURED_RULE_SEMANTICS_REQUIRED,
        Phase17FExecutionBlockReason.APPROVED_PHASE17E_SOURCE_GAP,
    }
)


class Phase17FExecutionRecordPayload(TypedDict):
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: str
    coverage_status: str
    execution_status: str
    block_reason: str | None
    faction_id: str
    faction_name: str
    detachment_id: str | None
    detachment_name: str | None
    source_ids: list[str]
    source_pdf_package_id: str
    rule_name: str
    handler_id: str | None
    rule_ir_hash: str | None
    phase17e_unsupported_reason: str | None


class Phase17FExecutionPackagePayload(TypedDict):
    edition_id: str
    source_edition: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    upstream_identity: str
    imported_at_schema_version: str
    source_payload_checksum_sha256: str
    upstream_payload_checksum_sha256: str
    execution_records: list[Phase17FExecutionRecordPayload]
    status_counts: dict[str, int]
    blocked_count: int
    unapproved_blocked_count: int


@dataclass(frozen=True, slots=True)
class Phase17FExecutionRecord:
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: Phase17ECoverageKind
    coverage_status: Phase17ECoverageStatus
    execution_status: Phase17FExecutionStatus
    faction_id: str
    faction_name: str
    source_ids: tuple[str, ...]
    source_pdf_package_id: str
    rule_name: str
    detachment_id: str | None = None
    detachment_name: str | None = None
    handler_id: str | None = None
    rule_ir_hash: str | None = None
    block_reason: Phase17FExecutionBlockReason | None = None
    phase17e_unsupported_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_id",
            _validate_identifier("execution_id", self.execution_id),
        )
        object.__setattr__(
            self,
            "coverage_descriptor_id",
            _validate_identifier("coverage_descriptor_id", self.coverage_descriptor_id),
        )
        object.__setattr__(
            self,
            "coverage_kind",
            _coverage_kind_from_token(self.coverage_kind),
        )
        object.__setattr__(
            self,
            "coverage_status",
            _coverage_status_from_token(self.coverage_status),
        )
        execution_status = _execution_status_from_token(self.execution_status)
        object.__setattr__(self, "execution_status", execution_status)
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(
            self,
            "faction_name",
            _validate_non_empty_text("faction_name", self.faction_name),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )
        object.__setattr__(
            self,
            "source_pdf_package_id",
            _validate_identifier("source_pdf_package_id", self.source_pdf_package_id),
        )
        object.__setattr__(self, "rule_name", _validate_non_empty_text("rule_name", self.rule_name))
        if self.detachment_id is not None:
            object.__setattr__(
                self,
                "detachment_id",
                _validate_identifier("detachment_id", self.detachment_id),
            )
        if self.detachment_name is not None:
            object.__setattr__(
                self,
                "detachment_name",
                _validate_non_empty_text("detachment_name", self.detachment_name),
            )
        if self.handler_id is not None:
            object.__setattr__(
                self,
                "handler_id",
                _validate_identifier("handler_id", self.handler_id),
            )
        if self.rule_ir_hash is not None:
            object.__setattr__(
                self,
                "rule_ir_hash",
                _validate_sha256("rule_ir_hash", self.rule_ir_hash),
            )
        block_reason = self.block_reason
        if block_reason is not None:
            block_reason = _block_reason_from_token(block_reason)
            object.__setattr__(self, "block_reason", block_reason)
        if self.phase17e_unsupported_reason is not None:
            object.__setattr__(
                self,
                "phase17e_unsupported_reason",
                _validate_identifier(
                    "phase17e_unsupported_reason",
                    self.phase17e_unsupported_reason,
                ),
            )

        if self.is_blocked and block_reason is None:
            raise Phase17FFactionExecutionError("Blocked Phase17F rows require block_reason.")
        if not self.is_blocked and block_reason is not None:
            raise Phase17FFactionExecutionError(
                "Only blocked Phase17F rows can include block_reason."
            )
        if (
            execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
            and self.handler_id is None
        ):
            raise Phase17FFactionExecutionError(
                "Structured-semantics blocked rows require handler_id."
            )
        if (
            execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
            and self.rule_ir_hash is None
        ):
            raise Phase17FFactionExecutionError("Generic executable rows require rule_ir_hash.")
        if (
            execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
            and self.handler_id is None
        ):
            raise Phase17FFactionExecutionError("Named-handler executable rows require handler_id.")
        if (
            execution_status is Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP
            and self.phase17e_unsupported_reason is None
        ):
            raise Phase17FFactionExecutionError(
                "Approved-source-gap rows require phase17e_unsupported_reason."
            )

    @property
    def is_blocked(self) -> bool:
        return self.execution_status in {
            Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED,
            Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP,
        }

    @property
    def is_approved_blocked(self) -> bool:
        return self.is_blocked and self.block_reason in APPROVED_EXECUTION_BLOCK_REASONS

    def to_payload(self) -> Phase17FExecutionRecordPayload:
        return {
            "execution_id": self.execution_id,
            "coverage_descriptor_id": self.coverage_descriptor_id,
            "coverage_kind": self.coverage_kind.value,
            "coverage_status": self.coverage_status.value,
            "execution_status": self.execution_status.value,
            "block_reason": None if self.block_reason is None else self.block_reason.value,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "source_ids": list(self.source_ids),
            "source_pdf_package_id": self.source_pdf_package_id,
            "rule_name": self.rule_name,
            "handler_id": self.handler_id,
            "rule_ir_hash": self.rule_ir_hash,
            "phase17e_unsupported_reason": self.phase17e_unsupported_reason,
        }

    @classmethod
    def from_payload(cls, payload: Phase17FExecutionRecordPayload) -> Self:
        block_reason = payload["block_reason"]
        return cls(
            execution_id=payload["execution_id"],
            coverage_descriptor_id=payload["coverage_descriptor_id"],
            coverage_kind=_coverage_kind_from_token(payload["coverage_kind"]),
            coverage_status=_coverage_status_from_token(payload["coverage_status"]),
            execution_status=_execution_status_from_token(payload["execution_status"]),
            block_reason=None if block_reason is None else _block_reason_from_token(block_reason),
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            source_ids=tuple(payload["source_ids"]),
            source_pdf_package_id=payload["source_pdf_package_id"],
            rule_name=payload["rule_name"],
            handler_id=payload["handler_id"],
            rule_ir_hash=payload["rule_ir_hash"],
            phase17e_unsupported_reason=payload["phase17e_unsupported_reason"],
        )


@dataclass(frozen=True, slots=True)
class Phase17FExecutionPackage:
    execution_records: tuple[Phase17FExecutionRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_records",
            _validate_execution_records(self.execution_records),
        )

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Phase17FExecutionStatus}
        for record in self.execution_records:
            counts[record.execution_status.value] += 1
        return counts

    def blocked_records(self) -> tuple[Phase17FExecutionRecord, ...]:
        return tuple(record for record in self.execution_records if record.is_blocked)

    def unapproved_blocked_records(self) -> tuple[Phase17FExecutionRecord, ...]:
        return tuple(
            record
            for record in self.execution_records
            if record.is_blocked and not record.is_approved_blocked
        )

    def payload_without_checksum(self) -> Phase17FExecutionPackagePayload:
        blocked_records = self.blocked_records()
        unapproved_records = self.unapproved_blocked_records()
        return {
            "edition_id": EDITION_ID,
            "source_edition": SOURCE_EDITION,
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_title": SOURCE_TITLE,
            "source_version": SOURCE_VERSION,
            "source_date": SOURCE_DATE,
            "upstream_identity": UPSTREAM_IDENTITY,
            "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
            "source_payload_checksum_sha256": "",
            "upstream_payload_checksum_sha256": _upstream_payload_checksum_sha256(),
            "execution_records": [record.to_payload() for record in self.execution_records],
            "status_counts": self.status_counts(),
            "blocked_count": len(blocked_records),
            "unapproved_blocked_count": len(unapproved_records),
        }

    def source_payload_checksum_sha256(self) -> str:
        return _sha256_payload(self.payload_without_checksum())

    def to_payload(self) -> Phase17FExecutionPackagePayload:
        payload = self.payload_without_checksum()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: Phase17FExecutionPackagePayload) -> Self:
        package = cls(
            execution_records=tuple(
                Phase17FExecutionRecord.from_payload(record)
                for record in payload["execution_records"]
            )
        )
        if package.source_payload_checksum_sha256() != payload["source_payload_checksum_sha256"]:
            raise Phase17FFactionExecutionError("Phase17F execution payload checksum is stale.")
        if _upstream_payload_checksum_sha256() != payload["upstream_payload_checksum_sha256"]:
            raise Phase17FFactionExecutionError("Phase17F upstream payload checksum is stale.")
        return package


def phase17f_execution_package() -> Phase17FExecutionPackage:
    return Phase17FExecutionPackage(
        execution_records=tuple(_execution_record(row) for row in _coverage_rows())
    )


def execution_records() -> tuple[Phase17FExecutionRecord, ...]:
    return phase17f_execution_package().execution_records


def source_package_identity_payload() -> dict[str, str]:
    package = phase17f_execution_package()
    return {
        "edition_id": EDITION_ID,
        "source_edition": SOURCE_EDITION,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "upstream_identity": UPSTREAM_IDENTITY,
        "source_payload_checksum_sha256": package.source_payload_checksum_sha256(),
        "upstream_payload_checksum_sha256": _upstream_payload_checksum_sha256(),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def _coverage_rows() -> tuple[Phase17ECoverageRow, ...]:
    return faction_coverage_2026_27.coverage_rows()


def _execution_record(row: Phase17ECoverageRow) -> Phase17FExecutionRecord:
    if row.status is Phase17ECoverageStatus.UNSUPPORTED:
        if row.unsupported_reason is None:
            raise Phase17FFactionExecutionError("Phase17E unsupported row lacks reason.")
        execution_status = Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP
        block_reason = Phase17FExecutionBlockReason.APPROVED_PHASE17E_SOURCE_GAP
        phase17e_unsupported_reason = row.unsupported_reason.value
    elif row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED:
        execution_status = Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
        block_reason = Phase17FExecutionBlockReason.STRUCTURED_RULE_SEMANTICS_REQUIRED
        phase17e_unsupported_reason = None
    elif row.status is Phase17ECoverageStatus.GENERIC_SUPPORTED:
        execution_status = Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        block_reason = None
        phase17e_unsupported_reason = None
    elif row.status is Phase17ECoverageStatus.IMPLEMENTED:
        execution_status = Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
        block_reason = None
        phase17e_unsupported_reason = None
    else:
        raise Phase17FFactionExecutionError("Unsupported Phase17E coverage status.")

    return Phase17FExecutionRecord(
        execution_id=f"phase17f:{row.descriptor_id}",
        coverage_descriptor_id=row.descriptor_id,
        coverage_kind=row.coverage_kind,
        coverage_status=row.status,
        execution_status=execution_status,
        block_reason=block_reason,
        faction_id=row.faction_id,
        faction_name=row.faction_name,
        detachment_id=row.detachment_id,
        detachment_name=row.detachment_name,
        source_ids=row.source_ids,
        source_pdf_package_id=row.source_pdf_package_id,
        rule_name=row.rule_name,
        handler_id=row.handler_id,
        rule_ir_hash=row.rule_ir_hash,
        phase17e_unsupported_reason=phase17e_unsupported_reason,
    )


def _validate_execution_records(
    records: tuple[Phase17FExecutionRecord, ...],
) -> tuple[Phase17FExecutionRecord, ...]:
    if type(records) is not tuple:
        raise Phase17FFactionExecutionError("Phase17F execution_records must be a tuple.")
    coverage_rows_by_descriptor_id = {row.descriptor_id: row for row in _coverage_rows()}
    coverage_descriptor_ids = set(coverage_rows_by_descriptor_id)
    seen: set[str] = set()
    covered: set[str] = set()
    validated: list[Phase17FExecutionRecord] = []
    for record in records:
        if type(record) is not Phase17FExecutionRecord:
            raise Phase17FFactionExecutionError(
                "Phase17F execution_records must contain Phase17FExecutionRecord values."
            )
        if record.execution_id in seen:
            raise Phase17FFactionExecutionError("Phase17F execution_records must be unique.")
        if record.coverage_descriptor_id not in coverage_descriptor_ids:
            raise Phase17FFactionExecutionError(
                "Phase17F execution record references unknown Phase17E coverage row."
            )
        coverage_row = coverage_rows_by_descriptor_id[record.coverage_descriptor_id]
        expected_record = _execution_record(coverage_row)
        if record.to_payload() != expected_record.to_payload():
            raise Phase17FFactionExecutionError(
                "Phase17F execution record does not match Phase17E coverage row."
            )
        seen.add(record.execution_id)
        covered.add(record.coverage_descriptor_id)
        validated.append(record)
    if covered != coverage_descriptor_ids:
        raise Phase17FFactionExecutionError(
            "Phase17F execution_records must cover every Phase17E coverage row."
        )
    return tuple(sorted(validated, key=lambda record: record.execution_id))


def _coverage_kind_from_token(token: object) -> Phase17ECoverageKind:
    if type(token) is Phase17ECoverageKind:
        return token
    if type(token) is not str:
        raise Phase17FFactionExecutionError("Phase17F coverage kind token must be a string.")
    try:
        return Phase17ECoverageKind(token)
    except ValueError as exc:
        raise Phase17FFactionExecutionError(
            f"Unsupported Phase17F coverage kind: {token}."
        ) from exc


def _coverage_status_from_token(token: object) -> Phase17ECoverageStatus:
    if type(token) is Phase17ECoverageStatus:
        return token
    if type(token) is not str:
        raise Phase17FFactionExecutionError("Phase17F coverage status token must be a string.")
    try:
        return Phase17ECoverageStatus(token)
    except ValueError as exc:
        raise Phase17FFactionExecutionError(
            f"Unsupported Phase17F coverage status: {token}."
        ) from exc


def _execution_status_from_token(token: object) -> Phase17FExecutionStatus:
    if type(token) is Phase17FExecutionStatus:
        return token
    if type(token) is not str:
        raise Phase17FFactionExecutionError("Phase17F execution status token must be a string.")
    try:
        return Phase17FExecutionStatus(token)
    except ValueError as exc:
        raise Phase17FFactionExecutionError(
            f"Unsupported Phase17F execution status: {token}."
        ) from exc


def _block_reason_from_token(token: object) -> Phase17FExecutionBlockReason:
    if type(token) is Phase17FExecutionBlockReason:
        return token
    if type(token) is not str:
        raise Phase17FFactionExecutionError("Phase17F block reason token must be a string.")
    try:
        return Phase17FExecutionBlockReason(token)
    except ValueError as exc:
        raise Phase17FFactionExecutionError(f"Unsupported Phase17F block reason: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise Phase17FFactionExecutionError(f"Phase17F {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise Phase17FFactionExecutionError(f"Phase17F {field_name} must not be empty.")
    return stripped


def _validate_non_empty_text(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise Phase17FFactionExecutionError(f"Phase17F {field_name} must be a tuple.")
    if not values:
        raise Phase17FFactionExecutionError(f"Phase17F {field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise Phase17FFactionExecutionError(f"Phase17F {field_name} must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise Phase17FFactionExecutionError(f"Phase17F {field_name} must be a SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise Phase17FFactionExecutionError(
            f"Phase17F {field_name} must be a lowercase SHA-256 digest."
        )
    return digest


def _upstream_payload_checksum_sha256() -> str:
    return faction_coverage_2026_27.source_package_identity_payload()[
        "source_payload_checksum_sha256"
    ]


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
