"""Build the reviewed Orders 20/21 source artifacts offline."""

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
    / "core_aura_psychic_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/aura_psychic_2026_09_06.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-aura-psychic"
VERSION = "maintained-app-mirrors-observed-2026-09-06"
OBSERVED_AT = "2026-09-06T12:57:51Z"
AUDIT_ID = "core-aura-psychic-maintained-app-mirrors-2026-09-06"
FORTY_K_URL = "https://www.40k.app/rules/22-other-rules-and-abilities"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"
AURA_TEXT = (
    "Abilities that affect models or units within a stated range are aura abilities, and are "
    "tagged with the word \u2018Aura\u2019.\n"
    "While a model with an aura ability is on the battlefield, it is always within range of "
    "its own aura ability.\n"
    "A unit can be affected by more than one aura ability at a time, but if a unit is within "
    "range of the same aura ability more than once, that aura ability only applies to that "
    "unit once."
)
PSYCHIC_TEXT = (
    "When using psychic abilities with a psychic level, a PSYKER unit cannot use the same "
    "psychic ability more than once per phase."
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
    for slug, section, source_text, consumers in (
        (
            "aura-abilities",
            "22.01",
            AURA_TEXT,
            [
                "warhammer40k_core.engine.rule_aura_resolution:aura_affected_unit_ids",
                "warhammer40k_core.engine.aura_applications:non_stacking_aura_applications",
            ],
        ),
        (
            "psychic-abilities-with-a-psychic-level",
            "22.03.01",
            PSYCHIC_TEXT,
            [
                "warhammer40k_core.engine.psychic_ability_usage:psychic_ability_unavailable_reason",
                "warhammer40k_core.engine.psychic_ability_restore:validate_psychic_usage_history",
            ],
        ),
    ):
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
            "evidence_id": f"core-aura-psychic-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P22/P22B {section} {slug}",
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
        if section == "22.03.01":
            providers.append(("Game Datamissions", GDM_URL, "931"))
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
                "evidence_id": f"core-aura-psychic-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-aura-psychic-source-v1",
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
            "Psychic wording agrees; 40k.app does not expose an App-data version, "
            "so co-version equivalence is not asserted."
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
                raise SystemExit(f"P22/P22B source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
