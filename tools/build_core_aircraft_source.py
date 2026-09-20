# ruff: noqa: E501, RUF001
"""Build the reviewed Order 66 source artifacts offline."""

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
    / "core_aircraft_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/aircraft_2026_09_20.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-aircraft"
VERSION = "maintained-app-mirrors-observed-2026-09-20"
OBSERVED_AT = "2026-09-20T14:34:15Z"
AUDIT_ID = "core-aircraft-maintained-app-mirrors-2026-09-20"
FORTY_K_URL = "https://www.40k.app/rules/23-aircraft"
RULES = (
    (
        "deployment",
        "23.01",
        "In the Declare Battle Formations step, all AIRCRAFT units must be placed in strategic reserves (20.01).",
    ),
    (
        "movement",
        "23.02",
        "AIRCRAFT units are only eligible to make an ingress move (20.04); they are not eligible to make any other type of move. At the end of your opponent’s turn, all AIRCRAFT units in your army that are on the battlefield must be placed in strategic reserves. Each time a unit makes any type of move, its models can be moved through AIRCRAFT models. Each time a unit makes a pile-in, consolidation or surge move, unless that unit can FLY, while making that move, ignore AIRCRAFT units for the purposes of selecting enemy units and determining the closest enemy unit. Being engaged solely with one or more AIRCRAFT units does not prevent a unit from being eligible to make a normal or advance move.",
    ),
    (
        "shooting",
        "23.03",
        "The Plunging Fire rule (22.05) has no effect on attacks made by, or targeting, AIRCRAFT units.",
    ),
    (
        "charging-and-fighting",
        "23.04",
        "AIRCRAFT units are not eligible to declare a charge, and can only make melee attacks that target FLYING units. Only FLYING units can select AIRCRAFT units as a charge target, and only FLYING models can make melee attacks that target AIRCRAFT units.",
    ),
)
CONSUMERS = {
    "deployment": [
        "warhammer40k_core.engine.reserve_declarations:apply_mandatory_aircraft_reserve_declarations"
    ],
    "movement": [
        "warhammer40k_core.engine.aircraft_rules:aircraft_movement_target_allowed",
        "warhammer40k_core.engine.aircraft_turn_end:aircraft_turn_end_binding",
        "warhammer40k_core.engine.movement_locks:movement_lock_reason",
    ],
    "shooting": ["warhammer40k_core.engine.shooting_targets:_plunging_fire_applies"],
    "charging-and-fighting": [
        "warhammer40k_core.engine.charge_targets:charge_target_restriction",
        "warhammer40k_core.engine.aircraft_rules:aircraft_melee_target_allowed",
    ],
}


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
    for slug, section, source_text in RULES:
        consumers = CONSUMERS[slug]
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
            "evidence_id": f"core-aircraft-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P23 {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        review["observation_sha256"] = _observation(review)
        evidence.append(review)
        providers: list[tuple[str, str, str | None]] = [("40k.app", FORTY_K_URL, None)]
        for provider, url, version in providers:
            row_id = f"{slug}:{'gdm' if version else '40k-app'}"
            audit: dict[str, object] = {
                "row_id": row_id,
                "provider_name": provider,
                "source_url": url,
                "observed_at": OBSERVED_AT,
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
                "evidence_id": f"core-aircraft-mirror:{row_id}",
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
                "observed_at": None if version else OBSERVED_AT,
                "app_version": version,
                "verification_status": "authoritative_app_mirror",
                "provider_non_affiliation_recorded": True,
            }
            mirror["observation_sha256"] = _observation(mirror)
            evidence.append(mirror)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-aircraft-source-v1",
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
            "23.01–23.04 retained from the 40k.app search-index observation. The direct fetch returned "
            "403. No App-data version or co-version comparison is asserted."
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
                raise SystemExit(f"P23 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
