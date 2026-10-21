"""Illustrated casualties/dice, canonical attachment and constrained flight scope."""

import json
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, scenario
from tests.support.section09_fixtures import add_unit
from tests.support.section21_fixtures import (
    BODY,
    LORD,
    SERPENT,
    SPAWN,
    SurgeScene,
    descriptor,
    offer_surge,
    submit_surge,
    surge_path,
    surge_scene,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phase_movement_history import surge_locked
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.take_to_the_skies import flight_choice_context
from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def test_worked_surge_example_uses_survivors_and_active_players_real_d6(
    section21_definitions: Section02Definitions,
) -> None:
    d = section21_definitions
    unit = d.unit(BODY)
    target = d.unit(BODY, army_id="enemy", identity="target")
    starts = tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5))
    own = geometry(unit, starts)[0]
    assert isinstance(own.base, CircularBase)
    enemy_x = 10 + 2 * own.base.radius + 10
    state = native_state(
        d,
        unit,
        starts,
        enemy=target,
        enemy_poses=tuple(Pose.at(enemy_x, p.position.y) for p in starts),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.active_player_id = "opponent"
    s = SurgeScene(d, state, unit, target, starts)
    session = s.session()
    # The source ability and completed shooting trigger are explicit Core premises;
    # native damage, dice, finite selection and physical movement are the consumers.
    for model in unit.own_models[:2]:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.current_wounds,
            damage_kind=DamageKind.NORMAL,
        )
    unit = next(a for a in state.army_definitions if a.player_id == "owner").unit_by_id(
        unit.unit_instance_id
    )
    s.unit = unit
    rolled = DiceRollManager(
        state.game_id, event_log=session.lifecycle.decision_controller.event_log
    ).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Section21 illustrated source-granted Surge distance",
            roll_type="movement_end_surge.distance",
            actor_id=state.active_player_id,
        )
    )
    assert rolled.original_result.spec.actor_id == state.active_player_id
    assert rolled.original_result.spec.actor_id == "opponent"
    assert 1 <= rolled.current_total <= 6
    request = offer_surge(session, s, maximum=float(rolled.current_total))
    assert request.actor_id == "owner"
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:casualty-select",
        option_id=f"surge:{unit.unit_instance_id}:target:{target.unit_instance_id}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    alive = tuple(m for m in unit.own_models if m.is_alive)
    assert len(alive) == 3
    path = PathWitness.for_paths(
        tuple(
            (m.model_instance_id, (p, Pose.at(10 + rolled.current_total, p.position.y)))
            for m, p in zip(unit.own_models, starts, strict=True)
            if m.is_alive
        )
    )
    status = submit_surge(session, request, path)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert state.phase_movement_history[-1].model_instance_ids == tuple(
        sorted(m.model_instance_id for m in alive)
    )


