"""Reviewed current 40k.app Sorcerer rules, compiled into existing generic owners."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from tools.faction_rule_ir_bundle import generate_registered_rule_ir_shard
else:
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data/source_audits/sorcerer_2026_11/source-observation-current.json"
SOURCE_SHA256 = "7045ea750defe53c819b69828490a9fa644ed8520c335a49fd574c6986e61a8b"
ARTIFACT_SCHEMA = "core-v2-emperors-children-sorcerer-rule-ir-v1"
SOURCE_PACKAGE_ID = "40k-app-11e-emperors-children-sorcerer-2026-11-01"
WARPED_TEXT = (
    "While this model is leading a unit, each time a ranged attack targets that unit, "
    "models in it have the Benefit of Cover against that attack."
)
WRACKING_TEXT = (
    "In your Shooting phase, after this model has shot, select one INFANTRY unit hit by "
    "one or more of those attacks made with its Agonising Energies. Until the start of "
    "your next turn, that unit is wracked with agonies. While a unit is wracked with "
    'agonies, subtract 2" from its Move characteristic and subtract 2 from Charge rolls '
    "made for it."
)


def generated_artifact_payload() -> dict[str, object]:
    raw = SOURCE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Sorcerer source capture drifted.")
    source = json.loads(raw)
    for text in (WARPED_TEXT, WRACKING_TEXT):
        if text not in source["unit"]["captured_text"]:
            raise ValueError("Sorcerer complete current ability text drifted.")
    records: dict[str, object] = {}
    for row_id, name, rule in (
        ("000004085:3", "Warped Interference (Psychic)", _warped_interference()),
        ("000004085:4", "Wracking Agonies (Psychic)", _wracking_agonies()),
    ):
        records[row_id] = {
            "ability_name": name,
            "normalized_text_sha256": hashlib.sha256(rule.normalized_text.encode()).hexdigest(),
            "rule_ir": rule.to_payload(),
        }
    payload: dict[str, object] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_snapshot_filename": SOURCE_PATH.name,
        "source_snapshot_sha256": SOURCE_SHA256,
        "source_artifact_hash": SOURCE_SHA256,
        "datasheet_id": "000004085",
        "datasheet_name": "Sorcerer",
        "records": records,
        "package_hash": "",
    }
    payload["package_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _warped_interference() -> RuleIR:
    text = WARPED_TEXT
    leading = "While this model is leading a unit"
    clause = RuleClause(
        clause_id="sorcerer:000004085:3:clause:001",
        template_id="catalog-ir:conditional-leading-ranged-cover",
        source_span=_span(text, text),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span(text, leading),
                parameters=_parameters(("relationship", "this_model_leading_unit")),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span(text, "that unit")),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span(
                    text, "models in it have the Benefit of Cover against that attack"
                ),
                parameters=_parameters(
                    ("attack_kind", "ranged"),
                    ("operation", "grant"),
                    ("status", "benefit_of_cover"),
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE, source_span=_span(text, leading)
        ),
    )
    return _rule("000004085:3", text, (clause,))


def _wracking_agonies() -> RuleIR:
    text = WRACKING_TEXT
    clauses = [
        RuleClause(
            clause_id="sorcerer:000004085:4:clause:001",
            template_id="phase17c:selected-target-constraint",
            source_span=_span(text, text.split(". Until")[0]),
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
                    (
                        "weapon_names",
                        (
                            "Agonising Energies - witchfire",
                            "Agonising Energies - focused witchfire",
                        ),
                    ),
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.ENEMY_UNIT,
                source_span=_span(text, "one INFANTRY unit"),
                parameters=_parameters(
                    ("allegiance", "enemy"),
                    ("required_keyword", "INFANTRY"),
                    ("target_relationship", "hit_by_those_attacks"),
                ),
            ),
        )
    ]
    for index, template, fragment, kind, parameters in (
        (
            2,
            "phase17c:selected-unit-characteristic-modifier",
            'subtract 2" from its Move characteristic',
            RuleEffectKind.MODIFY_CHARACTERISTIC,
            _parameters(("characteristic", Characteristic.MOVEMENT.value), ("delta", -2)),
        ),
        (
            3,
            "phase17c:selected-unit-dice-roll-modifier",
            "subtract 2 from Charge rolls made for it",
            RuleEffectKind.MODIFY_DICE_ROLL,
            _parameters(("delta", -2), ("roll_type", "charge")),
        ),
    ):
        clauses.append(
            RuleClause(
                clause_id=f"sorcerer:000004085:4:clause:{index:03d}",
                template_id=template,
                source_span=_span(text, fragment),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT, source_span=_span(text, "that unit")
                ),
                effects=(
                    RuleEffectSpec(
                        kind=kind, source_span=_span(text, fragment), parameters=parameters
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=_span(text, "Until the start of your next turn"),
                    parameters=_parameters(
                        ("battle_round_offset", 1),
                        ("boundary", "start"),
                        ("endpoint", "turn"),
                        ("owner", "source_player"),
                    ),
                ),
            )
        )
    return _rule("000004085:4", text, tuple(clauses))


def _rule(row: str, text: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"sorcerer:datasheet:{row}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{row}",
        normalized_text=text,
        parser_version="manual-source-backed-rule-ir:v1",
        clauses=clauses,
    )


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))


if __name__ == "__main__":
    generate_registered_rule_ir_shard(shard_id="emperors-children")
