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
    / "aeldari_wave_serpent_shining_spears_eldrad_dire_avengers_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-rule-ir-v1"
SOURCE_PACKAGE_ID = (
    "gw-11e-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-datasheets-2026-06-14"
)
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

ELDRAD_ULTHRAN_DATASHEET_ID = "000000568"
DIRE_AVENGERS_DATASHEET_ID = "000000593"
WAVE_SERPENT_DATASHEET_ID = "000000599"
SHINING_SPEARS_DATASHEET_ID = "000000602"

DOOM_ROW_ID = "000000568:4"
BLADESTORM_ROW_ID = "000000593:2"
WAVE_SERPENT_SHIELD_ROW_ID = "000000599:3"
EXTREME_MOBILITY_ROW_ID = "000000602:2"

DATASHEETS = {
    ELDRAD_ULTHRAN_DATASHEET_ID: "Eldrad Ulthran",
    DIRE_AVENGERS_DATASHEET_ID: "Dire Avengers",
    WAVE_SERPENT_DATASHEET_ID: "Wave Serpent",
    SHINING_SPEARS_DATASHEET_ID: "Shining Spears",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    DOOM_ROW_ID: (
        'At the end of your Movement phase, select one enemy unit within 18" of and visible '
        "to this model. Until the start of your next Command phase, each time a friendly "
        "AELDARI model makes an attack that targets that enemy unit, add 1 to the Wound roll."
    ),
    BLADESTORM_ROW_ID: (
        "Ranged weapons equipped by models in this unit have the [SUSTAINED HITS 1] ability "
        "while targeting an enemy unit within half range."
    ),
    WAVE_SERPENT_SHIELD_ROW_ID: (
        "Each time a ranged attack targets this model, if the Strength characteristic of "
        "that attack is greater than the Toughness characteristic of this model, subtract "
        "1 from the Wound roll."
    ),
    EXTREME_MOBILITY_ROW_ID: (
        "Each time this unit makes a Normal, Advance, Fall Back or Charge move, ignore any "
        "vertical distance when determining the total distance models in this unit can be "
        "moved during that move."
    ),
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    DOOM_ROW_ID: "Doom (Psychic)",
    BLADESTORM_ROW_ID: "Bladestorm",
    WAVE_SERPENT_SHIELD_ROW_ID: "Wave Serpent Shield",
    EXTREME_MOBILITY_ROW_ID: "Extreme Mobility",
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
            raise ValueError("Aeldari datasheet source row is missing.")
        if row["description"] != expected_text:
            raise ValueError("Aeldari datasheet source text drifted.")
        if row["name"] != ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Aeldari datasheet ability name drifted.")


def _rule_ir(source_row_id: str, text: str) -> RuleIR:
    clauses: tuple[RuleClause, ...]
    if source_row_id == DOOM_ROW_ID:
        clauses = _doom_clauses(source_row_id, text)
    elif source_row_id == BLADESTORM_ROW_ID:
        clauses = (_bladestorm_clause(source_row_id, text),)
    elif source_row_id == WAVE_SERPENT_SHIELD_ROW_ID:
        clauses = (_wave_serpent_shield_clause(source_row_id, text),)
    elif source_row_id == EXTREME_MOBILITY_ROW_ID:
        clauses = (_extreme_mobility_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Aeldari datasheet source row.")
    return RuleIR(
        rule_id=f"phase17p:aeldari:four-datasheets:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _doom_clauses(source_row_id: str, text: str) -> tuple[RuleClause, RuleClause]:
    selection_text = (
        'At the end of your Movement phase, select one enemy unit within 18" of and visible '
        "to this model."
    )
    effect_text = (
        "Until the start of your next Command phase, each time a friendly AELDARI model "
        "makes an attack that targets that enemy unit, add 1 to the Wound roll."
    )
    return (
        RuleClause(
            clause_id=_clause_id(source_row_id, 1),
            template_id="phase17c:selected-target-constraint",
            source_span=_span(text, selection_text),
            trigger=RuleTrigger(
                kind=RuleTriggerKind.TIMING_WINDOW,
                source_span=_span(text, "At the end of your Movement phase"),
                parameters=_parameters(
                    ("edge", "end"),
                    ("owner", "active_player"),
                    ("phase", "movement"),
                    ("subject", "this_model"),
                    ("timing_window", "movement_phase_end"),
                ),
            ),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.DISTANCE_PREDICATE,
                    source_span=_span(text, 'within 18" of'),
                    parameters=_parameters(
                        ("distance_inches", 18.0),
                        ("negated", False),
                        ("object_kind", "model"),
                        ("object_reference", "this"),
                        ("predicate", "within"),
                        ("qualifier", None),
                        ("range_kind", "numeric_range"),
                    ),
                ),
                RuleCondition(
                    kind=RuleConditionKind.VISIBILITY_PREDICATE,
                    source_span=_span(text, "visible to this model"),
                    parameters=_parameters(
                        ("observer", "this_model"),
                        ("predicate", "visible_to"),
                        ("target_reference", "selected_unit"),
                    ),
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.ENEMY_UNIT,
                source_span=_span(text, "one enemy unit"),
                parameters=_parameters(("allegiance", "enemy")),
            ),
        ),
        RuleClause(
            clause_id=_clause_id(source_row_id, 2),
            template_id="phase17c:dice-roll-modifier",
            source_span=_span(text, effect_text),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.TARGET_CONSTRAINT,
                    source_span=_span(text, "targets that enemy unit"),
                    parameters=_parameters(
                        ("gate_subject", "attack_target"),
                        ("relationship", "attack_targets_selected_unit"),
                        ("target_reference", "selected_unit"),
                    ),
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.FRIENDLY_UNIT,
                source_span=_span(text, "a friendly AELDARI model"),
                parameters=_parameters(
                    ("allegiance", "friendly"),
                    ("required_keyword", "AELDARI"),
                ),
            ),
            effects=(
                _effect(
                    text,
                    RuleEffectKind.MODIFY_DICE_ROLL,
                    "add 1 to the Wound roll",
                    ("attack_role", "attacker"),
                    ("delta", 1),
                    ("roll_type", "wound"),
                ),
            ),
            duration=RuleDuration(
                kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                source_span=_span(text, "Until the start of your next Command phase"),
                parameters=_parameters(
                    ("battle_round_offset", 1),
                    ("boundary", "start"),
                    ("endpoint", "phase"),
                    ("owner", "source_player"),
                    ("phase", "command"),
                ),
            ),
        ),
    )


def _bladestorm_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17p:half-range-weapon-ability-grant",
        source_span=_span(text, text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span(text, "within half range"),
                parameters=_parameters(
                    ("predicate", "within_half_range"),
                    ("range_reference", "weapon_range"),
                    ("subject", "target_unit"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "models in this unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                "[SUSTAINED HITS 1] ability",
                ("attack_role", "attacker"),
                ("weapon_ability", "Sustained Hits"),
                ("weapon_ability_value", 1),
                ("weapon_scope", "ranged"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(text, "while targeting an enemy unit within half range"),
        ),
    )


def _wave_serpent_shield_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17p:defensive-strength-toughness-wound-modifier",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(text, "Each time a ranged attack targets this model"),
            parameters=_parameters(
                ("attack_kind", "ranged"),
                ("attack_role", "target"),
                ("timing_window", "attack_sequence.wound"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.MODIFY_DICE_ROLL,
                "subtract 1 from the Wound roll",
                ("attack_role", "target"),
                ("delta", -1),
                ("roll_type", "wound"),
                ("target_constraint", "attack_strength_greater_than_target_toughness"),
                ("weapon_scope", "ranged"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(
                text,
                "if the Strength characteristic of that attack is greater than the Toughness "
                "characteristic of this model",
            ),
        ),
    )


def _extreme_mobility_clause(source_row_id: str, text: str) -> RuleClause:
    movement_modes = ("normal", "advance", "fall_back", "charge")
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17p:movement-ignore-vertical-distance",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(
                text,
                "Each time this unit makes a Normal, Advance, Fall Back or Charge move",
            ),
            parameters=_parameters(
                ("edge", "during"),
                ("movement_modes", movement_modes),
                ("phase", "movement"),
                ("subject", "this_unit"),
                ("timing_window", "unit_makes_move"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "this unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                "ignore any vertical distance",
                ("movement_modes", movement_modes),
                ("permission", "ignore_vertical_distance"),
            ),
        ),
    )


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17p:aeldari:four-datasheets:{source_row_id}:clause:{index:03d}"


def _effect(
    text: str,
    kind: RuleEffectKind,
    fragment: str,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind,
        source_span=_span(text, fragment),
        parameters=_parameters(*parameters),
    )


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
