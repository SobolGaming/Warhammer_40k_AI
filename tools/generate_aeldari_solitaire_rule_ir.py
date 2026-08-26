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

from warhammer40k_core.core.attributes import Characteristic
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
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_JSON_DIR = (
    REPO_ROOT / "data" / "source_snapshots" / "wahapedia" / "10th-edition" / "2026-06-14" / "json"
)
SOURCE_PATH = SOURCE_JSON_DIR / "Datasheets_abilities.json"
ABILITIES_SOURCE_PATH = SOURCE_JSON_DIR / "Abilities.json"
OFFICIAL_PDF_PATH = (
    REPO_ROOT
    / "data"
    / "raw"
    / "faction_packs"
    / "eng_22-07_warhammer_40,000_faction_pack_aeldari-qe1ykopo7h-blfkukhecc.pdf"
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
    / "aeldari.json"
)

ARTIFACT_SCHEMA = "core-v2-aeldari-solitaire-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-solitaire-datasheet-2026-08"
SHARD_ID = "aeldari"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

DATASHEET_ID = "000002538"
DATASHEET_NAME = "Solitaire"
DISPARATE_PATHS_LINK_ROW_ID = f"{DATASHEET_ID}:5"
BLITZ_ROW_ID = f"{DATASHEET_ID}:6"
BLUR_OF_MOVEMENT_ROW_ID = f"{DATASHEET_ID}:7"
PATH_OF_DAMNATION_ROW_ID = f"{DATASHEET_ID}:8"
FLIP_BELT_ROW_ID = f"{DATASHEET_ID}:9"
DISPARATE_PATHS_ABILITY_ROW_ID = "000009896:AE"

RULE_IR_SOURCE_ROW_IDS = (
    BLITZ_ROW_ID,
    BLUR_OF_MOVEMENT_ROW_ID,
    FLIP_BELT_ROW_ID,
)
VALIDATED_DATASHEET_SOURCE_ROW_IDS = (
    DISPARATE_PATHS_LINK_ROW_ID,
    BLITZ_ROW_ID,
    BLUR_OF_MOVEMENT_ROW_ID,
    PATH_OF_DAMNATION_ROW_ID,
    FLIP_BELT_ROW_ID,
)
ABILITY_NAMES = {
    BLITZ_ROW_ID: "Blitz",
    BLUR_OF_MOVEMENT_ROW_ID: "Blur of Movement",
    FLIP_BELT_ROW_ID: "Flip Belt",
}
EXPECTED_SOURCE_ARTIFACT_HASH = "2cf705d43ab06ba0345438d9104a8cf4dc6eff2d8c13e19f230ec8aa6169b693"
EXPECTED_ABILITIES_SOURCE_ARTIFACT_HASH = (
    "5d2718402066eecc33195e14f98d44900e374e8450ef246c2b766dd08e833990"
)
EXPECTED_SOURCE_ROW_HASHES = {
    DISPARATE_PATHS_LINK_ROW_ID: (
        "9fb6a60d9569ef218781538a7230e4d9b6288a7c81fe7af4ac09f4fe601c1067"
    ),
    BLITZ_ROW_ID: "9ea4336d9d3f3172e95406c7b6296913e0acaef48dc8a26846fe743531c8211b",
    BLUR_OF_MOVEMENT_ROW_ID: ("78f23f7ed60e51ab6b9045011b91ceebac67a4a4d5898872556af3b1e88cdd87"),
    PATH_OF_DAMNATION_ROW_ID: ("c674d63ce799698d3666314f44274310aee1ad5056420b36391c5cfb2cd87bbb"),
    FLIP_BELT_ROW_ID: ("7c9b047b1c82c1f3f5ac84333db059aa669a666a724d300703f4f8fd3e0fc273"),
}
EXPECTED_SOURCE_TEXT_SHA256 = {
    BLITZ_ROW_ID: "f448046c569cf50472f22eb24e23694891bdb1ce2259330b42a76ec79ec5bc9d",
    BLUR_OF_MOVEMENT_ROW_ID: ("c12db118b5fdabb537def15f7f957529eaba99d020a3f7703fbce50aa4087f61"),
    PATH_OF_DAMNATION_ROW_ID: ("68f9f2b4114e7651ffa6f574d7fca75f35602236e3b1921225a33ec03423b752"),
    FLIP_BELT_ROW_ID: ("a77f0c48d79b77c43e29f08b60cc35078c583d3cfc651d20b4d51fa2940aeeb9"),
}
EXPECTED_DISPARATE_PATHS_ROW_HASH = (
    "4d4c33de2795689a0fcdc0b56570b95f22664ada3b67a492da111d102a610635"
)
EXPECTED_DISPARATE_PATHS_TEXT_SHA256 = (
    "d2edb7f4a69c283f496a68becfa6353697afbb4f3429e5fa6b068634837650af"
)
EXPECTED_REVIEW_ROW = {
    "datasheet_id": DATASHEET_ID,
    "datasheet_name": DATASHEET_NAME,
    "group": "Harlequins",
    "pdf_page_reference": None,
    "review_note": "Explicitly reviewed: the Faction Pack neither reprints nor updates this row.",
    "review_row_id": f"source:{DATASHEET_ID}",
    "treatment": "unchanged_predecessor",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Aeldari Solitaire RuleIR artifact.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed artifact differs from generated output.",
    )
    args = parser.parse_args()
    generate_registered_rule_ir_shard(shard_id=SHARD_ID, check=args.check)


