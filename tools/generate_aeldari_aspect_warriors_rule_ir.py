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
    / "aeldari_aspect_warriors_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-aspect-warriors-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-aspect-warriors-datasheets-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

FIRE_DRAGONS_DATASHEET_ID = "000000596"
SWOOPING_HAWKS_DATASHEET_ID = "000000600"
WARP_SPIDERS_DATASHEET_ID = "000000601"
ASSURED_DESTRUCTION_ROW_ID = "000000596:2"
GRENADE_PACK_FLYOVER_ROW_ID = "000000600:3"
FLICKERJUMP_ROW_ID = "000000601:3"

DATASHEETS = {
    FIRE_DRAGONS_DATASHEET_ID: "Fire Dragons",
    SWOOPING_HAWKS_DATASHEET_ID: "Swooping Hawks",
    WARP_SPIDERS_DATASHEET_ID: "Warp Spiders",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    ASSURED_DESTRUCTION_ROW_ID: (
        "In your Shooting phase, each time a model in this unit makes a ranged attack that "
        "targets a MONSTER or VEHICLE unit, you can re-roll the Hit roll, you can re-roll "
        "the Wound roll and you can re-roll the Damage roll."
    ),
    GRENADE_PACK_FLYOVER_ROW_ID: (
        "Once per turn, in your Movement phase, when this unit is set up on the battlefield "
        "or ends a Normal, Advance or Fall Back move, it can use this ability. If it does, "
        'select one enemy unit within 8" of and visible to this unit and roll one D6 for each '
        "Swooping Hawks model in this unit: for each 4+, that enemy unit suffers 1 mortal "
        "wound (to a maximum of 6 mortal wounds). Each time this unit uses this ability, until "
        "the end of the turn, you cannot target this unit with the Grenade Stratagem."
    ),
    FLICKERJUMP_ROW_ID: (
        "In your Movement phase, each time this unit is selected to make a Normal move, it can "
        "use this ability. If it does, until the end of the turn, this unit is not eligible to "
        'declare a charge and models in it have a Move characteristic of 24". Each time this '
        "unit uses this ability, at the end of the phase, roll one D6 for each model in this "
        "unit: for each 1, this unit suffers 1 mortal wound."
    ),
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    ASSURED_DESTRUCTION_ROW_ID: "Assured Destruction",
    GRENADE_PACK_FLYOVER_ROW_ID: "Grenade Pack Flyover",
    FLICKERJUMP_ROW_ID: "Flickerjump",
}


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    _validate_source_rows()
    records: dict[str, object] = {}
    for source_row_id, normalized_text in RULE_TEXT_BY_SOURCE_ROW_ID.items():
        rule_ir = _rule_ir(source_row_id, normalized_text)
        records[source_row_id] = {
            "ability_name": ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id],
            "normalized_text_sha256": hashlib.sha256(normalized_text.encode()).hexdigest(),
            "rule_ir": rule_ir.to_payload(),
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
            raise ValueError("Aeldari Aspect Warrior source row is missing.")
        if row["description"] != expected_text:
            raise ValueError("Aeldari Aspect Warrior source text drifted.")
        if row["name"] != ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Aeldari Aspect Warrior ability name drifted.")


def _rule_ir(source_row_id: str, text: str) -> RuleIR:
    if source_row_id == ASSURED_DESTRUCTION_ROW_ID:
        clauses = (_assured_destruction_clause(source_row_id, text),)
    elif source_row_id == GRENADE_PACK_FLYOVER_ROW_ID:
        clauses = (_grenade_pack_flyover_clause(source_row_id, text),)
    elif source_row_id == FLICKERJUMP_ROW_ID:
        clauses = (_flickerjump_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Aeldari Aspect Warrior source row.")
    return RuleIR(
        rule_id=f"phase17l:aeldari:aspect-warriors:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _assured_destruction_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17l:conditional-ranged-attack-full-rerolls",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(text, "each time a model in this unit makes a ranged attack"),
            parameters=_parameters(
                ("attack_kind", "ranged"),
                ("owner", "active_player"),
                ("phase", "shooting"),
                ("subject", "this_unit"),
                ("roll_types", ("hit", "wound", "damage")),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=_span(text, "targets a MONSTER or VEHICLE unit"),
                parameters=_parameters(
                    ("gate_subject", "target_unit"),
                    ("keyword_match", "any"),
                    ("required_keywords", ("MONSTER", "VEHICLE")),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "a model in this unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll the Hit roll",
                ("roll_type", "hit_roll"),
                ("selection", "whole_roll"),
            ),
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll the Wound roll",
                ("roll_type", "wound_roll"),
                ("selection", "whole_roll"),
            ),
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll the Damage roll",
                ("roll_type", "damage_roll"),
                ("selection", "whole_roll"),
            ),
        ),
    )


