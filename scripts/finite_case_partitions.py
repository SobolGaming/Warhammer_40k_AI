"""Two finite source-bound partitions; baseline ratios are not measurements."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import cast

from scripts import preflight_case_partition as preflight
from scripts.hosted_timing_calibration import read_json

FILENAME = "step5g-case-partitions.json"
SCHEMA = "finite-step5g-case-partitions-v1"
OWNERS = {
    "tests/infrastructure/missions/unit/test_step5g_pairing_certification.py": (
        "d682066797209b9152457a68d726f41313acc5fdb7d15ac17badedc11925954b",
        32,
    ),
    "tests/infrastructure/missions/unit/test_step5g_pairing_certification_layout_b.py": (
        "0ee5e52f49e404ef87bcc5e255983b99a2b9aab68f9943090b3e612f5bab7109",
        30,
    ),
}


def partitions(root: Path, files: set[str]) -> dict[str, dict[str, float]]:
    from scripts.build_test_shards import _selection_no_links

    if not files.intersection(OWNERS):
        return {}
    path = root / "ci/test_shards" / FILENAME
    _selection_no_links(root, path)
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or value.keys() != {"schema", "role", "partitions"}
        or value["schema"] != SCHEMA
        or value["role"] != "Derived ratios preserve baseline file totals; not new measurements"
        or not isinstance(value["partitions"], dict)
        or value["partitions"].keys() != OWNERS.keys()
    ):
        raise SystemExit("Invalid finite step5g partition index.")
    result: dict[str, dict[str, float]] = {}
    for owner, (digest, count) in OWNERS.items():
        source = root / owner
        _selection_no_links(root, source)
        row = value["partitions"][owner]
        if (
            hashlib.sha256(source.read_bytes()).hexdigest() != digest
            or not isinstance(row, dict)
            or row.keys() != {"source_sha256", "nodes", "nodes_sha256", "weights"}
            or row["source_sha256"] != digest
            or not isinstance(row["nodes"], list)
            or len(row["nodes"]) != count
            or any(
                not isinstance(node, str) or not node.startswith(owner + "::")
                for node in row["nodes"]
            )
            or row["nodes"] != sorted(set(row["nodes"]))
            or hashlib.sha256(("\n".join(row["nodes"]) + "\n").encode()).hexdigest()
            != row["nodes_sha256"]
            or not isinstance(row["weights"], dict)
            or row["weights"].keys() != set(row["nodes"])
        ):
            raise SystemExit("Finite step5g source or inventory changed.")
        weights: dict[str, float] = {}
        for node, weight in row["weights"].items():
            if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
                raise SystemExit("Finite step5g weights must be positive finite ratios.")
            weights[node] = float(weight)
        if owner in files:
            result[owner] = weights
    return result


def partition_selectors(root: Path, selectors: set[str]) -> set[str]:
    result = preflight.partition_selectors(root, selectors)
    for owner, weights in partitions(root, result).items():
        result = (result - {owner}) | weights.keys()
    return result


def partition_durations(root: Path, durations: dict[str, float]) -> dict[str, float]:
    result = preflight.partition_durations(root, durations)
    for owner, weights in partitions(root, set(result)).items():
        total = result.pop(owner)
        denominator = math.fsum(weights.values())
        result.update({node: total * value / denominator for node, value in weights.items()})
    return result


def source_metadata(root: Path) -> dict[str, str]:
    path = root / "ci/test_shards" / FILENAME
    return {"file": FILENAME, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_cases(root: Path, cases: dict[str, float]) -> None:
    for owner, weights in partitions(root, {node.split("::", 1)[0] for node in cases}).items():
        actual = {node for node in cases if node.split("::", 1)[0] == owner}
        if actual != weights.keys():
            raise SystemExit("Finite step5g partition differs from complete case inventory.")


def add_metadata(root: Path, summary: dict[str, object], cases: dict[str, float]) -> None:
    validate_cases(root, cases)
    if any(node.split("::", 1)[0] in OWNERS for node in cases):
        summary["step5g_partitions"] = source_metadata(root)


def validate_metadata(root: Path, summary: dict[str, object], cases: dict[str, float]) -> None:
    validate_cases(root, cases)
    if any(node.split("::", 1)[0] in OWNERS for node in cases):
        value = summary.get("step5g_partitions")
        if not isinstance(value, dict) or cast(dict[str, object], value) != source_metadata(root):
            raise SystemExit("Finite step5g partition metadata is missing or changed.")
