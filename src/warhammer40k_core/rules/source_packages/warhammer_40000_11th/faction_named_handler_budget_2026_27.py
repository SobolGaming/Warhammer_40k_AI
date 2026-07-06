from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17i-named-handler-budget-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Phase 17I Named Handler Budget"
SOURCE_VERSION = "2026-27"
SOURCE_DATE = "2026-07-03"
SOURCE_EDITION = "11th"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17i-named-handler-budget-v1"

_APPROVED_PRE_WS14_NAMED_HANDLER_EXECUTION_IDS = (
    "phase17f:phase17e:adepta-sororitas:army-rule",
    "phase17f:phase17e:adeptus-custodes:army-rule",
    "phase17f:phase17e:adeptus-mechanicus:army-rule",
    "phase17f:phase17e:aeldari:army-rule",
    "phase17f:phase17e:astra-militarum:army-rule",
    "phase17f:phase17e:black-templars:army-rule",
    "phase17f:phase17e:chaos-daemons:army-rule",
    "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule",
    "phase17f:phase17e:chaos-knights:army-rule",
    "phase17f:phase17e:chaos-space-marines:army-rule",
    "phase17f:phase17e:death-guard:army-rule",
    "phase17f:phase17e:drukhari:army-rule",
    "phase17f:phase17e:emperors-children:army-rule",
    "phase17f:phase17e:enhancement:aeldari:corsair-coterie:archraider",
    "phase17f:phase17e:enhancement:aeldari:corsair-coterie:infamy",
    "phase17f:phase17e:enhancement:aeldari:corsair-coterie:voidstone",
    "phase17f:phase17e:enhancement:aeldari:corsair-coterie:webway-pathstone",
    "phase17f:phase17e:genestealer-cults:army-rule",
    "phase17f:phase17e:grey-knights:army-rule",
    "phase17f:phase17e:imperial-knights:army-rule",
    "phase17f:phase17e:leagues-of-votann:army-rule",
    "phase17f:phase17e:necrons:army-rule",
    "phase17f:phase17e:orks:army-rule",
    "phase17f:phase17e:space-marines:army-rule",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:cloak-and-shadow",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:into-the-breach",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:lethal-ruse",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:outcast-ambush",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:pirates-due",
    "phase17f:phase17e:stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:vengeful-sorrow",
    "phase17f:phase17e:stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:casting-back-the-veil",
    "phase17f:phase17e:stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:eldritch-suppression",
    "phase17f:phase17e:stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:nomads-of-the-hidden-way",
    "phase17f:phase17e:tau-empire:army-rule",
    "phase17f:phase17e:thousand-sons:army-rule",
    "phase17f:phase17e:tyranids:army-rule",
    "phase17f:phase17e:world-eaters:army-rule",
)


class Phase17INamedHandlerBudgetError(ValueError):
    """Raised when the Phase 17I named-handler budget is inconsistent."""


class Phase17INamedHandlerApprovalReason(StrEnum):
    PRE_WS14_EXISTING_RUNTIME_CONSUMER = "pre_ws14_existing_runtime_consumer"


class Phase17INamedHandlerBudgetEntryPayload(TypedDict):
    execution_id: str
    approved_reason: str


class Phase17INamedHandlerBudgetReportPayload(TypedDict):
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    upstream_identity: str
    source_edition: str
    imported_at_schema_version: str
    source_payload_checksum_sha256: str
    upstream_payload_checksum_sha256: str
    named_handler_count: int
    approved_named_handler_count: int
    unapproved_named_handler_count: int
    stale_approval_count: int
    approval_reason_counts: dict[str, int]
    named_handler_execution_ids: list[str]
    unapproved_named_handler_execution_ids: list[str]
    stale_approved_execution_ids: list[str]
    approved_entries: list[Phase17INamedHandlerBudgetEntryPayload]


