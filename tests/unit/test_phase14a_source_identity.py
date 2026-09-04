from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import cast

import pytest
from tools.build_core_abilities_source import (
    build_payload as build_core_abilities_source_payload,
)
from tools.build_core_attached_units_source import (
    build_payload as build_attached_units_source_payload,
)
from tools.build_core_attack_sequence_source import (
    build_payload as build_attack_sequence_source_payload,
)
from tools.build_core_command_phase_source import (
    CoreCommandPhaseSourceBuildError,
    build_core_command_phase_source_payload,
)
from tools.build_core_movement_phase_source import build_payload as build_movement_source_payload
from tools.build_core_other_concepts_source import (
    build_payload as build_other_concepts_source_payload,
)
from tools.build_core_transports_source import (
    build_payload as build_transports_source_payload,
)

from warhammer40k_core.core.missions import MissionSourcePackageDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.rules import source_evidence as source_evidence_module
from warhammer40k_core.rules.source_authority_registry import (
    EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256,
    SourceAuthorityRegistryError,
    load_source_authority_registry_from_json_bytes,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog
from warhammer40k_core.rules.source_evidence import (
    CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID,
    CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    RuleEvidenceAuthority,
    RuleEvidenceError,
    RuleEvidenceKind,
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleSourcePackage,
    RuleVerificationStatus,
    SourceAuthorityScope,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    app_core_rules_hidden_2026_08_09,
    chapter_approved_2026_27,
    core_abilities,
    core_abilities_2026_09,
    core_attached_units_2026_09,
    core_attack_sequence_2026_09,
    core_command_phase_2026_08,
    core_movement_phase_2026_08,
    core_other_concepts_2026_08,
    core_rules,
    core_stratagems,
    core_stratagems_2026_08,
    core_transports_2026_09,
    july_rules_updates_2026_07,
)

PROJECT_AUTHORITY_POLICY_ID = CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID
CORE_RULES_REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
CORE_RULES_REVIEW_AUDIT_PATH = Path("data/source_audits/40k_app/core_rules_2026_08_25.audit.json")
CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH = Path(
    "data/source_audits/maintained_app_mirrors/core_rules_2026_09_02.audit.json"
)


def test_eleventh_core_rules_source_catalog_cites_local_pdf_and_round_trips() -> None:
    catalog = core_rules.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    bundle = catalog.ruleset_bundles[0]
    document = catalog.documents[0]

    assert bundle.ruleset_id.to_payload()["edition"] == "11e"
    assert core_rules.LOCAL_CORE_RULES_PDF in document.title
    assert any(
        core_rules.LOCAL_CORE_RULES_PDF in source.raw_text for source in document.source_texts
    )
    assert len(document.source_texts) == 1
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert SourceCatalog.from_payload(payload).to_payload() == payload


def test_p09a_move_units_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_movement_phase_2026_08/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_movement_phase_2026_08.source_package()
    rule = core_movement_phase_2026_08.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (core_movement_phase_2026_08.EXPECTED_ARTIFACT_SHA256)
    assert json.loads(raw) == build_movement_source_payload()
    assert rule.section_id == "09.02"
    assert rule.transcription_sha256 == core_movement_phase_2026_08.TRANSCRIPTION_SHA256
    assert {
        "battlefield",
        "Strategic Reserves",
        "embarked within a Transport",
        "DISEMBARK (18.04)",
        "INGRESS (20.04)",
    } <= {
        token
        for token in (
            "battlefield",
            "Strategic Reserves",
            "embarked within a Transport",
            "DISEMBARK (18.04)",
            "INGRESS (20.04)",
        )
        if token in rule.source_text
    }
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert {record.semantic_execution_status for record in evidence} == {
        "executable_engine_runtime"
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )
    consumer_ids = set(rule.runtime_consumer_ids) | {
        consumer_id for record in evidence for consumer_id in record.runtime_consumer_ids
    }
    for consumer_id in sorted(consumer_ids):
        module_name, separator, qualified_name = consumer_id.partition(":")
        assert separator, consumer_id
        resolved: object = importlib.import_module(module_name)
        for attribute in qualified_name.split("."):
            resolved = getattr(resolved, attribute)
        assert resolved is not None, consumer_id


def test_p19_attached_units_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attached_units_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_attached_units_2026_09.source_package()
    rule = core_attached_units_2026_09.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (core_attached_units_2026_09.EXPECTED_ARTIFACT_SHA256)
    assert json.loads(raw) == build_attached_units_source_payload()
    assert rule.section_id == "19.01.01"
    assert rule.source_id == core_attached_units_2026_09.BODYGUARD_UNIT_DESTROYED_SOURCE_ID
    assert rule.transcription_sha256 == core_attached_units_2026_09.TRANSCRIPTION_SHA256
    assert "remain a single unit for all rules purposes" in rule.source_text
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p19_attached_units_source_loader_rejects_schema_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attached_units_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    payload = json.loads(raw)
    payload["rules"][0]["section_id"] = "19.01"

    with pytest.raises(
        core_attached_units_2026_09.CoreAttachedUnitsSourceArtifactError,
        match="reviewed identity",
    ):
        core_attached_units_2026_09.core_attached_units_source_artifact_from_json_bytes(
            json.dumps(payload).encode()
        )
    with pytest.raises(
        core_attached_units_2026_09.CoreAttachedUnitsSourceArtifactError,
        match="bytes drifted",
    ):
        core_attached_units_2026_09.validate_core_attached_units_source_artifact_bytes(raw + b"\n")


def test_p24f_deadly_demise_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_abilities_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_abilities_2026_09.source_package()
    rule = core_abilities_2026_09.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == core_abilities_2026_09.EXPECTED_ARTIFACT_SHA256
    assert json.loads(raw) == build_core_abilities_source_payload()
    assert rule.section_id == "24.08"
    assert rule.source_id == core_abilities_2026_09.DEADLY_DEMISE_SOURCE_ID
    assert rule.transcription_sha256 == core_abilities_2026_09.TRANSCRIPTION_SHA256
    assert "Each time a model with this ability is destroyed" in rule.source_text
    assert "when this unit is destroyed" not in rule.source_text.lower()
    assert rule.when_descriptor.startswith("Each time a model with this ability is destroyed")
    assert rule.trigger_kind == "after_model_destroyed"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    mirror = next(
        record for record in evidence if record.authority == "project_authoritative_app_mirror"
    )
    assert mirror.provider_name == "Game Datamissions"
    assert mirror.app_version == "931"
    assert mirror.review_audit_source_observation_sha256 == (
        "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
    )
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p24f_deadly_demise_source_loader_rejects_timing_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_abilities_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    payload = json.loads(raw)
    payload["rules"][0]["trigger_kind"] = "after_unit_destroyed"

    with pytest.raises(
        core_abilities_2026_09.CoreAbilitiesSourceArtifactError,
        match="reviewed identity",
    ):
        core_abilities_2026_09.core_abilities_source_artifact_from_json_bytes(
            json.dumps(payload).encode()
        )
    with pytest.raises(
        core_abilities_2026_09.CoreAbilitiesSourceArtifactError,
        match="bytes drifted",
    ):
        core_abilities_2026_09.validate_core_abilities_source_artifact_bytes(raw + b"\n")


def test_p05a_destroyed_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attack_sequence_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_attack_sequence_2026_09.source_package()
    rule = core_attack_sequence_2026_09.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (
        core_attack_sequence_2026_09.EXPECTED_ARTIFACT_SHA256
    )
    assert json.loads(raw) == build_attack_sequence_source_payload()
    assert rule.section_id == "05.04.04"
    assert rule.source_id == core_attack_sequence_2026_09.DESTROYED_RULE_ID
    assert rule.transcription_sha256 == core_attack_sequence_2026_09.TRANSCRIPTION_SHA256
    assert "only removed after the attacking unit" in rule.source_text
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p05a_destroyed_source_loader_rejects_schema_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attack_sequence_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    payload = json.loads(raw)
    payload["rules"][0]["section_id"] = "05.04"

    with pytest.raises(
        core_attack_sequence_2026_09.CoreAttackSequenceSourceArtifactError,
        match="reviewed identity",
    ):
        core_attack_sequence_2026_09.core_attack_sequence_source_artifact_from_json_bytes(
            json.dumps(payload).encode()
        )
    with pytest.raises(
        core_attack_sequence_2026_09.CoreAttackSequenceSourceArtifactError,
        match="bytes drifted",
    ):
        core_attack_sequence_2026_09.validate_core_attack_sequence_source_artifact_bytes(
            raw + b"\n"
        )


def test_p18c_p18d_p18e_transport_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_transports_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_transports_2026_09.source_package()
    rules = core_transports_2026_09.source_rule_records()
    rules_by_source_id = {rule.source_id: rule for rule in rules}
    emergency_rule = rules_by_source_id[core_transports_2026_09.EMERGENCY_DISEMBARK_MOVE_SOURCE_ID]
    assault_rule = rules_by_source_id[core_transports_2026_09.ASSAULT_DISEMBARK_MOVE_SOURCE_ID]
    shock_rule = rules_by_source_id[core_transports_2026_09.SHOCK_DISEMBARK_MOVE_SOURCE_ID]

    assert hashlib.sha256(raw).hexdigest() == (core_transports_2026_09.EXPECTED_ARTIFACT_SHA256)
    assert json.loads(raw) == build_transports_source_payload()
    assert emergency_rule.section_id == "18.05"
    assert emergency_rule.transcription_sha256 == (
        core_transports_2026_09.EMERGENCY_DISEMBARK_TRANSCRIPTION_SHA256
    )
    assert "Before moving: Make a hazard roll for each model" in emergency_rule.source_text
    assert "While moving: Set up each model" in emergency_rule.source_text
    assert assault_rule.section_id == "18.06"
    assert assault_rule.transcription_sha256 == (
        core_transports_2026_09.ASSAULT_DISEMBARK_TRANSCRIPTION_SHA256
    )
    assert "Did not embark within that TRANSPORT this phase" in assault_rule.source_text
    assert "wholly within the set" in assault_rule.source_text
    assert shock_rule.section_id == "18.07"
    assert shock_rule.transcription_sha256 == (
        core_transports_2026_09.SHOCK_DISEMBARK_TRANSCRIPTION_SHA256
    )
    assert "must still be engaged with that enemy unit" in shock_rule.source_text
    assert "your opponent must select each of those units, one at a time" in (
        shock_rule.source_text
    )
    for rule in rules:
        evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)
        assert rule.load_support_status == "loaded"
        assert rule.semantic_execution_status == "executable_engine_runtime"
        assert {record.evidence_kind for record in evidence} == {
            "project_reviewed_app_transcription",
            "third_party_mirror",
        }
        assert all(record.runtime_consumer_ids for record in evidence)
    assault_mirror = next(
        record
        for record in package.source_evidence_catalog.records_for_source_id(assault_rule.source_id)
        if record.authority == "project_authoritative_app_mirror"
    )
    assert assault_mirror.provider_name == "Game Datamissions"
    assert assault_mirror.app_version == "931"
    assert assault_mirror.review_audit_source_observation_sha256 == (
        "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
    )
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p18c_p18d_p18e_transport_source_loader_rejects_schema_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_transports_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    payload = json.loads(raw)
    payload["rules"][1]["section_id"] = "18.05"

    with pytest.raises(
        core_transports_2026_09.CoreTransportsSourceArtifactError,
        match="reviewed identity",
    ):
        core_transports_2026_09.core_transports_source_artifact_from_json_bytes(
            json.dumps(payload).encode()
        )
    with pytest.raises(
        core_transports_2026_09.CoreTransportsSourceArtifactError,
        match="bytes drifted",
    ):
        core_transports_2026_09.validate_core_transports_source_artifact_bytes(raw + b"\n")


