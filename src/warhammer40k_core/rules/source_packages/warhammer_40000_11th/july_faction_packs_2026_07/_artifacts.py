from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence, Set
from typing import Final, cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.text_normalization import (
    TextNormalizationError,
    normalize_rule_text,
)

JULY_FACTION_PACK_PACKAGE_SCHEMA: Final = "core-v2-july-faction-pack-staging-package-v1"
JULY_FACTION_PACK_LEDGER_SCHEMA: Final = "core-v2-july-faction-pack-delta-ledger-v1"
JULY_DETACHMENT_SCHEMA: Final = "core-v2-july-faction-pack-detachments-v1"
JULY_SUBRULE_SCHEMA: Final = "core-v2-july-faction-pack-subrules-v1"
JULY_PHASE17E_SCHEMA: Final = "core-v2-july-faction-pack-phase17e-coverage-v1"
JULY_PHASE17F_SCHEMA: Final = "core-v2-july-faction-pack-phase17f-execution-v1"
JULY_RUNTIME_SCAFFOLD_SCHEMA: Final = "core-v2-july-faction-pack-runtime-scaffolds-v1"
JULY_DATASHEET_SCHEMA: Final = "core-v2-july-faction-pack-datasheets-v1"
JULY_DATASHEET_PREVIEW_SCHEMA: Final = "core-v2-july-faction-pack-datasheet-preview-v1"
JULY_FACTION_PACK_SOURCE_PACKAGE_ID: Final = "gw-11e-staged-faction-packs-2026-07"
JULY_FACTION_PACK_SOURCE_DATE: Final = "2026-07-22"
JULY_FACTION_PACK_ACTIVATION_STATUS: Final = "staged"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[-:._][a-z0-9]+)*$")
_ARTIFACT_PATH_RE = re.compile(r"^artifacts/[a-z0-9][a-z0-9._/-]*\.json$")
_SUCCESSOR_PACKAGE_SUFFIX = "-faction-pack-2026-07"
_PREDECESSOR_PACKAGE_SUFFIX = "-faction-pack-2026-06"
_APPROVED_DISPOSITIONS = frozenset(
    {
        "rules_updates_already_applied",
        "in_scope_source_only",
        "in_scope_runtime_affected",
        "excluded_imperial_armour",
        "excluded_legends",
    }
)
_APPROVED_REFERENCE_KINDS = frozenset(
    {
        "phase17e_descriptor_id",
        "source_row_id",
        "datasheet_id",
        "datasheet_ability_id",
    }
)
_APPROVED_RULE_KINDS = frozenset(
    {
        "detachment_rule",
        "enhancement",
        "stratagem",
    }
)
_APPROVED_COVERAGE_KINDS = frozenset(
    {
        "detachment",
        "detachment_rule",
        "detachment_enhancement",
        "detachment_stratagem",
    }
)
_BLOCKED_EXECUTION_STATUS = "blocked_structured_semantics_required"
_BLOCK_REASON = "structured_rule_semantics_required"
_LOAD_SUPPORT_STATUS = "loaded"
_SEMANTIC_EXECUTION_STATUS = "blocked"
_APPROVED_DATASHEET_OVERLAY_OPERATIONS = frozenset(
    {
        "add_keyword",
        "remove_ability",
        "replace_ability_text",
        "remove_from_current_inventory",
    }
)
_EXPECTED_FACTION_IDS = frozenset(
    {
        "adepta-sororitas",
        "adeptus-custodes",
        "adeptus-mechanicus",
        "aeldari",
        "astra-militarum",
        "black-templars",
        "blood-angels",
        "chaos-daemons",
        "chaos-knights",
        "chaos-space-marines",
        "dark-angels",
        "death-guard",
        "drukhari",
        "emperors-children",
        "genestealer-cults",
        "grey-knights",
        "imperial-agents",
        "imperial-knights",
        "leagues-of-votann",
        "necrons",
        "orks",
        "space-marines",
        "space-wolves",
        "tau-empire",
        "thousand-sons",
        "tyranids",
        "world-eaters",
    }
)


class JulyFactionPackStagingError(ValueError):
    """Raised when staged July faction-pack data violates CORE V2 invariants."""


class StagedPredecessorArtifact(msgspec.Struct, frozen=True):
    source_package_id: str
    source_date: str
    source_payload_checksum_sha256: str

    def validate(self) -> None:
        _validate_identifier("predecessor source_package_id", self.source_package_id)
        if self.source_date != "2026-06-11" and not (
            self.source_package_id == "gw-11e-phase17e-exact-faction-subrules-2026-27"
            and self.source_date == "2026-06-21"
        ):
            raise JulyFactionPackStagingError(
                "Staged predecessor source_date does not match the active June package."
            )
        _validate_sha256(
            "predecessor source_payload_checksum_sha256",
            self.source_payload_checksum_sha256,
        )


class StagedArtifactReference(msgspec.Struct, frozen=True):
    artifact_id: str
    artifact_path: str
    artifact_sha256: str

    def validate(self) -> None:
        _validate_identifier("staged artifact_id", self.artifact_id)
        _validate_artifact_path(self.artifact_path)
        _validate_sha256("staged artifact_sha256", self.artifact_sha256)


class StablePredecessorReference(msgspec.Struct, frozen=True):
    reference_kind: str
    reference_id: str

    def validate(self) -> None:
        if self.reference_kind not in _APPROVED_REFERENCE_KINDS:
            raise JulyFactionPackStagingError(
                "July faction-pack predecessor reference kind is unsupported."
            )
        _validate_identifier("predecessor reference_id", self.reference_id)


