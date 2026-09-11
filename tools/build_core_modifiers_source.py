"""Build the reviewed Orders 26, 27, 28, 29 and 37 source artifacts offline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "core_modifiers_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/modifiers_2026_09_07.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-modifiers"
VERSION = "maintained-app-mirrors-observed-2026-09-07"
OBSERVED_AT = "2026-09-07T02:46:54Z"
AUDIT_ID = "core-modifiers-maintained-app-mirrors-2026-09-07"
SOURCE_URL = "https://www.40k.app/rules/02-datasheets"
TRANSCRIPTION_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/modifiers_2026_09_07.transcription.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _observation(value: dict[str, object]) -> str:
    evidence = copy.deepcopy(value)
    evidence.update(
        observation_sha256="",
        load_support_status="not_loaded",
        semantic_execution_status="not_certified",
        runtime_consumer_ids=[],
    )
    return _hash(evidence)


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for row in json.loads(TRANSCRIPTION_PATH.read_text(encoding="utf-8")):
        slug, section, source_text = row["slug"], row["section"], row["source_text"]
        consumers = [row["consumer"]]
        observed_at = row.get("observed_at", OBSERVED_AT)
        source_url = row.get("source_url", SOURCE_URL)
        source_id = f"{PACKAGE_ID}:{slug}"
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
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
        shared: dict[str, object] = {
            "rule_source_id": source_id,
            "app_build": None,
            "capture_artifact_path": None,
            "capture_sha256": None,
            "transcription_sha256": text_hash,
            "official_corroborating_source_ids": [],
            "observation_sha256": "",
            "load_support_status": "loaded",
            "semantic_execution_status": "executable_engine_runtime",
            "runtime_consumer_ids": consumers,
        }
        review = {
            **shared,
            "evidence_id": f"core-modifiers-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P02E {section} {slug}"
            if slug == "stratagem-cost-limits"
            else f"P02A/P02B/P02C {section} {slug}"
            if section == "02.02.01"
            else f"P24I {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        review["observation_sha256"] = _observation(review)
        evidence.append(review)
        providers: list[tuple[str, str, str | None]] = [("40k.app", source_url, None)]
        for provider, url, version in providers:
            row_id = f"{slug}:{'gdm-v931' if version else '40k-app'}"
            audit: dict[str, object] = {
                "row_id": row_id,
                "provider_name": provider,
                "source_url": url,
                "observed_at": observed_at,
                "app_version": version,
                "policy_id": POLICY,
                "rule_source_id": source_id,
                "transcription_sha256": text_hash,
                "provider_non_affiliation_recorded": True,
            }
            audit_hash = _hash(audit)
            audits.append({**audit, "source_observation_sha256": audit_hash})
            mirror = {
                **shared,
                "evidence_id": f"core-modifiers-mirror:{row_id}",
                "evidence_kind": "third_party_mirror",
                "authority": "project_authoritative_app_mirror",
                "project_authority_policy_id": POLICY,
                "review_audit_id": AUDIT_ID,
                "review_audit_row_id": row_id,
                "review_audit_source_observation_sha256": audit_hash,
                "provider_name": provider,
                "source_title": f"{provider} {section} {slug}",
                "source_platform": "Web",
                "source_url": url,
                "observed_at": None if version else observed_at,
                "app_version": version,
                "verification_status": "authoritative_app_mirror",
                "provider_non_affiliation_recorded": True,
            }
            mirror["observation_sha256"] = _observation(mirror)
            evidence.append(mirror)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-modifiers-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    payload["package_hash"] = _hash(payload)
    return payload, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "rows": audits,
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "co_version_comparison": (
            "02.02.01, 02.02.02 and 24.29 operative clauses observed through "
            "the 40k.app search index; "
            "direct retrieval returned HTTP 403. No App version or co-version comparison "
            "is inferred. The retained transcription separates reviewed obligations. "
            "Order 37 adds the 02.02.01 CP-cost limit observed in the same search index "
            "on 2026-09-11T19:52:51Z; earlier observation tuples remain unchanged."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"P02A/P02B/P02C source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