def test_native_components_surge_as_one_attached_rules_unit(
    section21_definitions: Section02Definitions,
) -> None:
    d = section21_definitions
    body = d.unit(LORD)
    leader = d.unit(LORD, identity="leader")
    enemy = d.unit(SPAWN, army_id="enemy", identity="target")
    first = geometry(body, (Pose.at(10, 10),))[0]
    other = geometry(enemy, (Pose.at(10, 10), Pose.at(10, 12.5)), enemy=True)[0]
    assert isinstance(first.base, CircularBase)
    assert isinstance(other.base, CircularBase)
    x = 10 + first.base.radius + other.base.radius + 9
    state = native_state(
        d, body, (Pose.at(10, 10),), enemy=enemy, enemy_poses=(Pose.at(x, 10), Pose.at(x, 12.5))
    )
    add_unit(state, leader, (Pose.at(10, 12.5),))
    ids = tuple(sorted((body.unit_instance_id, leader.unit_instance_id)))
    formation = AttachedUnitFormation(
        "attached-unit:section02:s21",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=ids,
        source_id="constructed:s21:attachment-permission",
        attachment_source_ids=("constructed:s21:attachment-permission",),
    )
    state.army_definitions[:] = [
        replace(a, attached_units=(formation,)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    state.starting_attached_unit_records[:] = [
        r for a in state.army_definitions for r in starting_attached_unit_records_for_army(a)
    ]
    state.starting_strength_records[:] = [
        r for a in state.army_definitions for r in starting_strength_records_for_army(a)
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    s = SurgeScene(d, state, body, enemy, (Pose.at(10, 10),))
    session = s.session()
    request = offer_surge(session, s)
    canonical = formation.attached_unit_instance_id
    assert {o.option_id for o in request.options if o.option_id.startswith("surge:")} == {
        f"surge:{canonical}:target:{enemy.unit_instance_id}"
    }
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:attached-select",
        option_id=f"surge:{canonical}:target:{enemy.unit_instance_id}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    before = state.to_payload()
    records = session.lifecycle.decision_controller.to_payload()
    invalid = submit_surge(
        session,
        request,
        PathWitness.for_paths(((body.own_model_ids()[0], (Pose.at(10, 10), Pose.at(14, 10))),)),
        result_id="s21:missing-leader",
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == records
    path = PathWitness.for_paths(
        tuple(
            (u.own_model_ids()[0], (Pose.at(10, y), Pose.at(14, y)))
            for u, y in ((body, 10), (leader, 12.5))
        )
    )
    status = submit_surge(session, request, path)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert set(state.phase_movement_history[-1].model_instance_ids) == {
        *body.own_model_ids(),
        *leader.own_model_ids(),
    }
    assert surge_locked(state, body.unit_instance_id)
    assert surge_locked(state, leader.unit_instance_id)
    assert (
        rules_unit_view_by_id(
            state=state, unit_instance_id=leader.unit_instance_id
        ).unit_instance_id
        == canonical
    )
    assert (
        json.loads(json.dumps(session.lifecycle.decision_controller.to_payload()))
        == session.lifecycle.decision_controller.to_payload()
    )


def test_surge_does_not_offer_take_to_the_skies(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions)
    board = scenario(s.state)
    with pytest.raises(GameLifecycleError, match="Surge cannot take to the skies"):
        resolve_triggered_movement(
            scenario=board,
            ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
            unit_placement=board.battlefield_state.unit_placement_by_id(s.unit.unit_instance_id),
            descriptor=descriptor(s),
            path_witness=surge_path(s, (4,)),
            battle_round=1,
            turn_player_id="owner",
            take_to_the_skies=True,
        )


def test_one_flying_component_makes_unit_flying_without_granting_sibling_transit(
    section21_definitions: Section02Definitions,
) -> None:
    d = section21_definitions
    body = d.unit(SERPENT)
    leader = d.unit(LORD, identity="grounded")
    state = native_state(d, body, (Pose.at(10, 10),))
    add_unit(state, leader, (Pose.at(10, 13),))
    formation = AttachedUnitFormation(
        "attached-unit:section02:s21-flight",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:s21:mixed-attachment-permission",
        attachment_source_ids=("constructed:s21:mixed-attachment-permission",),
    )
    # This is an explicit Core attachment contract using native physical models,
    # not a claim that the two native datasheets have legal attachment permission.
    state.army_definitions[:] = [
        replace(a, attached_units=(formation,)) for a in state.army_definitions
    ]
    view = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    assert "FLY" in view.keywords
    assert "FLY" not in leader.keywords
    choice = flight_choice_context(
        unit=view, ruleset=state.runtime_ruleset_descriptor(), selected=True
    )
    assert choice["flying_model_instance_ids"] == list(body.own_model_ids())
    assert choice["flight_penalty_inches"] == 2
    for component, expected in ((body, True), (leader, False)):
        cap = MovementCapabilitySet.from_keywords(
            component.keywords,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            movement_mode=MovementMode.NORMAL,
            take_to_the_skies=True,
            unit=component,
            model_instance_id=component.own_model_ids()[0],
            current_model_instance_ids=component.own_model_ids(),
        )
        assert cap.can_transit_all_terrain is expected
        assert cap.ignores_vertical_distance is expected
