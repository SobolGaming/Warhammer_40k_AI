"""Aircraft movement restrictions through real native owners and public decisions."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import paths, scenario
from tests.support.section03_session import movement_session
from tests.support.section05_fixtures import replace_unit
from tests.support.section09_fixtures import begin
from tests.support.section23_fixtures import scene
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement import (
    MovementActionAvailabilityContext,
    resolve_normal_move,
)
from warhammer40k_core.geometry.pose import Pose


def test_native_aircraft_identity_has_ingress_only_policy(
    section23_definitions: Section02Definitions,
) -> None:
    state, aircraft, _ = scene(section23_definitions, aircraft_attacker=True)
    policy = AircraftMovementPolicy.from_unit(
        unit=aircraft, ruleset_descriptor=state.runtime_ruleset_descriptor()
    )
    assert "AIRCRAFT" in aircraft.keywords
    assert policy.uses_aircraft_rules
    assert not policy.can_declare_charge
    assert AircraftMovementPolicy.from_payload(policy.to_payload()) == policy
    assert policy.effective_keywords == aircraft.keywords
    context = MovementActionAvailabilityContext(
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        unit_instance_id=aircraft.unit_instance_id,
        player_id="owner",
        enemy_engagement_model_ids=(),
        aircraft_movement_policy=policy,
    )
    assert context.evaluate().available_actions == ()


@pytest.mark.parametrize("action", ["normal", "charge", "mutation"])
def test_aircraft_rejects_other_movement_before_state_mutation(
    section23_definitions: Section02Definitions, action: str
) -> None:
    state, aircraft, target = scene(section23_definitions, aircraft_attacker=True)
    world = scenario(state)
    witness = paths(aircraft, (Pose.at(15, 15),), (Pose.at(16, 15),))
    before = state.to_payload()
    if action == "normal":
        result = resolve_normal_move(
            scenario=world,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=world.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id),
            path_witness=witness,
        )
        assert not result.is_valid
    elif action == "charge":
        with pytest.raises(GameLifecycleError, match="aircraft_ingress_only"):
            resolve_charge_move(
                scenario=world,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                unit_placement=world.battlefield_state.unit_placement_by_id(
                    aircraft.unit_instance_id
                ),
                path_witness=witness,
                selected_target_unit_instance_ids=(target.unit_instance_id,),
                maximum_distance_inches=12,
            )
    else:
        placed = world.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
        moved = replace(
            placed,
            model_placements=(replace(placed.model_placements[0], pose=Pose.at(16, 15)),),
        )
        with pytest.raises(GameLifecycleError, match="aircraft_ingress_only"):
            state.replace_battlefield_state(world.battlefield_state.with_unit_placement(moved))
    assert state.to_payload() == before


@pytest.mark.parametrize("ordinary_enemy", [False, True])
def test_public_movement_choices_distinguish_aircraft_only_engagement(
    section23_definitions: Section02Definitions, ordinary_enemy: bool
) -> None:
    d = section23_definitions
    state, mover, enemy = scene(d, distance=2)
    if ordinary_enemy:
        # Same physical engagement with the Aircraft keyword removed is a
        # controlled ordinary-enemy counterexample, not an unrelated extra unit.
        from tests.unit_keyword_helpers import with_unit_keywords

        replace_unit(state, with_unit_keywords(enemy, keywords=("INFANTRY",)))
    session = movement_session(d, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s23:select", option_id=mover.unit_instance_id
    )
    next_request = status.decision_request
    assert next_request is not None
    request = next_request
    options = {o.option_id for o in request.options}
    if ordinary_enemy:
        assert "normal_move" not in options
        assert "advance" not in options
        assert any(o.startswith("fall_back:") for o in options)
    else:
        assert {"normal_move", "advance", "remain_stationary"} == options
    before = state.to_payload()
    controller = session.lifecycle.decision_controller.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=request.request_id, result_id="s23:invalid", option_id="invented"
        )
    assert state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == controller
