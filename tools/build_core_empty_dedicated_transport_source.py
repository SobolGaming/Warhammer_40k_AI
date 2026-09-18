"""Reproduce the reviewed Order 59 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-empty-dedicated-transport"
VERSION = "maintained-app-mirrors-observed-2026-09-18"
OBSERVED_AT = "2026-09-18T16:45:00+00:00"
AUDIT_ID = "core-empty-dedicated-transport-maintained-app-mirrors-2026-09-18"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:empty-dedicated-transport"
TEXT = (
    "A friendly unit must be embarked within each friendly DEDICATED TRANSPORT model. "
    "At the end of this step, each friendly DEDICATED TRANSPORT model without an "
    "embarked unit is destroyed, but they do not trigger rules that are triggered when "
    "a model is destroyed."
)
URL = "https://www.40k.app/rules/18-transports"
CONSUMERS = [
    (
        "warhammer40k_core.engine.empty_dedicated_transport_destruction:"
        "apply_empty_dedicated_transport_destruction"
    ),
    "warhammer40k_core.engine.setup_flow:SetupFlow.advance",
    ("warhammer40k_core.engine.setup_completion:_append_empty_transport_manifest_violations"),
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "destroys_at_declare_battle_formations_end": True,
    "triggers_destroyed_model_rules": False,
    "requires_embarked_unit": True,
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_empty_dedicated_transport_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/empty_dedicated_transport_2026_09_18.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    slug = "empty-dedicated-transport"
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
        "transcription_scope": "Complete 18.01 empty Dedicated Transport operative text.",
        "reviewed_obligations": [
            "A friendly unit must be embarked within each friendly Dedicated Transport model.",
            (
                "At the end of Declare Battle Formations, destroy every Dedicated Transport "
                "model without an embarked unit."
            ),
            "That destruction does not trigger rules that trigger when a model is destroyed.",
        ],
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": f"core-empty-dedicated-transport-mirror:{slug}",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": slug,
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "40k.app",
        "source_title": "40k.app 18.01 Transport Capacity empty Dedicated Transport",
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
        "evidence_id": f"core-empty-dedicated-transport-review:{slug}",
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
        "artifact_schema": "core-v2-core-empty-dedicated-transport-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "18.01",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "destruction_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete 18.01 empty Dedicated Transport operative text retrieved from the "
            "40k.app Transports page."
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
                raise SystemExit(f"Order 59 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
