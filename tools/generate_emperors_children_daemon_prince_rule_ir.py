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

ARTIFACT_SCHEMA = "core-v2-emperors-children-daemon-prince-of-slaanesh-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-emperors-children-daemon-prince-of-slaanesh-datasheet-2026-08"
SHARD_ID = "emperors-children"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

DATASHEET_ID = "000004086"
DATASHEET_NAME = "Daemon Prince of Slaanesh"
LORD_OF_EXCESS_ROW_ID = f"{DATASHEET_ID}:3"
EXCESSIVE_VIGOUR_ROW_ID = f"{DATASHEET_ID}:4"
ECSTATIC_DEATH_ROW_ID = f"{DATASHEET_ID}:5"

ABILITY_NAMES = {
    LORD_OF_EXCESS_ROW_ID: "Lord of Excess",
    EXCESSIVE_VIGOUR_ROW_ID: "Excessive Vigour (Aura)",
    ECSTATIC_DEATH_ROW_ID: "Ecstatic Death",
}
EXPECTED_SOURCE_ARTIFACT_HASH = "2cf705d43ab06ba0345438d9104a8cf4dc6eff2d8c13e19f230ec8aa6169b693"
EXPECTED_SOURCE_ROW_HASHES = {
    LORD_OF_EXCESS_ROW_ID: ("78e9180d09d0b2449a327b5e1b45dc399ac22e593353c36d07e6424f11175b48"),
    EXCESSIVE_VIGOUR_ROW_ID: ("fa4e2fb6e1cb8c9e3141d365181a8210e39c61f9dd420beb28add5b72f4f02fd"),
    ECSTATIC_DEATH_ROW_ID: ("dc693e26449c6f0db0ad5ca17d4b64905621889f187a12b9f018504fbd7ddfd9"),
}
EXPECTED_PREDECESSOR_TEXT_SHA256 = {
    LORD_OF_EXCESS_ROW_ID: ("9e718c2486acc18b48038a0b06413c9893a4127bd99514806c78c0eb186f01f2"),
    EXCESSIVE_VIGOUR_ROW_ID: ("564f7f1afb6326b673c3f72de5756362440274fad4c4c461442e9ace42ce8bfa"),
    ECSTATIC_DEATH_ROW_ID: ("6093398da2860af58c4d65a875a41127ce78307b4a894976f81a9fea79c05e06"),
}
EXPECTED_REVIEW_ROW = {
    "datasheet_id": DATASHEET_ID,
    "datasheet_name": DATASHEET_NAME,
    "review_row_id": f"source:{DATASHEET_ID}",
    "review_treatment": "unchanged_predecessor",
    "pdf_page_reference": None,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Emperor's Children Daemon Prince RuleIR artifact."
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
    review_payload = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    review_row = _validated_review_row(review_payload)
    rule_irs = {
        LORD_OF_EXCESS_ROW_ID: _lord_of_excess_rule_ir(
            _row_description(source_rows[LORD_OF_EXCESS_ROW_ID])
        ),
        EXCESSIVE_VIGOUR_ROW_ID: _excessive_vigour_rule_ir(
            _row_description(source_rows[EXCESSIVE_VIGOUR_ROW_ID])
        ),
        ECSTATIC_DEATH_ROW_ID: _ecstatic_death_rule_ir(
            _row_description(source_rows[ECSTATIC_DEATH_ROW_ID])
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
        "official_document_pages": [],
        "review_manifest_filename": REVIEW_MANIFEST_PATH.name,
        "review_manifest_sha256": canonical_json_sha256(REVIEW_MANIFEST_PATH),
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheets": [review_row],
        "records": {
            source_row_id: {
                "datasheet_id": DATASHEET_ID,
                "datasheet_name": DATASHEET_NAME,
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
    if source_artifact.artifact_hash() != EXPECTED_SOURCE_ARTIFACT_HASH:
        raise ValueError("Daemon Prince source artifact hash drifted.")
    source_rows: dict[str, NormalizedSourceRow] = {}
    for row in source_artifact.rows:
        if row.source_row_id not in ABILITY_NAMES:
            continue
        source_row_id = row.source_row_id
        fields = row.runtime_fields_payload()
        if fields.get("datasheet_id") != DATASHEET_ID:
            raise ValueError("Daemon Prince source datasheet identity drifted.")
        if fields.get("name") != ABILITY_NAMES[source_row_id]:
            raise ValueError("Daemon Prince source ability identity drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Daemon Prince source ability text is missing.")
        if source_row_hash(row) != EXPECTED_SOURCE_ROW_HASHES[source_row_id]:
            raise ValueError("Daemon Prince source row hash drifted.")
        if (
            hashlib.sha256(description.encode()).hexdigest()
            != EXPECTED_PREDECESSOR_TEXT_SHA256[source_row_id]
        ):
            raise ValueError("Daemon Prince predecessor ability text drifted.")
        source_rows[source_row_id] = row
    if set(source_rows) != set(ABILITY_NAMES):
        raise ValueError("Daemon Prince source-row inventory drifted.")
    return source_rows


def _validated_review_row(review_payload: object) -> dict[str, object]:
    if not isinstance(review_payload, dict):
        raise TypeError("Daemon Prince faction-pack review manifest is missing.")
    manifest = cast(dict[str, object], review_payload)
    raw_factions = manifest.get("factions")
    if not isinstance(raw_factions, list):
        raise TypeError("Daemon Prince faction-pack review manifest is missing.")
    factions: list[dict[str, object]] = []
    for raw_faction in cast(list[object], raw_factions):
        if not isinstance(raw_faction, dict):
            continue
        faction_row = cast(dict[str, object], raw_faction)
        if faction_row.get("faction_id") == "emperors-children":
            factions.append(faction_row)
    if len(factions) != 1:
        raise ValueError("Daemon Prince review faction identity drifted.")
    faction = factions[0]
    raw_rows = faction.get("rows")
    if not isinstance(raw_rows, list):
        raise TypeError("Daemon Prince review faction rows are invalid.")
    if (
        faction.get("pdf_filename") != OFFICIAL_PDF_PATH.name
        or faction.get("pdf_sha256") != hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("Daemon Prince review PDF provenance drifted.")
    rows: list[dict[str, object]] = []
    for raw_row in cast(list[object], raw_rows):
        if not isinstance(raw_row, dict):
            continue
        row = cast(dict[str, object], raw_row)
        if row.get("datasheet_id") == DATASHEET_ID:
            rows.append(row)
    if len(rows) != 1:
        raise ValueError("Daemon Prince review-row inventory drifted.")
    row = rows[0]
    actual = {
        "datasheet_id": row.get("datasheet_id"),
        "datasheet_name": row.get("datasheet_name"),
        "review_row_id": row.get("review_row_id"),
        "review_treatment": row.get("treatment"),
        "pdf_page_reference": row.get("pdf_page_reference"),
    }
    if actual != EXPECTED_REVIEW_ROW:
        raise ValueError("Daemon Prince review row drifted.")
    return actual


def _lord_of_excess_rule_ir(text: str) -> RuleIR:
    source_row_id = LORD_OF_EXCESS_ROW_ID
    clause = RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:conditional-ability-grant",
        source_span=_span(text, text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span(
                    text,
                    'within 3" of one or more friendly Slaanesh Infantry units',
                ),
                parameters=_parameters(
                    ("allegiance", "friendly"),
                    ("distance_inches", 3),
                    ("object_kind", "unit"),
                    ("predicate", "within"),
                    ("required_keyword_sequence", ("SLAANESH", "INFANTRY")),
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
                source_span=_span(text, "Lone Operative ability"),
                parameters=_parameters(
                    ("ability", "lone_operative"),
                    ("target_scope", "this_model"),
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(text, "While this model is within"),
        ),
    )
    return _rule_ir(source_row_id, text, clause)


def _excessive_vigour_rule_ir(text: str) -> RuleIR:
    source_row_id = EXCESSIVE_VIGOUR_ROW_ID
    clause = RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17p:charged-melee-weapon-characteristic-aura",
        source_span=_span(text, text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.AURA,
                source_span=_span(text, "While a friendly Slaanesh unit is within"),
            ),
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span(text, 'within 6" of this model'),
                parameters=_parameters(
                    ("distance_inches", 6),
                    ("object_kind", "unit"),
                    ("object_reference", "this_model"),
                    ("predicate", "within"),
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.KEYWORD_GATE,
                source_span=_span(text, "Slaanesh unit"),
                parameters=_parameters(("required_keyword", "SLAANESH")),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.AURA_UNITS,
            source_span=_span(text, "a friendly Slaanesh unit"),
            parameters=_parameters(
                ("allegiance", "friendly"),
                ("include_source_unit", True),
            ),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                source_span=_span(
                    text,
                    (
                        "improve the Armour Penetration characteristic of melee weapons "
                        "equipped by models in that unit by 1"
                    ),
                ),
                parameters=_parameters(
                    ("characteristic", "armor_penetration"),
                    ("delta", -1),
                    ("requires_charge_move_this_turn", True),
                    ("target_scope", "aura_units"),
                    ("weapon_scope", "melee"),
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(text, "While a friendly Slaanesh unit is within"),
        ),
    )
    return _rule_ir(source_row_id, text, clause)


def _ecstatic_death_rule_ir(text: str) -> RuleIR:
    source_row_id = ECSTATIC_DEATH_ROW_ID
    clause = RuleClause(
        clause_id=_clause_id(source_row_id, 1),
        template_id="phase17c:conditional-model-fight-on-death",
        source_span=_span(text, text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.MODEL_DESTROYED,
            source_span=_span(text, "this model is destroyed by a melee attack"),
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
                source_span=_span(text, "it has not fought this phase"),
                parameters=_parameters(
                    ("gate_subject", "destroyed_model"),
                    ("relationship", "has_not_fought_this_phase"),
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
                source_span=_span(
                    text,
                    (
                        "This model can fight after the attacking unit has finished making "
                        "its attacks"
                    ),
                ),
                parameters=_parameters(
                    ("ability", "fight_on_death"),
                    ("optional", True),
                    ("trigger_roll_threshold", 2),
                    ("trigger_roll_type", "emperors_children_ecstatic_death"),
                ),
            ),
        ),
    )
    return _rule_ir(source_row_id, text, clause)


def _rule_ir(source_row_id: str, text: str, clause: RuleClause) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:emperors-children:daemon-prince:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=(clause,),
    )


def _row_description(row: NormalizedSourceRow) -> str:
    description = row.runtime_fields_payload().get("description")
    if type(description) is not str or not description:
        raise ValueError("Daemon Prince source ability text is missing.")
    return description


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:emperors-children:daemon-prince:datasheet:{source_row_id}:clause:{index:03d}"


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
