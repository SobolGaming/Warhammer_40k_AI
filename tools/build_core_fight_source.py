"""Build the reviewed P12 source artifact offline; never fetch runtime inputs."""

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
    / "core_fight_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/fight_2026_09_05.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-fight"
VERSION = "maintained-app-mirrors-observed-2026-09-05"
OBSERVED_AT = "2026-09-05T18:32:47-04:00"
AUDIT_ID = "core-fight-maintained-app-mirrors-2026-09-05"
FORTY_K_URL = "https://www.40k.app/rules/12-fight-phase"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"

CONSOLIDATE_TEXT = (
    "When eligible: It is the Fight phase and your unit was eligible to fight this phase.\n"
    'Maximum distance: 3"\nEffect: Your unit moves as described in Moving (03).\n'
    "Before moving: Select consolidation mode:\n"
    "Ongoing Consolidation: If your unit is engaged, you must select this mode and select every "
    "enemy unit it is engaged with.\n"
    'Engaging Consolidation: Otherwise, if your unit is within 3" of one or more enemy units, '
    "you must select this mode and select one or more of those enemy units.\n"
    'Objective Consolidation: Otherwise, if your unit is within 3" of one or more objectives, '
    "you must select this mode and select one of those objectives.\n"
    "While moving:\n"
    "Ongoing Consolidation: Models in base\u2011contact with one or more enemy models cannot be "
    "moved. Each model that is moved must end its move closer to the closest selected enemy "
    "unit, and engaged with it if possible.\n"
    "Engaging Consolidation: Each model that is moved must end its move closer to the closest "
    "selected enemy unit, and engaged with it if possible.\n"
    "Objective Consolidation: Each model that is moved must end its move within range of the "
    "selected objective if possible, or closer to it if not.\n"
    "After moving:\n"
    "Ongoing Consolidation: Each model that started this move engaged with an enemy unit must "
    "still be engaged with that enemy unit.\n"
    "Engaging Consolidation: Your unit must be engaged with all of the selected enemy units. "
    "If one or more enemy units engaged with your unit have not been selected to fight this "
    "phase, your opponent must select each of those units, one at a time; when each is selected, "
    "it becomes eligible to fight and is selected to fight (12.04).\n"
    "Objective Consolidation: Your unit must be unengaged and within range "
    "of the selected objective."
)
ONGOING_ERRATUM_TEXT = (
    "Each model that started this move engaged with an enemy unit must still be engaged with "
    "that enemy unit. If one or more enemy units engaged with your unit have not been selected "
    "to fight this phase, your opponent must select each of those units, one at a time; when "
    "each is selected, it becomes eligible to fight and is selected to fight"
)
STEP_TEXT = (
    "Both players make consolidation moves (12.08) with all of their eligible units they choose "
    "to move. The \u2018Eligible If\u2019 section describes which units are eligible to make such "
    "moves. The player whose turn it is resolves all of their moves first, followed by their "
    "opponent. Each unit cannot make more than one consolidation move during this step."
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
        ("consolidation-move", "12.08", CONSOLIDATE_TEXT),
        ("ongoing-consolidation-erratum", "Errata", ONGOING_ERRATUM_TEXT),
        ("consolidate-step", "12.07", STEP_TEXT),
    )
    for slug, section, source_text in specifications:
        source_id = f"{PACKAGE_ID}:{slug}"
        alias = section == "Errata"
        provider = "Game Datamissions" if alias else "40k.app"
        url = GDM_URL if alias else FORTY_K_URL
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
        consumers = (
            ["warhammer40k_core.engine.consolidation_fight_queue:start_consolidation_fight_queue"]
            if alias
            else (
                ["warhammer40k_core.engine.phases.fight:FightPhaseHandler"]
                if section == "12.07"
                else [
                    "warhammer40k_core.engine.consolidation_validation:validate_consolidation",
                    "warhammer40k_core.engine.consolidation_model_constraints:consolidation_model_violation",
                    "warhammer40k_core.engine.consolidation_fight_queue:start_consolidation_fight_queue",
                ]
            )
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
            "evidence_id": f"core-fight-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P12 {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        mirror = {
            **shared,
            "evidence_id": f"core-fight-mirror:{slug}",
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
        "artifact_schema": "core-v2-core-fight-source-v1",
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
                raise SystemExit(f"P12 generated source drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
