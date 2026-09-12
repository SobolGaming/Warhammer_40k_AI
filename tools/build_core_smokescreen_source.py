"""Build the reviewed Order 40 source artifacts offline."""

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
    / "core_smokescreen_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/smokescreen_2026_09_12.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-smokescreen"
VERSION = "maintained-app-mirrors-observed-2026-09-12"
OBSERVED_AT = "2026-09-12T11:17:25Z"
AUDIT_ID = "core-smokescreen-maintained-app-mirrors-2026-09-12"
FORTY_K_URL = "https://www.40k.app/rules/15-stratagems"
SMOKESCREEN_TEXT = (
    "WHEN: Start of your opponent\u2019s Shooting phase. "
    "TARGET: One friendly SMOKE unit. "
    "EFFECT: Until the end of the phase, each time an attack targets either your SMOKE unit, "
    "or a unit that is not fully visible to the attacking model because of one or more "
    "models in your SMOKE unit, the target has the benefit of cover against that attack (13.08)."
)
SOURCE_ID = "gw-11e-core-stratagems:core:smokescreen"


def execution_payload() -> dict[str, object]:
    from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleParameter,
        RuleTargetKind,
        RuleTargetSpec,
    )
    from warhammer40k_core.rules.source_data import RuleSourceText

    text = RuleSourceText.from_raw(
        source_id=SOURCE_ID,
        raw_text=SMOKESCREEN_TEXT,
        objective_scope=ObjectiveRuleScope.CORE_RULES,
    ).normalized_text
    span = TextSpan(start=0, end=len(text), text=text)
    rule = RuleIR(
        rule_id=f"{SOURCE_ID}:rule",
        source_id=SOURCE_ID,
        normalized_text=text,
        parser_version="reviewed-core-smokescreen-v1",
        clauses=(
            RuleClause(
                clause_id=f"{SOURCE_ID}:cover",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=span,
                        parameters=(RuleParameter("ability", "cover_from_obscuring_models"),),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=(RuleParameter("endpoint", "phase"),),
                ),
            ),
        ),
    )
    return {"rule_ir": rule.to_payload(), "requires_opponent_turn": True}


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
            "smokescreen",
            "15.10",
            SMOKESCREEN_TEXT,
            [
                "warhammer40k_core.engine.obscuring_model_cover:obscuring_model_cover_sources",
                "warhammer40k_core.engine.attack_sequence_hit_wound:_benefit_of_cover_ballistic_skill_penalty",
            ],
        ),
    ):
        source_id = SOURCE_ID
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
            "evidence_id": f"core-smokescreen-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P15A {section} {slug}",
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
                "evidence_id": f"core-smokescreen-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-smokescreen-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
        "execution_payload": execution_payload(),
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
            "Complete 15.10 operative text reviewed against the 40k.app search-index observation "
            "and the retained GW Core Rules PDF, printed page 57 (PDF page 57). WHEN, TARGET "
            "and EFFECT wording matches, with layout whitespace normalized. The PDF lists "
            "1 CP; the mirror observation also lists 1 CP. The direct mirror fetch returned "
            "403. No App-data version, page capture or co-version mirror comparison is asserted."
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
                raise SystemExit(f"P15A source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
