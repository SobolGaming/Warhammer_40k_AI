"""Core14 player totals, physical ownership, and controlling rules units."""

import json
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from tests.support.section09_fixtures import add_unit
from tests.support.section14_fixtures import context, objective_state
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    resolve_objective_control,
)
from warhammer40k_core.engine.unit_objective_control import current_unit_objective_control
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("x", "enemy_x", "expected"),
    [(30, 40, None), (10, 30, "owner"), (30, 10, "opponent"), (10, 10, None)],
)
def test_native_player_scores_gain_and_tie(
    section14_definitions: Section02Definitions, x: float, enemy_x: float, expected: str | None
) -> None:
    state, unit, enemy = objective_state(section14_definitions, x=x, enemy_x=enemy_x)
    before = state.to_payload()
    assert state.objective_control_records == []  # no initial controller
    record = resolve_objective_control(context(state))
    result = record.results[0]
    assert result.controlled_by_player_id == expected
    if x == enemy_x == 10:
        assert result.status is ObjectiveControlStatus.CONTESTED
        assert len(result.scores) == 2
        assert result.scores[0].score == result.scores[1].score
    elif expected is None:
        assert result.status is ObjectiveControlStatus.UNCONTROLLED
    for contributor in result.contributors:
        physical = unit if contributor.player_id == "owner" else enemy
        assert contributor.unit_instance_id == physical.unit_instance_id
        assert contributor.model_instance_id in physical.own_model_ids()
        assert (
            contributor.effective_objective_control
            == physical.own_models[0].characteristic(Characteristic.OBJECTIVE_CONTROL).final
        )
    assert (
        ObjectiveControlRecord.from_payload(json.loads(json.dumps(record.to_payload()))) == record
    )
    assert state.to_payload() == before


def test_multiple_native_models_and_units_sum_only_in_range_members(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = objective_state(section14_definitions, subject_sheet=AVENGERS, enemy_x=10)
    support = section14_definitions.unit("000004078", identity="support")
    add_unit(state, support, (Pose.at(10, 12),))
    result = resolve_objective_control(context(state)).results[0]
    rows = tuple(c for c in result.contributors if c.player_id == "owner")
    assert 1 < len(rows) < len(unit.own_models) + len(support.own_models)
    assert {r.unit_instance_id for r in rows} == {unit.unit_instance_id, support.unit_instance_id}
    assert next(s.score for s in result.scores if s.player_id == "owner") == sum(
        r.effective_objective_control for r in rows
    )
    assert result.controlled_by_player_id == "owner"


def test_battle_shock_zeroes_only_affected_physical_units(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = objective_state(section14_definitions, enemy_x=10)
    # Constructed already-shocked checkpoint; the real shock application lifecycle
    # is covered in Section08. No invented datasheet ability or roll is used here.
    result = resolve_objective_control(
        replace(context(state), battle_shocked_unit_ids=(unit.unit_instance_id,))
    ).results[0]
    friendly = next(c for c in result.contributors if c.player_id == "owner")
    enemy = next(c for c in result.contributors if c.player_id == "opponent")
    assert friendly.battle_shocked
    assert friendly.effective_objective_control == 0
    assert not enemy.battle_shocked
    assert enemy.effective_objective_control > 0
    assert result.controlled_by_player_id == "opponent"


@pytest.mark.parametrize("positive_outside", [False, True])
def test_controlling_unit_can_use_positive_member_outside_range_and_attached_owner(
    section14_definitions: Section02Definitions, positive_outside: bool
) -> None:
    state, body, _ = objective_state(section14_definitions, subject_sheet=AVENGERS)
    # Constructed mixed-OC checkpoint retains every native ID and envelope.
    body = replace(
        body,
        own_models=tuple(
            replace(
                m,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 0)
                    if v.characteristic is Characteristic.OBJECTIVE_CONTROL
                    else v
                    for v in m.characteristics
                ),
            )
            for m in body.own_models
        ),
    )
    state.army_definitions[0] = replace(state.army_definitions[0], units=(body,))
    leader = section14_definitions.unit("000004078", identity="leader")
    support = section14_definitions.unit("000004078", identity="support")
    add_unit(state, support, (Pose.at(10, 12),))
    if positive_outside:
        add_unit(state, leader, (Pose.at(30, 12),))
        formation = AttachedUnitFormation(
            "attached-unit:section02:s14",
            body.unit_instance_id,
            (leader.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((body.unit_instance_id, leader.unit_instance_id))
            ),
            source_id="constructed:s14:attachment-checkpoint",
            attachment_source_ids=("constructed:s14:attachment-checkpoint",),
        )
        state.army_definitions[:] = [
            replace(a, attached_units=(formation,)) if a.player_id == "owner" else a
            for a in state.army_definitions
        ]
    result = resolve_objective_control(context(state)).results[0]
    assert result.controlled_by_player_id == "owner"
    assert all(
        c.effective_objective_control == 0
        for c in result.contributors
        if c.unit_instance_id == body.unit_instance_id
    )
    control = current_unit_objective_control(state=state, unit_instance_id=body.unit_instance_id)
    assert control.within_range(result)
    assert control.controls(result) is positive_outside
    assert not control.controls(replace(result, contributors=()))
    if positive_outside:
        other = current_unit_objective_control(
            state=state, unit_instance_id=leader.unit_instance_id
        )
        assert other == control
        assert other.controls(result)
    assert current_unit_objective_control(
        state=state, unit_instance_id=support.unit_instance_id
    ).controls(result)


