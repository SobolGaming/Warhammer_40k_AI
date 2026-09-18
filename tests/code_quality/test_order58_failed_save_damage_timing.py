from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tools.build_core_failed_save_damage_timing_source import (
    ARTIFACT_PATH,
    AUDIT_PATH,
    build_payloads,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_failed_save_damage_timing_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_failed_save_damage_timing_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text(encoding="utf-8") == (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        )
    assert (
        source.source_package().source_catalog.catalog_sha256()
        == source.source_catalog().catalog_sha256()
    )
    (rule,) = source.source_rules()
    assert source.TIMING_POLICY.source_rule_id == rule.source_id
    assert source.TIMING_POLICY.applies_after_saving_throw is True
    assert source.TIMING_POLICY.applies_before_saving_throw is False
    assert source.TIMING_POLICY.replacement_damage == 0
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "unused_failed_save_damage_replacement" in rule.runtime_consumer_ids[0]
    with pytest.raises(source.FailedSaveDamageTimingSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_failed_save_damage_replacement_has_one_post_save_mutation_owner() -> None:
    owner = (ENGINE / "failed_save_damage_timing.py").read_text(encoding="utf-8")
    grouped = (ENGINE / "attack_sequence_grouped_allocation.py").read_text(encoding="utf-8")
    assert "TIMING_POLICY" in owner
    assert "unused_failed_save_damage_replacement(" in grouped
    assert "timing_source_rule_id" in grouped
    assert "_unused_failed_save_damage_replacement(" not in grouped
    assert ".failed_save_damage_replacement(" not in grouped
    calls = _failed_save_replacement_call_modules()
    assert calls == ("failed_save_damage_timing.py",)
    save_fn = _function_named(
        ENGINE / "attack_sequence_grouped_allocation.py",
        "_resolve_grouped_damage_from",
    )
    lines = _call_lines(save_fn)
    assert lines["resolve_saving_throw"] < lines["unused_failed_save_damage_replacement"]
    assert lines["unused_failed_save_damage_replacement"] < lines["_damage_value"]
    replacement_line = lines["unused_failed_save_damage_replacement"]
    assert replacement_line < lines["allocated_attack_damage_modifier"]


def test_order58_performance_has_matched_inputs_and_passes_declared_budgets() -> None:
    directory = ROOT / "docs/performance/order58"
    base, head = (json.loads((directory / f"{name}.json").read_text()) for name in ("base", "head"))
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "timing_boundary",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    assert base["scenario"]["attack_count"] == head["scenario"]["attack_count"]
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        wounds = report["samples"][0]["defender_wounds_remaining"]
        replaced = report["samples"][0]["replacement_events"]
        assert all(sample["complete"] is True for sample in report["samples"])
        assert all(sample["defender_wounds_remaining"] == wounds for sample in report["samples"])
        assert all(sample["replacement_events"] == replaced for sample in report["samples"])
    assert head["samples"][0]["replacement_events"] == 1
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


def _failed_save_replacement_call_modules() -> tuple[str, ...]:
    modules: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_failed_save_replacement_call(node) for node in ast.walk(tree)):
            modules.append(path.name)
    return tuple(modules)


def _is_failed_save_replacement_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "failed_save_damage_replacement":
        return True
    return isinstance(func, ast.Name) and func.id == "failed_save_damage_replacement"


def _function_named(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name} in {path.name}")


def _call_lines(function: ast.FunctionDef) -> dict[str, int]:
    lines: dict[str, int] = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name not in lines or node.lineno < lines[name]:
            lines[name] = node.lineno
    return lines
