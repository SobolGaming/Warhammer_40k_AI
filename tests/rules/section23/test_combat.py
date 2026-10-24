"""Unit FLY and physical model FLY remain separate Aircraft combat requirements."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section04_fixtures import add_enemy
from tests.support.section05_fixtures import replace_unit
from tests.support.section23_fixtures import AVENGERS, HAWKS, LORD, scene
from tests.unit_keyword_helpers import with_model_keywords, with_unit_keywords
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind
from warhammer40k_core.engine.aircraft_rules import aircraft_melee_target_ids
from warhammer40k_core.engine.charge_targets import charge_target_candidates
from warhammer40k_core.engine.fight_movement_mode_authority import (
    legal_consolidation_modes,
    legal_pile_in_target_rules_unit_ids,
)
from warhammer40k_core.engine.fight_resolution import melee_target_unit_ids
from warhammer40k_core.engine.surge_movement import closest_surge_targets
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("flying", [False, True])
def test_charge_pile_in_and_surge_use_fly_without_skies_choice(
    section23_definitions: Section02Definitions, flying: bool
) -> None:
    state, mover, aircraft = scene(section23_definitions, distance=4)
    ground = add_enemy(section23_definitions, state, identity="ground", x=20, y=15)
    if flying:
        mover = with_unit_keywords(mover, keywords=(*mover.keywords, "FLY"))
        replace_unit(state, mover)
    candidate = next(
        c
        for c in charge_target_candidates(
            state=state,
            unit_instance_id=mover.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        if c.target_unit_instance_id == aircraft.unit_instance_id
    )
    assert candidate.is_legal is flying
    pile_targets = legal_pile_in_target_rules_unit_ids(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=mover.unit_instance_id,
        state=state,
    )
    assert ground.unit_instance_id in pile_targets
    assert (aircraft.unit_instance_id in pile_targets) is flying
    targets = closest_surge_targets(
        scenario=scenario(state), unit_instance_id=mover.unit_instance_id
    )
    assert targets == ((aircraft.unit_instance_id,) if flying else (ground.unit_instance_id,))


@pytest.mark.parametrize("flying", [False, True])
def test_aircraft_melee_can_target_only_flying_units(
    section23_definitions: Section02Definitions, flying: bool
) -> None:
    state, aircraft, target = scene(section23_definitions, aircraft_attacker=True, distance=2)
    if flying:
        target = with_unit_keywords(target, keywords=(*target.keywords, "FLY"))
        replace_unit(state, target)
    targets = melee_target_unit_ids(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=aircraft.unit_instance_id,
    )
    assert (target.unit_instance_id in targets) is flying


@pytest.mark.parametrize("flying_index", [0, 1])
def test_mixed_unit_can_charge_but_only_individually_flying_model_can_attack_aircraft(
    section23_definitions: Section02Definitions, flying_index: int
) -> None:
    d = section23_definitions
    mover = d.unit(AVENGERS)
    mover = replace(
        mover,
        own_models=tuple(
            with_model_keywords(model, keywords=(*model.keywords, "FLY"))
            if index == flying_index
            else model
            for index, model in enumerate(mover.own_models)
        ),
    )
    aircraft = with_unit_keywords(d.unit(LORD, army_id="enemy"), keywords=("AIRCRAFT", "FLY"))
    state = native_state(
        d,
        mover,
        tuple(Pose.at(15, 15 + i * 1.3) for i in range(len(mover.own_models))),
        enemy=aircraft,
        enemy_poses=(Pose.at(18, 15),),
    )
    assert "FLY" in mover.keywords
    candidates = charge_target_candidates(
        state=state,
        unit_instance_id=mover.unit_instance_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    assert candidates[0].is_legal
    for index, model in enumerate(mover.own_models):
        targets = aircraft_melee_target_ids(
            scenario=scenario(state),
            unit_instance_id=mover.unit_instance_id,
            model_instance_id=model.model_instance_id,
            target_ids=(aircraft.unit_instance_id,),
        )
        assert bool(targets) is (index == flying_index)


def test_native_flying_datasheet_has_aircraft_charge_permission_without_taking_to_skies(
    section23_definitions: Section02Definitions,
) -> None:
    d = section23_definitions
    own = d.unit(HAWKS)
    assert "FLY" in own.keywords
    assert all("FLY" in m.keywords for m in own.own_models)
    target = with_unit_keywords(d.unit(LORD, army_id="enemy"), keywords=("AIRCRAFT", "FLY"))
    state = native_state(
        d,
        own,
        tuple(Pose.at(15, 15 + i * 1.5) for i in range(len(own.own_models))),
        enemy=target,
        enemy_poses=(Pose.at(20, 15),),
    )
    assert charge_target_candidates(
        state=state,
        unit_instance_id=own.unit_instance_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )[0].is_legal
    for model in own.own_models:
        assert aircraft_melee_target_ids(
            scenario=scenario(state),
            unit_instance_id=own.unit_instance_id,
            model_instance_id=model.model_instance_id,
            target_ids=(target.unit_instance_id,),
        ) == (target.unit_instance_id,)


@pytest.mark.parametrize("flying", [False, True])
def test_consolidation_ignores_aircraft_when_unit_cannot_fly(
    section23_definitions: Section02Definitions, flying: bool
) -> None:
    state, mover, _ = scene(section23_definitions, distance=2)
    if flying:
        mover = with_unit_keywords(mover, keywords=(*mover.keywords, "FLY"))
        replace_unit(state, mover)
    modes = legal_consolidation_modes(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=mover.unit_instance_id,
        objective_markers=(),
        state=state,
    )
    assert modes == ((ConsolidationModeKind.ONGOING,) if flying else ())