class JulyReviewItemArtifact(msgspec.Struct, frozen=True):
    item_id: str
    name: str
    disposition: str
    predecessor_references: list[StablePredecessorReference]

    def validate(self) -> None:
        _validate_identifier("review item_id", self.item_id)
        _validate_text("review item name", self.name)
        if self.disposition not in _APPROVED_DISPOSITIONS:
            raise JulyFactionPackStagingError(
                "July faction-pack review disposition is unsupported."
            )
        seen_references: set[tuple[str, str]] = set()
        for reference in self.predecessor_references:
            reference.validate()
            key = (reference.reference_kind, reference.reference_id)
            if key in seen_references:
                raise JulyFactionPackStagingError(
                    "July faction-pack review item repeats a predecessor reference."
                )
            seen_references.add(key)
        if self.disposition == "in_scope_runtime_affected" and not self.predecessor_references:
            raise JulyFactionPackStagingError(
                "Runtime-affected July review items require a stable predecessor reference."
            )


class JulyPackReviewArtifact(msgspec.Struct, frozen=True):
    faction_id: str
    faction_name: str
    successor_package_id: str
    successor_pdf_sha256: str
    successor_pdf_path: str
    predecessor_package_id: str
    predecessor_pdf_sha256: str
    review_items: list[JulyReviewItemArtifact]

    def validate(self) -> None:
        _validate_identifier("review faction_id", self.faction_id)
        _validate_text("review faction_name", self.faction_name)
        _validate_identifier("successor_package_id", self.successor_package_id)
        _validate_identifier("predecessor_package_id", self.predecessor_package_id)
        _validate_sha256("successor_pdf_sha256", self.successor_pdf_sha256)
        _validate_sha256("predecessor_pdf_sha256", self.predecessor_pdf_sha256)
        _validate_pdf_path(self.successor_pdf_path)
        expected_successor_id = f"gw-11e-{self.faction_id}{_SUCCESSOR_PACKAGE_SUFFIX}"
        expected_predecessor_id = f"gw-11e-{self.faction_id}{_PREDECESSOR_PACKAGE_SUFFIX}"
        if self.successor_package_id != expected_successor_id:
            raise JulyFactionPackStagingError(
                "July faction-pack successor package does not match faction_id."
            )
        if self.predecessor_package_id != expected_predecessor_id:
            raise JulyFactionPackStagingError(
                "July faction-pack predecessor package does not match faction_id."
            )
        if not self.review_items:
            raise JulyFactionPackStagingError(
                "Every pending July faction pack requires one or more review items."
            )
        seen_item_ids: set[str] = set()
        for item in self.review_items:
            item.validate()
            if item.item_id in seen_item_ids:
                raise JulyFactionPackStagingError(
                    "July faction-pack review item IDs must be unique within a pack."
                )
            seen_item_ids.add(item.item_id)


class JulyDeltaLedgerArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    ledger_id: str
    source_package_id: str
    source_date: str
    pack_reviews: list[JulyPackReviewArtifact]

    def validate(self) -> None:
        if self.artifact_schema != JULY_FACTION_PACK_LEDGER_SCHEMA:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger artifact schema is unsupported."
            )
        _validate_identifier("ledger_id", self.ledger_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger source package identity is stale."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger source date is stale."
            )
        faction_ids: set[str] = set()
        successor_package_ids: set[str] = set()
        predecessor_package_ids: set[str] = set()
        for review in self.pack_reviews:
            review.validate()
            if review.faction_id in faction_ids:
                raise JulyFactionPackStagingError(
                    "Every pending July faction pack must have exactly one review row."
                )
            if review.successor_package_id in successor_package_ids:
                raise JulyFactionPackStagingError("July successor package IDs must be unique.")
            if review.predecessor_package_id in predecessor_package_ids:
                raise JulyFactionPackStagingError("June predecessor package IDs must be unique.")
            faction_ids.add(review.faction_id)
            successor_package_ids.add(review.successor_package_id)
            predecessor_package_ids.add(review.predecessor_package_id)
        if frozenset(faction_ids) != _EXPECTED_FACTION_IDS:
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger must cover the exact 27-faction set."
            )


class JulyDetachmentRowArtifact(msgspec.Struct, frozen=True):
    source_row_id: str
    predecessor_source_row_id: str | None
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    source_pdf_package_id: str
    source_pdf_page: int
    tags: list[str]
    removed_tags: list[str]
    component_source_row_ids: list[str]
    load_support_status: str
    semantic_execution_status: str
    block_reason: str

    def validate(self) -> None:
        _validate_staged_row_id(self.source_row_id)
        if self.predecessor_source_row_id is not None:
            _validate_identifier(
                "detachment predecessor_source_row_id", self.predecessor_source_row_id
            )
        _validate_identifier("detachment faction_id", self.faction_id)
        _validate_text("detachment faction_name", self.faction_name)
        _validate_identifier("detachment detachment_id", self.detachment_id)
        _validate_text("detachment detachment_name", self.detachment_name)
        _validate_successor_package_id(self.faction_id, self.source_pdf_package_id)
        _validate_page(self.source_pdf_page)
        _validate_unique_identifiers("detachment tags", self.tags)
        _validate_unique_identifiers("detachment removed_tags", self.removed_tags)
        if set(self.tags).intersection(self.removed_tags):
            raise JulyFactionPackStagingError(
                "July detachment tags cannot also be recorded as removed."
            )
        _validate_unique_identifiers(
            "detachment component_source_row_ids",
            self.component_source_row_ids,
        )
        _validate_blocked_support(
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            block_reason=self.block_reason,
        )


class JulyDetachmentArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    predecessor_package_id: str
    predecessor_package_sha256: str
    rows: list[JulyDetachmentRowArtifact]

    def validate(self) -> None:
        _validate_artifact_header(
            actual_schema=self.artifact_schema,
            expected_schema=JULY_DETACHMENT_SCHEMA,
            artifact_id=self.artifact_id,
            source_package_id=self.source_package_id,
            source_date=self.source_date,
            predecessor_package_id=self.predecessor_package_id,
            predecessor_package_sha256=self.predecessor_package_sha256,
            expected_predecessor_id="gw-11e-faction-detachments-2026-27",
        )
        _validate_unique_rows(self.rows)
        for row in self.rows:
            row.validate()


class JulySubruleRowArtifact(msgspec.Struct, frozen=True):
    source_row_id: str
    predecessor_source_row_id: str | None
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    rule_kind: str
    rule_id: str
    rule_name: str
    raw_rule_text: str
    normalized_rule_text: str
    timing_descriptor: str | None
    rule_category: str | None
    source_pdf_package_id: str
    source_pdf_page: int
    load_support_status: str
    semantic_execution_status: str
    block_reason: str

    def validate(self) -> None:
        _validate_staged_row_id(self.source_row_id)
        if self.predecessor_source_row_id is not None:
            _validate_identifier(
                "subrule predecessor_source_row_id", self.predecessor_source_row_id
            )
        _validate_identifier("subrule faction_id", self.faction_id)
        _validate_text("subrule faction_name", self.faction_name)
        _validate_identifier("subrule detachment_id", self.detachment_id)
        _validate_text("subrule detachment_name", self.detachment_name)
        if self.rule_kind not in _APPROVED_RULE_KINDS:
            raise JulyFactionPackStagingError("July subrule kind is unsupported.")
        _validate_identifier("subrule rule_id", self.rule_id)
        _validate_text("subrule rule_name", self.rule_name)
        raw_rule_text = _validate_text("subrule raw_rule_text", self.raw_rule_text)
        normalized_rule_text = _validate_text(
            "subrule normalized_rule_text",
            self.normalized_rule_text,
        )
        try:
            expected_normalized = normalize_rule_text(raw_rule_text)
        except TextNormalizationError as exc:
            raise JulyFactionPackStagingError(
                "July subrule raw text cannot be normalized."
            ) from exc
        if normalized_rule_text != expected_normalized:
            raise JulyFactionPackStagingError(
                "July subrule normalized text must be produced at the source boundary."
            )
        if self.timing_descriptor is not None:
            _validate_text("subrule timing_descriptor", self.timing_descriptor)
        if self.rule_category is not None:
            _validate_text("subrule rule_category", self.rule_category)
        _validate_successor_package_id(self.faction_id, self.source_pdf_package_id)
        _validate_page(self.source_pdf_page)
        _validate_blocked_support(
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            block_reason=self.block_reason,
        )


class JulySubruleArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    predecessor_package_id: str
    predecessor_package_sha256: str
    rows: list[JulySubruleRowArtifact]

    def validate(self) -> None:
        _validate_artifact_header(
            actual_schema=self.artifact_schema,
            expected_schema=JULY_SUBRULE_SCHEMA,
            artifact_id=self.artifact_id,
            source_package_id=self.source_package_id,
            source_date=self.source_date,
            predecessor_package_id=self.predecessor_package_id,
            predecessor_package_sha256=self.predecessor_package_sha256,
            expected_predecessor_id="gw-11e-phase17e-exact-faction-subrules-2026-27",
        )
        _validate_unique_rows(self.rows)
        for row in self.rows:
            row.validate()


class JulyPhase17ECoverageRowArtifact(msgspec.Struct, array_like=True, frozen=True):
    descriptor_id: str
    source_row_id: str
    coverage_kind: str
    coverage_status: str
    unsupported_reason: str
    runtime_consumer_ids: list[str]

    def validate(self) -> None:
        _validate_staged_descriptor_id(self.descriptor_id)
        _validate_staged_row_id(self.source_row_id)
        if self.coverage_kind not in _APPROVED_COVERAGE_KINDS:
            raise JulyFactionPackStagingError("July Phase 17E coverage kind is unsupported.")
        if self.coverage_status != "unsupported":
            raise JulyFactionPackStagingError("July PR 2 Phase 17E rows must remain unsupported.")
        if self.unsupported_reason != _BLOCK_REASON:
            raise JulyFactionPackStagingError(
                "July PR 2 Phase 17E rows require the structured-semantics reason."
            )
        if self.runtime_consumer_ids:
            raise JulyFactionPackStagingError(
                "July PR 2 Phase 17E source-only rows cannot declare runtime consumers."
            )


class JulyPhase17ECoverageArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    predecessor_package_id: str
    predecessor_package_sha256: str
    rows: list[JulyPhase17ECoverageRowArtifact]

    def validate(self) -> None:
        _validate_artifact_header(
            actual_schema=self.artifact_schema,
            expected_schema=JULY_PHASE17E_SCHEMA,
            artifact_id=self.artifact_id,
            source_package_id=self.source_package_id,
            source_date=self.source_date,
            predecessor_package_id=self.predecessor_package_id,
            predecessor_package_sha256=self.predecessor_package_sha256,
            expected_predecessor_id="gw-11e-phase17e-faction-coverage-2026-27",
        )
        _validate_unique_rows(self.rows, id_field="descriptor_id")
        for row in self.rows:
            row.validate()


class JulyPhase17FExecutionRowArtifact(msgspec.Struct, array_like=True, frozen=True):
    execution_id: str
    coverage_descriptor_id: str
    source_row_id: str
    execution_status: str
    block_reason: str
    runtime_consumer_ids: list[str]
    handler_id: str | None

    def validate(self) -> None:
        _validate_staged_execution_id(self.execution_id)
        _validate_staged_descriptor_id(self.coverage_descriptor_id)
        _validate_staged_row_id(self.source_row_id)
        if self.execution_status != _BLOCKED_EXECUTION_STATUS:
            raise JulyFactionPackStagingError(
                "July PR 2 Phase 17F rows must remain explicitly blocked."
            )
        if self.block_reason != _BLOCK_REASON:
            raise JulyFactionPackStagingError(
                "July PR 2 Phase 17F rows require the structured-semantics reason."
            )
        if self.runtime_consumer_ids or self.handler_id is not None:
            raise JulyFactionPackStagingError(
                "July PR 2 Phase 17F source-only rows cannot declare runtime consumers or handlers."
            )


