"""Firing Deck shares shooting authority and never treats restricted cargo as shooters."""

from __future__ import annotations

import ast
import cProfile
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_firing_deck_has_shared_lifetime_and_no_phase_local_shooter_alias() -> None:
    source = (ENGINE / "phases/shooting_model.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "with_declaration"
    )
    assert "ineligible_unit_instance_ids" not in {arg.arg for arg in method.args.kwonlyargs}
    for module in ("phases/shooting_eligibility.py", "stratagems_geometry.py"):
        assert "shooting_state_restriction_reason(" in (ENGINE / module).read_text(encoding="utf-8")
    eligibility = (ENGINE / "shooting_eligibility_state.py").read_text(encoding="utf-8")
    assert "firing_deck_prevents_shooting(" in eligibility
    query = (ENGINE / "firing_deck_restrictions.py").read_text(encoding="utf-8")
    assert "EffectExpiration.end_turn(" in query
    assert "decision_records" not in query
    assert "event_records" not in query
    history = (ENGINE / "primary_mission_boundary_unit_history_authority.py").read_text(
        encoding="utf-8"
    )
    assert "declared.update(cast(list[str], ineligible))" not in history


def test_firing_deck_source_artifacts_are_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_firing_deck_source.py"), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_firing_deck_matched_performance_evidence() -> None:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order65"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    budgets = json.loads((folder / "budgets.json").read_text(encoding="utf-8"))
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "scenario",
        "timing_boundary",
        "hashes",
    ):
        assert base[key] == head[key], key
    assert head["workload_id"] == budgets["workload_id"]
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    for baseline, current in zip(base["rows"], head["rows"], strict=True):
        assert baseline["contribute"] == current["contribute"]
        assert len(baseline["samples"]) == len(current["samples"]) == 7
        for sample in current["samples"]:
            assert sample["complete"]
            assert sample["restricted_queries"] == 100
        for metric, additive in (
            ("declaration_seconds", "declaration_additive_seconds"),
            ("hundred_queries_seconds", "hundred_queries_additive_seconds"),
        ):
            before, after = baseline["summary"][metric], current["summary"][metric]
            assert after["mean"] <= before["mean"] * budgets["mean_ratio"] + budgets[additive]
            assert (
                after["maximum"]
                <= before["maximum"] * budgets["maximum_ratio"]
                + budgets["maximum_additive_seconds"]
            )


def test_firing_deck_live_query_work_is_bounded_by_matching_effects() -> None:
    from tests.firing_deck_helpers import PASSENGERS, firing_deck_session, submit_firing_deck
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.shooting_eligibility_state import (
        shooting_state_restriction_reason,
    )

    session, request, proposal = firing_deck_session()
    submit_firing_deck(session, request, proposal)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=PASSENGERS[1])
    before = state.to_payload()
    profiler = cProfile.Profile()
    with profiler:
        reasons = [
            shooting_state_restriction_reason(state=state, rules_unit=view, player_id="player-a")
            for _ in range(100)
        ]
    assert reasons == ["firing_deck"] * 100
    checks = sum(
        entry.callcount
        for entry in profiler.getstats()
        if not isinstance(entry.code, str)
        and entry.code.co_name == "firing_deck_restriction_payload"
    )
    budgets = json.loads(
        (ROOT / "docs/performance/order65/budgets.json").read_text(encoding="utf-8")
    )
    assert checks == 100 * budgets["query_payload_checks_per_effect"]
    assert state.to_payload() == before
