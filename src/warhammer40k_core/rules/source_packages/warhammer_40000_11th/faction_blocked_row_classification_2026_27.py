from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    parameter_payload,
)
from warhammer40k_core.rules.rule_templates import (
    RESOURCE_MODIFIER_TEMPLATE_ID,
    TIMING_WINDOW_TEMPLATE_ID,
    rule_template_by_id,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)

EDITION_ID = "warhammer_40000_11th"
SOURCE_EDITION = "11th"
SOURCE_PACKAGE_ID = "gw-11e-phase17i-blocked-row-classification-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Phase 17I Blocked Row Classification"
SOURCE_VERSION = "2026-27"
SOURCE_DATE = "2026-07-02"
UPSTREAM_IDENTITY = faction_execution_2026_27.SOURCE_PACKAGE_ID
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17i-blocked-row-classification-v1"
WAHAPEDIA_SOURCE_VERSION = "1" + "0" + "th-edition-2026-06-14"
_SOURCE_JSON_DIR = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_BRIDGE_SOURCE_ROW_RE = re.compile(
    r"bridge-source-row:(?P<table>Enhancements|Stratagems):(?P<id>[^:]+)$"
)
_SOURCE_DESCRIPTION_COLUMN = "description"
_COMMAND_POINT_OPERATION_RE = re.compile(
    r"(?:\b(?:gain|add|refund|spend|lose|remove)\s+\d+\s*(?:CP|Command Points?)\b|"
    r"\b(?:increase|reduce)\s+(?:the\s+)?(?:CP\s+)?cost\b[^.]*?"
    r"\bby\s+\d+\s*CP\b|\bfor\s+\d+\s*CP\b)",
    re.IGNORECASE,
)
_FACTION_LINK_SLUG_OVERRIDES = {
    "emperor-s-children": "emperors-children",
    "t-au-empire": "tau-empire",
}


class Phase17IBlockedRowClassificationError(ValueError):
    """Raised when Phase 17I blocked-row classification data is invalid."""


class Phase17IClassificationSourceKind(StrEnum):
    WAHAPEDIA_BRIDGE_TEXT = "wahapedia_bridge_text"
    PHASE17F_METADATA_ONLY = "phase17f_metadata_only"


class Phase17IMissingCapabilityFamily(StrEnum):
    ARMY_RULE_STATE = "army_rule_state"
    ATTACK_SEQUENCE_RUNTIME = "attack_sequence_runtime"
    BATTLE_SHOCK_RUNTIME = "battle_shock_runtime"
    DAMAGE_SAVE_OR_FEEL_NO_PAIN_RUNTIME = "damage_save_or_feel_no_pain_runtime"
    DESTRUCTION_TRIGGER_RUNTIME = "destruction_trigger_runtime"
    DETACHMENT_RULE_STATE = "detachment_rule_state"
    DURATION_AND_EXPIRY_STATE = "duration_and_expiry_state"
    ENHANCEMENT_ASSIGNMENT_EFFECT = "enhancement_assignment_effect"
    FACTION_RESOURCE_LEDGER = "faction_resource_ledger"
    GENERIC_IR_EXECUTION_BINDING = "generic_ir_execution_binding"
    MOVEMENT_OR_CHARGE_RUNTIME = "movement_or_charge_runtime"
    MUSTERING_CONSTRAINT = "mustering_constraint"
    OBJECTIVE_CONTROL_OR_SCORING_RUNTIME = "objective_control_or_scoring_runtime"
    PLACEMENT_OR_RESERVES_RUNTIME = "placement_or_reserves_runtime"
    PLAYER_CHOICE_SELECTION = "player_choice_selection"
    SOURCE_TEXT_NOT_AVAILABLE = "source_text_not_available"
    STRATAGEM_ACTIVATION_AND_TARGETING = "stratagem_activation_and_targeting"
    STRATAGEM_COST_MODIFIER_RUNTIME = "stratagem_cost_modifier_runtime"
    STRATAGEM_EFFECT_EXECUTION = "stratagem_effect_execution"
    TRANSPORT_RUNTIME = "transport_runtime"
    UNREPRESENTED_RULE_LANGUAGE = "unrepresented_rule_language"


class Phase17IBlockedRowClassificationPayload(TypedDict):
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: str
    faction_id: str
    faction_name: str
    detachment_id: str | None
    detachment_name: str | None
    rule_name: str
    rule_id: str | None
    source_ids: list[str]
    classification_source_kind: str
    source_text_source_id: str | None
    existing_template_ids: list[str]
    existing_template_families: list[str]
    missing_capability_families: list[str]
    ir_clause_count: int
    unsupported_clause_count: int
    unsupported_diagnostic_reasons: list[str]


class Phase17IFrequencySummaryPayload(TypedDict):
    family: str
    row_count: int
    coverage_kind_counts: dict[str, int]
    example_execution_ids: list[str]


class Phase17IBlockedRowClassificationReportPayload(TypedDict):
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
    wahapedia_source_version: str
    wahapedia_artifact_hashes: dict[str, str]
    structured_blocked_count: int
    source_text_matched_count: int
    source_text_missing_count: int
    classification_rows: list[Phase17IBlockedRowClassificationPayload]
    existing_template_summaries: list[Phase17IFrequencySummaryPayload]
    missing_capability_summaries: list[Phase17IFrequencySummaryPayload]


