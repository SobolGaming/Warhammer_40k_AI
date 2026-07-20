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
OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "aeldari_autarchs_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-autarchs-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-autarchs-datasheets-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

AUTARCH_DATASHEET_ID = "000000577"
AUTARCH_WAYLEAPER_DATASHEET_ID = "000002759"
SUPERLATIVE_STRATEGIST_ROW_ID = "000000577:3"
ASPECT_TRAINING_ROW_ID = "000000577:5"
INDOMITABLE_STRENGTH_ROW_ID = "000002759:4"

DATASHEETS = {
    AUTARCH_DATASHEET_ID: "Autarch",
    AUTARCH_WAYLEAPER_DATASHEET_ID: "Autarch Wayleaper",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    SUPERLATIVE_STRATEGIST_ROW_ID: (
        "While this model is leading a unit, you can re-roll Advance rolls made for that unit, "
        "and you can re-roll any rolls made for that unit while it is performing an Agile "
        "Manoeuvre."
    ),
    ASPECT_TRAINING_ROW_ID: (
        "- While this model is leading a Howling Banshees unit, it has the Fights First ability.\n"
        "- While this model is leading a Striking Scorpions unit, it has the Infiltrators, "
        'Scouts 7" and Stealth abilities.'
    ),
    INDOMITABLE_STRENGTH_ROW_ID: (
        "While this model is leading a unit, each time you spend a Battle Focus token to enable "
        "that unit to perform an Agile Manoeuvre, roll one D6: on a 3+, you gain 1 Battle Focus "
        "token."
    ),
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    SUPERLATIVE_STRATEGIST_ROW_ID: "Superlative Strategist",
    ASPECT_TRAINING_ROW_ID: "ASPECT TRAINING",
    INDOMITABLE_STRENGTH_ROW_ID: "Indomitable Strength of Will",
}


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    _validate_source_rows()
    records: dict[str, object] = {}
    for source_row_id, normalized_text in RULE_TEXT_BY_SOURCE_ROW_ID.items():
        records[source_row_id] = {
            "ability_name": ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id],
            "normalized_text_sha256": hashlib.sha256(normalized_text.encode()).hexdigest(),
            "rule_ir": _rule_ir(source_row_id, normalized_text).to_payload(),
        }
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
        "datasheets": DATASHEETS,
        "records": records,
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _validate_source_rows() -> None:
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rows_by_id = {row["source_row_id"]: row["fields"] for row in payload["rows"]}
    for source_row_id, expected_text in RULE_TEXT_BY_SOURCE_ROW_ID.items():
        row = rows_by_id.get(source_row_id)
        if row is None:
            raise ValueError("Aeldari Autarch datasheet source row is missing.")
        if row["description"] != expected_text:
            raise ValueError("Aeldari Autarch datasheet source text drifted.")
        if row["name"] != ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Aeldari Autarch datasheet ability name drifted.")


