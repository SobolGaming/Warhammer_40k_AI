"""Offline source reproducibility and shared canonical-keyword roster authority."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_order67_source_artifacts_are_reproducible() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_mustering_limits_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_roster_duplicate_limit_uses_shared_catalog_keyword_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    module = ast.parse((engine / "army_mustering.py").read_text(encoding="utf-8"))
    owner = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_append_unit_limit_violations"
    )
    calls = [node.func for node in ast.walk(owner) if isinstance(node, ast.Call)]
    assert (
        sum(isinstance(call, ast.Name) and call.id == "datasheet_unit_limit" for call in calls) == 1
    )
    predicate = ast.parse((engine / "roster_unit_limits.py").read_text(encoding="utf-8"))
    assert not [node for node in ast.walk(predicate) if isinstance(node, ast.Call)]
    tokens = {node.value for node in ast.walk(predicate) if isinstance(node, ast.Constant)}
    assert {"BATTLELINE", "DEDICATED TRANSPORT"} <= tokens


def test_order67_matched_roster_validation_cost() -> None:
    folder = ROOT / "docs/performance/order67"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    budget = json.loads((folder / "budgets.json").read_text(encoding="utf-8"))
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "hashes",
        "timing_boundary",
    ):
        assert base[key] == head[key], key
    assert head["workload"] == budget["workload"]
    assert [row["unit_count"] for row in head["rows"]] == [2, 4, 20]
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["unit_count"] == after["unit_count"]
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
