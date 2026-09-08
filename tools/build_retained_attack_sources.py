"""Generate the two reviewed, versioned faction consumers for Order 30."""

# Source transcriptions preserve the observed punctuation.
# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId, SourceDocumentId
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
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText

ROOT = Path(__file__).resolve().parents[1]
PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "retained_attack_sources_2026_09/artifacts/package.json"
)
PACKAGE_ID = "reviewed-retained-attack-faction-sources"
VERSION = "app-data-946-observed-2026-09-08"
OBSERVED_AT = "2026-09-08T01:39:45+00:00"
POLICY = "faction-source-policy:maintained-direct-app-data-mirror:2026-09-05"
AUDIT_ID = "retained-attack-faction-app-mirror-2026-09-08"
FOR_THE_CHAPTER_TEXT = (
    "Each time a model in this unit is destroyed, roll one D6: on a 3+, do not remove it "
    "from play. The destroyed model can shoot after the attacking model’s unit has finished "
    "making its attacks, and is then removed from play. When resolving these attacks, any "
    "Hazardous tests taken for that attack are automatically passed.\n"
    "Designer’s Note: This ability is triggered even when a model in this unit is destroyed "
    "as the result of failing a Hazardous test, meaning such a model may be able to shoot "
    "twice in the same phase."
)
UNENDING_FIDELITY_TEXT = (
    "Target: One GREY KNIGHTS INFANTRY unit from your army that was selected as the target "
    "of one or more of the attacking unit’s attacks.\n"
    "When: Your opponent’s Shooting phase or the Fight phase.just after an enemy unit has "
    "selected its targets.\n"
    "Effect: Until the end of the phase, each time a model in your unit is destroyed, if "
    "that model has not shot or fought this phase, roll one D6. On a 4+, do not remove the "
    "destroyed model from play; it can shoot or fight after the attacking unit has finished "
    "making its attacks, and is then removed from play.\n1 CP"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _parameters(**values: RuleParameterValue) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in values.items())