@dataclass(frozen=True, slots=True)
class Phase17IBlockedRowClassification:
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: Phase17ECoverageKind
    faction_id: str
    faction_name: str
    rule_name: str
    source_ids: tuple[str, ...]
    classification_source_kind: Phase17IClassificationSourceKind
    existing_template_ids: tuple[str, ...]
    existing_template_families: tuple[str, ...]
    missing_capability_families: tuple[Phase17IMissingCapabilityFamily, ...]
    ir_clause_count: int
    unsupported_clause_count: int
    unsupported_diagnostic_reasons: tuple[str, ...]
    detachment_id: str | None = None
    detachment_name: str | None = None
    rule_id: str | None = None
    source_text_source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_id", _validate_identifier("execution_id", self.execution_id)
        )
        object.__setattr__(
            self,
            "coverage_descriptor_id",
            _validate_identifier("coverage_descriptor_id", self.coverage_descriptor_id),
        )
        object.__setattr__(self, "coverage_kind", _coverage_kind_from_token(self.coverage_kind))
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(self, "faction_name", _validate_text("faction_name", self.faction_name))
        object.__setattr__(self, "rule_name", _validate_text("rule_name", self.rule_name))
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )
        object.__setattr__(
            self,
            "classification_source_kind",
            _classification_source_kind_from_token(self.classification_source_kind),
        )
        object.__setattr__(
            self,
            "existing_template_ids",
            _validate_identifier_tuple(
                "existing_template_ids", self.existing_template_ids, allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "existing_template_families",
            _validate_identifier_tuple(
                "existing_template_families", self.existing_template_families, allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "missing_capability_families",
            _validate_missing_capability_tuple(self.missing_capability_families),
        )
        object.__setattr__(
            self,
            "ir_clause_count",
            _validate_non_negative_int("ir_clause_count", self.ir_clause_count),
        )
        object.__setattr__(
            self,
            "unsupported_clause_count",
            _validate_non_negative_int("unsupported_clause_count", self.unsupported_clause_count),
        )
        if self.unsupported_clause_count > self.ir_clause_count:
            raise Phase17IBlockedRowClassificationError(
                "unsupported_clause_count cannot exceed ir_clause_count."
            )
        object.__setattr__(
            self,
            "unsupported_diagnostic_reasons",
            _validate_identifier_tuple(
                "unsupported_diagnostic_reasons",
                self.unsupported_diagnostic_reasons,
                allow_empty=True,
            ),
        )
        if self.detachment_id is not None:
            object.__setattr__(
                self, "detachment_id", _validate_identifier("detachment_id", self.detachment_id)
            )
        if self.detachment_name is not None:
            object.__setattr__(
                self, "detachment_name", _validate_text("detachment_name", self.detachment_name)
            )
        if self.rule_id is not None:
            object.__setattr__(self, "rule_id", _validate_identifier("rule_id", self.rule_id))
        if self.source_text_source_id is not None:
            object.__setattr__(
                self,
                "source_text_source_id",
                _validate_identifier("source_text_source_id", self.source_text_source_id),
            )
        if (
            self.classification_source_kind
            is Phase17IClassificationSourceKind.WAHAPEDIA_BRIDGE_TEXT
            and self.source_text_source_id is None
        ):
            raise Phase17IBlockedRowClassificationError(
                "Wahapedia bridge classifications require source_text_source_id."
            )
        if (
            self.classification_source_kind
            is Phase17IClassificationSourceKind.PHASE17F_METADATA_ONLY
            and Phase17IMissingCapabilityFamily.SOURCE_TEXT_NOT_AVAILABLE
            not in self.missing_capability_families
        ):
            raise Phase17IBlockedRowClassificationError(
                "Metadata-only classifications require source_text_not_available."
            )

    def to_payload(self) -> Phase17IBlockedRowClassificationPayload:
        return {
            "execution_id": self.execution_id,
            "coverage_descriptor_id": self.coverage_descriptor_id,
            "coverage_kind": self.coverage_kind.value,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "rule_name": self.rule_name,
            "rule_id": self.rule_id,
            "source_ids": list(self.source_ids),
            "classification_source_kind": self.classification_source_kind.value,
            "source_text_source_id": self.source_text_source_id,
            "existing_template_ids": list(self.existing_template_ids),
            "existing_template_families": list(self.existing_template_families),
            "missing_capability_families": [
                family.value for family in self.missing_capability_families
            ],
            "ir_clause_count": self.ir_clause_count,
            "unsupported_clause_count": self.unsupported_clause_count,
            "unsupported_diagnostic_reasons": list(self.unsupported_diagnostic_reasons),
        }

    @classmethod
    def from_payload(cls, payload: Phase17IBlockedRowClassificationPayload) -> Self:
        return cls(
            execution_id=payload["execution_id"],
            coverage_descriptor_id=payload["coverage_descriptor_id"],
            coverage_kind=_coverage_kind_from_token(payload["coverage_kind"]),
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            rule_name=payload["rule_name"],
            rule_id=payload["rule_id"],
            source_ids=tuple(payload["source_ids"]),
            classification_source_kind=_classification_source_kind_from_token(
                payload["classification_source_kind"]
            ),
            source_text_source_id=payload["source_text_source_id"],
            existing_template_ids=tuple(payload["existing_template_ids"]),
            existing_template_families=tuple(payload["existing_template_families"]),
            missing_capability_families=tuple(
                _missing_capability_from_token(family)
                for family in payload["missing_capability_families"]
            ),
            ir_clause_count=payload["ir_clause_count"],
            unsupported_clause_count=payload["unsupported_clause_count"],
            unsupported_diagnostic_reasons=tuple(payload["unsupported_diagnostic_reasons"]),
        )


@dataclass(frozen=True, slots=True)
class Phase17IFrequencySummary:
    family: str
    row_count: int
    coverage_kind_counts: Mapping[str, int]
    example_execution_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", _validate_identifier("family", self.family))
        object.__setattr__(self, "row_count", _validate_positive_int("row_count", self.row_count))
        object.__setattr__(
            self,
            "coverage_kind_counts",
            _validate_count_mapping("coverage_kind_counts", self.coverage_kind_counts),
        )
        object.__setattr__(
            self,
            "example_execution_ids",
            _validate_identifier_tuple("example_execution_ids", self.example_execution_ids),
        )
        if sum(self.coverage_kind_counts.values()) != self.row_count:
            raise Phase17IBlockedRowClassificationError(
                "Frequency summary coverage_kind_counts must sum to row_count."
            )

    def to_payload(self) -> Phase17IFrequencySummaryPayload:
        return {
            "family": self.family,
            "row_count": self.row_count,
            "coverage_kind_counts": dict(sorted(self.coverage_kind_counts.items())),
            "example_execution_ids": list(self.example_execution_ids),
        }

    @classmethod
    def from_payload(cls, payload: Phase17IFrequencySummaryPayload) -> Self:
        return cls(
            family=payload["family"],
            row_count=payload["row_count"],
            coverage_kind_counts=payload["coverage_kind_counts"],
            example_execution_ids=tuple(payload["example_execution_ids"]),
        )


@dataclass(frozen=True, slots=True)
class Phase17IBlockedRowClassificationReport:
    classification_rows: tuple[Phase17IBlockedRowClassification, ...]
    wahapedia_artifact_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "classification_rows",
            _validate_classification_rows(self.classification_rows),
        )
        object.__setattr__(
            self,
            "wahapedia_artifact_hashes",
            _validate_artifact_hashes(self.wahapedia_artifact_hashes),
        )

    @property
    def structured_blocked_count(self) -> int:
        return len(self.classification_rows)

    @property
    def source_text_matched_count(self) -> int:
        return sum(
            1
            for row in self.classification_rows
            if row.classification_source_kind
            is Phase17IClassificationSourceKind.WAHAPEDIA_BRIDGE_TEXT
        )

    @property
    def source_text_missing_count(self) -> int:
        return self.structured_blocked_count - self.source_text_matched_count

    def existing_template_summaries(self) -> tuple[Phase17IFrequencySummary, ...]:
        return _frequency_summaries(
            rows=self.classification_rows,
            family_values=lambda row: row.existing_template_families,
        )

    def missing_capability_summaries(self) -> tuple[Phase17IFrequencySummary, ...]:
        return _frequency_summaries(
            rows=self.classification_rows,
            family_values=lambda row: tuple(
                family.value for family in row.missing_capability_families
            ),
        )

    def payload_without_checksum(self) -> Phase17IBlockedRowClassificationReportPayload:
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
            "wahapedia_source_version": WAHAPEDIA_SOURCE_VERSION,
            "wahapedia_artifact_hashes": dict(sorted(self.wahapedia_artifact_hashes.items())),
            "structured_blocked_count": self.structured_blocked_count,
            "source_text_matched_count": self.source_text_matched_count,
            "source_text_missing_count": self.source_text_missing_count,
            "classification_rows": [row.to_payload() for row in self.classification_rows],
            "existing_template_summaries": [
                summary.to_payload() for summary in self.existing_template_summaries()
            ],
            "missing_capability_summaries": [
                summary.to_payload() for summary in self.missing_capability_summaries()
            ],
        }

    def source_payload_checksum_sha256(self) -> str:
        return _sha256_payload(self.payload_without_checksum())

    def to_payload(self) -> Phase17IBlockedRowClassificationReportPayload:
        payload = self.payload_without_checksum()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: Phase17IBlockedRowClassificationReportPayload) -> Self:
        report = cls(
            classification_rows=tuple(
                Phase17IBlockedRowClassification.from_payload(row)
                for row in payload["classification_rows"]
            ),
            wahapedia_artifact_hashes=payload["wahapedia_artifact_hashes"],
        )
        if report.to_payload() != payload:
            raise Phase17IBlockedRowClassificationError(
                "Phase17I blocked-row classification payload is stale."
            )
        return report


