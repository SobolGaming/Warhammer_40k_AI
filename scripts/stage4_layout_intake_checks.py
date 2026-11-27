"""Opt-in regressions for the first prospective Movement intake."""

from __future__ import annotations

from pathlib import Path

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


def test_batch_can_revisit_first_pairing_at_last_page() -> None:
    from scripts import stage4_layout_batch as batch

    rows = [
        {"page": page, "pairing": [pair], "component": page, "origin_type": kind}
        for page, (pair, kind) in enumerate(
            (
                ("P", "empty"),
                ("A", "empty"),
                ("B", "empty"),
                ("C", "contested"),
                ("D", "contested"),
                ("E", "held"),
                ("F", "empty"),
                ("G", "contested"),
                ("P", "held"),
            ),
            start=9,
        )
    ]
    assert batch.choose(rows, 8, 2) == rows[1:]


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


def test_page_9_screen_probe_uses_native_child_fork() -> None:
    from hashlib import sha256

    recipe = intake.load_recipe()
    setup, _, _, _ = intake.source_inventory(recipe)
    seed = sha256(f"{recipe['seed_namespace']}/1".encode()).hexdigest()
    proof = intake.preflight(recipe, setup, seed)
    assert proof["origin"]["type"] == "empty"
    assert proof["strict_restore_and_replay"]
    assert proof["menu"]["hold"] == "accepted"
    assert proof["menu"]["probes"] == [{"id": proof["menu"]["selected_screen"], "violation": None}]


def test_receipt_verification_rejects_an_omitted_no_origin_bridge() -> None:
    from scripts import stage4_layout_batch as batch

    _, development, candidate, _ = intake.source_inventory(intake.load_recipe())
    candidate["trajectory_sha256"] = [bench.payload_digest("synthetic admitted origin")]
    bridge = {
        **candidate,
        "id": "reserve-page-10",
        "source_diagram_pages": [10],
        "geometry_sha256": [development["families"][0]["geometry_sha256"][0]],
        "trajectory_sha256": [],
    }
    pinned = {family["id"]: family for family in (candidate, bridge)}
    pages = [
        {
            "page": 9,
            "family_id": candidate["id"],
            "pairing": ["take-and-hold", "take-and-hold"],
            "origin_type": "empty",
            "status": "provisionally_eligible",
        },
        {"page": 10, "family_id": bridge["id"], "status": "ineligible"},
    ]
    reduced = {**development, "families": [*development["families"], candidate]}
    reduced_components = intake.evaluation.validate_split(reduced)
    assert [candidate["id"]] in reduced_components
    with pytest.raises(intake.IntakeGap, match="full_provenance_graph_mismatch"):
        batch.analyze(development, pinned, pages, expected_components=reduced_components)
    assert pages[0]["status"] == "provisionally_eligible"

    analysis = batch.analyze(development, pinned, pages)
    assert [bridge["id"], candidate["id"], "west"] in analysis["components"]
    assert pages[0]["reason"] == "development_component_overlap"
    assert analysis["qualified_counts"] == dict.fromkeys(batch.TYPES, 0)


@pytest.mark.parametrize("alias", ["original", "symlink", "hardlink"])
def test_verification_rejects_scored_receipts_before_reading(
    alias: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from os import link

    from scripts import stage4_layout_batch as batch

    scored = batch.HISTORICAL_SCORED_RECEIPTS[0]
    path = scored
    if alias == "symlink":
        path = tmp_path / "preflight.json"
        try:
            path.symlink_to(scored)
        except OSError:
            pytest.skip("Creating a symbolic link is unavailable on this platform.")
    if alias == "hardlink":
        path = tmp_path / "preflight.json"
        try:
            link(scored, path)
        except OSError:
            pytest.skip("Creating a hard link is unavailable on this volume.")

    def forbid_read(_path: Path) -> bytes:
        raise AssertionError("Verifier read a historical scored receipt")

    monkeypatch.setattr(Path, "read_bytes", forbid_read)
    with pytest.raises(intake.IntakeGap, match="historical_scored_receipt_forbidden"):
        batch.verify_file(path)


def test_outcome_blind_cli_rejects_historical_receipt_without_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from scripts import stage4_layout_batch as batch

    def forbid_read(_path: Path, **_kwargs: object) -> str:
        raise AssertionError("Verifier entered a scored receipt reader")

    monkeypatch.setattr(Path, "read_text", forbid_read)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4_benchmark_entry",
            "--layout-intake-verify",
            str(batch.HISTORICAL_SCORED_RECEIPTS[2]),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        bench.main()
    assert exc.value.code == 2
    assert "historical_scored_receipt_forbidden" in capsys.readouterr().err


def test_batch_round_trip_preserves_wall_cap_after_development_overlap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    from hashlib import sha256

    from scripts import stage4_layout_batch as batch

    now = 0.0
    recipe = intake.load_recipe()

    def fake_preflight(page: int, cap: float) -> tuple[list[bench.Row], str | None]:
        nonlocal now
        assert page < 50
        now += min(cap, 84)
        attempts = [
            {
                "seed_index": index,
                "startup_seed_hex": sha256(
                    f"{recipe['seed_namespace']}/{index}".encode()
                ).hexdigest(),
                "status": "ineligible",
            }
            for index in (1, 2)
        ]
        if page not in (9, 15):
            return attempts, None
        for attempt in attempts:
            attempt.update(
                a2_origin_reached=True,
                strict_restore_and_replay=True,
                origin={
                    "type": "empty",
                    "controller": None,
                    "visible_contact_oc": {bench.A: 0, bench.B: 0},
                },
                event_prefix_sha256=bench.payload_digest(f"event {page}"),
                decision_prefix_sha256=bench.payload_digest(f"decision {page}"),
                origin_sha256=bench.payload_digest(f"origin {page}"),
                status="origin_verified",
            )
        if page == 15:
            attempts[0]["origin_sha256"] = intake.DEVELOPMENT_ORIGINS["west"][0]
            return attempts[:1], "preflight_wall_cap"
        for attempt in attempts:
            attempt.update(
                status="eligible",
                menu={
                    "actor_id": bench.A,
                    "issued_options": [bench.HOLD, bench.NORMAL],
                    "hold": "accepted",
                    "eligible_candidates": ["synthetic-screen"],
                    "selected_screen": "synthetic-screen",
                    "probes": [{"id": "synthetic-screen", "violation": None}],
                },
            )
        return attempts, None

    monkeypatch.setattr(batch, "monotonic", lambda: now)
    monkeypatch.setattr(batch, "preflight_page", fake_preflight)
    batch.run()
    receipt = json.loads(capsys.readouterr().out)
    by_page = {page["page"]: page for page in receipt["pages"]}
    assert by_page[15]["reason"] == by_page[50]["reason"] == "development_component_overlap"
    assert by_page[15]["preflight_disposition"] == "preflight_wall_cap"
    assert by_page[50]["preflight_disposition"] == "batch_wall_cap"
    assert "attempts" not in by_page[50]
    assert ["reserve-page-15", "reserve-page-50", "west"] in receipt["components"]

    verification = batch.verify_receipt(receipt)
    assert verification["provenance_vertices"] == 37
    assert verification["qualified_counts"] == {"empty": 1, "contested": 0, "held": 0}
    assert verification["proposed_pages"] == []

    # The earlier producer did not write the execution disposition.
    for page in receipt["pages"]:
        page.pop("preflight_disposition", None)
    assert batch.verify_receipt(receipt) == verification
