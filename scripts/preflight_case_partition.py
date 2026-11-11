"""One source-bound finite partition; measurements remain separate from weights."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import cast

from scripts.hosted_timing_calibration import read_json

OWNER = "tests/infrastructure/adapters/test_canonical_coverage_preflight.py"
SOURCE_SHA256 = "90b2fbdcaa950cfa3002dc7c1b3172473639b66c94fd9192839162f95d148068"
FILENAME = "preflight-case-partition.json"
SCHEMA = "finite-preflight-case-partition-v1"
NODES = tuple(
    OWNER + "::" + name
    for name in (
        "test_consistent_tampering_still_reproduces_the_real_engine",
        "test_coverage_totals_derive_each_kind_without_fixed_fixture_counts",
        "test_coverage_totals_reject_missing_or_noninteger_counts[-1]",
        "test_coverage_totals_reject_missing_or_noninteger_counts[1.0]",
        "test_coverage_totals_reject_missing_or_noninteger_counts[1]",
        "test_coverage_totals_reject_missing_or_noninteger_counts[None]",
        "test_coverage_totals_reject_missing_or_noninteger_counts[True]",
        "test_coverage_totals_require_typed_rows[None]",
        "test_coverage_totals_require_typed_rows[rows1]",
        "test_coverage_totals_require_typed_rows[rows2]",
        "test_coverage_totals_require_typed_rows[rows3]",
        "test_coverage_totals_require_typed_rows[rows4]",
    )
)


def partition(root: Path, files: frozenset[str]) -> dict[str, float]:
    if OWNER not in files:
        return {}
    from scripts.build_test_shards import _selection_no_links

    source = root / OWNER
    path = root / "ci/test_shards" / FILENAME
    _selection_no_links(root, source)
    _selection_no_links(root, path)
    value = read_json(path)
    if (
        hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256
        or not isinstance(value, dict)
        or value.keys() != {"schema", "source_file", "source_sha256", "nodes", "weights", "role"}
        or value["schema"] != SCHEMA
        or value["source_file"] != OWNER
        or value["source_sha256"] != SOURCE_SHA256
        or value["nodes"] != list(NODES)
        or value["role"] != "Derived ratios preserve baseline file totals; not new measurements"
        or not isinstance(value["weights"], dict)
        or value["weights"].keys() != set(NODES)
    ):
        raise SystemExit("Preflight finite partition source or exact inventory changed.")
    weights: dict[str, float] = {}
    for node in NODES:
        weight = value["weights"][node]
        if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
            raise SystemExit("Preflight partition weights must be positive finite ratios.")
        weights[node] = float(weight)
    return weights


def validate_case_inventory(cases: dict[str, float]) -> None:
    actual = {node for node in cases if node.split("::", 1)[0] == OWNER}
    if actual and actual != set(NODES):
        raise SystemExit("Preflight partition differs from the complete measured case inventory.")


def partition_durations(root: Path, durations: dict[str, float]) -> dict[str, float]:
    weights = partition(root, frozenset(durations))
    if not weights:
        return durations
    result = dict(durations)
    total = result.pop(OWNER)
    denominator = math.fsum(weights.values())
    result.update({node: total * weight / denominator for node, weight in weights.items()})
    return result


def partition_selectors(root: Path, selectors: set[str]) -> set[str]:
    weights = partition(root, frozenset(selectors))
    return (selectors - {OWNER}) | weights.keys() if weights else selectors


def source_metadata(root: Path) -> dict[str, str]:
    path = root / "ci/test_shards" / FILENAME
    return {"file": FILENAME, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_metadata(root: Path, value: object) -> None:
    if not isinstance(value, dict) or cast(dict[str, object], value) != source_metadata(root):
        raise SystemExit("Preflight partition metadata is missing or changed.")
    partition(root, frozenset({OWNER}))
