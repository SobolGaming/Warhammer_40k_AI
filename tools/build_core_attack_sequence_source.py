# ruff: noqa: E501,RUF001
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
    / "core_attack_sequence_2026_09"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://www.40k.app/rules/05-attack-sequence"
OBSERVED_AT = "2026-09-01T14:18:39-04:00"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
REVIEW_AUDIT_ROW_ID = "category:05"
REVIEW_AUDIT_OBSERVATION_SHA256 = "c771b8acbb62f912cc21c649a6a1ec0cac5d5a1f02e5454747b9427a8571892e"

SOURCE_TEXT = """DESTROYED
Throughout a battle, models will suffer damage, lose wounds and be destroyed. When every model in a unit has been destroyed, that unit is destroyed.

When a model is destroyed, first resolve any rules that are triggered when it is destroyed, then it is removed from the battlefield. If any such rules apply, and if the model was destroyed as the result of an attack, unless otherwise stated, those rules are only resolved and that model is only removed after the attacking unit’s attacks have been resolved. Unless otherwise stated, destroyed models and units cannot use abilities or be selected or targeted by rules.

Some rules only trigger if an enemy model or unit was destroyed by you, or by a model or unit from your army. This means that the enemy model or unit was destroyed by an attack made by a model from your army, or by a player rule you have. Enemy models or units that are destroyed by any other means are not destroyed by you, or by a model or unit from your army."""

RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.attack_sequence_destruction_boundary:attack_destruction_requires_end_of_attacks_boundary",
    "warhammer40k_core.engine.attack_sequence_destruction_boundary:defer_destroyed_attack_damage_if_required",
    "warhammer40k_core.engine.attack_sequence_destruction_boundary:resolve_pending_attack_destruction_until_blocked",
    "warhammer40k_core.engine.attack_sequence_dispatch:resolve_attack_sequence_until_blocked",
    "warhammer40k_core.engine.model_destruction_cause_attack_restore:validate_pending_attack_destruction_boundary",
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
        "rule_source_id": "core_rules_05_04_04_destroyed",
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
        "evidence_id": "core-v2-attack-sequence-source-review:destroyed",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": "Reviewed transcription of 05.04.04 Destroyed",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": "40k-app-attack-sequence-2026-09-01:destroyed",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "40k.app",
        "source_title": "40k.app Core Rules 05.04.04 Destroyed",
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
        "artifact_schema": "core-v2-attack-sequence-source-v1",
        "source_package_id": "gw-11e-core-attack-sequence",
        "source_version": "40k-app-attack-sequence-observed-2026-09-01",
        "source_document": {
            "document_id": "40k-app-attack-sequence-2026-09-01",
            "source_title": "40k.app Core Rules Attack Sequence",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "destroyed",
                "source_id": "core_rules_05_04_04_destroyed",
                "section_id": "05.04.04",
                "section_heading": "DESTROYED",
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
        description="Build the reviewed 05.04.04 Destroyed source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Attack Sequence source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
