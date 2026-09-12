# ruff: noqa: E501
"""Reproduce the reviewed P04 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/core_target_replacement_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/target_replacement_2026_09_12.audit.json"
)
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-target-replacement"
VERSION = "maintained-app-mirrors-observed-2026-09-12"
OBSERVED_AT = "2026-09-12T14:47:00+00:00"
AUDIT_ID = "core-target-replacement-maintained-app-mirrors-2026-09-12"
RULES = (
    (
        "target-no-longer-eligible-or-viable",
        "04.03.03",
        "04-making-attacks",
        "Target No Longer Eligible Or Viable\nIf a unit that was an eligible target for a rule or attack when it was selected stops being an eligible target (for example, because a rule enables it to make an out-of-phase move that takes it out of range), the controlling player can select new targets.",
    ),
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for slug, section, _page, source_text in RULES:
        source_id = f"{PACKAGE_ID}:{slug}"
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
        url = "https://www.40k.app/rules/04-making-attacks"
        consumers = [
            "warhammer40k_core.engine.target_replacement:replacement_selection",
            "warhammer40k_core.engine.shooting_target_replacement:next_shooting_target_replacement",
        ]
        observed_at = OBSERVED_AT
        rules.append(
            {
                "source_id": source_id,
                "section_id": section,
                "source_text": source_text,
                "transcription_sha256": text_hash,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": consumers,
            }
        )
        audit: dict[str, object] = {
            "row_id": slug,
            "provider_name": "40k.app",
            "source_url": url,
            "observed_at": observed_at,
            "app_version": None,
            "policy_id": POLICY,
            "rule_source_id": source_id,
            "transcription_sha256": text_hash,
            "provider_non_affiliation_recorded": True,
        }
        audit_hash = _hash(audit)
        audits.append({**audit, "source_observation_sha256": audit_hash})
        row: dict[str, object] = {
            "evidence_id": f"core-target-replacement-mirror:{slug}",
            "rule_source_id": source_id,
            "evidence_kind": "third_party_mirror",
            "authority": "project_authoritative_app_mirror",
            "project_authority_policy_id": POLICY,
            "review_audit_id": AUDIT_ID,
            "review_audit_row_id": slug,
            "review_audit_source_observation_sha256": audit_hash,
            "provider_name": "40k.app",
            "source_title": f"40k.app {section} {slug}",
            "source_platform": "Web",
            "source_url": url,
            "observed_at": observed_at,
            "app_version": None,
            "app_build": None,
            "capture_artifact_path": None,
            "capture_sha256": None,
            "transcription_sha256": text_hash,
            "official_corroborating_source_ids": [],
            "verification_status": "authoritative_app_mirror",
            "provider_non_affiliation_recorded": True,
            "observation_sha256": "",
            "load_support_status": "loaded",
            "semantic_execution_status": "executable_engine_runtime",
            "runtime_consumer_ids": consumers,
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
            "evidence_id": f"core-target-replacement-review:{slug}",
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
        evidence.append(review)
        evidence.append(row)
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-target-replacement-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "rows": audits,
        "observation_time_precision": "minute",
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "co_version_comparison": "Expanded 04.03.03 read directly in both approved mirrors. The operative paragraphs agree. Neither rule page exposes an App version, so no co-version identity is asserted.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"P04 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
