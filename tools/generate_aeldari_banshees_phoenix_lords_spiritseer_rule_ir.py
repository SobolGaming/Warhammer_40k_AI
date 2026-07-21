from __future__ import annotations

import hashlib
import json
from pathlib import Path

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
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
from warhammer40k_core.rules.source_data import RuleSourceText

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
    / "aeldari_banshees_phoenix_lords_spiritseer_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-banshees-phoenix-lords-spiritseer-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-banshees-phoenix-lords-spiritseer-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

DATASHEETS = {
    "000000572": "Jain Zar",
    "000000574": "Fuegan",
    "000000588": "Spiritseer",
    "000000594": "Howling Banshees",
    "000003909": "Lhykhis",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    "000000572:4": (
        "While this model is leading a unit, each time that unit Advances, do not make an "
        'Advance roll. Instead, until the end of the phase, add 6" to the Move characteristic '
        "of models in that unit and each time a model in that unit makes an Advance move, "
        "ignore any vertical distance when determining the total distance that model can be "
        "moved during that move."
    ),
    "000000572:5": (
        "Each time this model makes an attack that targets a CHARACTER unit, you can re-roll "
        "the Wound roll."
    ),
    "000000574:3": (
        'While this model is leading a unit, add 6" to the Range characteristic of Melta '
        "weapons equipped by models in that unit."
    ),
    "000000574:4": (
        "The first time this model is destroyed, at the end of the phase, roll one D6: on a "
        "2+, set this model back up on the battlefield as close as possible to where it was "
        "destroyed and not within Engagement Range of one or more enemy units, with its full "
        "wounds remaining."
    ),
    "000000588:3": (
        'While this model is within 3" of one or more friendly Wraith Construct units, this '
        "model has the Lone Operative ability."
    ),
    "000000588:4": (
        "Once per turn, in your Movement phase, when this model starts or ends a move, select "
        'one friendly Wraith Construct unit within 6" of this model (excluding TITANIC units) '
        "and one enemy unit visible to this model. Until the start of your next Movement phase, "
        "weapons equipped by models in that friendly unit have the [SUSTAINED HITS 1] ability "
        "while targeting that enemy unit."
    ),
    "000000588:5": (
        'In your Command phase, select one friendly Wraith Construct unit within 6" of this '
        "model. If one or more models in that unit are destroyed, you can return one destroyed "
        "model to that unit. Otherwise, one model in that unit regains up to D3 lost wounds. "
        "Each unit can only be selected for this ability once per turn."
    ),
    "000000594:3": (
        "This unit is eligible to declare a charge in a turn in which it Advanced or Fell Back."
    ),
    "000003909:4": (
        "While this model is leading a unit, that unit is eligible to declare a charge in a "
        "turn in which it used its Flickerjump ability."
    ),
    "000003909:5": (
        "In your Shooting phase, after this model has shot, select one enemy unit hit by one or "
        "more of those attacks. Until the end of the turn, each time a friendly Aeldari model "
        "makes an attack that targets that unit, an unmodified Hit roll of 5+ scores a Critical "
        "Hit."
    ),
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    "000000572:4": "Whirling Death",
    "000000572:5": "Storm of Silence",
    "000000574:3": "Burning Lance",
    "000000574:4": "Unquenchable Resolve",
    "000000588:3": "Spiritseer",
    "000000588:4": "Spirit Mark (Psychic)",
    "000000588:5": "Tears of Isha (Psychic)",
    "000000594:3": "Acrobatic",
    "000003909:4": "Empyric Ambush",
    "000003909:5": "Whispering Web",
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
            raise ValueError("Aeldari datasheet source row is missing.")
        if row["description"] != expected_text:
            raise ValueError("Aeldari datasheet source text drifted.")
        if row["name"] != ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Aeldari datasheet ability name drifted.")


def _rule_ir(source_row_id: str, text: str) -> RuleIR:
    source_id = f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}"
    if source_row_id in {"000000572:5", "000003909:5"}:
        compiled = compile_rule_source_text(
            RuleSourceText.from_raw(source_id=source_id, raw_text=text),
            source_keyword_sequence_parts=("AELDARI",),
        ).rule_ir
        if not compiled.is_supported:
            raise ValueError("Aeldari compiler-backed RuleIR became unsupported.")
        return compiled
    builders = {
        "000000572:4": _whirling_death_clause,
        "000000574:3": _burning_lance_clause,
        "000000574:4": _unquenchable_resolve_clause,
        "000000588:3": _spiritseer_clause,
        "000000588:4": _spirit_mark_clause,
        "000000588:5": _tears_of_isha_clause,
        "000000594:3": _acrobatic_clause,
        "000003909:4": _empyric_ambush_clause,
    }
    builder = builders.get(source_row_id)
    if builder is None:
        raise ValueError("Unsupported Aeldari source row.")
    return RuleIR(
        rule_id=f"phase17n:aeldari:datasheet:{source_row_id}",
        source_id=source_id,
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=(builder(source_row_id, text),),
    )


