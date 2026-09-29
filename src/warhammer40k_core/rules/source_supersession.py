"""Retained source observations that no longer control a runtime rule row."""

from __future__ import annotations

import hashlib
from typing import Final

import msgspec

from warhammer40k_core.rules.source_evidence import LoadSupportStatus, SemanticExecutionStatus

SUPERSESSION_KINDS: Final = frozenset(
    {
        "label_only_transcription",
        "incomplete_excerpt",
        "mislocated_locator",
        "retired_consumer",
    }
)


class SourceSupersessionError(ValueError):
    """Raised when a superseded source observation is incomplete or still certified."""


class SupersededSourceRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    record_id: str
    source_id: str
    kind: str
    prior_text: str
    prior_sha256: str
    successor: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    reason: str

    def validate(self) -> None:
        if (
            not self.record_id
            or self.record_id != self.record_id.strip()
            or not self.source_id
            or self.source_id != self.source_id.strip()
            or not self.successor
            or self.successor != self.successor.strip()
            or not self.prior_text
            or not self.reason
            or self.reason != self.reason.strip()
        ):
            raise SourceSupersessionError(
                "A superseded source record requires its identity, prior text, successor, "
                "and reason."
            )
        if self.kind not in SUPERSESSION_KINDS:
            raise SourceSupersessionError("A superseded source record kind is unsupported.")
        if self.load_support_status != "loaded":
            raise SourceSupersessionError(
                "A superseded source observation stays loaded as provenance."
            )
        if self.semantic_execution_status != "not_certified":
            raise SourceSupersessionError(
                "A superseded source observation cannot claim semantic execution."
            )
        if hashlib.sha256(self.prior_text.encode()).hexdigest() != self.prior_sha256:
            raise SourceSupersessionError("A superseded source transcription hash drifted.")


def validate_superseded_source_records(
    records: tuple[SupersededSourceRecord, ...],
) -> None:
    seen: set[str] = set()
    for record in records:
        if record.record_id in seen:
            raise SourceSupersessionError("Superseded source record IDs must be unique.")
        seen.add(record.record_id)
        record.validate()


__all__ = (
    "SUPERSESSION_KINDS",
    "SourceSupersessionError",
    "SupersededSourceRecord",
    "validate_superseded_source_records",
)
