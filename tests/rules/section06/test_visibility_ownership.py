"""Observer/target rules-unit ownership and current FAQ63 at real geometry owners."""

from dataclasses import replace
from fractions import Fraction

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, MAULERFIEND, Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, placement, scenario
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.shooting_model_blockers import shooting_dynamic_model_blockers
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.stratagems_geometry import visible_enemy_unit_ids_for_source
from warhammer40k_core.geometry.continuous_visibility import resolve_visibility_pair
from warhammer40k_core.geometry.physical_visibility import (
    BattlefieldVisibilityBounds,
    resolve_physical_any_visibility,
    resolve_physical_any_visibility_uncached,
    resolve_physical_visibility,
)
from warhammer40k_core.geometry.physical_visibility_formulas import decide_physical_any
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism
from warhammer40k_core.geometry.visibility_formulas import ModelDomain


@pytest.mark.parametrize("third_unit", [False, True])
def test_observer_and_target_members_are_excluded_but_other_units_block(
    section06_definitions: Section02Definitions, third_unit: bool
) -> None:
    d = section06_definitions
    observer, target = d.unit(), d.unit(army_id="enemy", identity="target")
    op = tuple(Pose.at(5 + 2 * i, 10) for i in range(5))
    tp = tuple(Pose.at(22 + 2 * i, 10) for i in range(5))
    state = native_state(d, observer, op, enemy=target, enemy_poses=tp)
    if third_unit:
        third = d.unit(MAULERFIEND, army_id="enemy", identity="third")
        state.army_definitions[1] = replace(state.army_definitions[1], units=(target, third))
        assert state.battlefield_state is not None
        board = state.battlefield_state
        state.replace_battlefield_state(
            replace(
                board,
                placed_armies=tuple(
                    replace(
                        a,
                        unit_placements=(
                            *a.unit_placements,
                            placement(third, (Pose.at(17, 10),), enemy=True),
                        ),
                    )
                    if a.player_id == "opponent"
                    else a
                    for a in board.placed_armies
                ),
            )
        )
    blockers = shooting_dynamic_model_blockers(
        scenario=scenario(state),
        observing_unit_id=observer.unit_instance_id,
        target_unit_id=target.unit_instance_id,
    )
    assert not {m.model_id for m in blockers}.intersection(
        (*observer.own_model_ids(), *target.own_model_ids())
    )
    assert len(blockers) == int(third_unit)
    targets = geometry(target, tp, enemy=True)
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        los_cache_key="s06:members",
        observer_model=geometry(observer, op)[0],
        target_models=targets,
        target_model_keywords=tuple(
            (m.model_id, target.own_models[i].keywords) for i, m in enumerate(targets)
        ),
        dynamic_model_blockers=blockers,
    )
    resolve_visibility_pair.cache_clear()
    resolve_physical_visibility.cache_clear()
    assert unit_has_line_of_sight_to_target(
        state=state,
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        observing_unit=observer,
        target_unit_id=target.unit_instance_id,
        placed_alive_models_only=True,
    ) is (not third_unit)
    assert resolve_visibility_pair.cache_info().currsize == 0
    assert resolve_physical_visibility.cache_info().currsize == 0
    witness = context.resolve_line_of_sight()
    assert context.has_line_of_sight() is witness.unit_visible
    assert witness.unit_visible is (not third_unit)
    assert witness.unit_fully_visible is (not third_unit)


def test_unspecified_visible_unit_uses_rule_owner_not_another_friend(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    owner = d.unit(LORD_EXULTANT)
    enemy = d.unit(LORD_EXULTANT, army_id="enemy", identity="enemy")
    friend = d.unit(LORD_EXULTANT, identity="friend")
    state = native_state(d, owner, (Pose.at(10, 10),), enemy=enemy, enemy_poses=(Pose.at(20, 10),))
    state.army_definitions[0] = replace(state.army_definitions[0], units=(owner, friend))
    assert state.battlefield_state is not None
    board = state.battlefield_state
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=15,
        center_y_inches=10,
        width_inches=0.2,
        depth_inches=8,
        display_template_id="s06:wall",
    )
    feature = TerrainFeatureDefinition(
        feature_id="s06:wall",
        feature_kind=TerrainFeatureKind.HILLS_AND_SEALED_BUILDINGS,
        footprint_center_x_inches=15,
        footprint_center_y_inches=10,
        footprint_width_inches=0.2,
        footprint_depth_inches=8,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=15,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.2,
                depth_inches=8,
                height_inches=8,
            ),
        ),
        source_id="constructed:s06:wall",
    )
    state.replace_battlefield_state(
        replace(
            board,
            terrain_features=(feature,),
            placed_armies=tuple(
                replace(
                    a, unit_placements=(*a.unit_placements, placement(friend, (Pose.at(20, 22),)))
                )
                if a.player_id == "owner"
                else a
                for a in board.placed_armies
            ),
        )
    )
    assert (
        visible_enemy_unit_ids_for_source(
            state=state,
            player_id="owner",
            source_unit_instance_id=owner.unit_instance_id,
            range_inches=48,
        )
        == ()
    )

    assert visible_enemy_unit_ids_for_source(
        state=state,
        player_id="owner",
        source_unit_instance_id=friend.unit_instance_id,
        range_inches=48,
    ) == (enemy.unit_instance_id,)
    assert (
        visible_enemy_unit_ids_for_source(
            state=state,
            player_id="opponent",
            source_unit_instance_id=friend.unit_instance_id,
            range_inches=48,
        )
        == ()
    )


