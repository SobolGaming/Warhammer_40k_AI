from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from tools.faction_rule_ir_bundle import generate_registered_rule_ir_shard
else:
    from faction_rule_ir_bundle import generate_registered_rule_ir_shard

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
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as source_overlay,
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
OFFICIAL_PDF_PATH = (
    REPO_ROOT
    / "data"
    / "raw"
    / "faction_packs"
    / "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children-srspmclqtm-i8ey7hgk2s.pdf"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_pack_rule_ir"
    / "artifacts"
    / "shards"
    / "emperors-children.json"
)

ARTIFACT_SCHEMA = "core-v2-emperors-children-fulgrim-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-emperors-children-fulgrim-datasheet-2026-07"
SHARD_ID = "emperors-children"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEET_ID = "000004077"
DATASHEET_NAME = "Fulgrim"
SUPPORTED_SOURCE_ROW_IDS = tuple(f"{DATASHEET_ID}:{line}" for line in range(4, 10))

ABILITY_NAMES = {
    f"{DATASHEET_ID}:4": "Daemonic Poisons",
    f"{DATASHEET_ID}:5": "Daemon Primarch of Slaanesh",
    f"{DATASHEET_ID}:6": "Serpentine",
    f"{DATASHEET_ID}:7": "Beguiling Form",
    f"{DATASHEET_ID}:8": "Daemonic Speed",
    f"{DATASHEET_ID}:9": "Enthralling Hypnosis (Aura)",
}


def main() -> None:
    generate_registered_rule_ir_shard(shard_id=SHARD_ID)