def _whirling_death_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:conditional-leading-fixed-advance",
        conditions=(_leading_condition(text),),
        target=_target(
            text,
            RuleTargetKind.SELECTED_UNIT,
            "that unit",
            ("relationship", "this_model_leading_unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT,
                "do not make an Advance roll",
                ("roll_type", "advance"),
                ("fixed_result", 6),
                ("skip_roll", True),
            ),
            _effect(
                text,
                RuleEffectKind.MODIFY_MOVE_DISTANCE,
                'add 6" to the Move characteristic',
                ("characteristic", "movement"),
                ("delta", 6),
                ("target_scope", "models_in_leading_unit"),
            ),
            _effect(
                text,
                RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                "ignore any vertical distance",
                ("movement_action", "advance"),
                ("permission", "ignore_vertical_distance"),
                ("target_scope", "models_in_leading_unit"),
            ),
        ),
        duration=_duration(
            text,
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            "until the end of the phase",
            ("endpoint", "phase"),
        ),
    )


def _burning_lance_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:conditional-leading-weapon-range-modifier",
        conditions=(_leading_condition(text),),
        target=_target(
            text,
            RuleTargetKind.SELECTED_UNIT,
            "that unit",
            ("relationship", "this_model_leading_unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                'add 6" to the Range characteristic',
                ("characteristic", "range"),
                ("delta", 6),
                ("required_weapon_keyword", "MELTA"),
                ("target_scope", "weapons_equipped_by_models_in_leading_unit"),
            ),
        ),
        duration=_duration(
            text, RuleDurationKind.WHILE_CONDITION_TRUE, "While this model is leading a unit"
        ),
    )


def _unquenchable_resolve_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17c:first-death-return-full-wounds",
        trigger=_trigger(
            text,
            RuleTriggerKind.MODEL_DESTROYED,
            "this model is destroyed",
            ("destroyed_target", "this_model"),
            ("event_order", "first"),
            ("resolution_timing", "phase_end"),
            ("timing_window", "phase_end_after_destroyed"),
        ),
        conditions=(
            _condition(
                text,
                RuleConditionKind.FREQUENCY_LIMIT,
                "The first time",
                ("event", "target_destroyed"),
                ("event_order", "first"),
                ("scope", "battle"),
            ),
            _condition(
                text,
                RuleConditionKind.DICE_ROLL_GATE,
                "on a 2+",
                ("comparison", "greater_or_equal"),
                ("roll_count", 1),
                ("roll_expression", "D6"),
                ("success_threshold", 2),
            ),
            _condition(
                text,
                RuleConditionKind.DISTANCE_PREDICATE,
                "not within Engagement Range of one or more enemy units",
                ("distance_inches", None),
                ("negated", True),
                ("object_allegiance", "enemy"),
                ("object_kind", "unit"),
                ("object_quantity", "one_or_more"),
                ("predicate", "within_engagement_range"),
                ("qualifier", None),
                ("range_kind", "engagement_range"),
            ),
        ),
        target=_target(text, RuleTargetKind.THIS_MODEL, "this model"),
        effects=(
            _effect(
                text,
                RuleEffectKind.RETURN_DESTROYED_TARGET,
                "set this model back up on the battlefield",
                ("action", "set_back_up"),
                ("placement_anchor", "destroyed_position"),
                ("placement_kind", "battlefield_set_up"),
                ("placement_preference", "as_close_as_possible"),
                ("restore_wounds_mode", "full_health"),
                ("target", "this_model"),
                ("target_lifecycle", "destroyed"),
                ("target_scope", "destroyed_model"),
            ),
        ),
        duration=_duration(text, RuleDurationKind.IMMEDIATE, "at the end of the phase"),
    )


