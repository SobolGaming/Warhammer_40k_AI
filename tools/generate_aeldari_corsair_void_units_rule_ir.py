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
    / "aeldari_corsair_void_units_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-corsair-void-units-datasheet-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-corsair-void-units-datasheets-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEETS = {
    "000002531": "Corsair Voidreavers",
    "000002532": "Corsair Voidscarred",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    "000002531:3": (
        "Each time a model in this unit makes an attack, re-roll a Hit roll of 1. If the "
        "target of that attack is within range of an objective marker, you can re-roll the "
        "Hit roll instead."
    ),
    "000002531:4": "The bearer has a 4+ invulnerable save.",
    "000002532:3": (
        "At the start of the battle, select one unit from your opponent's army. Weapons "
        "equipped by models in this unit have the [LETHAL HITS] and [PRECISION] abilities "
        "while targeting that unit."
    ),
    "000002532:4": (
        "Once per turn, the first time a saving throw is failed for the bearer's unit, "
        "change the Damage characteristic of that attack to 0."
    ),
    "000002532:6": "The bearer has a 4+ invulnerable save.",
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    "000002531:3": "Reavers of the Void",
    "000002531:4": "Mistshield",
    "000002532:3": "Piratical Raiders",
    "000002532:4": "Channeller Stones",
    "000002532:6": "Mistshield",
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
            raise ValueError("Corsair void-unit source row is missing.")
        if row["description"] != expected_text:
            raise ValueError("Corsair void-unit source text drifted.")
        if row["name"] != ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Corsair void-unit ability name drifted.")


def _rule_ir(source_row_id: str, text: str) -> RuleIR:
    clauses: tuple[RuleClause, ...]
    if source_row_id == "000002531:3":
        clauses = (_reavers_of_the_void_clause(source_row_id, text),)
    elif source_row_id in {"000002531:4", "000002532:6"}:
        clauses = (_mistshield_clause(source_row_id, text),)
    elif source_row_id == "000002532:3":
        clauses = _piratical_raiders_clauses(source_row_id, text)
    elif source_row_id == "000002532:4":
        clauses = (_channeller_stones_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Corsair void-unit source row.")
    return RuleIR(
        rule_id=f"phase17k:aeldari:corsair-void-units:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _reavers_of_the_void_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:conditional-objective-hit-reroll",
        source_span=_span(text, text),
        target=_target(text, RuleTargetKind.THIS_UNIT, "this unit"),
        effects=(
            _effect(
                text,
                RuleEffectKind.REROLL_PERMISSION,
                "re-roll a Hit roll of 1",
                ("roll_type", "hit"),
                ("reroll_unmodified_value", 1),
                ("full_reroll_if_target_within_objective_range", True),
            ),
        ),
    )


def _mistshield_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:passive-model-characteristic-set",
        source_span=_span(text, text),
        target=_target(text, RuleTargetKind.THIS_MODEL, "bearer"),
        effects=(
            _effect(
                text,
                RuleEffectKind.SET_CHARACTERISTIC,
                "4+ invulnerable save",
                ("characteristic", "invulnerable_save"),
                ("value", 4),
            ),
        ),
    )


def _piratical_raiders_clauses(source_row_id: str, text: str) -> tuple[RuleClause, ...]:
    tracked_parameters = (
        ("tracked_target_owner", "this_unit"),
        ("tracked_target_role", "prey"),
        ("target_reference", "tracked_target"),
    )
    selection = RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:start-battle-tracked-target-selection",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "At the start of the battle"),
            parameters=_parameters(
                ("edge", "start"),
                ("owner", "controlling_player"),
                ("phase", "battle"),
                ("subject", "this_unit"),
                ("timing_window", "start_battle"),
            ),
        ),
        target=_target(text, RuleTargetKind.ENEMY_UNIT, "one unit from your opponent's army"),
        effects=(
            _effect(
                text,
                RuleEffectKind.SELECT_TRACKED_TARGET,
                "select one unit from your opponent's army",
                ("replacement", False),
                ("selection_kind", "select_one"),
                ("target_allegiance", "enemy"),
                ("target_lifecycle", "until_destroyed"),
                ("target_scope", "enemy_unit"),
                ("tracked_target_owner", "this_unit"),
                ("tracked_target_role", "prey"),
            ),
        ),
    )
    grants = tuple(
        RuleClause(
            clause_id=_clause_id(source_row_id, index),
            template_id="phase17c:tracked-target-weapon-ability-grant",
            source_span=_span(text, text),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.TARGET_CONSTRAINT,
                    source_span=_span(text, "while targeting that unit"),
                    parameters=_parameters(
                        ("gate_subject", "attack_target"),
                        ("relationship", "attack_targets_tracked_target"),
                        *tracked_parameters,
                    ),
                ),
            ),
            target=_target(text, RuleTargetKind.THIS_UNIT, "this unit"),
            effects=(
                _effect(
                    text,
                    RuleEffectKind.GRANT_WEAPON_ABILITY,
                    ability_fragment,
                    ("weapon_ability", ability_name),
                    ("weapon_scope", "all"),
                    *tracked_parameters,
                ),
            ),
        )
        for index, (ability_fragment, ability_name) in enumerate(
            (("[LETHAL HITS]", "Lethal Hits"), ("[PRECISION]", "Precision")),
            start=2,
        )
    )
    return (selection, *grants)


def _channeller_stones_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:first-failed-save-damage-replacement",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(text, "the first time a saving throw is failed"),
            parameters=_parameters(
                ("outcome", "failed"),
                ("roll_type", "attack_sequence.save"),
                ("timing_window", "after_failed_saving_throw"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                source_span=_span(text, "Once per turn"),
                parameters=_parameters(
                    ("activation_kind", "automatic_first_occurrence"),
                    ("max_uses", 1),
                    ("scope", "turn"),
                    ("usage_subject", "bearers_unit"),
                ),
            ),
        ),
        target=_target(text, RuleTargetKind.THIS_UNIT, "bearer's unit"),
        effects=(
            _effect(
                text,
                RuleEffectKind.SET_CHARACTERISTIC,
                "change the Damage characteristic of that attack to 0",
                ("characteristic", "damage"),
                ("value", 0),
                ("attack_role", "defender"),
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


def _target(text: str, kind: RuleTargetKind, fragment: str) -> RuleTargetSpec:
    return RuleTargetSpec(kind=kind, source_span=_span(text, fragment))


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:aeldari:corsair-void-units:{source_row_id}:clause:{index:03d}"


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