@dataclass(frozen=True, slots=True)
class _SourceTextRecord:
    source_text_source_id: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class _SourceTextIndex:
    rows_by_table_and_id: Mapping[tuple[str, str], Mapping[str, object]]
    detachment_rows_by_faction_and_detachment_slug: Mapping[
        tuple[str, str], tuple[Mapping[str, object], ...]
    ]
    ability_rows_by_faction_and_name_slug: Mapping[
        tuple[str, str], tuple[Mapping[str, object], ...]
    ]
    artifact_hashes: Mapping[str, str]

    @classmethod
    def load(cls) -> Self:
        artifact_hashes: dict[str, str] = {}
        rows_by_table_and_id: dict[tuple[str, str], Mapping[str, object]] = {}
        artifact_rows_by_table: dict[str, tuple[Mapping[str, object], ...]] = {}
        for table in (
            "Factions",
            "Abilities",
            "Detachment_abilities",
            "Enhancements",
            "Stratagems",
        ):
            artifact = _load_source_json_artifact(table)
            artifact_hashes[table] = _artifact_hash(artifact, table=table)
            rows = _artifact_rows(artifact, table=table)
            artifact_rows_by_table[table] = rows
            for row in rows:
                rows_by_table_and_id[(table, _source_row_id(row, table=table))] = row

        faction_slug_by_bridge_id = _faction_slug_by_bridge_id(artifact_rows_by_table["Factions"])
        return cls(
            rows_by_table_and_id=rows_by_table_and_id,
            detachment_rows_by_faction_and_detachment_slug=(
                _detachment_ability_index(
                    artifact_rows_by_table["Detachment_abilities"],
                    faction_slug_by_bridge_id=faction_slug_by_bridge_id,
                )
            ),
            ability_rows_by_faction_and_name_slug=_ability_index(
                artifact_rows_by_table["Abilities"],
                faction_slug_by_bridge_id=faction_slug_by_bridge_id,
            ),
            artifact_hashes=artifact_hashes,
        )

    def source_text_for_record(self, record: Phase17FExecutionRecord) -> _SourceTextRecord | None:
        exact_text = self._exact_subrule_text_for_record(record)
        if exact_text is not None:
            return exact_text
        if (
            record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
            and record.detachment_name is not None
        ):
            rows = self.detachment_rows_by_faction_and_detachment_slug.get(
                (record.faction_id, _slug_for_text(record.detachment_name)),
                (),
            )
            if rows:
                return _source_text_record("Detachment_abilities", rows[0])
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE:
            rows = self.ability_rows_by_faction_and_name_slug.get(
                (record.faction_id, _slug_for_text(record.rule_name)),
                (),
            )
            if rows:
                return _source_text_record("Abilities", rows[0])
        return None

    def _exact_subrule_text_for_record(
        self, record: Phase17FExecutionRecord
    ) -> _SourceTextRecord | None:
        for source_id in record.source_ids:
            match = _BRIDGE_SOURCE_ROW_RE.search(source_id)
            if match is None:
                continue
            table = match.group("table")
            row = self.rows_by_table_and_id.get((table, match.group("id")))
            if row is not None:
                return _source_text_record(table, row)
        return None


