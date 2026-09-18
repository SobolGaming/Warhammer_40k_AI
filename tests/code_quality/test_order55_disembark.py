from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.build_core_large_model_disembark_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_disembark_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_disembark_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text(encoding="utf-8") == (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        )
    assert source.source_package().source_catalog == source.source_catalog()
    (rule,) = source.source_rules()
    assert source.DISEMBARK_POLICY.source_rule_id == rule.source_id
    assert source.DISEMBARK_POLICY.requires_impossible_size_fit
    assert source.DISEMBARK_POLICY.requires_unengaged
    assert source.DISEMBARK_POLICY.uses_mode_setup_distance
    assert source.DISEMBARK_POLICY.maximum_base_distance_inches == 1
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.LargeModelDisembarkSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_all_disembark_consumers_use_the_shared_endpoint_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    shared = (engine / "transport_disembark_geometry.py").read_text()
    assert "base_fits_disembark_distance(model.base, transport.base, distance_inches)" in shared
    assert "if not oversized and enemy_unit_id in allowed_engagement_units:" in shared
    assert "DISEMBARK_POLICY.maximum_base_distance_inches" in shared
    assert "model.range_to(transport) <= DISEMBARK_POLICY.maximum_base_distance_inches" in shared
    assert "base_distance_to(" not in shared
    assert "append_disembark_endpoint_violations(" in (engine / "transports.py").read_text()
    assert "resolve_disembark_internal(" in (engine / "emergency_disembark.py").read_text()
    assert (
        "resolve_disembark_internal("
        in (engine / "phases/movement_rules_unit_disembark.py").read_text()
    )
    assert (
        "resolve_rules_unit_disembark("
        in (engine / "destroyed_transport_rules_unit_disembark.py").read_text()
    )
    fit = (ROOT / "src/warhammer40k_core/geometry/disembark_fit.py").read_text()
    assert "@lru_cache(maxsize=512)" in fit
    assert "shapely" not in fit
    assert "except" not in fit.replace("exception", "")


def test_disembark_performance_has_matched_inputs_and_passes_declared_budgets() -> None:
    directory = ROOT / "docs/performance/order55"
    base, head = (json.loads((directory / f"{name}.json").read_text()) for name in ("base", "head"))
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
        (base, [False, False, False, True]),
        (head, [True, False, False, True]),
    ):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(sample["accepted"] == expected for sample in report["samples"])
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


def test_cold_asymmetric_fit_diagnostics_pass_without_dropping_stalled_cases() -> None:
    report = json.loads((ROOT / "docs/performance/order55/geometry.json").read_text())
    assert len(report["cases"]) == 6
    assert len(report["samples"]) == 7
    assert report["earlier_quantified_prototype"]["ellipse-circle-positive"].startswith(
        "interrupted"
    )
    assert report["earlier_quantified_prototype"]["ellipse-ellipse-positive"].startswith(
        "interrupted"
    )
    assert report["full_game_certified"] is False
    for sample in report["samples"]:
        assert sample["fits"] == [True, False, False, True, True, True]
        assert sample["seconds"] < report["maximum_sample_budget_seconds"]