def test_p06a_visibility_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_other_concepts_2026_08/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_other_concepts_2026_08.source_package()
    rule = core_other_concepts_2026_08.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (core_other_concepts_2026_08.EXPECTED_ARTIFACT_SHA256)
    assert json.loads(raw) == build_other_concepts_source_payload()
    assert rule.section_id == "06.01"
    assert rule.source_id == core_other_concepts_2026_08.VISIBILITY_SOURCE_ID
    assert rule.transcription_sha256 == core_other_concepts_2026_08.TRANSCRIPTION_SHA256
    assert "imaginary straight line, 1 mm wide" in rule.source_text
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert {record.semantic_execution_status for record in evidence} == {
        "executable_engine_runtime"
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p06b_mortal_wounds_source_artifact_is_pinned_typed_and_executable() -> None:
    package = core_other_concepts_2026_08.source_package()
    rule = core_other_concepts_2026_08.source_rule_record_by_id("mortal-wounds")
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert rule.section_id == "06.02"
    assert rule.source_id == core_other_concepts_2026_08.MORTAL_WOUNDS_SOURCE_ID
    assert rule.transcription_sha256 == (
        core_other_concepts_2026_08.MORTAL_WOUNDS_TRANSCRIPTION_SHA256
    )
    assert "for each of those mortal wounds" in rule.source_text
    assert "If a non‑CHARACTER model in that unit has lost one or more wounds" in (  # noqa: RUF001
        rule.source_text
    )
    assert "Otherwise, if that unit contains one or more non‑CHARACTER models" in (  # noqa: RUF001
        rule.source_text
    )
    assert "one or more CHARACTER models in that unit have lost one or more wounds" in (
        rule.source_text
    )
    assert "Otherwise, you must select one CHARACTER model" in rule.source_text
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert {record.semantic_execution_status for record in evidence} == {
        "executable_engine_runtime"
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert package.evidence_required_source_ids == tuple(
        sorted(
            (
                core_other_concepts_2026_08.VISIBILITY_SOURCE_ID,
                core_other_concepts_2026_08.MORTAL_WOUNDS_SOURCE_ID,
            )
        )
    )


def test_p06_other_concepts_runtime_consumer_ids_resolve() -> None:
    package = core_other_concepts_2026_08.source_package()
    rules = (
        core_other_concepts_2026_08.source_rule_record(),
        core_other_concepts_2026_08.source_rule_record_by_id("mortal-wounds"),
    )
    consumer_ids = {consumer_id for rule in rules for consumer_id in rule.runtime_consumer_ids} | {
        consumer_id
        for evidence in package.source_evidence_catalog.records
        for consumer_id in evidence.runtime_consumer_ids
    }

    for consumer_id in sorted(consumer_ids):
        module_name, separator, qualified_name = consumer_id.partition(":")
        assert separator, consumer_id
        assert module_name, consumer_id
        assert qualified_name, consumer_id
        resolved: object = importlib.import_module(module_name)
        for attribute in qualified_name.split("."):
            resolved = getattr(resolved, attribute)
        assert resolved is not None, consumer_id


def test_p06a_visibility_source_artifact_rejects_text_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_other_concepts_2026_08/artifacts/package.json"
    )
    payload = cast(dict[str, object], json.loads(artifact_path.read_text()))
    rules = cast(list[dict[str, object]], payload["rules"])
    rules[0]["source_text"] = f"{rules[0]['source_text']} altered"
    with pytest.raises(
        core_other_concepts_2026_08.CoreOtherConceptsSourceArtifactError,
        match="reviewed identity",
    ):
        core_other_concepts_2026_08.core_other_concepts_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = artifact_path.read_bytes()
    core_other_concepts_2026_08.validate_core_other_concepts_source_artifact_bytes(raw)
    with pytest.raises(
        core_other_concepts_2026_08.CoreOtherConceptsSourceArtifactError,
        match="artifact bytes drifted",
    ):
        core_other_concepts_2026_08.validate_core_other_concepts_source_artifact_bytes(raw + b"\n")


def test_p09b_fall_back_source_artifact_pins_optional_desperate_escape_sequence() -> None:
    package = core_movement_phase_2026_08.source_package()
    selecting_modes = core_movement_phase_2026_08.source_rule_record_by_id("selecting-modes")
    fall_back = core_movement_phase_2026_08.source_rule_record_by_id("fall-back-move")

    assert selecting_modes.section_id == "09.02.02"
    assert "ordered retreat is not mandatory" in selecting_modes.source_text
    assert "select desperate escape instead" in selecting_modes.source_text
    assert selecting_modes.semantic_execution_status == "partial_engine_runtime"
    assert fall_back.section_id == "09.07"
    assert "Make a hazard roll for each model in your unit" in fall_back.source_text
    assert "If your unit is not battle-shocked" in fall_back.source_text
    assert "make a battle-shock roll for your unit" in fall_back.source_text
    assert fall_back.semantic_execution_status == "executable_engine_runtime"
    assert package.evidence_required_source_ids == tuple(
        sorted(rule.source_id for rule in core_movement_phase_2026_08.source_rule_records())
    )
    assert len(package.source_evidence_catalog.records_for_source_id(fall_back.source_id)) == 2


def test_p09a_move_units_source_artifact_rejects_text_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_movement_phase_2026_08/artifacts/package.json"
    )
    payload = cast(dict[str, object], json.loads(artifact_path.read_text()))
    rules = cast(list[dict[str, object]], payload["rules"])
    rule = rules[0]
    rule["source_text"] = f"{rule['source_text']} altered"
    with pytest.raises(
        core_movement_phase_2026_08.CoreMovementPhaseSourceArtifactError,
        match="reviewed identity",
    ):
        core_movement_phase_2026_08.core_movement_phase_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = artifact_path.read_bytes()
    core_movement_phase_2026_08.validate_core_movement_phase_source_artifact_bytes(raw)
    with pytest.raises(
        core_movement_phase_2026_08.CoreMovementPhaseSourceArtifactError,
        match="artifact bytes drifted",
    ):
        core_movement_phase_2026_08.validate_core_movement_phase_source_artifact_bytes(raw + b"\n")


def test_july_rules_updates_source_catalog_cites_pdfs_and_preserves_identity() -> None:
    source_package = july_rules_updates_2026_07.source_package()
    catalog = source_package.source_catalog
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert len(catalog.documents) == 3
    universal_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in document.title
    )
    event_companion_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in document.title
    )
    app_core_documents = tuple(
        document
        for document in catalog.documents
        if "Warhammer 40,000 App Core Rules" in document.title
    )
    assert len(universal_documents) == 1
    assert len(event_companion_documents) == 1
    assert len(app_core_documents) == 1
    universal_document = universal_documents[0]
    event_companion_document = event_companion_documents[0]
    universal_rules = july_rules_updates_2026_07.universal_rule_records()
    event_rules = july_rules_updates_2026_07.event_companion_rule_records()
    artifact = july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
        _july_rules_update_artifact_path().read_bytes()
    )
    app_core_rules = artifact.app_core_rules_update.rules
    assert {rule.rule_id: rule.behavior_descriptor for rule in universal_rules} == {
        "modifying-a-stratagem-cp-cost": "unnamed_zero_cp_reduces_cost_by_one",
        "stratagem-repeat-and-limit-exceptions": (
            "repeat_or_limit_exception_requires_named_stratagem"
        ),
        "stratagems-that-prevent-targeting": ("protective_targeting_range_is_eighteen_inches"),
        "stratagems-that-add-identical-units": ("identical_unit_replacement_once_per_battle"),
    }
    assert {rule.rule_id: rule.behavior_descriptor for rule in event_rules} == {
        "generating-command-points": "non_core_cp_gain_maximum_one_per_battle_round",
    }
    assert len(app_core_rules) == 16
    assert {rule.rule_id for rule in app_core_rules} == set(
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS
    )
    assert {rule.behavior_descriptor for rule in app_core_rules} >= {
        "fight_on_death_models_wait_for_their_units_single_attack_selection",
        "embarked_return_requires_remaining_transport_capacity",
        "post_roll_profile_changes_split_attack_pools",
        "forced_desperate_escape_tests_all_models_and_battle_shock",
        "objective_consolidation_requires_unengaged_endpoint",
        "objective_control_determined_first_at_phase_and_turn_end",
        "precision_mortals_prioritize_selected_character_group",
        "torrent_excludes_indirect_fire_and_precision",
        "incursion_allows_one_three_dp_detachment",
        "normal_move_limited_to_once_per_unit_per_phase",
        "fly_heavy_uses_horizontal_distance_for_three_inch_limit",
        "infantry_monster_vehicle_hazard_failure_inflicts_one_mortal_wound",
    }
    assert len(july_rules_updates_2026_07.changed_event_layouts()) == 8
    assert all(
        not row.deployment_zones_changed
        for row in july_rules_updates_2026_07.changed_event_layouts()
    )
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256 in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256 in encoded
    universal_source_ids = {source.source_id for source in universal_document.source_texts}
    event_source_texts_by_id = {
        source.source_id: source for source in event_companion_document.source_texts
    }
    assert {rule.source_id for rule in universal_rules} <= universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID not in universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID in event_source_texts_by_id
    assert (
        "maximum of 1CP per battle round"
        in event_source_texts_by_id[
            july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID
        ].raw_text
    )
    assert {rule.source_id for rule in app_core_rules} == {
        source.source_id for source in app_core_documents[0].source_texts
    }
    assert any("Bane of Cowards" in rule.source_text for rule in app_core_rules)
    assert SourceCatalog.from_payload(payload).to_payload() == payload
    assert (
        hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == "5dc3a27783541c49a3ffbd90c4deab9874f364c5bf3a2237133d7af2d6188d59"
    )

    for relative_path, expected_sha256 in (
        (
            july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF,
            july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256,
        ),
        (
            july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF,
            july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256,
        ),
    ):
        assert hashlib.sha256(Path(relative_path).read_bytes()).hexdigest() == expected_sha256


