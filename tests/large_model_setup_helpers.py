"""Real canonical state for oversized setup resolver and performance regressions."""

from dataclasses import replace

from tests.phase10p_reserves_helpers import battle_state_with_reserve
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, ModelPlacement
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
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def oversized_deployment_case(
    *, zone_width: float = 3.0, x: float | None = None
) -> tuple[GameState, DeploymentPlacementRequest, DeploymentPlacementProposal]:
    state, _, _, unit = battle_state_with_reserve()
    assert state.mission_setup is not None
    state.mission_setup = replace(
        MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
            terrain_layout_id="disruption-vs-reconnaissance-layout-2",
            attacker_player_id="player-a",
            defender_player_id="player-b",
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
            DeploymentZone.rectangle(
                "large-a", "player-a", min_x=0, min_y=0, max_x=zone_width, max_y=44
            ),
            DeploymentZone.rectangle("large-b", "player-b", min_x=42, min_y=0, max_x=60, max_y=44),
        ),
    )
    state.reserve_states.clear()
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    state.battle_phase_index = None
    state.active_player_id = None
    selection = deployment_unit_selection_request(
        state=state, ruleset_descriptor=state.runtime_ruleset_descriptor(), player_id="player-a"
    )
    request = deployment_placement_request_from_selection(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        selection_request=selection,
        result=DecisionResult.for_request(
            result_id="order54-select",
            request=selection,
            selected_option_id=f"deploy:{unit.unit_instance_id}",
        ),
    )
    radius = 200 / 25.4 / 2
    proposal = DeploymentPlacementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        game_id=request.game_id,
        ruleset_descriptor_hash=request.ruleset_descriptor_hash,
        setup_step=SetupStep.DEPLOY_ARMIES,
        player_id=request.player_id,
        unit_instance_id=request.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
        model_placements=(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=Pose.at(radius if x is None else x, 30),
            ),
        ),
        context=request.context,
    )
    return state, request, proposal