class JulyPhase17FExecutionArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    predecessor_package_id: str
    predecessor_package_sha256: str
    rows: list[JulyPhase17FExecutionRowArtifact]

    def validate(self) -> None:
        _validate_artifact_header(
            actual_schema=self.artifact_schema,
            expected_schema=JULY_PHASE17F_SCHEMA,
            artifact_id=self.artifact_id,
            source_package_id=self.source_package_id,
            source_date=self.source_date,
            predecessor_package_id=self.predecessor_package_id,
            predecessor_package_sha256=self.predecessor_package_sha256,
            expected_predecessor_id="gw-11e-phase17f-faction-execution-2026-27",
        )
        _validate_unique_rows(self.rows, id_field="execution_id")
        for row in self.rows:
            row.validate()


class JulyRuntimeScaffoldRowArtifact(msgspec.Struct, array_like=True, frozen=True):
    scaffold_id: str
    source_row_id: str
    coverage_descriptor_id: str
    execution_id: str
    load_support_status: str
    semantic_execution_status: str
    block_reason: str
    named_handler_id: str | None

    def validate(self) -> None:
        _validate_identifier("runtime scaffold_id", self.scaffold_id)
        _validate_staged_row_id(self.source_row_id)
        _validate_staged_descriptor_id(self.coverage_descriptor_id)
        _validate_staged_execution_id(self.execution_id)
        _validate_blocked_support(
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            block_reason=self.block_reason,
        )
        if self.named_handler_id is not None:
            raise JulyFactionPackStagingError(
                "July PR 2 source-only runtime scaffolds cannot name handlers."
            )


class JulyRuntimeScaffoldArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    phase17e_artifact_id: str
    phase17f_artifact_id: str
    rows: list[JulyRuntimeScaffoldRowArtifact]

    def validate(self) -> None:
        if self.artifact_schema != JULY_RUNTIME_SCAFFOLD_SCHEMA:
            raise JulyFactionPackStagingError(
                "July runtime scaffold artifact schema is unsupported."
            )
        _validate_identifier("runtime scaffold artifact_id", self.artifact_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July runtime scaffold belongs to the wrong staged package."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July runtime scaffold source date is stale.")
        _validate_identifier("runtime scaffold phase17e_artifact_id", self.phase17e_artifact_id)
        _validate_identifier("runtime scaffold phase17f_artifact_id", self.phase17f_artifact_id)
        _validate_unique_rows(self.rows, id_field="scaffold_id")
        for row in self.rows:
            row.validate()


class JulyDatasheetOverlayOperationArtifact(msgspec.Struct, frozen=True):
    operation_id: str
    operation_kind: str
    target_source_row_id: str
    field_name: str
    replacement_value: str | None

    def validate(self) -> None:
        _validate_identifier("datasheet overlay operation_id", self.operation_id)
        if self.operation_kind not in _APPROVED_DATASHEET_OVERLAY_OPERATIONS:
            raise JulyFactionPackStagingError(
                "July datasheet overlay operation kind is unsupported."
            )
        _validate_identifier("datasheet overlay target_source_row_id", self.target_source_row_id)
        _validate_identifier("datasheet overlay field_name", self.field_name)
        if self.operation_kind in {"add_keyword", "replace_ability_text"}:
            if self.replacement_value is None:
                raise JulyFactionPackStagingError(
                    "July datasheet add/update operation requires a replacement value."
                )
            _validate_text("datasheet overlay replacement_value", self.replacement_value)
        elif self.replacement_value is not None:
            raise JulyFactionPackStagingError(
                "July datasheet removal operation cannot carry a replacement value."
            )


class JulyDatasheetRowArtifact(msgspec.Struct, frozen=True):
    source_row_id: str
    predecessor_datasheet_source_row_id: str
    datasheet_id: str
    datasheet_name: str
    faction_id: str
    faction_name: str
    source_pdf_package_id: str
    source_pdf_page: int
    source_treatment: str
    inventory_status: str
    historical_provenance_retained: bool
    load_support_status: str
    semantic_execution_status: str
    runtime_support_claim: str
    overlay_operations: list[JulyDatasheetOverlayOperationArtifact]

    def validate(self) -> None:
        _validate_staged_row_id(self.source_row_id)
        _validate_identifier(
            "datasheet predecessor_datasheet_source_row_id",
            self.predecessor_datasheet_source_row_id,
        )
        _validate_identifier("datasheet datasheet_id", self.datasheet_id)
        if self.predecessor_datasheet_source_row_id != self.datasheet_id:
            raise JulyFactionPackStagingError(
                "July datasheet review must retain its stable predecessor datasheet ID."
            )
        _validate_text("datasheet datasheet_name", self.datasheet_name)
        _validate_identifier("datasheet faction_id", self.faction_id)
        _validate_text("datasheet faction_name", self.faction_name)
        _validate_successor_package_id(self.faction_id, self.source_pdf_package_id)
        _validate_page(self.source_pdf_page)
        if self.source_treatment != "complete_pdf":
            raise JulyFactionPackStagingError(
                "July changed datasheets require complete-PDF staged review."
            )
        if self.inventory_status not in {
            "current_matched_play",
            "historical_predecessor_only",
        }:
            raise JulyFactionPackStagingError("July datasheet inventory status is unsupported.")
        if not self.historical_provenance_retained:
            raise JulyFactionPackStagingError(
                "July datasheet review must retain historical provenance."
            )
        _validate_blocked_support(
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            block_reason=_BLOCK_REASON,
        )
        if self.runtime_support_claim != "unknown":
            raise JulyFactionPackStagingError(
                "July PR 3 datasheet review cannot upgrade runtime support."
            )
        if not self.overlay_operations:
            raise JulyFactionPackStagingError(
                "July changed datasheet review requires one or more overlay operations."
            )
        seen_operation_ids: set[str] = set()
        for operation in self.overlay_operations:
            operation.validate()
            if operation.operation_id in seen_operation_ids:
                raise JulyFactionPackStagingError(
                    "July datasheet overlay operation IDs must be unique within a row."
                )
            seen_operation_ids.add(operation.operation_id)
        removal_operations = [
            operation
            for operation in self.overlay_operations
            if operation.operation_kind == "remove_from_current_inventory"
        ]
        if (self.inventory_status == "historical_predecessor_only") != bool(removal_operations):
            raise JulyFactionPackStagingError(
                "July removed datasheets require exactly an inventory-removal overlay."
            )


class JulyDatasheetArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    predecessor_manifest_path: str
    predecessor_manifest_sha256: str
    excluded_content_categories: list[str]
    rows: list[JulyDatasheetRowArtifact]

    def validate(self) -> None:
        if self.artifact_schema != JULY_DATASHEET_SCHEMA:
            raise JulyFactionPackStagingError("July datasheet artifact schema is unsupported.")
        _validate_identifier("datasheet artifact_id", self.artifact_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July datasheet artifact belongs to the wrong staged package."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July datasheet artifact source date is stale.")
        if (
            self.predecessor_manifest_path
            != "data/source_manifests/faction_pack_datasheet_review_v1.json"
        ):
            raise JulyFactionPackStagingError(
                "July datasheet predecessor review manifest path is unexpected."
            )
        _validate_sha256(
            "datasheet predecessor_manifest_sha256",
            self.predecessor_manifest_sha256,
        )
        if self.excluded_content_categories != [
            "imperial-armour",
            "legends",
        ]:
            raise JulyFactionPackStagingError(
                "July datasheet artifact must exclude Imperial Armour and Legends."
            )
        _validate_unique_rows(self.rows)
        datasheet_ids: set[str] = set()
        for row in self.rows:
            row.validate()
            if row.datasheet_id in datasheet_ids:
                raise JulyFactionPackStagingError(
                    "July datasheet review must map each datasheet exactly once."
                )
            datasheet_ids.add(row.datasheet_id)


class JulyDatasheetPreviewRowArtifact(msgspec.Struct, array_like=True, frozen=True):
    datasheet_id: str
    datasheet_name: str
    faction_id: str
    inventory_status: str
    load_support_status: str
    semantic_execution_status: str
    runtime_support_claim: str

    def validate(self) -> None:
        _validate_identifier("datasheet preview datasheet_id", self.datasheet_id)
        _validate_text("datasheet preview datasheet_name", self.datasheet_name)
        _validate_identifier("datasheet preview faction_id", self.faction_id)
        if self.inventory_status not in {
            "current_matched_play",
            "historical_predecessor_only",
        }:
            raise JulyFactionPackStagingError(
                "July datasheet preview inventory status is unsupported."
            )
        _validate_blocked_support(
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            block_reason=_BLOCK_REASON,
        )
        if self.runtime_support_claim != "unknown":
            raise JulyFactionPackStagingError(
                "July datasheet preview cannot upgrade runtime support."
            )


class JulyDatasheetPreviewArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    preview_marker: str
    datasheet_artifact_id: str
    datasheet_artifact_sha256: str
    rows: list[JulyDatasheetPreviewRowArtifact]

    def validate(self) -> None:
        if self.artifact_schema != JULY_DATASHEET_PREVIEW_SCHEMA:
            raise JulyFactionPackStagingError(
                "July datasheet preview artifact schema is unsupported."
            )
        _validate_identifier("datasheet preview artifact_id", self.artifact_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July datasheet preview belongs to the wrong staged package."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July datasheet preview source date is stale.")
        if self.preview_marker != "staged_preview_not_current":
            raise JulyFactionPackStagingError(
                "July datasheet support output must be marked as a staged preview."
            )
        if self.datasheet_artifact_id != "gw-11e-july-faction-pack-datasheets-2026-07":
            raise JulyFactionPackStagingError(
                "July datasheet preview links the wrong datasheet artifact."
            )
        _validate_sha256(
            "datasheet preview datasheet_artifact_sha256",
            self.datasheet_artifact_sha256,
        )
        _validate_unique_rows(self.rows, id_field="datasheet_id")
        for row in self.rows:
            row.validate()


class JulyStagingPackageArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    activation_status: str
    predecessor_artifacts: list[StagedPredecessorArtifact]
    delta_ledger_artifact: str
    delta_ledger_sha256: str
    staged_data_artifacts: list[StagedArtifactReference]

    def validate(self) -> None:
        if self.artifact_schema != JULY_FACTION_PACK_PACKAGE_SCHEMA:
            raise JulyFactionPackStagingError(
                "July faction-pack staging package artifact schema is unsupported."
            )
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July faction-pack staging source package identity is stale."
            )
        _validate_text("source_title", self.source_title)
        _validate_identifier("source_version", self.source_version)
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July faction-pack staging source date is stale.")
        if self.activation_status != JULY_FACTION_PACK_ACTIVATION_STATUS:
            raise JulyFactionPackStagingError(
                "July faction-pack successor must remain staged before promotion."
            )
        if self.delta_ledger_artifact != "artifacts/delta-ledger.json":
            raise JulyFactionPackStagingError(
                "July faction-pack delta ledger artifact path is unexpected."
            )
        _validate_artifact_path(self.delta_ledger_artifact)
        _validate_sha256("delta_ledger_sha256", self.delta_ledger_sha256)
        predecessor_ids: set[str] = set()
        for predecessor in self.predecessor_artifacts:
            predecessor.validate()
            if predecessor.source_package_id in predecessor_ids:
                raise JulyFactionPackStagingError(
                    "July staging package repeats a predecessor package identity."
                )
            predecessor_ids.add(predecessor.source_package_id)
        expected_predecessors = {
            "gw-11e-faction-detachments-2026-27",
            "gw-11e-phase17e-exact-faction-subrules-2026-27",
            "gw-11e-phase17e-faction-coverage-2026-27",
            "gw-11e-phase17f-faction-execution-2026-27",
        }
        if predecessor_ids != expected_predecessors:
            raise JulyFactionPackStagingError(
                "July staging package must link the exact active June source packages."
            )
        seen_artifact_ids: set[str] = set()
        seen_artifact_paths: set[str] = set()
        for artifact in self.staged_data_artifacts:
            artifact.validate()
            if artifact.artifact_id in seen_artifact_ids:
                raise JulyFactionPackStagingError("July staged artifact IDs must be unique.")
            if artifact.artifact_path in seen_artifact_paths:
                raise JulyFactionPackStagingError("July staged artifact paths must be unique.")
            seen_artifact_ids.add(artifact.artifact_id)
            seen_artifact_paths.add(artifact.artifact_path)
        expected_staged_artifact_ids = {
            "gw-11e-july-faction-pack-datasheet-preview-2026-07",
            "gw-11e-july-faction-pack-datasheets-2026-07",
            "gw-11e-july-faction-pack-detachments-2026-07",
            "gw-11e-july-faction-pack-subrules-2026-07",
            "gw-11e-july-faction-pack-phase17e-coverage-2026-07",
            "gw-11e-july-faction-pack-phase17f-execution-2026-07",
            "gw-11e-july-faction-pack-runtime-scaffolds-2026-07",
        }
        if seen_artifact_ids != expected_staged_artifact_ids:
            raise JulyFactionPackStagingError(
                "July staging package must declare the exact staged PR 2 artifacts."
            )

    def source_payload_checksum_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(msgspec.to_builtins(self))).hexdigest()


def july_staging_package_from_json_bytes(raw: bytes) -> JulyStagingPackageArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyStagingPackageArtifact,
        artifact_description="staging package",
    )
    artifact.validate()
    return artifact


def july_delta_ledger_from_json_bytes(raw: bytes) -> JulyDeltaLedgerArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyDeltaLedgerArtifact,
        artifact_description="delta ledger",
    )
    artifact.validate()
    return artifact


def july_detachments_from_json_bytes(raw: bytes) -> JulyDetachmentArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyDetachmentArtifact,
        artifact_description="detachment",
    )
    artifact.validate()
    return artifact


def july_subrules_from_json_bytes(raw: bytes) -> JulySubruleArtifact:
    artifact = _decode_json_artifact(raw, JulySubruleArtifact, artifact_description="subrule")
    artifact.validate()
    return artifact


def july_phase17e_from_json_bytes(raw: bytes) -> JulyPhase17ECoverageArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyPhase17ECoverageArtifact,
        artifact_description="Phase 17E coverage",
    )
    artifact.validate()
    return artifact


def july_phase17f_from_json_bytes(raw: bytes) -> JulyPhase17FExecutionArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyPhase17FExecutionArtifact,
        artifact_description="Phase 17F execution",
    )
    artifact.validate()
    return artifact


def july_runtime_scaffolds_from_json_bytes(raw: bytes) -> JulyRuntimeScaffoldArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyRuntimeScaffoldArtifact,
        artifact_description="runtime scaffold",
    )
    artifact.validate()
    return artifact


def july_datasheets_from_json_bytes(raw: bytes) -> JulyDatasheetArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyDatasheetArtifact,
        artifact_description="datasheet review and overlay",
    )
    artifact.validate()
    return artifact


def july_datasheet_preview_from_json_bytes(raw: bytes) -> JulyDatasheetPreviewArtifact:
    artifact = _decode_json_artifact(
        raw,
        JulyDatasheetPreviewArtifact,
        artifact_description="datasheet support preview",
    )
    artifact.validate()
    return artifact


