# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from tests.shared.category_migration.order86_table_quarters import (
    BaseShape,
    CircularBase,
    Fraction,
    Model,
    ModelVolume,
    OvalBase,
    Pose,
    RectangularBase,
    _analytic_quarter_oracle,
    _assert_forged_quarter_witnesses_rejected,
    _exact_rectangle_contact_facing,
    hypot,
    inf,
    nextafter,
    pytest,
    replace,
    scoring_table_quarter_id_or_none,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def test_quarter_requires_every_model_in_one_rectangle() -> None:
    model = Model("one", Pose.at(10, 10), CircularBase(0.5), ModelVolume(1))
    other = replace(model, model_id="two", pose=Pose.at(50, 10))
    assert (
        scoring_table_quarter_id_or_none(geometry_models=(model, other), center_x=30, center_y=30)
        is None
    )
    assert scoring_table_quarter_id_or_none(geometry_models=(), center_x=30, center_y=30) is None


@pytest.mark.parametrize("shape", ["oval", "rectangle"])
@pytest.mark.parametrize("facing", [0.0, 17.0, 90.0, 137.0])
@pytest.mark.parametrize("gap", [0.01, 0.02])
def test_rotated_analytic_base_and_hull_edges(shape: str, facing: float, gap: float) -> None:
    import math

    from warhammer40k_core.geometry.base import OvalBase, RectangularBase

    angle = math.radians(facing)
    half_x = (
        math.hypot(2 * math.cos(angle), math.sin(angle))
        if shape == "oval"
        else 2 * abs(math.cos(angle)) + abs(math.sin(angle))
    )
    base = OvalBase(4, 2) if shape == "oval" else RectangularBase(4, 2)
    model = Model(
        "model", Pose.at(30 - half_x - gap, 10, facing_degrees=facing), base, ModelVolume(1)
    )
    assert scoring_table_quarter_id_or_none(geometry_models=(model,), center_x=30, center_y=30) == (
        "table-quarter:south-west" if gap == 0.02 else None
    )


@pytest.mark.parametrize(
    ("x", "facing", "base", "expected"),
    [
        (1.7694605058044857, 101.0, RectangularBase(6.2, 2.4), (False, True, True)),
        (27.775333743981115, 17.0, RectangularBase(4.0, 2.0), (True, False, False)),
    ],
)
def test_r86_001_reported_hulls_and_adjacent_positions(
    x: float, facing: float, base: RectangularBase, expected: tuple[bool, ...]
) -> None:
    for position, qualifies in zip(
        (nextafter(x, -inf), x, nextafter(x, inf)), expected, strict=True
    ):
        model = Model(
            "review-hull", Pose.at(position, 10, facing_degrees=facing), base, ModelVolume(1)
        )
        answer = "table-quarter:south-west" if qualifies else None
        assert _analytic_quarter_oracle(model, 30, 30, 1 / 25.4) == answer
        assert (
            scoring_table_quarter_id_or_none(geometry_models=(model,), center_x=30, center_y=30)
            == answer
        )


@pytest.mark.parametrize(
    ("base", "facing"),
    [
        (RectangularBase(6.2, 2.4), 101.0),
        (RectangularBase(4, 2), 17.0),
        (OvalBase(6.2, 2.4), 101.0),
        (OvalBase(4, 2), 17.0),
    ],
)
@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("border", ["outer-low", "outer-high", "divider-low", "divider-high"])
def test_r86_001_rotated_boundaries_match_exact_shapes_at_adjacent_floats(
    base: BaseShape, facing: float, axis: int, border: str
) -> None:
    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse
    from warhammer40k_core.geometry.visibility_shapes import model_visibility_prism

    centered = Model("border", Pose.at(0, 0, facing_degrees=facing), base, ModelVolume(1))
    footprint = model_visibility_prism(centered).footprint
    if isinstance(footprint, RationalEllipse):
        support = hypot(float(footprint.first_axis[axis]), float(footprint.second_axis[axis]))
    else:
        support = float(max(point[axis] for point in footprint))
    half = Fraction(1 / 25.4) / 2
    boundary = {
        "outer-low": Fraction(0),
        "outer-high": Fraction(60),
        "divider-low": Fraction(30) - half,
        "divider-high": Fraction(30) + half,
    }[border]
    upper = border in {"outer-high", "divider-low"}
    anchor = float(boundary) + (-support if upper else support)
    answers: list[str | None] = []
    for coordinate in (nextafter(anchor, -inf), anchor, nextafter(anchor, inf)):
        pose = (
            Pose.at(coordinate, 10, facing_degrees=facing)
            if axis == 0
            else Pose.at(10, coordinate, facing_degrees=facing)
        )
        model = replace(centered, pose=pose)
        expected = _analytic_quarter_oracle(model, 30, 30, 1 / 25.4)
        answers.append(expected)
        assert (
            wholly_within_table_quarter(
                models=(model,), center_x=30, center_y=30, divider_width_inches=1 / 25.4
            )
            == expected
        )
    assert None in answers
    assert any(answer is not None for answer in answers)