@pytest.mark.parametrize("bounded", [False, True])
def test_faq63_incoming_body_part_and_clipped_outgoing_origin(bounded: bool) -> None:
    # Explicit analytic boundary input: supported catalog has no overhanging body
    # measurement. This enters the actual exact physical evaluator, with no
    # setup/movement/miniature certification or synthetic replacement of native data.
    def prism(x0: int, y0: int, x1: int, y1: int) -> VisibilityPrism:
        a, b, c, d = map(Fraction, (x0, y0, x1, y1))
        return VisibilityPrism(
            ((a, b), (c, b), (c, d), (a, d)), Fraction(0), Fraction(2), (a, b, c, d)
        )

    body = prism(2, -3, 4, 3)
    opponent = prism(12, 1, 14, 3)
    wall = prism(8, 0, 9, 12)
    bounds = (
        BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(16), Fraction(12))
        if bounded
        else None
    )
    incoming = resolve_physical_visibility((opponent,), (body,), (wall,), (wall,), bounds)
    outgoing = resolve_physical_visibility((body,), (opponent,), (wall,), (wall,), bounds)
    assert (
        resolve_physical_any_visibility(
            (opponent,), (body,), (wall,), (wall,), bounds
        ).model_visible
        is incoming.model_visible
    )
    assert (
        resolve_physical_any_visibility(
            (body,), (opponent,), (wall,), (wall,), bounds
        ).model_visible
        is outgoing.model_visible
    )
    assert incoming.model_visible
    assert not incoming.model_fully_visible
    assert incoming.clear_corridor is not None
    assert incoming.clear_corridor[1][1] < 0
    assert outgoing.model_visible is (not bounded)
    assert resolve_physical_visibility((body,), (opponent,), (), (), bounds).model_fully_visible
    assert not resolve_physical_visibility(
        (opponent,), (prism(2, 1, 4, 3),), (wall,), (wall,), bounds
    ).model_visible

    def check_boolean_evidence(composite: bool, blocked: bool) -> None:
        def prism(x: int, y: int) -> VisibilityPrism:
            a, b, c, d = map(Fraction, (x, y, x + 1, y + 1))
            return VisibilityPrism(
                ((a, b), (c, b), (c, d), (a, d)), Fraction(0), Fraction(2), (a, b, c, d)
            )

        observers = (prism(0, 0), prism(0, 3)) if composite else (prism(0, 0),)
        targets: tuple[VisibilityPrism, ...] = (
            (prism(8, 0), prism(8, 3)) if composite else (prism(8, 0),)
        )
        blockers = targets if blocked else ()
        bounds = (
            BattlefieldVisibilityBounds(Fraction(1, 2), Fraction(0), Fraction(12), Fraction(12))
            if bounded
            else None
        )
        resolve_physical_visibility.cache_clear()
        resolve_visibility_pair.cache_clear()
        resolve_physical_any_visibility.cache_clear()
        args = (observers, targets, blockers, blockers, bounds)
        evidence = resolve_physical_any_visibility(*args)
        assert evidence == resolve_physical_any_visibility_uncached(*args)
        assert resolve_physical_any_visibility(*args) is evidence
        if composite:
            mixed = resolve_physical_any_visibility(
                observers, targets, targets[:1], targets[:1], bounds
            )
            assert mixed.model_visible
            assert mixed.clear_corridor is not None
            assert targets[-1].contains_point(mixed.clear_corridor[1])
        assert resolve_physical_visibility.cache_info().currsize == 0
        assert resolve_visibility_pair.cache_info().currsize == 0
        assert not hasattr(evidence, "model_fully_visible")
        assert evidence.model_visible is (not blocked)
        if blocked:
            complete = resolve_physical_visibility(*args)
            assert evidence.model_visible is complete.model_visible
            assert evidence.input_fingerprint == complete.input_fingerprint
        else:
            assert (
                decide_physical_any(
                    tuple(map(ModelDomain.from_prism, observers)),
                    tuple(map(ModelDomain.from_prism, targets)),
                    blockers,
                    None if bounds is None else bounds.values,
                )
                is evidence.model_visible
            )
        full_only = resolve_physical_any_visibility(observers, targets, (), observers, bounds)
        clear = resolve_physical_any_visibility(observers, targets, (), (), bounds)
        assert full_only.model_visible is clear.model_visible is True
        assert full_only.input_fingerprint != clear.input_fingerprint
        changed = resolve_physical_any_visibility(observers, targets, (), blockers, bounds)
        assert changed.model_visible
        if blocked:
            assert changed.input_fingerprint != evidence.input_fingerprint
        assert resolve_physical_any_visibility(*args) is evidence

    for composite in (False, True):
        for blocked in (False, True):
            check_boolean_evidence(composite, blocked)
