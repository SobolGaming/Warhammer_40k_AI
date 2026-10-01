"""Fast gate for the measured failed-setup/restore/view/replay component workload."""

import hashlib
import json
from pathlib import Path

from tests.performance_evidence_helpers import (
    assert_historical_report,
    historical_input_bytes,
)

ROOT = Path(__file__).resolve().parents[2]


def test_failed_setup_component_keeps_matched_hard_cases_and_budget() -> None:
    directory = ROOT / "docs/performance/order101"
    base, head = (json.loads((directory / f"{name}.json").read_text()) for name in ("base", "head"))
    budgets = json.loads((directory / "budgets.json").read_text())
    for field in (
        "workload",
        "cpu",
        "memory_bytes",
        "platform",
        "python",
        "host_role",
        "concurrency",
        "timing_boundary",
        "scenario",
        "hashes",
    ):
        assert base[field] == head[field], field
    assert head["workload"] == budgets["workload"]
    assert_historical_report(head)
    assert head["host_role"] == "provisional"
    assert head["concurrency"] == 1
    assert base["coverage"] is False
    assert head["coverage"] is False
    assert base["full_game_certified"] is False
    assert head["full_game_certified"] is False
    assert budgets["full_game_certified"] is False
    for filename, digest in head["hashes"].items():
        assert hashlib.sha256(historical_input_bytes(filename)).hexdigest() == digest
    assert [row["case"] for row in head["rows"]] == ["cargo-5", "cargo-100", "loaded-deep-strike"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["case"] == after["case"]
        assert before["completion_rate"] == after["completion_rate"] == 1
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        assert before["selected_after_failure"] == [True] * 7
        assert after["selected_after_failure"] == [False] * 7
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budgets["mean_ratio"] + budgets["mean_additive_seconds"]
        )
        assert max(after["samples_seconds"]) <= budgets["maximum_seconds"]
