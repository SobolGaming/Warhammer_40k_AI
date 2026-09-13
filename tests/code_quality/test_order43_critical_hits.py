"""Critical-hit authority and generated-content regression gates."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "script",
    ["build_core_critical_hits_source.py", "generate_faction_stratagem_activation_support.py"],
)
def test_critical_hit_source_generators_reproduce_versioned_data(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / script), "--check"], cwd=ROOT, check=True)


def test_attack_hit_resolution_has_one_threshold_authority() -> None:
    tree = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/attack_sequence_hit_wound.py").read_text()
    )
    hit = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_roll_hit"
    )
    calls = [
        node.func.id
        for node in ast.walk(hit)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert calls.count("resolve_hit_thresholds") == 1
    assert "unmodified == 6" not in ast.unparse(hit)
    resolver = (ROOT / "src/warhammer40k_core/engine/hit_thresholds.py").read_text()
    assert resolver.count("for effect in _matching_generic_attack_effects(") == 1
    assert "required_targeting_rule_id" in resolver


def test_activation_generator_emits_json_and_loader_validates_eagerly() -> None:
    generator = (ROOT / "tools/generate_faction_stratagem_activation_support.py").read_text()
    assert "_module_text" not in generator
    assert "faction_stratagem_activation_2026_27.json" in generator
    loader = (
        ROOT
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "faction_stratagem_activation_2026_27.py"
    ).read_text()
    assert "_ARTIFACT = validate_artifact_bytes(" in loader
    assert "RuleIR.from_payload(" in loader


def test_critical_hit_slice_evidence_is_comparable_and_within_budget() -> None:
    import json

    directory = ROOT / "docs/performance/order43"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for key in ("platform", "python", "hashes", "mode"):
        assert base[key] == head[key]
    assert head["mode"] == "uninstrumented_timing"
    assert not head["full_game_certified"]
    assert set(base["results"]) == set(head["results"])
    for name, measured in head["results"].items():
        original = base["results"][name]
        assert len(measured["samples"]) == len(original["samples"]) == budget["samples_per_case"]
        assert measured["completion_rate"] == original["completion_rate"] == 1
        assert (
            measured["mean_seconds"]
            <= original["mean_seconds"] * budget["mean_base_multiplier"]
            + budget["mean_additive_seconds"]
        )
        assert measured["maximum_seconds"] <= budget["maximum_seconds"]
        assert [(row["decision_count"], row["hit_count"]) for row in measured["samples"]] == [
            (row["decision_count"], row["hit_count"]) for row in original["samples"]
        ]
