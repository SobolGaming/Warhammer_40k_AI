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
    / "core_transports_2026_09"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://www.40k.app/rules/18-transports"
OBSERVED_AT = "2026-09-01T18:46:11-04:00"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
REVIEW_AUDIT_ROW_ID = "category:18"
REVIEW_AUDIT_OBSERVATION_SHA256 = "d9a06d3c5b350f66bad9e4b89f62242fd0f0b4c54579ea3ad6bbf2c2674b8d0e"

SOURCE_TEXT = """EMERGENCY DISEMBARK MOVE
When eligible: Your unit is embarked within a TRANSPORT model that was just destroyed.
Maximum distance: SET-UP DISTANCE: 6\"
Effect: Your unit is set up as described in Set Up (03.02)
Before moving: Make a hazard roll for each model in your unit (06.03)
While moving: Set up each model in your unit:
- Wholly within the set-up distance of that TRANSPORT, and as close as possible to that TRANSPORT.
- Or: If the above is not possible while remaining unengaged, set up that model wholly within the set-up distance of that TRANSPORT, as close as possible to that TRANSPORT, and engaged.
Each model that still cannot be set up is destroyed.
After moving: Your unit is battle-shocked and, until the end of the turn, it is not eligible to declare a charge."""

RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.attack_sequence_destroyed_transport:_continue_pending_destroyed_transport_disembark",
    "warhammer40k_core.engine.attack_sequence_destroyed_transport:_request_destroyed_transport_disembark_placement",
    "warhammer40k_core.engine.emergency_disembark:apply_transport_hazard_mortal_wounds_service",
    "warhammer40k_core.engine.emergency_disembark:resolve_destroyed_transport_hazard_rolls_service",
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
        "rule_source_id": "gw-11e-core-rules:transports:emergency-disembark-move",
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
        "evidence_id": "core-v2-transports-source-review:emergency-disembark-move",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": "Reviewed transcription of 18.05 Emergency Disembark Move",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": "40k-app-transports-2026-09-01:emergency-disembark-move",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "40k.app",
        "source_title": "40k.app Core Rules 18.05 Emergency Disembark Move",
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
        "artifact_schema": "core-v2-transports-source-v1",
        "source_package_id": "gw-11e-core-transports",
        "source_version": "40k-app-transports-observed-2026-09-01",
        "source_document": {
            "document_id": "40k-app-transports-2026-09-01",
            "source_title": "40k.app Core Rules Transports",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "emergency-disembark-move",
                "source_id": "gw-11e-core-rules:transports:emergency-disembark-move",
                "section_id": "18.05",
                "section_heading": "EMERGENCY DISEMBARK MOVE",
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
        description="Build the reviewed 18.05 Emergency Disembark source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Transports source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