def test_july_app_rows_pin_historical_owner_and_project_authoritative_mirror_evidence() -> None:
    source_package = july_rules_updates_2026_07.source_package()
    evidence_records = source_package.source_evidence_catalog.records
    artifact = july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
        _july_rules_update_artifact_path().read_bytes()
    )
    rules_by_source_id = {rule.source_id: rule for rule in artifact.app_core_rules_update.rules}
    evidence_by_source_id = {
        source_id: source_package.source_evidence_catalog.records_for_source_id(source_id)
        for source_id in rules_by_source_id
    }
    review_context, review_source_observation_by_row_id = _core_rules_review_audit_context()

    assert hashlib.sha256(_july_rules_update_artifact_path().read_bytes()).hexdigest() == (
        july_rules_updates_2026_07.EXPECTED_ARTIFACT_SHA256
    )
    assert july_rules_updates_2026_07.EXPECTED_ARTIFACT_SHA256 == (
        "d87e8847ac50ac483e93792be8af7a19b340873fbe3c9f8b9047d036f14d3249"
    )
    assert july_rules_updates_2026_07.PACKAGE_HASH == (
        "3608f6c6a26dabb2952482d8a47c1a153244af7bbf602a278b7b9d4eb5df3c3d"
    )
    assert len(evidence_records) == 32
    assert len(rules_by_source_id) == len(source_package.evidence_required_source_ids) == 16
    assert set(evidence_by_source_id) == set(rules_by_source_id)
    assert all(len(records) == 2 for records in evidence_by_source_id.values())
    owner_records = tuple(
        record
        for record in evidence_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    mirror_records = tuple(
        record for record in evidence_records if record.evidence_kind == "third_party_mirror"
    )
    assert len(owner_records) == len(mirror_records) == 16
    assert all(record.authority == "unverified_transcription_only" for record in owner_records)
    assert all(record.verification_status == "unverified" for record in owner_records)
    assert all(record.project_authority_policy_id is None for record in owner_records)
    assert all(record.review_audit_id is None for record in owner_records)
    assert all(record.review_audit_row_id is None for record in owner_records)
    assert all(record.review_audit_source_observation_sha256 is None for record in owner_records)
    assert all(record.observed_at is None for record in owner_records)
    assert all(record.source_url is None for record in owner_records)
    assert all(record.authority == "project_authoritative_app_mirror" for record in mirror_records)
    assert all(
        record.project_authority_policy_id == PROJECT_AUTHORITY_POLICY_ID
        for record in mirror_records
    )
    assert review_context == {
        "audit_id": CORE_RULES_REVIEW_AUDIT_ID,
        "observed_at": "2026-08-25T00:00:00-04:00",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "provider_affiliation": "not_affiliated_with_or_endorsed_by_games_workshop",
    }
    assert all(record.review_audit_id == review_context["audit_id"] for record in mirror_records)
    assert all(
        record.review_audit_row_id in review_source_observation_by_row_id
        for record in mirror_records
    )
    assert all(
        record.review_audit_source_observation_sha256
        == review_source_observation_by_row_id[cast(str, record.review_audit_row_id)]
        for record in mirror_records
    )
    assert all(record.observed_at == review_context["observed_at"] for record in mirror_records)
    assert all(
        record.project_authority_policy_id == review_context["project_authority_policy_id"]
        for record in mirror_records
    )
    assert all(record.provider_name == "40k.app" for record in mirror_records)
    assert all(record.official_corroborating_source_ids == () for record in evidence_records)
    assert all(
        record.provider_non_affiliation_recorded
        == (
            review_context["provider_affiliation"]
            == "not_affiliated_with_or_endorsed_by_games_workshop"
        )
        for record in mirror_records
    )
    assert not any(record.provider_non_affiliation_recorded for record in owner_records)
    assert all(
        RuleEvidenceRecord.from_payload(record.to_payload()) == record
        for record in evidence_records
    )
    assert all(
        hashlib.sha256(rules_by_source_id[source_id].source_text.encode()).hexdigest()
        == evidence.transcription_sha256
        for source_id, records in evidence_by_source_id.items()
        for evidence in records
    )

    fight_on_death_source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "05.04.05-fight-on-death"
    ]
    fight_on_death_records = evidence_by_source_id[fight_on_death_source_id]
    assert {record.verification_status for record in fight_on_death_records} == {
        "unverified",
        "authoritative_app_mirror",
    }
    for fight_on_death in fight_on_death_records:
        assert fight_on_death.transcription_sha256 == (
            "d2b9c094f1eda640ccfa76817e741497d960ff5d6015d7d9afa7616e3cd77741"
        )
        assert fight_on_death.load_support_status == "loaded"
        assert fight_on_death.semantic_execution_status == "partial_engine_runtime"
        assert fight_on_death.runtime_consumer_ids == (
            "warhammer40k_core.engine.fight_on_death:restore_model_awaiting_fight_on_death",
            "warhammer40k_core.engine.rule_model_destruction_fight_continuation:"
            "remove_remaining_fight_on_death_models_at_phase_end",
        )

    objective_consolidation_records = evidence_by_source_id[
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS["12.08-objective-consolidation"]
    ]
    objective_consolidation_rule = rules_by_source_id[
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS["12.08-objective-consolidation"]
    ]
    objective_owner = next(
        record
        for record in objective_consolidation_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    objective_mirror = next(
        record
        for record in objective_consolidation_records
        if record.evidence_kind == "third_party_mirror"
    )
    assert objective_consolidation_rule.behavior_descriptor == (
        "objective_consolidation_requires_unengaged_endpoint"
    )
    assert "must be unengaged" in objective_consolidation_rule.source_text
    assert objective_owner.authority == "unverified_transcription_only"
    assert objective_owner.verification_status == "unverified"
    assert objective_mirror.authority == "project_authoritative_app_mirror"
    assert objective_mirror.project_authority_policy_id == PROJECT_AUTHORITY_POLICY_ID
    assert objective_mirror.review_audit_id == CORE_RULES_REVIEW_AUDIT_ID
    assert objective_mirror.review_audit_row_id == ("finding:july-transcription-conflict-12-08")
    assert objective_mirror.review_audit_source_observation_sha256 == (
        "726ce364500c7f1d6b9776651f430ac05ad144a5899877fdbd857128e6cf041c"
    )
    assert objective_mirror.source_url == "https://www.40k.app/rules/12-fight-phase"
    assert objective_mirror.verification_status == "conflict"
    assert {record.verification_status for record in objective_consolidation_records} == {
        "unverified",
        "conflict",
    }
    assert all(
        record.semantic_execution_status == "blocked_by_source_conflict"
        for record in objective_consolidation_records
    )
    assert all(not record.runtime_consumer_ids for record in objective_consolidation_records)
    not_observed_rule_ids = {
        "faq-heavy-fly-horizontal-distance",
        "faq-hazardous-mixed-unit-keywords",
    }
    assert {
        rule_id
        for rule_id in not_observed_rule_ids
        if any(
            record.verification_status == "not_observed_on_mirror"
            for record in evidence_by_source_id[
                july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[rule_id]
            ]
        )
    } == not_observed_rule_ids
    provenance = artifact.app_core_rules_update.transcription_provenance
    assert provenance.provenance_kind == "repository_transcription_without_retained_app_capture"
    assert provenance.authority == "unverified_transcription_only"
    assert provenance.observation_date is provenance.app_version is provenance.source_url is None
    assert provenance.screenshot_sha256 is provenance.source_binary_sha256 is None
    catalog_encoded = json.dumps(source_package.source_catalog.to_payload(), sort_keys=True)
    assert "40k.app" not in catalog_encoded
    assert not any(record.evidence_id in catalog_encoded for record in evidence_records)
    assert "secondary_mirror_only" not in catalog_encoded
    assert "project_authoritative_app_mirror" not in catalog_encoded
    assert not hasattr(july_rules_updates_2026_07, "source_catalog")
    assert not hasattr(july_rules_updates_2026_07, "app_core_rule_evidence_records")


def test_rule_source_package_rejects_provenance_and_grouped_status_gaps() -> None:
    package = july_rules_updates_2026_07.source_package()
    source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "01.02.03-embarked-model-return"
    ]
    records = package.source_evidence_catalog.records_for_source_id(source_id)
    owner = next(
        record for record in records if record.evidence_kind == "owner_supplied_app_transcription"
    )
    mirror = next(record for record in records if record.evidence_kind == "third_party_mirror")

    evidence_catalog = SourceEvidenceCatalog(records=(owner, mirror))
    assert evidence_catalog.records == tuple(
        sorted((owner, mirror), key=lambda record: record.evidence_id)
    )
    assert evidence_catalog.records_for_source_id(source_id) == evidence_catalog.records
    with pytest.raises(RuleEvidenceError, match="evidence IDs must be unique"):
        SourceEvidenceCatalog(records=(owner, owner))
    with pytest.raises(RuleEvidenceError, match="mirror comparison alone is insufficient"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=tuple(
                    record
                    for record in package.source_evidence_catalog.records
                    if record.evidence_id != owner.evidence_id
                )
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )

    contradictory_payload = mirror.to_payload()
    contradictory_payload["semantic_execution_status"] = "unsupported"
    contradictory = RuleEvidenceRecord.from_payload(contradictory_payload)
    with pytest.raises(RuleEvidenceError, match="must agree on load and semantic"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=_replace_evidence_records(package, contradictory)
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )

    mismatched_payload = owner.to_payload()
    mismatched_payload["transcription_sha256"] = "0" * 64
    mismatched_payload["observation_sha256"] = _observation_sha256(mismatched_payload)
    mismatched = RuleEvidenceRecord.from_payload(mismatched_payload)
    with pytest.raises(RuleEvidenceError, match="does not match its source row"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=_replace_evidence_records(package, mismatched)
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )


def test_rule_source_package_requires_exact_evidence_inventory_and_catalog_ownership() -> None:
    package = july_rules_updates_2026_07.source_package()
    source_ids = tuple(sorted(july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS.values()))[:2]
    first_records = package.source_evidence_catalog.records_for_source_id(source_ids[0])
    second_records = package.source_evidence_catalog.records_for_source_id(source_ids[1])

    with pytest.raises(RuleEvidenceError, match="must exactly cover required source IDs"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=first_records),
            evidence_required_source_ids=source_ids,
            source_authority_scope=package.source_authority_scope,
        )
    with pytest.raises(RuleEvidenceError, match="must exactly cover required source IDs"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=first_records + second_records),
            evidence_required_source_ids=(source_ids[0],),
            source_authority_scope=package.source_authority_scope,
        )

    absent_source_id = f"{july_rules_updates_2026_07.SOURCE_PACKAGE_ID}:app-core-rules:absent"
    absent_payload = next(
        record
        for record in first_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    ).to_payload()
    absent_payload["evidence_id"] = "repository-app-core-rules-transcription:absent"
    absent_payload["rule_source_id"] = absent_source_id
    absent_payload["observation_sha256"] = _observation_sha256(absent_payload)
    absent_record = RuleEvidenceRecord.from_payload(absent_payload)
    with pytest.raises(RuleEvidenceError, match="outside its authorized source scope"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=(absent_record,)),
            evidence_required_source_ids=(absent_source_id,),
            source_authority_scope=package.source_authority_scope,
        )


def test_rule_source_package_requires_grouped_conflict_block_equivalence() -> None:
    package = july_rules_updates_2026_07.source_package()
    source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "01.02.03-embarked-model-return"
    ]
    records = package.source_evidence_catalog.records_for_source_id(source_id)
    blocked_records: list[RuleEvidenceRecord] = []
    for record in records:
        payload = record.to_payload()
        payload["semantic_execution_status"] = "blocked_by_source_conflict"
        blocked_records.append(RuleEvidenceRecord.from_payload(payload))

    with pytest.raises(RuleEvidenceError, match="source-conflict evidence and blocked semantic"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=_replace_evidence_records(package, *blocked_records)
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )

    mirror = next(record for record in records if record.evidence_kind == "third_party_mirror")
    unblocked_conflict_payload = mirror.to_payload()
    unblocked_conflict_payload["authority"] = "secondary_mirror_only"
    unblocked_conflict_payload["project_authority_policy_id"] = None
    unblocked_conflict_payload["verification_status"] = "conflict"
    unblocked_conflict_payload["observation_sha256"] = _observation_sha256(
        unblocked_conflict_payload
    )
    with pytest.raises(RuleEvidenceError, match="Conflicting source evidence must block"):
        RuleEvidenceRecord.from_payload(unblocked_conflict_payload)


def test_rule_source_package_rejects_executable_hidden_owner_without_authoritative_evidence() -> (
    None
):
    package = app_core_rules_hidden_2026_08_09.source_package()
    owner = next(
        record
        for record in package.source_evidence_catalog.records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )

    with pytest.raises(
        RuleEvidenceError,
        match="executable or partial semantics require an official App capture or project",
    ):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=(owner,)),
            evidence_required_source_ids=(app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID,),
            source_authority_scope=package.source_authority_scope,
        )