def canonical_json_sha256_from_bytes(raw: bytes) -> str:
    try:
        payload = cast(object, json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JulyFactionPackStagingError(
            "July faction-pack artifact is not valid UTF-8 JSON."
        ) from exc
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def audit_manifest_links(
    *,
    ledger: JulyDeltaLedgerArtifact,
    pending_packages: Mapping[str, tuple[str, str]],
    current_packages: Mapping[str, tuple[str, str]],
) -> None:
    if type(ledger) is not JulyDeltaLedgerArtifact:
        raise JulyFactionPackStagingError(
            "July manifest-link audit requires a delta ledger artifact."
        )
    pending = _validate_manifest_mapping("pending_packages", pending_packages)
    current = _validate_manifest_mapping("current_packages", current_packages)
    ledger_successors = {review.successor_package_id for review in ledger.pack_reviews}
    if set(pending) != ledger_successors:
        raise JulyFactionPackStagingError(
            "Every pending July faction pack must have exactly one ledger review row."
        )
    expected_current_ids = {review.predecessor_package_id for review in ledger.pack_reviews}
    deathwatch_package_id = "gw-11e-deathwatch-faction-pack-2026-06"
    if set(current) != expected_current_ids | {deathwatch_package_id}:
        raise JulyFactionPackStagingError(
            "July predecessor audit requires the exact active June package set."
        )
    for review in ledger.pack_reviews:
        successor_sha256, successor_path = pending[review.successor_package_id]
        predecessor_sha256, _predecessor_path = current[review.predecessor_package_id]
        if (successor_sha256, successor_path) != (
            review.successor_pdf_sha256,
            review.successor_pdf_path,
        ):
            raise JulyFactionPackStagingError(
                "July successor package hash or path drifted from the pending manifest."
            )
        if predecessor_sha256 != review.predecessor_pdf_sha256:
            raise JulyFactionPackStagingError(
                "June predecessor package hash drifted from the current manifest."
            )


def audit_runtime_predecessor_references(
    *,
    ledger: JulyDeltaLedgerArtifact,
    stable_reference_ids_by_kind: Mapping[str, Set[str]],
) -> None:
    if type(ledger) is not JulyDeltaLedgerArtifact:
        raise JulyFactionPackStagingError(
            "July predecessor-reference audit requires a delta ledger artifact."
        )
    available: dict[str, Set[str]] = {}
    for kind, values in stable_reference_ids_by_kind.items():
        if kind not in _APPROVED_REFERENCE_KINDS:
            raise JulyFactionPackStagingError(
                "Stable predecessor reference audit received an unsupported kind."
            )
        available[kind] = values
    for review in ledger.pack_reviews:
        for item in review.review_items:
            if item.disposition != "in_scope_runtime_affected":
                continue
            for reference in item.predecessor_references:
                if reference.reference_id not in available.get(
                    reference.reference_kind, frozenset()
                ):
                    raise JulyFactionPackStagingError(
                        "Runtime-affected July review item has no stable predecessor row."
                    )


def audit_load_only_artifact_links(
    *,
    detachments: JulyDetachmentArtifact,
    subrules: JulySubruleArtifact,
    phase17e: JulyPhase17ECoverageArtifact,
    phase17f: JulyPhase17FExecutionArtifact,
    runtime_scaffolds: JulyRuntimeScaffoldArtifact,
) -> None:
    source_row_ids = {row.source_row_id for row in detachments.rows} | {
        row.source_row_id for row in subrules.rows
    }
    component_source_row_ids = {
        source_row_id for row in detachments.rows for source_row_id in row.component_source_row_ids
    }
    subrule_source_row_ids = {row.source_row_id for row in subrules.rows}
    if not component_source_row_ids.issubset(subrule_source_row_ids):
        raise JulyFactionPackStagingError(
            "July detachment component links must resolve to staged subrule rows."
        )
    phase17e_by_source = {row.source_row_id: row for row in phase17e.rows}
    if set(phase17e_by_source) != source_row_ids:
        raise JulyFactionPackStagingError(
            "July Phase 17E coverage must map every staged load-only source row exactly once."
        )
    phase17f_by_source = {row.source_row_id: row for row in phase17f.rows}
    if set(phase17f_by_source) != source_row_ids:
        raise JulyFactionPackStagingError(
            "July Phase 17F execution must map every staged load-only source row exactly once."
        )
    for source_row_id, execution in phase17f_by_source.items():
        if execution.coverage_descriptor_id != phase17e_by_source[source_row_id].descriptor_id:
            raise JulyFactionPackStagingError(
                "July Phase 17F execution must link its matching Phase 17E descriptor."
            )
    scaffolds_by_source = {row.source_row_id: row for row in runtime_scaffolds.rows}
    if set(scaffolds_by_source) != source_row_ids:
        raise JulyFactionPackStagingError(
            "July runtime scaffolds must map every staged load-only source row exactly once."
        )
    for source_row_id, scaffold in scaffolds_by_source.items():
        phase17e_row = phase17e_by_source[source_row_id]
        phase17f_row = phase17f_by_source[source_row_id]
        if (
            scaffold.coverage_descriptor_id != phase17e_row.descriptor_id
            or scaffold.execution_id != phase17f_row.execution_id
        ):
            raise JulyFactionPackStagingError(
                "July runtime scaffold links drifted from staged Phase 17E/17F rows."
            )


def audit_datasheet_preview_links(
    *,
    datasheets: JulyDatasheetArtifact,
    preview: JulyDatasheetPreviewArtifact,
    datasheet_artifact_sha256: str,
) -> None:
    _validate_sha256("datasheet artifact SHA-256", datasheet_artifact_sha256)
    if preview.datasheet_artifact_id != datasheets.artifact_id:
        raise JulyFactionPackStagingError("July datasheet preview artifact identity link is stale.")
    if preview.datasheet_artifact_sha256 != datasheet_artifact_sha256:
        raise JulyFactionPackStagingError("July datasheet preview artifact hash link is stale.")
    review_by_id = {row.datasheet_id: row for row in datasheets.rows}
    preview_by_id = {row.datasheet_id: row for row in preview.rows}
    if set(review_by_id) != set(preview_by_id):
        raise JulyFactionPackStagingError(
            "July datasheet preview must map every staged review row exactly once."
        )
    for datasheet_id, preview_row in preview_by_id.items():
        review_row = review_by_id[datasheet_id]
        expected = (
            review_row.datasheet_name,
            review_row.faction_id,
            review_row.inventory_status,
            review_row.load_support_status,
            review_row.semantic_execution_status,
            review_row.runtime_support_claim,
        )
        actual = (
            preview_row.datasheet_name,
            preview_row.faction_id,
            preview_row.inventory_status,
            preview_row.load_support_status,
            preview_row.semantic_execution_status,
            preview_row.runtime_support_claim,
        )
        if actual != expected:
            raise JulyFactionPackStagingError(
                "July datasheet preview drifted from its staged review row."
            )


def _decode_json_artifact[ArtifactT](
    raw: bytes,
    artifact_type: type[ArtifactT],
    *,
    artifact_description: str,
) -> ArtifactT:
    try:
        return msgspec.json.decode(raw, type=artifact_type)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError(
            f"July faction-pack {artifact_description} artifact is invalid."
        ) from exc


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_manifest_mapping(
    field_name: str,
    value: object,
) -> dict[str, tuple[str, str]]:
    if not isinstance(value, Mapping):
        raise JulyFactionPackStagingError(f"{field_name} must be a mapping.")
    validated: dict[str, tuple[str, str]] = {}
    for raw_package_id, raw_identity in cast(Mapping[object, object], value).items():
        package_id = _validate_identifier("manifest package_id", raw_package_id)
        if type(raw_identity) is not tuple:
            raise JulyFactionPackStagingError(
                "Manifest identity values must be (sha256, local path) tuples."
            )
        identity = cast(tuple[object, ...], raw_identity)
        if len(identity) != 2 or type(identity[0]) is not str or type(identity[1]) is not str:
            raise JulyFactionPackStagingError(
                "Manifest identity values must be (sha256, local path) tuples."
            )
        sha256 = _validate_sha256("manifest sha256", identity[0])
        path = identity[1]
        _validate_pdf_path(path)
        validated[package_id] = (sha256, path)
    return validated


def _validate_artifact_header(
    *,
    actual_schema: str,
    expected_schema: str,
    artifact_id: str,
    source_package_id: str,
    source_date: str,
    predecessor_package_id: str,
    predecessor_package_sha256: str,
    expected_predecessor_id: str,
) -> None:
    if actual_schema != expected_schema:
        raise JulyFactionPackStagingError("July staged data artifact schema is unsupported.")
    _validate_identifier("staged data artifact_id", artifact_id)
    if source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
        raise JulyFactionPackStagingError("July staged data belongs to the wrong package.")
    if source_date != JULY_FACTION_PACK_SOURCE_DATE:
        raise JulyFactionPackStagingError("July staged data source date is stale.")
    if predecessor_package_id != expected_predecessor_id:
        raise JulyFactionPackStagingError("July staged data predecessor package is incorrect.")
    _validate_sha256("staged data predecessor_package_sha256", predecessor_package_sha256)


def _validate_unique_rows(rows: Sequence[object], *, id_field: str = "source_row_id") -> None:
    if not rows:
        raise JulyFactionPackStagingError("July staged data artifact requires rows.")
    row_ids: set[str] = set()
    for row in rows:
        row_id = cast(str, getattr(row, id_field))
        if row_id in row_ids:
            raise JulyFactionPackStagingError("July staged data row IDs must be unique.")
        row_ids.add(row_id)


def _validate_unique_identifiers(field_name: str, values: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        validated = _validate_identifier(field_name, value)
        if validated in seen:
            raise JulyFactionPackStagingError(
                f"July faction-pack {field_name} must not contain duplicates."
            )
        seen.add(validated)


def _validate_successor_package_id(faction_id: str, package_id: str) -> None:
    expected = f"gw-11e-{faction_id}{_SUCCESSOR_PACKAGE_SUFFIX}"
    if package_id != expected:
        raise JulyFactionPackStagingError("July staged row source PDF does not match its faction.")


def _validate_page(value: object) -> int:
    if type(value) is not int or value < 1:
        raise JulyFactionPackStagingError(
            "July faction-pack source PDF page must be a positive integer."
        )
    return value


def _validate_staged_row_id(value: str) -> None:
    _validate_identifier("staged source_row_id", value)
    if not value.startswith(f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:"):
        raise JulyFactionPackStagingError("July source row ID must belong to the staged package.")


def _validate_staged_descriptor_id(value: str) -> None:
    _validate_identifier("staged coverage descriptor_id", value)
    if not value.startswith(f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:phase17e:"):
        raise JulyFactionPackStagingError(
            "July coverage descriptor ID must belong to the staged package."
        )


def _validate_staged_execution_id(value: str) -> None:
    _validate_identifier("staged execution_id", value)
    if not value.startswith(f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:phase17f:"):
        raise JulyFactionPackStagingError("July execution ID must belong to the staged package.")


def _validate_blocked_support(
    *,
    load_support_status: str,
    semantic_execution_status: str,
    block_reason: str,
) -> None:
    if load_support_status != _LOAD_SUPPORT_STATUS:
        raise JulyFactionPackStagingError("July staged row must be load-supported.")
    if semantic_execution_status != _SEMANTIC_EXECUTION_STATUS:
        raise JulyFactionPackStagingError("July PR 2 staged row must remain blocked.")
    if block_reason != _BLOCK_REASON:
        raise JulyFactionPackStagingError(
            "July PR 2 staged row requires the structured-semantics block reason."
        )


_validate_identifier = IdentifierValidator(
    JulyFactionPackStagingError,
    pattern=_IDENTIFIER_RE,
    pattern_message="July faction-pack {field_name} must be a stable identifier.",
)


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise JulyFactionPackStagingError(
            f"July faction-pack {field_name} must be non-empty normalized text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise JulyFactionPackStagingError(
            f"July faction-pack {field_name} must be a lowercase SHA-256."
        )
    return value


def _validate_artifact_path(value: object) -> str:
    if (
        type(value) is not str
        or "\\" in value
        or ".." in value.split("/")
        or _ARTIFACT_PATH_RE.fullmatch(value) is None
    ):
        raise JulyFactionPackStagingError(
            "July faction-pack artifact path must be normalized package JSON."
        )
    return value


def _validate_pdf_path(value: object) -> str:
    if (
        type(value) is not str
        or "\\" in value
        or ".." in value.split("/")
        or not value.startswith("data/raw/faction_packs/eng_")
        or not value.endswith(".pdf")
    ):
        raise JulyFactionPackStagingError(
            "July faction-pack PDF path must be a normalized raw source path."
        )
    return value
