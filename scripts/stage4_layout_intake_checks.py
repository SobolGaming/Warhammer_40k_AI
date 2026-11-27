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
