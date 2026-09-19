from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tools.build_core_embark_setup_turn_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_embark_setup_turn_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_embark_source_is_pinned_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert (
            path.read_bytes() == (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        )
    package = source.source_package()
    assert package.source_catalog.catalog_sha256() == source.source_catalog().catalog_sha256()
    assert source.EMBARK_POLICY.forbids_setup_this_turn
    assert source.EMBARK_POLICY.scopes_to_actual_turn_player
    (rule,) = source.source_rules()
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.EmbarkSetupTurnSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_every_embark_consumer_supplies_history_and_actual_turn() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    calls: list[str] = []
    for path in engine.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "resolve_embark"
            ):
                keywords = {argument.arg for argument in node.keywords}
                assert {"movement_history", "turn_player_id"} <= keywords, path
                calls.append(path.name)
    assert calls == ["movement_fall_back_embark.py", "movement_fall_back_embark.py"]
    owner = (engine / "transport_embark_validation.py").read_text(encoding="utf-8")
    assert "unit_disembarked_this_phase" not in owner
    assert "EMBARK_POLICY" in owner
    assert "embark_after_setup_forbidden(" in (
        engine / "transport_embark_prevalidation.py"
    ).read_text(encoding="utf-8")


def test_order61_component_performance_has_matched_inputs_and_budget() -> None:
    directory = ROOT / "docs/performance/order61"
    base, head = (json.loads((directory / f"{name}.json").read_text()) for name in ("base", "head"))
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "concurrency",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(row["complete"] and row["queries"] == 50 for row in report["samples"])
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


def test_return_setup_restore_uses_shared_historical_model_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    owner = ast.parse((engine / "phase_movement_history.py").read_text(encoding="utf-8"))
    validator = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "validate_return_on_death_setup_authority"
    )
    calls = [node for node in ast.walk(validator) if isinstance(node, ast.Call)]
    timeline_builds = [
        node
        for node in calls
        if isinstance(node.func, ast.Name) and node.func.id == "build_model_authority_timeline"
    ]
    assert len(timeline_builds) == 1
    assert not any(
        timeline_builds[0] in tuple(ast.walk(node))
        for node in ast.walk(validator)
        if isinstance(node, (ast.For, ast.While))
    )
    assert {arg.arg for arg in timeline_builds[0].keywords} == {
        "state",
        "event_records",
        "decision_records",
    }
    assert any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "has_living_model_before_event"
        for node in calls
    )
    restore = ast.parse((engine / "lifecycle_restore_consistency.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == validator.name
        for node in ast.walk(restore)
    )


def test_return_setup_restore_performance_is_matched_and_within_budget() -> None:
    directory = ROOT / "docs/performance/order61"
    base, head = (
        json.loads((directory / f"restore-{name}.json").read_text()) for name in ("base", "head")
    )
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "checkpoint_sha256",
        "script_sha256",
        "lock_sha256",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples_seconds"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= (
        base["maximum_seconds"] * base["budgets"]["maximum_ratio"]
        + base["budgets"]["maximum_additive_seconds"]
    )
