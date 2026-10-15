from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import cast

import pytest
from tools.build_core_abilities_source import build_payload as build_core_abilities_source_payload
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
from tools.build_core_fight_on_death_source import build_payloads as build_fight_on_death_payloads
from tools.build_core_movement_phase_source import build_payload as build_movement_source_payload
from tools.build_core_other_concepts_source import (
    build_payload as build_other_concepts_source_payload,
)
from tools.build_core_transports_source import build_payload as build_transports_source_payload

from warhammer40k_core.core.missions import MissionSourcePackageDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.prebattle_records import SCOUT_ALTERNATION_FAQ_SOURCE_RULE_ID
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
    core_fight_on_death_2026_09,
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


__all__: list[str] = []
__all__ += ["CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID", "CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH"]
__all__ += ["CORE_RULES_MAINTAINED_MIRROR_POLICY_ID", "CORE_RULES_REVIEW_AUDIT_ID"]
__all__ += ["CORE_RULES_REVIEW_AUDIT_PATH", "CORE_RULES_SOURCE_AUTHORITY_SCOPE"]
__all__ += ["EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256", "CoreCommandPhaseSourceBuildError"]
__all__ += ["PROJECT_AUTHORITY_POLICY_ID", "MissionSourcePackageDefinition", "Path"]
__all__ += ["RuleEvidenceAuthority", "RuleEvidenceError", "RuleEvidenceKind"]
__all__ += ["RuleEvidencePayload", "RuleEvidenceRecord", "RuleSourcePackage"]
__all__ += ["SCOUT_ALTERNATION_FAQ_SOURCE_RULE_ID", "RuleVerificationStatus", "RulesetDescriptor"]
__all__ += ["SourceAuthorityRegistryError", "SourceAuthorityScope", "SourceCatalog"]
__all__ += ["SourceEvidenceCatalog", "_app_hidden_transcription_artifact_path"]
__all__ += ["_app_hidden_transcription_payload", "_canonical_payload_sha256"]
__all__ += ["_command_phase_evidence_observation_sha256"]
__all__ += ["_core_command_phase_source_artifact_path", "_core_command_phase_source_payload"]
__all__ += ["_core_rules_review_audit_context", "_core_stratagem_app_source_artifact_path"]
__all__ += ["_core_stratagem_app_source_payload", "_july_rules_update_artifact_path"]
__all__ += ["_july_rules_update_payload", "_observation_sha256", "_replace_evidence_records"]
__all__ += ["_universal_rule_payload", "app_core_rules_hidden_2026_08_09"]
__all__ += ["build_attached_units_source_payload", "build_attack_sequence_source_payload"]
__all__ += ["build_core_abilities_source_payload", "build_core_command_phase_source_payload"]
__all__ += ["build_fight_on_death_payloads", "build_movement_source_payload"]
__all__ += ["build_other_concepts_source_payload", "build_transports_source_payload", "cast"]
__all__ += ["chapter_approved_2026_27", "core_abilities", "core_abilities_2026_09"]
__all__ += ["core_attached_units_2026_09", "core_attack_sequence_2026_09"]
__all__ += ["core_command_phase_2026_08", "core_fight_on_death_2026_09"]
__all__ += ["core_movement_phase_2026_08", "core_other_concepts_2026_08", "core_rules"]
__all__ += ["core_stratagems", "core_stratagems_2026_08", "core_transports_2026_09", "hashlib"]
__all__ += ["importlib", "json", "july_rules_updates_2026_07"]
__all__ += ["load_source_authority_registry_from_json_bytes", "pytest", "source_evidence_module"]
