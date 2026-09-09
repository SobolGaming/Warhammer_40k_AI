from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

from tools.build_core_actions_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_actions_2026_09

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_action_source_generation_and_reused_shooting_bindings_are_exact() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert (
            path.read_bytes() == (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        )
    package = core_actions_2026_09.source_package()
    assert len(package.evidence_required_source_ids) == 4
    source_root = ARTIFACT_PATH.parents[2]
    indirect = json.loads(
        (source_root / "core_indirect_shooting_2026_09/artifacts/package.json").read_text()
    )
    stratagems = json.loads(
        (source_root / "core_stratagems_2026_08/artifacts/package.json").read_text()
    )
    rows = [*indirect["rules"], *stratagems["rules"]]
    consumer = (
        "warhammer40k_core.engine.activity_restrictions:record_completed_shooting_restriction"
    )
    for source_id in core_actions_2026_09.RESTRICTION_POLICY.after_shooting_source_rule_ids[-2:]:
        row = next(row for row in rows if row["source_id"] == source_id)
        assert consumer in row["runtime_consumer_ids"]
        assert row["semantic_execution_status"] == "partial_engine_runtime"


def test_action_queries_do_not_reconstruct_activity_from_phase_or_whole_history() -> None:
    tree = ast.parse((ENGINE / "mission_action_eligibility.py").read_text())
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not {"mission_action_states", "shooting_phase_state", "upper", "casefold"} & attributes
    activity = ast.parse((ENGINE / "activity_restrictions.py").read_text())
    query = next(
        node
        for node in activity.body
        if isinstance(node, ast.FunctionDef) and node.name == "has_activity_restriction"
    )
    attributes = {node.attr for node in ast.walk(query) if isinstance(node, ast.Attribute)}
    assert {
        "active_player_id",
        "battle_round",
        "current_battle_phase",
        "persisting_effects",
    } <= attributes
    assert not {"mission_action_states", "records", "shooting_phase_state"} & attributes
    completion = ast.parse((ENGINE / "model_attack_history.py").read_text())
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_completed_shooting_restriction"
        for node in ast.walk(completion)
    )


def test_action_restriction_slice_stays_within_versioned_work_budgets() -> None:
    from scripts.measure_action_restrictions import sample

    budgets = json.loads((ROOT / "docs/performance/order34/budgets.json").read_text())
    result = sample(profile=True)
    assert result["decision_count"] == 1
    assert result["action_count"] == 1
    counts = result["work_counts"]
    assert isinstance(counts, dict)
    counts = cast(dict[str, int], counts)
    assert counts["record_persisting_effect"] == 1
    assert counts["expire_persisting_effects_at_boundary"] == 4
    for metric, maximum in budgets["work_limits"].items():
        assert counts.get(metric, 0) <= maximum, (metric, counts)


def test_shooting_unit_selection_has_engine_preflight_before_recording() -> None:
    tree = ast.parse((ENGINE / "lifecycle_shooting_prevalidation.py").read_text())
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "invalid_shooting_unit_selection_status"
        for node in ast.walk(tree)
    )
    lifecycle = ast.parse((ENGINE / "lifecycle.py").read_text())
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "pre_validate_shooting_decision"
        for node in ast.walk(lifecycle)
    )


def test_historical_action_consumers_supply_exact_checkpoint_event_authority() -> None:
    for name in (
        "mission_action_options.py",
        "primary_mission_action_integrity.py",
        "primary_mission_action_decline_integrity.py",
        "primary_mission_pending_request_integrity.py",
    ):
        tree = ast.parse((ENGINE / name).read_text())
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "primary_mission_action_boundary_state_from_checkpoint"
        ]
        assert len(calls) == 1, name
        assert {"event_records", "checkpoint_event_id"} <= {
            keyword.arg for keyword in calls[0].keywords
        }, name
