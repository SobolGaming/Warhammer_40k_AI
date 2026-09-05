"""Build the reviewed P14 source artifact offline; never fetch runtime inputs."""

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
    / "core_objectives_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/objectives_2026_09_05.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-objectives"
VERSION = "maintained-app-mirrors-observed-2026-09-05"
OBSERVED_AT = "2026-09-05T08:38:21-04:00"
AUDIT_ID = "core-objectives-maintained-app-mirrors-2026-09-05"
FORTY_K_URL = "https://www.40k.app/rules/14-objectives"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"

TERRAIN_TEXT = (
    "If a mission uses objectives, it will state where they are located on the battlefield. "
    "Typically, your mission will have a deployment map showing several points where objectives "
    "should be placed. The location of each point should coincide with a terrain area (13.01); "
    "that terrain area is the objective, and is called a terrain objective.\n"
    "When measuring distances to and from an objective, measure to and from the closest part of it."
)
MARKER_TEXT = (
    "If the location point of an objective does not coincide with a terrain area, you must denote "
    "the location of that objective with a flat, circular marker, 40 mm in diameter, centred on "
    "that point \u2013 this is called an objective marker. Models can move through "
    "objective markers "
    "and they can end a move on top of objective markers.\n"
    'A model is within range of an objective marker while it is within 3" horizontally and 5" '
    "vertically of that objective marker. When measuring distances to and from an objective "
    "marker, measure to and from the closest part of it."
)
CONTROL_TEXT = (
    "At the start of the battle, no objective on the battlefield is controlled by either player. "
    "To gain control of an objective, a player will need one or more models with an OC "
    "characteristic of 1 or more within range of it. A model is within range of a terrain "
    "objective while it is within that terrain area."
)
ALIAS_TEXT = (
    "If a rule refers to an 'objective marker', does this mean an 'objective'?\n"
    "Yes (excluding rules in the Core Rules)'."
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _observation(evidence: dict[str, object]) -> str:
    value = copy.deepcopy(evidence)
    value.update(
        observation_sha256="",
        load_support_status="not_loaded",
        semantic_execution_status="not_certified",
        runtime_consumer_ids=[],
    )
    return _hash(value)


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    specifications = (
        ("terrain-objectives", "14.01", TERRAIN_TEXT),
        ("objectives-not-within-a-terrain-area", "14.01.01", MARKER_TEXT),
        ("terrain-objective-control-range", "14.02", CONTROL_TEXT),
        ("objective-marker-terminology-faq", "FAQ", ALIAS_TEXT),
    )
    for slug, section, source_text in specifications:
        source_id = f"{PACKAGE_ID}:{slug}"
        alias = section == "FAQ"
        provider = "Game Datamissions" if alias else "40k.app"
        url = GDM_URL if alias else FORTY_K_URL
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
        consumers = (
            ["warhammer40k_core.rules.objective_terminology:normalize_objective_rule_text"]
            if alias
            else [
                "warhammer40k_core.engine.objective_geometry:measure_rules_unit_to_objective",
                "warhammer40k_core.engine.objective_control:resolve_objective_control",
            ]
        )
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
        audit = {
            "row_id": slug,
            "provider_name": provider,
            "source_url": url,
            "observed_at": OBSERVED_AT,
            "app_version": "931" if alias else None,
            "policy_id": POLICY,
            "rule_source_id": source_id,
            "transcription_sha256": text_hash,
            "provider_non_affiliation_recorded": True,
        }
        audit_hash = _hash(audit)
        audit_rows.append({**audit, "source_observation_sha256": audit_hash})
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
            "evidence_id": f"core-objectives-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P14 {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        mirror = {
            **shared,
            "evidence_id": f"core-objectives-mirror:{slug}",
            "evidence_kind": "third_party_mirror",
            "authority": "project_authoritative_app_mirror",
            "project_authority_policy_id": POLICY,
            "review_audit_id": AUDIT_ID,
            "review_audit_row_id": slug,
            "review_audit_source_observation_sha256": audit_hash,
            "provider_name": provider,
            "source_title": f"{provider} {section} {slug}",
            "source_platform": "Web",
            "source_url": url,
            "observed_at": None if alias else OBSERVED_AT,
            "app_version": "931" if alias else None,
            "verification_status": "authoritative_app_mirror",
            "provider_non_affiliation_recorded": True,
        }
        for row in (review, mirror):
            row["observation_sha256"] = _observation(row)
            evidence.append(row)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-objectives-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    payload["package_hash"] = _hash(payload)
    audit_payload: dict[str, object] = {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "rows": audit_rows,
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "co_version_comparison": "No co-versioned observation from both providers is present.",
    }
    return payload, audit_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"P14 generated source drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
