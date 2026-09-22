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
    ):
        assert {
            "resolve_charge_move",
            "charge_movement_placement",
            "battlefield_with_charge_placement",
        } <= _calls(filename), filename
    for filename in (
        "phases/charge.py",
        "catalog_setup_reactive_charge_move.py",
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


def test_order74_terrain_exclusion_has_one_shared_proof_owner() -> None:
    for consumer in (
        "charge_model_endpoints.py",
        "consolidation_model_constraints.py",
        "surge_movement.py",
    ):
        assert "movement_reachability" in _calls(consumer)
        assert "decide" not in _calls(consumer)
    for history in ("charge_endpoint_history.py", "surge_history.py"):
        assert "endpoint_excluded_by_terrain" in _calls(history)
    geometry = ROOT / "src/warhammer40k_core/geometry/movement_reachability.py"
    tree = ast.parse(geometry.read_text())
    resolver = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_cached_reachability"
    )
    assert isinstance(resolver.body[-1], ast.Return)
    assert "UNRESOLVED" in ast.unparse(resolver.body[-1])
    assert "endpoint_excluded_by_terrain" in ast.unparse(resolver)


def test_order74_matched_facade_performance_retains_the_base_rejection() -> None:
    import hashlib

    from warhammer40k_core.build_identity import verified_engine_build_identity

    directory = ROOT / "docs/performance/order74"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "concurrency",
        "timing_boundary",
        "hashes",
        "budget",
    ):
        assert base[key] == head[key], key
    assert head["revision"] == verified_engine_build_identity().build_id
    assert len(base["samples"]) == len(head["samples"]) == 3
    assert all(not sample["valid"] for sample in base["samples"])
    assert all(sample["valid"] for sample in head["samples"])
    assert head["maximum_seconds"] <= head["budget"]["maximum_head_seconds"]
    assert not head["full_game_certified"]
    for path, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )


def test_historical_charge_movement_capabilities_use_the_event_bound_component() -> None:
    tree = ast.parse((ENGINE / "charge_endpoint_history.py").read_text())
    constructors = {
        ("AircraftMovementPolicy", "from_unit"),
        ("MovementCapabilitySet", "from_keywords"),
    }
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            continue
        constructor = (node.func.value.id, node.func.attr)
        if constructor not in constructors:
            continue
        found.add(constructor)
        unit = next(keyword.value for keyword in node.keywords if keyword.arg == "unit")
        assert isinstance(unit, ast.Name)
        assert unit.id == "unit_at_charge"
    assert found == constructors
    assert "charge_component_at_physical_boundary" in _calls("charge_endpoint_history.py")


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