@pytest.mark.parametrize("shape", ["rectangle", "ellipse"])
@pytest.mark.parametrize("border", ["outer", "divider"])
def test_r86_001_exact_rotated_contact_and_neighbors(shape: str, border: str) -> None:
    from math import degrees

    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter
    from warhammer40k_core.geometry.visibility_shapes import rational_rotation

    if shape == "rectangle":
        facing = _exact_rectangle_contact_facing()
        cosine, sine = rational_rotation(facing)
        radius = float(cosine + sine)
        assert Fraction(radius) == cosine + sine
        base: BaseShape = RectangularBase(2, 2)
        center_x = 30.0 if border == "outer" else 4 * radius + 0.125
        center_y = 30.0
        coordinate = radius if border == "outer" else 3 * radius
        assert Fraction(coordinate) == (1 if border == "outer" else 3) * (cosine + sine)
        if border == "divider":
            assert Fraction(center_x) - Fraction(0.125) == 4 * (cosine + sine)
    else:
        # A non-cardinal dyadic rotation with a 3:4:5 ellipse support. This
        # establishes real contact, unlike nominally tangent rounded sqrt values.
        sine = Fraction(1, 2**28)
        facing = degrees(float(sine))
        assert rational_rotation(facing) == (Fraction(1), sine)
        base = OvalBase(6, float(8 * sine))
        radius = float(5 * sine)
        center_x = center_y = 30.0
        coordinate = radius if border == "outer" else 29.875 - radius
    expected = (False, True, True) if border == "outer" else (True, True, False)
    for value, qualifies in zip(
        (nextafter(coordinate, -inf), coordinate, nextafter(coordinate, inf)), expected, strict=True
    ):
        pose = (
            Pose.at(value, 10, facing_degrees=facing)
            if shape == "rectangle"
            else Pose.at(10, value, facing_degrees=facing)
        )
        model = Model("exact-contact", pose, base, ModelVolume(1))
        answer = "table-quarter:south-west" if qualifies else None
        assert _analytic_quarter_oracle(model, center_x, center_y, 0.25) == answer
        assert (
            wholly_within_table_quarter(
                models=(model,), center_x=center_x, center_y=center_y, divider_width_inches=0.25
            )
            == answer
        )


@pytest.mark.parametrize(("x", "y"), [(-10, 10), (70, 10), (30, 10), (10, -10), (10, 70)])
def test_r86_001_ellipse_negative_clearance_is_rejected_before_squaring(x: float, y: float) -> None:
    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter

    model = Model("outside", Pose.at(x, y, facing_degrees=17), OvalBase(4, 2), ModelVolume(1))
    assert (
        wholly_within_table_quarter(
            models=(model,), center_x=30, center_y=30, divider_width_inches=1 / 25.4
        )
        is None
    )


def test_divider_and_centre_exclusion_are_distinct() -> None:
    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter

    model = Model("model", Pose.at(28, 28), CircularBase(0.5), ModelVolume(1))
    assert (
        wholly_within_table_quarter(
            models=(model,), center_x=30, center_y=30, divider_width_inches=1 / 25.4
        )
        == "table-quarter:south-west"
    )
    assert (
        scoring_table_quarter_id_or_none(geometry_models=(model,), center_x=30, center_y=30) is None
    )
    outside_board = replace(model, pose=Pose.at(0.49, 10))
    assert (
        scoring_table_quarter_id_or_none(geometry_models=(outside_board,), center_x=30, center_y=30)
        is None
    )


