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


def test_order98_repairs_the_eight_runtime_source_rows() -> None:
    command = _call(
        f"{_PACKAGE_ROOT}.core_command_phase_2026_08._artifacts",
        "core_command_phase_source_artifact_from_json_bytes",
        _load(f"{_PACKAGE_ROOT}.core_command_phase_2026_08"),
    )
    abilities = _call(
        f"{_PACKAGE_ROOT}.core_abilities_2026_09._artifacts",
        "core_abilities_source_artifact_from_json_bytes",
        _load(f"{_PACKAGE_ROOT}.core_abilities_2026_09"),
    )
    attached = _call(
        f"{_PACKAGE_ROOT}.core_attached_units_2026_09._artifacts",
        "core_attached_units_source_artifact_from_json_bytes",
        _load(f"{_PACKAGE_ROOT}.core_attached_units_2026_09"),
    )
    movement = _call(
        f"{_PACKAGE_ROOT}.core_movement_phase_2026_08._artifacts",
        "core_movement_phase_source_artifact_from_json_bytes",
        _load(f"{_PACKAGE_ROOT}.core_movement_phase_2026_08"),
    )
    other = _call(
        f"{_PACKAGE_ROOT}.core_other_concepts_2026_08._artifacts",
        "core_other_concepts_source_artifact_from_json_bytes",
        _load(f"{_PACKAGE_ROOT}.core_other_concepts_2026_08"),
    )
    large = _call(
        f"{_PACKAGE_ROOT}.core_large_model_setup_2026_09",
        "validate_source_artifact_bytes",
        _load(f"{_PACKAGE_ROOT}.core_large_model_setup_2026_09"),
    )

    command_rules = {rule.rule_id: rule for rule in command.rules}
    start = command_rules["start-of-command-phase"]
    gain = command_rules["gain-core-cp"]
    shock = command_rules["battle-shock"]
    assert start.source_text == (
        "Rules that are triggered at the start of the Command phase are resolved now."
    )
    assert gain.source_text == "Both players gain 1 Command Point (CP)."
    assert "half\u2011strength" in shock.source_text
    assert "Battle-shock Examples" in shock.source_text
    assert shock.source_text != shock.official_pdf_source_text
    assert start.semantic_execution_status == gain.semantic_execution_status
    assert start.semantic_execution_status == "executable_engine_runtime"
    assert shock.semantic_execution_status == "partial_engine_runtime"
    for rule in command.rules:
        assert rule.source_text != rule.section_heading
        assert rule.load_support_status == "loaded"
        for consumer_id in rule.runtime_consumer_ids:
            assert _resolve(consumer_id) is not None
    assert {record.kind for record in command.superseded_records} == {"label_only_transcription"}
    assert all(
        record.load_support_status == "loaded"
        and record.semantic_execution_status == "not_certified"
        for record in command.superseded_records
    )

    scout = next(
        rule
        for rule in abilities.rules
        if rule.source_id == "gw-11e-core-abilities:faq:alternating-scout-moves"
    )
    assert (
        "warhammer40k_core.engine.prebattle_integrity:validate_prebattle_alternation_restore"
        in scout.runtime_consumer_ids
    )
    assert (
        "warhammer40k_core.engine.prebattle_alternation:validate_prebattle_alternation_restore"
        not in scout.runtime_consumer_ids
    )
    assert scout.semantic_execution_status == "executable_engine_runtime"
    retired_scout = abilities.superseded_records[0]
    assert retired_scout.kind == "retired_consumer"
    assert retired_scout.semantic_execution_status == "not_certified"
    assert _resolve(retired_scout.successor) is not None

    bodyguard = attached.rules[0]
    assert (
        "warhammer40k_core.engine.starting_attached_units:starting_attached_unit_records_for_army"
    ) in bodyguard.runtime_consumer_ids
    assert (
        "warhammer40k_core.engine.starting_attached_units:"
        "starting_attached_unit_records_from_armies" not in bodyguard.runtime_consumer_ids
    )
    retired_attached = attached.superseded_records[0]
    assert retired_attached.kind == "retired_consumer"
    assert retired_attached.load_support_status == "loaded"
    assert retired_attached.semantic_execution_status == "not_certified"
    assert _resolve(retired_attached.successor) is not None

    move_units = next(rule for rule in movement.rules if rule.rule_id == "move-units-step")
    assert "not been selected to move this phase" in move_units.source_text
    assert "one presented elsewhere" in move_units.source_text
    assert move_units.semantic_execution_status == "executable_engine_runtime"
    move_mirror = next(
        row
        for row in movement.evidence
        if row.evidence_id == "40k-app-movement-phase-2026-08-30:move-units-step"
    )
    assert move_mirror.transcription_sha256 == _HISTORICAL_MOVE_UNITS_EXCERPT_SHA256
    assert movement.superseded_records[0].kind == "incomplete_excerpt"
    assert movement.superseded_records[0].semantic_execution_status == "not_certified"
    for consumer_id in move_units.runtime_consumer_ids:
        assert _resolve(consumer_id) is not None

    visibility = next(rule for rule in other.rules if rule.rule_id == "visibility-classifications")
    assert visibility.section_id == "06.01"
    assert visibility.section_heading == "VISIBILITY"
    assert "When a rule references a" not in visibility.source_text
    assert "MODEL FULLY VISIBLE" in visibility.source_text
    assert visibility.semantic_execution_status == "executable_engine_runtime"
    locator = other.superseded_records[0]
    assert locator.kind == "mislocated_locator"
    assert locator.prior_text == "06.01.01"
    assert locator.successor == "06.01"
    assert locator.semantic_execution_status == "not_certified"
    for consumer_id in visibility.runtime_consumer_ids:
        assert _resolve(consumer_id) is not None

    setup = large.rules[0]
    assert "..." not in setup.source_text
    assert "During Deployment:" in setup.source_text
    assert "From Strategic Reserves:" in setup.source_text
    assert "Disembarking from a Transport:" in setup.source_text
    assert "(excluding AIRCRAFT models)" in setup.source_text
    assert setup.semantic_execution_status == "executable_engine_runtime"
    assert large.superseded_records[0].kind == "incomplete_excerpt"
    assert large.superseded_records[0].semantic_execution_status == "not_certified"
    assert "..." in large.superseded_records[0].prior_text
    for consumer_id in setup.runtime_consumer_ids:
        assert _resolve(consumer_id) is not None


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


@pytest.mark.parametrize(
    ("package_name", "source_id"),
    [
        ("core_movement_phase_2026_08", "gw-11e-core-rules:movement-phase:fall-back-move"),
        ("core_movement_phase_2026_08", "gw-11e-core-rules:movement-phase:move-units-step"),
        ("core_command_phase_2026_08", "gw-11e-core-rules:command-phase:gain-core-cp"),
    ],
)
def test_order98_rejects_unregistered_controlling_text(
    package_name: str,
    source_id: str,
) -> None:
    package = importlib.import_module(f"{_PACKAGE_ROOT}.{package_name}").source_package()
    with pytest.raises(RuleEvidenceError, match="does not match its source row"):
        _replace_controlling_text(package, source_id)
