from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope

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
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_overlay import SourceOverlayOperationKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_maulerfiend_datasheet_overlay_2026_07 as source_overlay,
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
OFFICIAL_PDF_DIRECTORY = REPO_ROOT / "data" / "raw" / "faction_packs"
REVIEW_MANIFEST_PATH = (
    REPO_ROOT / "data" / "source_manifests" / "faction_pack_datasheet_review_v1.json"
)

MANUAL_PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEET_NAME = "Maulerfiend"

CHAOS_SPACE_MARINES_DATASHEET_ID = "000000968"
THOUSAND_SONS_DATASHEET_ID = "000001029"
WORLD_EATERS_DATASHEET_ID = "000002639"

SIEGE_CRAWLER_ROW_ID = f"{CHAOS_SPACE_MARINES_DATASHEET_ID}:3"
SNARLING_PROTECTOR_ROW_ID = f"{THOUSAND_SONS_DATASHEET_ID}:2"
SCENT_OF_BLOOD_ROW_ID = f"{WORLD_EATERS_DATASHEET_ID}:3"
SAVAGE_EXALTATION_ROW_ID = f"{WORLD_EATERS_DATASHEET_ID}:4"

_ABILITY_NAME_BY_SOURCE_ROW_ID = {
    SIEGE_CRAWLER_ROW_ID: "Siege Crawler",
    SNARLING_PROTECTOR_ROW_ID: "Snarling Protector",
    SCENT_OF_BLOOD_ROW_ID: "The Scent of Blood",
    SAVAGE_EXALTATION_ROW_ID: "Savage Exaltation",
}
_EXPECTED_PREDECESSOR_TEXT_SHA256 = {
    SIEGE_CRAWLER_ROW_ID: "1df0c4e1113123b7e634de4a22551fa0b2e69d3c37fd9bf9e846ae200ac39b25",
    SNARLING_PROTECTOR_ROW_ID: ("be2835acce7faf8afdfbcbbc6b4a7458a8a99e4fc6972c687952958632fda7ec"),
    SCENT_OF_BLOOD_ROW_ID: ("ff7dfa8c10d5a6af8f51ce6c4bde7970d71563ddc8410e42db5e3ec64ff885b7"),
    SAVAGE_EXALTATION_ROW_ID: ("e7d3e123885f659acd4ad1342c5aefcc4915ad052e7fca3a26ba511c8c20f190"),
}


@dataclass(frozen=True, slots=True)
class _FactionSpec:
    faction_id: str
    shard_id: str
    datasheet_id: str
    source_package_id: str
    artifact_schema: str
    official_pdf_filename: str
    official_document_pages: tuple[int, ...]
    review_treatment: str
    pdf_page_reference: str | None
    source_row_ids: tuple[str, ...]
    rule_ir_builder_by_source_row_id: dict[str, Callable[[str, _FactionSpec], RuleIR]]


