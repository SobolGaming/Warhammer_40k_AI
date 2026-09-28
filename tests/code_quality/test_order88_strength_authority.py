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
    for module, function in (
        ("attack_sequence_hit_wound.py", "_roll_wound"),
        ("attack_modifier_evaluation.py", "select_wound_modifiers"),
        ("attack_sequence_hit_wound.py", "_reroll_wound_for_twin_linked_if_needed"),
    ):
        tree = ast.parse((engine / module).read_text())
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
    ):
        assert base[key] == head[key], key
    _assert_versioned_strength_fixture_inputs(base["hashes"], head["hashes"])
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


def _assert_versioned_strength_fixture_inputs(base: dict[str, str], head: dict[str, str]) -> None:
    proof = json.loads(
        (ROOT / "docs/performance/order93/inherited-fixture-migration.json").read_text()
    )["strength_fixture_migration"]
    helper = "tests/psychic_modifier_helpers.py"
    assert proof["schema_version"] == 1
    assert set(proof["changed_files"]) == {helper}
    assert proof["comparison_revision"] == "d7bcb10bd9e34b1eabb060465be7f9517d8417eb"
    assert (
        proof["comparison_runtime_build_id"]
        == json.loads((ROOT / "docs/performance/order93/base.json").read_text())["runtime_build_id"]
    )
    assert (
        proof["historical_baseline_runtime_build_id"]
        == json.loads((ROOT / "docs/performance/order88/base.json").read_text())["runtime_build_id"]
    )
    assert proof["entrypoint"] == "strength_session"
    assert proof["entrypoint_kwargs"] == {"strength": 1}
    assert proof["driver_entrypoints"] == ["pending_request", "complete_attack"]
    assert base.keys() == head.keys()
    migration = proof["changed_files"][helper]
    for name in base:
        if name == helper:
            assert base[name] == migration["base_sha256"]
            assert head[name] == migration["head_sha256"]
            assert head[name] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        else:
            assert base[name] == head[name], name
    assert [row["phase"] for row in proof["cases"]] == ["shooting", "fight"]
    for row, token_count in zip(proof["cases"], (152, 118), strict=True):
        assert row["game_id"] == f"order88-{row['phase']}"
        assert row["wound_count"] == 12
        assert row["normalized_rng_event_count"] == token_count
        assert row["base_component_sha256"] == row["head_component_sha256"]
        assert set(row["base_component_sha256"]) == {
            "initial_lifecycle",
            "pending_request",
            "prepared_lifecycle",
            "wound_steps",
            "normalized_rng_tokens",
        }
        assert (
            row["base_final_lifecycle_sha256"]
            == row["head_final_without_added_wire_evidence_sha256"]
        )
        if row["phase"] == "shooting":
            assert row["base_final_lifecycle_sha256"] == row["head_final_lifecycle_sha256"]
            assert row["added_wire_evidence"] == []
            assert row["physical_weapon_bindings"] == []
        else:
            assert len(row["physical_weapon_bindings"]) == 1
            binding = row["physical_weapon_bindings"][0]
            assert binding["available_match_count"] == 1
            assert len(row["added_wire_evidence"]) == 5
            for addition in row["added_wire_evidence"]:
                assert addition["path"][-1] == "weapon_instance_id"
                assert addition["value"] == binding["weapon_instance_id"]