def build_payload() -> dict[str, object]:
    rows = []
    evidence = []
    audits = []
    source_texts = []
    for slug, text, url, actions, threshold, previous, hazardous in (
        (
            "space-marines:hellblaster-squad:for-the-chapter",
            FOR_THE_CHAPTER_TEXT,
            "https://www.40k.app/factions/space-marines/units/hellblaster-squad",
            ("shoot",),
            3,
            False,
            True,
        ),
        (
            "grey-knights:hallowed-conclave:unending-fidelity",
            UNENDING_FIDELITY_TEXT,
            "https://www.40k.app/factions/grey-knights/detachments/hallowed-conclave",
            ("shoot", "fight"),
            4,
            True,
            False,
        ),
    ):
        source_id = f"faction-app:{slug}"
        source = RuleSourceText.from_raw(
            source_id=source_id, raw_text=text, objective_scope=ObjectiveRuleScope.NON_CORE_RULES
        )
        source_texts.append(source)
        normalized = source.normalized_text
        span = TextSpan(text=normalized, start=0, end=len(normalized))
        clause = RuleClause(
            clause_id=f"{source_id}:grant",
            template_id="retained-attack:model-destruction-grant"
            if hazardous
            else "retained-attack:timed-unit-grant",
            source_span=span,
            trigger=RuleTrigger(
                kind=RuleTriggerKind.MODEL_DESTROYED,
                source_span=span,
                parameters=_parameters(
                    destroyed_target="this_model",
                    timing_window="after_attacking_unit_finished_attacks",
                ),
            )
            if hazardous
            else None,
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_MODEL if hazardous else RuleTargetKind.SELECTED_UNIT,
                source_span=span,
            ),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.GRANT_ABILITY,
                    source_span=span,
                    parameters=_parameters(
                        ability="retained_destruction_attack",
                        actions=actions,
                        optional=True,
                        trigger_roll_threshold=threshold,
                        requires_not_shot_or_fought_this_phase=previous,
                        shooting_hazardous_tests_automatically_pass=hazardous,
                    ),
                ),
            ),
            duration=None
            if hazardous
            else RuleDuration(
                kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                source_span=span,
                parameters=_parameters(endpoint="phase"),
            ),
        )
        rule_ir = RuleIR(
            rule_id=f"{source_id}:rule-ir",
            source_id=source_id,
            normalized_text=normalized,
            parser_version="reviewed-retained-attack-v1",
            clauses=(clause,),
        )
        consumer = (
            "warhammer40k_core.engine.retained_attack_grants:static_retained_attack_source"
            if hazardous
            else "warhammer40k_core.engine.retained_attack_grants:persisted_retained_attack_sources"
        )
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        rows.append(
            {
                "source_id": source_id,
                "source_text": text,
                "transcription_sha256": text_hash,
                "rule_ir": rule_ir.to_payload(),
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": [consumer],
                "fieldability_certified": False,
            }
        )
        audit = {
            "audit_id": AUDIT_ID,
            "row_id": slug,
            "provider_name": "40k.app",
            "source_url": url,
            "observed_at": OBSERVED_AT,
            "app_version": "946",
            "policy_id": POLICY,
            "rule_source_id": source_id,
            "transcription_sha256": text_hash,
            "provider_non_affiliation_recorded": True,
        }
        observation_hash = _hash(audit)
        audits.append({**audit, "source_observation_sha256": observation_hash})
        for mirrored in (False, True):
            item: dict[str, object] = {
                "evidence_id": f"{AUDIT_ID}:{slug}:{'mirror' if mirrored else 'transcription'}",
                "rule_source_id": source_id,
                "evidence_kind": "third_party_mirror"
                if mirrored
                else "project_reviewed_app_transcription",
                "authority": "project_authoritative_app_mirror"
                if mirrored
                else "unverified_transcription_only",
                "project_authority_policy_id": POLICY if mirrored else None,
                "review_audit_id": AUDIT_ID if mirrored else None,
                "review_audit_row_id": slug if mirrored else None,
                "review_audit_source_observation_sha256": observation_hash if mirrored else None,
                "provider_name": "40k.app" if mirrored else "CORE V2 Source Review",
                "source_title": slug,
                "source_platform": "Web" if mirrored else "Repository",
                "source_url": url if mirrored else None,
                "observed_at": OBSERVED_AT if mirrored else None,
                "app_version": "946" if mirrored else None,
                "app_build": None,
                "capture_artifact_path": None,
                "capture_sha256": None,
                "transcription_sha256": text_hash,
                "official_corroborating_source_ids": [],
                "verification_status": "authoritative_app_mirror" if mirrored else "unverified",
                "provider_non_affiliation_recorded": mirrored,
                "observation_sha256": "",
                "load_support_status": "not_loaded",
                "semantic_execution_status": "not_certified",
                "runtime_consumer_ids": [],
            }
            item["observation_sha256"] = _hash(item)
            item.update(
                load_support_status="loaded",
                semantic_execution_status="executable_engine_runtime",
                runtime_consumer_ids=[consumer],
            )
            evidence.append(item)
    package_id = DataPackageId(
        namespace="core-v2-reviewed-app-mirror", package_name=PACKAGE_ID, version=VERSION
    )
    catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(version_id=VERSION, source_date=date(2026, 9, 8)),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(
                    package_id=package_id, document_id="retained-attack-consumers"
                ),
                title="Reviewed retained attack faction rules",
                source_texts=tuple(source_texts),
            ),
        ),
        ruleset_bundles=(),
    )
    payload: dict[str, object] = {
        "stratagem_profile": {
            "source_id": "faction-app:grey-knights:hallowed-conclave:unending-fidelity",
            "stratagem_id": "grey-knights-hallowed-conclave-unending-fidelity",
            "detachment_id": "grey-knights-hallowed-conclave",
            "name": "Unending Fidelity",
            "command_point_cost": 1,
            "category": "strategic_ploy",
            "trigger_kind": "after_unit_selected_as_target",
            "phases": ["shooting", "fight"],
            "target_policy_id": "selected_target_unit",
            "required_keywords": ["INFANTRY"],
            "required_faction_keywords": ["GREY KNIGHTS"],
            "opponent_turn_phases": ["shooting"],
        },
        "historical_official_sources": [
            {
                "source_id": f"gw-11e-{faction}-faction-pack-2026-07",
                "source_url": f"https://assets.warhammer-community.com/{filename}",
                "artifact_path": f"data/raw/faction_packs/{filename}",
                "sha256": hashlib.sha256(
                    (ROOT / "data/raw/faction_packs" / filename).read_bytes()
                ).hexdigest(),
                "relationship": "historical_primary_not_current_corroboration",
            }
            for faction, filename in (
                (
                    "space-marines",
                    "eng_22-07_warhammer_40,000_faction_pack_space_marines-631fzvmfjm-2qfrbosgdj.pdf",
                ),
                (
                    "grey-knights",
                    "eng_22-07_warhammer_40,000_faction_pack_grey_knights-dlzvusufhy-uialb3pko4.pdf",
                ),
            )
        ],
        "artifact_schema": "core-v2-retained-attack-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "source_catalog": catalog.to_payload(),
        "rules": rows,
        "evidence": evidence,
        "audit_rows": audits,
        "version_evidence": {
            "source_url": "https://www.40k.app/factions/updates",
            "observed_at": OBSERVED_AT,
            "statement": "Version 946\nReleased 2026-09-02.",
        },
        "capture_method": "browser rendered page and accessibility tree",
        "scope": (
            "Only the two named matched-play rule consumers; no complete faction, "
            "detachment or datasheet fieldability certification."
        ),
        "package_hash": "",
    }
    payload["package_hash"] = _hash(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build_payload(), indent=2, ensure_ascii=False) + "\n").encode()
    if args.check:
        if PATH.read_bytes() != raw:
            raise SystemExit("Retained attack source artifact drift.")
    else:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
