"""P01I source provenance, shared quarter ownership and matched query costs."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from tools.build_core_table_quarters_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_table_quarters_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_table_quarter_source_is_reproducible_and_authorized() -> None:
    artifact, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text()) == artifact
    assert json.loads(AUDIT_PATH.read_text()) == audit
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == source.EXPECTED_ARTIFACT_SHA256
    assert source.source_package().evidence_required_source_ids == (
        source.TABLE_QUARTERS_SOURCE_ID,
    )
    assert source.DIVIDER_WIDTH_INCHES == 1 / 25.4


def test_all_quarter_consumers_share_geometry_including_restore() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for filename in ("primary_scoring_spatial_evidence.py", "secondary_scoring_occupancy.py"):
        text = (engine / filename).read_text()
        assert "scoring_table_quarter_id_or_none(" in text
        assert "quarter_bounds" not in text
        assert "base_footprint_within_bounds(" not in text
    assert (
        "build_primary_scoring_spatial_evidence("
        in (engine / "primary_scoring_commit_checkpoint_authority.py").read_text()
    )
    assert (
        "build_secondary_battlefield_occupancy("
        in (engine / "secondary_scoring_state_evidence_authority.py").read_text()
    )
    shared = (engine / "table_quarters.py").read_text()
    assert "quarter_source.DIVIDER_WIDTH_INCHES" in shared
    assert "wholly_within_table_quarter(" in shared


def test_quarter_query_matched_cost_and_result_gate() -> None:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order86"
    base, head = (json.loads((folder / name).read_text()) for name in ("base.json", "head.json"))
    budget = json.loads((folder / "budget.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "cpu",
        "memory_bytes",
        "platform",
        "python",
        "concurrency",
        "timing_boundary",
        "hashes",
    ):
        assert base[key] == head[key], key
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert head["workload"] == budget["workload"]
    assert not head["full_game_certified"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["gap"] == after["gap"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == budget["samples"]
        assert before["qualifying_counts"] == [100] * budget["samples"]
        assert (
            after["qualifying_counts"] == [0 if after["gap"] == 0.01 else 100] * budget["samples"]
        )
        assert after["mean_seconds"] == statistics.mean(after["samples_seconds"])
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
        )
        assert max(after["samples_seconds"]) <= budget["maximum_query_seconds"]


def test_inherited_completion_diagnostic_has_a_fresh_matched_baseline() -> None:
    folder = ROOT / "docs/performance"
    base = json.loads((folder / "order86/completion-base.json").read_text())
    head = json.loads((folder / "order77/r77_001_boundary/completion-head.json").read_text())
    budgets = json.loads((folder / "order77/budgets.json").read_text())
    assert base["revision"] == "c727a6ad08ff9204d5338dabc736bbf767812a1e"
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "library_versions",
        "timing_boundary",
        "hashes",
    ):
        assert base[key] == head[key], key
    assert len(base["samples"]) == len(head["samples"]) == budgets["required_completed_submissions"]
    for before, after in zip(base["samples"], head["samples"], strict=True):
        assert before["repeat"] == after["repeat"]
        assert before["action_status"] == after["action_status"] == "completed"
        assert after["seconds"] <= budgets["maximum_restore_seconds"]
        assert (
            after["seconds"]
            <= before["seconds"] * budgets["maximum_ratio"] + budgets["jitter_allowance_seconds"]
        )