def test_rule_evidence_rejects_mirror_official_authority_and_uncaptured_app_claims() -> None:
    def invalid_record(
        *,
        evidence_kind: RuleEvidenceKind,
        authority: RuleEvidenceAuthority,
        verification_status: RuleVerificationStatus,
        project_authority_policy_id: str | None = None,
        review_audit_id: str | None = None,
        review_audit_row_id: str | None = None,
        review_audit_source_observation_sha256: str | None = None,
        observed_at: str | None = "2026-08-25T12:00:00-04:00",
    ) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id="evidence:test",
            rule_source_id="source:test",
            evidence_kind=evidence_kind,
            authority=authority,
            project_authority_policy_id=project_authority_policy_id,
            review_audit_id=review_audit_id,
            review_audit_row_id=review_audit_row_id,
            review_audit_source_observation_sha256=review_audit_source_observation_sha256,
            provider_name="40k.app",
            source_title="Core Concepts",
            source_platform="Web",
            source_url="https://www.40k.app/rules/01-core-concepts",
            observed_at=observed_at,
            app_version=None,
            app_build=None,
            capture_artifact_path=None,
            capture_sha256=None,
            transcription_sha256="0" * 64,
            official_corroborating_source_ids=(),
            provider_non_affiliation_recorded=True,
            observation_sha256="0" * 64,
            load_support_status="loaded",
            semantic_execution_status="not_certified",
            runtime_consumer_ids=(),
            verification_status=verification_status,
        )

    with pytest.raises(RuleEvidenceError, match="mirror authority classification is invalid"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="official_primary",
            verification_status="mirror_only",
        )

    with pytest.raises(RuleEvidenceError, match="requires its authority policy ID"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="project_authoritative_app_mirror",
            verification_status="authoritative_app_mirror",
        )

    with pytest.raises(RuleEvidenceError, match="App-data version or observation timestamp"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="project_authoritative_app_mirror",
            verification_status="authoritative_app_mirror",
            project_authority_policy_id=PROJECT_AUTHORITY_POLICY_ID,
            review_audit_id=CORE_RULES_REVIEW_AUDIT_ID,
            review_audit_row_id="category:01",
            review_audit_source_observation_sha256=(
                "3668da89d60d6234672f11be41cb08ddca6816354db062b47c4b4adf8ebf2ec5"
            ),
            observed_at=None,
        )

    with pytest.raises(RuleEvidenceError, match="verification_status is unsupported"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="secondary_mirror_only",
            verification_status=cast(RuleVerificationStatus, "official_corroborated"),
        )

    with pytest.raises(RuleEvidenceError, match="version, build, and a hashed retained capture"):
        invalid_record(
            evidence_kind="official_app_capture",
            authority="official_primary",
            verification_status="official_app_captured",
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "review_audit_id",
        "review_audit_row_id",
        "review_audit_source_observation_sha256",
    ],
)
def test_project_authoritative_mirror_requires_complete_retained_audit_link(
    field_name: str,
) -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = cast(dict[str, object], record.to_payload())
    payload[field_name] = None
    payload["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, payload))

    with pytest.raises(RuleEvidenceError, match="maintained App-mirror record"):
        RuleEvidenceRecord.from_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "replacement", "expected_message"),
    [
        ("review_audit_id", "does-not-exist", "audit ID or row ID is not registered"),
        ("review_audit_row_id", "does-not-exist", "audit ID or row ID is not registered"),
        (
            "review_audit_source_observation_sha256",
            "0" * 64,
            "audit reference does not match its registered row",
        ),
    ],
)
def test_project_authoritative_mirror_authenticates_retained_audit_registry_row(
    field_name: str,
    replacement: str,
    expected_message: str,
) -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = cast(dict[str, object], record.to_payload())
    payload[field_name] = replacement
    payload["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, payload))

    with pytest.raises(RuleEvidenceError, match=expected_message):
        RuleEvidenceRecord.from_payload(payload)


def test_superseded_mirror_policy_rejects_new_observation_identity() -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = record.to_payload()
    payload["evidence_id"] = f"{record.evidence_id}:new-observation"
    payload["observed_at"] = "2026-09-02T00:00:00-04:00"
    payload["observation_sha256"] = _observation_sha256(payload)

    with pytest.raises(RuleEvidenceError, match="restricted to its immutable observation"):
        RuleEvidenceRecord.from_payload(payload)


def test_source_authority_registry_is_pinned_typed_and_tamper_evident() -> None:
    raw = Path("src/warhammer40k_core/rules/source_authority_registry.json").read_bytes()

    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256
    registry = load_source_authority_registry_from_json_bytes(raw)
    scope = registry.scope(CORE_RULES_SOURCE_AUTHORITY_SCOPE)
    assert scope.edition == "warhammer_40000_11th"
    assert scope.corpus == "core_rules_categories_01_25"
    assert len(scope.legacy_observations) == 33
    assert len(scope.source_packages) == 10
    with pytest.raises(SourceAuthorityRegistryError, match="drifted from their reviewed pin"):
        load_source_authority_registry_from_json_bytes(raw + b"\n")


def test_maintained_mirror_evidence_accepts_either_provider_with_complete_tuple() -> None:
    existing = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = existing.to_payload()
    payload.update(
        {
            "evidence_id": "game-datamissions-core-rules-data-931:test-rule",
            "project_authority_policy_id": CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
            "review_audit_id": "core-rules-maintained-app-mirrors-2026-09-02",
            "review_audit_row_id": "game-datamissions-core-rules-data-931",
            "review_audit_source_observation_sha256": (
                "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
            ),
            "provider_name": "Game Datamissions",
            "source_title": "Game Datamissions Core Rules Data Changelog",
            "source_url": "https://game-datamissions.com/11th/rules/changelog",
            "observed_at": None,
            "app_version": "931",
        }
    )
    payload["observation_sha256"] = _observation_sha256(payload)

    record = RuleEvidenceRecord.from_payload(payload)

    assert record.provider_name == "Game Datamissions"
    assert record.app_version == "931"
    assert record.observed_at is None
    assert record.project_authority_policy_id == CORE_RULES_MAINTAINED_MIRROR_POLICY_ID

    missing_version = dict(payload)
    missing_version["app_version"] = None
    missing_version["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, missing_version)
    )
    with pytest.raises(RuleEvidenceError, match="App-data version or observation timestamp"):
        RuleEvidenceRecord.from_payload(missing_version)

    legacy_policy = dict(payload)
    legacy_policy["project_authority_policy_id"] = PROJECT_AUTHORITY_POLICY_ID
    legacy_policy["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, legacy_policy)
    )
    with pytest.raises(RuleEvidenceError, match=r"historical 40k\.app-only policy"):
        RuleEvidenceRecord.from_payload(legacy_policy)

    invalid_url = dict(payload)
    invalid_url["source_url"] = "https://game-datamissions.com/11th/rules/../factions"
    invalid_url["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, invalid_url))
    with pytest.raises(RuleEvidenceError, match="canonical HTTPS Core Rules changelog URL"):
        RuleEvidenceRecord.from_payload(invalid_url)


def test_core_rules_source_authority_scope_rejects_faction_rule_source_id() -> None:
    package = july_rules_updates_2026_07.source_package()
    existing_source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "01.02.03-embarked-model-return"
    ]
    existing_records = package.source_evidence_catalog.records_for_source_id(existing_source_id)
    faction_source_id = "faction:chaos-daemons:test-rule"

    owner_payload = next(
        record
        for record in existing_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    ).to_payload()
    owner_payload["evidence_id"] = "repository-app-transcription:faction-test-rule"
    owner_payload["rule_source_id"] = faction_source_id
    owner_payload["observation_sha256"] = _observation_sha256(owner_payload)
    owner = RuleEvidenceRecord.from_payload(owner_payload)

    mirror_payload = next(
        record for record in existing_records if record.evidence_kind == "third_party_mirror"
    ).to_payload()
    mirror_payload.update(
        {
            "evidence_id": "game-datamissions-data-931:faction-test-rule",
            "rule_source_id": faction_source_id,
            "project_authority_policy_id": CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
            "review_audit_id": "core-rules-maintained-app-mirrors-2026-09-02",
            "review_audit_row_id": "game-datamissions-core-rules-data-931",
            "review_audit_source_observation_sha256": (
                "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
            ),
            "provider_name": "Game Datamissions",
            "source_title": "Game Datamissions Core Rules Data Changelog",
            "source_url": "https://game-datamissions.com/11th/rules/changelog",
            "observed_at": None,
            "app_version": "931",
        }
    )
    mirror_payload["observation_sha256"] = _observation_sha256(mirror_payload)
    mirror = RuleEvidenceRecord.from_payload(mirror_payload)

    with pytest.raises(RuleEvidenceError, match="outside its authorized source scope"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=(owner, mirror)),
            evidence_required_source_ids=(faction_source_id,),
            source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
        )


def test_core_rules_source_authority_scope_rejects_strict_subset_inventory() -> None:
    package = july_rules_updates_2026_07.source_package()
    retained_source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "01.02.03-embarked-model-return"
    ]
    retained_records = package.source_evidence_catalog.records_for_source_id(retained_source_id)

    with pytest.raises(RuleEvidenceError, match="omits a rule source ID"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(records=retained_records),
            evidence_required_source_ids=(retained_source_id,),
            source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
        )


@pytest.mark.stubbed
def test_source_evidence_catalog_rejects_co_versioned_mirror_disagreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )

    class _StubbedAuthorityRegistry:
        def authorize_audit_reference(self, **_: object) -> SourceAuthorityScope:
            return CORE_RULES_SOURCE_AUTHORITY_SCOPE

    monkeypatch.setattr(
        source_evidence_module,
        "source_authority_registry",
        _StubbedAuthorityRegistry,
    )
    forty_k_payload = existing.to_payload()
    forty_k_payload.update(
        {
            "evidence_id": "40k-app-data-931:test-rule",
            "project_authority_policy_id": CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
            "app_version": "931",
        }
    )
    forty_k_payload["observation_sha256"] = _observation_sha256(forty_k_payload)
    forty_k = RuleEvidenceRecord.from_payload(forty_k_payload)

    game_datamissions_payload = dict(forty_k_payload)
    game_datamissions_payload.update(
        {
            "evidence_id": "game-datamissions-data-931:test-rule",
            "provider_name": "Game Datamissions",
            "source_title": "Game Datamissions Core Rules Data Changelog",
            "source_url": "https://game-datamissions.com/11th/rules/changelog",
            "review_audit_row_id": "game-datamissions-core-rules-data-931",
            "review_audit_source_observation_sha256": (
                "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
            ),
        }
    )
    game_datamissions_payload["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, game_datamissions_payload)
    )
    matching_game_datamissions = RuleEvidenceRecord.from_payload(game_datamissions_payload)

    catalog = SourceEvidenceCatalog(records=(forty_k, matching_game_datamissions))
    assert {record.provider_name for record in catalog.records} == {
        "40k.app",
        "Game Datamissions",
    }

    disagreeing_payload = dict(game_datamissions_payload)
    disagreeing_payload["transcription_sha256"] = "0" * 64
    disagreeing_payload["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, disagreeing_payload)
    )
    disagreeing_game_datamissions = RuleEvidenceRecord.from_payload(disagreeing_payload)
    with pytest.raises(
        RuleEvidenceError,
        match="Co-versioned maintained App mirrors disagree",
    ):
        SourceEvidenceCatalog(records=(forty_k, disagreeing_game_datamissions))


