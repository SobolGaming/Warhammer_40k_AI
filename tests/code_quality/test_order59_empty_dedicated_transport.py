from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tools.build_core_empty_dedicated_transport_source import (
    ARTIFACT_PATH,
    AUDIT_PATH,
    build_payloads,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_empty_dedicated_transport_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_empty_dedicated_transport_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text(encoding="utf-8") == (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        )
    assert (
        source.source_package().source_catalog.catalog_sha256()
        == source.source_catalog().catalog_sha256()
    )
    (rule,) = source.source_rules()
    assert source.DESTRUCTION_POLICY.source_rule_id == rule.source_id
    assert source.DESTRUCTION_POLICY.destroys_at_declare_battle_formations_end is True
    assert source.DESTRUCTION_POLICY.triggers_destroyed_model_rules is False
    assert source.DESTRUCTION_POLICY.requires_embarked_unit is True
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "apply_empty_dedicated_transport_destruction" in rule.runtime_consumer_ids[0]
    with pytest.raises(source.EmptyDedicatedTransportSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_empty_dedicated_transport_destruction_has_one_mutation_owner() -> None:
    owner = (ENGINE / "empty_dedicated_transport_destruction.py").read_text(encoding="utf-8")
    setup_flow = (ENGINE / "setup_flow.py").read_text(encoding="utf-8")
    assert "DESTRUCTION_POLICY" in owner
    assert "destroy_unplaced_model_without_reactions(" in owner
    assert "destroyed_model_rules_triggered" in owner
    assert "replace_battlefield_state(" in owner
    assert "apply_empty_dedicated_transport_destruction(" in setup_flow
    assert "destroy_model_by_rule(" not in owner
    assert "destroy_model_by_rule(" not in setup_flow
    assert _apply_call_modules() == ("setup_flow.py",)


def test_order59_performance_has_matched_inputs_and_passes_declared_budgets() -> None:
    directory = ROOT / "docs/performance/order59"
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
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        destroyed = report["samples"][0]["destroyed_model_count"]
        events = report["samples"][0]["destruction_events"]
        assert all(sample["complete"] is True for sample in report["samples"])
        assert all(sample["destroyed_model_count"] == destroyed for sample in report["samples"])
        assert all(sample["destruction_events"] == events for sample in report["samples"])
    assert head["samples"][0]["destroyed_model_count"] == 1
    assert head["samples"][0]["destruction_events"] == 1
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


def _apply_call_modules() -> tuple[str, ...]:
    modules: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_apply_call(node) for node in ast.walk(tree)):
            modules.append(path.name)
    return tuple(modules)


def _is_apply_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "apply_empty_dedicated_transport_destruction"
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "apply_empty_dedicated_transport_destruction"
    )
