# ruff: noqa: E501, RUF001
"""Build the reviewed Order 33 source artifacts offline."""

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
    / "core_indirect_shooting_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/indirect_shooting_2026_09_09.audit.json"
)
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-indirect-shooting"
VERSION = "maintained-app-mirrors-observed-2026-09-09"
OBSERVED_AT = "2026-09-09T12:02:18.843Z"
AUDIT_ID = "core-indirect-shooting-maintained-app-mirrors-2026-09-09"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"
INDIRECT_TEXT = "INDIRECT SHOOTING\nWhen eligible: All of the following apply to your unit:\n- Unengaged and did not make an advance move this turn.\n- Has one or more [INDIRECT FIRE] weapons.\nEffect: Your unit shoots as described in Making Attacks (04).\nWhile shooting:\n- [INDIRECT FIRE] weapons in your unit can target units that are not visible to the attacking model.\n- Each time an [INDIRECT FIRE] weapon makes an attack:\n  - The target has the benefit of cover against that attack (13.08).\n  - You cannot re‑roll hit rolls.\n  - An unmodified hit roll of 1‑5 fails, unless your unit remained stationary this turn and the target is visible to one or more friendly units, in which case an unmodified hit roll of 1‑3 fails instead.\nAfter shooting: Until the end of the phase, your unit is not eligible to start an action."


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
    for slug, section, source_text, observed_at, source_url, consumers in (
        (
            "indirect-shooting",
            "10.07",
            INDIRECT_TEXT,
            OBSERVED_AT,
            "https://www.40k.app/rules/10-shooting-phase",
            [
                "warhammer40k_core.engine.phases.shooting_declaration_validation:_apply_phase13d_weapon_modifiers",
                "warhammer40k_core.engine.phases.shooting_requests:_shooting_types_for_selected_type_for_rules_unit",
                "warhammer40k_core.engine.attack_sequence_hit_wound:_roll_hit",
            ],
        ),
        (
            "remain-stationary",
            "09.04",
            "REMAIN STATIONARY\nWhen eligible: Any unit.\nEffect: No models are moved (either in straight lines or rotated). Units that remain stationary do not trigger any rules that are triggered when a unit starts or ends a move.",
            "2026-09-09T12:16:21.670Z",
            "https://www.40k.app/rules/09-movement-phase",
            ["warhammer40k_core.engine.phases.shooting_targeting:_rules_unit_remained_stationary"],
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
            "evidence_id": f"core-indirect-shooting-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P10 {section} {slug}",
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
                "evidence_id": f"core-indirect-shooting-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-indirect-shooting-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "attack_policy": {
            "source_rule_id": f"{PACKAGE_ID}:indirect-shooting",
            "no_visible_rule_id": "weapon-ability:indirect-fire:no-visible-target",
            "cover_rule_id": "weapon-ability:indirect-fire:benefit-of-cover",
            "no_hit_rerolls_rule_id": "weapon-ability:indirect-fire:no-hit-rerolls",
            "stationary_visible_rule_id": "weapon-ability:indirect-fire:stationary-friendly-visible",
            "minimum_unmodified_success": 6,
            "stationary_visible_minimum_unmodified_success": 4,
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
            "Complete 10.07 observed directly in the browser. No App version exposed and no "
            "co-version comparison asserted. Partial status excludes the Order 34 Action clause."
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
                raise SystemExit(f"P10 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
