"""Native Scouts at the exact pre-battle owner; no prior phase or muster work."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section09_fixtures import movement_mission
from tests.support.section24_fixtures import BODY, LORD
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleStage, SetupStep
from warhammer40k_core.engine.prebattle import (
    ScoutMoveProposal,
    prebattle_action_selection_request,
    prebattle_proposal_request_from_selection,
)
from warhammer40k_core.engine.scout_movement import resolve_scout_move
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("distance", [0, 6, 6.001])
def test_native_scouts_supply_distance_and_require_full_witnessed_coherent_path(
    section24_definitions: Section02Definitions, distance: float
) -> None:
    d = section24_definitions
    own = d.unit(BODY)
    enemy = d.unit(LORD, army_id="enemy", identity="target")
    poses = tuple(Pose.at(10, 8 + 1.3 * i) for i in range(len(own.own_models)))
    state = native_state(d, own, poses, enemy=enemy, enemy_poses=(Pose.at(35, 8),))
    state.mission_setup = replace(
        movement_mission(),
        deployment_zones=(
            DeploymentZone.rectangle(
                "constructed:s24:own", "owner", min_x=0, max_x=20, min_y=0, max_y=44
            ),
            DeploymentZone.rectangle(
                "constructed:s24:enemy", "opponent", min_x=30, max_x=44, min_y=0, max_y=44
            ),
        ),
    )
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    state.battle_phase_index = None
    state.active_player_id = None
    selection = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        player_id="owner",
    )
    option = next(
        o
        for o in selection.options
        if isinstance(o.payload, dict) and o.payload.get("action_kind") == "scout_move"
    )
    request = prebattle_proposal_request_from_selection(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        selection_request=selection,
        result=DecisionResult.for_request(
            result_id="s24:scout", request=selection, selected_option_id=option.option_id
        ),
    )
    assert request.scout_distance_inches == 6
    proposal = ScoutMoveProposal(
        request.request_id,
        request.proposal_kind,
        state.game_id,
        state.ruleset_descriptor_hash,
        SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        "owner",
        own.unit_instance_id,
        request.action_kind,
        request.source_rule_id,
        6,
        PathWitness.for_paths(
            tuple(
                (mid, (p, Pose.at(p.position.x + distance, p.position.y)))
                for mid, p in zip(own.own_model_ids(), poses, strict=True)
            )
        ),
        request.context,
    )
    before = state.to_payload()
    result = resolve_scout_move(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        request=request,
        proposal=proposal,
        source_event_id=None,
    )
    assert result.is_valid is (distance <= 6), result.to_payload()
    assert state.to_payload() == before