def _spiritseer_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17c:conditional-ability-grant",
        conditions=(
            _condition(
                text,
                RuleConditionKind.DISTANCE_PREDICATE,
                'within 3" of one or more friendly Wraith Construct units',
                ("allegiance", "friendly"),
                ("distance_inches", 3),
                ("object_kind", "unit"),
                ("predicate", "within"),
                ("required_keyword_sequence", ("WRAITH CONSTRUCT",)),
            ),
        ),
        target=_target(text, RuleTargetKind.THIS_MODEL, "this model"),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "Lone Operative ability",
                ("ability", "lone_operative"),
                ("target_scope", "this_model"),
            ),
        ),
        duration=_duration(
            text, RuleDurationKind.WHILE_CONDITION_TRUE, "While this model is within"
        ),
    )


def _spirit_mark_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:movement-start-or-end-friendly-enemy-target-pair",
        trigger=_trigger(
            text,
            RuleTriggerKind.TIMING_WINDOW,
            "when this model starts or ends a move",
            ("edges", ("start", "end")),
            ("owner", "active_player"),
            ("phase", "movement"),
            ("subject", "this_model"),
            ("timing_window", "model_starts_or_ends_move"),
        ),
        conditions=(
            _condition(
                text,
                RuleConditionKind.FREQUENCY_LIMIT,
                "Once per turn",
                ("limit", 1),
                ("period", "turn"),
            ),
            _condition(
                text,
                RuleConditionKind.DISTANCE_PREDICATE,
                'within 6" of this model',
                ("distance_inches", 6),
                ("object_kind", "unit"),
                ("predicate", "within"),
                ("subject", "selected_friendly_unit"),
            ),
            _condition(
                text,
                RuleConditionKind.KEYWORD_GATE,
                "Wraith Construct unit",
                ("excluded_keywords", ("TITANIC",)),
                ("gate_subject", "selected_friendly_unit"),
                ("required_keyword_sequence", ("WRAITH CONSTRUCT",)),
            ),
            _condition(
                text,
                RuleConditionKind.VISIBILITY_PREDICATE,
                "visible to this model",
                ("object_reference", "this_model"),
                ("predicate", "visible_to"),
                ("subject", "selected_enemy_unit"),
            ),
        ),
        target=_target(
            text,
            RuleTargetKind.FRIENDLY_UNIT,
            "one friendly Wraith Construct unit",
            ("allegiance", "friendly"),
            ("paired_target", "one_visible_enemy_unit"),
            ("selection", "one"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                "[SUSTAINED HITS 1] ability",
                ("attack_role", "attacker"),
                ("target_scope", "selected_friendly_unit"),
                ("target_unit_scope", "selected_enemy_unit"),
                ("weapon_ability", "Sustained Hits"),
                ("weapon_ability_value", 1),
            ),
        ),
        duration=_duration(
            text,
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            "Until the start of your next Movement phase",
            ("boundary", "start"),
            ("endpoint", "next_movement_phase"),
        ),
    )


def _tears_of_isha_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:command-phase-friendly-unit-restoration",
        trigger=_trigger(
            text,
            RuleTriggerKind.TIMING_WINDOW,
            "In your Command phase",
            ("edge", "start"),
            ("owner", "active_player"),
            ("phase", "command"),
            ("subject", "this_model"),
            ("timing_window", "command_phase_start"),
        ),
        conditions=(
            _condition(
                text,
                RuleConditionKind.DISTANCE_PREDICATE,
                'within 6" of this model',
                ("distance_inches", 6),
                ("object_kind", "unit"),
                ("predicate", "within"),
                ("subject", "selected_friendly_unit"),
            ),
            _condition(
                text,
                RuleConditionKind.KEYWORD_GATE,
                "Wraith Construct unit",
                ("gate_subject", "selected_friendly_unit"),
                ("required_keyword_sequence", ("WRAITH CONSTRUCT",)),
            ),
            _condition(
                text,
                RuleConditionKind.FREQUENCY_LIMIT,
                "Each unit can only be selected for this ability once per turn",
                ("limit", 1),
                ("period", "turn"),
                ("scope", "selected_unit"),
            ),
        ),
        target=_target(
            text,
            RuleTargetKind.FRIENDLY_UNIT,
            "one friendly Wraith Construct unit",
            ("allegiance", "friendly"),
            ("selection", "one"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.RETURN_DESTROYED_TARGET,
                "return one destroyed model to that unit",
                ("amount", 1),
                ("condition", "unit_has_destroyed_models"),
                ("restore_wounds_mode", "full_health"),
                ("target_scope", "selected_unit"),
            ),
            _effect(
                text,
                RuleEffectKind.RESTORE_LOST_WOUNDS,
                "one model in that unit regains up to D3 lost wounds",
                ("amount_expression", "D3"),
                ("condition", "unit_has_no_destroyed_models"),
                ("maximum_models", 1),
                ("target_scope", "selected_unit"),
            ),
        ),
        duration=_duration(text, RuleDurationKind.IMMEDIATE, "In your Command phase"),
    )


