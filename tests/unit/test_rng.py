from __future__ import annotations

import pytest

from warhammer40k_core.core.rng import RandomSource, RandomSourceError


def test_random_source_same_seed_and_history_are_deterministic() -> None:
    left = RandomSource("seed", history=("event-a", "decision-b"))
    right = RandomSource("seed", history=("event-a", "decision-b"))

    assert left.randint_inclusive(1, 6, stream_label="advance:die-0") == right.randint_inclusive(
        1,
        6,
        stream_label="advance:die-0",
    )
    assert left.to_payload() == right.to_payload()


def test_random_source_history_changes_draw_stream() -> None:
    left = RandomSource("seed", history=("branch-a",))
    right = RandomSource("seed", history=("branch-b",))

    left_value = left.randint_inclusive(1, 100_000, stream_label="branch-test")
    right_value = right.randint_inclusive(1, 100_000, stream_label="branch-test")

    assert left.history_digest() != right.history_digest()
    assert left_value != right_value


def test_random_source_serialization_round_trips_exactly() -> None:
    source = RandomSource("seed", history=("event-a",), draw_count=2)

    assert RandomSource.from_payload(source.to_payload()).to_payload() == source.to_payload()


def test_random_source_rejects_invalid_inputs() -> None:
    with pytest.raises(RandomSourceError):
        RandomSource("")
    with pytest.raises(RandomSourceError):
        RandomSource("seed", history=("",))
    with pytest.raises(RandomSourceError):
        RandomSource("seed", draw_count=-1)
    with pytest.raises(RandomSourceError):
        RandomSource("seed").append_history("")
    with pytest.raises(RandomSourceError):
        RandomSource("seed").fork("")
    with pytest.raises(RandomSourceError):
        RandomSource("seed").randint_inclusive(6, 1, stream_label="bad-bounds")
    with pytest.raises(RandomSourceError):
        RandomSource("seed").randint_inclusive(1, 6, stream_label="")


def test_random_source_fork_keeps_seed_and_draw_count_with_added_history() -> None:
    source = RandomSource("seed", history=("event-a",), draw_count=3)
    forked = source.fork("decision-b")

    assert forked.to_payload() == {
        "seed": "seed",
        "history": ["event-a", "decision-b"],
        "draw_count": 3,
    }
