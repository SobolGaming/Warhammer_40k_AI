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
    / "aeldari_shroud_runners_wraithblades_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-shroud-runners-wraithblades-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-shroud-runners-wraithblades-datasheets-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

SHROUD_RUNNERS_DATASHEET_ID = "000002533"
WRAITHBLADES_DATASHEET_ID = "000000598"
TARGET_ACQUISITION_ROW_ID = "000002533:4"
MALEVOLENT_SOULS_ROW_ID = "000000598:1"
FORCESHIELD_ROW_ID = "000000598:3"

DATASHEETS = {
    SHROUD_RUNNERS_DATASHEET_ID: "Shroud Runners",
    WRAITHBLADES_DATASHEET_ID: "Wraithblades",
}
RULE_TEXT_BY_SOURCE_ROW_ID = {
    TARGET_ACQUISITION_ROW_ID: (
        "In your Shooting phase, after this unit has shot, select one enemy unit hit by one "
        "or more of those attacks made with a long rifle. Until the end of the phase, that "
        "enemy unit cannot have the Benefit of Cover."
    ),
    MALEVOLENT_SOULS_ROW_ID: (
        "Each time a model in this unit is destroyed by a melee attack, if that model has not "
        "fought this phase, roll one D6. On a 3+, do not remove it from play; that destroyed "
        "model can fight after the attacking unit has finished making its attacks, and is then "
        "removed from play."
    ),
    FORCESHIELD_ROW_ID: "The bearer has a 4+ invulnerable save.",
}
ABILITY_NAME_BY_SOURCE_ROW_ID = {
    TARGET_ACQUISITION_ROW_ID: "Target Acquisition",
    MALEVOLENT_SOULS_ROW_ID: "Malevolent Souls",
    FORCESHIELD_ROW_ID: "Forceshield",
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
    if source_row_id == TARGET_ACQUISITION_ROW_ID:
        clauses = (_target_acquisition_clause(source_row_id, text),)
    elif source_row_id == MALEVOLENT_SOULS_ROW_ID:
        clauses = (_malevolent_souls_clause(source_row_id, text),)
    elif source_row_id == FORCESHIELD_ROW_ID:
        clauses = (_forceshield_clause(source_row_id, text),)
    else:
        raise ValueError("Unsupported Aeldari datasheet source row.")
    return RuleIR(
        rule_id=f"phase17k:aeldari:shroud-runners-wraithblades:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _target_acquisition_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:weapon-filtered-post-shoot-status-denial",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "In your Shooting phase, after this unit has shot"),
            parameters=_parameters(
                ("edge", "after"),
                ("owner", "active_player"),
                ("phase", "shooting"),
                ("subject", "this_unit"),
                ("target_relationship", "hit_by_those_attacks"),
                ("timing_window", "just_after_friendly_unit_has_shot"),
                ("weapon_names", ("Long rifle",)),
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
        effects=(
            _effect(
                text,
                RuleEffectKind.SET_CONTEXTUAL_STATUS,
                "that enemy unit cannot have the Benefit of Cover",
                ("operation", "deny"),
                ("rules_context", "status_denial"),
                ("status", "benefit_of_cover"),
                ("status_label", "Benefit of Cover"),
                ("target_scope", "selected_unit"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span(text, "Until the end of the phase"),
            parameters=_parameters(("endpoint", "phase")),
        ),
    )


def _malevolent_souls_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:conditional-model-fight-on-death",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.MODEL_DESTROYED,
            source_span=_span(text, "a model in this unit is destroyed by a melee attack"),
            parameters=_parameters(
                ("destroyed_target", "this_model"),
                ("timing_window", "after_attacking_unit_finished_attacks"),
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, "destroyed by a melee attack"),
                parameters=_parameters(
                    ("attack_kind", "melee"),
                    ("gate_subject", "destroyed_model"),
                    ("relationship", "destroyed_by_attack"),
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, "that model has not fought this phase"),
                parameters=_parameters(
                    ("gate_subject", "destroyed_model"),
                    ("relationship", "has_not_fought_this_phase"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "a model in this unit"),
        ),
        effects=(
            _effect(
                text,
                RuleEffectKind.GRANT_ABILITY,
                "that destroyed model can fight after the attacking unit has finished making "
                "its attacks",
                ("ability", "fight_on_death"),
                ("optional", True),
                ("trigger_roll_threshold", 3),
                ("trigger_roll_type", "aeldari_malevolent_souls"),
            ),
        ),
    )


def _forceshield_clause(source_row_id: str, text: str) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:passive-model-characteristic-set",
        source_span=_span(text, text),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "bearer"),
        ),
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
    return f"phase17k:aeldari:shroud-runners-wraithblades:{source_row_id}:clause:{index:03d}"


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
