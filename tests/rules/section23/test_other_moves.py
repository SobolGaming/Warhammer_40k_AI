"""Direct shared movement owners preserve Aircraft's Ingress-only restriction."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import paths, scenario
from tests.support.section23_fixtures import scene
from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.fight_movement_paths import validate_fight_paths
from warhammer40k_core.engine.fight_resolution import FightMovementProposal
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phases.movement import (
    AdvanceRollRequest,
    AdvanceRollResult,
    resolve_advance_move,
)
from warhammer40k_core.geometry.pose import Pose


def test_actual_advance_owner_rejects_aircraft_with_faithful_roll_input(
    section23_definitions: Section02Definitions,
) -> None:
    state, own, _ = scene(section23_definitions, aircraft_attacker=True)
    world = scenario(state)
    request = AdvanceRollRequest.for_unit(
        request_id="s23:advance",
        game_id=state.game_id,
        battle_round=1,
        player_id="owner",
        unit_instance_id=own.unit_instance_id,
    )
    roll = AdvanceRollResult.from_roll_state(
        request=request,
        roll_state=DiceRollState.from_result(
            DiceRollResult.from_values(
                roll_id="s23:fixed",
                spec=request.spec,
                values=(6,),
                source="fixed",
            )
        ),
    )
    before = state.to_payload()
    result = resolve_advance_move(
        scenario=world,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=world.battlefield_state.unit_placement_by_id(own.unit_instance_id),
        path_witness=paths(own, (Pose.at(15, 15),), (Pose.at(16, 15),)),
        advance_roll=roll,
    )
    assert not result.is_valid
    assert state.to_payload() == before


@pytest.mark.parametrize("mode", [MovementMode.PILE_IN, MovementMode.CONSOLIDATE])
def test_aircraft_cannot_pile_in_or_consolidate_at_shared_physical_owner(
    section23_definitions: Section02Definitions, mode: MovementMode
) -> None:
    state, own, _ = scene(section23_definitions, aircraft_attacker=True)
    world = scenario(state)
    placed = world.battlefield_state.unit_placement_by_id(own.unit_instance_id)
    witness = paths(own, (Pose.at(15, 15),), (Pose.at(16, 15),))
    before = state.to_payload()
    results, _ = validate_fight_paths(
        scenario=world,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        before=placed,
        after=placed,
        witness=witness,
        movement_mode=mode,
        displacement_kind=ModelDisplacementKind.PILE_IN
        if mode is MovementMode.PILE_IN
        else ModelDisplacementKind.CONSOLIDATE,
        distance_budget_inches=3,
        proposal=FightMovementProposal(
            proposal_request_id="s23:fight",
            proposal_kind=ProposalKind.PILE_IN
            if mode is MovementMode.PILE_IN
            else ProposalKind.CONSOLIDATE,
            unit_instance_id=own.unit_instance_id,
            movement_phase_action=mode.value,
            movement_mode=mode,
            witness=witness,
        ),
    )
    assert results
    assert not results[0].is_valid
    assert results[0].violations[0].violation_code == "aircraft_ingress_only"
    assert state.to_payload() == before
