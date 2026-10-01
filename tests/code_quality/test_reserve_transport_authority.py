"""Keep Order 63 on the shared placement and replay authority paths."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_loaded_transport_policies_use_shared_placement_and_replay_owners() -> None:
    assert "RESERVE_EMBARKED_CARGO_UNSUPPORTED" not in (ENGINE / "reserves.py").read_text(
        encoding="utf-8"
    )
    standard = (ENGINE / "standard_disembark_resolution.py").read_text(encoding="utf-8")
    assert "inherited_disembark_violations(" in standard
    grouped = (ENGINE / "phases/movement_rules_unit_disembark.py").read_text(encoding="utf-8")
    assert "ingress_rules_unit_placement=selection.attempted_placement" in grouped
    for name in ("phases/movement_reinforcements.py", "stratagems_ingress.py"):
        assert "inherited_restrictions_for_arrival(" in (ENGINE / name).read_text(encoding="utf-8")
    origin = ast.parse((ENGINE / "ingress_placement_history.py").read_text(encoding="utf-8"))
    calls = {
        node.func.attr
        for node in ast.walk(origin)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert {"capture", "run", "from_payload"} <= calls
    lifecycle = (ENGINE / "lifecycle.py").read_text(encoding="utf-8")
    assert lifecycle.index("_history_origins.capture(") < lifecycle.index(
        "self.decision_controller.submit_result(result)"
    )
    assert "_history_origins.validate(lifecycle)" in lifecycle


def test_order63_source_generator_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_reserve_transport_source.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


def test_failed_setup_restore_uses_independent_origin_and_shared_engine_replay() -> None:
    wiring = ast.parse((ENGINE / "lifecycle_history_origins.py").read_text(encoding="utf-8"))
    validate = next(
        node
        for node in wiring.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate"
    )
    calls = {
        node.func.attr
        for node in ast.walk(validate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "validate_failed_setup_origin" in calls
    owner = ast.parse((ENGINE / "movement_failed_setup_history.py").read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(owner) if isinstance(node, ast.Attribute)}
    assert {"from_payload", "submit_decision"} <= attributes
    assert "replace_transport_cargo_state" not in attributes
    assert "decision_controller" not in {
        target.attr
        for node in ast.walk(owner)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
    }
    names = {
        node.func.id
        for node in ast.walk(owner)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "advance_recorded_automatic_progress" in names
    assert "validate_transport_cargo_location_suffix" in names
    cargo_history = ast.parse((ENGINE / "transport_cargo_location_history.py").read_text())
    cargo_attributes = {
        node.attr for node in ast.walk(cargo_history) if isinstance(node, ast.Attribute)
    }
    assert "transport_cargo_state_for_embarked_unit" in cargo_attributes
    assert not {
        "replace_transport_cargo_state",
        "replace_reserve_state",
        "replace_battlefield_state",
        "replace_army_definition",
    }.intersection(cargo_attributes)
    families = {
        node.value
        for node in ast.walk(owner)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "disembark_placement_invalid",
        "combat_disembark_placement_invalid",
        "reinforcement_placement_invalid",
    } <= families
    authority = ast.parse((ENGINE / "movement_failed_setup_authority.py").read_text())
    calls_by_name = {
        node.func.id: node
        for node in ast.walk(authority)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "historical_model_ids_by_physical_unit" in calls_by_name
    reserve_call = calls_by_name["validate_primary_reserve_placement_request_authority"]
    assert "historical_living_model_ids_by_component" in {
        keyword.arg for keyword in reserve_call.keywords
    }


def test_order63_matched_measurement_gate() -> None:
    folder = ROOT / "docs/performance/order63"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    loaded = json.loads((folder / "loaded-head.json").read_text(encoding="utf-8"))
    for key in ("workload_id", "hashes", "platform", "python", "cpu", "memory_bytes", "budgets"):
        assert head[key] == base[key]
    for report in (base, head, loaded):
        assert len(report["samples"]) == 7
        assert all(sample["complete"] for sample in report["samples"])
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    limits = base["budgets"]
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * limits["mean_ratio"] + limits["mean_additive_seconds"]
    )
    assert (
        head["maximum_seconds"]
        <= base["maximum_seconds"] * limits["maximum_ratio"] + limits["maximum_additive_seconds"]
    )
