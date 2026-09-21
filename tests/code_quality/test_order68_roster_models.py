"""Order 68 source reproducibility and explicit model-selection authority."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_order68_reviewed_sources_are_reproducible() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_roster_models_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_order68_shared_bearer_has_no_first_model_inference() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for filename in (
        "enhancement_bearers.py",
        "generic_enhancement_effects.py",
        "generic_rule_selected_to_fight_effects.py",
    ):
        tree = ast.parse((engine / filename).read_text(encoding="utf-8"))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "own_models"
        ]
    assert "grant_unit_keywords" not in (engine / "roster_bearer_validation.py").read_text(
        encoding="utf-8"
    )


def test_order68_model_fields_are_required() -> None:
    from warhammer40k_core.engine.army_mustering import EnhancementAssignment, WarlordSelection
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_roster_models_2026_09 as source,
    )

    assert len(source.source_rules()) == 2
    assert source.source_package().source_catalog.documents
    for cls in (EnhancementAssignment, WarlordSelection):
        fields = cls.__dataclass_fields__
        import dataclasses

        for key in ("model_profile_id", "model_index"):
            assert fields[key].default is dataclasses.MISSING


def test_order68_corsair_bearer_eligibility_cannot_use_datasheet_keywords() -> None:
    path = ROOT / "src/warhammer40k_core/engine/roster_bearer_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_append_corsair_coterie_enhancement_target_violations"
    )
    assert "model" in {arg.arg for arg in helper.args.kwonlyargs}
    assert not [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Name) and node.id in {"datasheet", "datasheet_has_keyword"}
    ]


def test_order68_matched_roster_validation_cost() -> None:
    folder = ROOT / "docs/performance/order68"
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
