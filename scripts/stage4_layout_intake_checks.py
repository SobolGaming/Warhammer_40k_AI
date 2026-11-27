"""Opt-in regressions for the first prospective Movement intake."""

from __future__ import annotations

import pytest

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_layout_intake as intake


@pytest.mark.parametrize(
    ("contact", "controller", "category"),
    [
        ((0, 0), None, "empty"),
        ((2, 1), bench.A, "contested"),
        ((0, 1), bench.B, "held"),
    ],
)
def test_origin_categories_are_defined_by_visible_control(
    contact: tuple[int, int], controller: str | None, category: str
) -> None:
    assert (
        intake.classify_origin(dict(zip((bench.A, bench.B), contact, strict=True)), controller)
        == category
    )


def test_retained_control_without_contact_is_ineligible() -> None:
    with pytest.raises(intake.IntakeGap, match="origin_type_ineligible"):
        intake.classify_origin({bench.A: 0, bench.B: 0}, bench.A)


def test_first_recipe_uses_earliest_unused_diagram() -> None:
    recipe = intake.load_recipe()
    setup, manifest, reserve, used = intake.source_inventory(recipe)
    assert used == [13, 14, 38]
    assert reserve["source_diagram_pages"] == [9]
    assert reserve["trajectory_sha256"] == []
    assert setup.battlefield_layout_id == recipe["layout"]
    assert intake.evaluation.validate_split(manifest) == [
        ["guard"],
        ["layout-c", "shooting"],
        ["west"],
    ]
    with pytest.raises(intake.IntakeGap, match="candidate_page_order"):
        intake.source_inventory({**recipe, "source_page": 10})


@pytest.mark.parametrize(
    ("field", "binding", "component"),
    [
        (
            "trajectory_sha256",
            "fb22f83cbb3890e655fc764abc1cbccd22991f2cb7ad398ec7b6f487ab846398",
            "synthetic-reserve, west",
        ),
        (
            "geometry_sha256",
            "45793e48a681e6d0acd2361798d73f832037d136059a1352859d5ccd82475e32",
            "layout-c, shooting, synthetic-reserve",
        ),
    ],
)
def test_published_development_binding_rejects_reserve_collision(
    field: str, binding: str, component: str
) -> None:
    _, manifest, reserve, _ = intake.source_inventory(intake.load_recipe())
    synthetic = {
        **reserve,
        "id": "synthetic-reserve",
        "source_diagram_pages": [10],
        "scenario_lineage": ["synthetic-scenario"],
        "geometry_families": ["synthetic-geometry"],
        "geometry_sha256": [bench.payload_digest("synthetic board")],
        "trajectory_sha256": [bench.payload_digest("synthetic origin")],
    }
    manifest["families"].append(synthetic)
    assert ["synthetic-reserve"] in intake.evaluation.validate_split(manifest)

    synthetic[field].append(binding)
    with pytest.raises(bench.BenchmarkGap, match=f"crosses a connected component: {component}"):
        intake.evaluation.validate_split(manifest)


def test_frozen_batch_inventory_and_original_page_9() -> None:
    from scripts import stage4_layout_batch as batch

    plan = batch.load_plan()
    original = intake.load_recipe()
    layouts, development, used = intake.development_inventory()
    assert [row["page"] for row in plan["pages"]] == list(range(9, 54))
    assert [
        row["page"] for row in plan["pages"] if row.get("exclude") == "development_diagram"
    ] == used
    assert batch.recipe_for(plan["pages"][0], original) == original
    for row in plan["pages"]:
        if "exclude" in row:
            continue
        recipe = batch.recipe_for(row, original)
        _, candidate = intake.source_candidate(recipe, layouts[recipe["layout"]], development)
        assert candidate["source_diagram_pages"] == [row["page"]]
        assert recipe["native_probe_cap"] == 2
        assert recipe["worker_wall_seconds"] == 180
        assert recipe["seed_namespace"] == "stage4-movement-comparison-v1"


def test_batch_selection_skips_earliest_page_only_when_quotas_require_it() -> None:
    from scripts import stage4_layout_batch as batch

    rows = [
        {"page": page, "pairing": [pair], "component": component, "origin_type": kind}
        for page, pair, component, kind in (
            (9, "a", "A", "empty"),
            (10, "a", "B", "contested"),
            (12, "b", "C", "contested"),
            (15, "c", "D", "held"),
            (18, "d", "E", "held"),
            (21, "e", "F", "empty"),
            (24, "f", "G", "empty"),
            (27, "g", "G", "empty"),
            (30, "h", "H", "empty"),
            (33, "i", "I", "empty"),
        )
    ]
    selected = batch.choose(rows, 8, 2)
    assert selected is not None
    assert [row["page"] for row in selected] == [10, 12, 15, 18, 21, 24, 30, 33]
    assert batch.choose([row for row in rows if row["page"] != 10], 8, 2) is None


def test_batch_overlap_transitively_connects_failed_and_unattempted_candidates() -> None:
    from scripts import stage4_layout_batch as batch

    _, development, first, _ = intake.source_inventory(intake.load_recipe())
    first["trajectory_sha256"] = [bench.payload_digest("first")]
    bridge = {
        **first,
        "id": "reserve-page-10",
        "source_diagram_pages": [10],
        "scenario_lineage": ["bridge"],
        "geometry_families": ["bridge"],
        "geometry_sha256": [development["families"][0]["geometry_sha256"][0]],
    }
    last = {
        **bridge,
        "id": "reserve-page-11",
        "source_diagram_pages": [11],
        "geometry_sha256": [bench.payload_digest("other board")],
        "trajectory_sha256": [],
    }
    assert ["reserve-page-10", "reserve-page-11", "reserve-page-9", "west"] in batch.group_families(
        development, [first, bridge, last]
    )


def test_batch_preserves_origin_types_even_for_failed_native_menus() -> None:
    from scripts import stage4_layout_batch as batch

    receipt: bench.Row = {}
    attempts = [
        {"origin": {"type": "held"}, "status": "eligible"},
        {
            "origin": {"type": "held"},
            "status": "ineligible",
            "reason": "screen_unavailable_under_cap",
        },
    ]
    batch.candidate_disposition(receipt, attempts, None)
    assert receipt == {
        "origin_type": "held",
        "status": "ineligible",
        "reason": "seed_preflight_failed",
    }
    receipt = {}
    attempts[1] = {"origin": {"type": "contested"}, "status": "eligible"}
    batch.candidate_disposition(receipt, attempts, None)
    assert receipt == {"status": "ineligible", "reason": "origin_type_mismatch"}
