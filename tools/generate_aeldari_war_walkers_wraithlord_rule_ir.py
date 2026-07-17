from __future__ import annotations

import hashlib
import json
from pathlib import Path

from warhammer40k_core.core.attributes import Characteristic
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
    / "aeldari_war_walkers_wraithlord_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-war-walkers-wraithlord-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-war-walkers-wraithlord-datasheets-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

WAR_WALKERS_DATASHEET_ID = "000000612"
WRAITHLORD_DATASHEET_ID = "000000613"
CRYSTALLINE_TARGETING_ROW_ID = "000000612:3"
FATED_HERO_ROW_ID = "000000613:2"
PSYCHIC_GUIDANCE_ROW_ID = "000000613:3"

DATASHEETS = {
    WAR_WALKERS_DATASHEET_ID: "War Walkers",
    WRAITHLORD_DATASHEET_ID: "Wraithlord",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    CRYSTALLINE_TARGETING_ROW_ID: (
        "In your Shooting phase, after this unit has shot, select one enemy unit hit by one "
        "or more of those attacks. Until the end of the phase, each time a friendly AELDARI "
        "unit makes an attack that targets that enemy unit, improve the Armour Penetration "
        "characteristic of that attack by 1. Each unit can only be selected for this ability "
        "once per turn."
    ),
    FATED_HERO_ROW_ID: (
        "At the start of the battle, select one of the following keywords: INFANTRY; MONSTER; "
        "MOUNTED; VEHICLE. Each time this model makes an attack that targets a unit with the "
        "selected keyword, re-roll a Hit roll of 1 and re-roll a Wound roll of 1."
    ),
    PSYCHIC_GUIDANCE_ROW_ID: (
        'While this model is within 12" of one or more friendly Aeldari Psyker models, improve '
        "the Ballistic Skill and Weapon Skill characteristics of weapons equipped by this "
        "model by 1 and it has a Leadership characteristic of 6+."
    ),
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    CRYSTALLINE_TARGETING_ROW_ID: "Crystalline Targeting",
    FATED_HERO_ROW_ID: "Fated Hero",
    PSYCHIC_GUIDANCE_ROW_ID: "Psychic Guidance",
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
    if source_row_id == CRYSTALLINE_TARGETING_ROW_ID:
        clauses = _crystalline_targeting_clauses(source_row_id, text)
    elif source_row_id == FATED_HERO_ROW_ID:
        clauses = (_fated_hero_clause(source_row_id, text),)
    elif source_row_id == PSYCHIC_GUIDANCE_ROW_ID:
        clauses = (_psychic_guidance_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Aeldari datasheet source row.")
    return RuleIR(
        rule_id=f"phase17k:aeldari:war-walkers-wraithlord:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _crystalline_targeting_clauses(
    source_row_id: str,
    text: str,
) -> tuple[RuleClause, RuleClause]:
    selection_text = (
        "In your Shooting phase, after this unit has shot, select one enemy unit hit by one "
        "or more of those attacks."
    )
    effect_text = (
        "Until the end of the phase, each time a friendly AELDARI unit makes an attack that "
        "targets that enemy unit, improve the Armour Penetration characteristic of that attack "
        "by 1. Each unit can only be selected for this ability once per turn."
    )
    return (
        RuleClause(
            clause_id=_clause_id(source_row_id, 1),
            template_id="phase17c:selected-target-constraint",
            source_span=_span(text, selection_text),
            trigger=RuleTrigger(
                kind=RuleTriggerKind.TIMING_WINDOW,
                source_span=_span(text, "after this unit has shot"),
                parameters=_parameters(
                    ("edge", "after"),
                    ("owner", "active_player"),
                    ("phase", "shooting"),
                    ("subject", "this_unit"),
                    ("target_relationship", "hit_by_those_attacks"),
                    ("timing_window", "just_after_friendly_unit_has_shot"),
                ),
            ),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.FREQUENCY_LIMIT,
                    source_span=_span(
                        text,
                        "Each unit can only be selected for this ability once per turn",
                    ),
                    parameters=_parameters(
                        ("maximum_uses", 1),
                        ("scope", "turn"),
                        ("subject", "selected_target_unit"),
                    ),
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.ENEMY_UNIT,
                source_span=_span(text, "one enemy unit hit by one or more of those attacks"),
                parameters=_parameters(
                    ("allegiance", "enemy"),
                    ("target_relationship", "hit_by_those_attacks"),
                ),
            ),
        ),
        RuleClause(
            clause_id=_clause_id(source_row_id, 2),
            template_id="phase17c:characteristic-modifier",
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
                source_span=_span(text, "a friendly AELDARI unit"),
                parameters=_parameters(
                    ("allegiance", "friendly"),
                    ("required_keyword", "AELDARI"),
                ),
            ),
            effects=(
                _effect(
                    text,
                    RuleEffectKind.MODIFY_CHARACTERISTIC,
                    "improve the Armour Penetration characteristic of that attack by 1",
                    ("attack_role", "attacker"),
                    ("characteristic", Characteristic.ARMOR_PENETRATION.value),
                    ("delta", -1),
                ),
            ),
            duration=RuleDuration(
                kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                source_span=_span(text, "Until the end of the phase"),
                parameters=_parameters(("endpoint", "phase")),
            ),
        ),
    )


