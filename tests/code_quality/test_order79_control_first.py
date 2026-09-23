"""Source, shared boundary ownership and reproducible performance evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import july_rules_updates_2026_07

ROOT = Path(__file__).resolve().parents[2]


def test_order79_registered_control_first_source_matches_fresh_observation() -> None:
    observation = json.loads((ROOT / "docs/performance/order79/preflight.json").read_bytes())[
        "source"
    ]
    package = july_rules_updates_2026_07.source_package()
    source = next(
        source
        for document in package.source_catalog.documents
        for source in document.source_texts
        if source.source_id == observation["stable_source_id"]
    )
    assert source.raw_text == observation["operative_transcription"]
    assert (
        hashlib.sha256(source.raw_text.encode()).hexdigest() == observation["transcription_sha256"]
    )
    assert source.source_id in package.evidence_required_source_ids
    assert observation["app_version"] is None


def test_order79_shared_turn_owner_separates_snapshot_from_cleanup() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    boundary = ast.parse((engine / "turn_end_boundary.py").read_text())
    functions = {node.name: node for node in boundary.body if isinstance(node, ast.FunctionDef)}
    determine = functions["determine_turn_end_control"]
    calls = {
        node.func.attr
        for node in ast.walk(determine)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "record_objective_control_boundary" in calls
    assert not calls & {"clear_turn_action_states", "resolve_end_turn_cleanup_boundary"}
    for name in ("game_state.py", "boundary_rule_flow.py"):
        assert "turn_end_boundary import" in (engine / name).read_text()
    flow = (engine / "battle_round_flow.py").read_text()
    assert flow.index("prepare_turn_end_control_boundary(\n") < flow.index(
        "trigger_kind=TimingTriggerKind.END_TURN"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {"source_text", "lower", "casefold"}
        for node in ast.walk(boundary)
    )


def test_order79_matched_boundary_performance() -> None:
    folder = ROOT / "docs/performance/order79"
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
    for path, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert [row["case"] for row in head["rows"]] == ["player-b", "player-a"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 5
        assert after["controllers"] == [None] * 5
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
    assert not head["full_game_certified"]
