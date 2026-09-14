"""Keep every Charge consumer on canonical models and the shared path authority."""

import ast
import json
from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_charge_2026_09 import (
    CHARGE_ENDPOINT_SOURCE_ID,
    source_evidence_records,
    source_rules,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def _calls(filename: str) -> set[str]:
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(ast.parse((ENGINE / filename).read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }


def test_charge_move_consumers_share_canonical_physical_mutation_and_stale_path_checks() -> None:
    for filename in (
        "phases/charge_proposal_flow.py",
        "catalog_setup_reactive_charge_move.py",
        "stratagems_apply.py",
    ):
        assert {
            "resolve_charge_move",
            "charge_movement_placement",
            "battlefield_with_charge_placement",
        } <= _calls(filename), filename
    for filename in (
        "phases/charge.py",
        "catalog_setup_reactive_charge_move.py",
        "stratagems_apply.py",
    ):
        assert "validate_charge_witness_for_proposal" in _calls(filename), filename
    for path in (*ENGINE.glob("charge*.py"), *ENGINE.joinpath("phases").glob("charge*.py")):
        names = {
            node.name
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.FunctionDef)
        }
        assert (
            not {
                "_charge_ended_closer_to_any_selected_target",
                "_charge_preferred_distance_possible",
            }
            & names
        )
    assert "movement_reachability" in _calls("charge_model_endpoints.py")
    assert "physical_model_authority_before_event" in _calls("charge_endpoint_history.py")
    assert "validate_charge_endpoint_history" in _calls("charge_target_authority.py")


def test_order47_endpoint_execution_has_reviewed_source_and_distinct_load_status() -> None:
    rule = next(row for row in source_rules() if row.source_id == CHARGE_ENDPOINT_SOURCE_ID)
    assert rule.section_id == "11.04"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert rule.runtime_consumer_ids == (
        "warhammer40k_core.engine.charge_move_resolution:resolve_charge_move",
        "warhammer40k_core.engine.charge_model_endpoints:charge_model_endpoint_witness",
    )
    evidence = tuple(
        row for row in source_evidence_records() if row.rule_source_id == rule.source_id
    )
    assert len(evidence) == 2
    mirror = next(row for row in evidence if row.provider_name == "40k.app")
    assert mirror.source_url == "https://www.40k.app/rules/11-charge-phase"
    assert mirror.observed_at == "2026-09-14T14:09:27.140Z"
    assert mirror.provider_non_affiliation_recorded


def test_order47_matched_charge_slice_meets_its_versioned_budget() -> None:
    directory = ROOT / "docs/performance/order47"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "mode",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
        "scenario",
        "hashes",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * budget["mean_regression_factor"]
        + budget["mean_regression_allowance_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_seconds"]
    assert all(row["decision_count"] <= budget["maximum_decisions"] for row in head["samples"])
    assert all(row["event_count"] <= budget["maximum_events"] for row in head["samples"])
