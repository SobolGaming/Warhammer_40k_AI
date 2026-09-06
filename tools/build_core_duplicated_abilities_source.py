"""Build the reviewed Order 22 source artifacts offline."""

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
    / "core_duplicated_abilities_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/duplicated_abilities_2026_09_06.audit.json"
)
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-duplicated-abilities"
VERSION = "maintained-app-mirrors-observed-2026-09-06"
OBSERVED_AT = "2026-09-06T14:49:36Z"
AUDIT_ID = "core-duplicated-abilities-maintained-app-mirrors-2026-09-06"
FORTY_K_URL = "https://www.40k.app/rules/24-core-abilities"
DUPLICATED_TEXT = (
    "Multiple instances of the same core ability or weapon ability are not cumulative, regardless "
    "of any numbers or keywords included in them. In such cases, the controlling player must "
    "select which instance will apply at any one time. In the case of duplicated weapon abilities, "
    "this selection must be made each time that unit makes attacks, in the Select Weapons step.\n"
    "Multiple instances of core abilities that include a number are duplicated even if that number "
    "varies. However, in the case of Scouts, you must select the lowest number not shared by every "
    'model in that unit (e.g. if every model in a unit has both Scouts 6" and Scouts 8", you could '
    'select Scouts 8" as it is shared by every model, but if a unit contains one model with Scouts '
    '6" and five with Scouts 8", you must select Scouts 6").\n'
    "Multiple instances of weapon abilities that include a number (e.g. [SUSTAINED HITS 1]) are "
    "duplicated even if that number varies (e.g. the controlling player would have to select "
    "between [SUSTAINED HITS 1] and [SUSTAINED HITS 2]).\n"
    "Multiple instances of weapon abilities that include a keyword are duplicated even if that "
    "keyword varies (e.g. the controlling player would have to select between "
    "[ANTI\u2011VEHICLE 4+] "
    "and [ANTI\u2011INFANTRY 2+])."
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
            "duplicated-abilities",
            "24.02",
            DUPLICATED_TEXT,
            [
                "warhammer40k_core.core.ability_sources:datasheet_ability_sources",
                "warhammer40k_core.core.weapon_ability_sources:weapon_ability_sources",
                "warhammer40k_core.core.weapon_ability_sources:grant_weapon_ability",
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
                "semantic_execution_status": "partial_engine_runtime",
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
            "semantic_execution_status": "partial_engine_runtime",
            "runtime_consumer_ids": consumers,
        }
        review = {
            **shared,
            "evidence_id": f"core-duplicated-abilities-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P24C1 {section} {slug}",
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
                "evidence_id": f"core-duplicated-abilities-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-duplicated-abilities-source-v1",
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
            "24.02 retained from the 40k.app search-index observation. The direct fetch returned "
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
                raise SystemExit(f"P24C1 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
