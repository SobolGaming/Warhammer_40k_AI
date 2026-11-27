"""Opt-in checks for Stage 4 layout isolation and descriptive baselines."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_evaluation as evaluation
from scripts import stage4_policy_target as link
from scripts.stage4_split_objective import sealed_receipt


def _family(name: str, page: int, *, partition: str = "development") -> bench.Row:
    digest = bench.payload_digest
    return {
        "id": name,
        "partition": partition,
        "scoring_artifact_sha256": digest("shared scoring package"),
        "source_diagram_pages": [page],
        "scenario_lineage": [f"scenario-{name}"],
        "geometry_families": [f"geometry-{name}"],
        "geometry_sha256": [digest(["footprints", name])],
        "trajectory_sha256": [digest(["origin", name]), digest(["endpoint", name])],
    }


def _manifest(*families: bench.Row) -> bench.Row:
    artifact = evaluation.event_layouts.battlefield_artifact()
    return {
        "schema": evaluation.SPLIT_SCHEMA,
        "layout_release": {
            "package": artifact.source_package_id,
            "artifact_sha256": artifact.package_hash,
            "pdf_sha256": artifact.source_pdf_sha256,
        },
        "families": list(families),
    }


def test_independent_diagrams_can_split_under_shared_package_hashes() -> None:
    # Synthetic assignments exercise the contract on pages already seen in development.
    manifest = _manifest(_family("a", 13), _family("b", 14, partition="reserve"))
    assert evaluation.validate_split(manifest) == [["a"], ["b"]]


@pytest.mark.parametrize(
    "bridge", ["source_diagram_pages", "scenario_lineage", "geometry_families", "geometry_sha256"]
)
def test_reuse_and_shared_trajectory_join_families_transitively(bridge: str) -> None:
    original = _family("a", 13)
    variant = _family("b", 14)
    continuation = _family("c", 38)
    variant[bridge] += original[bridge]
    continuation["trajectory_sha256"].append(variant["trajectory_sha256"][-1])
    manifest = _manifest(continuation, original, variant)
    assert evaluation.validate_split(manifest) == [["a", "b", "c"]]
    continuation["partition"] = "reserve"
    with pytest.raises(bench.BenchmarkGap, match="crosses a connected component: a, b, c"):
        evaluation.validate_split(manifest)


@pytest.mark.parametrize(
    "field", ["scoring_artifact_sha256", "source_diagram_pages", *evaluation.LINEAGE_FIELDS]
)
def test_missing_family_provenance_fails_closed(field: str) -> None:
    family = _family("a", 13)
    del family[field]
    with pytest.raises(bench.BenchmarkGap, match=field):
        evaluation.validate_split(_manifest(family))


def test_arms_seeds_and_responses_do_not_get_independent_assignments() -> None:
    family = _family("a", 13)
    sibling = {**family, "partition": "reserve"}
    with pytest.raises(bench.BenchmarkGap, match="Duplicate Stage 4 family"):
        evaluation.validate_split(_manifest(family, sibling))

    for field in ("arms", "seed_partitions", "response_partitions"):
        with pytest.raises(bench.BenchmarkGap, match="Stage 4 family requires exactly"):
            evaluation.validate_split(_manifest({**family, field: {"variant": "reserve"}}))


def test_missing_or_unrecognized_source_fails_closed() -> None:
    data = _manifest(_family("a", 13))
    release = data["layout_release"]
    artifact = release.pop("artifact_sha256")
    with pytest.raises(bench.BenchmarkGap, match="Layout release requires exactly"):
        evaluation.validate_split(data)
    release["artifact_sha256"] = "f" * 64
    with pytest.raises(bench.BenchmarkGap, match="different Event Companion layout release"):
        evaluation.validate_split(data)
    release["artifact_sha256"] = artifact
    data["families"][0]["source_diagram_pages"] = [999]
    with pytest.raises(bench.BenchmarkGap, match="Unknown Stage 4 source diagram page"):
        evaluation.validate_split(data)
    data["families"][0]["source_diagram_pages"] = [13]
    data["families"][0]["trajectory_sha256"] = []
    with pytest.raises(bench.BenchmarkGap, match="trajectory_sha256 requires a nonempty list"):
        evaluation.validate_split(data)


def test_reserve_requires_development_comparator() -> None:
    with pytest.raises(bench.BenchmarkGap, match="requires a development comparator"):
        evaluation.validate_split(_manifest(_family("a", 13, partition="reserve")))


def test_duplicate_json_fields_cannot_override_partitions() -> None:
    with pytest.raises(bench.BenchmarkGap, match="Duplicate Stage 4 manifest field partition"):
        json.loads(
            '{"partition":"development","partition":"reserve"}',
            object_pairs_hook=evaluation._unique_object,
        )


@pytest.fixture
def receipts() -> tuple[bench.Row, bench.Row, bench.Row]:
    return (
        json.loads(bench.RECEIPT.read_text(encoding="utf-8")),
        json.loads(bench.WEST_RECEIPT.read_text(encoding="utf-8")),
        sealed_receipt(),
    )


def test_paired_baselines_and_guard_reversal(
    receipts: tuple[bench.Row, bench.Row, bench.Row],
) -> None:
    rows = evaluation.development_baselines(*receipts)
    assert rows == [("West", 4, -3, 5), ("Central Guard", 4, 13, 5), ("Layout C", 3, 0, 5)]
    assert [screen - hold for _, _, hold, screen in rows] == [8, -8, 5]
    assert "Hindsight ceiling" not in evaluation.baseline_table(rows)
    assert evaluation.baseline_table(rows, hindsight=True).splitlines()[-3:] == [
        "| West | A4 Movement | -3 | 5 | -3 | 5 |",
        "| Central Guard | A4 Movement | 13 | 5 | 13 | 13 |",
        "| Layout C | A3 Movement | 0 | 5 | 0 | 5 |",
    ]


def test_layout_c_link_uses_the_manifest_diagram_identity() -> None:
    source = sealed_receipt()["protocol"]["layout_source"]
    manifest = _manifest(_family("a", 38), _family("b", 14, partition="reserve"))
    assert link.source_diagram_key(source["pdf_sha256"], source["page"]) == link.source_diagram_key(
        manifest["layout_release"]["pdf_sha256"], manifest["families"][0]["source_diagram_pages"][0]
    )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_receipt_horizon_drift_fails_closed(
    receipts: tuple[bench.Row, bench.Row, bench.Row], index: int
) -> None:
    changed = deepcopy(receipts)
    protocol = changed[index] if index < 2 else changed[index]["protocol"]
    protocol["horizon"][0] += 1
    with pytest.raises(bench.BenchmarkGap, match="seal"):
        evaluation.development_baselines(*changed)
