from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING or __package__:
    from tools.canonical_json_hash import canonical_json_sha256
    from tools.faction_rule_ir_bundle import generate_registered_rule_ir_shard
else:
    from canonical_json_hash import canonical_json_sha256
    from faction_rule_ir_bundle import generate_registered_rule_ir_shard

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
    parameter_payload,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_overlay import SourceOverlayOperationKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as source_overlay,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
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
REVIEW_MANIFEST_PATH = (
    REPO_ROOT / "data" / "source_manifests" / "faction_pack_datasheet_review_v1.json"
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

ARTIFACT_SCHEMA = "core-v2-emperors-children-lord-exultant-maulerfiend-chaos-spawn-rule-ir-v1"
SOURCE_PACKAGE_ID = (
    "gw-11e-emperors-children-lord-exultant-maulerfiend-chaos-spawn-datasheets-2026-08"
)
SHARD_ID = "emperors-children"
MANUAL_PARSER_VERSION = "manual-source-backed-rule-ir:v1"

LORD_EXULTANT_DATASHEET_ID = "000004078"
CHAOS_SPAWN_DATASHEET_ID = "000004090"
MAULERFIEND_DATASHEET_ID = "000004091"

EUPHORIC_STRIKES_ROW_ID = f"{LORD_EXULTANT_DATASHEET_ID}:4"
LORD_OF_THE_HOST_ROW_ID = f"{LORD_EXULTANT_DATASHEET_ID}:5"
SCUTTLING_HORRORS_ROW_ID = f"{CHAOS_SPAWN_DATASHEET_ID}:3"
GLUTTON_FOR_PUNISHMENT_ROW_ID = f"{MAULERFIEND_DATASHEET_ID}:3"

DATASHEETS = {
    LORD_EXULTANT_DATASHEET_ID: "Lord Exultant",
    CHAOS_SPAWN_DATASHEET_ID: "Chaos Spawn",
    MAULERFIEND_DATASHEET_ID: "Maulerfiend",
}
ABILITY_NAMES = {
    EUPHORIC_STRIKES_ROW_ID: "Euphoric Strikes",
    LORD_OF_THE_HOST_ROW_ID: "LORD OF THE HOST",
    SCUTTLING_HORRORS_ROW_ID: "Scuttling Horrors",
    GLUTTON_FOR_PUNISHMENT_ROW_ID: "Glutton for Punishment",
}
EXPECTED_PREDECESSOR_TEXT_SHA256 = {
    EUPHORIC_STRIKES_ROW_ID: ("25e0b51ee3dd0032335245b2395c002487584b176310f4567aeb17cfeca3c061"),
    LORD_OF_THE_HOST_ROW_ID: ("3c17e8920f6d33be40be6a0c40a296b7b08f99f86d3123e2f675bd8daa01d129"),
    SCUTTLING_HORRORS_ROW_ID: ("177258dc4b4111e79f37c1b4521b8153c587014f6ff39f55439e9f7561614f0a"),
    GLUTTON_FOR_PUNISHMENT_ROW_ID: (
        "e4815aa8797fcc8c40a1551d5a84913b7fb74ea541ab58fee1cc3ae8232ae618"
    ),
}
EXPECTED_REVIEW_ROWS = {
    LORD_EXULTANT_DATASHEET_ID: {
        "datasheet_id": LORD_EXULTANT_DATASHEET_ID,
        "datasheet_name": "Lord Exultant",
        "review_row_id": f"source:{LORD_EXULTANT_DATASHEET_ID}",
        "review_treatment": "unchanged_predecessor",
        "pdf_page_reference": None,
    },
    CHAOS_SPAWN_DATASHEET_ID: {
        "datasheet_id": CHAOS_SPAWN_DATASHEET_ID,
        "datasheet_name": "Chaos Spawn",
        "review_row_id": f"source:{CHAOS_SPAWN_DATASHEET_ID}",
        "review_treatment": "rules_update",
        "pdf_page_reference": "Rules Updates, physical PDF page 9",
    },
    MAULERFIEND_DATASHEET_ID: {
        "datasheet_id": MAULERFIEND_DATASHEET_ID,
        "datasheet_name": "Maulerfiend",
        "review_row_id": f"source:{MAULERFIEND_DATASHEET_ID}",
        "review_treatment": "unchanged_predecessor",
        "pdf_page_reference": None,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the grouped Emperor's Children datasheet RuleIR artifact."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed artifact differs from generated output.",
    )
    args = parser.parse_args()
    generate_registered_rule_ir_shard(shard_id=SHARD_ID, check=args.check)


def generated_artifact_payload() -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source_artifact = WahapediaJsonArtifact.from_payload(
        cast(WahapediaJsonArtifactPayload, source_payload)
    )
    source_rows = _validated_source_rows(source_artifact)
    current_text_by_source_row_id = {
        source_row_id: _row_description(row) for source_row_id, row in source_rows.items()
    }
    current_text_by_source_row_id[SCUTTLING_HORRORS_ROW_ID] = (
        _validated_scuttling_horrors_overlay_text(source_rows[SCUTTLING_HORRORS_ROW_ID])
    )
    review_payload = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    review_rows = _validated_review_rows(review_payload)
    rule_irs = {
        EUPHORIC_STRIKES_ROW_ID: _euphoric_strikes_rule_ir(
            current_text_by_source_row_id[EUPHORIC_STRIKES_ROW_ID]
        ),
        LORD_OF_THE_HOST_ROW_ID: _lord_of_the_host_rule_ir(
            current_text_by_source_row_id[LORD_OF_THE_HOST_ROW_ID]
        ),
        SCUTTLING_HORRORS_ROW_ID: _scuttling_horrors_rule_ir(
            current_text_by_source_row_id[SCUTTLING_HORRORS_ROW_ID]
        ),
        GLUTTON_FOR_PUNISHMENT_ROW_ID: _glutton_for_punishment_rule_ir(
            current_text_by_source_row_id[GLUTTON_FOR_PUNISHMENT_ROW_ID]
        ),
    }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_artifact.artifact_hash(),
        "official_document_filename": OFFICIAL_PDF_PATH.name,
        "official_document_sha256": hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest(),
        "official_document_pages": [9],
        "review_manifest_filename": REVIEW_MANIFEST_PATH.name,
        "review_manifest_sha256": canonical_json_sha256(REVIEW_MANIFEST_PATH),
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheets": [review_rows[datasheet_id] for datasheet_id in sorted(review_rows)],
        "records": {
            source_row_id: {
                "datasheet_id": source_row_id.split(":", maxsplit=1)[0],
                "datasheet_name": DATASHEETS[source_row_id.split(":", maxsplit=1)[0]],
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


def _validated_source_rows(
    source_artifact: WahapediaJsonArtifact,
) -> dict[str, NormalizedSourceRow]:
    source_rows: dict[str, NormalizedSourceRow] = {}
    for row in source_artifact.rows:
        if row.source_row_id not in ABILITY_NAMES:
            continue
        fields = row.runtime_fields_payload()
        source_row_id = row.source_row_id
        datasheet_id = source_row_id.split(":", maxsplit=1)[0]
        if fields.get("datasheet_id") != datasheet_id:
            raise ValueError("Grouped Emperor's Children source datasheet identity drifted.")
        if fields.get("name") != ABILITY_NAMES[source_row_id]:
            raise ValueError("Grouped Emperor's Children source ability identity drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Grouped Emperor's Children source ability text is missing.")
        if (
            hashlib.sha256(description.encode()).hexdigest()
            != EXPECTED_PREDECESSOR_TEXT_SHA256[source_row_id]
        ):
            raise ValueError("Grouped Emperor's Children predecessor ability text drifted.")
        source_rows[source_row_id] = row
    if set(source_rows) != set(ABILITY_NAMES):
        raise ValueError("Grouped Emperor's Children source-row inventory drifted.")
    return source_rows


def _validated_scuttling_horrors_overlay_text(source_row: NormalizedSourceRow) -> str:
    operations = tuple(
        operation
        for operation in source_overlay.overlay_pack().operations
        if operation.source_table == "Datasheets_abilities"
        and operation.source_row_id == SCUTTLING_HORRORS_ROW_ID
    )
    if len(operations) != 1:
        raise ValueError("Scuttling Horrors overlay operation inventory drifted.")
    operation = operations[0]
    if (
        operation.operation_kind is not SourceOverlayOperationKind.UPDATE_ROW
        or operation.expected_preimage_hash != source_row_hash(source_row)
        or dict(operation.fields) != {"description": source_overlay.SCUTTLING_HORRORS_DESCRIPTION}
    ):
        raise ValueError("Scuttling Horrors overlay operation drifted.")
    return source_overlay.SCUTTLING_HORRORS_DESCRIPTION


def _validated_review_rows(review_payload: object) -> dict[str, dict[str, object]]:
    if not isinstance(review_payload, dict):
        raise TypeError("Grouped Emperor's Children faction-pack review manifest is missing.")
    manifest = cast(dict[str, object], review_payload)
    raw_factions = manifest.get("factions")
    if not isinstance(raw_factions, list):
        raise TypeError("Grouped Emperor's Children faction-pack review manifest is missing.")
    factions: list[dict[str, object]] = []
    for raw_faction in cast(list[object], raw_factions):
        if not isinstance(raw_faction, dict):
            continue
        faction = cast(dict[str, object], raw_faction)
        if faction.get("faction_id") == "emperors-children":
            factions.append(faction)
    if len(factions) != 1:
        raise ValueError("Grouped Emperor's Children review faction identity drifted.")
    faction = factions[0]
    raw_rows = faction.get("rows")
    if not isinstance(raw_rows, list):
        raise TypeError("Grouped Emperor's Children review faction rows are invalid.")
    if (
        faction.get("pdf_filename") != OFFICIAL_PDF_PATH.name
        or faction.get("pdf_sha256") != hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("Grouped Emperor's Children review PDF provenance drifted.")
    rows: dict[str, dict[str, object]] = {}
    for raw_row in cast(list[object], raw_rows):
        if not isinstance(raw_row, dict):
            continue
        row = cast(dict[str, object], raw_row)
        if row.get("datasheet_id") not in DATASHEETS:
            continue
        datasheet_id = cast(str, row["datasheet_id"])
        expected = EXPECTED_REVIEW_ROWS[datasheet_id]
        actual = {
            "datasheet_id": datasheet_id,
            "datasheet_name": row.get("datasheet_name"),
            "review_row_id": row.get("review_row_id"),
            "review_treatment": row.get("treatment"),
            "pdf_page_reference": row.get("pdf_page_reference"),
        }
        if actual != expected:
            raise ValueError("Grouped Emperor's Children review row drifted.")
        rows[datasheet_id] = actual
    if set(rows) != set(DATASHEETS):
        raise ValueError("Grouped Emperor's Children review-row inventory drifted.")
    return rows


def _euphoric_strikes_rule_ir(text: str) -> RuleIR:
    source_row_id = EUPHORIC_STRIKES_ROW_ID
    return _manual_rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17c:characteristic-modifier",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "at the start of the Fight phase"),
                    parameters=_parameters(("edge", "start"), ("phase", "fight")),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.FREQUENCY_LIMIT,
                        source_span=_span(
                            text,
                            (
                                "Once per battle, at the start of the Fight phase, this model "
                                "can use this ability"
                            ),
                        ),
                        parameters=_parameters(
                            ("activation_kind", "optional_ability_use"),
                            ("max_uses", 1),
                            ("scope", "battle"),
                            ("usage_subject", "this_model"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "this model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=_span(
                            text,
                            (
                                "add 3 to the Attacks characteristic of melee weapons equipped "
                                "by this model"
                            ),
                        ),
                        parameters=_parameters(
                            ("characteristic", "attacks"),
                            ("delta", 3),
                            ("weapon_scope", "melee"),
                        ),
                    ),
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=_span(
                            text,
                            ("improve the Armour Penetration characteristic of those weapons by 1"),
                        ),
                        parameters=_parameters(
                            ("characteristic", "armor_penetration"),
                            ("delta", -1),
                            ("weapon_scope", "melee"),
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


def _lord_of_the_host_rule_ir(text: str) -> RuleIR:
    source_row_id = LORD_OF_THE_HOST_ROW_ID
    condition_text = (
        "If this model is attached to an Emperor's Children Battleline unit during the "
        "Declare Battle Formations step"
    )
    return _manual_rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            _conditional_leader_ability_grant_clause(
                source_row_id=source_row_id,
                index=1,
                text=text,
                condition_text=condition_text,
                ability="infiltrators",
                effect_text="Infiltrators",
            ),
            _conditional_leader_ability_grant_clause(
                source_row_id=source_row_id,
                index=2,
                text=text,
                condition_text=condition_text,
                ability="scouts",
                effect_text='Scouts 6"',
                distance_inches=6,
            ),
        ),
    )


def _conditional_leader_ability_grant_clause(
    *,
    source_row_id: str,
    index: int,
    text: str,
    condition_text: str,
    ability: str,
    effect_text: str,
    distance_inches: int | None = None,
) -> RuleClause:
    effect_parameters: list[tuple[str, RuleParameterValue]] = [
        ("ability", ability),
        ("target_scope", "this_model"),
    ]
    if distance_inches is not None:
        effect_parameters.append(("distance_inches", distance_inches))
    return RuleClause(
        clause_id=_clause_id(source_row_id, index),
        template_id="phase17m:conditional-leading-bodyguard-ability-grant",
        source_span=_span(text, text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, condition_text),
                parameters=_parameters(("relationship", "this_model_leading_unit")),
            ),
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=_span(text, "Battleline"),
                parameters=_parameters(
                    ("gate_subject", "bodyguard_unit"),
                    ("required_keyword", "BATTLELINE"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span(text, effect_text),
                parameters=_parameters(*effect_parameters),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(text, condition_text),
        ),
    )


def _glutton_for_punishment_rule_ir(text: str) -> RuleIR:
    source_row_id = GLUTTON_FOR_PUNISHMENT_ROW_ID
    return _manual_rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            _source_strength_attack_roll_clause(
                source_row_id=source_row_id,
                index=1,
                text=text,
                clause_text=(
                    "Each time this model makes an attack, if it is below its Starting Strength, "
                    "add 1 to the Hit roll."
                ),
                condition_text="if it is below its Starting Strength",
                target_constraint="source_unit_below_starting_strength",
                roll_type="hit",
                effect_text="add 1 to the Hit roll",
            ),
            _source_strength_attack_roll_clause(
                source_row_id=source_row_id,
                index=2,
                text=text,
                clause_text=(
                    "If this model is also Below Half-strength, add 1 to the Wound roll as well."
                ),
                condition_text="If this model is also Below Half-strength",
                target_constraint="source_unit_below_half_strength",
                roll_type="wound",
                effect_text="add 1 to the Wound roll",
            ),
        ),
    )


def _source_strength_attack_roll_clause(
    *,
    source_row_id: str,
    index: int,
    text: str,
    clause_text: str,
    condition_text: str,
    target_constraint: str,
    roll_type: str,
    effect_text: str,
) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(source_row_id, index),
        template_id="phase17c:dice-roll-modifier",
        source_span=_span(text, clause_text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(text, "Each time this model makes an attack"),
            parameters=_parameters(("roll_type", roll_type)),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, condition_text),
                parameters=_parameters(
                    ("gate_subject", "source_unit"),
                    ("relationship", "this_model_makes_attack"),
                    ("target_constraint", target_constraint),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(
                text,
                "this model",
                start_at=text.index(clause_text),
            ),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_DICE_ROLL,
                source_span=_span(text, effect_text),
                parameters=_parameters(("delta", 1), ("roll_type", roll_type)),
            ),
        ),
    )