@cache
def phase17i_blocked_row_classification_report() -> Phase17IBlockedRowClassificationReport:
    source_index = _SourceTextIndex.load()
    return Phase17IBlockedRowClassificationReport(
        classification_rows=tuple(
            _classification_row(record, source_index=source_index)
            for record in _structured_blocked_records()
        ),
        wahapedia_artifact_hashes=source_index.artifact_hashes,
    )


def classification_rows() -> tuple[Phase17IBlockedRowClassification, ...]:
    return phase17i_blocked_row_classification_report().classification_rows


def source_package_identity_payload() -> dict[str, str]:
    report = phase17i_blocked_row_classification_report()
    return {
        "edition_id": EDITION_ID,
        "source_edition": SOURCE_EDITION,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "upstream_identity": UPSTREAM_IDENTITY,
        "source_payload_checksum_sha256": report.source_payload_checksum_sha256(),
        "upstream_payload_checksum_sha256": _upstream_payload_checksum_sha256(),
        "structured_blocked_count": str(report.structured_blocked_count),
        "source_text_matched_count": str(report.source_text_matched_count),
        "source_text_missing_count": str(report.source_text_missing_count),
        "wahapedia_source_version": WAHAPEDIA_SOURCE_VERSION,
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def _classification_row(
    record: Phase17FExecutionRecord,
    *,
    source_index: _SourceTextIndex,
) -> Phase17IBlockedRowClassification:
    source_text = source_index.source_text_for_record(record)
    if source_text is None:
        existing_template_ids = _metadata_template_ids(record)
        return Phase17IBlockedRowClassification(
            execution_id=record.execution_id,
            coverage_descriptor_id=record.coverage_descriptor_id,
            coverage_kind=record.coverage_kind,
            faction_id=record.faction_id,
            faction_name=record.faction_name,
            detachment_id=record.detachment_id,
            detachment_name=record.detachment_name,
            rule_name=record.rule_name,
            rule_id=record.rule_id,
            source_ids=record.source_ids,
            classification_source_kind=Phase17IClassificationSourceKind.PHASE17F_METADATA_ONLY,
            source_text_source_id=None,
            existing_template_ids=existing_template_ids,
            existing_template_families=_template_families(existing_template_ids),
            missing_capability_families=_missing_capabilities_for_record(
                record=record,
                normalized_text=None,
                rule_ir=None,
                source_text_available=False,
            ),
            ir_clause_count=0,
            unsupported_clause_count=0,
            unsupported_diagnostic_reasons=(),
        )

    source = RuleSourceText.from_raw(
        source_id=f"{SOURCE_PACKAGE_ID}:{record.coverage_descriptor_id}:source-text",
        raw_text=source_text.raw_text,
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    existing_template_ids = tuple(
        sorted({clause.template_id for clause in rule_ir.clauses if clause.template_id is not None})
    )
    return Phase17IBlockedRowClassification(
        execution_id=record.execution_id,
        coverage_descriptor_id=record.coverage_descriptor_id,
        coverage_kind=record.coverage_kind,
        faction_id=record.faction_id,
        faction_name=record.faction_name,
        detachment_id=record.detachment_id,
        detachment_name=record.detachment_name,
        rule_name=record.rule_name,
        rule_id=record.rule_id,
        source_ids=record.source_ids,
        classification_source_kind=Phase17IClassificationSourceKind.WAHAPEDIA_BRIDGE_TEXT,
        source_text_source_id=source_text.source_text_source_id,
        existing_template_ids=existing_template_ids,
        existing_template_families=_template_families(existing_template_ids),
        missing_capability_families=_missing_capabilities_for_record(
            record=record,
            normalized_text=source.normalized_text,
            rule_ir=rule_ir,
            source_text_available=True,
        ),
        ir_clause_count=len(rule_ir.clauses),
        unsupported_clause_count=sum(
            1 for clause in rule_ir.clauses if clause.unsupported_reason is not None
        ),
        unsupported_diagnostic_reasons=tuple(
            sorted({diagnostic.reason.value for diagnostic in rule_ir.diagnostics})
        ),
    )


def _structured_blocked_records() -> tuple[Phase17FExecutionRecord, ...]:
    return tuple(
        record
        for record in faction_execution_2026_27.phase17f_execution_package().execution_records
        if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )


def _metadata_template_ids(record: Phase17FExecutionRecord) -> tuple[str, ...]:
    template_ids: set[str] = set()
    if record.timing_descriptor is not None:
        template_ids.add(TIMING_WINDOW_TEMPLATE_ID)
    if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_STRATAGEM:
        template_ids.add(RESOURCE_MODIFIER_TEMPLATE_ID)
    return tuple(sorted(template_ids))


def _template_families(template_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted({rule_template_by_id(template_id).family.value for template_id in template_ids})
    )


def _missing_capabilities_for_record(
    *,
    record: Phase17FExecutionRecord,
    normalized_text: str | None,
    rule_ir: RuleIR | None,
    source_text_available: bool,
) -> tuple[Phase17IMissingCapabilityFamily, ...]:
    families: set[Phase17IMissingCapabilityFamily] = {
        Phase17IMissingCapabilityFamily.GENERIC_IR_EXECUTION_BINDING,
    }
    if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE:
        families.add(Phase17IMissingCapabilityFamily.ARMY_RULE_STATE)
    elif record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE:
        families.add(Phase17IMissingCapabilityFamily.DETACHMENT_RULE_STATE)
    elif record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT:
        families.add(Phase17IMissingCapabilityFamily.ENHANCEMENT_ASSIGNMENT_EFFECT)
    elif record.coverage_kind is Phase17ECoverageKind.DETACHMENT_STRATAGEM:
        families.update(
            {
                Phase17IMissingCapabilityFamily.STRATAGEM_ACTIVATION_AND_TARGETING,
                Phase17IMissingCapabilityFamily.STRATAGEM_EFFECT_EXECUTION,
                Phase17IMissingCapabilityFamily.FACTION_RESOURCE_LEDGER,
            }
        )
    if not source_text_available:
        families.add(Phase17IMissingCapabilityFamily.SOURCE_TEXT_NOT_AVAILABLE)
        return _sorted_missing_capabilities(families)
    if normalized_text is None or rule_ir is None:
        raise Phase17IBlockedRowClassificationError(
            "Source-text classifications require normalized text and RuleIR."
        )
    if rule_ir.diagnostics:
        families.add(Phase17IMissingCapabilityFamily.UNREPRESENTED_RULE_LANGUAGE)
    text = normalized_text.lower()
    if _contains_any(
        text,
        ("select one", "select up to", "select two", "choose", "one of the following"),
    ):
        families.add(Phase17IMissingCapabilityFamily.PLAYER_CHOICE_SELECTION)
    if "battle-shock" in text or "battleshock" in text:
        families.add(Phase17IMissingCapabilityFamily.BATTLE_SHOCK_RUNTIME)
    if _contains_any(
        text,
        (
            "hit roll",
            "wound roll",
            "damage roll",
            "critical hit",
            "critical wound",
            "lethal hits",
            "sustained hits",
            "devastating wounds",
            "precision",
            "attack",
            "attacks",
        ),
    ):
        families.add(Phase17IMissingCapabilityFamily.ATTACK_SEQUENCE_RUNTIME)
    if _contains_any(
        text,
        (
            "saving throw",
            "armour save",
            "invulnerable save",
            "feel no pain",
            "mortal wound",
            "mortal wounds",
            "lost wounds",
            "regains",
            "wounds remaining",
            "damage characteristic",
        ),
    ):
        families.add(Phase17IMissingCapabilityFamily.DAMAGE_SAVE_OR_FEEL_NO_PAIN_RUNTIME)
    if _contains_any(text, ("destroyed", "destroys")):
        families.add(Phase17IMissingCapabilityFamily.DESTRUCTION_TRIGGER_RUNTIME)
    if _contains_any(
        text,
        (
            "normal move",
            "advance move",
            "fall back",
            "falls back",
            "charge move",
            "charge roll",
            "pile-in",
            "consolidation",
            "move ",
            "moves ",
            "moved ",
            "reposition",
            "redeploy",
        ),
    ):
        families.add(Phase17IMissingCapabilityFamily.MOVEMENT_OR_CHARGE_RUNTIME)
    if _contains_any(text, ("set up", "strategic reserves", "reserves", "deep strike", "redeploy")):
        families.add(Phase17IMissingCapabilityFamily.PLACEMENT_OR_RESERVES_RUNTIME)
    if _contains_any(text, ("transport", "embark", "embarked", "disembark")):
        families.add(Phase17IMissingCapabilityFamily.TRANSPORT_RUNTIME)
    if _contains_any(
        text,
        ("objective marker", "objective control", " oc ", "victory point", "victory points", " vp"),
    ):
        families.add(Phase17IMissingCapabilityFamily.OBJECTIVE_CONTROL_OR_SCORING_RUNTIME)
    if _contains_any(
        text,
        (
            "miracle dice",
            "pain token",
            "cabal point",
            "judgement token",
            "blood tithe",
            "waaagh",
        ),
    ) or (
        _contains_any(text, ("command point", "command points", " cp", "1cp", "2cp", "3cp"))
        and not _all_command_point_operations_are_structured(text=text, rule_ir=rule_ir)
    ):
        families.add(Phase17IMissingCapabilityFamily.FACTION_RESOURCE_LEDGER)
    if (
        "stratagem" in text
        and "cost" in text
        and _contains_any(
            text,
            ("command point", "command points", " cp", "1cp", "2cp", "3cp"),
        )
    ) and not _all_stratagem_cost_operations_are_structured(text=text, rule_ir=rule_ir):
        families.add(Phase17IMissingCapabilityFamily.STRATAGEM_COST_MODIFIER_RUNTIME)
    if _contains_any(text, ("when mustering", "army roster", "when you select", "must include")):
        families.add(Phase17IMissingCapabilityFamily.MUSTERING_CONSTRAINT)
    if _contains_any(text, ("until the end", "until your next", "until the start", "once per")):
        families.add(Phase17IMissingCapabilityFamily.DURATION_AND_EXPIRY_STATE)
    return _sorted_missing_capabilities(families)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _all_command_point_operations_are_structured(*, text: str, rule_ir: RuleIR) -> bool:
    operation_count = len(tuple(_COMMAND_POINT_OPERATION_RE.finditer(text)))
    if operation_count == 0:
        return False
    return operation_count == len(_structured_command_point_effects(rule_ir))


def _all_stratagem_cost_operations_are_structured(*, text: str, rule_ir: RuleIR) -> bool:
    operation_count = sum(
        1
        for match in _COMMAND_POINT_OPERATION_RE.finditer(text)
        if "cost" in match.group(0).lower() or match.group(0).lower().startswith("for ")
    )
    if operation_count == 0:
        return False
    structured_count = sum(
        1
        for effect in _structured_command_point_effects(rule_ir)
        if parameter_payload(effect.parameters).get("operation") == "modify_stratagem_cost"
    )
    return operation_count == structured_count


def _structured_command_point_effects(rule_ir: RuleIR) -> tuple[RuleEffectSpec, ...]:
    return tuple(
        effect
        for clause in rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.MODIFY_COMMAND_POINTS
    )


def _sorted_missing_capabilities(
    families: set[Phase17IMissingCapabilityFamily],
) -> tuple[Phase17IMissingCapabilityFamily, ...]:
    return tuple(sorted(families, key=lambda family: family.value))


def _frequency_summaries(
    *,
    rows: tuple[Phase17IBlockedRowClassification, ...],
    family_values: Callable[[Phase17IBlockedRowClassification], tuple[str, ...]],
) -> tuple[Phase17IFrequencySummary, ...]:
    grouped: dict[str, list[Phase17IBlockedRowClassification]] = {}
    for row in rows:
        for family in family_values(row):
            grouped.setdefault(family, []).append(row)
    summaries: list[Phase17IFrequencySummary] = []
    for family, family_rows in grouped.items():
        coverage_counts = Counter(row.coverage_kind.value for row in family_rows)
        summaries.append(
            Phase17IFrequencySummary(
                family=family,
                row_count=len(family_rows),
                coverage_kind_counts=dict(sorted(coverage_counts.items())),
                example_execution_ids=tuple(sorted(row.execution_id for row in family_rows)[:5]),
            )
        )
    return tuple(sorted(summaries, key=lambda summary: (-summary.row_count, summary.family)))


def _load_source_json_artifact(table: str) -> Mapping[str, object]:
    path = _SOURCE_JSON_DIR / f"{table}.json"
    if not path.is_file():
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text artifact is missing: {path}."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text artifact {table} must be a JSON object."
        )
    return cast(Mapping[str, object], payload)


def _artifact_rows(
    artifact: Mapping[str, object], *, table: str
) -> tuple[Mapping[str, object], ...]:
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text artifact {table} rows must be a list."
        )
    validated: list[Mapping[str, object]] = []
    row_values = cast(list[object], rows)
    for row in row_values:
        if not isinstance(row, dict):
            raise Phase17IBlockedRowClassificationError(
                f"Phase17I source text artifact {table} rows must contain objects."
            )
        validated.append(cast(Mapping[str, object], row))
    return tuple(validated)


