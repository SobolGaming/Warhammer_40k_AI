"""Strict records for the offline clause-evidence inventory, never runtime input."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class FileEvidence(Record):
    path: str
    sha256: str


class AssertionEvidence(Record):
    nodeid: str
    role: Literal["semantic", "facade", "invalid", "replay", "viewer"]
    assertion: str
    proves: str


class Requirement(Record):
    row_id: str
    requirement_id: str
    source_blocks: list[int]
    source_detail: str | None = None
    summary: str
    owners: list[str]
    evidence: list[AssertionEvidence]
    qualifications: list[str]


class Nonoperative(Record):
    row_id: str
    source_blocks: list[int]
    classification: Literal["example", "metadata", "cross_reference", "context"]
    reason: str


class AssertionReceipt(Record):
    nodeid: str
    assertion: str
    sha256: str
    test_ast_sha256: str


class Block(Record):
    ordinal: int
    kind: str
    sha256: str
    value: Any


class SelectedSource(Record):
    row_id: str
    category: str
    locator: str
    title: str
    occurrence: int
    source_sha256: str
    blocks: list[Block]
    selected_provider: str
    historical_source_row_sha256: str
    historical_blocks: list[Block] | None = None
    review_category: str


class ChangelogEntry(Record):
    entry_id: str
    version: str
    kind: str
    entry_sha256: str
    entry: Any
    summary: str
    source_rows: list[str]
    requirement_ids: list[str]
    disposition: str
    qualification: str


class RuntimeRule(Record):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: str
    semantic_execution_status: str
    runtime_consumer_ids: list[str]
    selected_rows: list[str]
    relation: Literal["selected_excerpt", "reviewed_layout", "superseded", "source_repair_required"]
    review: str
    retired_consumer_successors: dict[str, list[str]] = {}


class RuntimePackage(FileEvidence):
    source_package_id: str
    source_version: str
    package_hash: str
    metadata_sha256: str
    rules: list[RuntimeRule]


class Followup(Record):
    finding_id: str
    pr_id: str
    kind: Literal["evidence", "source", "gameplay"]
    description: str
    requirement_ids: list[str]
    runtime_source_ids: list[str]


class Inventory(Record):
    schema_id: Literal["core-v2-order97-clause-evidence-v1"]
    reviewed_commit: str
    runtime_input: Literal[False]
    caudit_01_closed: Literal[False]
    outcome: Literal["clause_evidence_inventory"]
    categories: list[str]
    files: list[FileEvidence]
    qualifications: list[str]
    followups: list[Followup]
    sources: list[SelectedSource]
    requirements: list[Requirement]
    nonoperative: list[Nonoperative]
    assertions: list[AssertionReceipt]
    changelog: list[ChangelogEntry]
    runtime_packages: list[RuntimePackage]
