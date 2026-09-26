"""Keep dash sentinels out of Strength comparisons and preserve source authority."""

import ast
import hashlib
import json
import statistics
from pathlib import Path

from tools.build_core_modifiers_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_modifiers_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_strength_consumers_use_the_shared_interaction_query() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    violations: list[str] = []
    for path in engine.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in {"raw", "base", "final"}
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "strength"
            ):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, violations
    tree = ast.parse((engine / "attack_sequence_hit_wound.py").read_text())
    for function in (
        "_roll_wound",
        "_wound_roll_modifier",
        "_reroll_wound_for_twin_linked_if_needed",
    ):
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "strength_for_interaction"
            for node in ast.walk(owner)
        ), function


def test_absent_strength_source_is_reproducible_and_authorized() -> None:
    artifact, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text()) == artifact
    assert json.loads(AUDIT_PATH.read_text()) == audit
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == source.EXPECTED_ARTIFACT_SHA256
    assert source.ABSENT_STRENGTH_SOURCE_ID in source.source_package().evidence_required_source_ids
    rule = next(
        row for row in source.source_rules() if row.source_id == source.ABSENT_STRENGTH_SOURCE_ID
    )
    assert rule.section_id == "02.04.01"
    assert rule.runtime_consumer_ids == (
        "warhammer40k_core.core.weapon_profiles:WeaponProfile.strength_for_interaction",
    )


def test_strength_diagnostic_keeps_matched_inputs_and_work_counts() -> None:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order88"
    base, head = (json.loads((folder / name).read_text()) for name in ("base.json", "head.json"))
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "hardware_status",
        "concurrency",
        "coverage",
        "fixture",
        "seeds",
        "policy",
        "timing_boundary",
        "hashes",
    ):
        assert base[key] == head[key], key
    for path, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert not head["full_game_certified"]
    assert head["full_game_samples"] == 0
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["phase"] == after["phase"]
        assert before["wound_count"] == after["wound_count"] == [12] * 5
        assert len(after["samples_seconds"]) == len(before["samples_seconds"]) == 5
        assert after["mean"] == statistics.mean(after["samples_seconds"])
        assert after["p95_and_maximum"] == max(after["samples_seconds"])
