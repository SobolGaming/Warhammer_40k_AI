from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.build_core_surge_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_surge_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_surge_source_is_pinned_reproducible_and_execution_classified() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text() == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert (
        source.source_package().source_catalog.catalog_sha256()
        == source.source_catalog().catalog_sha256()
    )
    assert source.source_rules()[0].semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.SurgeSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_surge_does_not_regain_automatic_flight_or_runtime_name_parsing() -> None:
    for module in (
        "surge_movement.py",
        "surge_endpoints.py",
        "surge_choices.py",
        "triggered_movement_resolution.py",
    ):
        text = (ENGINE / module).read_text()
        assert ".upper()" not in text
        assert ".lower()" not in text
        assert "blood_surge" not in text
    resolver = (ENGINE / "triggered_movement_resolution.py").read_text()
    assert '"Surge cannot take to the skies."' in resolver
    assert "validate_surge_endpoints(" in resolver


def test_surge_locks_use_shared_authority_for_every_movement_family() -> None:
    for module in (
        "charge_eligibility.py",
        "fight_rules_unit_movement.py",
        "physical_proposal_context.py",
        "triggered_movement_selection.py",
        "phases/movement_validation.py",
    ):
        text = (ENGINE / module).read_text()
        assert "surge_locked" in text or "movement_lock_reason" in text
    assert (
        "validate_battlefield_movement_locks(state=self" in (ENGINE / "game_state.py").read_text()
    )


def test_surge_live_and_historical_descriptors_share_recorded_grant_validation() -> None:
    import ast

    authority = ast.parse((ENGINE / "surge_authority.py").read_text())
    functions = {node.name: node for node in authority.body if isinstance(node, ast.FunctionDef)}
    calls = {
        node.func.id
        for node in ast.walk(functions["validate_surge_selection_chain"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_validate_surge_granted_descriptor" in calls
    grant_comparisons = {
        ast.unparse(node)
        for node in ast.walk(functions["_validate_surge_granted_descriptor"])
        if isinstance(node, ast.Compare)
    }
    assert "proposal.unit_instance_id != unit.unit_instance_id" in grant_comparisons
    for module in ("surge_authority.py", "surge_history.py"):
        tree = ast.parse((ENGINE / module).read_text())
        uses = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_surge_selection_chain"
        ]
        assert uses
        assert all(any(keyword.arg == "request" for keyword in use.keywords) for use in uses)


def test_surge_performance_evidence_uses_identical_workload_and_declared_budgets() -> None:
    directory = ROOT / "docs/performance/order52"
    base, head = (
        json.loads((directory / name).read_text())
        for name in ("matched-base.json", "matched-head.json")
    )
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
    for report, accepted in ((base, [True, True]), (head, [True, False])):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(row["accepted"] == accepted for row in report["samples"])
        assert all(row["path_result_counts"] == [5, 5] for row in report["samples"])
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


@pytest.mark.parametrize("prefix", ["grant", "moving-unit"])
def test_surge_grant_validation_retains_matched_performance_evidence(prefix: str) -> None:
    directory = ROOT / "docs/performance/order52"
    base, head = (
        json.loads((directory / name).read_text())
        for name in (f"{prefix}-base.json", f"{prefix}-head.json")
    )
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
        "event_counts",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples_seconds"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]
