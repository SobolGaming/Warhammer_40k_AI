"""Guard the source-backed shared unit-scope predicate and its measured workload."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_revival_2026_09

ROOT = Path(__file__).resolve().parents[2]


def test_revival_source_is_registered_and_generated_from_the_reviewed_observation() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_revival_source.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    source = core_revival_2026_09
    (rule,) = source.source_rules()
    assert rule.source_id == source.REVIVAL_SOURCE_ID
    assert rule.section_id == "01.02.03"
    assert "only if those enemy units were already engaged" in rule.source_text
    mirror = next(
        row for row in source.source_evidence_records() if row.evidence_kind == "third_party_mirror"
    )
    assert mirror.authority == "project_authoritative_app_mirror"
    assert mirror.app_version is None
    assert mirror.observed_at == "2026-09-24T13:16:10+00:00"
    assert source.source_package().source_authority_scope == "warhammer_40000_11th_core_rules"


def test_revival_uses_one_shared_physical_predicate_and_no_producer_model_allowlists() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for path in engine.rglob("*.py"):
        tree = ast.parse(path.read_text())
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "phase_start_enemy_engagement_model_ids"
        ]
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.keyword)
            and node.arg == "phase_start_enemy_engagement_model_ids"
        ]
    assert "revival_engagement_evidence(" in (engine / "healing_revival.py").read_text()
    history = (engine / "revival_engagement_history.py").read_text()
    assert "physical_model_authority_before_event(" in history
    assert "validate_mutation_decision_closure(" in history
    assert "validate_revival_engagement_geometry(" in history
    assert (
        "validate_revival_engagement_history("
        in (engine / "lifecycle_restore_consistency.py").read_text()
    )
    predicate = ast.parse((engine / "revival_engagement.py").read_text())
    calls = {
        node.func.id
        for node in ast.walk(predicate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "physical_geometry_models_for_rules_unit" in calls
    assert "geometry_models_are_physically_engaged" in calls
    assert not [
        node
        for node in ast.walk(predicate)
        if isinstance(node, ast.Attribute)
        and node.attr in {"source_text", "lower", "casefold", "is_within_engagement_range"}
    ]


def test_revival_matched_slice_performance() -> None:
    folder = ROOT / "docs/performance/order82"
    base, head = (json.loads((folder / name).read_bytes()) for name in ("base.json", "head.json"))
    budget = json.loads((folder / "budgets.json").read_bytes())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "cpu",
        "memory_bytes",
        "platform",
        "python",
        "concurrency",
        "hashes",
        "timing_boundary",
        "fixture",
    ):
        assert base[key] == head[key], key
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert head["workload"] == budget["workload"]
    assert [row["case"] for row in head["rows"]] == [
        "unengaged-control",
        "same-enemy-unit",
        "attached",
        "retained-enemy",
        "new-enemy-unit",
    ]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 3
        assert all(
            (status == "invalid") == (after["case"] == "new-enemy-unit")
            for status in after["outcomes"]
        )
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
        )
        assert after["maximum_seconds"] <= budget["maximum_seconds"]
    assert not head["full_game_certified"]
