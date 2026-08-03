from __future__ import annotations

import hashlib
import json
from pathlib import Path

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
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
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as source_overlay,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    REPO_ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / "10th-edition"
    / "2026-06-14"
    / "json"
    / "Datasheets_abilities.json"
)
OFFICIAL_PDF_PATH = (
    REPO_ROOT
    / "data"
    / "raw"
    / "faction_packs"
    / "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children-srspmclqtm-i8ey7hgk2s.pdf"
)
REVIEW_MANIFEST_PATH = (
    REPO_ROOT / "data" / "source_manifests" / "faction_pack_datasheet_review_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "emperors_children_lucius_2026_07"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-emperors-children-lucius-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-emperors-children-lucius-datasheet-2026-07"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEET_ID = "000004083"
DATASHEET_NAME = "Lucius the Eternal"
SUPPORTED_SOURCE_ROW_IDS = (f"{DATASHEET_ID}:5", f"{DATASHEET_ID}:6")
REVIEW_ROW_ID = f"source:{DATASHEET_ID}"
REVIEW_TREATMENT = "unchanged_predecessor"

ABILITY_NAMES = {
    f"{DATASHEET_ID}:5": "A Challenge Worthy of Skill",
    f"{DATASHEET_ID}:6": "Duellist's Hubris",
}


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source_rows = _validated_source_rows(source_payload)
    review_payload = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    review_row = _validated_review_row(review_payload)
    rule_irs = {
        f"{DATASHEET_ID}:5": _challenge_rule_ir(source_rows[f"{DATASHEET_ID}:5"]),
        f"{DATASHEET_ID}:6": _duellists_hubris_rule_ir(source_rows[f"{DATASHEET_ID}:6"]),
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
        "official_document_filename": OFFICIAL_PDF_PATH.name,
        "official_document_sha256": hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest(),
        "official_document_pages": [],
        "review_manifest_filename": REVIEW_MANIFEST_PATH.name,
        "review_manifest_sha256": hashlib.sha256(REVIEW_MANIFEST_PATH.read_bytes()).hexdigest(),
        "review_row_id": review_row["review_row_id"],
        "review_treatment": review_row["treatment"],
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheet_id": DATASHEET_ID,
        "datasheet_name": DATASHEET_NAME,
        "records": {
            source_row_id: {
                "ability_name": ABILITY_NAMES[source_row_id],
                "normalized_text_sha256": hashlib.sha256(
                    rule_ir.normalized_text.encode()
                ).hexdigest(),
                "rule_ir": rule_ir.to_payload(),
            }
            for source_row_id, rule_ir in rule_irs.items()
        },
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _validated_source_rows(source_payload: object) -> dict[str, str]:
    if not isinstance(source_payload, dict) or not isinstance(source_payload.get("rows"), list):
        raise TypeError("Lucius source artifact rows are missing.")
    source_rows: dict[str, str] = {}
    for row in source_payload["rows"]:
        if not isinstance(row, dict) or row.get("source_row_id") not in SUPPORTED_SOURCE_ROW_IDS:
            continue
        fields = row.get("fields")
        if not isinstance(fields, dict):
            raise TypeError("Lucius source row fields are missing.")
        source_row_id = row["source_row_id"]
        if fields.get("datasheet_id") != DATASHEET_ID:
            raise ValueError("Lucius source datasheet identity drifted.")
        if fields.get("name") != ABILITY_NAMES[source_row_id]:
            raise ValueError("Lucius source ability name drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Lucius source ability text is missing.")
        source_rows[source_row_id] = description
    if set(source_rows) != set(SUPPORTED_SOURCE_ROW_IDS):
        raise ValueError("Lucius source-row inventory drifted.")
    return source_rows


def _validated_review_row(review_payload: object) -> dict[str, object]:
    if not isinstance(review_payload, dict) or not isinstance(review_payload.get("factions"), list):
        raise TypeError("Lucius faction-pack review manifest is missing.")
    factions = tuple(
        faction
        for faction in review_payload["factions"]
        if isinstance(faction, dict) and faction.get("faction_id") == "emperors-children"
    )
    if len(factions) != 1 or not isinstance(factions[0].get("rows"), list):
        raise ValueError("Lucius faction-pack review faction identity drifted.")
    faction = factions[0]
    if (
        faction.get("pdf_filename") != OFFICIAL_PDF_PATH.name
        or faction.get("pdf_sha256") != hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("Lucius faction-pack review PDF provenance drifted.")
    rows = tuple(
        row
        for row in faction["rows"]
        if isinstance(row, dict) and row.get("datasheet_id") == DATASHEET_ID
    )
    if len(rows) != 1:
        raise ValueError("Lucius faction-pack review row inventory drifted.")
    row = rows[0]
    if (
        row.get("datasheet_name") != DATASHEET_NAME
        or row.get("review_row_id") != REVIEW_ROW_ID
        or row.get("treatment") != REVIEW_TREATMENT
        or row.get("pdf_page_reference") is not None
    ):
        raise ValueError("Lucius faction-pack review row drifted.")
    return row


def _challenge_rule_ir(text: str) -> RuleIR:
    source_row_id = f"{DATASHEET_ID}:5"
    return _rule_ir(
        source_row_id,
        text,
        (
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17k:conditional-target-keyword-attack-rerolls",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=_span(text, "Each time this model makes an attack"),
                    parameters=_parameters(
                        ("actor", "this_model"),
                        ("roll_types", ("hit", "wound")),
                        ("timing_window", "attack_sequence"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.KEYWORD_GATE,
                        source_span=_span(text, "CHARACTER, MONSTER or WALKER unit"),
                        parameters=_parameters(
                            ("gate_subject", "attack_target"),
                            (
                                "required_keyword_any",
                                ("CHARACTER", "MONSTER", "WALKER"),
                            ),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "this model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.REROLL_PERMISSION,
                        source_span=_span(text, "re-roll the Hit roll"),
                        parameters=_parameters(
                            ("roll_type", "hit_roll"),
                            ("selection", "whole_roll"),
                        ),
                    ),
                    RuleEffectSpec(
                        kind=RuleEffectKind.REROLL_PERMISSION,
                        source_span=_span(text, "re-roll the Wound roll"),
                        parameters=_parameters(
                            ("roll_type", "wound_roll"),
                            ("selection", "whole_roll"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _duellists_hubris_rule_ir(text: str) -> RuleIR:
    source_row_id = f"{DATASHEET_ID}:6"
    return _rule_ir(
        source_row_id,
        text,
        (
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17k:conditional-not-leading-self-ability-grant",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "At the start of the Fight phase"),
                    parameters=_parameters(
                        ("edge", "start"),
                        ("phase", "fight"),
                        ("timing_window", "start_fight_phase"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(text, "if this model is not leading a unit"),
                        parameters=_parameters(
                            ("relationship", "this_model_not_leading_unit"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "this model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(text, "it has the Fights First ability"),
                        parameters=_parameters(
                            ("ability", "fights_first"),
                            ("target_scope", "this_model"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "until the end of the phase"),
                    parameters=_parameters(
                        ("endpoint", "phase"),
                        ("phase", "fight"),
                    ),
                ),
            ),
        ),
    )


def _rule_ir(source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:emperors-children:lucius:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:emperors-children:lucius:datasheet:{source_row_id}:clause:{index:03d}"


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


def _sha256_payload(payload: dict[str, object]) -> str:
    hash_payload = {**payload, "package_hash": ""}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