def _grenade_pack_flyover_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17l:optional-movement-or-setup-flyover-mortal-wounds",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(
                text,
                "when this unit is set up on the battlefield or ends a Normal, Advance or "
                "Fall Back move",
            ),
            parameters=_parameters(
                ("actions", ("set_up", "normal_move", "advance", "fall_back")),
                ("edge", "after"),
                ("owner", "active_player"),
                ("optional", True),
                ("phase", "movement"),
                ("subject", "this_unit"),
                ("timing_window", "movement_move_end_or_setup"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                source_span=_span(text, "Once per turn"),
                parameters=_parameters(("limit", 1), ("period", "turn")),
            ),
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span(text, 'within 8" of'),
                parameters=_parameters(
                    ("distance_inches", 8),
                    ("object_kind", "unit"),
                    ("predicate", "within"),
                    ("subject", "selected_enemy_unit"),
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.VISIBILITY_PREDICATE,
                source_span=_span(text, "visible to this unit"),
                parameters=_parameters(
                    ("object_reference", "this_unit"),
                    ("predicate", "visible_to"),
                    ("subject", "selected_enemy_unit"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span(text, "select one enemy unit"),
            parameters=_parameters(("allegiance", "enemy"), ("selection", "one")),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.INFLICT_MORTAL_WOUNDS,
                "for each 4+, that enemy unit suffers 1 mortal wound (to a maximum of 6 mortal "
                "wounds)",
                ("damage_kind", "mortal_wounds"),
                ("maximum_mortal_wounds", 6),
                ("mortal_wounds_expression", "1"),
                ("required_model_keyword", "SWOOPING HAWKS"),
                ("roll_count_scope", "each_model_in_this_unit"),
                ("roll_expression", "D6"),
                ("success_threshold", 4),
                ("target_scope", "selected_enemy_unit"),
            ),
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "you cannot target this unit with the Grenade Stratagem",
                ("ability", "stratagem_target_restriction"),
                ("forbidden_stratagem_handler_ids", ("core:explosives",)),
                ("target_scope", "this_unit"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span(text, "until the end of the turn"),
            parameters=_parameters(("endpoint", "turn")),
        ),
    )


def _flickerjump_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17l:optional-normal-move-characteristic-set-and-phase-end-risk",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.UNIT_SELECTED,
            source_span=_span(text, "each time this unit is selected to make a Normal move"),
            parameters=_parameters(
                ("action", "normal_move"),
                ("owner", "active_player"),
                ("optional", True),
                ("phase", "movement"),
                ("subject", "this_unit"),
                ("timing_window", "selected_to_make_movement_action"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "this unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.SET_CHARACTERISTIC,
                'models in it have a Move characteristic of 24"',
                ("characteristic", "movement"),
                ("target_scope", "models_in_this_unit"),
                ("value", 24),
            ),
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "this unit is not eligible to declare a charge",
                ("ability", "charge_forbidden"),
                ("target_scope", "this_unit"),
            ),
            _effect(
                text,
                RuleEffectKind.INFLICT_MORTAL_WOUNDS,
                "for each 1, this unit suffers 1 mortal wound",
                ("damage_kind", "mortal_wounds"),
                ("mortal_wounds_expression", "1"),
                ("roll_count_scope", "each_model_in_this_unit_at_phase_end"),
                ("roll_expression", "D6"),
                ("success_values", ("1",)),
                ("target_scope", "this_unit"),
                ("timing_window", "end_of_phase"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span(text, "until the end of the turn"),
            parameters=_parameters(("endpoint", "turn")),
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
    return f"phase17l:aeldari:aspect-warriors:{source_row_id}:clause:{index:03d}"


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


def _sha256_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {**payload, "package_hash": ""}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
