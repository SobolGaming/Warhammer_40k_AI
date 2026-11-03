"""Generate the bounded, source-only Core description admission from reviewed observations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "data/source_audits/core_descriptions_2026_11/reviewed-observations.json"
OBSERVATIONS_SHA256 = "2cc9783d22512e9135b450d44a12e694ab742edd8475f83ed55bbd63a6daf3e3"
ARTIFACT_PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "core_descriptions_2026_11/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/core_descriptions_2026_11/source-admission.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
AUDIT_ID = "core-descriptions-maintained-app-mirror-2026-11-03"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    raw = OBSERVATIONS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OBSERVATIONS_SHA256:
        raise ValueError("Reviewed Core description observations drifted.")
    observations = json.loads(raw)
    fresh = observations["fresh_observation"]
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for observation in observations["rules"]:
        section = observation["section_id"]
        source = observation["source_id"]
        text = observation["source_text"]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        rules.append(
            {
                "source_id": source,
                "section_id": section,
                "source_text": text,
                "transcription_sha256": text_hash,
                "dependency_source_ids": ["gw-11e-core-abilities:core:scout-move"]
                if section == "24.31"
                else [],
                "load_support_status": "loaded",
                "semantic_execution_status": "not_certified",
                "runtime_consumer_ids": [],
            }
        )
        audit = {
            "row_id": section + ":40k-app",
            "provider_name": fresh["provider_name"],
            "source_url": fresh["source_url"],
            "observed_at": fresh["observed_at"],
            "app_version": None,
            "policy_id": POLICY,
            "rule_source_id": source,
            "transcription_sha256": text_hash,
            "provider_non_affiliation_recorded": True,
            "rendered_section_sha256": hashlib.sha256(
                fresh["sections"][section]["captured_text"].encode()
            ).hexdigest(),
            "reviewed_observations_sha256": OBSERVATIONS_SHA256,
        }
        audit_hash = _hash(audit)
        audits.append({**audit, "source_observation_sha256": audit_hash})
        mirror = {
            "rule_source_id": source,
            "app_build": None,
            "capture_artifact_path": None,
            "capture_sha256": None,
            "transcription_sha256": text_hash,
            "official_corroborating_source_ids": [],
            "observation_sha256": "",
            "load_support_status": "loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
            "evidence_id": "core-descriptions:" + section + ":40k-app",
            "evidence_kind": "third_party_mirror",
            "authority": "project_authoritative_app_mirror",
            "project_authority_policy_id": POLICY,
            "review_audit_id": AUDIT_ID,
            "review_audit_row_id": audit["row_id"],
            "review_audit_source_observation_sha256": audit_hash,
            "provider_name": fresh["provider_name"],
            "source_title": "40k.app " + section,
            "source_platform": "Web",
            "source_url": fresh["source_url"],
            "observed_at": fresh["observed_at"],
            "app_version": None,
            "verification_status": "authoritative_app_mirror",
            "provider_non_affiliation_recorded": True,
        }
        mirror["observation_sha256"] = _hash({**mirror, "load_support_status": "not_loaded"})
        review = {
            **mirror,
            "evidence_id": "core-descriptions-review:" + section,
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
        review["observation_sha256"] = _hash({**review, "load_support_status": "not_loaded"})
        evidence.extend((review, mirror))
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-descriptions-source-v1",
        "source_package_id": "gw-11e-core-descriptions",
        "source_version": "maintained-app-mirror-observed-2026-11-03",
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": fresh["observed_at"],
        "rows": audits,
        "authority_limit": (
            "Project-authoritative maintained mirror; no official-primary, App-build, "
            "network-byte-capture or runtime certification claim."
        ),
        "comparison": observations["comparison"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(
                    f"Core description source artifact drift: {path.relative_to(ROOT)}"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
