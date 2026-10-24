"""03.02 setup gates with complete native units and atomic invalid evaluations."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import native_state, placement, scenario
from tests.support.section03_setup import deployment_case
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
)
from warhammer40k_core.engine.deployment import resolve_deployment_placement
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.reserves import resolve_reserve_arrival
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("valid", None),
        ("incoherent", "unit_coherency_broken"),
        ("outside_zone", "deployment_zone_violation"),
        ("overlap", "model_overlap"),
        ("missing", "model_set_drift"),
    ],
)
def test_native_setup_requires_complete_coherent_legal_placement(
    section03_definitions: Section02Definitions,
    section03_setup_mission: MissionSetup,
    case: str,
    code: str | None,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    poses = {
        "valid": (Pose.at(10, 10), Pose.at(12.5, 10)),
        "incoherent": (Pose.at(2, 10), Pose.at(15, 10)),
        "outside_zone": (Pose.at(20, 10), Pose.at(22.5, 10)),
        "overlap": (Pose.at(10, 10), Pose.at(10, 10)),
        "missing": (Pose.at(10, 10), Pose.at(12.5, 10)),
    }[case]
    state = native_state(section03_definitions, unit)
    request, proposal = deployment_case(state, unit, section03_setup_mission, poses)
    if case == "missing":
        proposal = replace(proposal, model_placements=proposal.model_placements[:1])
    before = state.to_payload()
    result = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
    )
    assert result.is_valid is (code is None)
    if code:
        assert code in {v.violation_code.value for v in result.violations}
    assert (result.transition_batch is not None) is (code is None)
    assert state.to_payload() == before


@pytest.mark.parametrize(
    ("case", "valid"),
    [
        ("valid", True),
        ("incoherent", False),
        ("engaged", False),
        ("outside_strip", False),
        ("missing", False),
    ],
)
def test_reserve_setup_failure_keeps_entire_prior_location(
    section03_definitions: Section02Definitions, case: str, valid: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    enemy_poses = (
        (Pose.at(4, 10), Pose.at(4, 12.5))
        if case == "engaged"
        else (Pose.at(30, 10), Pose.at(30, 12.5))
    )
    state = native_state(section03_definitions, unit, enemy=enemy, enemy_poses=enemy_poses)
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        placed_armies=tuple(
            a for a in state.battlefield_state.placed_armies if a.player_id == "opponent"
        ),
    )
    reserve_unit(state, unit)
    poses = (Pose.at(1, 10), Pose.at(1, 12.5))
    if case == "incoherent":
        poses = (Pose.at(1, 10), Pose.at(1, 25))
    if case == "outside_strip":
        poses = (Pose.at(20, 10), Pose.at(20, 12.5))
    attempted = placement(unit, poses)
    if case == "missing":
        attempted = replace(attempted, model_placements=attempted.model_placements[:1])
    before = state.to_payload()
    result = resolve_reserve_arrival(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=state.reserve_states[0],
        attempted_placement=attempted,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is valid
    assert (result.transition_batch is not None) is valid
    assert state.to_payload() == before
