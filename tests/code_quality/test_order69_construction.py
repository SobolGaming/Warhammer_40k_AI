"""Core construction ownership, empty content records and matched cost evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_order69_source_is_reproducible_and_loadable() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_roster_construction_2026_09 as source,
    )

    subprocess.run(
        [sys.executable, "tools/build_core_roster_construction_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert len(source.source_rules()) == 4
    assert source.source_package().source_catalog.documents


def test_order69_evaluator_is_content_neutral_and_does_not_parse_keywords() -> None:
    path = ROOT / "src/warhammer40k_core/engine/roster_construction_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"name", "upper", "lower", "casefold", "source_text"}
    ]
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(module is not None and "faction_content" in module for module in imports)


def test_order69_published_catalogs_have_no_faction_constraint_records() -> None:
    folder = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    for name in ("chaos_daemons_roster_2026_07", "court_of_slaughter_anvanth_2026_08"):
        artifact = json.loads(
            (folder / name / "artifacts/catalog.json").read_text(encoding="utf-8")
        )
        assert artifact["schema_version"] == "canonical-catalog-v2-construction"
        for row in artifact["army_catalog"]["detachments"]:
            assert row["construction_constraints"] == []
            assert row["canonical_detachment_id"] == row["detachment_id"]


def test_order69_attachment_report_and_mustering_share_formation_authority() -> None:
    folder = ROOT / "src/warhammer40k_core/engine"
    source = (folder / "army_mustering.py").read_text(encoding="utf-8")
    assert "def _resolve_attached_unit_formations" not in source
    assert "resolve_attached_unit_formations(" in source
    tree = ast.parse((folder / "roster_attachment_validation.py").read_text(encoding="utf-8"))
    report = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "append_attachment_violations"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_attached_unit_formations"
        for node in ast.walk(report)
    )


def test_order69_matched_roster_validation_cost() -> None:
    folder = ROOT / "docs/performance/order69"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    budget = json.loads((folder / "budgets.json").read_text(encoding="utf-8"))
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
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
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    assert [row["unit_count"] for row in head["rows"]] == [2, 4, 20]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
