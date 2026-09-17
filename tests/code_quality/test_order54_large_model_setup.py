from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.build_core_large_model_setup_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_setup_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_oversized_setup_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text() == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert source.source_package().source_catalog == source.source_catalog()
    (rule,) = source.source_rules()
    assert source.SETUP_POLICY.source_rule_id == rule.source_id
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.LargeModelSetupSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_oversized_setup_consumers_share_geometry_and_activity_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in ("deployment_geometry.py", "prebattle_setup_geometry.py"):
        assert "oversized_deployment_violation(" in (engine / name).read_text()
    for name in (
        "shooting_eligibility_state.py",
        "charge_eligibility.py",
        "phases/movement_options_dice.py",
        "phases/movement_resolvers.py",
        "triggered_movement_handler_impl.py",
        "triggered_movement_selection.py",
        "setup_turn_prevalidation.py",
    ):
        assert "large_model_activity_reason(" in (engine / name).read_text()
    assert "base_fits_edge_band(" in (engine / "reserve_setup_geometry.py").read_text()
    assert "_model_can_fit_within_edge_band" not in (engine / "reserves.py").read_text()
    assert (
        "validate_arrival_restriction_evidence("
        in (engine / "primary_reserve_arrival_integrity.py").read_text()
    )


def test_oversized_setup_performance_evidence_has_matched_inputs() -> None:
    directory = ROOT / "docs/performance/order54"
    base, head = (json.loads((directory / name).read_text()) for name in ("base.json", "head.json"))
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "timing_boundary",
        "scenario",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report, expected in (
        (base, [False, False, True, False]),
        (head, [True, False, True, False]),
    ):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(row["accepted"] == expected for row in report["samples"])
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]
