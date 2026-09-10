# ruff: noqa: E501, RUF001
"""Build the reviewed Order 34 source artifacts offline."""

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
    / "core_actions_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/actions_2026_09_09.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-actions"
VERSION = "maintained-app-mirrors-observed-2026-09-09"
OBSERVED_AT = "2026-09-09T14:50:00+00:00"
AUDIT_ID = "core-actions-maintained-app-mirrors-2026-09-09"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"
OBSERVED_RULES = (
    (
        "performing-actions",
        "16.01",
        "PERFORMING ACTIONS\nSome rules allow units to perform actions. Each action states:\n- STARTS: When it is started.\n- UNITS: Which friendly units can perform it.\n- USE LIMIT: How many times friendly units can start it.\n- COMPLETES: When it completes.\n- EFFECT: What the effects of completing it are.\n- Any additional restrictions that may apply.\nSTARTING AN ACTION\nA unit is eligible to start an action unless one or more of the following apply to that unit:\n- It is not on the battlefield.\n- It is an AIRCRAFT/FORTIFICATION unit.\n- It is battle-shocked.\n- It has an OC characteristic of 0 or ‘-’.\n- It is engaged (unless it is a TITANIC unit).\n- It made an advance or fall-back move this turn.\n- It started another action this turn.\nIf a unit starts an action, until the end of the turn:\n- It is not eligible to shoot (excluding TITANIC units).\n- It is not eligible to declare a charge.\nCOMPLETING AN ACTION\nIf a unit performing an action makes a move (excluding pile-in and consolidation moves) or leaves the battlefield, that unit does not complete that action. Otherwise, when an action is completed, its ‘Effect’ section is triggered.",
        "https://www.40k.app/rules/16-actions",
    ),
    (
        "normal-shooting",
        "10.04",
        "NORMAL SHOOTING\nWhen eligible: Your unit is unengaged and did not make an advance move this turn.\nEffect: Your unit shoots as described in Making Attacks (04).\nAfter shooting: Until the end of the phase, your unit is not eligible to start an action.",
        "https://www.40k.app/rules/10-shooting-phase",
    ),
    (
        "assault-shooting",
        "10.05",
        "ASSAULT SHOOTING\nWhen eligible: All of the following apply to your unit:\n- Unengaged and made an advance move this turn.\n- Has one or more [ASSAULT] weapons.\nEffect: Your unit shoots as described in Making Attacks (04).\nWhile shooting: You can only select [ASSAULT] weapons to make attacks with.\nAfter shooting: Until the end of the phase, your unit is not eligible to start an action.",
        "https://www.40k.app/rules/10-shooting-phase",
    ),
    (
        "close-quarters-shooting",
        "10.06",
        "CLOSE-QUARTERS SHOOTING\nWhen eligible: All of the following apply to your unit:\n- Engaged and did not make an advance move this turn.\n- Has one or more [CLOSE‑QUARTERS] weapons or is a MONSTER/VEHICLE unit.\nEffect: Your unit shoots as described in Making Attacks (04).\nWhile shooting: Models in your unit can target enemy units your unit is engaged with.\n- MONSTER/VEHICLE Models: Each time a MONSTER/VEHICLE model in your unit makes an attack:\n  - Unless that attack is made with a [CLOSE‑QUARTERS] weapon and targets a unit your unit is engaged with, subtract 1 from the hit roll.\n  - If that attack is made with a [BLAST] weapon, it still cannot target a unit your unit is engaged with.\n- Non-MONSTER/Non-VEHICLE Models: You can only select [CLOSE‑QUARTERS] weapons to make attacks with and you can only select enemy units that are engaged with your unit as targets.\nAfter shooting: Until the end of the phase, your unit is not eligible to start an action.",
        "https://www.40k.app/rules/10-shooting-phase",
    ),
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
    for slug, section, source_text, source_url in OBSERVED_RULES:
        observed_at = OBSERVED_AT
        consumers = [
            "warhammer40k_core.engine.activity_restrictions:record_action_restriction"
            if slug == "performing-actions"
            else "warhammer40k_core.engine.activity_restrictions:record_completed_shooting_restriction",
            "warhammer40k_core.engine.mission_action_eligibility:mission_action_unit_ineligibility_reason",
        ]
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
            "evidence_id": f"core-actions-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P16 {section} {slug}",
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
                "evidence_id": f"core-actions-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-actions-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "restriction_policy": {
            "action_source_rule_id": f"{PACKAGE_ID}:performing-actions",
            "after_shooting_descriptor_id": "core:after-shooting-action-restriction",
            "after_shooting_source_rule_ids": [
                f"{PACKAGE_ID}:normal-shooting",
                f"{PACKAGE_ID}:assault-shooting",
                f"{PACKAGE_ID}:close-quarters-shooting",
                "gw-11e-core-indirect-shooting:indirect-shooting",
                "gw-11e-core-stratagems:rule:snap-shooting",
            ],
            "action_expiration": "end_turn",
            "shooting_expiration": "end_phase",
            "shooting_exempt_keyword": "TITANIC",
        },
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
            "Complete 16.01 and 10.04-10.06 observed in the browser. No App version exposed; "
            "no co-version comparison asserted. Only Action restriction semantics are certified. "
            "10.07 and 15.09 reuse their retained authenticated source packages."
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
                raise SystemExit(f"P16 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
