"""Admit reviewed derived allocation data; never trust an offline search's scores."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import cast

from scripts.historical_shard_snapshot import HISTORICAL_REVISION, HistoricalSnapshot
from scripts.hosted_timing_calibration import _object, read_json

FILENAME = "current-derived-assignment.json"
SCHEMA = "reviewed-derived-current-shard-assignment-v1"
ROLE = "Derived planning assignment only; no new hosted observations or timing qualification"
CURRENT_PLANNING_CEILING = 1350
CURRENT_PLANNING_POLICY = "native-serial-current-planning-v1"


def current_planning_policy() -> dict[str, object]:
    """Declare the reviewed current forecast guard separately from execution approval."""
    return {
        "version": CURRENT_PLANNING_POLICY,
        "role": "Current empirical projection guard; not observed completion or timing approval",
        "ceiling_seconds": CURRENT_PLANNING_CEILING,
        "rounding_seconds": 30,
        "planning_gap_to_1620_second_approval": 270,
    }


def load_assignment(
    directory: Path,
    descriptor: dict[str, object],
    history: HistoricalSnapshot,
) -> tuple[tuple[tuple[str, ...], ...], dict[str, object]]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    reference = _object(
        descriptor["assignment"], {"file", "sha256"}, "derived assignment reference"
    )
    path = directory / FILENAME
    if (
        reference["file"] != FILENAME
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Derived current assignment evidence changed.")
    record = _object(
        read_json(path),
        {
            "schema",
            "role",
            "historical_revision",
            "current_runtime_fingerprint",
            "baseline_sha256",
            "shards",
            "retained_selector_moves",
            "new_selector_placement",
        },
        "derived current assignment",
    )
    if (
        record["schema"] != SCHEMA
        or record["role"] != ROLE
        or record["historical_revision"] != HISTORICAL_REVISION
        or record["current_runtime_fingerprint"] != descriptor["current_runtime_fingerprint"]
        or record["baseline_sha256"] != cast(dict[str, object], descriptor["baseline"])["sha256"]
    ):
        raise SystemExit("Derived current assignment source binding differs.")
    shards = _object(record["shards"], {str(index) for index in range(1, 13)}, "current shards")
    for value in shards.values():
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(node, str) for node in value)
        ):
            raise SystemExit("Current shards require nonempty string selector lists.")
        if value != sorted(set(value)):
            raise SystemExit("Current shard selectors must be sorted and unique.")
    groups = tuple(tuple(cast(list[str], shards[str(index)])) for index in range(1, 13))
    owners = set(cast(dict[str, str], descriptor["new_test_sources"]))
    expected = Counter(selector for group in history.groups for selector in group)
    expected.update(owners)
    selected = Counter(selector for group in groups for selector in group)
    if selected != expected or len(selected) != 508:
        raise SystemExit("Derived current assignment selector inventory differs.")
    extension = history.scope.extension
    assert extension is not None
    if (
        extension.pinned_selector not in groups[3]
        or groups[4] != (extension.fixed_selector,)
        or SERIAL_BEHAVIORAL_CASE not in groups[1]
        or SERIAL_BEHAVIORAL_CASE in groups[0]
    ):
        raise SystemExit("Derived assignment changed a pinned file or controller role.")
    original = {
        selector: index for index, group in enumerate(history.groups, 1) for selector in group
    }
    current = {selector: index for index, group in enumerate(groups, 1) for selector in group}
    moves = [
        {"selector": selector, "from": original[selector], "to": current[selector]}
        for selector in sorted(original)
        if original[selector] != current[selector]
    ]
    if record["retained_selector_moves"] != moves or record["new_selector_placement"] != {
        owner: current[owner] for owner in sorted(owners)
    }:
        raise SystemExit("Derived assignment relocation disclosure differs.")
    return groups, record


def require_planning_limits(values: tuple[float, ...]) -> None:
    if (
        len(values) != 10
        or any(not math.isfinite(value) or value < 0 for value in values)
        or max(values) > CURRENT_PLANNING_CEILING
    ):
        raise SystemExit(
            "Derived current assignment exceeds its reviewed current planning ceiling."
        )
