"""Lethal Hits must keep one shared, recorded player-choice authority."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_lethal_hits_source_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_lethal_hits_source.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


def test_auto_wounding_is_owned_by_the_shared_choice() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    tree = ast.parse((engine / "attack_sequence_dice_rerolls.py").read_text())
    owner = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_roll_hit_and_wound"
    )
    calls = [
        n.func.id
        for n in ast.walk(owner)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls.count("lethal_hit_wound_choice") == 1
    assert "lethal_hits_applies" not in calls
    for filename in ("lifecycle_attack_prevalidation.py", "lifecycle_restore_consistency.py"):
        assert "validate_lethal_hit_history(" in (engine / filename).read_text()
    assert "*_asdf.ATTACK_SEQUENCE_DECISION_TYPES" in (engine / "lifecycle.py").read_text()


def test_shared_attack_performance_stays_within_fixed_budgets() -> None:
    directory = ROOT / "docs/performance/order44"
    budget = json.loads((directory / "budgets.json").read_text())
    for prefix in ("", "lethal-"):
        base = json.loads((directory / f"{prefix}base.json").read_text())
        head = json.loads((directory / f"{prefix}head.json").read_text())
        for field in ("workload_id", "platform", "python", "mode", "hashes"):
            assert base[field] == head[field]
        assert not head["full_game_certified"]
        assert head["mode"] == "uninstrumented_timing"
        assert set(base["results"]) == set(head["results"])
        key = "lethal_" if prefix else ""
        for name, row in head["results"].items():
            original = base["results"][name]
            assert len(row["samples"]) == len(original["samples"]) == budget["samples_per_case"]
            assert row["completion_rate"] == original["completion_rate"] == 1
            assert row["mean_seconds"] <= (
                original["mean_seconds"] * budget[f"{key}mean_base_multiplier"]
                + budget[f"{key}mean_additive_seconds"]
            )
            assert row["maximum_seconds"] <= budget[f"{key}maximum_seconds"]
            if prefix:
                assert all(
                    0 < sample["lethal_choice_count"] <= sample["hit_count"]
                    for sample in row["samples"]
                )
