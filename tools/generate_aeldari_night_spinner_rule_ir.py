from __future__ import annotations

import hashlib
import json
from pathlib import Path

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
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
    / "aeldari_night_spinner_2026_06"
    / "artifacts"
    / "rule_ir.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-night-spinner-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-night-spinner-datasheet-2026-06-14"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

NIGHT_SPINNER_DATASHEET_ID = "000000611"
MONOFILAMENT_WEB_ROW_ID = "000000611:3"
MONOFILAMENT_WEB_SOURCE_TEXT = (
    "In your Shooting phase, after this model has shot, if one or more of those attacks made "
    "with its doomweaver scored a hit against an enemy unit, until the start of your next turn, "
    "that enemy unit is pinned. While a unit is pinned, subtract 2 from that unit's Move "
    "characteristic and subtract 2 from Charge rolls made for it."
)
MONOFILAMENT_WEB_NORMALIZED_TEXT = MONOFILAMENT_WEB_SOURCE_TEXT


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    _validate_source_row(source_payload)
    rule_ir = _monofilament_web_rule_ir()
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
        "datasheet_id": NIGHT_SPINNER_DATASHEET_ID,
        "datasheet_name": "Night Spinner",
        "records": {
            MONOFILAMENT_WEB_ROW_ID: {
                "ability_name": "Monofilament Web",
                "normalized_text_sha256": hashlib.sha256(
                    rule_ir.normalized_text.encode()
                ).hexdigest(),
                "rule_ir": rule_ir.to_payload(),
            }
        },
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _validate_source_row(source_payload: object) -> None:
    if not isinstance(source_payload, dict):
        raise TypeError("Night Spinner source artifact must be an object.")
    rows = source_payload.get("rows")
    if not isinstance(rows, list):
        raise TypeError("Night Spinner source artifact rows are missing.")
    source_row = next(
        (
            row
            for row in rows
            if isinstance(row, dict) and row.get("source_row_id") == MONOFILAMENT_WEB_ROW_ID
        ),
        None,
    )
    if not isinstance(source_row, dict):
        raise TypeError("Night Spinner source row is missing.")
    fields = source_row.get("fields")
    if not isinstance(fields, dict):
        raise TypeError("Night Spinner source row fields are missing.")
    if fields.get("datasheet_id") != NIGHT_SPINNER_DATASHEET_ID:
        raise ValueError("Night Spinner source datasheet identity drifted.")
    if fields.get("name") != "Monofilament Web":
        raise ValueError("Night Spinner source ability name drifted.")
    if fields.get("description") != MONOFILAMENT_WEB_SOURCE_TEXT:
        raise ValueError("Night Spinner source ability text drifted.")


def _monofilament_web_rule_ir() -> RuleIR:
    text = MONOFILAMENT_WEB_NORMALIZED_TEXT
    selection_text = (
        "In your Shooting phase, after this model has shot, if one or more of those attacks made "
        "with its doomweaver scored a hit against an enemy unit"
    )
    duration_text = "until the start of your next turn"
    source_id = f"{SOURCE_PACKAGE_ID}:datasheet:{MONOFILAMENT_WEB_ROW_ID}"
    return RuleIR(
        rule_id=f"phase17k:aeldari:night-spinner:datasheet:{MONOFILAMENT_WEB_ROW_ID}",
        source_id=source_id,
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=(
            RuleClause(
                clause_id=_clause_id(1),
                template_id="phase17c:selected-target-constraint",
                source_span=_span(text, selection_text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "after this model has shot"),
                    parameters=_parameters(
                        ("attacker_model_reference", "this_model"),
                        ("edge", "after"),
                        ("owner", "active_player"),
                        ("phase", "shooting"),
                        ("subject", "this_model"),
                        ("target_relationship", "hit_by_those_attacks"),
                        ("timing_window", "just_after_friendly_unit_has_shot"),
                        ("weapon_names", ("Doomweaver",)),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.ENEMY_UNIT,
                    source_span=_span(text, "an enemy unit"),
                    parameters=_parameters(
                        ("allegiance", "enemy"),
                        ("target_relationship", "hit_by_those_attacks"),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(2),
                template_id="phase17c:selected-unit-characteristic-modifier",
                source_span=_span(
                    text,
                    "subtract 2 from that unit's Move characteristic",
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "that enemy unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=_span(
                            text,
                            "subtract 2 from that unit's Move characteristic",
                        ),
                        parameters=_parameters(
                            ("characteristic", Characteristic.MOVEMENT.value),
                            ("delta", -2),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, duration_text),
                    parameters=_parameters(
                        ("battle_round_offset", 1),
                        ("boundary", "start"),
                        ("endpoint", "turn"),
                        ("owner", "source_player"),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(3),
                template_id="phase17c:selected-unit-dice-roll-modifier",
                source_span=_span(text, "subtract 2 from Charge rolls made for it"),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(text, "that enemy unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_DICE_ROLL,
                        source_span=_span(text, "subtract 2 from Charge rolls made for it"),
                        parameters=_parameters(
                            ("delta", -2),
                            ("roll_type", "charge"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, duration_text),
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


def _clause_id(index: int) -> str:
    return f"phase17k:aeldari:night-spinner:datasheet:{MONOFILAMENT_WEB_ROW_ID}:clause:{index:03d}"


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
