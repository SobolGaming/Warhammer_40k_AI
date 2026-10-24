"""Native touching models cannot translate or pivot during an approach move."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.fight_resolution import (
    FightMovementProposal,
    fight_base_contact_movement_violation,
    resolve_fight_movement,
)
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("shift", [0, 0.001, 1])
def test_01_04_03_already_touching_must_stay_but_zero_path_is_move(
    section01_definitions: Section02Definitions, shift: float
) -> None:
    unit = section01_definitions.unit(LORD_EXULTANT, identity="source")
    enemy = section01_definitions.unit(LORD_EXULTANT, identity="enemy", army_id="opposing")
    state = minimal_state(section01_definitions, unit)
    state.army_definitions.append(
        replace(
            state.army_definitions[0],
            army_id="opposing",
            player_id="opponent",
            units=(enemy,),
        )
    )
    place_units(state)
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    geometry = geometry_model_for_placement(
        model=unit.own_models[0], placement=before.model_placements[0]
    )
    assert isinstance(geometry.base, CircularBase)
    enemy_place = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
    pose = before.model_placements[0].pose
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(
            enemy_place,
            model_placements=(
                replace(
                    enemy_place.model_placements[0],
                    pose=Pose.at(pose.position.x + 2 * geometry.base.radius, pose.position.y),
                ),
            ),
        )
    )
    scenario = battlefield_scenario_for_state(state=state)
    endpoint = Pose.at(pose.position.x - shift, pose.position.y)
    after = replace(before, model_placements=(replace(before.model_placements[0], pose=endpoint),))
    rules = RulesetDescriptor.warhammer_40000_eleventh()
    assert fight_base_contact_movement_violation(
        scenario=scenario,
        ruleset_descriptor=rules,
        before=before,
        after=after,
        state=state,
    ) == (None if shift == 0 else "base_contact_model_moved")
    if shift == 0:
        proposal = FightMovementProposal(
            "Core-approach",
            ProposalKind.PILE_IN,
            unit.unit_instance_id,
            "pile_in",
            MovementMode.PILE_IN,
            pile_in_target_unit_instance_ids=(enemy.unit_instance_id,),
            witness=PathWitness.for_paths(((unit.own_model_ids()[0], (pose, pose)),)),
        )
        assert not proposal.is_no_move_choice
        result = resolve_fight_movement(
            scenario=scenario, ruleset_descriptor=rules, proposal=proposal, state=state
        )
        assert result.movement_phase_action == "pile_in"
        assert result.attempted_placement == before
        assert len(result.path_validation_results) == 1
        assert all(row.is_valid for row in result.path_validation_results)
