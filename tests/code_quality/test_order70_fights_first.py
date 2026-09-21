"""Source, ownership and cost guards for model-complete Fights First."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_order70_source_is_pinned_reproducible_and_executable() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_fights_first_2026_09 as source,
    )

    subprocess.run(
        [sys.executable, "tools/build_core_fights_first_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert {row.section_id for row in source.source_rules()} == {"24.13", "01.02"}
    assert source.source_package().source_catalog.documents
    for row in source.source_rules():
        assert row.load_support_status == "loaded"
        assert row.semantic_execution_status == "executable_engine_runtime"


def test_order70_live_order_does_not_use_start_snapshot_as_ability_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    tree = ast.parse((engine / "fight_order.py").read_text(encoding="utf-8"))
    query = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "eligible_fight_contexts_for_player"
    )
    text = ast.unparse(query)
    assert "FightsFirstRegistry.from_state(state)" in text
    assert "fight_order_state.fights_first_registry" not in text
    for name in ("fights_first.py", "fights_first_native.py"):
        tree = ast.parse((engine / name).read_text(encoding="utf-8"))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in {"name", "upper", "lower", "casefold", "source_text"}
        ]
    effects = (engine / "rules_unit_effects.py").read_text(encoding="utf-8")
    assert "validate_native_fights_first_effects(" in effects
    # Conditional descriptors may decide applicability, never exempt a grant
    # from the common model-scope restriction.
    inventory = ast.parse((engine / "fights_first.py").read_text(encoding="utf-8"))
    assert not [
        node
        for node in ast.walk(inventory)
        if isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.NotEq) for operator in node.ops)
        and any(
            isinstance(value, ast.Name) and value.id == "CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID"
            for value in (node.left, *node.comparators)
        )
    ]


def test_order70_matched_live_query_cost() -> None:
    folder = ROOT / "docs/performance/order70"
    base = json.loads((folder / "base.json").read_bytes())
    head = json.loads((folder / "head.json").read_bytes())
    budget = json.loads((folder / "budgets.json").read_bytes())
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
    assert [row["grant_count"] for row in head["rows"]] == [0, 1, 4]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert before["source_count"] == after["source_count"] == after["grant_count"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