def _artifact_hash(artifact: Mapping[str, object], *, table: str) -> str:
    value = artifact.get("artifact_hash")
    if type(value) is not str:
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text artifact {table} lacks artifact_hash."
        )
    return _validate_sha256(f"wahapedia_artifact_hashes[{table}]", value)


def _source_row_id(row: Mapping[str, object], *, table: str) -> str:
    value = row.get("source_row_id")
    if type(value) is not str:
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text row in {table} lacks source_row_id."
        )
    return _validate_identifier("source_row_id", value)


def _source_text_record(table: str, row: Mapping[str, object]) -> _SourceTextRecord:
    fields = _row_fields(row, table=table)
    raw_text = _required_field_text(fields, field_name=_SOURCE_DESCRIPTION_COLUMN, table=table)
    source_row_id = _source_row_id(row, table=table)
    return _SourceTextRecord(
        source_text_source_id=(
            f"wahapedia:{WAHAPEDIA_SOURCE_VERSION}:{table}:{source_row_id}:description"
        ),
        raw_text=raw_text,
    )


def _row_fields(row: Mapping[str, object], *, table: str) -> Mapping[str, str]:
    fields = row.get("fields")
    if not isinstance(fields, dict):
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text row in {table} lacks fields."
        )
    validated: dict[str, str] = {}
    field_values = cast(dict[object, object], fields)
    for key, value in field_values.items():
        if type(key) is not str or type(value) is not str:
            raise Phase17IBlockedRowClassificationError(
                f"Phase17I source text row in {table} fields must be strings."
            )
        validated[key] = value
    return validated


