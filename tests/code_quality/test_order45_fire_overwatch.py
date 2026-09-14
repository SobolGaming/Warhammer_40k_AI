"""Order 45 target authority and measured phase-end cost gates."""

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_snap_range_requires_rules_unit_scope_at_every_consumer() -> None:
    phases = ROOT / "src/warhammer40k_core/engine/phases"
    for filename in (
        "shooting_eligibility.py",
        "shooting_requests.py",
        "shooting_declaration_validation.py",
    ):
        calls = [
            node
            for node in ast.walk(ast.parse((phases / filename).read_text()))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_snap_shooting_type_allowed_for_unit_target"
        ]
        assert len(calls) == 1
        arguments = {keyword.arg: ast.unparse(keyword.value) for keyword in calls[0].keywords}
        assert arguments["rules_unit"] == "rules_unit"
        assert "unit" not in arguments
    targeting = ast.parse((phases / "shooting_targeting.py").read_text())
    functions = {node.name: node for node in targeting.body if isinstance(node, ast.FunctionDef)}
    for name in ("_snap_shooting_type_allowed_for_unit_target", "_unit_target_within_max_range"):
        parameters = {
            argument.arg: argument.annotation for argument in functions[name].args.kwonlyargs
        }
        assert "unit" not in parameters
        annotation = parameters["rules_unit"]
        assert annotation is not None
        assert ast.unparse(annotation) == "RulesUnitView"
    query = ast.unparse(functions["_unit_target_within_max_range"])
    assert "rules_unit.components" in query
    assert "scenario.model_is_present_on_battlefield" in query


def test_overwatch_uses_phase_end_scope_and_shared_snap_target_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    sequencing = (engine / "core_movement_end_sequencing.py").read_text()
    assert "fire-overwatch-end-movement-round-" in sequencing
    assert "moved_unit_instance_id" not in sequencing
    assert "_active_player_end_movement_overwatch_trigger_unit_ids" not in sequencing
    assert "require_legal_affordable_target=True" not in sequencing
    assert "fire_overwatch_has_potential_shooter(" in sequencing
    for relative in (
        "stratagems_targeting.py",
        "phases/shooting_declaration_validation.py",
    ):
        text = (engine / relative).read_text()
        assert "fire_overwatch_target_unit_ids(" in text
        assert "_fire_overwatch_triggering_enemy_unit_id" not in text
    handler = (engine / "stratagems_fire_overwatch.py").read_text()
    assert "request_out_of_phase_shooting_declaration(" in handler
    assert "triggering_enemy_unit_instance_id" not in handler
    assert "target_unit_ids=" not in handler
    for relative in (
        "phases/shooting_eligibility.py",
        "phases/shooting_requests.py",
        "phases/shooting_declaration_validation.py",
    ):
        assert "_snap_shooting_type_allowed_for_unit_target(" in (engine / relative).read_text()
    scope = (engine / "fire_overwatch.py").read_text()
    assert "for component in unit.components" in scope
    assert "for model in component.unit.own_models" in scope
    assert "model_is_present_on_battlefield(" in scope
    assert "rules_unit_persisting_effects(" in scope
    assert (
        "fire_overwatch_shooter_ineligibility_reason("
        in (engine / "stratagems_targeting.py").read_text()
    )
    validation = (engine / "phases/shooting_declaration_validation.py").read_text()
    assert validation.index('violation_code="out_of_phase_target_unit_drift"') < validation.index(
        "hidden_target_model_ids = _hidden_target_model_ids("
    )


@pytest.mark.parametrize("prefix", ["", "r45-001-"])
def test_overwatch_phase_end_cost_is_comparable_complete_and_bounded(prefix: str) -> None:
    directory = ROOT / "docs/performance/order45"
    base = json.loads((directory / f"{prefix}base.json").read_text())
    head = json.loads((directory / f"{prefix}head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    expected_workload = "r45-001-attached-overwatch-v1" if prefix else budget["workload_id"]
    assert base["workload_id"] == head["workload_id"] == expected_workload
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
        assert base[field] == head[field]
    for report in (base, head):
        assert len(report["samples"]) == budget["samples"]
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * budget["mean_base_multiplier"] + budget["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_seconds"]
    assert all(row["decision_count"] <= budget["maximum_decisions"] for row in head["samples"])
    assert all(row["event_count"] <= budget["maximum_events"] for row in head["samples"])


def test_overwatch_discovery_retains_exact_ruin_and_reserve_boundary_evidence() -> None:
    directory = ROOT / "docs/performance/order45"
    report = json.loads((directory / "ruin_scenarios.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert report["base"]["test_file_sha256"] == report["head"]["test_file_sha256"]
    assert report["samples_per_case"] == 1
    assert report["full_game_certified"] is False
    base = {row["name"]: row for row in report["base"]["cases"]}
    head = {row["name"]: row for row in report["head"]["cases"]}
    assert base.keys() == head.keys()
    assert len(head) == 2
    for name, row in head.items():
        assert row["status"] == base[name]["status"] == "passed"
        assert row["seconds"] <= (
            base[name]["seconds"] * budget["ruin_case_mean_base_multiplier"]
            + budget["ruin_case_additive_seconds"]
        )
        assert row["seconds"] <= budget["ruin_case_maximum_seconds"]


def test_overwatch_discovery_preserves_existing_rapid_ingress_budgets() -> None:
    directory = ROOT / "docs/performance/order45"
    base = json.loads((directory / "rapid-ingress-base.json").read_text())
    head = json.loads((directory / "rapid-ingress-head.json").read_text())
    budget = json.loads((ROOT / "docs/performance/order35/budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for key in ("platform", "python", "cpu", "memory_bytes", "mode", "hashes", "decision_policy"):
        assert base[key] == head[key]
    assert base["summaries"].keys() == head["summaries"].keys() == budget["work_limits"].keys()
    for case, row in head["summaries"].items():
        assert row["samples"] == base["summaries"][case]["samples"] == 7
        assert row["completion_rate"] == base["summaries"][case]["completion_rate"] == 1
        assert row["mean"] <= (
            base["summaries"][case]["mean"] * budget["reference_mean_ratio"]
            + budget["reference_mean_allowance_seconds"]
        )
        assert row["max"] <= budget["max_seconds"][case]
