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


def test_v963_execution_and_hit_restore_share_classification_and_keep_wound_owner() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    hit_owner = (engine / "attack_sequence_hit_wound.py").read_text(encoding="utf-8")
    model = (engine / "attack_sequence_model.py").read_text(encoding="utf-8")
    resolver = (engine / "hit_thresholds.py").read_text(encoding="utf-8")
    assert "successful, critical = classify_hit_roll(" in hit_owner
    assert "expected_success, expected_critical = classify_hit_roll(" in model
    assert "snap = sources.SNAP_NO_CRITICAL_SOURCE_ID in thresholds.source_ids" in resolver
    assert "critical = not snap and critical_rule.matches(unmodified_roll)" in resolver
    assert "critical_hit=critical" in hit_owner
    assert "if critical and (" in hit_owner
    assert "def _critical_wound_threshold(" in hit_owner
    assert "critical = critical_threshold.matches(unmodified)" in hit_owner
    lethal = (engine / "lethal_hits.py").read_text(encoding="utf-8")
    assert "not hit.critical" in lethal
    events = (engine / "attack_sequence_dice_rerolls.py").read_text(encoding="utf-8")
    assert "if hit_roll.critical:" in events
    assert "roll_critical=hit_roll.critical" in events
    post_roll = (engine / "attack_sequence_post_roll.py").read_text(encoding="utf-8")
    assert 'critical=payload["critical"]' in post_roll


def test_v963_source_is_complete_and_historical_observations_remain_immutable() -> None:
    import hashlib
    import json
    from typing import cast

    from tools import v963_snap_source
    from tools.build_core_critical_hits_source import build_payloads

    selected = v963_snap_source.selected_record()
    assert selected["ref"] == "15.09"
    assert len(cast(list[object], selected["text"])) == 10
    text = v963_snap_source.source_text()
    assert "Those hits are not critical hits." in text
    assert "unmodified hit roll of 6" in text
    assert "cannot re\u2011roll hit rolls" in text
    current, _audit = build_payloads()
    mapping = json.loads(
        (ROOT / "data/source_audits/v963_snap/historical-inputs.json").read_bytes()
    )
    for row in mapping["files"]:
        raw = (ROOT / row["historical_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert len(raw) == row["bytes"]
    package = next(row for row in mapping["files"] if row["path"].endswith("package.json"))
    old = json.loads((ROOT / package["historical_path"]).read_bytes())
    assert cast(list[object], current["rules"])[:2] == old["rules"]
    assert cast(list[object], current["evidence"])[:4] == old["evidence"]


def test_restoration_and_pre_submission_share_hit_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for filename, function in (
        ("lifecycle_restore_consistency.py", "validate_payload_consistency"),
        ("lifecycle_attack_prevalidation.py", "pre_validate_attack_sequence_decision"),
    ):
        tree = ast.parse((engine / filename).read_text())
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_attack_hit_authority"
            for node in ast.walk(owner)
        )
    lifecycle = ast.parse((engine / "lifecycle.py").read_text())
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_payload_consistency"
        for node in ast.walk(lifecycle)
    )


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


def test_hit_restore_and_continuation_stay_within_fixed_budgets() -> None:
    import json

    directory = ROOT / "docs/performance/order43"
    base = json.loads((directory / "restore-base.json").read_text())
    head = json.loads((directory / "restore-head.json").read_text())
    budget = json.loads((directory / "restore-budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for key in ("platform", "python", "hashes", "mode"):
        assert base[key] == head[key]
    assert set(base["results"]) == set(head["results"]) == {"shooting", "fight"}
    for name, measured in head["results"].items():
        original = base["results"][name]
        assert len(measured["samples"]) == len(original["samples"]) == budget["samples_per_case"]
        assert measured["completion_rate"] == original["completion_rate"] == 1
        for metric in ("restore_seconds", "continuation_seconds"):
            assert measured[metric]["mean_seconds"] <= (
                original[metric]["mean_seconds"] * budget["mean_base_multiplier"]
                + budget["mean_additive_seconds"]
            )
            assert measured[metric]["maximum_seconds"] <= budget[f"maximum_{metric}"]
        assert [(row["decision_count"], row["event_count"]) for row in measured["samples"]] == [
            (row["decision_count"], row["event_count"]) for row in original["samples"]
        ]
