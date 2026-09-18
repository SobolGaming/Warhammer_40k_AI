from __future__ import annotations

import json
from math import isclose
from pathlib import Path

import pytest
from tools.build_core_measuring_to_destroyed_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_measuring_to_destroyed_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_measuring_to_destroyed_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text(encoding="utf-8") == (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        )
    assert (
        source.source_package().source_catalog.catalog_sha256()
        == source.source_catalog().catalog_sha256()
    )
    (rule,) = source.source_rules()
    assert source.MEASUREMENT_POLICY.source_rule_id == rule.source_id
    assert source.MEASUREMENT_POLICY.uses_former_footprint is True
    assert source.MEASUREMENT_POLICY.destroyed_unit_resolves_to_last_destroyed_model is True
    assert source.MEASUREMENT_POLICY.grants_living_battlefield_authority is False
    assert source.MEASUREMENT_POLICY.uses_catalog_geometry_for_base_or_hull is True
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert (
        "destroyed_referent_measurement:former_footprint_for_destroyed_model"
        in (rule.runtime_consumer_ids[0])
    )
    with pytest.raises(source.MeasuringToDestroyedSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_destroyed_referent_query_is_the_shared_authority() -> None:
    query = (ENGINE / "destroyed_referent_measurement.py").read_text(encoding="utf-8")
    assert "MEASUREMENT_POLICY" in query
    assert "geometry_model_for_placement" in query
    assert "destroyed_model_placement" in query
    assert "cause_id" in query
    assert "boundary_id" in query
    assert "seen_model_ids" not in query
    assert "Vehicle" not in query
    assert "Walker" not in query
    assert "WALKER" not in query
    assert ".upper()" not in query
    assert "except Exception" not in query
    deadly = (ENGINE / "deadly_demise.py").read_text(encoding="utf-8")
    assert "former_geometry_for_destroyed_or_placed_model(" in deadly
    assert "event_records=event_records" in deadly
    attack = (ENGINE / "attack_sequence_damage_resolution.py").read_text(encoding="utf-8")
    assert "event_records=decisions.event_log.records" in attack
    rule = (ENGINE / "rule_model_destruction.py").read_text(encoding="utf-8")
    assert "event_records=decisions.event_log.records" in rule


def test_order57_performance_has_matched_inputs_and_passes_declared_budgets() -> None:
    directory = ROOT / "docs/performance/order57"
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
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    assert base["scenario"]["query_count"] == head["scenario"]["query_count"]
    assert base["scenario"]["destroyed_query_available"] is False
    assert head["scenario"]["destroyed_query_available"] is True
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        ordinary = report["samples"][0]["ordinary_distance"]
        target_count = report["samples"][0]["deadly_demise_target_count"]
        assert ordinary > 0
        assert target_count >= 1
        assert all(sample["ordinary_distance"] == ordinary for sample in report["samples"])
        assert all(
            sample["deadly_demise_target_count"] == target_count for sample in report["samples"]
        )
        assert all(sample["complete"] is True for sample in report["samples"])
    head_destroyed = [sample["destroyed_distance"] for sample in head["samples"]]
    ordinary = head["samples"][0]["ordinary_distance"]
    assert all(isclose(distance, ordinary, abs_tol=1e-9) for distance in head_destroyed)
    assert all(sample["destroyed_seconds"] is None for sample in base["samples"])
    assert all(sample["destroyed_seconds"] is not None for sample in head["samples"])
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]
