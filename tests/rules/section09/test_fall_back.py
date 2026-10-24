"""09.07 and both 09.07.01 nodes: modes, hazard consequences and FAQ13."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, scenario
from tests.support.section09_fixtures import (
    choose,
    events,
    finish_hazard_choices,
    movement_case,
    propose,
    select,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_desperate_escape import (
    battle_shocked_roll_modifiers_for_record,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phases.movement import (
    DesperateEscapeRoll,
    DesperateEscapeRollPayload,
    FallBackModeKind,
    resolve_fall_back_move,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("shocked", [False, True])
@pytest.mark.parametrize(
    "mode", [FallBackModeKind.ORDERED_RETREAT, FallBackModeKind.DESPERATE_ESCAPE]
)
def test_selected_desperate_mode_requests_exactly_one_hazard_per_model(
    section09_definitions: Section02Definitions,
    shocked: bool,
    mode: FallBackModeKind,
) -> None:
    unit = section09_definitions.unit("000004090")
    state = native_state(section09_definitions, unit)
    board = scenario(state)
    starts = grid(unit)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=mode,
        path_witness=paths(
            unit, starts, tuple(Pose.at(p.position.x, p.position.y - 4) for p in starts)
        ),
        battle_shocked_unit_ids=(unit.unit_instance_id,) if shocked else (),
    )
    assert result.is_valid
    expected = len(unit.own_models) if shocked or mode is FallBackModeKind.DESPERATE_ESCAPE else 0
    assert len(result.desperate_escape_requirements) == expected
    assert len({r.model_instance_id for r in result.desperate_escape_requirements}) == expected
    for requirement in result.desperate_escape_requirements:
        assert requirement.roll_spec().expression.quantity == 1
        assert requirement.roll_spec().expression.sides == 6


@pytest.mark.parametrize("face", range(1, 7))
@pytest.mark.parametrize("penalty", [0, -1])
def test_desperate_escape_hazard_faces_use_the_modified_value(
    section09_definitions: Section02Definitions,
    face: int,
    penalty: int,
) -> None:
    unit = section09_definitions.unit("000004090")
    state = native_state(section09_definitions, unit)
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        path_witness=paths(unit, grid(unit), (Pose.at(10, 6), Pose.at(12, 6))),
    )
    requirement = result.desperate_escape_requirements[0]
    # Constructed already-authorized modifier contract. Native Bane source is tested below.
    modifiers = (
        (
            RollModifier(
                modifier_id="constructed:penalty", source_id="constructed:source", operand=penalty
            ),
        )
        if penalty
        else ()
    )
    roll = DesperateEscapeRoll.from_roll_state(
        requirement=requirement,
        roll_state=DiceRollManager(state.game_id).roll_fixed(requirement.roll_spec(), (face,)),
        roll_modifiers=modifiers,
    )
    assert roll.value == max(1, face + penalty)
    assert roll.is_failed is (face + penalty <= 2)
    assert DesperateEscapeRoll.from_payload(roll.to_payload()) == roll


@pytest.mark.parametrize("shocked", [False, True])
def test_native_bane_of_cowards_penalty_applies_only_when_shocked(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    catalog = section09_definitions.package.army_catalog
    native = section09_definitions.unit("000001114")
    ability = next(a for a in native.datasheet_abilities if a.name == "Bane of Cowards")
    record = next(
        r
        for r in catalog_ability_records_from_catalog(catalog)
        if r.definition.source_id == ability.source_id
    )
    modifiers = battle_shocked_roll_modifiers_for_record(
        record=record,
        target_unit_instance_id="section02:subject",
        battle_shocked_unit_ids=("section02:subject",) if shocked else (),
    )
    assert len(modifiers) == int(shocked)
    if shocked:
        assert modifiers[0].operand == -1
        assert modifiers[0].source_id == ability.source_id


@pytest.mark.parametrize("mode", ["ordered_retreat", "desperate_escape"])
def test_only_desperate_escape_can_cross_enemy_models_but_both_must_end_unengaged(
    section09_definitions: Section02Definitions,
    mode: str,
) -> None:
    unit = section09_definitions.unit("000004090")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    state = native_state(
        section09_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13.8), Pose.at(12.5, 13.8)),
    )
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=FallBackModeKind(mode),
        path_witness=paths(unit, starts, (Pose.at(10, 18), Pose.at(12.5, 18))),
    )
    assert result.is_valid is (mode == "desperate_escape")


@pytest.mark.parametrize(
    "mode", [FallBackModeKind.ORDERED_RETREAT, FallBackModeKind.DESPERATE_ESCAPE]
)
def test_fall_back_cannot_finish_still_engaged(
    section09_definitions: Section02Definitions,
    mode: FallBackModeKind,
) -> None:
    unit = section09_definitions.unit("000004090")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    state = native_state(
        section09_definitions, unit, enemy=enemy, enemy_poses=(Pose.at(10, 13.8), Pose.at(12, 13.8))
    )
    board = scenario(state)
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        fall_back_mode=mode,
        path_witness=paths(unit, grid(unit), grid(unit)),
    )
    assert not result.is_valid
    assert any(
        v.violation_code == "enemy_engagement_range_end_forbidden"
        for r in result.path_validation_results
        for v in r.violations
    )


@pytest.mark.parametrize("shocked", [False, True])
def test_failed_escape_hazards_inflict_mortals_instead_of_removing_native_multiwound_models(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "section09-hazard-consequence"
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    rolls = events(session, "desperate_escape_roll_resolved")
    assert len(rolls) == 2
    failed = sum(
        int(
            DesperateEscapeRoll.from_payload(
                cast(DesperateEscapeRollPayload, r["desperate_escape_roll"])
            ).is_failed
        )
        for r in rolls
    )
    assert failed > 0, "This retained seed must exercise a failed hazard."
    # Retained baseline measured the legacy whole-model choice. The corrected
    # consumer uses native Section06 allocation choices; expectations stay exact.
    finish_hazard_choices(session, status)
    assert state.battlefield_state is not None
    assert set(unit.own_model_ids()).issubset(state.battlefield_state.placed_model_ids())
    current = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    assert (
        sum(m.current_wounds for m in current.alive_models())
        == sum(m.initial_wounds for m in unit.own_models) - failed
    )


@pytest.mark.parametrize("shocked", [False, True])
def test_all_escape_hazards_are_rolled_as_one_simultaneous_batch(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    # Simultaneous means all dice precede any consequence or player choice; it
    # does not prescribe the number of internal RNG journal records.
    records = session.lifecycle.decision_controller.event_log.records
    indices = [
        i
        for i, e in enumerate(records)
        if e.event_type == "dice_rolled" and "desperate_escape" in str(e.payload)
    ]
    assert indices
    assert not any(
        e.event_type
        in {
            "decision_requested",
            "model_destroyed",
            "mortal_wound_applied",
            "movement_activation_completed",
        }
        for e in records[indices[0] + 1 : indices[-1]]
    )
    assert len(events(session, "desperate_escape_roll_resolved")) == 2


@pytest.mark.parametrize(
    ("mode", "shocked"),
    [
        (FallBackModeKind.ORDERED_RETREAT, False),
        (FallBackModeKind.DESPERATE_ESCAPE, False),
        (FallBackModeKind.DESPERATE_ESCAPE, True),
    ],
)
def test_faq13_native_auto_pass_permission_covers_desperate_mode_hazards(
    section09_definitions: Section02Definitions,
    mode: FallBackModeKind,
    shocked: bool,
) -> None:
    unit = section09_definitions.unit("000000969")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    state = native_state(
        section09_definitions,
        unit,
        (Pose.at(20, 10),),
        enemy=enemy,
        enemy_poses=(Pose.at(20, 14), Pose.at(22.5, 14)),
    )
    board = scenario(state)
    index = AbilityCatalogIndex.from_records(
        catalog_ability_records_from_catalog(section09_definitions.package.army_catalog)
    )
    result = resolve_fall_back_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        ability_index=index,
        fall_back_mode=mode,
        battle_shocked_unit_ids=(unit.unit_instance_id,) if shocked else (),
        path_witness=paths(unit, (Pose.at(20, 10),), (Pose.at(20, 22),)),
    )
    assert result.is_valid, result.to_payload()
    # Native Scuttling Walker auto-pass is consumed, not injected into the tested
    # function. FAQ13 identifies these hazards as the auto-passed tests.
    assert result.desperate_escape_requirements == ()


@pytest.mark.parametrize("shocked", [False, True])
def test_voluntary_escape_tests_battle_shock_after_moving_only_if_not_already_shocked(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "section09-hazard-consequence"
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    finish_hazard_choices(session, status)
    assert state.battlefield_state is not None
    surviving = set(unit.own_model_ids()).intersection(state.battlefield_state.placed_model_ids())
    assert surviving, "Retained deterministic scene must leave a unit for its after-move rule."
    assert len(events(session, "desperate_escape_battle_shock_resolved")) == int(not shocked)
    if not shocked:
        types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
        assert (
            types.index("fall_back_move_applied")
            < types.index("desperate_escape_battle_shock_resolved")
            < types.index("movement_activation_completed")
        )
