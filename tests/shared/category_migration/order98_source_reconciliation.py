"""Order 98 source reconciliation for the eight reviewed runtime rows."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace
from typing import Any

import pytest

from warhammer40k_core.rules.source_catalog import SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import (
    RuleEvidenceError,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

_PACKAGE_ROOT = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"


def _call(module_name: str, function_name: str, raw: bytes) -> Any:
    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    return function(raw)


_HISTORICAL_MOVE_UNITS_EXCERPT_SHA256 = (
    "6ea310aedead79971d092f9ae035b0c0b79499bcc656e3899a5546ba6234c54f"
)


def _load(package: str) -> bytes:
    return package_artifact_bytes(package, "artifacts/package.json")


def _resolve(consumer_id: str) -> object:
    module_name, symbol_name = consumer_id.split(":", 1)
    resolved: object = importlib.import_module(module_name)
    for part in symbol_name.split("."):
        resolved = getattr(resolved, part)
    return resolved


def _observation_sha256(payload: Any) -> str:
    body = dict(payload)
    body["observation_sha256"] = ""
    body["load_support_status"] = "not_loaded"
    body["semantic_execution_status"] = "not_certified"
    body["runtime_consumer_ids"] = []
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _replace_controlling_text(package: RuleSourcePackage, source_id: str) -> RuleSourcePackage:
    documents: list[SourceDocument] = []
    for document in package.source_catalog.documents:
        source_texts = tuple(
            RuleSourceText.from_raw(
                source_id=source.source_id,
                raw_text=f"{source.raw_text}\nUnauthorized.",
                objective_scope=source.objective_scope,
            )
            if source.source_id == source_id
            else source
            for source in document.source_texts
        )
        documents.append(replace(document, source_texts=source_texts))
    catalog = replace(package.source_catalog, documents=tuple(documents))
    replacement = catalog.source_text_by_id(source_id).raw_text
    transcription_sha256 = hashlib.sha256(replacement.encode()).hexdigest()
    records: list[RuleEvidenceRecord] = []
    for record in package.source_evidence_catalog.records:
        if (
            record.rule_source_id != source_id
            or record.evidence_kind != "project_reviewed_app_transcription"
        ):
            records.append(record)
            continue
        payload = record.to_payload()
        payload["transcription_sha256"] = transcription_sha256
        payload["observation_sha256"] = _observation_sha256(payload)
        records.append(RuleEvidenceRecord.from_payload(payload))
    return RuleSourcePackage(
        source_catalog=catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=tuple(records)),
        evidence_required_source_ids=package.evidence_required_source_ids,
        source_authority_scope=package.source_authority_scope,
    )


__all__: list[str] = []
__all__ += ["Any", "RuleEvidenceError", "RuleEvidenceRecord", "RuleSourcePackage"]
__all__ += ["RuleSourceText", "SourceDocument", "SourceEvidenceCatalog"]
__all__ += ["_HISTORICAL_MOVE_UNITS_EXCERPT_SHA256", "_PACKAGE_ROOT", "_call", "_load"]
__all__ += ["_observation_sha256", "_replace_controlling_text", "_resolve", "hashlib"]
__all__ += ["importlib", "json", "package_artifact_bytes", "pytest", "replace"]
