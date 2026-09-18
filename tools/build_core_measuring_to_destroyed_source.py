"""Reproduce the reviewed Order 57 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-measuring-to-destroyed"
VERSION = "maintained-app-mirrors-observed-2026-09-18"
OBSERVED_AT = "2026-09-18T12:05:00+00:00"
AUDIT_ID = "core-measuring-to-destroyed-maintained-app-mirrors-2026-09-18"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:measuring-to-destroyed"
TEXT = (
    "When a player has to measure the distance to a destroyed model, that player can "
    "measure to any point occupied by that model's base (or any part of that model if "
    "it does not have a base or is a Vehicle, excluding Walker models that have a base) "
    "before it was destroyed.\n"
    "When a player has to measure the distance to a destroyed unit, they measure to the "
    "last model destroyed in that unit."
)
URL = "https://www.40k.app/rules/05-attack-sequence"
CONSUMERS = [
    (
        "warhammer40k_core.engine.destroyed_referent_measurement:"
        "former_footprint_for_destroyed_model"
    ),
    ("warhammer40k_core.engine.destroyed_referent_measurement:former_footprint_for_destroyed_unit"),
    ("warhammer40k_core.engine.destroyed_referent_measurement:distance_to_destroyed_model"),
    ("warhammer40k_core.engine.destroyed_referent_measurement:distance_to_destroyed_unit"),
    "warhammer40k_core.engine.deadly_demise:deadly_demise_target_unit_ids",
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "uses_former_footprint": True,
    "destroyed_unit_resolves_to_last_destroyed_model": True,
    "grants_living_battlefield_authority": False,
    "uses_catalog_geometry_for_base_or_hull": True,
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_measuring_to_destroyed_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/measuring_to_destroyed_2026_09_18.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    audit: dict[str, object] = {
        "row_id": "measuring-to-destroyed",
        "provider_name": "40k.app",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": "Complete 05.04.06 operative text.",
        "reviewed_obligations": [
            "Measure to a destroyed model using any point of its former base, or any part of the model if it has no base or is a Vehicle excluding Walker models that have a base.",  # noqa: E501
            "Measure to a destroyed unit using the last model destroyed in that unit.",
            "Former-footprint measurement grants no living battlefield authority.",
        ],
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": "core-measuring-to-destroyed-mirror:measuring-to-destroyed",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": "measuring-to-destroyed",
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "40k.app",
        "source_title": "40k.app 05.04.06 Measuring To A Destroyed Model Or Unit",
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
        "evidence_id": "core-measuring-to-destroyed-review:measuring-to-destroyed",
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
        "artifact_schema": "core-v2-core-measuring-to-destroyed-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "05.04.06",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "measurement_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete 05.04.06 operative text retrieved from the 40k.app Attack Sequence page."
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
                raise SystemExit(f"Order 57 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