def _acrobatic_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:charge-after-movement-actions",
        target=_target(text, RuleTargetKind.THIS_UNIT, "This unit"),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "in a turn in which it Advanced",
                ("ability", "can_advance_and_charge"),
                ("target_scope", "this_unit"),
            ),
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "or Fell Back",
                ("ability", "can_fall_back_and_charge"),
                ("target_scope", "this_unit"),
            ),
        ),
        duration=_duration(text, RuleDurationKind.PERMANENT, "This unit"),
    )


def _empyric_ambush_clause(source_row_id: str, text: str) -> RuleClause:
    return _clause(
        source_row_id,
        text,
        "phase17n:conditional-leading-charge-after-movement-action",
        conditions=(_leading_condition(text),),
        target=_target(
            text,
            RuleTargetKind.SELECTED_UNIT,
            "that unit",
            ("relationship", "this_model_leading_unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "eligible to declare a charge",
                ("ability", "can_charge_after_movement_action"),
                ("movement_action_effect_kind", "catalog_movement_action_grant"),
                ("target_scope", "leading_unit"),
            ),
        ),
        duration=_duration(
            text, RuleDurationKind.WHILE_CONDITION_TRUE, "While this model is leading a unit"
        ),
    )


def _leading_condition(text: str) -> RuleCondition:
    return _condition(
        text,
        RuleConditionKind.TARGET_CONSTRAINT,
        "this model is leading a unit",
        ("relationship", "this_model_leading_unit"),
    )


def _clause(
    source_row_id: str,
    text: str,
    template_id: str,
    *,
    trigger: RuleTrigger | None = None,
    conditions: tuple[RuleCondition, ...] = (),
    target: RuleTargetSpec | None = None,
    effects: tuple[RuleEffectSpec, ...] = (),
    duration: RuleDuration | None = None,
) -> RuleClause:
    return RuleClause(
        clause_id=f"phase17n:aeldari:{source_row_id}:clause:001",
        template_id=template_id,
        source_span=_span(text, text),
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
    )


def _trigger(
    text: str, kind: RuleTriggerKind, fragment: str, *parameters: tuple[str, RuleParameterValue]
) -> RuleTrigger:
    return RuleTrigger(
        kind=kind, source_span=_span(text, fragment), parameters=_parameters(*parameters)
    )


def _condition(
    text: str, kind: RuleConditionKind, fragment: str, *parameters: tuple[str, RuleParameterValue]
) -> RuleCondition:
    return RuleCondition(
        kind=kind, source_span=_span(text, fragment), parameters=_parameters(*parameters)
    )


def _target(
    text: str, kind: RuleTargetKind, fragment: str, *parameters: tuple[str, RuleParameterValue]
) -> RuleTargetSpec:
    return RuleTargetSpec(
        kind=kind, source_span=_span(text, fragment), parameters=_parameters(*parameters)
    )


def _effect(
    text: str, kind: RuleEffectKind, fragment: str, *parameters: tuple[str, RuleParameterValue]
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind, source_span=_span(text, fragment), parameters=_parameters(*parameters)
    )


def _duration(
    text: str, kind: RuleDurationKind, fragment: str, *parameters: tuple[str, RuleParameterValue]
) -> RuleDuration:
    return RuleDuration(
        kind=kind, source_span=_span(text, fragment), parameters=_parameters(*parameters)
    )


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


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