@pytest.mark.parametrize("gap", [0.01, 0.02])
@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_primary_secondary_scores_restore_views_and_exact_replay(gap: float, player: str) -> None:
    import json

    from tests.phase17n_primary_mission_helpers import phase17n_event_setup
    from tests.phase17n_step6g_secondary_certification_helpers import (
        _drive_secondary_scoring_through_facade,
        secondary_certification_session,
        step6g_tactical_certification_rows,
    )
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.scoring import VictoryPointSourceKind

    row = next(
        r
        for r in step6g_tactical_certification_rows(frozenset({"engage-on-all-fronts"}))
        if r.scoring_player_id == player
    )
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance" if player == "player-a" else "take-and-hold",
        defender_force_disposition_id="take-and-hold" if player == "player-a" else "reconnaissance",
    )

    def positions(state: GameState) -> None:
        battlefield = state.battlefield_state
        assert battlefield is not None
        unit = next(
            u
            for a in state.army_definitions
            if a.player_id == player
            for u in a.units
            if "intercessor-unit" in u.unit_instance_id
        )
        placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
        radius = unit.own_models[0].geometry.base_shape().max_radius()
        # Keep one model near the north-west divider, with its squad extending west.
        x = battlefield.battlefield_width_inches / 2 - radius - gap
        y = battlefield.battlefield_depth_inches * 0.75
        state.battlefield_state = battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    replace(p, pose=Pose.at(x - i * 1.5, y))
                    for i, p in enumerate(placement.model_placements)
                )
            )
        )

    session, _, _ = secondary_certification_session(
        row, mission_setup=setup, prepare_positions=positions
    )
    _drive_secondary_scoring_through_facade(session, row=row, score_tactical=True)
    state = session.lifecycle.state
    assert state is not None
    ledger = state.victory_point_ledger_for_player(player)
    secondary = next(
        t
        for t in ledger.transactions
        if t.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
        and t.source_id == "engage-on-all-fronts"
    )
    primary = next(
        t
        for t in ledger.transactions
        if isinstance(t.metadata, dict)
        and str(t.metadata.get("scoring_rule_id", "")).startswith("reconnaissance-sweep-")
    )
    assert secondary.amount == (3 if gap == 0.01 else 5)
    assert primary.amount == (3 if gap == 0.01 else 6)
    occupancy = next(
        e.occupancy
        for e in state.secondary_scoring_state_evidence_records
        if e.scoring_player_id == player
    )
    assert occupancy is not None
    assert len(occupancy.presence_quarter_ids) == (3 if gap == 0.01 else 4)
    if gap == 0.01:
        _assert_forged_quarter_witnesses_rejected(state, player)
    payload = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(payload)))
    assert restored.to_persistence_payload() == payload
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        events = restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert events == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        public = json.dumps(events)
        assert "table_quarter_unit_witnesses" not in public
        assert "presence_quarter_ids" not in public
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order86")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    ("center_x", "center_y", "width"),
    [(0, 30, 1), (30, 0, 1), (30, 30, 0), (30, 30, -1), (0.01, 30, 1)],
)
def test_invalid_quarter_dimensions_fail_closed(
    center_x: float, center_y: float, width: float
) -> None:
    from warhammer40k_core.geometry.pose import GeometryError
    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter

    with pytest.raises(GeometryError, match="positive rectangles"):
        wholly_within_table_quarter(
            models=(), center_x=center_x, center_y=center_y, divider_width_inches=width
        )


def test_source_artifact_rejects_changed_divider_bytes() -> None:
    from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_table_quarters_2026_09 as source,
    )

    raw = package_artifact_bytes(source.__name__, "artifacts/package.json")
    assert source.validate_source_artifact_bytes(raw).divider_width_mm == 1.0
    with pytest.raises(source.TableQuartersSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(
            raw.replace(b'"divider_width_mm": 1.0', b'"divider_width_mm": 0.0')
        )
