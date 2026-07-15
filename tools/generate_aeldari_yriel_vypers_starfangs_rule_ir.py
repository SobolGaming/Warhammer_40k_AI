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
OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "aeldari_yriel_vypers_starfangs_2026_06"
    / "artifacts"
    / "rule_ir.json"
)
PDF_PATH = (
    REPO_ROOT
    / "data"
    / "raw"
    / "faction_packs"
    / "eng_09-06_warhammer40000_faction_pack_aeldari-glkjirbhiw-9udkry7xbr.pdf"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-yriel-vypers-starfangs-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-yriel-vypers-starfangs-datasheets-2026-06-09"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

PRINCE_YRIEL_DATASHEET_ID = "000004193"
VYPERS_DATASHEET_ID = "000000605"
STARFANGS_DATASHEET_ID = "000004195"

PIRATICAL_HERO_ROW_ID = "000004193:4"
PRINCE_OF_CORSAIRS_ROW_ID = "000004193:5"
HARASSMENT_FIRE_ROW_ID = "000000605:3"
HALLUCINOGEN_GRENADES_ROW_ID = "000004195:4"

PIRATICAL_HERO_TEXT = (
    "While this model is leading a unit, each time a model in that unit makes an attack, "
    "that attack has the [SUSTAINED HITS 1] ability and add 1 to the Hit roll."
)
PRINCE_OF_CORSAIRS_TEXT = (
    "After both players have deployed their armies, if this unit is on the battlefield (or "
    "any Transport it is embarked within is on the battlefield), select up to three AELDARI "
    "units from your army and redeploy them. When doing so, you can set those units up in "
    "Strategic Reserves, regardless of how many units are already in Strategic Reserves."
)
HARASSMENT_FIRE_TEXT = (
    "In your Shooting phase, after this unit has shot, select one enemy unit hit by one or "
    "more of those attacks. Until the start of your next turn, that enemy unit is suppressed. "
    "While a unit is suppressed, each time a model in that unit makes an attack, subtract 1 "
    "from the Hit roll."
)
HALLUCINOGEN_GRENADES_TEXT = (
    "At the start of your opponent's Shooting phase, this unit can use this ability. If it "
    'does, select one Aeldari Infantry unit from your army visible to and within 36" of this '
    "unit: until the end of the phase, that unit has the Stealth ability."
)


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    records = {
        PIRATICAL_HERO_ROW_ID: _record_payload(
            datasheet_id=PRINCE_YRIEL_DATASHEET_ID,
            datasheet_name="Prince Yriel",
            ability_name="Piratical Hero",
            rule_ir=_piratical_hero_rule_ir(),
        ),
        PRINCE_OF_CORSAIRS_ROW_ID: _record_payload(
            datasheet_id=PRINCE_YRIEL_DATASHEET_ID,
            datasheet_name="Prince Yriel",
            ability_name="Prince of Corsairs",
            rule_ir=_prince_of_corsairs_rule_ir(),
        ),
        HARASSMENT_FIRE_ROW_ID: _record_payload(
            datasheet_id=VYPERS_DATASHEET_ID,
            datasheet_name="Vypers",
            ability_name="Harassment Fire",
            rule_ir=_harassment_fire_rule_ir(),
        ),
        HALLUCINOGEN_GRENADES_ROW_ID: _record_payload(
            datasheet_id=STARFANGS_DATASHEET_ID,
            datasheet_name="Starfangs",
            ability_name="Hallucinogen Grenades",
            rule_ir=_hallucinogen_grenades_rule_ir(),
        ),
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_pdf_filename": PDF_PATH.name,
        "source_pdf_sha256": hashlib.sha256(PDF_PATH.read_bytes()).hexdigest(),
        "datasheets": [
            {
                "datasheet_id": PRINCE_YRIEL_DATASHEET_ID,
                "datasheet_name": "Prince Yriel",
                "source_page_numbers": [12, 13],
            },
            {
                "datasheet_id": VYPERS_DATASHEET_ID,
                "datasheet_name": "Vypers",
                "source_page_numbers": [16, 17],
            },
            {
                "datasheet_id": STARFANGS_DATASHEET_ID,
                "datasheet_name": "Starfangs",
                "source_page_numbers": [18, 19],
            },
        ],
        "records": records,
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _record_payload(
    *,
    datasheet_id: str,
    datasheet_name: str,
    ability_name: str,
    rule_ir: RuleIR,
) -> dict[str, object]:
    return {
        "datasheet_id": datasheet_id,
        "datasheet_name": datasheet_name,
        "ability_name": ability_name,
        "normalized_text_sha256": hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest(),
        "rule_ir": rule_ir.to_payload(),
    }


def _piratical_hero_rule_ir() -> RuleIR:
    text = PIRATICAL_HERO_TEXT
    leading = "While this model is leading a unit"
    attack = "each time a model in that unit makes an attack"
    return _rule_ir(
        source_row_id=PIRATICAL_HERO_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(PIRATICAL_HERO_ROW_ID, 1),
                template_id="phase17c:weapon-ability-grant",
                source_span=_span(text, text),
                conditions=(_leading_unit_condition(text, leading),),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "a unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                        source_span=_span(text, "that attack has the [SUSTAINED HITS 1] ability"),
                        parameters=_parameters(
                            ("target_scope", "models_in_selected_unit"),
                            ("weapon_ability", "Sustained Hits"),
                            ("weapon_ability_value", 1),
                            ("weapon_scope", "all"),
                        ),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(PIRATICAL_HERO_ROW_ID, 2),
                template_id="phase17c:dice-roll-modifier",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=_span(text, attack),
                    parameters=_parameters(
                        ("actor", "selected_unit"),
                        ("roll_type", "hit"),
                        ("timing_window", "attack_sequence.hit"),
                    ),
                ),
                conditions=(_leading_unit_condition(text, leading),),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "a unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_DICE_ROLL,
                        source_span=_span(text, "add 1 to the Hit roll"),
                        parameters=_parameters(
                            ("attack_role", "attacker"),
                            ("delta", 1),
                            ("roll_type", "hit_roll"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _prince_of_corsairs_rule_ir() -> RuleIR:
    text = PRINCE_OF_CORSAIRS_TEXT
    return _rule_ir(
        source_row_id=PRINCE_OF_CORSAIRS_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(PRINCE_OF_CORSAIRS_ROW_ID, 1),
                template_id="phase17c:placement-permission-restriction",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.SETUP,
                    source_span=_span(text, "After both players have deployed their armies"),
                    parameters=_parameters(
                        ("edge", "after"),
                        ("timing_window", "after_both_armies_deployed"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(
                            text,
                            "if this unit is on the battlefield (or any Transport it is embarked "
                            "within is on the battlefield)",
                        ),
                        parameters=_parameters(
                            ("gate_subject", "source_unit"),
                            (
                                "relationship",
                                "source_unit_or_embarked_transport_on_battlefield",
                            ),
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.FREQUENCY_LIMIT,
                        source_span=_span(text, "up to three AELDARI units"),
                        parameters=_parameters(("maximum_uses", 3), ("scope", "battle")),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.FRIENDLY_UNIT,
                    source_span=_span(text, "AELDARI units from your army"),
                    parameters=_parameters(
                        ("allegiance", "friendly"),
                        ("required_keyword", "AELDARI"),
                    ),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.PLACEMENT_PERMISSION,
                        source_span=_span(text, "redeploy them"),
                        parameters=_parameters(
                            ("action", "redeploy"),
                            ("allowed", True),
                            ("maximum_units", 3),
                        ),
                    ),
                    RuleEffectSpec(
                        kind=RuleEffectKind.PLACEMENT_PERMISSION,
                        source_span=_span(
                            text,
                            "set those units up in Strategic Reserves, regardless of how many "
                            "units are already in Strategic Reserves",
                        ),
                        parameters=_parameters(
                            ("action", "redeploy_to_strategic_reserves"),
                            ("allowed", True),
                            ("ignore_strategic_reserves_limit", True),
                            ("maximum_units", 3),
                            ("placement_kind", "strategic_reserves"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _harassment_fire_rule_ir() -> RuleIR:
    text = HARASSMENT_FIRE_TEXT
    selection = (
        "In your Shooting phase, after this unit has shot, select one enemy unit hit by one or "
        "more of those attacks."
    )
    effect = (
        "Until the start of your next turn, that enemy unit is suppressed. While a unit is "
        "suppressed, each time a model in that unit makes an attack, subtract 1 from the Hit roll."
    )
    return _rule_ir(
        source_row_id=HARASSMENT_FIRE_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(HARASSMENT_FIRE_ROW_ID, 1),
                template_id="phase17c:selected-target-constraint",
                source_span=_span(text, selection),
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
                target=RuleTargetSpec(
                    kind=RuleTargetKind.ENEMY_UNIT,
                    source_span=_span(text, "one enemy unit"),
                    parameters=_parameters(
                        ("allegiance", "enemy"),
                        ("target_relationship", "hit_by_those_attacks"),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(HARASSMENT_FIRE_ROW_ID, 2),
                template_id="phase17c:dice-roll-modifier",
                source_span=_span(text, effect),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=_span(
                        text,
                        "each time a model in that unit makes an attack",
                    ),
                    parameters=_parameters(
                        ("actor", "selected_unit"),
                        ("target_reference", "selected_unit"),
                        ("timing_window", "attack_sequence.attack"),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "that enemy unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_DICE_ROLL,
                        source_span=_span(text, "subtract 1 from the Hit roll"),
                        parameters=_parameters(
                            ("attack_role", "attacker"),
                            ("delta", -1),
                            ("roll_type", "hit_roll"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "Until the start of your next turn"),
                    parameters=_parameters(
                        ("battle_round_offset", 1),
                        ("boundary", "start"),
                        ("endpoint", "turn"),
                        ("owner", "source_player"),
                    ),
                ),
            ),
        ),
    )


def _hallucinogen_grenades_rule_ir() -> RuleIR:
    text = HALLUCINOGEN_GRENADES_TEXT
    selection = (
        "At the start of your opponent's Shooting phase, this unit can use this ability. If it "
        'does, select one Aeldari Infantry unit from your army visible to and within 36" of this '
        "unit"
    )
    return _rule_ir(
        source_row_id=HALLUCINOGEN_GRENADES_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(HALLUCINOGEN_GRENADES_ROW_ID, 1),
                template_id="phase17c:selected-target-constraint",
                source_span=_span(text, selection),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "At the start of your opponent's Shooting phase"),
                    parameters=_parameters(
                        ("edge", "start"),
                        ("optional", True),
                        ("owner", "opponent"),
                        ("phase", "shooting"),
                        ("subject", "this_unit"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.VISIBILITY_PREDICATE,
                        source_span=_span(text, "visible to"),
                        parameters=_parameters(
                            ("observer", "this_unit"),
                            ("predicate", "visible_to"),
                            ("target_reference", "selected_unit"),
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.DISTANCE_PREDICATE,
                        source_span=_span(text, 'within 36" of this unit'),
                        parameters=_parameters(
                            ("distance_inches", 36.0),
                            ("negated", False),
                            ("object_kind", "unit"),
                            ("object_reference", "this"),
                            ("predicate", "within"),
                            ("qualifier", None),
                            ("range_kind", "numeric_range"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.FRIENDLY_UNIT,
                    source_span=_span(text, "one Aeldari Infantry unit from your army"),
                    parameters=_parameters(
                        ("allegiance", "friendly"),
                        ("required_keyword_sequence", ("AELDARI", "INFANTRY")),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(HALLUCINOGEN_GRENADES_ROW_ID, 2),
                template_id="phase17c:grant-ability",
                source_span=_span(
                    text,
                    "until the end of the phase, that unit has the Stealth ability",
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "that unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(text, "has the Stealth ability"),
                        parameters=_parameters(
                            ("ability", "stealth"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "until the end of the phase"),
                    parameters=_parameters(("boundary", "end"), ("endpoint", "phase")),
                ),
            ),
        ),
    )


def _leading_unit_condition(text: str, fragment: str) -> RuleCondition:
    return RuleCondition(
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        source_span=_span(text, fragment),
        parameters=_parameters(
            ("relationship", "this_model_leading_unit"),
        ),
    )


def _rule_ir(*, source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:aeldari:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:aeldari:datasheet:{source_row_id}:clause:{index:03d}"


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
