"""Order 42 shared authority, source reproducibility and retained timing gates."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_target_replacement_component_cost_is_comparable_complete_and_bounded() -> None:
    directory = ROOT / "docs/performance/order42"
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
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
    ):
        assert base[field] == head[field]
    for path, digest in base["file_hashes"].items():
        if path != "src/warhammer40k_core/_engine_build_manifest.json":
            assert head["file_hashes"][path] == digest
    assert (
        set(base["summaries"])
        == set(head["summaries"])
        == {"eligible", "moved_target", "no_alternative"}
    )
    for case, measured in head["summaries"].items():
        assert measured["completion_rate"] == 1
        assert measured["samples"] == budget["samples_per_case"]
        assert (
            measured["mean"]
            <= base["summaries"][case]["mean"] * budget["mean_base_multiplier"]
            + budget["mean_additive_seconds"]
        )
        assert measured["max"] <= budget["maximum_seconds"]
    assert {
        (row["decision_type"], row["option_count"])
        for row in head["rows"]
        if row["case"] == "moved_target"
    } == {("select_target_replacement", 2)}
    assert {
        (row["decision_type"], row["option_count"])
        for row in head["rows"]
        if row["case"] == "no_alternative"
    } == {("select_target_replacement", 1)}
    assert {row["decision_type"] for row in head["rows"] if row["case"] == "eligible"} == {
        row["decision_type"] for row in base["rows"] if row["case"] == "eligible"
    }


def test_target_replacement_service_has_no_action_or_hit_resolution_dependencies() -> None:
    source = (ROOT / "src/warhammer40k_core/engine/target_replacement.py").read_text()
    tree = ast.parse(source)
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(
        module
        and any(token in module for token in ("shooting", "charge", "attack_sequence", "geometry"))
        for module in modules
    )
    for filename in ("shooting_target_replacement.py", "target_replacement_dispatch.py"):
        text = (ROOT / "src/warhammer40k_core/engine" / filename).read_text()
        assert "replacement_" in text
        assert "roll_random_characteristic(" not in text
        assert "_roll_hit(" not in text
    redaction = (ROOT / "src/warhammer40k_core/adapters/redaction.py").read_text()
    assert "target_replacement_authority_sha256" in redaction


def test_target_replacement_source_generator_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_target_replacement_source.py"), "--check"],
        check=True,
        cwd=ROOT,
    )
