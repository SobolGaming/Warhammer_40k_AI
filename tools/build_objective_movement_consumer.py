"""Reproduce the one retained consumer without modifying source archives or load-only rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = (
    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
    "stratagem:leagues-of-votann:hearthfyre-arsenal:000010452007"
)
PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "core_objective_movement_consumer_2026_10.json"
)


def build() -> dict[str, object]:
    selected = json.loads((ROOT / "data/source_audits/order97/selected-sources.json").read_bytes())
    core = next(row for row in selected if row["row_id"] == "rule:01:01.04.03:1")
    assert (
        core["source_sha256"] == "0d9cbb45d59f4f90f0c0c34a2dedc6dbaf360ea7c9e602c21dc5807499706771"
    )
    native = json.loads(
        (
            ROOT
            / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
            / "faction_stratagem_activation_2026_27.json"
        ).read_bytes()
    )
    profiles = native["profiles"]
    profile = next(row for row in profiles if row["source_id"] == SOURCE_ID)
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=SOURCE_ID,
            raw_text=profile["effect_descriptor"],
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=("IRONKIN STEELJACKS",),
    )
    assert rule.rule_ir.is_supported
    return {
        "schema_version": "core-objective-movement-consumer-v1",
        "selected_core": core,
        "consumer_profile": profile,
        "consumer_profile_sha256": hashlib.sha256(
            json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "rule_ir": rule.rule_ir.to_payload(),
        "required_name_keyword": "IRONKIN STEELJACKS",
        "requires_opponent_turn": True,
        "target_forbidden_if_within_engagement_range": True,
        "requires_objective_marker": True,
        "scope": (
            "One applicable consumer for 01.04.03-obligation-06; "
            "other faction rules remain unchanged."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), ensure_ascii=False, indent=2) + "\n").encode()
    if args.check:
        assert PATH.read_bytes() == raw, "Objective movement source artifact drift."
    else:
        PATH.write_bytes(raw)


if __name__ == "__main__":
    main()