def generated_artifact_payload() -> dict[str, object]:
    source_artifact = _source_artifact(SOURCE_PATH)
    source_rows = _validated_datasheet_source_rows(source_artifact)
    _validate_disparate_paths_ability(
        source_link_row=source_rows[DISPARATE_PATHS_LINK_ROW_ID],
        abilities_artifact=_source_artifact(ABILITIES_SOURCE_PATH),
    )
    review_payload = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    review_row = _validate_review_row(review_payload)
    rule_irs = {
        BLITZ_ROW_ID: _blitz_rule_ir(_row_description(source_rows[BLITZ_ROW_ID])),
        BLUR_OF_MOVEMENT_ROW_ID: _blur_of_movement_rule_ir(
            _row_description(source_rows[BLUR_OF_MOVEMENT_ROW_ID])
        ),
        FLIP_BELT_ROW_ID: _flip_belt_rule_ir(_row_description(source_rows[FLIP_BELT_ROW_ID])),
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
        "review_row_id": review_row["review_row_id"],
        "review_treatment": review_row["treatment"],
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


def _source_artifact(path: Path) -> WahapediaJsonArtifact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))


def _validated_datasheet_source_rows(
    source_artifact: WahapediaJsonArtifact,
) -> dict[str, NormalizedSourceRow]:
    if source_artifact.artifact_hash() != EXPECTED_SOURCE_ARTIFACT_HASH:
        raise ValueError("Solitaire datasheet-ability source artifact hash drifted.")
    rows: dict[str, NormalizedSourceRow] = {}
    for row in source_artifact.rows:
        if row.source_row_id not in VALIDATED_DATASHEET_SOURCE_ROW_IDS:
            continue
        source_row_id = row.source_row_id
        fields = row.runtime_fields_payload()
        if fields.get("datasheet_id") != DATASHEET_ID:
            raise ValueError("Solitaire source datasheet identity drifted.")
        if source_row_hash(row) != EXPECTED_SOURCE_ROW_HASHES[source_row_id]:
            raise ValueError("Solitaire source row hash drifted.")
        if source_row_id == DISPARATE_PATHS_LINK_ROW_ID:
            if (
                fields.get("ability_id") != "000009896"
                or fields.get("type") != "Faction"
                or fields.get("name") != ""
                or fields.get("description") != ""
            ):
                raise ValueError("Solitaire Disparate Paths linkage drifted.")
        else:
            expected_name, expected_type = {
                BLITZ_ROW_ID: ("Blitz", "Datasheet"),
                BLUR_OF_MOVEMENT_ROW_ID: ("Blur of Movement", "Datasheet"),
                PATH_OF_DAMNATION_ROW_ID: (
                    "PATH OF DAMNATION",
                    "Fortification (левая колонка)",
                ),
                FLIP_BELT_ROW_ID: ("Flip Belt", "Wargear"),
            }[source_row_id]
            description = fields.get("description")
            if fields.get("name") != expected_name or fields.get("type") != expected_type:
                raise ValueError("Solitaire source ability identity drifted.")
            if type(description) is not str or not description:
                raise ValueError("Solitaire source ability text is missing.")
            if (
                hashlib.sha256(description.encode()).hexdigest()
                != EXPECTED_SOURCE_TEXT_SHA256[source_row_id]
            ):
                raise ValueError("Solitaire predecessor ability text drifted.")
        rows[source_row_id] = row
    if set(rows) != set(VALIDATED_DATASHEET_SOURCE_ROW_IDS):
        raise ValueError("Solitaire source-row inventory drifted.")
    return rows


def _validate_disparate_paths_ability(
    *,
    source_link_row: NormalizedSourceRow,
    abilities_artifact: WahapediaJsonArtifact,
) -> None:
    if abilities_artifact.artifact_hash() != EXPECTED_ABILITIES_SOURCE_ARTIFACT_HASH:
        raise ValueError("Disparate Paths ability source artifact hash drifted.")
    link_fields = source_link_row.runtime_fields_payload()
    matches = tuple(
        row
        for row in abilities_artifact.rows
        if row.source_row_id == DISPARATE_PATHS_ABILITY_ROW_ID
    )
    if len(matches) != 1:
        raise ValueError("Disparate Paths resolved source-row inventory drifted.")
    row = matches[0]
    fields = row.runtime_fields_payload()
    if (
        link_fields.get("ability_id") != fields.get("id")
        or fields.get("faction_id") != "AE"
        or fields.get("name") != "Disparate Paths"
        or source_row_hash(row) != EXPECTED_DISPARATE_PATHS_ROW_HASH
    ):
        raise ValueError("Disparate Paths resolved source linkage drifted.")
    description = fields.get("description")
    if type(description) is not str or (
        hashlib.sha256(description.encode()).hexdigest() != EXPECTED_DISPARATE_PATHS_TEXT_SHA256
    ):
        raise ValueError("Disparate Paths resolved source text drifted.")