def test_rule_evidence_official_capture_requires_authenticated_retained_bytes() -> None:
    capture_content = b"retained official App capture"
    payload: RuleEvidencePayload = {
        "evidence_id": "evidence:official-app-capture",
        "rule_source_id": "source:official-app-rule",
        "evidence_kind": "official_app_capture",
        "authority": "official_primary",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "Games Workshop",
        "source_title": "Warhammer 40,000 App Core Rules",
        "source_platform": "Warhammer 40,000 App",
        "source_url": None,
        "observed_at": "2026-08-25T12:00:00-04:00",
        "app_version": "11.0.0",
        "app_build": "test-build",
        "capture_artifact_path": "docs/source_rules/app_captures/core-rules.bin",
        "capture_sha256": hashlib.sha256(capture_content).hexdigest(),
        "transcription_sha256": hashlib.sha256(b"captured official rule text").hexdigest(),
        "official_corroborating_source_ids": [],
        "verification_status": "official_app_captured",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "not_certified",
        "runtime_consumer_ids": [],
    }
    observation_payload = dict(payload)
    observation_payload["observation_sha256"] = ""
    observation_payload["load_support_status"] = "not_loaded"
    observation_payload["semantic_execution_status"] = "not_certified"
    observation_payload["runtime_consumer_ids"] = []
    payload["observation_sha256"] = hashlib.sha256(
        json.dumps(observation_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    record = RuleEvidenceRecord.from_payload(payload, capture_content=capture_content)
    assert (
        RuleEvidenceRecord.from_payload(record.to_payload(), capture_content=capture_content)
        == record
    )

    missing_timestamp = dict(payload)
    missing_timestamp["observed_at"] = None
    missing_timestamp["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, missing_timestamp)
    )
    with pytest.raises(RuleEvidenceError, match="requires the Games Workshop App"):
        RuleEvidenceRecord.from_payload(missing_timestamp, capture_content=capture_content)

    with pytest.raises(RuleEvidenceError, match="retained capture bytes"):
        RuleEvidenceRecord.from_payload(payload)
    with pytest.raises(RuleEvidenceError, match="retained capture bytes"):
        RuleEvidenceRecord.from_payload(payload, capture_content=b"different capture")

    mirror_claim = dict(payload)
    mirror_claim["provider_name"] = "40k.app"
    mirror_claim["source_platform"] = "Web"
    mirror_claim["source_url"] = "https://www.40k.app/rules/01-core-concepts"
    with pytest.raises(RuleEvidenceError, match="requires the Games Workshop App"):
        RuleEvidenceRecord.from_payload(mirror_claim, capture_content=capture_content)

    traversal_claim = dict(payload)
    traversal_claim["capture_artifact_path"] = "../capture.bin"
    with pytest.raises(RuleEvidenceError, match="normalized relative POSIX path"):
        RuleEvidenceRecord.from_payload(traversal_claim, capture_content=capture_content)
    for invalid_path in ("C:/escape.bin", r"safe\..\escape.bin"):
        platform_escape_claim = dict(payload)
        platform_escape_claim["capture_artifact_path"] = invalid_path
        with pytest.raises(RuleEvidenceError, match="normalized relative POSIX path"):
            RuleEvidenceRecord.from_payload(
                platform_escape_claim,
                capture_content=capture_content,
            )

    unknown_field_claim = dict(payload)
    unknown_field_claim["unexpected"] = True
    with pytest.raises(RuleEvidenceError, match="payload fields drifted"):
        RuleEvidenceRecord.from_payload(unknown_field_claim, capture_content=capture_content)

    invalid_list_claim = dict(payload)
    invalid_list_claim["runtime_consumer_ids"] = "not-a-list"
    with pytest.raises(RuleEvidenceError, match="runtime_consumer_ids must be a list"):
        RuleEvidenceRecord.from_payload(invalid_list_claim, capture_content=capture_content)

    mirror_payload = next(
        record
        for record in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if record.evidence_kind == "third_party_mirror"
        and record.verification_status == "authoritative_app_mirror"
    ).to_payload()
    mislabeled_mirror = dict(mirror_payload)
    mislabeled_mirror["provider_name"] = "Games Workshop"
    mislabeled_mirror["source_platform"] = "Warhammer 40,000 App"
    with pytest.raises(RuleEvidenceError, match="maintained App-mirror record"):
        RuleEvidenceRecord.from_payload(mislabeled_mirror)
    for invalid_url in (
        "https://www.40k.app/rulesevil",
        "https://www.40k.app/rules/../evil",
        "https://www.40k.app/rules//evil",
        "https://www.40k.app/rules/%2e%2e/evil",
        "https://www.40k.app/rules/evil\nsuffix",
        "https://www.40k.app/rules/evil\rsuffix",
        "https://www.40k.app/rules/evil\tsuffix",
    ):
        invalid_mirror_url = dict(mirror_payload)
        invalid_mirror_url["source_url"] = invalid_url
        with pytest.raises(RuleEvidenceError, match="canonical HTTPS rules URL"):
            RuleEvidenceRecord.from_payload(invalid_mirror_url)
    false_conflict_claim = dict(mirror_payload)
    false_conflict_claim["semantic_execution_status"] = "blocked_by_source_conflict"
    false_conflict_record = RuleEvidenceRecord.from_payload(false_conflict_claim)
    package = july_rules_updates_2026_07.source_package()
    with pytest.raises(RuleEvidenceError, match="must agree on load and semantic"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=_replace_evidence_records(package, false_conflict_record)
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )


def test_app_hidden_retains_historical_owner_and_authoritative_mirror_evidence() -> None:
    payload = _app_hidden_transcription_payload()
    raw = _app_hidden_transcription_artifact_path().read_bytes()
    artifact = app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
        raw
    )
    source_package = app_core_rules_hidden_2026_08_09.source_package()
    catalog = source_package.source_catalog
    catalog_payload = catalog.to_payload()
    source_capture = cast(dict[str, object], payload["source_capture"])
    evidence_records = source_package.source_evidence_catalog.records_for_source_id(
        app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID
    )
    owner = next(
        record
        for record in evidence_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    mirror = next(
        record for record in evidence_records if record.evidence_kind == "third_party_mirror"
    )
    review_context, review_source_observation_by_row_id = _core_rules_review_audit_context()

    assert hashlib.sha256(raw).hexdigest() == (
        app_core_rules_hidden_2026_08_09.EXPECTED_ARTIFACT_SHA256
    )
    assert app_core_rules_hidden_2026_08_09.EXPECTED_ARTIFACT_SHA256 == (
        "a63c25996e95c03f0953fc3841e47228d6d9533cdb4ef34a8e2324bc29d0f902"
    )
    assert app_core_rules_hidden_2026_08_09.PACKAGE_HASH == (
        "b65d4058463a2825b8808d1d7dfff2e82c8c87641f4241bf600e1bb82a866058"
    )
    assert hashlib.sha256(artifact.rule.source_text.encode()).hexdigest() == (
        app_core_rules_hidden_2026_08_09.TRANSCRIPTION_SHA256
    )
    assert artifact.source_capture.observation_date == "2026-08-09"
    assert artifact.source_capture.provenance_kind == "owner_supplied_app_transcription"
    assert artifact.source_capture.availability == (
        "transcription_only_no_source_url_app_version_or_binary"
    )
    assert set(source_capture) == {
        "availability",
        "observation_date",
        "provenance_kind",
        "source_platform",
        "source_title",
        "supplied_by",
    }
    assert "supersession" not in payload
    assert artifact.source_relationship.official_pdf_source_package_id == (
        core_rules.SOURCE_PACKAGE_ID
    )
    assert artifact.source_relationship.official_pdf_rule_reference == "13.09 Hidden"
    assert artifact.source_relationship.comparison_scope == (
        "hidden_terrain_area_feature_eligibility"
    )
    assert artifact.source_relationship.relationship_status == (
        "maintained_app_wording_supersedes_pdf_by_project_source_policy"
    )
    assert len(evidence_records) == 2
    assert owner.authority == "unverified_transcription_only"
    assert owner.project_authority_policy_id is None
    assert owner.review_audit_id is None
    assert owner.review_audit_row_id is None
    assert owner.review_audit_source_observation_sha256 is None
    assert owner.observed_at is None
    assert owner.verification_status == "unverified"
    assert not owner.provider_non_affiliation_recorded
    assert owner.source_url is owner.app_version is owner.app_build is None
    assert owner.capture_artifact_path is owner.capture_sha256 is None
    assert mirror.authority == "project_authoritative_app_mirror"
    assert (
        mirror.project_authority_policy_id
        == review_context["project_authority_policy_id"]
        == PROJECT_AUTHORITY_POLICY_ID
    )
    assert mirror.review_audit_id == review_context["audit_id"] == CORE_RULES_REVIEW_AUDIT_ID
    assert mirror.review_audit_row_id == "finding:hidden-unverified-source-13-09"
    assert (
        mirror.review_audit_source_observation_sha256
        == (review_source_observation_by_row_id[mirror.review_audit_row_id])
    )
    assert mirror.review_audit_source_observation_sha256 == (
        "62d982be96a81f69059f11def8a0ee75e6ae64f2dfd6f7132e4913140e9aaaf4"
    )
    assert mirror.observed_at == review_context["observed_at"]
    assert mirror.verification_status == "authoritative_app_mirror"
    assert mirror.provider_name == "40k.app"
    assert mirror.provider_non_affiliation_recorded == (
        review_context["provider_affiliation"]
        == "not_affiliated_with_or_endorsed_by_games_workshop"
    )
    assert mirror.source_url == "https://www.40k.app/rules/13-terrain"
    assert all(record.load_support_status == "loaded" for record in evidence_records)
    assert all(
        record.semantic_execution_status == "executable_engine_runtime"
        for record in evidence_records
    )
    assert {record.runtime_consumer_ids for record in evidence_records} == {
        (
            "warhammer40k_core.engine.shooting_targets:unit_has_line_of_sight_to_target",
            "warhammer40k_core.engine.terrain_hidden:terrain_hidden_model_ids",
        )
    }
    assert all(
        RuleEvidenceRecord.from_payload(record.to_payload()) == record
        for record in evidence_records
    )
    assert len(catalog.documents) == 1
    assert catalog.catalog_version.source_date == "2026-08-09"
    assert "project-authoritative 40k.app App mirror" in catalog.documents[0].title
    assert (
        catalog.source_text_by_id(app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID).raw_text
        == artifact.rule.source_text
    )
    provenance = catalog.source_text_by_id(
        f"{app_core_rules_hidden_2026_08_09.SOURCE_PACKAGE_ID}:manifest:provenance"
    )
    assert (
        "historical transcription remains explicitly unverified on its own" in provenance.raw_text
    )
    assert PROJECT_AUTHORITY_POLICY_ID in provenance.raw_text
    assert "non-affiliated hosting provider" in provenance.raw_text
    assert SourceCatalog.from_payload(catalog_payload).to_payload() == catalog_payload
    assert not hasattr(app_core_rules_hidden_2026_08_09, "source_catalog")


def test_app_hidden_transcription_artifact_rejects_unrecorded_source_metadata() -> None:
    payload = _app_hidden_transcription_payload()
    source_capture = cast(dict[str, object], payload["source_capture"])
    source_capture["source_url"] = "https://example.invalid/unrecorded"

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="artifact is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_app_source_artifacts_reject_project_authority_policy_id_drift() -> None:
    july_payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], july_payload["app_core_rules_update"])
    contexts = cast(list[dict[str, object]], app_update["evidence_contexts"])
    mirror_context = next(
        context for context in contexts if context["evidence_kind"] == "third_party_mirror"
    )
    mirror_context["project_authority_policy_id"] = "core-rules-source-policy:wrong"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="mirror provenance drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(july_payload, sort_keys=True).encode()
        )

    hidden_payload = _app_hidden_transcription_payload()
    hidden_evidence = cast(list[dict[str, object]], hidden_payload["evidence_records"])
    hidden_mirror = next(
        record for record in hidden_evidence if record["evidence_kind"] == "third_party_mirror"
    )
    hidden_mirror["project_authority_policy_id"] = "core-rules-source-policy:wrong"
    hidden_mirror["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, hidden_mirror)
    )

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="transcription evidence is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(hidden_payload, sort_keys=True).encode()
        )


def test_app_source_artifacts_reject_retained_audit_link_drift() -> None:
    july_package = july_rules_updates_2026_07.source_package()
    july_payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], july_payload["app_core_rules_update"])
    july_evidence = cast(list[dict[str, object]], app_update["evidence_records"])
    july_mirror_artifact = next(
        record
        for record in july_evidence
        if record["evidence_context_id"] == "40k-app-comparison-2026-08-25"
    )
    july_mirror_record = next(
        record
        for record in july_package.source_evidence_catalog.records
        if record.evidence_id == july_mirror_artifact["evidence_id"]
    )
    july_mirror_artifact["review_audit_row_id"] = "category:02"
    july_mirror_payload = july_mirror_record.to_payload()
    july_mirror_payload["review_audit_row_id"] = "category:02"
    july_mirror_artifact["observation_sha256"] = _observation_sha256(july_mirror_payload)

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="evidence record is invalid",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(july_payload, sort_keys=True).encode()
        )

    hidden_package = app_core_rules_hidden_2026_08_09.source_package()
    hidden_payload = _app_hidden_transcription_payload()
    hidden_evidence = cast(list[dict[str, object]], hidden_payload["evidence_records"])
    hidden_mirror_artifact = next(
        record for record in hidden_evidence if record["evidence_kind"] == "third_party_mirror"
    )
    hidden_mirror_record = next(
        record
        for record in hidden_package.source_evidence_catalog.records
        if record.evidence_id == hidden_mirror_artifact["evidence_id"]
    )
    hidden_mirror_artifact["review_audit_row_id"] = "category:13"
    hidden_mirror_payload = hidden_mirror_record.to_payload()
    hidden_mirror_payload["review_audit_row_id"] = "category:13"
    hidden_mirror_artifact["observation_sha256"] = _observation_sha256(hidden_mirror_payload)

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="transcription evidence is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(hidden_payload, sort_keys=True).encode()
        )


def test_app_hidden_transcription_artifact_rejects_text_and_byte_drift() -> None:
    payload = _app_hidden_transcription_payload()
    rule = cast(dict[str, object], payload["rule"])
    rule["source_text"] = f"{rule['source_text']} altered"

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="source-text hash is stale",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = _app_hidden_transcription_artifact_path().read_bytes()
    app_core_rules_hidden_2026_08_09.validate_hidden_transcription_artifact_bytes(raw)
    semantically_equivalent_bytes = json.dumps(
        _app_hidden_transcription_payload(), sort_keys=True
    ).encode()
    assert semantically_equivalent_bytes != raw
    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="artifact bytes drifted",
    ):
        app_core_rules_hidden_2026_08_09.validate_hidden_transcription_artifact_bytes(
            semantically_equivalent_bytes
        )