@dataclass(frozen=True, slots=True)
class Phase17INamedHandlerBudgetEntry:
    execution_id: str
    approved_reason: Phase17INamedHandlerApprovalReason

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_id", _validate_identifier("execution_id", self.execution_id)
        )
        object.__setattr__(
            self,
            "approved_reason",
            _approval_reason_from_token(self.approved_reason),
        )

    def to_payload(self) -> Phase17INamedHandlerBudgetEntryPayload:
        return {
            "execution_id": self.execution_id,
            "approved_reason": self.approved_reason.value,
        }

    @classmethod
    def from_payload(cls, payload: Phase17INamedHandlerBudgetEntryPayload) -> Self:
        return cls(
            execution_id=payload["execution_id"],
            approved_reason=_approval_reason_from_token(payload["approved_reason"]),
        )


@dataclass(frozen=True, slots=True)
class Phase17INamedHandlerBudgetReport:
    approved_entries: tuple[Phase17INamedHandlerBudgetEntry, ...]
    named_handler_records: tuple[Phase17FExecutionRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approved_entries",
            _validate_budget_entries(self.approved_entries),
        )
        object.__setattr__(
            self,
            "named_handler_records",
            _validate_named_handler_records(self.named_handler_records),
        )

    @property
    def named_handler_execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted(record.execution_id for record in self.named_handler_records))

    @property
    def approved_execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted(entry.execution_id for entry in self.approved_entries))

    @property
    def unapproved_named_handler_execution_ids(self) -> tuple[str, ...]:
        approved_ids = set(self.approved_execution_ids)
        return tuple(
            execution_id
            for execution_id in self.named_handler_execution_ids
            if execution_id not in approved_ids
        )

    @property
    def stale_approved_execution_ids(self) -> tuple[str, ...]:
        named_handler_ids = set(self.named_handler_execution_ids)
        return tuple(
            execution_id
            for execution_id in self.approved_execution_ids
            if execution_id not in named_handler_ids
        )

    def approval_reason_counts(self) -> dict[str, int]:
        counts = {reason.value: 0 for reason in Phase17INamedHandlerApprovalReason}
        for entry in self.approved_entries:
            counts[entry.approved_reason.value] += 1
        return counts

    def payload_without_checksum(self) -> Phase17INamedHandlerBudgetReportPayload:
        return {
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_title": SOURCE_TITLE,
            "source_version": SOURCE_VERSION,
            "source_date": SOURCE_DATE,
            "upstream_identity": faction_execution_2026_27.SOURCE_PACKAGE_ID,
            "source_edition": SOURCE_EDITION,
            "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
            "source_payload_checksum_sha256": "",
            "upstream_payload_checksum_sha256": _upstream_payload_checksum_sha256(),
            "named_handler_count": len(self.named_handler_records),
            "approved_named_handler_count": len(self.approved_entries),
            "unapproved_named_handler_count": len(self.unapproved_named_handler_execution_ids),
            "stale_approval_count": len(self.stale_approved_execution_ids),
            "approval_reason_counts": self.approval_reason_counts(),
            "named_handler_execution_ids": list(self.named_handler_execution_ids),
            "unapproved_named_handler_execution_ids": list(
                self.unapproved_named_handler_execution_ids
            ),
            "stale_approved_execution_ids": list(self.stale_approved_execution_ids),
            "approved_entries": [entry.to_payload() for entry in self.approved_entries],
        }

    def source_payload_checksum_sha256(self) -> str:
        return _sha256_payload(self.payload_without_checksum())

    def to_payload(self) -> Phase17INamedHandlerBudgetReportPayload:
        payload = self.payload_without_checksum()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: Phase17INamedHandlerBudgetReportPayload) -> Self:
        report = cls(
            approved_entries=tuple(
                Phase17INamedHandlerBudgetEntry.from_payload(entry)
                for entry in payload["approved_entries"]
            ),
            named_handler_records=_named_handler_records(),
        )
        if report.source_payload_checksum_sha256() != payload["source_payload_checksum_sha256"]:
            raise Phase17INamedHandlerBudgetError("Phase17I named-handler budget payload is stale.")
        if _upstream_payload_checksum_sha256() != payload["upstream_payload_checksum_sha256"]:
            raise Phase17INamedHandlerBudgetError(
                "Phase17I named-handler budget upstream payload checksum is stale."
            )
        return report


