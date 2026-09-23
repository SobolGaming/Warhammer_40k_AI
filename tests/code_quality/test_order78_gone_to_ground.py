"""Preserve source identity, shared concealment authority and measured workload."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_gone_to_ground_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]


def test_order78_generated_source_matches_reviewed_preflight() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_gone_to_ground_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads((ROOT / "docs/performance/order78/preflight.json").read_bytes())["source"]
    (rule,) = source.source_rules()
    assert rule.source_text == observed["operative_transcription"]
    assert rule.transcription_sha256 == observed["transcription_sha256"]
    mirror = next(
        row for row in source.source_evidence_records() if row.evidence_kind == "third_party_mirror"
    )
    assert mirror.observed_at == observed["observed_at"]
    assert mirror.source_url == observed["source_url"]
    assert mirror.app_version is None
    assert mirror.provider_non_affiliation_recorded
    assert source.source_package().source_authority_scope == "warhammer_40000_11th_core_rules"


def test_order78_shared_authority_keeps_hidden_occupancy_separate_from_concealment() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    hidden = ast.parse((engine / "hidden_detection.py").read_text())
    calls = {
        node.func.id
        for node in ast.walk(hidden)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "model_within_solid_terrain" not in calls
    assert "blocker_record_is_dense_feature" in calls
    assert not [
        node
        for node in ast.walk(hidden)
        if isinstance(node, ast.Attribute)
        and node.attr in {"source_text", "lower", "upper", "casefold"}
    ]
    targets = ast.parse((engine / "shooting_targets.py").read_text())
    consumers = {
        node.name
        for node in targets.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "hidden_detection_eligible_target_model_ids"
            for call in ast.walk(node)
        )
    }
    assert consumers == {"_target_candidate", "unit_has_line_of_sight_to_target"}
    from warhammer40k_core.engine.hidden_detection import GONE_TO_GROUND_SOURCE_ID

    assert GONE_TO_GROUND_SOURCE_ID == source.GONE_TO_GROUND_SOURCE_ID
    proof = json.loads(
        (ROOT / "data/source_audits/order78-runtime-consumer-proof-v1.json").read_bytes()
    )
    assert proof["source_id"] == GONE_TO_GROUND_SOURCE_ID
    for clause in proof["clauses"]:
        assert clause["regression_ids"]
        for reference in clause["regression_ids"]:
            path, name = reference.split(":")
            tree = ast.parse((ROOT / path).read_text())
            assert any(
                isinstance(node, ast.FunctionDef) and node.name == name for node in tree.body
            )


def test_order78_matched_query_evidence() -> None:
    folder = ROOT / "docs/performance/order78"
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
    assert [row["case"] for row in head["rows"]] == [
        "dense-outside",
        "dense-inside",
        "attached-outside",
        "light-outside",
        "not-hidden",
        "fully-visible",
    ]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        assert after["legal"] == (after["case"] in {"light-outside", "not-hidden", "fully-visible"})
        assert after["shared_los"] == after["legal"]
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
    assert not head["full_game_certified"]