def test_july_rules_updates_artifact_rejects_unknown_fields() -> None:
    payload = _july_rules_update_payload()
    payload["unexpected"] = True

    with pytest.raises(july_rules_updates_2026_07.JulyRulesUpdateArtifactError):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_unknown_app_evidence_reference() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    evidence_ids = cast(list[str], rules[0]["evidence_ids"])
    rules[0]["evidence_ids"] = [evidence_ids[0], "40k-app:missing-evidence"]

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="unknown evidence",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_cross_rule_evidence_links() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    first_evidence_ids = cast(list[str], rules[0]["evidence_ids"])
    second_evidence_ids = cast(list[str], rules[1]["evidence_ids"])
    first_mirror_id = next(
        evidence_id for evidence_id in first_evidence_ids if evidence_id.startswith("40k-app-")
    )
    second_mirror_id = next(
        evidence_id for evidence_id in second_evidence_ids if evidence_id.startswith("40k-app-")
    )
    first_evidence_ids[first_evidence_ids.index(first_mirror_id)] = second_mirror_id
    second_evidence_ids[second_evidence_ids.index(second_mirror_id)] = first_mirror_id

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="evidence links cross source-rule identities",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_transcription_and_raw_byte_drift() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    rules[0]["source_text"] = f"{rules[0]['source_text']} altered"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="transcription hash is stale",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = _july_rules_update_artifact_path().read_bytes()
    july_rules_updates_2026_07.validate_july_rules_update_artifact_bytes(raw)
    semantically_equivalent_bytes = json.dumps(
        _july_rules_update_payload(), sort_keys=True
    ).encode()
    assert semantically_equivalent_bytes != raw
    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="artifact bytes drifted",
    ):
        july_rules_updates_2026_07.validate_july_rules_update_artifact_bytes(
            semantically_equivalent_bytes
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("rule_id", "unexpected-global-rule"),
        ("behavior_descriptor", "unexpected_global_behavior"),
    ],
)
def test_july_rules_updates_artifact_rejects_universal_rule_identity_drift(
    field_name: str,
    replacement: str,
) -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)[field_name] = replacement

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update rule identity inventory drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_universal_rule_source_suffix_drift() -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)["source_id"] = (
        "gw-11e-rules-and-event-updates-2026-07-22:universal-rules:wrong-rule"
    )

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update source identity drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    "field_name",
    ["document_id", "source_version", "source_url", "local_pdf"],
)
def test_july_rules_updates_artifact_rejects_universal_document_metadata_drift(
    field_name: str,
) -> None:
    payload = _july_rules_update_payload()
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    universal_update[field_name] = "unexpected"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update document metadata drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_eleventh_source_package_identity_payloads_are_json_safe() -> None:
    mission_package = chapter_approved_2026_27.source_package_definition()
    mission_payload = mission_package.to_payload()
    ability_identity = core_abilities.source_package_identity_payload()
    stratagem_identity = core_stratagems.source_package_identity_payload()
    payload = {
        "mission_package": mission_payload,
        "ability_identity": ability_identity,
        "stratagem_identity": stratagem_identity,
    }
    encoded = json.dumps(payload, sort_keys=True)

    assert mission_payload["edition_id"] == "warhammer_40000_11th"
    assert ability_identity["edition_id"] == "warhammer_40000_11th"
    assert stratagem_identity["edition_id"] == "warhammer_40000_11th"
    assert mission_payload["source_package_id"].startswith("gw-11e-")
    assert ability_identity["source_package_id"].startswith("gw-11e-")
    assert stratagem_identity["source_package_id"].startswith("gw-11e-")
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionSourcePackageDefinition.from_payload(mission_payload).to_payload() == (
        mission_payload
    )


def test_p15df_core_stratagem_app_source_is_hash_pinned_and_truthful() -> None:
    raw = _core_stratagem_app_source_artifact_path().read_bytes()
    source_package = core_stratagems_2026_08.source_package()
    rules = core_stratagems_2026_08.source_rule_records()
    rules_by_id = {rule.rule_id: rule for rule in rules}
    evidence_by_source_id = {
        source_id: source_package.source_evidence_catalog.records_for_source_id(source_id)
        for source_id in source_package.evidence_required_source_ids
    }
    catalog_payload = source_package.source_catalog.to_payload()

    assert hashlib.sha256(raw).hexdigest() == (core_stratagems_2026_08.EXPECTED_ARTIFACT_SHA256)
    assert core_stratagems_2026_08.PACKAGE_HASH == (
        "f373b194b005a56b5caa0f52f540e26ddee45655ac9e89e8f8e85d4d642616d7"
    )
    assert [(rule.section_id, rule.title) for rule in rules] == [
        ("15.05", "Crushing Impact"),
        ("15.06", "Explosives"),
        ("15.07", "Rapid Ingress"),
        ("15.08", "Fire Overwatch"),
        ("15.09", "Snap Shooting"),
        ("FAQ", "Insane Bravery"),
    ]
    assert core_stratagems_2026_08.RULE_SOURCE_IDS == {
        "crushing-impact": "gw-11e-core-stratagems:core:crushing-impact",
        "explosives": "gw-11e-core-stratagems:core:explosives",
        "rapid-ingress": "gw-11e-core-stratagems:core:rapid-ingress",
        "fire-overwatch": "gw-11e-core-stratagems:core:fire-overwatch",
        "snap-shooting": "gw-11e-core-stratagems:rule:snap-shooting",
        "insane-bravery": "gw-11e-core-stratagems:core:insane-bravery",
    }
    assert {rule.rule_id: rule.runtime_rule_id for rule in rules} == {
        "crushing-impact": "core:crushing-impact",
        "explosives": "core:explosives",
        "rapid-ingress": "core:rapid-ingress",
        "fire-overwatch": "core:fire-overwatch",
        "snap-shooting": "core:snap-shooting",
        "insane-bravery": "core:insane-bravery",
    }
    assert "MONSTER/VEHICLE" in rules_by_id["crushing-impact"].source_text
    assert "T characteristic" in rules_by_id["crushing-impact"].source_text
    assert "EXPLOSIVES/GRENADES model" in rules_by_id["explosives"].source_text
    assert "excluding AIRCRAFT" in rules_by_id["rapid-ingress"].source_text
    assert "shoots using Snap Shooting" in rules_by_id["fire-overwatch"].source_text
    assert "unmodified hit roll of 6" in rules_by_id["snap-shooting"].source_text
    assert "not eligible to start an action" in rules_by_id["snap-shooting"].source_text
    assert rules_by_id["insane-bravery"].source_text == (
        "Can I use the Insane Bravery stratagem on a battle-shocked unit?\n"
        "No, as a unit's controlling player cannot target that unit with stratagems (01.07)."
    )
    assert all(
        hashlib.sha256(rule.source_text.encode()).hexdigest()
        == core_stratagems_2026_08.TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]
        == rule.transcription_sha256
        for rule in rules
    )
    assert all(
        rule.source_observation_sha256
        == core_stratagems_2026_08.SOURCE_OBSERVATION_SHA256_BY_RULE_ID[rule.rule_id]
        for rule in rules
    )
    assert {rule.rule_id: rule.semantic_execution_status for rule in rules} == {
        "crushing-impact": "partial_engine_runtime",
        "explosives": "partial_engine_runtime",
        "rapid-ingress": "partial_engine_runtime",
        "fire-overwatch": "partial_engine_runtime",
        "snap-shooting": "partial_engine_runtime",
        "insane-bravery": "executable_engine_runtime",
    }
    assert all(rule.load_support_status == "loaded" for rule in rules)
    assert all(rule.runtime_consumer_ids for rule in rules)

    review_context, review_source_observation_by_row_id = _core_rules_review_audit_context()
    maintained_audit = cast(
        dict[str, object],
        json.loads(CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH.read_text(encoding="utf-8")),
    )
    maintained_sources = cast(list[dict[str, object]], maintained_audit["observations"])
    maintained_game_datamissions = next(
        row
        for row in maintained_sources
        if row["observation_id"] == "game-datamissions-core-rules-data-931"
    )
    assert len(evidence_by_source_id) == len(rules) == 6
    assert all(len(records) == 2 for records in evidence_by_source_id.values())
    for rule in rules:
        records = evidence_by_source_id[rule.source_id]
        project_review = next(
            record
            for record in records
            if record.evidence_kind == "project_reviewed_app_transcription"
        )
        mirror = next(record for record in records if record.evidence_kind == "third_party_mirror")
        assert project_review.evidence_kind == "project_reviewed_app_transcription"
        assert project_review.authority == "unverified_transcription_only"
        assert project_review.provider_name == "CORE V2 Source Review"
        assert project_review.source_url is project_review.observed_at is None
        assert project_review.verification_status == "unverified"
        assert mirror.evidence_kind == "third_party_mirror"
        assert mirror.authority == "project_authoritative_app_mirror"
        if rule.rule_id == "insane-bravery":
            assert mirror.project_authority_policy_id == CORE_RULES_MAINTAINED_MIRROR_POLICY_ID
            assert mirror.review_audit_id == maintained_audit["audit_id"]
            assert mirror.review_audit_row_id == maintained_game_datamissions["observation_id"]
            assert (
                mirror.review_audit_source_observation_sha256
                == (maintained_game_datamissions["source_observation_sha256"])
            )
            assert mirror.source_url == "https://game-datamissions.com/11th/rules/changelog"
            assert mirror.observed_at is None
            assert mirror.app_version == "931"
            assert mirror.provider_name == "Game Datamissions"
        else:
            assert mirror.project_authority_policy_id == PROJECT_AUTHORITY_POLICY_ID
            assert mirror.review_audit_id == review_context["audit_id"]
            assert mirror.source_url == "https://www.40k.app/rules/15-stratagems"
            assert mirror.observed_at == "2026-08-26T11:15:23-04:00"
            assert mirror.review_audit_row_id is not None
            assert (
                mirror.review_audit_source_observation_sha256
                == (review_source_observation_by_row_id[mirror.review_audit_row_id])
            )
        assert mirror.provider_non_affiliation_recorded
        assert mirror.verification_status == "authoritative_app_mirror"
        assert mirror.observation_sha256 == rule.source_observation_sha256
        assert all(
            record.transcription_sha256 == rule.transcription_sha256
            and record.load_support_status == rule.load_support_status
            and record.semantic_execution_status == rule.semantic_execution_status
            and record.runtime_consumer_ids == rule.runtime_consumer_ids
            and RuleEvidenceRecord.from_payload(record.to_payload()) == record
            for record in (project_review, mirror)
        )

    anomaly = core_stratagems_2026_08.numbering_anomalies()[0]
    assert anomaly.section_id == "12.01"
    assert anomaly.stale_section_id == "15.06"
    assert anomaly.resolved_section_id == "15.05"
    assert anomaly.resolved_source_id == rules_by_id["crushing-impact"].source_id
    assert anomaly.resolution_basis == "stable_title_and_complete_operative_text"
    assert anomaly.source_text == (
        "Because both RED**** units made charge moves this turn, they are both Fights First "
        "units this phase and are both eligible to make pile-in moves, even though the MONSTER "
        "is unengaged as it destroyed its charge target in the Charge phase using the Crushing "
        "Impact stratagem (15.06)."
    )
    assert hashlib.sha256(anomaly.source_text.encode()).hexdigest() == (
        anomaly.transcription_sha256
    )
    assert anomaly.transcription_sha256 == (
        core_stratagems_2026_08.EXPECTED_ANOMALY_TRANSCRIPTION_SHA256
    )
    assert anomaly.source_observation_sha256 == (
        core_stratagems_2026_08.EXPECTED_ANOMALY_OBSERVATION_SHA256
    )
    assert (
        anomaly.review_audit_source_observation_sha256
        == (review_source_observation_by_row_id["category:12"])
    )
    assert SourceCatalog.from_payload(catalog_payload).to_payload() == catalog_payload
    assert len(source_package.source_catalog.documents) == 2
    assert source_package.source_catalog.ruleset_bundles[0].source_document_ids == tuple(
        document.document_id for document in source_package.source_catalog.documents
    )