def _required_field_text(fields: Mapping[str, str], *, field_name: str, table: str) -> str:
    value = fields.get(field_name)
    if value is None:
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I source text row in {table} lacks {field_name}."
        )
    return _validate_text(field_name, value)


def _faction_slug_by_bridge_id(
    faction_rows: tuple[Mapping[str, object], ...],
) -> Mapping[str, str]:
    slugs: dict[str, str] = {}
    for row in faction_rows:
        fields = _row_fields(row, table="Factions")
        bridge_id = _required_field_text(fields, field_name="id", table="Factions")
        link = _required_field_text(fields, field_name="link", table="Factions")
        raw_slug = link.rstrip("/").rsplit("/", maxsplit=1)[-1]
        slugs[bridge_id] = _FACTION_LINK_SLUG_OVERRIDES.get(raw_slug, raw_slug)
    return slugs


def _detachment_ability_index(
    rows: tuple[Mapping[str, object], ...],
    *,
    faction_slug_by_bridge_id: Mapping[str, str],
) -> Mapping[tuple[str, str], tuple[Mapping[str, object], ...]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        fields = _row_fields(row, table="Detachment_abilities")
        faction_slug = faction_slug_by_bridge_id.get(fields.get("faction_id", ""))
        detachment_name = fields.get("detachment")
        if faction_slug is None or detachment_name is None or not detachment_name.strip():
            continue
        grouped.setdefault((faction_slug, _slug_for_text(detachment_name)), []).append(row)
    return {
        key: tuple(sorted(value, key=lambda row: _source_row_id(row, table="Detachment_abilities")))
        for key, value in grouped.items()
    }


def _ability_index(
    rows: tuple[Mapping[str, object], ...],
    *,
    faction_slug_by_bridge_id: Mapping[str, str],
) -> Mapping[tuple[str, str], tuple[Mapping[str, object], ...]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        fields = _row_fields(row, table="Abilities")
        faction_slug = faction_slug_by_bridge_id.get(fields.get("faction_id", ""))
        name = fields.get("name")
        if faction_slug is None or name is None or not name.strip():
            continue
        grouped.setdefault((faction_slug, _slug_for_text(name)), []).append(row)
    return {
        key: tuple(sorted(value, key=lambda row: _source_row_id(row, table="Abilities")))
        for key, value in grouped.items()
    }


def _slug_for_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _validate_classification_rows(
    rows: tuple[Phase17IBlockedRowClassification, ...],
) -> tuple[Phase17IBlockedRowClassification, ...]:
    if type(rows) is not tuple:
        raise Phase17IBlockedRowClassificationError("Phase17I classification_rows must be a tuple.")
    expected_by_execution_id = {
        record.execution_id: record for record in _structured_blocked_records()
    }
    seen: set[str] = set()
    validated: list[Phase17IBlockedRowClassification] = []
    for row in rows:
        if type(row) is not Phase17IBlockedRowClassification:
            raise Phase17IBlockedRowClassificationError(
                "Phase17I classification_rows must contain classification rows."
            )
        expected = expected_by_execution_id.get(row.execution_id)
        if expected is None:
            raise Phase17IBlockedRowClassificationError(
                "Phase17I classification row references unknown structured-blocked execution row."
            )
        if row.execution_id in seen:
            raise Phase17IBlockedRowClassificationError(
                "Phase17I classification row execution IDs must be unique."
            )
        _validate_row_matches_execution_record(row=row, record=expected)
        seen.add(row.execution_id)
        validated.append(row)
    if seen != set(expected_by_execution_id):
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification rows must cover every structured-blocked execution row."
        )
    return tuple(sorted(validated, key=lambda row: row.execution_id))


def _validate_row_matches_execution_record(
    *,
    row: Phase17IBlockedRowClassification,
    record: Phase17FExecutionRecord,
) -> None:
    if row.coverage_descriptor_id != record.coverage_descriptor_id:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched coverage_descriptor_id."
        )
    if row.coverage_kind is not record.coverage_kind:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched coverage_kind."
        )
    if row.faction_id != record.faction_id:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched faction_id."
        )
    if row.faction_name != record.faction_name:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched faction_name."
        )
    if row.detachment_id != record.detachment_id:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched detachment_id."
        )
    if row.detachment_name != record.detachment_name:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched detachment_name."
        )
    if row.rule_name != record.rule_name:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched rule_name."
        )
    if row.rule_id != record.rule_id:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched rule_id."
        )
    if row.source_ids != record.source_ids:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification row has mismatched source_ids."
        )


