"""Small setup-boundary state; cached source mission only for deployment zone authority."""

from collections.abc import Iterator
from dataclasses import replace
from time import perf_counter

import pytest
from tests.support.section03_fixtures import placement

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
    deployment_placement_request_from_selection,
    deployment_unit_selection_request,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleStage, SetupStep
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="session")
def section03_setup_mission() -> Iterator[MissionSetup]:
    start = perf_counter()
    mission = replace(
        MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
            terrain_layout_id="disruption-vs-reconnaissance-layout-2",
            attacker_player_id="owner",
            defender_player_id="opponent",
            attacker_force_disposition_id="disruption",
            defender_force_disposition_id="reconnaissance",
        ),
        battlefield_layout_id=None,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        battlefield_regions=(),
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        objective_markers=(),
        deployment_zones=(
            DeploymentZone.rectangle("west", "owner", min_x=0, min_y=0, max_x=18, max_y=44),
            DeploymentZone.rectangle("east", "opponent", min_x=42, min_y=0, max_x=60, max_y=44),
        ),
        attacker_battlefield_edge="west",
        defender_battlefield_edge="east",
    )
    before = mission.to_payload()
    print(f"Section03 setup authority preparation: {perf_counter() - start:.6f}s; once")
    yield mission
    assert mission.to_payload() == before


def deployment_case(
    state: GameState, unit: UnitInstance, mission: MissionSetup, poses: tuple[Pose, ...]
) -> tuple[DeploymentPlacementRequest, DeploymentPlacementProposal]:
    state.mission_setup = mission
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    state.battle_phase_index = None
    state.active_player_id = None
    state.battlefield_state = BattlefieldRuntimeState("section03-setup", 60, 44, placed_armies=())
    request = deployment_unit_selection_request(
        state=state, ruleset_descriptor=state.runtime_ruleset_descriptor(), player_id="owner"
    )
    selected = deployment_placement_request_from_selection(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        selection_request=request,
        result=DecisionResult.for_request(
            result_id="select",
            request=request,
            selected_option_id=f"deploy:{unit.unit_instance_id}",
        ),
    )
    proposal = DeploymentPlacementProposal(
        proposal_request_id=selected.request_id,
        proposal_kind=selected.proposal_kind,
        game_id=state.game_id,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        setup_step=SetupStep.DEPLOY_ARMIES,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
        model_placements=placement(unit, poses).model_placements,
        context=selected.context,
    )
    return selected, proposal