@pytest.mark.parametrize(
    ("target", "field_name", "replacement"),
    [
        ("rule", "section_id", "15.06"),
        ("rule", "source_id", "gw-11e-core-stratagems:core:wrong"),
        ("rule", "source_text", "stale source text"),
        ("mirror", "source_url", "https://example.invalid/rules/15-stratagems"),
        ("faq_document", "app_version", "930"),
        ("insane_rule", "restrictions_text", "stale FAQ answer"),
        ("faq_mirror", "source_url", "https://example.invalid/changelog"),
        ("rule", "semantic_execution_status", "executable_engine_runtime"),
        ("anomaly", "resolved_section_id", "15.06"),
    ],
)
def test_p15df_core_stratagem_app_source_rejects_identity_evidence_and_status_drift(
    target: str,
    field_name: str,
    replacement: str,
) -> None:
    payload = _core_stratagem_app_source_payload()
    rules = cast(list[dict[str, object]], payload["rules"])
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    anomalies = cast(list[dict[str, object]], payload["numbering_anomalies"])
    faq_source_document = cast(dict[str, object], payload["faq_source_document"])
    if target == "rule":
        rules[0][field_name] = replacement
    elif target == "mirror":
        mirror = next(
            record
            for record in evidence
            if record["evidence_id"] == "40k-app-core-stratagems-2026-08-26:crushing-impact"
        )
        mirror[field_name] = replacement
    elif target == "faq_document":
        faq_source_document[field_name] = replacement
    elif target == "insane_rule":
        next(rule for rule in rules if rule["rule_id"] == "insane-bravery")[field_name] = (
            replacement
        )
    elif target == "faq_mirror":
        faq_mirror = next(
            record
            for record in evidence
            if record["evidence_id"] == "game-datamissions-core-rules-data-931:insane-bravery"
        )
        faq_mirror[field_name] = replacement
    else:
        anomalies[0][field_name] = replacement

    with pytest.raises(core_stratagems_2026_08.CoreStratagemAppSourceArtifactError):
        core_stratagems_2026_08.core_stratagem_app_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_p15df_core_stratagem_app_source_rejects_raw_byte_drift() -> None:
    raw = _core_stratagem_app_source_artifact_path().read_bytes()
    core_stratagems_2026_08.validate_core_stratagem_app_source_artifact_bytes(raw)

    with pytest.raises(
        core_stratagems_2026_08.CoreStratagemAppSourceArtifactError,
        match="artifact bytes drifted",
    ):
        core_stratagems_2026_08.validate_core_stratagem_app_source_artifact_bytes(raw + b"\n")


def test_p15df_core_stratagem_app_source_rejects_unknown_evidence_id_as_typed_error() -> None:
    payload = _core_stratagem_app_source_payload()
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    record = next(
        value
        for value in evidence
        if value["evidence_id"] == "core-v2-p15d-source-review:crushing-impact"
    )
    renamed_id = "core-v2-p15d-source-review:unknown"
    source_record = next(
        value
        for value in core_stratagems_2026_08.source_evidence_records()
        if value.evidence_id == record["evidence_id"]
    )
    source_record_payload = source_record.to_payload()
    source_record_payload["evidence_id"] = renamed_id
    source_record_payload["observation_sha256"] = _observation_sha256(source_record_payload)
    record["evidence_id"] = renamed_id
    record["observation_sha256"] = source_record_payload["observation_sha256"]

    with pytest.raises(
        core_stratagems_2026_08.CoreStratagemAppSourceArtifactError,
        match="evidence inventory drifted",
    ):
        core_stratagems_2026_08.core_stratagem_app_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_p08ab_command_phase_source_is_ordered_hash_pinned_and_truthful() -> None:
    raw = _core_command_phase_source_artifact_path().read_bytes()
    artifact_payload = _core_command_phase_source_payload()
    source_document = cast(dict[str, object], artifact_payload["source_document"])
    search_index_payload = cast(dict[str, object], artifact_payload["search_index_observation"])
    source_package = core_command_phase_2026_08.source_package()
    search_index_observation = core_command_phase_2026_08.search_index_observation()
    rules = core_command_phase_2026_08.source_rule_records()
    rules_by_id = {rule.rule_id: rule for rule in rules}

    assert hashlib.sha256(raw).hexdigest() == (core_command_phase_2026_08.EXPECTED_ARTIFACT_SHA256)
    assert core_command_phase_2026_08.PACKAGE_HASH == (
        "8785dda65406ce76add419f29263be499239122e1330941ab55a1dc3e6f10127"
    )
    assert [(rule.section_id, rule.display_order, rule.section_heading) for rule in rules] == [
        ("08.01", 1, "START OF COMMAND PHASE"),
        ("08.02", 2, "GAIN CORE CP"),
        ("08.03", 3, "BATTLE-SHOCK"),
    ]
    assert core_command_phase_2026_08.RULE_SOURCE_IDS == {
        "start-of-command-phase": ("gw-11e-core-rules:command-phase:start-of-command-phase"),
        "gain-core-cp": "gw-11e-core-rules:command-phase:gain-core-cp",
        "battle-shock": "gw-11e-core-rules:command-phase:battle-shock",
    }
    assert rules_by_id["start-of-command-phase"].source_id == (
        core_command_phase_2026_08.START_OF_COMMAND_PHASE_SOURCE_ID
    )
    assert rules_by_id["gain-core-cp"].source_id == (
        core_command_phase_2026_08.GAIN_CORE_CP_SOURCE_ID
    )
    assert rules_by_id["battle-shock"].source_id == (
        core_command_phase_2026_08.BATTLE_SHOCK_SOURCE_ID
    )
    assert rules_by_id["battle-shock"].runtime_consumer_ids == (
        "warhammer40k_core.engine.phases.command:_resolve_battle_shock_step",
        "warhammer40k_core.engine.battle_shock:collect_battle_shock_test_requests",
        "warhammer40k_core.engine.battle_shock_resolution:"
        "record_battle_shock_result_and_outcome_events",
    )
    assert rules_by_id["start-of-command-phase"].official_pdf_source_text == (
        "Rules that are triggered at the start of the Command phase are resolved now."
    )
    assert rules_by_id["gain-core-cp"].official_pdf_source_text == (
        "Both players gain 1 Command Point (CP)."
    )
    assert rules_by_id["battle-shock"].official_pdf_source_text == (
        "The active player must now make one battle-shock roll (01.07) for each unit in their "
        "army that fulfils one or both of the following conditions:\n"
        "- That unit is currently battle-shocked.\n"
        "- That unit is at, or below, half-strength.\n"
        "If a unit was battle-shocked at the start of this step and its battle-shock roll during "
        "this step succeeds, it is no longer battle-shocked."
    )
    assert all(
        hashlib.sha256(rule.source_text.encode()).hexdigest()
        == rule.transcription_sha256
        == core_command_phase_2026_08.TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]
        for rule in rules
    )
    assert all(
        hashlib.sha256(rule.official_pdf_source_text.encode()).hexdigest()
        == rule.official_pdf_transcription_sha256
        == core_command_phase_2026_08.OFFICIAL_PDF_TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]
        for rule in rules
    )
    assert (
        hashlib.sha256(Path(core_rules.LOCAL_CORE_RULES_PDF).read_bytes()).hexdigest()
        == (source_document["official_pdf_sha256"])
    )
    assert source_document["official_pdf_sha256"] == (
        core_command_phase_2026_08.EXPECTED_OFFICIAL_PDF_SHA256
    )
    assert source_document["official_pdf_source_id"] == (
        "gw-11e-core-rules:manifest:local-core-rules-pdf"
    )
    assert source_document["authoritative_category_url"] == (
        "https://www.40k.app/rules/08-command-phase"
    )
    assert source_document["authoritative_category_observed_at"] == ("2026-08-25T00:00:00-04:00")
    assert source_document["authoritative_category_scope"] == ("category_08_review_audit_record")
    assert source_document["category_body_capture_status"] == (
        "review_audit_without_retained_page_body"
    )
    assert source_document["review_audit_source_observation_sha256"] == (
        "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e"
    )
    assert source_document["exact_text_source_scope"] == (
        "retained_official_pdf_sections_08.01_through_08.03"
    )
    assert search_index_payload["source_url"] == "https://www.40k.app/rules"
    assert search_index_payload["observed_at"] == "2026-08-26T14:49:10-04:00"
    assert search_index_payload["observation_scope"] == ("command_phase_five_heading_sequence_only")
    assert search_index_observation.normalized_observed_text == (
        "START OF COMMAND PHASE\n"
        "GAIN CORE CP\n"
        "BATTLE-SHOCK\n"
        "COMMAND ABILITIES\n"
        "END OF COMMAND PHASE"
    )
    assert [
        (heading.display_order, heading.normalized_heading)
        for heading in search_index_observation.headings
    ] == [
        (1, "START OF COMMAND PHASE"),
        (2, "GAIN CORE CP"),
        (3, "BATTLE-SHOCK"),
        (4, "COMMAND ABILITIES"),
        (5, "END OF COMMAND PHASE"),
    ]
    assert all(
        hashlib.sha256(heading.normalized_heading.encode()).hexdigest()
        == heading.transcription_sha256
        for heading in search_index_observation.headings
    )
    assert search_index_observation.sequence_transcription_sha256 == (
        core_command_phase_2026_08.EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256
    )
    assert search_index_observation.source_observation_sha256 == (
        core_command_phase_2026_08.EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256
    )

    review_context, source_observation_by_row_id = _core_rules_review_audit_context()
    assert review_context["observed_at"] == "2026-08-25T00:00:00-04:00"
    assert (
        source_observation_by_row_id["category:08"]
        == (source_document["review_audit_source_observation_sha256"])
    )
    expected_semantic_status = {
        "start-of-command-phase": "executable_engine_runtime",
        "gain-core-cp": "executable_engine_runtime",
        "battle-shock": "partial_engine_runtime",
    }
    for rule in rules:
        evidence = source_package.source_evidence_catalog.records_for_source_id(rule.source_id)
        project_review = next(
            record
            for record in evidence
            if record.evidence_kind == "project_reviewed_app_transcription"
        )
        mirror = next(record for record in evidence if record.evidence_kind == "third_party_mirror")
        assert project_review.source_url is project_review.observed_at is None
        assert project_review.verification_status == "unverified"
        assert mirror.source_url == search_index_observation.source_url
        assert mirror.observed_at == search_index_observation.observed_at
        assert mirror.source_title == (
            "40k.app Core Rules search-index Command-phase heading sequence"
        )
        assert mirror.review_audit_id == search_index_observation.observation_id
        assert mirror.review_audit_row_id == search_index_observation.observation_row_id
        assert (
            mirror.review_audit_source_observation_sha256
            == search_index_observation.source_observation_sha256
        )
        assert (
            mirror.review_audit_source_observation_sha256
            != (source_observation_by_row_id["category:08"])
        )
        assert mirror.observation_sha256 == rule.source_observation_sha256
        assert all(
            record.transcription_sha256 == rule.transcription_sha256
            and record.load_support_status == "loaded"
            and record.semantic_execution_status == expected_semantic_status[rule.rule_id]
            and record.runtime_consumer_ids == rule.runtime_consumer_ids
            and RuleEvidenceRecord.from_payload(record.to_payload()) == record
            for record in evidence
        )
        assert (
            source_package.source_catalog.source_text_by_id(rule.source_id).raw_text
            == rule.section_heading
        )
        assert (
            source_package.source_catalog.source_text_by_id(
                f"{rule.source_id}:official-pdf-body"
            ).raw_text
            == rule.official_pdf_source_text
        )

    catalog_payload = source_package.source_catalog.to_payload()
    assert SourceCatalog.from_payload(catalog_payload).to_payload() == catalog_payload


