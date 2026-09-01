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
    / "core_attached_units_2026_09"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://www.40k.app/rules/19-attached-units"
OBSERVED_AT = "2026-09-01T09:02:35-04:00"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
REVIEW_AUDIT_ROW_ID = "category:19"
REVIEW_AUDIT_OBSERVATION_SHA256 = "9328cc0ae8f0c22dc52418c3238a105d7031cdfdb5daf78bd377c56f36c795bd"

SOURCE_TEXT = """ATTACHED UNITS AFTER THEIR BODYGUARD UNIT IS DESTROYED
Some units have rules stating that when the bodyguard unit in an attached unit is destroyed, leader/support units that were attached to them become separate units with their original starting strengths. When the bodyguard unit in an attached unit affected by such a rule is destroyed, all of those leader/support units remain a single unit for all rules purposes."""

RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.attached_unit_reconciliation:validate_attached_rules_unit_identity_after_destruction",
    "warhammer40k_core.engine.rules_unit_placement:RulesUnitPlacement.from_battlefield",
    "warhammer40k_core.engine.rules_units:current_rules_unit_views_for_identity",
    "warhammer40k_core.engine.starting_attached_units:starting_attached_unit_records_from_armies",
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
        "rule_source_id": "gw-11e-core-rules:attached-units:bodyguard-unit-destroyed",
        "app_version": None,
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
        "evidence_id": "core-v2-attached-units-source-review:bodyguard-unit-destroyed",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": "Reviewed transcription of 19.01.01 Attached Units After Their Bodyguard Unit Is Destroyed",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": "40k-app-attached-units-2026-09-01:bodyguard-unit-destroyed",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "40k.app",
        "source_title": "40k.app Core Rules 19.01.01 Attached Units After Their Bodyguard Unit Is Destroyed",
        "source_platform": "Web",
        "source_url": SOURCE_URL,
        "observed_at": OBSERVED_AT,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    transcription_sha256 = _sha256_text(SOURCE_TEXT)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-attached-units-source-v1",
        "source_package_id": "gw-11e-core-attached-units",
        "source_version": "40k-app-attached-units-observed-2026-09-01",
        "source_document": {
            "document_id": "40k-app-attached-units-2026-09-01",
            "source_title": "40k.app Core Rules Attached Units",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "bodyguard-unit-destroyed",
                "source_id": "gw-11e-core-rules:attached-units:bodyguard-unit-destroyed",
                "section_id": "19.01.01",
                "section_heading": "ATTACHED UNITS AFTER THEIR BODYGUARD UNIT IS DESTROYED",
                "source_text": SOURCE_TEXT,
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
        description="Build the reviewed 19.01.01 Attached Units source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Attached Units source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
