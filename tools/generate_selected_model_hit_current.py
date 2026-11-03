"""Generate the reviewed current lowering successor without rewriting historical source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "selected_model_hit_current_2026_11.json"
)
PREDECESSOR = "02b5c11d47776e8a050dd004db3f1d725c8ec1828e1624017c439bc0fa1c2219"


def generated_payload() -> dict[str, object]:
    previous = faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id("000003909:5")
    if previous is None or RuleIR.from_payload(previous).ir_hash() != PREDECESSOR:
        raise ValueError("Selected model hit predecessor drifted.")
    current = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=previous["source_id"],
            raw_text=previous["normalized_text"],
            objective_scope=ObjectiveRuleScope.HISTORICAL_TEXT,
        ),
        source_keyword_sequence_parts=("AELDARI",),
    ).rule_ir
    if not current.is_supported or current.rule_id != previous["rule_id"]:
        raise ValueError("Selected model hit successor identity drifted.")
    return {
        "schema_version": "selected-model-hit-current-v1",
        "source_row_id": "000003909:5",
        "predecessor_ir_hash": PREDECESSOR,
        "rule_ir": current.to_payload(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(generated_payload(), sort_keys=True, indent=2) + "\n"
    if args.check:
        if OUTPUT.read_text() != text:
            raise ValueError("Selected model hit current successor is stale.")
    else:
        OUTPUT.write_text(text)


if __name__ == "__main__":
    main()