def phase17i_named_handler_budget_report() -> Phase17INamedHandlerBudgetReport:
    return Phase17INamedHandlerBudgetReport(
        approved_entries=approved_named_handler_budget_entries(),
        named_handler_records=_named_handler_records(),
    )


def approved_named_handler_budget_entries() -> tuple[Phase17INamedHandlerBudgetEntry, ...]:
    return tuple(
        Phase17INamedHandlerBudgetEntry(
            execution_id=execution_id,
            approved_reason=Phase17INamedHandlerApprovalReason.PRE_WS14_EXISTING_RUNTIME_CONSUMER,
        )
        for execution_id in _APPROVED_PRE_WS14_NAMED_HANDLER_EXECUTION_IDS
    )


def source_package_identity_payload() -> dict[str, str]:
    report = phase17i_named_handler_budget_report()
    return {
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "upstream_identity": faction_execution_2026_27.SOURCE_PACKAGE_ID,
        "source_edition": SOURCE_EDITION,
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
        "source_payload_checksum_sha256": report.source_payload_checksum_sha256(),
        "upstream_payload_checksum_sha256": _upstream_payload_checksum_sha256(),
    }


def _named_handler_records() -> tuple[Phase17FExecutionRecord, ...]:
    return tuple(
        record
        for record in faction_execution_2026_27.phase17f_execution_package().execution_records
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    )


def _validate_budget_entries(
    values: tuple[Phase17INamedHandlerBudgetEntry, ...],
) -> tuple[Phase17INamedHandlerBudgetEntry, ...]:
    if type(values) is not tuple:
        raise Phase17INamedHandlerBudgetError("Phase17I budget entries must be a tuple.")
    entries: list[Phase17INamedHandlerBudgetEntry] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not Phase17INamedHandlerBudgetEntry:
            raise Phase17INamedHandlerBudgetError(
                "Phase17I budget entries must contain budget entries."
            )
        if value.execution_id in seen:
            raise Phase17INamedHandlerBudgetError("Phase17I budget execution IDs must be unique.")
        seen.add(value.execution_id)
        entries.append(value)
    return tuple(sorted(entries, key=lambda entry: entry.execution_id))


def _validate_named_handler_records(
    values: tuple[Phase17FExecutionRecord, ...],
) -> tuple[Phase17FExecutionRecord, ...]:
    if type(values) is not tuple:
        raise Phase17INamedHandlerBudgetError("Phase17I named handler records must be a tuple.")
    records: list[Phase17FExecutionRecord] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not Phase17FExecutionRecord:
            raise Phase17INamedHandlerBudgetError(
                "Phase17I named handler records must contain Phase17F records."
            )
        if value.execution_status is not Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER:
            raise Phase17INamedHandlerBudgetError(
                "Phase17I named handler budget can include only executable named-handler records."
            )
        if value.execution_id in seen:
            raise Phase17INamedHandlerBudgetError(
                "Phase17I named handler execution IDs must be unique."
            )
        seen.add(value.execution_id)
        records.append(value)
    return tuple(sorted(records, key=lambda record: record.execution_id))


def _approval_reason_from_token(token: object) -> Phase17INamedHandlerApprovalReason:
    if type(token) is Phase17INamedHandlerApprovalReason:
        return token
    if type(token) is not str:
        raise Phase17INamedHandlerBudgetError(
            "Phase17I named-handler approval reason token must be a string."
        )
    try:
        return Phase17INamedHandlerApprovalReason(token)
    except ValueError as exc:
        raise Phase17INamedHandlerBudgetError(
            f"Unsupported Phase17I named-handler approval reason: {token}."
        ) from exc


def _sha256_payload(payload: Phase17INamedHandlerBudgetReportPayload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _upstream_payload_checksum_sha256() -> str:
    return faction_execution_2026_27.source_package_identity_payload()[
        "source_payload_checksum_sha256"
    ]


_validate_identifier = IdentifierValidator(Phase17INamedHandlerBudgetError)