def test_faq60_and_61_same_native_model_and_unit_control_two_objectives(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = objective_state(section14_definitions)
    markers = tuple(
        ObjectiveMarker(f"s14:objective:{i}", f"Objective{i}", x, 10) for i, x in enumerate((7, 13))
    )
    results = resolve_objective_control(context(state, *markers)).results
    oc = unit.own_models[0].characteristic(Characteristic.OBJECTIVE_CONTROL).final
    assert len(results) == 2
    assert all(r.controlled_by_player_id == "owner" for r in results)
    assert all(
        [(c.model_instance_id, c.effective_objective_control) for c in r.contributors]
        == [(unit.own_model_ids()[0], oc)]
        for r in results
    )
    control = current_unit_objective_control(state=state, unit_instance_id=unit.unit_instance_id)
    assert all(control.controls(r) for r in results)


def test_definitions_and_fresh_mutable_objective_graphs_are_isolated(
    section14_definitions: Section02Definitions,
) -> None:
    first, unit, _ = objective_state(section14_definitions)
    second, other, _ = objective_state(section14_definitions)
    before = second.to_payload()
    first.battle_shocked_unit_ids.append(unit.unit_instance_id)
    first.objective_control_records.append(resolve_objective_control(context(first)))
    assert second.to_payload() == before
    assert other.own_models[0] is not unit.own_models[0]


def test_constructed_source_diagram_uses_five_against_six_and_shocked_dash() -> None:
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContribution,
        ObjectiveControlResult,
    )

    # The source diagram has no authenticated datasheet or coordinates. Its
    # declared membership enters the real summation owner as typed contributions.
    # Native membership/partial and whole-base cases are asserted separately.
    rows = tuple(
        ObjectiveControlContribution(
            player_id=player,
            unit_instance_id=f"constructed:s14:{group}",
            model_instance_id=f"constructed:s14:{group}:{i}",
            objective_control=oc,
            effective_objective_control=0 if shocked else oc,
            battle_shocked=shocked,
            horizontal_distance_inches=0,
            vertical_gap_inches=0,
        )
        for player, group, count, oc, shocked in (
            ("BLUE", "A", 1, 3, False),
            ("BLUE", "B", 1, 2, False),
            ("RED", "C", 6, 1, False),
            ("BLUE", "D", 5, 2, True),
        )
        for i in range(count)
    )
    result = ObjectiveControlResult.from_contributors(
        objective_id="constructed:s14:diagram", contributors=rows
    )
    assert [(r.player_id, r.score) for r in result.scores] == [("BLUE", 5), ("RED", 6)]
    assert result.controlled_by_player_id == "RED"
    assert sum(c.effective_objective_control for c in result.contributors if c.battle_shocked) == 0
