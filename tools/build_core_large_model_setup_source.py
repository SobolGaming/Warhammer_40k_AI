# ruff: noqa: RUF001
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
HISTORICAL_EXCERPT = (
    "it must be set up so that it is touching your battlefield "
    "edge. ... (excluding AIRCRAFT models)"
)
TEXT = (
    "If a model cannot meet all of its set up restrictions because it is too large, consult the "
    "relevant section below:\n"
    "During Deployment: If a model is so large that its base cannot physically be set up wholly "
    "within your deployment zone, it must be set up so that it is touching your battlefield edge. "
    "During a turn in which such a large model is set up on the battlefield, that model’s unit "
    "cannot do any of the following:\n"
    "• Make a normal/advance/fall-back/charge move.\n"
    "• Make any attacks with ranged weapons.\n"
    "Some large models, typically Aircraft, have wings and other parts that extend significantly "
    "beyond their base. Such models can overhang a deployment zone if it is not possible to set "
    "them up otherwise, but when setting them up, their base must still be wholly within that "
    "deployment zone.\n"
    "From Strategic Reserves: If a model is so large that its base cannot physically be set up "
    "wholly within the distance required of the battlefield edge, it must be set up so that it is "
    "touching a battlefield edge. During a turn in which such a large model is set up on the "
    "battlefield (excluding AIRCRAFT models), that model’s unit cannot do any of the following:\n"
    "normal/advance/fall-back/charge move.\n"
    "Make any attacks with ranged weapons.\n"
    "Some large models, typically Aircraft, have wings and other parts that extend significantly "
    "beyond their base. Such models can overhang a battlefield edge if it is not possible to set "
    'them up otherwise, but when setting them up, they must still be more than 8" away from all '
    "enemy units.\n"
    "Disembarking from a Transport: When a unit disembarks from a Transport, it must be set up "
    'wholly within 3" of that model. If a disembarking model is so large that it is not possible '
    'to set it up wholly within 3" (typically because it is itself larger than 3" in all '
    'directions), set that model up with its base within 1" of that Transport’s base (or hull), '
    "and not engaged with any enemy units."
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
            "Complete selected 03.02.02 record. The previous ellipsis excerpt remains a "
            "superseded source record and does not certify disembark or reserve consumers."
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
        "superseded_records": [
            {
                "record_id": "incomplete-excerpt:large-model-setup",
                "source_id": SOURCE_ID,
                "kind": "incomplete_excerpt",
                "prior_text": HISTORICAL_EXCERPT,
                "prior_sha256": hashlib.sha256(HISTORICAL_EXCERPT.encode()).hexdigest(),
                "successor": SOURCE_ID,
                "load_support_status": "loaded",
                "semantic_execution_status": "not_certified",
                "reason": (
                    "The previous ellipsis joined a deployment-edge fragment to the Strategic "
                    "Reserves AIRCRAFT exception. The controlling text is the complete selected "
                    "03.02.02 record, with deployment, Strategic Reserves, and disembark clauses "
                    "kept separate."
                ),
            }
        ],
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
