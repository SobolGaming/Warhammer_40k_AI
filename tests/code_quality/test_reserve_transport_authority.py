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
