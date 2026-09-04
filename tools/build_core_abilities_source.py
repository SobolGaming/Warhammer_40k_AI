# ruff: noqa: E501
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "core_abilities_2026_09"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://game-datamissions.com/11th/rules/changelog"
APP_VERSION = "931"
OBSERVED_AT = "2026-09-02T12:30:09-04:00"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
REVIEW_AUDIT_ID = "core-rules-maintained-app-mirrors-2026-09-02"
REVIEW_AUDIT_ROW_ID = "game-datamissions-core-rules-data-931"
REVIEW_AUDIT_OBSERVATION_SHA256 = "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"

SOURCE_TEXT = """This ability always takes the form Deadly Demise X. Each time a model with this ability is destroyed, after the units embarked within it (if any) have made their emergency disembark moves, roll one D6. On a 6, that model suffers a deadly demise; each unit within 6\" of that model suffers a number of mortal wounds denoted by X (if this is a random number, roll separately for each unit within 6\")."""
WHEN_DESCRIPTOR = "Each time a model with this ability is destroyed, after the units embarked within it (if any) have made their emergency disembark moves"
EFFECT_DESCRIPTOR = 'roll one D6. On a 6, that model suffers a deadly demise; each unit within 6" of that model suffers a number of mortal wounds denoted by X (if this is a random number, roll separately for each unit within 6").'
RESTRICTIONS_DESCRIPTOR = "This ability always takes the form Deadly Demise X."

RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.ability_catalog:eleventh_edition_core_ability_catalog_records",
    "warhammer40k_core.engine.abilities:default_ability_handler_registry",
    "warhammer40k_core.engine.attack_sequence_damage_resolution:_resolve_deadly_demise_before_removal",
    "warhammer40k_core.engine.catalog_rule_consumption:record_core_deadly_demise_sources_for_unit",
    "warhammer40k_core.engine.deadly_demise:resolve_deadly_demise_trigger",
    "warhammer40k_core.engine.rule_model_destruction:destroy_model_with_rule_reactions",
]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _evidence_observation_sha256(evidence: dict[str, object]) -> str:
    observation = copy.deepcopy(evidence)
    observation["observation_sha256"] = ""
    observation["load_support_status"] = "not_loaded"
    observation["semantic_execution_status"] = "not_certified"
    observation["runtime_consumer_ids"] = []
    return _sha256_payload(observation)


def _evidence_rows(*, transcription_sha256: str) -> list[dict[str, object]]:
    shared: dict[str, object] = {
        "rule_source_id": "gw-11e-core-abilities:core:deadly-demise",
        "app_version": APP_VERSION,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription_sha256,
        "official_corroborating_source_ids": [],
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": RUNTIME_CONSUMER_IDS,
    }
    review = {
        **shared,
        "app_version": None,
        "evidence_id": "core-v2-core-abilities-source-review:deadly-demise",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": "Reviewed transcription of 24.08 Deadly Demise",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": "game-datamissions-core-rules-data-931:deadly-demise",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "Game Datamissions",
        "source_title": "Game Datamissions Core Rules 24.08 Deadly Demise",
        "source_platform": "Web",
        "source_url": SOURCE_URL,
        "observed_at": None,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    transcription_sha256 = _sha256_text(SOURCE_TEXT)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-abilities-source-v1",
        "source_package_id": "gw-11e-core-abilities",
        "source_version": "game-datamissions-v931-observed-2026-09-02",
        "source_document": {
            "document_id": REVIEW_AUDIT_ROW_ID,
            "source_title": "Game Datamissions Core Rules Data Changelog v931",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "app_version": APP_VERSION,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "deadly-demise",
                "runtime_ability_id": "core-deadly-demise",
                "runtime_handler_id": "core:deadly-demise",
                "source_id": "gw-11e-core-abilities:core:deadly-demise",
                "section_id": "24.08",
                "section_heading": "DEADLY DEMISE",
                "source_text": SOURCE_TEXT,
                "when_descriptor": WHEN_DESCRIPTOR,
                "effect_descriptor": EFFECT_DESCRIPTOR,
                "restrictions_descriptor": RESTRICTIONS_DESCRIPTOR,
                "trigger_kind": "after_model_destroyed",
                "transcription_sha256": transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": RUNTIME_CONSUMER_IDS,
            }
        ],
        "evidence": _evidence_rows(transcription_sha256=transcription_sha256),
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed 24.08 Deadly Demise source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Core abilities source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
