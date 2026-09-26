"""Build the reviewed Order 87 source artifacts offline."""

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
    / "core_random_profiles_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/random_profiles_2026_09_25.audit.json"
)
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-random-characteristics"
VERSION = "maintained-app-mirrors-observed-2026-09-25"
OBSERVED_AT = "2026-09-25T19:21:58+00:00"
AUDIT_ID = "core-random-characteristics-maintained-app-mirrors-2026-09-25"
GDM_URL = "https://game-datamissions.com/11th/rules/core-rules"
RANDOM_CHARACTERISTICS_TEXT = (
    "Random Movement: When a unit with a random M characteristic is selected to move, "
    "determine the entire unit’s move distance by rolling the indicated number of dice. "  # noqa: RUF001
    "Random Attacks: If a weapon has a random A characteristic, that characteristic is "
    "determined when generating attacks for that weapon at the Resolve Attacks step "
    "(04.03). If several weapons with random A characteristics are making identical "
    "attacks, generate the attacks for each of those weapons individually, and group "
    "them all together. Random Damage: If a weapon has a random D characteristic, "
    "then each time an attack made with it inflicts damage, the controlling player "
    "determines that weapon's characteristic when the opposing player has selected a "
    "model in the target unit to allocate that attack to. When determining a random D "
    "characteristic, the dice roll made is called a damage roll. Where a D characteristic "
    "includes an operator (e.g. a ‘+’, as in D6+1), the value after the operator is part "  # noqa: RUF001
    "of that D characteristic – it is not a modifier. Other Random Characteristics: "  # noqa: RUF001
    "For all other characteristics, roll to determine the value on an individual, "
    "per-model or per-weapon basis each time that characteristic is required."
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
    for slug, section, source_text, url, consumers in (
        (
            "random-characteristics",
            "02.02.03",
            RANDOM_CHARACTERISTICS_TEXT,
            GDM_URL,
            [
                "warhammer40k_core.engine.random_profile_evaluation:"
                "evaluate_unit_profile_characteristics",
                "warhammer40k_core.engine.random_profile_evaluation:evaluate_model_profile_inventory",
                "warhammer40k_core.engine.random_weapon_profiles:evaluate_attack_weapon_profile",
                "warhammer40k_core.engine.random_weapon_range:evaluate_weapon_ranges",
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
            "evidence_id": f"core-random-characteristics-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P02F {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        review["observation_sha256"] = _observation(review)
        evidence.append(review)
        providers: list[tuple[str, str, str | None]] = [("Game Datamissions", url, None)]
        for provider, url, version in providers:
            row_id = f"{slug}:gdm"
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
                "evidence_id": f"core-random-characteristics-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-random-characteristics-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "movement_grouping": (
            "one_independent_roll_per_distinct_expression_per_rules_unit_selection"
        ),
        "movement_grouping_authority": "owner_provisional_interpretation_2026_09_25",
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
            "Complete 02.02.03 observed in the expanded Game Datamissions browser UI "
            "on September 25, corroborating the September 24 Order 84 observation. "
            "The live page exposes no App-data version. No co-version equivalence "
            "or official-App observation is claimed. The official PDF remains "
            "historical provenance."
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
                raise SystemExit(f"P02F source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
