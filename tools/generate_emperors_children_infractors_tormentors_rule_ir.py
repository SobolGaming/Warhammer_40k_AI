from __future__ import annotations

import hashlib
import json
from pathlib import Path

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
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
    / "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json"
    / "Datasheets_abilities.json"
)
OFFICIAL_PDF_PATH = (
    REPO_ROOT
    / "data/raw/faction_packs"
    / "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children-srspmclqtm-i8ey7hgk2s.pdf"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "emperors_children_infractors_tormentors_2026_08/artifacts/rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-emperors-children-infractors-tormentors-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-emperors-children-infractors-tormentors-datasheets-2026-08"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEETS = {"000004079": "Tormentors", "000004080": "Infractors"}
ABILITY_NAMES = {
    "000004079:3": "Objective Defiled",
    "000004079:4": "Icon of Excess",
    "000004080:3": "Excessive Assault",
    "000004080:4": "Icon of Excess",
}


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source_rows = _validated_source_rows(source_payload)
    rule_irs = {
        source_row_id: _rule_ir_for_source_row(source_row_id, text)
        for source_row_id, text in source_rows.items()
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
        "official_document_filename": OFFICIAL_PDF_PATH.name,
        "official_document_sha256": hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest(),
        "official_document_pages": [9],
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheets": DATASHEETS,
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
        raise TypeError("Infractors/Tormentors source artifact rows are missing.")
    source_rows: dict[str, str] = {}
    for row in source_payload["rows"]:
        if not isinstance(row, dict) or row.get("source_row_id") not in ABILITY_NAMES:
            continue
        fields = row.get("fields")
        if not isinstance(fields, dict):
            raise TypeError("Infractors/Tormentors source row fields are missing.")
        source_row_id = row["source_row_id"]
        datasheet_id = source_row_id.split(":", maxsplit=1)[0]
        if fields.get("datasheet_id") != datasheet_id:
            raise ValueError("Infractors/Tormentors source datasheet identity drifted.")
        if fields.get("name") != ABILITY_NAMES[source_row_id]:
            raise ValueError("Infractors/Tormentors source ability name drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Infractors/Tormentors source ability text is missing.")
        source_rows[source_row_id] = description
    if set(source_rows) != set(ABILITY_NAMES):
        raise ValueError("Infractors/Tormentors source-row inventory drifted.")
    return source_rows


def _rule_ir_for_source_row(source_row_id: str, text: str) -> RuleIR:
    clauses: tuple[RuleClause, ...]
    if source_row_id == "000004079:3":
        clauses = (_objective_defiled_clause(source_row_id, text),)
    elif source_row_id in {"000004079:4", "000004080:4"}:
        clauses = tuple(
            _icon_of_excess_clause(source_row_id, text, index=index, phase=phase)
            for index, phase in enumerate(("shooting", "fight"), start=1)
        )
    elif source_row_id == "000004080:3":
        clauses = (_excessive_assault_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Infractors/Tormentors source row.")
    return RuleIR(
        rule_id=f"phase17n:emperors-children:battleline:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _objective_defiled_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17n:command-end-sticky-objective-control",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "At the end of your Command phase"),
            parameters=_parameters(
                ("edge", "end"),
                ("owner", "active_player"),
                ("phase", "command"),
                ("subject", "this_unit"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(
                    text, "if this unit is within range of an objective marker you control"
                ),
                parameters=_parameters(
                    ("gate_subject", "source_unit"),
                    ("relationship", "source_unit_within_controlled_objective"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "this unit"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span(text, "that objective marker remains under your control"),
                parameters=_parameters(
                    ("objective_scope", "controlled_objective_within_source_unit_range"),
                    (
                        "retention_end_condition",
                        "opponent_level_of_control_greater_than_source_player",
                    ),
                    ("status", "sticky_objective_control"),
                ),
            ),
        ),
    )


def _excessive_assault_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17n:conditional-objective-wound-reroll",
        source_span=_span(text, text),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "this unit"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.REROLL_PERMISSION,
                source_span=_span(text, "re-roll a Wound roll of 1"),
                parameters=_parameters(
                    ("attack_kind", "melee"),
                    ("full_reroll_if_target_within_objective_range", True),
                    ("reroll_unmodified_value", 1),
                    ("roll_type", "wound"),
                ),
            ),
        ),
    )


def _icon_of_excess_clause(
    source_row_id: str,
    text: str,
    *,
    index: int,
    phase: str,
) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, index),
        template_id="phase17n:phase-end-destruction-leadership-command-point-gain",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "At the end of your Shooting phase or the Fight phase"),
            parameters=_parameters(
                ("edge", "end"),
                ("owner", "active_player"),
                ("phase", phase),
                ("subject", "this_unit"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(
                    text, "if the bearer's unit destroyed one or more enemy units that phase"
                ),
                parameters=_parameters(
                    ("gate_subject", "source_unit"),
                    ("relationship", "source_unit_destroyed_enemy_unit_this_phase"),
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.DICE_ROLL_GATE,
                source_span=_span(text, "the bearer's unit takes a Leadership test"),
                parameters=_parameters(
                    ("comparison", "greater_or_equal"),
                    ("roll_count", 2),
                    ("roll_expression", "2D6"),
                    ("roll_type", "leadership"),
                    ("success_threshold_source", "target_leadership"),
                    ("test_target", "this_unit"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.PLAYER,
            source_span=_span(text, "you gain 1CP"),
            parameters=_parameters(("relationship", "source_player")),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=_span(text, "gain 1CP"),
                parameters=_parameters(
                    ("affected_player", "source_player"),
                    ("delta", 1),
                    ("operation", "gain"),
                ),
            ),
        ),
    )


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17n:emperors-children:battleline:datasheet:{source_row_id}:clause:{index:03d}"


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
