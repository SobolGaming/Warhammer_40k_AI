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
    / "aeldari_kharseth_2026_06"
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

ARTIFACT_SCHEMA = "core-v2-kharseth-datasheet-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-kharseth-datasheet-2026-06-09"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEET_ID = "000004194"
DATASHEET_NAME = "Kharseth"
AETHERSENSE_ROW_ID = "000004194:4"
FURY_OF_THE_VOID_ROW_ID = "000004194:5"

AETHERSENSE_TEXT = (
    "Enemy units that are set up on the battlefield from Reserves cannot be set up within "
    '12" of this model.'
)
FURY_OF_THE_VOID_TEXT = (
    "In your Shooting phase, after this model's unit has shot, select one enemy unit hit by "
    "one or more attacks made with this model's Dread of the Deep Void. Until the end of the "
    "turn, that unit is riven. Each time an AELDARI model from your army makes an attack that "
    "targets a riven unit, add 1 to the Strength characteristic of that attack."
)


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    records = {
        AETHERSENSE_ROW_ID: _record_payload(
            ability_name="Aethersense (Psychic)",
            rule_ir=_aethersense_rule_ir(),
        ),
        FURY_OF_THE_VOID_ROW_ID: _record_payload(
            ability_name="Fury of the Void (Psychic)",
            rule_ir=_fury_of_the_void_rule_ir(),
        ),
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_pdf_filename": PDF_PATH.name,
        "source_pdf_sha256": hashlib.sha256(PDF_PATH.read_bytes()).hexdigest(),
        "source_page_numbers": [14, 15],
        "datasheet_id": DATASHEET_ID,
        "datasheet_name": DATASHEET_NAME,
        "records": records,
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _record_payload(*, ability_name: str, rule_ir: RuleIR) -> dict[str, object]:
    return {
        "ability_name": ability_name,
        "normalized_text_sha256": hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest(),
        "rule_ir": rule_ir.to_payload(),
    }


def _aethersense_rule_ir() -> RuleIR:
    text = AETHERSENSE_TEXT
    return _rule_ir(
        source_row_id=AETHERSENSE_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=f"phase17k:aeldari:kharseth:{AETHERSENSE_ROW_ID}:clause:001",
                template_id="phase17c:placement-permission-restriction",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.SETUP,
                    source_span=_span(text, "set up on the battlefield from Reserves"),
                    parameters=_parameters(
                        ("setup_source", "reserves"),
                        ("subject", "enemy_unit"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.DISTANCE_PREDICATE,
                        source_span=_span(text, 'within 12" of this model'),
                        parameters=_parameters(
                            ("distance_inches", 12.0),
                            ("object_kind", "model"),
                            ("object_reference", "this_model"),
                            ("predicate", "within"),
                            ("range_kind", "numeric_range"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.ENEMY_UNIT,
                    source_span=_span(text, "Enemy units"),
                    parameters=_parameters(
                        ("allegiance", "enemy"),
                        ("setup_source", "reserves"),
                    ),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.PLACEMENT_RESTRICTION,
                        source_span=_span(text, "cannot be set up"),
                        parameters=_parameters(
                            ("allowed", False),
                            ("placement_source", "reserves"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _fury_of_the_void_rule_ir() -> RuleIR:
    text = FURY_OF_THE_VOID_TEXT
    selection_text = (
        "In your Shooting phase, after this model's unit has shot, select one enemy unit hit "
        "by one or more attacks made with this model's Dread of the Deep Void."
    )
    effect_text = (
        "Until the end of the turn, that unit is riven. Each time an AELDARI model from your "
        "army makes an attack that targets a riven unit, add 1 to the Strength characteristic "
        "of that attack."
    )
    return _rule_ir(
        source_row_id=FURY_OF_THE_VOID_ROW_ID,
        text=text,
        clauses=(
            RuleClause(
                clause_id=f"phase17k:aeldari:kharseth:{FURY_OF_THE_VOID_ROW_ID}:clause:001",
                template_id="phase17c:selected-target-constraint",
                source_span=_span(text, selection_text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "after this model's unit has shot"),
                    parameters=_parameters(
                        ("attacker_model_reference", "this_model"),
                        ("edge", "after"),
                        ("owner", "active_player"),
                        ("phase", "shooting"),
                        ("subject", "this_model"),
                        ("target_relationship", "hit_by_those_attacks"),
                        ("timing_window", "just_after_friendly_unit_has_shot"),
                        ("weapon_names", ("Dread of the Deep Void",)),
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
                clause_id=f"phase17k:aeldari:kharseth:{FURY_OF_THE_VOID_ROW_ID}:clause:002",
                template_id="phase17c:characteristic-modifier",
                source_span=_span(text, effect_text),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(text, "targets a riven unit"),
                        parameters=_parameters(
                            ("gate_subject", "attack_target"),
                            ("relationship", "attack_targets_selected_unit"),
                            ("target_reference", "selected_unit"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.FRIENDLY_UNIT,
                    source_span=_span(text, "an AELDARI model from your army"),
                    parameters=_parameters(
                        ("allegiance", "friendly"),
                        ("required_keyword", "AELDARI"),
                    ),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=_span(
                            text,
                            "add 1 to the Strength characteristic of that attack",
                        ),
                        parameters=_parameters(
                            ("attack_role", "attacker"),
                            ("characteristic", "strength"),
                            ("delta", 1),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "Until the end of the turn"),
                    parameters=_parameters(("endpoint", "turn")),
                ),
            ),
        ),
    )


def _rule_ir(*, source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:aeldari:kharseth:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
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