_FACTION_SPEC_BY_ID = {
    "chaos-space-marines": _FactionSpec(
        faction_id="chaos-space-marines",
        shard_id="chaos-space-marines",
        datasheet_id=CHAOS_SPACE_MARINES_DATASHEET_ID,
        source_package_id="gw-11e-chaos-space-marines-maulerfiend-datasheet-2026-07",
        artifact_schema="core-v2-chaos-space-marines-maulerfiend-rule-ir-v1",
        official_pdf_filename=(
            "eng_22-07_warhammer_40,000_faction_pack_chaos_space_marines-att4ehoaum-8mmiunajyf.pdf"
        ),
        official_document_pages=(),
        review_treatment="unchanged_predecessor",
        pdf_page_reference=None,
        source_row_ids=(SIEGE_CRAWLER_ROW_ID,),
        rule_ir_builder_by_source_row_id={
            SIEGE_CRAWLER_ROW_ID: lambda text, spec: _siege_crawler_rule_ir(text, spec)
        },
    ),
    "thousand-sons": _FactionSpec(
        faction_id="thousand-sons",
        shard_id="thousand-sons",
        datasheet_id=THOUSAND_SONS_DATASHEET_ID,
        source_package_id="gw-11e-thousand-sons-maulerfiend-datasheet-2026-07",
        artifact_schema="core-v2-thousand-sons-maulerfiend-rule-ir-v1",
        official_pdf_filename=(
            "eng_22-07_warhammer_40,000_faction_pack_thousand_sons-h1ysumgym3-kyfwf7cjpt.pdf"
        ),
        official_document_pages=(9, 10, 11),
        review_treatment="rules_update",
        pdf_page_reference="Rules Updates, physical PDF pages 9-11",
        source_row_ids=(SNARLING_PROTECTOR_ROW_ID,),
        rule_ir_builder_by_source_row_id={
            SNARLING_PROTECTOR_ROW_ID: lambda text, spec: _snarling_protector_rule_ir(text, spec)
        },
    ),
    "world-eaters": _FactionSpec(
        faction_id="world-eaters",
        shard_id="world-eaters",
        datasheet_id=WORLD_EATERS_DATASHEET_ID,
        source_package_id="gw-11e-world-eaters-maulerfiend-datasheet-2026-07",
        artifact_schema="core-v2-world-eaters-maulerfiend-rule-ir-v1",
        official_pdf_filename=(
            "eng_22-07_warhammer_40,000_faction_pack_world_eaters-5g8k1b5jg0-3ttsio6riy.pdf"
        ),
        official_document_pages=(7, 8),
        review_treatment="rules_update",
        pdf_page_reference="Rules Updates, physical PDF pages 7-8",
        source_row_ids=(SCENT_OF_BLOOD_ROW_ID, SAVAGE_EXALTATION_ROW_ID),
        rule_ir_builder_by_source_row_id={
            SCENT_OF_BLOOD_ROW_ID: lambda text, spec: _scent_of_blood_rule_ir(text, spec),
            SAVAGE_EXALTATION_ROW_ID: lambda text, spec: _savage_exaltation_rule_ir(text, spec),
        },
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate source-backed RuleIR for the non-EC Maulerfiend variants."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed stable RuleIR package differs from generated output.",
    )
    parser.add_argument(
        "--faction",
        choices=tuple(sorted(_FACTION_SPEC_BY_ID)),
        help="Identify the requesting faction shard; all stable shards remain atomic.",
    )
    args = parser.parse_args()
    shard_ids = (
        tuple(spec.shard_id for spec in _FACTION_SPEC_BY_ID.values())
        if args.faction is None
        else (_FACTION_SPEC_BY_ID[args.faction].shard_id,)
    )
    for shard_id in shard_ids:
        generate_registered_rule_ir_shard(shard_id=shard_id, check=args.check)


def generated_chaos_space_marines_artifact_payload() -> dict[str, object]:
    return _generated_artifact_payload(_FACTION_SPEC_BY_ID["chaos-space-marines"])


def generated_thousand_sons_artifact_payload() -> dict[str, object]:
    return _generated_artifact_payload(_FACTION_SPEC_BY_ID["thousand-sons"])


def generated_world_eaters_artifact_payload() -> dict[str, object]:
    return _generated_artifact_payload(_FACTION_SPEC_BY_ID["world-eaters"])


def _generated_artifact_payload(spec: _FactionSpec) -> dict[str, object]:
    source_payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    source_artifact = WahapediaJsonArtifact.from_payload(
        cast(WahapediaJsonArtifactPayload, source_payload)
    )
    source_rows = _validated_source_rows(source_artifact)
    current_text_by_source_row_id = _current_text_by_source_row_id(source_rows)
    review_payload = json.loads(REVIEW_MANIFEST_PATH.read_text(encoding="utf-8"))
    review_row = _validated_review_row(review_payload, spec=spec)
    official_pdf_path = OFFICIAL_PDF_DIRECTORY / spec.official_pdf_filename
    rule_irs = {
        source_row_id: spec.rule_ir_builder_by_source_row_id[source_row_id](
            RuleSourceText.from_raw(
                objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
                source_id=f"{spec.source_package_id}:datasheet:{source_row_id}",
                raw_text=current_text_by_source_row_id[source_row_id],
            ).normalized_text,
            spec,
        )
        for source_row_id in spec.source_row_ids
    }
    payload: dict[str, object] = {
        "artifact_schema": spec.artifact_schema,
        "source_package_id": spec.source_package_id,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "source_artifact_hash": source_artifact.artifact_hash(),
        "official_document_filename": official_pdf_path.name,
        "official_document_sha256": hashlib.sha256(official_pdf_path.read_bytes()).hexdigest(),
        "official_document_pages": list(spec.official_document_pages),
        "review_manifest_filename": REVIEW_MANIFEST_PATH.name,
        "review_manifest_sha256": canonical_json_sha256(REVIEW_MANIFEST_PATH),
        "review_row_id": review_row["review_row_id"],
        "review_treatment": review_row["review_treatment"],
        "overlay_package_hash": source_overlay.overlay_pack().package_hash(),
        "datasheet_id": spec.datasheet_id,
        "datasheet_name": DATASHEET_NAME,
        "records": {
            source_row_id: {
                "ability_name": _ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id],
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
        if row.source_row_id not in _ABILITY_NAME_BY_SOURCE_ROW_ID:
            continue
        fields = row.runtime_fields_payload()
        source_row_id = row.source_row_id
        expected_datasheet_id = source_row_id.split(":", maxsplit=1)[0]
        if fields.get("datasheet_id") != expected_datasheet_id:
            raise ValueError("Maulerfiend source datasheet identity drifted.")
        if fields.get("name") != _ABILITY_NAME_BY_SOURCE_ROW_ID[source_row_id]:
            raise ValueError("Maulerfiend source ability identity drifted.")
        description = fields.get("description")
        if type(description) is not str or not description:
            raise ValueError("Maulerfiend source ability text is missing.")
        if (
            hashlib.sha256(description.encode()).hexdigest()
            != _EXPECTED_PREDECESSOR_TEXT_SHA256[source_row_id]
        ):
            raise ValueError("Maulerfiend predecessor ability text drifted.")
        source_rows[source_row_id] = row
    if set(source_rows) != set(_ABILITY_NAME_BY_SOURCE_ROW_ID):
        raise ValueError("Maulerfiend source-row inventory drifted.")
    return source_rows


def _current_text_by_source_row_id(
    source_rows: dict[str, NormalizedSourceRow],
) -> dict[str, str]:
    pack = source_overlay.overlay_pack()
    operations = {
        operation.source_row_id: operation
        for operation in pack.operations
        if operation.source_table == "Datasheets_abilities"
    }
    expected_updated_rows = {SNARLING_PROTECTOR_ROW_ID, SCENT_OF_BLOOD_ROW_ID}
    if set(operations) != expected_updated_rows:
        raise ValueError("Maulerfiend current overlay row inventory drifted.")
    current = {
        source_row_id: _row_description(source_row)
        for source_row_id, source_row in source_rows.items()
    }
    expected_text = {
        SNARLING_PROTECTOR_ROW_ID: source_overlay.THOUSAND_SONS_SNARLING_PROTECTOR_DESCRIPTION,
        SCENT_OF_BLOOD_ROW_ID: source_overlay.WORLD_EATERS_SCENT_OF_BLOOD_DESCRIPTION,
    }
    for source_row_id in sorted(expected_updated_rows):
        operation = operations[source_row_id]
        if (
            operation.operation_kind is not SourceOverlayOperationKind.UPDATE_ROW
            or operation.expected_preimage_hash != source_row_hash(source_rows[source_row_id])
            or dict(operation.fields) != {"description": expected_text[source_row_id]}
        ):
            raise ValueError("Maulerfiend current overlay operation drifted.")
        current[source_row_id] = expected_text[source_row_id]
    return current


def _validated_review_row(
    review_payload: object,
    *,
    spec: _FactionSpec,
) -> dict[str, object]:
    if not isinstance(review_payload, dict):
        raise TypeError("Maulerfiend faction-pack review manifest is missing.")
    factions_value = review_payload.get("factions")
    if not isinstance(factions_value, list):
        raise TypeError("Maulerfiend faction-pack review factions are missing.")
    factions = tuple(
        cast(dict[str, object], faction)
        for faction in cast(list[object], factions_value)
        if isinstance(faction, dict) and faction.get("faction_id") == spec.faction_id
    )
    if len(factions) != 1:
        raise ValueError("Maulerfiend review faction identity drifted.")
    faction = factions[0]
    official_pdf_path = OFFICIAL_PDF_DIRECTORY / spec.official_pdf_filename
    if (
        faction.get("pdf_filename") != official_pdf_path.name
        or faction.get("pdf_sha256") != hashlib.sha256(official_pdf_path.read_bytes()).hexdigest()
    ):
        raise ValueError("Maulerfiend review PDF provenance drifted.")
    rows_value = faction.get("rows")
    if not isinstance(rows_value, list):
        raise TypeError("Maulerfiend review faction rows are invalid.")
    rows = tuple(
        cast(dict[str, object], row)
        for row in cast(list[object], rows_value)
        if isinstance(row, dict) and row.get("datasheet_id") == spec.datasheet_id
    )
    if len(rows) != 1:
        raise ValueError("Maulerfiend review-row inventory drifted.")
    row = rows[0]
    actual = {
        "datasheet_name": row.get("datasheet_name"),
        "review_row_id": row.get("review_row_id"),
        "review_treatment": row.get("treatment"),
        "pdf_page_reference": row.get("pdf_page_reference"),
    }
    expected = {
        "datasheet_name": DATASHEET_NAME,
        "review_row_id": f"source:{spec.datasheet_id}",
        "review_treatment": spec.review_treatment,
        "pdf_page_reference": spec.pdf_page_reference,
    }
    if actual != expected:
        raise ValueError("Maulerfiend review row drifted.")
    return actual


def _siege_crawler_rule_ir(text: str, spec: _FactionSpec) -> RuleIR:
    source_row_id = SIEGE_CRAWLER_ROW_ID
    return _manual_rule_ir(
        spec=spec,
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(spec, source_row_id, 1),
                template_id="phase17c:modifier-ignore-permission",
                source_span=_span(text, text),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(text, "this model"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(text, "ignore any or all modifiers"),
                        parameters=_parameters(
                            ("ability", "modifier_ignore_permission"),
                            (
                                "modifier_kinds",
                                (
                                    "movement_characteristic",
                                    "advance_roll",
                                    "charge_roll",
                                ),
                            ),
                            ("selection", "any_or_all"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.WHILE_CONDITION_TRUE,
                    source_span=_span(text, text),
                ),
            ),
        ),
    )


def _snarling_protector_rule_ir(text: str, spec: _FactionSpec) -> RuleIR:
    source_row_id = SNARLING_PROTECTOR_ROW_ID
    stratagem_trigger = RuleTrigger(
        kind=RuleTriggerKind.UNIT_SELECTED,
        source_span=_span(text, "target this unit with the Heroic Intervention Stratagem"),
        parameters=_parameters(
            ("selected_unit_allegiance", "friendly"),
            ("selection", "stratagem_target"),
            ("source_relationship", "stratagem_targets_source_unit"),
            ("stratagem_user", "source_player"),
            ("timing_window", "after_unit_selected_as_stratagem_target"),
            ("usage_scope", "source_model"),
        ),
    )
    stratagem_condition = RuleCondition(
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        source_span=_span(text, "target this unit with the Heroic Intervention Stratagem"),
        parameters=_parameters(
            ("gate_subject", "stratagem_target"),
            ("relationship", "stratagem_targets_source_unit"),
            ("selected_unit_allegiance", "friendly"),
        ),
    )
    stratagem_target = RuleTargetSpec(
        kind=RuleTargetKind.STRATAGEM_USE,
        source_span=_span(text, "That use"),
    )
    charge_text = text[text.index("When this unit declares a charge") :]
    return _manual_rule_ir(
        spec=spec,
        source_row_id=source_row_id,
        text=text,
        clauses=(
            RuleClause(
                clause_id=_clause_id(spec, source_row_id, 1),
                template_id="phase17c:stratagem-phase-use-exception",
                source_span=_span(
                    text,
                    text[: text.index("When this unit declares a charge")].rstrip(),
                ),
                trigger=stratagem_trigger,
                conditions=(stratagem_condition,),
                target=stratagem_target,
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(
                            text,
                            "does not prevent any uses of that Stratagem on other units this phase",
                        ),
                        parameters=_parameters(
                            ("ability", "stratagem_phase_use_exception"),
                            ("bypass_same_stratagem_per_phase", True),
                            ("does_not_block_other_units", True),
                            ("frequency_scope", "phase_per_unit"),
                            ("stratagem_id", "heroic-intervention"),
                        ),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(spec, source_row_id, 2),
                template_id="phase17c:stratagem-cost-modifier",
                source_span=_span(text, "That use is -1CP"),
                trigger=stratagem_trigger,
                conditions=(stratagem_condition,),
                target=stratagem_target,
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                        source_span=_span(text, "That use is -1CP"),
                        parameters=_parameters(
                            ("affected_player", "source_player"),
                            ("application_scope", "current_stratagem_use"),
                            ("delta", -1),
                            ("minimum_cost", 0),
                            ("operation", "modify_stratagem_cost"),
                            ("optional", False),
                            ("stacking", "cumulative"),
                            ("stratagem_id", "heroic-intervention"),
                        ),
                    ),
                ),
            ),
            RuleClause(
                clause_id=_clause_id(spec, source_row_id, 3),
                template_id="phase17c:friendly-engaged-anchor-charge-reroll",
                source_span=_span(text, charge_text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.UNIT_SELECTED,
                    source_span=_span(text, "When this unit declares a charge"),
                    parameters=_parameters(
                        ("selection", "charging_unit"),
                        ("source_relationship", "source_unit_declares_charge"),
                        (
                            "timing_window",
                            "after_charging_unit_selected_before_charge_roll",
                        ),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(text, "friendly engaged Psyker unit"),
                        parameters=_parameters(
                            ("exclude_source_unit", True),
                            ("gate_subject", "friendly_anchor"),
                            ("relationship", "friendly_engaged_keyword_unit"),
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.KEYWORD_GATE,
                        source_span=_span(text, "Psyker"),
                        parameters=_parameters(
                            ("gate_subject", "friendly_anchor"),
                            ("required_keyword", "PSYKER"),
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.DISTANCE_PREDICATE,
                        source_span=_span(text, 'within 12" of this unit'),
                        parameters=_parameters(
                            ("distance_inches", 12),
                            ("first_subject", "source_unit"),
                            ("negated", False),
                            ("range_kind", "numeric_range"),
                            ("second_subject", "friendly_anchor"),
                        ),
                    ),
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(
                            text,
                            "enemy unit engaged with that friendly Psyker unit",
                        ),
                        parameters=_parameters(
                            ("gate_subject", "required_enemy"),
                            (
                                "relationship",
                                "enemy_engaged_with_selected_friendly_anchor",
                            ),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_UNIT,
                    source_span=_span(
                        text,
                        "This unit",
                        start_at=text.index("When this unit declares a charge"),
                    ),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=_span(text, charge_text),
                        parameters=_parameters(
                            (
                                "ability",
                                "charge_reroll_with_friendly_engaged_keyword_anchor",
                            ),
                            ("component_selection_policy", "whole_roll"),
                            ("optional", True),
                            (
                                "required_charge_end_relationship",
                                "enemy_engaged_with_selected_anchor",
                            ),
                            ("roll_type", "charge_roll"),
                            ("selection_policy", "anchor_and_enemy_pair"),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, charge_text),
                    parameters=_parameters(("endpoint", "phase")),
                ),
            ),
        ),
    )


def _scent_of_blood_rule_ir(text: str, spec: _FactionSpec) -> RuleIR:
    source_row_id = SCENT_OF_BLOOD_ROW_ID
    return _manual_rule_ir(
        spec=spec,
        source_row_id=source_row_id,
        text=text,
        clauses=(
            _nearby_strength_charge_modifier_clause(
                spec=spec,
                source_row_id=source_row_id,
                index=1,
                text=text,
                clause_text=(
                    'If an enemy unit below Starting Strength is within 9" of this unit, '
                    "this unit has +1 to Charge rolls."
                ),
                condition_text=('an enemy unit below Starting Strength is within 9" of this unit'),
                target_constraint="target_unit_below_starting_strength",
                delta=1,
                priority=1,
            ),
            _nearby_strength_charge_modifier_clause(
                spec=spec,
                source_row_id=source_row_id,
                index=2,
                text=text,
                clause_text=(
                    'If an enemy unit Below Half-strength is within 9" of this unit, '
                    "this unit has +2 to Charge rolls."
                ),
                condition_text=('an enemy unit Below Half-strength is within 9" of this unit'),
                target_constraint="target_unit_below_half_strength",
                delta=2,
                priority=2,
            ),
        ),
    )


def _nearby_strength_charge_modifier_clause(
    *,
    spec: _FactionSpec,
    source_row_id: str,
    index: int,
    text: str,
    clause_text: str,
    condition_text: str,
    target_constraint: str,
    delta: int,
    priority: int,
) -> RuleClause:
    return RuleClause(
        clause_id=_clause_id(spec, source_row_id, index),
        template_id="phase17c:nearby-strength-charge-roll-modifier",
        source_span=_span(text, clause_text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, condition_text),
                parameters=_parameters(
                    ("distance_inches", 9.0),
                    ("gate_subject", "nearby_unit"),
                    ("relationship", "any_unit_within_distance_of_this_unit"),
                    ("target_allegiance", "enemy"),
                    ("target_constraint", target_constraint),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span(text, "this unit", start_at=text.index(clause_text)),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_DICE_ROLL,
                source_span=_span(text, f"+{delta} to Charge rolls"),
                parameters=_parameters(
                    ("delta", delta),
                    ("modifier_exclusive_group", "scent-of-blood-charge-modifier"),
                    ("modifier_priority", priority),
                    ("roll_type", "charge"),
                ),
            ),
        ),
    )


def _savage_exaltation_rule_ir(text: str, spec: _FactionSpec) -> RuleIR:
    source_row_id = SAVAGE_EXALTATION_ROW_ID
    return _manual_rule_ir(
        spec=spec,
        source_row_id=source_row_id,
        text=text,
        clauses=(
            _target_strength_melee_attack_clause(
                spec=spec,
                source_row_id=source_row_id,
                index=1,
                text=text,
                clause_text=(
                    "Each time this model makes a melee attack that targets an enemy unit that "
                    "is below its Starting Strength, add 1 to the Hit roll"
                ),
                condition_text="enemy unit that is below its Starting Strength",
                target_constraint="target_unit_below_starting_strength",
                roll_type="hit",
                effect_text="add 1 to the Hit roll",
            ),
            _target_strength_melee_attack_clause(
                spec=spec,
                source_row_id=source_row_id,
                index=2,
                text=text,
                clause_text=(
                    "if that attack targets an enemy unit that is Below Half-strength, add 1 "
                    "to the Wound roll as well"
                ),
                condition_text="enemy unit that is Below Half-strength",
                target_constraint="target_unit_below_half_strength",
                roll_type="wound",
                effect_text="add 1 to the Wound roll",
            ),
        ),
    )


def _target_strength_melee_attack_clause(
    *,
    spec: _FactionSpec,
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
        clause_id=_clause_id(spec, source_row_id, index),
        template_id="phase17c:dice-roll-modifier",
        source_span=_span(text, clause_text),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(text, "Each time this model makes a melee attack"),
            parameters=_parameters(("roll_type", roll_type)),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, condition_text),
                parameters=_parameters(
                    ("gate_subject", "attack_target"),
                    ("relationship", "this_model_makes_attack"),
                    ("target_allegiance", "enemy"),
                    ("target_constraint", target_constraint),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(text, "this model"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_DICE_ROLL,
                source_span=_span(text, effect_text),
                parameters=_parameters(
                    ("delta", 1),
                    ("roll_type", roll_type),
                    ("weapon_scope", "melee"),
                ),
            ),
        ),
    )


def _manual_rule_ir(
    *,
    spec: _FactionSpec,
    source_row_id: str,
    text: str,
    clauses: tuple[RuleClause, ...],
) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:{spec.faction_id}:maulerfiend:datasheet:{source_row_id}",
        source_id=f"{spec.source_package_id}:datasheet:{source_row_id}",
        normalized_text=text,
        parser_version=MANUAL_PARSER_VERSION,
        clauses=clauses,
    )


def _row_description(row: NormalizedSourceRow) -> str:
    description = row.runtime_fields_payload().get("description")
    if type(description) is not str or not description:
        raise ValueError("Maulerfiend source ability text is missing.")
    return description


def _clause_id(spec: _FactionSpec, source_row_id: str, index: int) -> str:
    return f"phase17k:{spec.faction_id}:maulerfiend:datasheet:{source_row_id}:clause:{index:03d}"


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