def _fated_hero_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:start-battle-keyword-choice-reroll",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "At the start of the battle"),
            parameters=_parameters(
                ("edge", "start"),
                ("keyword_options", ("INFANTRY", "MONSTER", "MOUNTED", "VEHICLE")),
                ("phase", "battle"),
                ("subject", "this_model"),
                ("timing_window", "start_battle"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll a Hit roll of 1",
                ("attack_role", "attacker"),
                ("reroll_unmodified_value", 1),
                ("roll_type", "hit"),
                ("target_required_keyword", "selected_keyword"),
                ("timing_window", "attack_sequence.hit"),
            ),
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll a Wound roll of 1",
                ("attack_role", "attacker"),
                ("reroll_unmodified_value", 1),
                ("roll_type", "wound"),
                ("target_required_keyword", "selected_keyword"),
                ("timing_window", "attack_sequence.wound"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.PERMANENT,
            source_span=_span(text, "Each time this model makes an attack"),
        ),
    )


def _psychic_guidance_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:characteristic-set",
        source_span=_span(text, text),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span(
                    text,
                    'this model is within 12" of one or more friendly Aeldari Psyker models',
                ),
                parameters=_parameters(
                    ("distance_inches", 12.0),
                    ("negated", False),
                    ("object_allegiance", "friendly"),
                    ("object_kind", "model"),
                    ("object_quantity", "one_or_more"),
                    ("predicate", "within"),
                    ("required_keyword_sequence", ("AELDARI", "PSYKER")),
                    ("subject", "this_model"),
                ),
            ),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                "Ballistic Skill",
                ("characteristic", Characteristic.BALLISTIC_SKILL.value),
                ("delta", -1),
                ("target_scope", "weapons_equipped_by_this_model"),
            ),
            _effect(
                text,
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                "Weapon Skill",
                ("characteristic", Characteristic.WEAPON_SKILL.value),
                ("delta", -1),
                ("target_scope", "weapons_equipped_by_this_model"),
            ),
            _effect(
                text,
                RuleEffectKind.SET_CHARACTERISTIC,
                "Leadership characteristic of 6+",
                ("characteristic", Characteristic.LEADERSHIP.value),
                ("value", "6+"),
            ),
        ),
    )


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


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:aeldari:war-walkers-wraithlord:{source_row_id}:clause:{index:03d}"


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


def _sha256_payload(payload: dict[str, object]) -> str:
    hash_payload = {**payload, "package_hash": ""}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