def _rule_ir(source_row_id: str, text: str) -> RuleIR:
    clauses: tuple[RuleClause, ...]
    if source_row_id == SUPERLATIVE_STRATEGIST_ROW_ID:
        clauses = _superlative_strategist_clauses(source_row_id, text)
    elif source_row_id == ASPECT_TRAINING_ROW_ID:
        clauses = _aspect_training_clauses(source_row_id, text)
    elif source_row_id == INDOMITABLE_STRENGTH_ROW_ID:
        clauses = (_indomitable_strength_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Aeldari Autarch datasheet source row.")
    return RuleIR(
        rule_id=f"phase17m:aeldari:autarchs:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _superlative_strategist_clauses(
    source_row_id: str,
    text: str,
) -> tuple[RuleClause, RuleClause]:
    relationship = RuleCondition(
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        source_span=_span(text, "this model is leading a unit"),
        parameters=_parameters(("relationship", "this_model_leading_unit")),
    )
    return (
        RuleClause(
            clause_id=_clause_id(source_row_id, 1),
            template_id="phase17c:roll-reroll-permission",
            source_span=_span(text, "you can re-roll Advance rolls made for that unit"),
            trigger=_after_roll_trigger(text, "advance_roll", "Advance rolls"),
            conditions=(relationship,),
            target=_selected_leading_unit_target(text, "that unit"),
            effects=(
                _effect(
                    text,
                    RuleEffectKind.REROLL_PERMISSION,
                    "re-roll Advance rolls",
                    ("roll_type", "advance_roll"),
                    ("selection", "whole_roll"),
                ),
            ),
        ),
        RuleClause(
            clause_id=_clause_id(source_row_id, 2),
            template_id="phase17m:agile-manoeuvre-roll-reroll",
            source_span=_span(
                text,
                "you can re-roll any rolls made for that unit while it is performing an Agile "
                "Manoeuvre",
            ),
            trigger=_after_roll_trigger(text, "agile_manoeuvre_roll", "any rolls"),
            conditions=(relationship,),
            target=_selected_leading_unit_target(text, "that unit"),
            effects=(
                _effect(
                    text,
                    RuleEffectKind.REROLL_PERMISSION,
                    "re-roll any rolls made for that unit while it is performing an Agile "
                    "Manoeuvre",
                    ("roll_type", "agile_manoeuvre_roll"),
                    ("selection", "whole_roll"),
                ),
            ),
        ),
    )


def _aspect_training_clauses(source_row_id: str, text: str) -> tuple[RuleClause, ...]:
    banshees_sentence = (
        "While this model is leading a Howling Banshees unit, it has the Fights First ability."
    )
    scorpions_sentence = (
        "While this model is leading a Striking Scorpions unit, it has the Infiltrators, "
        'Scouts 7" and Stealth abilities.'
    )
    clauses = [
        _conditional_leader_ability_clause(
            source_row_id=source_row_id,
            clause_index=1,
            text=text,
            sentence=banshees_sentence,
            bodyguard_keyword="HOWLING BANSHEES",
            ability="fights_first",
            effect_text="Fights First ability",
        )
    ]
    for clause_index, ability, effect_text, extra_parameters in (
        (2, "infiltrators", "Infiltrators", ()),
        (3, "scouts", 'Scouts 7"', (("distance_inches", 7.0),)),
        (4, "stealth", "Stealth", ()),
    ):
        clauses.append(
            _conditional_leader_ability_clause(
                source_row_id=source_row_id,
                clause_index=clause_index,
                text=text,
                sentence=scorpions_sentence,
                bodyguard_keyword="STRIKING SCORPIONS",
                ability=ability,
                effect_text=effect_text,
                extra_parameters=extra_parameters,
            )
        )
    return tuple(clauses)


def _conditional_leader_ability_clause(
    *,
    source_row_id: str,
    clause_index: int,
    text: str,
    sentence: str,
    bodyguard_keyword: str,
    ability: str,
    effect_text: str,
    extra_parameters: tuple[tuple[str, RuleParameterValue], ...] = (),
) -> RuleClause:
    relationship_text = sentence.split(",", maxsplit=1)[0]
    return RuleClause(
        clause_id=_clause_id(source_row_id, clause_index),
        template_id="phase17m:conditional-leading-bodyguard-ability-grant",
        source_span=_span(text, sentence),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, relationship_text),
                parameters=_parameters(("relationship", "this_model_leading_unit")),
            ),
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=_span(text, bodyguard_keyword.title()),
                parameters=_parameters(
                    ("gate_subject", "bodyguard_unit"),
                    ("required_keyword", bodyguard_keyword),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                effect_text,
                ("ability", ability),
                ("target_scope", "this_model"),
                *extra_parameters,
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(text, relationship_text),
        ),
    )


def _indomitable_strength_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17m:faction-resource-refund-roll",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "each time you spend a Battle Focus token"),
            parameters=_parameters(
                ("edge", "after"),
                ("resource_kind", "battle_focus_token"),
                ("timing_window", "faction_resource_spent"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, "this model is leading a unit"),
                parameters=_parameters(("relationship", "this_model_leading_unit")),
            ),
            RuleCondition(
                kind=RuleConditionKind.DICE_ROLL_GATE,
                source_span=_span(text, "on a 3+"),
                parameters=_parameters(
                    ("comparison", "greater_than_or_equal"),
                    ("threshold", 3),
                ),
            ),
        ),
        target=_selected_leading_unit_target(text, "that unit"),
        effects=(
            _effect(
                text,
                RuleEffectKind.MODIFY_FACTION_RESOURCE,
                "gain 1 Battle Focus token",
                ("amount", 1),
                ("operation", "gain"),
                ("resource_kind", "battle_focus_token"),
                ("roll_expression", "D6"),
                ("success_threshold", 3),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.IMMEDIATE,
            source_span=_span(text, "gain 1 Battle Focus token"),
        ),
    )


def _after_roll_trigger(text: str, roll_type: str, span_text: str) -> RuleTrigger:
    return RuleTrigger(
        kind=RuleTriggerKind.DICE_ROLL,
        source_span=_span(text, span_text),
        parameters=_parameters(
            ("edge", "after"),
            ("roll_type", roll_type),
            ("subject", "selected_unit"),
        ),
    )


def _selected_leading_unit_target(text: str, span_text: str) -> RuleTargetSpec:
    return RuleTargetSpec(
        kind=RuleTargetKind.SELECTED_UNIT,
        source_span=_span(text, span_text),
        parameters=_parameters(("relationship", "this_model_leading_unit")),
    )


def _effect(
    text: str,
    kind: RuleEffectKind,
    span_text: str,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind,
        source_span=_span(text, span_text),
        parameters=_parameters(*parameters),
    )


def _parameters(*values: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in values)


def _span(text: str, selected: str) -> TextSpan:
    start = text.index(selected)
    return TextSpan(start=start, end=start + len(selected), text=selected)


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17m:aeldari:autarchs:{source_row_id}:clause:{index:03d}"


def _sha256_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
