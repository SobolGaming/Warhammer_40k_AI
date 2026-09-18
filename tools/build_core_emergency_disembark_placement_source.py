"""Reproduce the reviewed Order 60 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-emergency-disembark-placement"
VERSION = "maintained-app-mirrors-observed-2026-09-18"
OBSERVED_AT = "2026-09-18T19:30:00+00:00"
AUDIT_ID = "core-emergency-disembark-placement-maintained-app-mirrors-2026-09-18"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:emergency-disembark-placement"
TEXT = (
    "While moving: Set up each model in your unit: "
    "- Wholly within the set-up distance of that TRANSPORT, and as close as possible "
    "to that TRANSPORT. "
    "- Or: If the above is not possible while remaining unengaged, set up that model "
    "wholly within the set-up distance of that TRANSPORT, as close as possible to that "
    "TRANSPORT, and engaged. "
    "Each model that still cannot be set up is destroyed."
)
URL = "https://www.40k.app/rules/18-transports"
CONSUMERS = [
    (
        "warhammer40k_core.engine.emergency_disembark_placement:"
        "append_emergency_disembark_placement_violations"
    ),
    (
        "warhammer40k_core.engine.emergency_disembark_placement:"
        "append_emergency_disembark_rules_unit_omission_violations"
    ),
    "warhammer40k_core.engine.transport_disembark_geometry:append_disembark_endpoint_violations",
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "setup_distance_inches": 6,
    "requires_closest_possible": True,
    "prefers_unengaged": True,
    "allows_engaged_when_unengaged_impossible": True,
    "destroys_only_unplaceable_models": True,
    "closest_tolerance_inches": 0.04,
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_emergency_disembark_placement_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/emergency_disembark_placement_2026_09_18.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    slug = "emergency-disembark-placement"
    audit: dict[str, object] = {
        "row_id": slug,
        "provider_name": "40k.app",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": (
            "Complete 18.05 Emergency Disembark while-moving placement text. "
            "Official historical rule ID "
            "gw-11e-core-rules:transports:emergency-disembark-move."
        ),
        "reviewed_obligations": [
            (
                "Set up each surviving model wholly within 6 inches of the destroyed "
                "Transport and as close as possible to that Transport."
            ),
            (
                "Prefer an unengaged set-up. An engaged endpoint is legal only when no "
                "unengaged 6-inch set-up exists."
            ),
            "Destroy only a model that still cannot be set up after that engaged fallback.",
        ],
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": f"core-emergency-disembark-placement-mirror:{slug}",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": slug,
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "40k.app",
        "source_title": "40k.app 18.05 Emergency Disembark Move placement",
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
        "evidence_id": f"core-emergency-disembark-placement-review:{slug}",
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
        "official_corroborating_source_ids": [],
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
        "artifact_schema": "core-v2-core-emergency-disembark-placement-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "18.05",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "placement_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete 18.05 Emergency Disembark while-moving placement text retrieved "
            "from the 40k.app Transports page."
        ),
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
                raise SystemExit(f"Order 60 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