@pytest.mark.parametrize(
    ("target", "field_name", "replacement"),
    [
        ("rule", "display_order", 2),
        ("rule", "official_pdf_source_text", "stale PDF text"),
        ("document", "category_body_capture_status", "captured"),
        ("mirror", "source_url", "https://www.40k.app/rules/08-command-phase"),
        ("search", "source_url", "https://www.40k.app/rules/08-command-phase"),
        ("search", "observed_at", "2026-08-26T14:50:10-04:00"),
        ("search_heading", "normalized_heading", "GAIN CORE CP FIRST"),
        ("search_heading", "display_order", 2),
        ("rule", "semantic_execution_status", "partial_engine_runtime"),
    ],
)
def test_p08ab_command_phase_source_rejects_identity_provenance_and_status_drift(
    target: str,
    field_name: str,
    replacement: object,
) -> None:
    payload = _core_command_phase_source_payload()
    rules = cast(list[dict[str, object]], payload["rules"])
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    if target == "rule":
        rules[0][field_name] = replacement
    elif target == "document":
        source_document = cast(dict[str, object], payload["source_document"])
        source_document[field_name] = replacement
    elif target == "search":
        search_index = cast(dict[str, object], payload["search_index_observation"])
        search_index[field_name] = replacement
    elif target == "search_heading":
        search_index = cast(dict[str, object], payload["search_index_observation"])
        headings = cast(list[dict[str, object]], search_index["headings"])
        headings[0][field_name] = replacement
    else:
        mirror = next(
            record
            for record in evidence
            if record["evidence_id"]
            == "40k-app-command-phase-search-index-2026-08-26:start-of-command-phase"
        )
        mirror[field_name] = replacement

    with pytest.raises(core_command_phase_2026_08.CoreCommandPhaseSourceArtifactError):
        core_command_phase_2026_08.core_command_phase_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "reordered_rules",
        "missing_rule",
        "extra_rule",
        "reordered_evidence",
        "missing_evidence",
        "extra_evidence",
    ],
)
def test_p08ab_command_phase_source_rejects_inventory_drift(mutation: str) -> None:
    payload = _core_command_phase_source_payload()
    rules = cast(list[dict[str, object]], payload["rules"])
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    if mutation == "reordered_rules":
        rules.reverse()
    elif mutation == "missing_rule":
        rules.pop()
    elif mutation == "extra_rule":
        rules.append(dict(rules[0]))
    elif mutation == "reordered_evidence":
        evidence.reverse()
    elif mutation == "missing_evidence":
        evidence.pop()
    else:
        extra_evidence = dict(evidence[0])
        extra_evidence["evidence_id"] = "core-v2-p08a-source-review:extra"
        evidence.append(extra_evidence)

    with pytest.raises(core_command_phase_2026_08.CoreCommandPhaseSourceArtifactError):
        core_command_phase_2026_08.core_command_phase_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    "malformation",
    ["malformed_json", "unknown_field"],
)
def test_p08ab_command_phase_source_rejects_malformed_or_unknown_fields(
    malformation: str,
) -> None:
    if malformation == "malformed_json":
        raw = b"{"
    else:
        payload = _core_command_phase_source_payload()
        payload["unexpected_field"] = True
        raw = json.dumps(payload, sort_keys=True).encode()

    with pytest.raises(
        core_command_phase_2026_08.CoreCommandPhaseSourceArtifactError,
        match="artifact is invalid",
    ):
        core_command_phase_2026_08.core_command_phase_source_artifact_from_json_bytes(raw)


def test_p08ab_search_index_fingerprint_covers_url_timestamp_scope_text_and_order() -> None:
    observation = cast(
        dict[str, object],
        _core_command_phase_source_payload()["search_index_observation"],
    )

    def fingerprint(payload: dict[str, object]) -> str:
        canonical = cast(dict[str, object], json.loads(json.dumps(payload)))
        canonical["source_observation_sha256"] = ""
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    expected = cast(str, observation["source_observation_sha256"])
    assert fingerprint(observation) == expected
    for field_name, replacement in (
        ("source_url", "https://www.40k.app/rules/08-command-phase"),
        ("observed_at", "2026-08-26T14:50:10-04:00"),
        ("observation_scope", "category_locator_only"),
        ("normalized_observed_text", "GAIN CORE CP\nSTART OF COMMAND PHASE"),
    ):
        mutated = cast(dict[str, object], json.loads(json.dumps(observation)))
        mutated[field_name] = replacement
        assert fingerprint(mutated) != expected

    reordered = cast(dict[str, object], json.loads(json.dumps(observation)))
    headings = cast(list[dict[str, object]], reordered["headings"])
    headings[0], headings[1] = headings[1], headings[0]
    assert fingerprint(reordered) != expected


@pytest.mark.parametrize(
    "mutation",
    [
        "reordered_heading_sequence",
        "category_url_substitution",
        "category_scope_substitution",
    ],
)
def test_p08ab_builder_rejects_reviewed_search_observation_identity_drift(
    mutation: str,
) -> None:
    payload = _core_command_phase_source_payload()
    source_document = cast(dict[str, object], payload["source_document"])
    search_index = cast(dict[str, object], payload["search_index_observation"])
    headings = cast(list[dict[str, object]], search_index["headings"])
    if mutation == "reordered_heading_sequence":
        headings[0], headings[1] = headings[1], headings[0]
    elif mutation == "category_url_substitution":
        search_index["source_url"] = source_document["authoritative_category_url"]
    else:
        search_index["observation_scope"] = source_document["authoritative_category_scope"]

    with pytest.raises(
        CoreCommandPhaseSourceBuildError,
        match="reviewed semantic identity",
    ):
        build_core_command_phase_source_payload(payload)


def test_p08ab_builder_rejects_rehashed_category_audit_substitution_for_search_link() -> None:
    payload = _core_command_phase_source_payload()
    source_document = cast(dict[str, object], payload["source_document"])
    search_index = cast(dict[str, object], payload["search_index_observation"])
    rules = cast(list[dict[str, object]], payload["rules"])
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    search_index.update(
        {
            "observation_id": source_document["review_audit_id"],
            "observation_row_id": source_document["review_audit_row_id"],
            "source_url": source_document["authoritative_category_url"],
            "observed_at": source_document["authoritative_category_observed_at"],
            "observation_scope": source_document["authoritative_category_scope"],
            "source_observation_sha256": source_document["review_audit_source_observation_sha256"],
        }
    )
    rules_by_source_id = {cast(str, rule["source_id"]): rule for rule in rules}
    for record in evidence:
        if record["evidence_kind"] != "third_party_mirror":
            continue
        record.update(
            {
                "review_audit_id": source_document["review_audit_id"],
                "review_audit_row_id": source_document["review_audit_row_id"],
                "review_audit_source_observation_sha256": source_document[
                    "review_audit_source_observation_sha256"
                ],
                "source_url": source_document["authoritative_category_url"],
                "observed_at": source_document["authoritative_category_observed_at"],
            }
        )
        record["observation_sha256"] = _command_phase_evidence_observation_sha256(record)
        rules_by_source_id[cast(str, record["rule_source_id"])]["source_observation_sha256"] = (
            record["observation_sha256"]
        )
    payload["package_hash"] = ""
    payload["package_hash"] = _canonical_payload_sha256(payload)

    assert search_index["observation_id"] == "40k-app-core-rules-2026-08-25"
    assert search_index["observation_row_id"] == "category:08"
    assert search_index["source_observation_sha256"] == (
        "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e"
    )
    assert all(
        rule["source_observation_sha256"]
        == next(
            record["observation_sha256"]
            for record in evidence
            if record["evidence_kind"] == "third_party_mirror"
            and record["rule_source_id"] == rule["source_id"]
        )
        for rule in rules
    )
    assert payload["package_hash"] == _canonical_payload_sha256({**payload, "package_hash": ""})

    with pytest.raises(
        CoreCommandPhaseSourceBuildError,
        match="reviewed semantic identity",
    ):
        build_core_command_phase_source_payload(payload)


def test_p08a_command_phase_source_rejects_raw_byte_drift() -> None:
    raw = _core_command_phase_source_artifact_path().read_bytes()
    core_command_phase_2026_08.validate_core_command_phase_source_artifact_bytes(raw)

    with pytest.raises(
        core_command_phase_2026_08.CoreCommandPhaseSourceArtifactError,
        match="artifact bytes drifted",
    ):
        core_command_phase_2026_08.validate_core_command_phase_source_artifact_bytes(raw + b"\n")


def test_project_reviewed_app_transcription_is_truthful_and_insufficient_alone() -> None:
    package = core_stratagems_2026_08.source_package()
    source_id = core_stratagems_2026_08.RULE_SOURCE_IDS["crushing-impact"]
    records = package.source_evidence_catalog.records_for_source_id(source_id)
    project_review = next(
        record for record in records if record.evidence_kind == "project_reviewed_app_transcription"
    )
    payload = project_review.to_payload()
    payload["provider_name"] = "Project Owner"
    payload["observation_sha256"] = _observation_sha256(payload)

    with pytest.raises(
        RuleEvidenceError,
        match="project-reviewed App transcription must retain repository-review provenance",
    ):
        RuleEvidenceRecord.from_payload(payload)
    with pytest.raises(
        RuleEvidenceError,
        match="executable or partial semantics require an official App capture or project",
    ):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=tuple(
                    record
                    for record in package.source_evidence_catalog.records
                    if record.rule_source_id != source_id or record == project_review
                )
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )


def test_ruleset_descriptor_hash_is_eleventh_only_and_deterministic() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    payload = descriptor.to_payload()

    assert payload["ruleset_id"]["edition"] == "11e"
    assert descriptor.descriptor_hash == RulesetDescriptor.from_payload(payload).descriptor_hash


def _replace_evidence_records(
    package: RuleSourcePackage,
    *replacements: RuleEvidenceRecord,
) -> tuple[RuleEvidenceRecord, ...]:
    replacements_by_id = {record.evidence_id: record for record in replacements}
    return tuple(
        replacements_by_id.get(record.evidence_id, record)
        for record in package.source_evidence_catalog.records
    )


def _july_rules_update_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            Path(
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
                "july_rules_updates_2026_07/artifacts/package.json"
            ).read_text()
        ),
    )


def _july_rules_update_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "july_rules_updates_2026_07/artifacts/package.json"
    )


def _app_hidden_transcription_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "app_core_rules_hidden_2026_08_09/artifacts/hidden.json"
    )


def _app_hidden_transcription_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(_app_hidden_transcription_artifact_path().read_text()),
    )


def _core_stratagem_app_source_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_stratagems_2026_08/artifacts/package.json"
    )


def _core_stratagem_app_source_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(_core_stratagem_app_source_artifact_path().read_text()),
    )


def _core_command_phase_source_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_command_phase_2026_08/artifacts/package.json"
    )


def _core_command_phase_source_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(_core_command_phase_source_artifact_path().read_text()),
    )


def _canonical_payload_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _command_phase_evidence_observation_sha256(record: dict[str, object]) -> str:
    observation = dict(record)
    observation["observation_sha256"] = ""
    observation["load_support_status"] = "not_loaded"
    observation["semantic_execution_status"] = "not_certified"
    observation["runtime_consumer_ids"] = []
    return _canonical_payload_sha256(observation)


def _core_rules_review_audit_context() -> tuple[dict[str, str], dict[str, str]]:
    payload = cast(
        dict[str, object],
        json.loads(CORE_RULES_REVIEW_AUDIT_PATH.read_text(encoding="utf-8")),
    )
    categories = cast(list[dict[str, object]], payload["categories"])
    findings = cast(list[dict[str, object]], payload["findings"])
    provider = cast(dict[str, object], payload["provider"])
    context = {
        "audit_id": cast(str, payload["audit_id"]),
        "observed_at": cast(str, payload["observed_at"]),
        "project_authority_policy_id": cast(str, provider["project_authority_policy_id"]),
        "provider_affiliation": cast(str, provider["affiliation"]),
    }
    source_observation_by_row_id = {
        **{
            f"category:{cast(str, row['category_id'])}": cast(str, row["source_observation_sha256"])
            for row in categories
        },
        **{
            f"finding:{cast(str, row['finding_id'])}": cast(str, row["source_observation_sha256"])
            for row in findings
        },
    }
    return context, source_observation_by_row_id


def _universal_rule_payload(payload: dict[str, object]) -> dict[str, object]:
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    rules = cast(list[dict[str, object]], universal_update["rules"])
    return rules[0]


def _observation_sha256(payload: RuleEvidencePayload) -> str:
    observation_payload = dict(payload)
    observation_payload["observation_sha256"] = ""
    observation_payload["load_support_status"] = "not_loaded"
    observation_payload["semantic_execution_status"] = "not_certified"
    observation_payload["runtime_consumer_ids"] = []
    return hashlib.sha256(
        json.dumps(observation_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