def _scuttling_horrors_rule_ir(text: str) -> RuleIR:
    source_row_id = SCUTTLING_HORRORS_ROW_ID
    source_id = f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}"
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(source_id=source_id, raw_text=text),
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
        ),
    )
    rule_ir = compiled.rule_ir
    if (
        rule_ir.source_id != source_id
        or rule_ir.normalized_text != text
        or not rule_ir.is_supported
    ):
        raise ValueError("Scuttling Horrors fixed-distance RuleIR compilation drifted.")
    if len(rule_ir.clauses) != 1 or len(rule_ir.clauses[0].effects) != 1:
        raise ValueError("Scuttling Horrors fixed-distance RuleIR shape drifted.")
    clause = rule_ir.clauses[0]
    if (
        clause.template_id != "phase17c:out-of-phase-action"
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or parameter_payload(clause.trigger.parameters)
        != {
            "edge": "after",
            "owner": "opponent",
            "phase": "movement",
            "subject": "enemy_unit",
            "timing_window": "enemy_unit_move_end",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or parameter_payload(clause.target.parameters)
        or clause.duration is not None
        or tuple(
            (condition.kind, parameter_payload(condition.parameters))
            for condition in clause.conditions
        )
        != (
            (
                RuleConditionKind.DISTANCE_PREDICATE,
                {
                    "distance_inches": 8,
                    "object_kind": "unit",
                    "object_reference": "this",
                    "predicate": "within",
                    "qualifier": None,
                    "range_kind": "numeric_range",
                    "subject": "enemy_unit",
                },
            ),
            (
                RuleConditionKind.DISTANCE_PREDICATE,
                {
                    "distance_inches": None,
                    "negated": True,
                    "object_allegiance": "enemy",
                    "object_kind": "unit",
                    "object_quantity": "one_or_more",
                    "predicate": "within_engagement_range",
                    "qualifier": None,
                    "range_kind": "engagement_range",
                    "subject": "this_unit",
                },
            ),
        )
    ):
        raise ValueError("Scuttling Horrors trigger, target, or condition semantics drifted.")
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.OUT_OF_PHASE_ACTION or parameter_payload(
        effect.parameters
    ) != {
        "action": "move",
        "action_group": "movement_end_reactive_normal_move",
        "distance_inches": 6,
        "movement_kind": "triggered",
        "movement_mode": "normal",
        "optional": True,
    }:
        raise ValueError("Scuttling Horrors fixed-distance move effect drifted.")
    return rule_ir


def _manual_rule_ir(*, source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=(
            f"phase17k:emperors-children:lord-exultant-maulerfiend-spawn:datasheet:{source_row_id}"
        ),
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=MANUAL_PARSER_VERSION,
        clauses=clauses,
    )


def _row_description(row: NormalizedSourceRow) -> str:
    description = row.runtime_fields_payload().get("description")
    if type(description) is not str or not description:
        raise ValueError("Grouped Emperor's Children source ability text is missing.")
    return description


def _clause_id(source_row_id: str, index: int) -> str:
    return (
        "phase17k:emperors-children:lord-exultant-maulerfiend-spawn:"
        f"datasheet:{source_row_id}:clause:{index:03d}"
    )


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _span(text: str, fragment: str, *, start_at: int = 0) -> TextSpan:
    start = text.index(fragment, start_at)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


def _sha256_payload(payload: dict[str, object]) -> str:
    hash_payload = {**payload, "package_hash": ""}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    main()
