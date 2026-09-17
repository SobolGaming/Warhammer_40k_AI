from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.build_core_super_heavy_walker_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_super_heavy_walker_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_movement_source_is_pinned_reproducible_and_source_linked() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text() == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert source.source_package().source_catalog == source.source_catalog()
    (descriptor,) = source.movement_abilities()
    (rule,) = source.source_rules()
    assert descriptor.source_rule_id == rule.source_id
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.MovementAbilitySourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_move_keyword_paths_share_authority_and_direct_status_owner() -> None:
    for module in (
        "move_ability_choices.py",
        "move_keyword_authority.py",
        "move_keyword_completion.py",
    ):
        text = (ENGINE / module).read_text()
        assert ".upper()" not in text
        assert ".lower()" not in text
        assert '== "Super-Heavy Walker"' not in text
    completion = (ENGINE / "move_keyword_completion.py").read_text()
    assert "apply_direct_battle_shock_state(" in completion
    assert "BattleShockTestRequest(" not in completion
    assert "MoveCompletionRuleBinding(" in completion
    assert "validate_move_keyword_history(" in completion
    assert "validate_restored_movement(" in (ENGINE / "lifecycle.py").read_text()
    resolution = (ENGINE / "triggered_movement_resolution.py").read_text()
    assert "choice_descriptor(move_keyword_choice) not in descriptors_for_move(" in resolution
    assert "ability_keywords, descriptor.movement_mode.value, is_surge=is_surge" in resolution


def test_movement_component_evidence_has_matched_inputs_and_unchanged_budgets() -> None:
    directory = ROOT / "docs/performance/order53"
    base, head = (json.loads((directory / name).read_text()) for name in ("base.json", "head.json"))
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "mode",
        "concurrency",
        "timing_boundary",
        "scenario",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report, accepted in ((base, False), (head, True)):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(row["accepted"] == [accepted] * 4 for row in report["samples"])
        assert all(row["path_result_counts"] == [5] * 4 for row in report["samples"])
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]