def _validate_artifact_hashes(values: object) -> Mapping[str, str]:
    if not isinstance(values, Mapping):
        raise Phase17IBlockedRowClassificationError(
            "Phase17I wahapedia_artifact_hashes must be a mapping."
        )
    validated: dict[str, str] = {}
    for key, value in cast(Mapping[object, object], values).items():
        table = _validate_identifier("artifact table", key)
        validated[table] = _validate_sha256("artifact hash", value)
    required_tables = {
        "Factions",
        "Abilities",
        "Detachment_abilities",
        "Enhancements",
        "Stratagems",
    }
    if set(validated) != required_tables:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I wahapedia_artifact_hashes must cover the required source artifacts."
        )
    return dict(sorted(validated.items()))


def _coverage_kind_from_token(token: object) -> Phase17ECoverageKind:
    if type(token) is Phase17ECoverageKind:
        return token
    if type(token) is not str:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I coverage kind token must be a string."
        )
    try:
        return Phase17ECoverageKind(token)
    except ValueError as exc:
        raise Phase17IBlockedRowClassificationError(
            f"Unsupported Phase17I coverage kind: {token}."
        ) from exc


def _classification_source_kind_from_token(token: object) -> Phase17IClassificationSourceKind:
    if type(token) is Phase17IClassificationSourceKind:
        return token
    if type(token) is not str:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I classification source kind token must be a string."
        )
    try:
        return Phase17IClassificationSourceKind(token)
    except ValueError as exc:
        raise Phase17IBlockedRowClassificationError(
            f"Unsupported Phase17I classification source kind: {token}."
        ) from exc


