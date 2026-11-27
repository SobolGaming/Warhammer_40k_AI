"""Validate Stage 4 split manifests and report the sealed development baselines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_policy_target as link
from scripts import stage4_split_objective as split
from scripts import stage4_split_objective_replay as split_replay
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)

SPLIT_SCHEMA = "stage4-unseen-layout-split-v1"
PARTITIONS = {"development", "reserve"}
LINEAGE_FIELDS = {
    "scenario_lineage": "scenario",
    "geometry_families": "geometry_family",
    "geometry_sha256": "geometry",
    "trajectory_sha256": "trajectory",
}
BENCHMARK_SEAL = "e3310a698d615a35e64507ffb9243b2336da88b9c3022ffcc9698551c98568f3"
WEST_SEAL = "85c868540a6b82a0836094d4c51c1d3903a564fb286b97da73b8265c7a65c370"


def _record(value: object, fields: set[str], name: str) -> bench.Row:
    if not isinstance(value, dict) or set(value) != fields:
        raise bench.BenchmarkGap(f"{name} requires exactly {', '.join(sorted(fields))}.")
    return value


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise bench.BenchmarkGap(f"Missing or invalid {name}.")
    return value


def _sha256(value: object, name: str) -> str:
    text = _identifier(value, name)
    bench.require(re.fullmatch(r"[a-f0-9]{64}", text) is not None, f"Invalid {name} SHA-256.")
    return text


def _nonempty_list(value: object, name: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise bench.BenchmarkGap(f"{name} requires a nonempty list.")
    return value


def validate_split(manifest: object) -> list[list[str]]:
    """Validate whole-family assignments before any reserve scoring is considered."""
    data = _record(manifest, {"schema", "layout_release", "families"}, "Stage 4 manifest")
    bench.require(data["schema"] == SPLIT_SCHEMA, "Unknown Stage 4 split schema.")
    release = _record(
        data["layout_release"], {"package", "artifact_sha256", "pdf_sha256"}, "Layout release"
    )
    artifact = event_layouts.battlefield_artifact()
    pdf = artifact.source_pdf_sha256
    bench.require(
        (release["package"], release["artifact_sha256"], release["pdf_sha256"])
        == (artifact.source_package_id, artifact.package_hash, pdf),
        "Manifest names a different Event Companion layout release.",
    )
    source_pages = {layout.source_page for layout in artifact.layouts}
    bench.require(len(source_pages) == len(artifact.layouts), "Ambiguous layout diagram pages.")
    keys_by_family: dict[str, frozenset[tuple[str, str]]] = {}
    partitions: dict[str, str] = {}
    for value in _nonempty_list(data["families"], "families"):
        family = _record(
            value,
            {"id", "partition", "scoring_artifact_sha256", "source_diagram_pages", *LINEAGE_FIELDS},
            "Stage 4 family",
        )
        name = _identifier(family["id"], "family ID")
        partition = _identifier(family["partition"], "partition")
        bench.require(partition in PARTITIONS, f"Unknown Stage 4 partition for {name}.")
        bench.require(name not in partitions, f"Duplicate Stage 4 family {name}.")
        _sha256(family["scoring_artifact_sha256"], f"{name} scoring artifact")
        pages = _nonempty_list(family["source_diagram_pages"], f"{name} diagram pages")
        keys = {link.source_diagram_key(pdf, page) for page in pages}
        bench.require(
            all(page in source_pages for page in pages),
            f"Unknown Stage 4 source diagram page for {name}.",
        )
        for field, namespace in LINEAGE_FIELDS.items():
            check = _sha256 if field.endswith("_sha256") else _identifier
            keys.update(
                (namespace, check(key, f"{name} {field}"))
                for key in _nonempty_list(family[field], f"{name} {field}")
            )
        keys_by_family[name] = frozenset(keys)
        partitions[name] = partition

    bench.require(
        "development" in partitions.values(), "Stage 4 split requires a development comparator."
    )
    groups = link.evaluation_groups(keys_by_family)
    for group in groups:
        bench.require(
            len({partitions[name] for name in group}) == 1,
            f"Stage 4 split crosses a connected component: {', '.join(group)}.",
        )
    return groups


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        bench.require(key not in result, f"Duplicate Stage 4 manifest field {key}.")
        result[key] = value
    return result


def _margin(arm: bench.Row) -> int:
    bench.require(arm["strict_replay"] is True, "A development arm lacks strict replay.")
    a, b = (arm["gain_vp"][player] for player in (bench.A, bench.B))
    return int(a - b)


def development_baselines(
    benchmark: bench.Row, west: bench.Row, layout_c: bench.Row
) -> list[tuple[str, int, int, int]]:
    """Return family, observed horizon round, Hold margin and Screen margin."""
    bench.require(bench.payload_digest(benchmark) == BENCHMARK_SEAL, "Benchmark seal mismatch.")
    bench.require(bench.payload_digest(west) == WEST_SEAL, "West seal mismatch.")
    link.verify_seal(layout_c)
    bench.check_receipt(benchmark)
    west_horizon = tuple(west["horizon"])
    c_horizon = tuple(layout_c["protocol"]["horizon"])
    bench.require(
        west_horizon == tuple(benchmark["horizon"]) == bench.HORIZON
        and c_horizon == split_replay.HORIZON,
        "Stale development comparison horizon.",
    )
    bench.require(
        all(
            receipt["partition"] == "development" and receipt["status"] == "observed"
            for receipt in (west, layout_c)
        ),
        "Expected observed development receipts.",
    )

    west_original = benchmark["fixtures"]["west"]
    bench.require(
        west["group"] == west_original["group"]
        and west["origin"]["checkpoint"] == west_original["origin"][2],
        "West receipts disagree on the paired origin.",
    )
    hold_arm, screen_arm = link.PAIRS[1]
    for arm in (hold_arm, screen_arm):
        bench.require(
            all(
                west["arms"][arm][key] == west_original["arms"][arm][key]
                for key in ("checkpoint", "event_log")
            ),
            "West receipts disagree on a paired endpoint.",
        )
    guard = bench.baseline_scores(benchmark["fixtures"]["guard"])
    west_hold, west_screen = (_margin(west["arms"][arm]) for arm in (hold_arm, screen_arm))
    c_hold, c_screen = (_margin(layout_c["arms"][arm]) for arm in (hold_arm, screen_arm))
    return [
        ("West", west_horizon[0], west_hold, west_screen),
        (
            "Central Guard",
            west_horizon[0],
            guard["baseline_margin_gain"],
            guard["screen_margin_gain"],
        ),
        ("Layout C", c_horizon[0], c_hold, c_screen),
    ]


def baseline_table(rows: list[tuple[str, int, int, int]], *, hindsight: bool = False) -> str:
    columns = ["Development family", "Horizon", "Always Hold", "Always Screen", bench.BASELINE]
    if hindsight:
        columns.append("Hindsight ceiling")
    lines = [
        "Ally follows in every arm. Values are changes in A-minus-B VP from the paired origin.",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for family, round_number, hold, screen in rows:
        # Both movement controls have zero immediate wound swing at these offers.
        values = [family, f"A{round_number} Movement", str(hold), str(screen), str(hold)]
        if hindsight:
            values.append(str(max(hold, screen)))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-split", help="Check a provenance-only manifest.")
    validate.add_argument("manifest", type=Path)
    baselines = commands.add_parser("baselines", help="Summarize the sealed development receipts.")
    baselines.add_argument("--hindsight", action="store_true")
    args = parser.parse_args()
    if args.command == "validate-split":
        manifest = json.loads(
            args.manifest.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
        print(json.dumps({"components": validate_split(manifest)}))
    else:
        benchmark = json.loads(bench.RECEIPT.read_text(encoding="utf-8"))
        west = json.loads(bench.WEST_RECEIPT.read_text(encoding="utf-8"))
        rows = development_baselines(benchmark, west, split.sealed_receipt())
        print(baseline_table(rows, hindsight=args.hindsight))


if __name__ == "__main__":
    main()
