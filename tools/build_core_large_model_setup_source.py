"""Reproduce the reviewed Order 54 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-large-model-setup"
VERSION = "maintained-app-mirrors-observed-2026-09-17"
OBSERVED_AT = "2026-09-17T00:00:00+00:00"
AUDIT_ID = "core-large-model-setup-maintained-app-mirrors-2026-09-17"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:large-model-setup"
TEXT = (
    "it must be set up so that it is touching your battlefield "
    "edge. ... (excluding AIRCRAFT models)"
)
URL = "https://www.40k.app/rules/03-moving"
CONSUMERS = [
    "warhammer40k_core.engine.large_model_setup:oversized_deployment_violation",
    "warhammer40k_core.engine.large_model_restrictions:large_model_activity_reason",
]
OBLIGATIONS = [
    (
        "Deployment exception requires proof the model base cannot "
        "fit wholly within its deployment zone."
    ),
    "The exceptional deployment base must contact that player's battlefield edge.",
    (
        "The unit cannot make Normal, Advance, Fall Back or Charge "
        "moves or ranged attacks during the setup turn."
    ),
    (
        "Strategic Reserves oversized edge placement has the same "
        "restriction, excluding AIRCRAFT models."
    ),
    (
        "Parts overhanging a deployment zone do not waive the "
        "requirement for the base to remain wholly within it."
    ),
    (
        "Pregame deployment is outside either player's turn; it does "
        "not create a first-turn restriction."
    ),
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "deployment_requires_impossible_fit": True,
    "deployment_requires_own_edge": True,
    "restricted_activities": ["normal", "advance", "fall_back", "charge", "ranged_attacks"],
    "reserve_exempt_keyword": "AIRCRAFT",
    "expiration": "end_of_setup_turn",
}

ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_large_model_setup_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/large_model_setup_2026_09_17.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    audit: dict[str, object] = {
        "row_id": "large-model-setup",
        "provider_name": "40k.app",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": (
            "Short excerpt; complete 03.02.02 operative text reviewed in the search index."
        ),
        "reviewed_obligations": OBLIGATIONS,
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": "core-large-model-setup-mirror:large-model-setup",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": "large-model-setup",
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "40k.app",
        "source_title": "40k.app 03.02.02 Setting Up Large Models",
        "source_platform": "Web",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription,
        "official_corroborating_source_ids": [],
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": CONSUMERS,
    }
    row["observation_sha256"] = _hash(
        {
            **row,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    review = {
        **row,
        "evidence_id": "core-large-model-setup-review:large-model-setup",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
    }
    review["observation_sha256"] = _hash(
        {
            **review,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-large-model-setup-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "03.02.02",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "setup_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "day",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": "Complete search-index text; direct retrieval returned HTTP 403.",
        "co_version_comparison": "No second-provider observation asserted.",
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"Order 54 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
