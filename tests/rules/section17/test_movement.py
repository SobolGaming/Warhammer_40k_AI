"""17.01 and FAQ39: actual physical transit, restricted blockers and endpoints."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, paths, scenario
from tests.support.section09_fixtures import choose, events, propose, select
from tests.support.section17_fixtures import DEFILER, LORD, PRINCE, SPAWN, movement_scene
from tests.unit_keyword_helpers import with_model_keywords
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("sheet", [PRINCE, DEFILER])
@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("friendly", [False, True])
def test_native_monster_and_vehicle_cross_models_through_public_witness(
    section17_definitions: Section02Definitions,
    sheet: str,
    action: str,
    friendly: bool,
) -> None:
    session, state, unit = movement_scene(section17_definitions, sheet, friendly=friendly)
    assert not unit_within_enemy_engagement_range(
        state=state, unit_instance_id=unit.unit_instance_id
    )
    request = choose(session, select(session, unit), action)
    end = Pose.at(22 if sheet == DEFILER else 18, 10)
    result = propose(session, request, unit, (end,))
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    assert state.battlefield_state is not None
    assert (
        state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[0].pose
        == end
    )
    assert len(events(session, "movement_activation_completed")) == 1
    assert state.movement_phase_state is not None
    assert unit.unit_instance_id in state.movement_phase_state.moved_unit_ids
    # FAQ5: passing through engagement creates no lasting engaged status.
    assert not unit_within_enemy_engagement_range(
        state=state, unit_instance_id=unit.unit_instance_id
    )
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer)


@pytest.mark.parametrize("sheet", [PRINCE, DEFILER])
@pytest.mark.parametrize("friendly", [False, True])
def test_transit_permission_never_allows_ending_on_another_model(
    section17_definitions: Section02Definitions,
    sheet: str,
    friendly: bool,
) -> None:
    session, state, unit = movement_scene(section17_definitions, sheet, friendly=friendly)
    request = choose(session, select(session, unit), "normal_move")
    original = state.battlefield_state
    result = propose(session, request, unit, (Pose.at(16 if sheet == DEFILER else 14, 10),))
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == original
    assert "end_on_model_overlap" in str(result.to_payload())
    assert not events(session, "movement_activation_completed")
    retry = session.lifecycle.decision_controller.queue.pending_requests[0]
    legal = propose(session, retry, unit, (Pose.at(10, 12),), result_id="s17:retry")
    assert legal.status_kind is not LifecycleStatusKind.INVALID, legal
    assert len(events(session, "movement_activation_completed")) == 1


@pytest.mark.parametrize("sheet", [PRINCE, DEFILER, LORD])
@pytest.mark.parametrize("friendly", [False, True])
@pytest.mark.parametrize("blocker_sheet", [PRINCE, DEFILER])
@pytest.mark.parametrize(
    "mode",
    [
        MovementMode.NORMAL,
        MovementMode.ADVANCE,
        MovementMode.CHARGE,
        MovementMode.PILE_IN,
        MovementMode.CONSOLIDATE,
    ],
)
def test_source_move_scope_and_faq39_keep_vehicle_blockers_and_enemy_restrictions(
    section17_definitions: Section02Definitions,
    sheet: str,
    friendly: bool,
    mode: MovementMode,
    blocker_sheet: str,
) -> None:
    d = section17_definitions
    unit = d.unit(sheet)
    mover = geometry(unit, (Pose.at(10, 10),))[0]
    blocker = geometry(d.unit(blocker_sheet, identity="blocker"), (Pose.at(20, 10),))[0]
    displacement = {
        MovementMode.NORMAL: ModelDisplacementKind.NORMAL_MOVE,
        MovementMode.ADVANCE: ModelDisplacementKind.ADVANCE,
        MovementMode.CHARGE: ModelDisplacementKind.CHARGE_MOVE,
        MovementMode.PILE_IN: ModelDisplacementKind.PILE_IN,
        MovementMode.CONSOLIDATE: ModelDisplacementKind.CONSOLIDATE,
    }[mode]
    legality = MovementLegalityContext.from_keywords(
        keywords=unit.own_models[0].keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind=displacement,
    )
    # An intentionally budget-free physical path kernel isolates transit policy;
    # public native budget/decision mutation is exercised separately above.
    path = legality.to_path_validation_context(
        moving_model=mover,
        witness=PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(30, 10))),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        friendly_models=(blocker,) if friendly else (),
        enemy_models=() if friendly else (blocker,),
        friendly_vehicle_monster_model_ids=(blocker.model_id,) if friendly else (),
        enemy_vehicle_monster_model_ids=() if friendly else (blocker.model_id,),
    )
    expected = friendly and (
        sheet == LORD or mode not in (MovementMode.NORMAL, MovementMode.ADVANCE)
    )
    result = path.validate()
    assert result.is_valid is expected, result.violations
    assert PathValidationContext.from_payload(path.to_payload()).validate() == result
    if not expected:
        assert result.violations
    overlap = replace(
        path, witness=PathWitness.for_paths(((mover.model_id, (mover.pose, blocker.pose)),))
    )
    assert not overlap.validate().is_valid


@pytest.mark.parametrize("keyword", ["MONSTER", "VEHICLE"])
@pytest.mark.parametrize("both", [False, True])
def test_physical_model_permission_does_not_promote_a_siblings_keyword(
    section17_definitions: Section02Definitions,
    keyword: str,
    both: bool,
) -> None:
    d = section17_definitions
    unit = d.unit(SPAWN)
    # Explicit heterogeneous Core model-keyword contract, not a native provider.
    unit = replace(
        unit,
        own_models=tuple(
            with_model_keywords(m, keywords=(*m.keywords, keyword)) if i == 0 or both else m
            for i, m in enumerate(unit.own_models)
        ),
    )
    starts = (Pose.at(10, 10), Pose.at(10, 12.5))
    enemy = d.unit(LORD, identity="blocker", army_id="enemy")
    state = native_state(d, unit, starts, enemy=enemy, enemy_poses=(Pose.at(14, 11.25),))
    board = scenario(state)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        path_witness=paths(unit, starts, (Pose.at(18, 10), Pose.at(18, 12.5))),
    )
    assert result.is_valid is both
    if not both:
        assert any(
            v.violation_code == "enemy_model_base_crossed"
            for r in result.path_validation_results
            for v in r.violations
        )


def test_normal_runtime_builder_preserves_core_model_keyword_capabilities(
    section17_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.abilities import movement_capability_flags_from_index

    session, _state, unit = movement_scene(section17_definitions, PRINCE)
    choose(session, select(session, unit), "normal_move")
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    index = bundle.ability_indexes_by_player_id["owner"]
    flags = movement_capability_flags_from_index(index=index, keywords=unit.own_models[0].keywords)
    assert "is_monster" in flags
    assert "blocks_friendly_vehicle_monster_pass_through" in flags
    assert "is_vehicle" not in flags
