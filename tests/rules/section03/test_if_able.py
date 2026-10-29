"""FAQ26 stays beside coherency: approach requirements never excuse a broken group."""

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import native_state, paths, scenario
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.fight_resolution import FightMovementProposal, resolve_fight_movement
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
def test_if_able_approach_cannot_split_coherency(
    section03_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    starts = (Pose.at(10, 10), Pose.at(13.5, 10))
    state = native_state(
        section03_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(19, 10), Pose.at(19, 12.5)),
    )
    witness = paths(unit, starts, (starts[0], Pose.at(16.5, 10)))
    proposal = FightMovementProposal(
        "constructed-if-able-approach",
        kind,
        unit.unit_instance_id,
        kind.value,
        MovementMode.PILE_IN if kind is ProposalKind.PILE_IN else MovementMode.CONSOLIDATE,
        pile_in_target_unit_instance_ids=(enemy.unit_instance_id,)
        if kind is ProposalKind.PILE_IN
        else (),
        consolidate_target_unit_instance_ids=(enemy.unit_instance_id,)
        if kind is ProposalKind.CONSOLIDATE
        else (),
        witness=witness,
    )
    result = resolve_fight_movement(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        proposal=proposal,
        state=state,
    )
    assert not result.is_valid
    assert result.coherency_result is not None
    assert not result.coherency_result.is_coherent
    assert result.rollback_record is not None
