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
OUTPUT_PATH = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "aeldari_corsair_skyreavers_2026_06"
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

ARTIFACT_SCHEMA = "core-v2-corsair-skyreavers-datasheet-rule-ir-v1"
SOURCE_PACKAGE_ID = "gw-11e-aeldari-corsair-skyreavers-datasheet-2026-06-09"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"
DATASHEET_ID = "000004196"
DATASHEET_NAME = "Corsair Skyreavers"
RAID_AND_RUN_ROW_ID = "000004196:4"

RAID_AND_RUN_TEXT = (
    "At the end of the Fight phase, if this unit was eligible to fight this phase, and is not "
    "within Engagement Range of one or more enemy units, it can make a Normal move of up to "
    'D3+3". Otherwise, if this unit was eligible to fight this phase, this unit can make a '
    'Fall Back move of up to D3+3".'
)


def main() -> None:
    payload = generated_artifact_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_artifact_payload() -> dict[str, object]:
    rule_ir = _raid_and_run_rule_ir()
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_pdf_filename": PDF_PATH.name,
        "source_pdf_sha256": hashlib.sha256(PDF_PATH.read_bytes()).hexdigest(),
        "source_page_numbers": [20, 21],
        "datasheet_id": DATASHEET_ID,
        "datasheet_name": DATASHEET_NAME,
        "records": {
            RAID_AND_RUN_ROW_ID: {
                "ability_name": "Raid and Run",
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


def _raid_and_run_rule_ir() -> RuleIR:
    text = RAID_AND_RUN_TEXT
    return RuleIR(
        rule_id=f"phase17k:aeldari:corsair-skyreavers:datasheet:{RAID_AND_RUN_ROW_ID}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{RAID_AND_RUN_ROW_ID}",
        normalized_text=text,
        parser_version=PARSER_VERSION,
        clauses=(
            RuleClause(
                clause_id=(f"phase17k:aeldari:corsair-skyreavers:{RAID_AND_RUN_ROW_ID}:clause:001"),
                template_id="phase17c:fight-end-conditional-triggered-movement",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "At the end of the Fight phase"),
                    parameters=_parameters(
                        ("edge", "end"),
                        ("owner", "either_player"),
                        ("phase", "fight"),
                        ("subject", "this_unit"),
                        ("timing_window", "end_fight_phase"),
                    ),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(text, "this unit was eligible to fight this phase"),
                        parameters=_parameters(
                            ("gate_subject", "this_unit"),
                            ("relationship", "eligible_to_fight_this_phase"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_UNIT,
                    source_span=_span(text, "this unit"),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.OUT_OF_PHASE_ACTION,
                        source_span=_span(text, 'make a Normal move of up to D3+3"'),
                        parameters=_movement_parameters(
                            movement_mode="normal",
                            engagement_state="not_within",
                        ),
                    ),
                    RuleEffectSpec(
                        kind=RuleEffectKind.OUT_OF_PHASE_ACTION,
                        source_span=_span(text, 'make a Fall Back move of up to D3+3"'),
                        parameters=_movement_parameters(
                            movement_mode="fall_back",
                            engagement_state="within",
                        ),
                    ),
                ),
            ),
        ),
    )


def _movement_parameters(*, movement_mode: str, engagement_state: str) -> tuple[RuleParameter, ...]:
    return _parameters(
        ("action", "move"),
        ("action_group", "fight_end_conditional_move"),
        ("distance_bonus", 3),
        ("distance_dice_quantity", 1),
        ("distance_dice_sides", 3),
        ("engagement_state", engagement_state),
        ("movement_kind", "triggered"),
        ("movement_mode", movement_mode),
        ("optional", True),
    )


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
