"""Reproduce the reviewed Order 58 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-failed-save-damage-timing"
VERSION = "maintained-app-mirrors-observed-2026-09-18"
OBSERVED_AT = "2026-09-18T15:10:00+00:00"
AUDIT_ID = "core-failed-save-damage-timing-maintained-app-mirrors-2026-09-18"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:damage-to-0-after-saves-faq"
TEXT = (
    "My unit has access to a rule that changes the Damage characteristic of an incoming "
    "attack to 0. When such an attack is allocated to a model in that unit, is the Damage "
    "changed before or after save rolls?\n"
    "After."
)
URL = "https://game-datamissions.com/11th/rules/changelog"
CONSUMERS = [
    ("warhammer40k_core.engine.failed_save_damage_timing:unused_failed_save_damage_replacement"),
    "warhammer40k_core.engine.attack_sequence_grouped_allocation:_resolve_grouped_damage_from",
    (
        "warhammer40k_core.engine.runtime_modifiers:"
        "RuntimeModifierRegistry.failed_save_damage_replacement"
    ),
    (
        "warhammer40k_core.engine.catalog_datasheet_rule_runtime:"
        "CatalogDatasheetRuleRuntime.failed_save_damage_replacement_bindings"
    ),
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "applies_after_saving_throw": True,
    "applies_before_saving_throw": False,
    "replacement_damage": 0,
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_failed_save_damage_timing_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/failed_save_damage_timing_2026_09_18.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    slug = "damage-to-0-after-saves-faq"
    audit: dict[str, object] = {
        "row_id": slug,
        "provider_name": "Game Datamissions",
        "source_url": URL,
        "observed_at": None,
        "app_version": "931",
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": "Complete v931 Damage-to-0 timing FAQ Q+A.",
        "reviewed_obligations": [
            "A rule that changes incoming attack Damage to 0 applies after the saving throw.",
            "No consumer may change that incoming Damage characteristic before the save roll.",
            "Replacement Damage is 0.",
        ],
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": f"core-failed-save-damage-timing-mirror:{slug}",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": slug,
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "Game Datamissions",
        "source_title": "Game Datamissions 05 FAQ v931 Damage-to-0 timing",
        "source_platform": "Web",
        "source_url": URL,
        "observed_at": None,
        "app_version": "931",
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
        "evidence_id": f"core-failed-save-damage-timing-review:{slug}",
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
        "app_version": None,
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
        "artifact_schema": "core-v2-core-failed-save-damage-timing-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "05 FAQ v931",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "timing_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete v931 FAQ question and the answer After. read from the Game Datamissions "
            "Core Rules Data Changelog with App-data 931 selected."
        ),
        "co_version_comparison": "No second-provider observation asserted.",
        "observed_browser_url": "https://game-datamissions.com/11th/rules/changelog?v=931",
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
                raise SystemExit(f"Order 58 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