def _missing_capability_from_token(token: object) -> Phase17IMissingCapabilityFamily:
    if type(token) is Phase17IMissingCapabilityFamily:
        return token
    if type(token) is not str:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I missing capability token must be a string."
        )
    try:
        return Phase17IMissingCapabilityFamily(token)
    except ValueError as exc:
        raise Phase17IBlockedRowClassificationError(
            f"Unsupported Phase17I missing capability: {token}."
        ) from exc


def _validate_missing_capability_tuple(
    values: tuple[Phase17IMissingCapabilityFamily, ...],
) -> tuple[Phase17IMissingCapabilityFamily, ...]:
    if type(values) is not tuple:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I missing_capability_families must be a tuple."
        )
    if not values:
        raise Phase17IBlockedRowClassificationError(
            "Phase17I missing_capability_families must not be empty."
        )
    return tuple(
        sorted(
            {_missing_capability_from_token(value) for value in values},
            key=lambda value: value.value,
        )
    )


def _validate_count_mapping(field_name: str, values: object) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be a mapping.")
    validated: dict[str, int] = {}
    for key, value in cast(Mapping[object, object], values).items():
        validated[_validate_identifier(f"{field_name} key", key)] = _validate_positive_int(
            f"{field_name} value", value
        )
    return dict(sorted(validated.items()))


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be a tuple.")
    if not values and not allow_empty:
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I {field_name} must be a SHA-256 digest."
        )
    if any(character not in "0123456789abcdef" for character in digest):
        raise Phase17IBlockedRowClassificationError(
            f"Phase17I {field_name} must be a lowercase SHA-256 digest."
        )
    return digest


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be an integer.")
    if value < 0:
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be non-negative.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    integer = _validate_non_negative_int(field_name, value)
    if integer == 0:
        raise Phase17IBlockedRowClassificationError(f"Phase17I {field_name} must be positive.")
    return integer


def _upstream_payload_checksum_sha256() -> str:
    return faction_execution_2026_27.source_package_identity_payload()[
        "source_payload_checksum_sha256"
    ]


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_validate_identifier = IdentifierValidator(Phase17IBlockedRowClassificationError)


def _validate_text(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)