def _validate_review_row(review_payload: object) -> dict[str, object]:
    if not isinstance(review_payload, dict):
        raise TypeError("Solitaire faction-pack review manifest is missing.")
    manifest = cast(dict[str, object], review_payload)
    raw_factions = manifest.get("factions")
    if not isinstance(raw_factions, list):
        raise TypeError("Solitaire faction-pack review manifest is missing.")
    factions = tuple(
        cast(dict[str, object], faction)
        for faction in cast(list[object], raw_factions)
        if isinstance(faction, dict)
        and cast(dict[str, object], faction).get("faction_id") == "aeldari"
    )
    if len(factions) != 1:
        raise ValueError("Solitaire faction-pack review faction identity drifted.")
    faction = factions[0]
    raw_rows = faction.get("rows")
    if not isinstance(raw_rows, list):
        raise TypeError("Solitaire faction-pack review rows are invalid.")
    if (
        faction.get("pdf_filename") != OFFICIAL_PDF_PATH.name
        or faction.get("pdf_sha256") != hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("Solitaire faction-pack review PDF provenance drifted.")
    rows = tuple(
        cast(dict[str, object], row)
        for row in cast(list[object], raw_rows)
        if isinstance(row, dict)
        and cast(dict[str, object], row).get("datasheet_id") == DATASHEET_ID
    )
    if len(rows) != 1 or rows[0] != EXPECTED_REVIEW_ROW:
        raise ValueError("Solitaire faction-pack review row drifted.")
    return dict(rows[0])


def _blitz_rule_ir(text: str) -> RuleIR:
    source_row_id = BLITZ_ROW_ID
    return _rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17p:optional-pre-normal-move-random-characteristic-modifiers",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.UNIT_SELECTED,
                    source_span=_span(text, "before this model makes a Normal move"),
                    parameters=_parameters(
                        ("action", "normal_move"),
                        ("owner", "active_player"),
                        ("optional", True),
                        ("phase", "movement"),
                        ("subject", "this_model"),
                        ("timing_window", "before_normal_move"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.FREQUENCY_LIMIT,
                        source_span=_span(text, "Once per battle"),
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
                        kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
                        source_span=_span(
                            text,
                            "add 2D6\" to this model's Move characteristic",
                        ),
                        parameters=_parameters(
                            ("characteristic", Characteristic.MOVEMENT.value),
                            ("operation", "add"),
                            ("roll_expression", "2D6"),
                            ("target_scope", "this_model"),
                        ),
                    ),
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=_span(
                            text,
                            (
                                "add 3 to the Attacks characteristic of this model's "
                                "Solitaire weapons"
                            ),
                        ),
                        parameters=_parameters(
                            ("characteristic", Characteristic.ATTACKS.value),
                            ("delta", 3),
                            ("target_scope", "this_model"),
                            ("weapon_names", ("Solitaire weapons",)),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "until the end of the turn"),
                    parameters=_parameters(("endpoint", "turn")),
                ),
            ),
        ),
    )


def _blur_of_movement_rule_ir(text: str) -> RuleIR:
    source_row_id = BLUR_OF_MOVEMENT_ROW_ID
    return _rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17c:grant-ability",
                source_span=_span(text, text),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "This model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(
                            text,
                            "eligible to declare a charge in a turn in which it Advanced",
                        ),
                        parameters=_parameters(
                            ("ability", "can_advance_and_charge"),
                            ("target_scope", "this_model"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.PERMANENT,
                    source_span=_span(text, text),
                ),
            ),
        ),
    )


def _flip_belt_rule_ir(text: str) -> RuleIR:
    source_row_id = FLIP_BELT_ROW_ID
    movement_modes = ("normal", "advance", "fall_back", "charge")
    return _rule_ir(
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(source_row_id, 1),
                template_id="phase17p:movement-ignore-vertical-distance",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(
                        text,
                        (
                            "Each time the bearer's unit makes a Normal, Advance, Fall Back or "
                            "Charge move"
                        ),
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
                    source_span=_span(text, "the bearer"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
                        source_span=_span(text, "ignore any vertical distance"),
                        parameters=_parameters(
                            ("movement_modes", movement_modes),
                            ("permission", "ignore_vertical_distance"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _rule_ir(*, source_row_id: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:aeldari:solitaire:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _row_description(row: NormalizedSourceRow) -> str:
    description = row.runtime_fields_payload().get("description")
    if type(description) is not str or not description:
        raise ValueError("Solitaire source ability text is missing.")
    return description


def _clause_id(source_row_id: str, index: int) -> str:
    return f"phase17k:aeldari:solitaire:datasheet:{source_row_id}:clause:{index:03d}"


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