def generated_artifact_payload() -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source_rows = _validated_source_rows(source_payload)
    rule_irs = {
        f"{DATASHEET_ID}:4": _daemonic_poisons_rule_ir(source_rows[f"{DATASHEET_ID}:4"]),
        f"{DATASHEET_ID}:5": _daemon_primarch_rule_ir(source_rows[f"{DATASHEET_ID}:5"]),
        f"{DATASHEET_ID}:6": _serpentine_rule_ir(source_rows[f"{DATASHEET_ID}:6"]),
        f"{DATASHEET_ID}:7": _beguiling_form_rule_ir(source_rows[f"{DATASHEET_ID}:7"]),
        f"{DATASHEET_ID}:8": _daemonic_speed_rule_ir(source_rows[f"{DATASHEET_ID}:8"]),
        f"{DATASHEET_ID}:9": _enthralling_hypnosis_rule_ir(source_rows[f"{DATASHEET_ID}:9"]),
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
        "official_document_filename": OFFICIAL_PDF_PATH.name,
        "official_document_sha256": hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest(),
        "official_document_pages": [8, 9],
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheet_id": DATASHEET_ID,
        "datasheet_name": DATASHEET_NAME,
        "records": {
            source_row_id: {
                "ability_name": ABILITY_NAMES[source_row_id],
                "normalized_text_sha256": hashlib.sha256(
                    rule_ir.normalized_text.encode()
                ).hexdigest(),
                "rule_ir": rule_ir.to_payload(),
            }
            for source_row_id, rule_ir in rule_irs.items()
        },
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def _validated_source_rows(source_payload: object) -> dict[str, str]:
    if not isinstance(source_payload, dict) or not isinstance(source_payload.get("rows"), list):
        raise TypeError("Fulgrim source artifact rows are missing.")
    source_rows: dict[str, str] = {}
    for row in source_payload["rows"]:
        if not isinstance(row, dict) or row.get("source_row_id") not in SUPPORTED_SOURCE_ROW_IDS:
            continue
        fields = row.get("fields")
        if not isinstance(fields, dict):
            raise TypeError("Fulgrim source row fields are missing.")
        source_row_id = row["source_row_id"]
        if fields.get("datasheet_id") != DATASHEET_ID:
            raise ValueError("Fulgrim source datasheet identity drifted.")
        if fields.get("name") != ABILITY_NAMES[source_row_id]:
            raise ValueError("Fulgrim source ability name drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Fulgrim source ability text is missing.")
        source_rows[source_row_id] = description
    if set(source_rows) != set(SUPPORTED_SOURCE_ROW_IDS):
        raise ValueError("Fulgrim source-row inventory drifted.")
    if source_rows[f"{DATASHEET_ID}:6"] != source_overlay.SERPENTINE_DESCRIPTION:
        raise ValueError("Fulgrim Serpentine overlay text drifted.")
    return source_rows


def _daemonic_poisons_rule_ir(text: str) -> RuleIR:
    source_row_id = f"{DATASHEET_ID}:4"
    poisoned_text = "Until the end of the battle, that enemy unit is poisoned."
    return _rule_ir(
        source_row_id,
        text,
        (
            _hit_target_selection_clause(
                source_row_id=source_row_id,
                index=1,
                text=text,
                source_text="In your Shooting phase",
                phase="shooting",
                owner="active_player",
                timing_window="just_after_friendly_unit_has_shot",
                weapon_names=(
                    "Daemonic blades - strike",
                    "Daemonic blades - sweep",
                    "Malefic lash",
                    "Serpentine tail",
                ),
            ),
            _poisoned_status_clause(
                source_row_id=source_row_id,
                index=2,
                text=text,
                source_text="In your Shooting phase and the Fight phase",
            ),
            _hit_target_selection_clause(
                source_row_id=source_row_id,
                index=3,
                text=text,
                source_text="the Fight phase",
                phase="fight",
                owner="attacking_model_controller",
                timing_window="just_after_friendly_model_finished_attacks",
            ),
            _poisoned_status_clause(
                source_row_id=source_row_id,
                index=4,
                text=text,
                source_text=poisoned_text,
            ),
        ),
    )


def _hit_target_selection_clause(
    *,
    source_row_id: str,
    index: int,
    text: str,
    source_text: str,
    phase: str,
    owner: str,
    timing_window: str,
    weapon_names: tuple[str, ...] | None = None,
) -> RuleClause:
    trigger_parameters: list[tuple[str, RuleParameterValue]] = [
        ("attacker_model_reference", "this_model"),
        ("edge", "after"),
        ("owner", owner),
        ("phase", phase),
        ("subject", "this_model"),
        ("target_relationship", "hit_by_those_attacks"),
        ("timing_window", timing_window),
    ]
    if weapon_names is not None:
        trigger_parameters.append(("weapon_names", weapon_names))
    return RuleClause(
        clause_id=_clause_id(source_row_id, index),
        template_id="phase17c:selected-target-constraint",
        source_span=_span(text, source_text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(text, "after this model has finished making its attacks"),
            parameters=_parameters(*trigger_parameters),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span(text, "one enemy unit"),
            parameters=_parameters(
                ("allegiance", "enemy"),
                ("target_relationship", "hit_by_those_attacks"),
            ),
        ),
    )


def _poisoned_status_clause(
    *,
    source_row_id: str,
    index: int,
    text: str,
    source_text: str,
) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, index),
        template_id="phase17k:persistent-selected-target-status",
        source_span=_span(text, source_text),
        target=RuleTargetSpec(
            kind=RuleTargetKind.SELECTED_UNIT,
            source_span=_span(text, "that enemy unit"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span(text, "that enemy unit is poisoned"),
                parameters=_parameters(
                    ("command_phase_mortal_wounds", "D3"),
                    ("command_phase_roll_threshold", 4),
                    ("command_phase_timing", "start_each_players_command_phase"),
                    ("status", "poisoned"),
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.PERMANENT,
            source_span=_span(text, "Until the end of the battle"),
        ),
    )


def _daemon_primarch_rule_ir(text: str) -> RuleIR:
    source_row_id = f"{DATASHEET_ID}:5"
    return _rule_ir(
        source_row_id,
        text,
        (
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17k:command-phase-self-ability-choice",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "At the start of your opponent's Command phase"),
                    parameters=_parameters(
                        ("edge", "start"),
                        ("owner", "opponent"),
                        ("phase", "command"),
                        ("subject", "this_model"),
                        ("timing_window", "start_opponents_command_phase"),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_this_model_span(text),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(
                            text,
                            (
                                "select one of the abilities in the Daemon Primarch of "
                                "Slaanesh section"
                            ),
                        ),
                        parameters=_parameters(
                            ("ability", "select_one_self_ability_mode"),
                            (
                                "option_source_rule_ids",
                                (
                                    f"{SOURCE_PACKAGE_ID}:datasheet:{DATASHEET_ID}:7",
                                    f"{SOURCE_PACKAGE_ID}:datasheet:{DATASHEET_ID}:8",
                                    f"{SOURCE_PACKAGE_ID}:datasheet:{DATASHEET_ID}:9",
                                ),
                            ),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(
                        text,
                        "Until the start of your opponent's next Command phase",
                    ),
                    parameters=_parameters(
                        ("battle_round_offset", 1),
                        ("boundary", "start"),
                        ("endpoint", "phase"),
                        ("owner", "opponent"),
                        ("phase", "command"),
                    ),
                ),
            ),
        ),
    )


def _serpentine_rule_ir(text: str) -> RuleIR:
    source_row_id = f"{DATASHEET_ID}:6"
    movement_modes = ("normal", "advance", "fall_back")
    return _rule_ir(
        source_row_id,
        text,
        (
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17k:model-terrain-height-transit",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(
                        text,
                        "Each time this model makes a Normal, Advance or Fall Back move",
                    ),
                    parameters=_parameters(
                        ("edge", "during"),
                        ("movement_modes", movement_modes),
                        ("phase", "movement"),
                        ("subject", "this_model"),
                        ("timing_window", "model_makes_move"),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "this model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                        source_span=_span(
                            text,
                            'move over sections of terrain features that are 4" or less in height',
                        ),
                        parameters=_parameters(
                            ("movement_modes", movement_modes),
                            ("permission", "move_over_as_if_not_there"),
                            ("terrain_height_max_inches", 4.0),
                            ("terrain_scope", "terrain_features"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _beguiling_form_rule_ir(text: str) -> RuleIR:
    return _mode_option_rule_ir(
        source_row_id=f"{DATASHEET_ID}:7",
        text=text,
        effect=RuleEffectSpec(
            kind=RuleEffectKind.MODIFY_DICE_ROLL,
            source_span=_span(text, "subtract 1 from the Hit roll"),
            parameters=_parameters(
                ("attack_role", "target"),
                ("delta", -1),
                ("roll_type", "hit"),
            ),
        ),
    )


def _daemonic_speed_rule_ir(text: str) -> RuleIR:
    return _mode_option_rule_ir(
        source_row_id=f"{DATASHEET_ID}:8",
        text=text,
        effect=RuleEffectSpec(
            kind=RuleEffectKind.GRANT_ABILITY,
            source_span=_span(text, "Fights First ability"),
            parameters=_parameters(("ability", "fights_first")),
        ),
    )


def _enthralling_hypnosis_rule_ir(text: str) -> RuleIR:
    return _mode_option_rule_ir(
        source_row_id=f"{DATASHEET_ID}:9",
        text=text,
        effect=RuleEffectSpec(
            kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
            source_span=_span(text, text),
            parameters=_parameters(
                ("aura_range_inches", 6.0),
                ("failure_effect", "remain_stationary"),
                ("status", "fall_back_leadership_test_denial"),
                ("test_characteristic", "leadership"),
            ),
        ),
    )


def _mode_option_rule_ir(
    *,
    source_row_id: str,
    text: str,
    effect: RuleEffectSpec,
) -> RuleIR:
    return _rule_ir(
        source_row_id,
        text,
        (
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17k:selectable-self-ability-option",
                source_span=_span(text, text),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_this_model_span(text),
                ),
                effects=(effect,),
            ),
        ),
    )


def _rule_ir(source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:emperors-children:fulgrim:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:emperors-children:fulgrim:datasheet:{source_row_id}:clause:{index:03d}"


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


def _this_model_span(text: str) -> TextSpan:
    fragment = "this model" if "this model" in text else "This model"
    return _span(text, fragment)


def _sha256_payload(payload: dict[str, object]) -> str:
    hash_payload = {**payload, "package_hash": ""}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
