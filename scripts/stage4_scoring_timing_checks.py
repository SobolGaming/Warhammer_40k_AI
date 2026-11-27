"""Focused checks for the Layout C boundary and matched-path evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_scoring_timing as timing
from scripts import stage4_split_objective as fixture


@pytest.fixture
def continuation() -> tuple[bench.Row, bench.Row]:
    early = fixture.sealed_receipt()["arms"]["screen-follow"]
    target = timing.objective_at(early, timing.A3_COMMAND)
    target.pop("boundary_id")
    records = {}
    for index, boundary in enumerate(timing.CONTINUATION_BOUNDARIES):
        objective = {
            **target,
            "vp": {bench.A: 6 if boundary == timing.A4_END else 0, bench.B: 0},
        }
        records[str(index)] = {
            "boundary": list(boundary),
            "objectives": {fixture.TARGET: objective},
        }
    return early, {
        "objective_boundaries": records,
        "material": dict.fromkeys(("origin", "endpoint"), early["material"]["endpoint"]),
        "rng_draw_delta": 0,
        "active_rng_draws": 0,
        "awards": [
            {
                "player": bench.A,
                "rule": timing.LATE_RULE,
                "boundary_id": str(timing.CONTINUATION_BOUNDARIES.index(timing.A4_END)),
                "vp_by_objective": {fixture.TARGET: 6},
            }
        ],
    }


def test_control_can_persist_across_both_scoring_windows(
    continuation: tuple[bench.Row, bench.Row],
) -> None:
    result = timing.timing_outcome(*continuation)
    rows = {row["boundary"]: row for row in result["target_boundaries"]}
    expected = {timing.B2_END: 0, timing.A3_COMMAND: 5, timing.A4_COMMAND: 0, timing.A4_END: 6}
    for boundary, points in expected.items():
        assert rows[boundary]["oc"] == {bench.A: 2, bench.B: 1}
        assert rows[boundary]["controller"] == bench.A
        assert rows[boundary]["vp"] == {bench.A: points, bench.B: 0}


def test_award_cannot_move_to_round_four_command(
    continuation: tuple[bench.Row, bench.Row],
) -> None:
    early, late = continuation
    row = late["objective_boundaries"][str(timing.CONTINUATION_BOUNDARIES.index(timing.A4_COMMAND))]
    row["objectives"][fixture.TARGET]["vp"][bench.A] = 6
    with pytest.raises(bench.BenchmarkGap, match="native window"):
        timing.timing_outcome(early, late)


def test_award_rule_must_match_turn_end_provenance(
    continuation: tuple[bench.Row, bench.Row],
) -> None:
    early, late = continuation
    late["awards"][0]["rule"] = fixture.RULE
    with pytest.raises(bench.BenchmarkGap, match="native window"):
        timing.timing_outcome(early, late)


def test_same_screen_and_opponent_paths_are_required() -> None:
    sealed = fixture.sealed_receipt()
    evidence = timing.matched_paths(sealed)
    assert set(evidence["shared_path_ids"]) == {"screen", "respond"}
    drift = deepcopy(sealed)
    drift["arms"]["screen-follow"]["menus"][2]["selected"] = bench.HOLD
    with pytest.raises(bench.BenchmarkGap, match="native respond path"):
        timing.matched_paths(drift)
