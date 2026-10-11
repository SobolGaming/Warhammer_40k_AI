"""D06 scenes declared before public setup; no live state/history injection.

The hill and Dedicated manifest are analytical Core fixtures, not faction grants.
The elevated recipe preserves the independently reproduced native entry path.
"""

from dataclasses import dataclass, replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.order135_transport_helpers import CARRIER, PASSENGER, cargo_proposal, transport_config
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition


def embark_config(*, player: str, elevated: bool) -> GameConfig:
    config = transport_config()
    assert config.mission_setup is not None
    enemy = "player-b" if player == "player-a" else "player-a"
    z = 8.0 if elevated else 0.0
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=6,
        depth_inches=6,
        display_template_id=None,
    )
    floor = TerrainFeatureDefinition(
        feature_id="d06:stable-floor",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=6,
        footprint_depth_inches=6,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=z,
                width_inches=6,
                depth_inches=6,
                thickness_inches=0.12,
            ),
        ),
        source_id="d06:predeclared-analytical-terrain",
    )
    mission = replace(
        config.mission_setup,
        battlefield_layout_id=None,
        deployment_map_id="d06:zones",
        terrain_layout_id="d06:terrain",
        terrain_features=(floor,) if elevated else (),
        deployment_zones=(
            DeploymentZone.rectangle("A", player, min_x=0, min_y=0, max_x=18, max_y=44),
            DeploymentZone.rectangle("B", enemy, min_x=24, min_y=0, max_x=44, max_y=44),
        ),
    )
    alpha, beta = config.army_muster_requests
    return replace(
        config,
        game_id=f"d06:{player}:{elevated}",
        army_muster_requests=(
            replace(
                alpha,
                player_id=player,
                force_disposition_id=alpha.force_disposition_id
                if player == "player-a"
                else beta.force_disposition_id,
            ),
            replace(
                beta,
                player_id=enemy,
                force_disposition_id=beta.force_disposition_id
                if player == "player-a"
                else alpha.force_disposition_id,
            ),
        ),
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )


def state_of(session: LocalGameSession) -> GameState:
    state = session.lifecycle.state
    assert state is not None
    return state


def choose(session: LocalGameSession, request: DecisionRequest, option: str) -> LifecycleStatus:
    status = session.submit_option(
        request_id=request.request_id,
        result_id=f"d06:{request.request_id}:{option}",
        option_id=option,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    return status


def propose(
    session: LocalGameSession, request: DecisionRequest, payload: JsonValue
) -> LifecycleStatus:
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"d06:{request.request_id}:proposal",
        payload=payload,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    return status


def move_payload(
    session: LocalGameSession,
    request: DecisionRequest,
    *,
    dy: float = 0,
    witness: PathWitness | None = None,
) -> JsonValue:
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    assert context.movement_phase_action is not None
    movement_mode = context.context["movement_mode"]
    assert isinstance(movement_mode, str)
    return validate_json_value(
        MovementProposalPayload(
            proposal_request_id=context.request_id,
            proposal_kind=context.proposal_kind,
            unit_instance_id=context.unit_instance_id,
            movement_phase_action=context.movement_phase_action,
            movement_mode=movement_mode,
            witness=witness
            or straight_line_witness_for_unit(
                session.lifecycle,
                unit_instance_id=context.unit_instance_id,
                dy=dy,
            ),
        ).to_payload()
    )


def default_choice(session: LocalGameSession, request: DecisionRequest) -> None:
    if request.decision_type == "submit_stratagem_target_proposal":
        propose(session, request, stratagem_decline_payload())
        return
    if request.decision_type == "select_movement_action":
        choose(session, request, "remain_stationary")
        return
    options = tuple(option.option_id for option in request.options)
    assert options, request.decision_type
    option = (
        "fixed:assassination:bring_it_down"
        if request.decision_type == "select_secondary_missions"
        else next(
            (x for x in options if x.startswith(("complete_", "end_", "decline", "skip", "keep"))),
            options[0],
        )
    )
    choose(session, request, option)


@dataclass
class EmbarkScene:
    session: LocalGameSession
    player: str
    elevated: bool
    disembarked: bool = False
    carrier_moved: bool = False
    passenger_moved: bool = False
    deployment_height_inches: float | None = None
    carrier_endpoint: Pose | None = None

    def handle(self, request: DecisionRequest) -> None:
        session = self.session
        state = state_of(session)
        assert state.battle_round <= 3, "D06 native scene cap"
        kind = request.decision_type
        z = (
            self.deployment_height_inches
            if self.deployment_height_inches is not None
            else 8.0
            if self.elevated
            else 0.0
        )
        if kind == "submit_deployment_placement":
            propose(
                session,
                request,
                deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, owner, _model: (
                        Pose.at(10, 10, z) if owner == self.player else Pose.at(28, 10)
                    ),
                ),
            )
            return
        if kind == "select_movement_unit" and request.actor_id == self.player:
            options = tuple(option.option_id for option in request.options)
            if not self.disembarked and PASSENGER in options:
                choose(session, request, PASSENGER)
                return
            if self.disembarked and not self.carrier_moved and CARRIER in options:
                choose(session, request, CARRIER)
                return
            if state.battle_round >= 2 and self.carrier_moved and not self.passenger_moved:
                choose(session, request, PASSENGER)
                return
        if kind == "select_movement_action" and request.actor_id == self.player:
            payload = request.payload
            assert isinstance(payload, dict)
            unit_instance_id = payload["unit_instance_id"]
            assert isinstance(unit_instance_id, str)
            option = (
                "disembark"
                if not self.disembarked
                else "advance"
                if unit_instance_id == CARRIER and self.elevated
                else "normal_move"
                if unit_instance_id in (PASSENGER, CARRIER)
                else "remain_stationary"
            )
            choose(session, request, option)
            return
        if kind == "submit_placement_proposal" and not self.disembarked:
            proposal = cargo_proposal(session)
            assert proposal.attempted_placement is not None
            proposal = replace(
                proposal,
                attempted_placement=replace(
                    proposal.attempted_placement,
                    player_id=self.player,
                    model_placements=tuple(
                        replace(x, player_id=self.player, pose=Pose.at(12, 12, z))
                        for x in proposal.attempted_placement.model_placements
                    ),
                ),
            )
            propose(session, request, validate_json_value(proposal.to_payload()))
            self.disembarked = True
            return
        if kind == "submit_movement_proposal" and request.actor_id == self.player:
            context = MovementProposalRequest.from_decision_request_payload(request.payload)
            if context.unit_instance_id == CARRIER and not self.carrier_moved:
                assert state.battlefield_state is not None
                placement = state.battlefield_state.unit_placement_by_id(CARRIER)
                endpoint = self.carrier_endpoint or Pose.at(15, 10)
                witness = PathWitness.for_paths(
                    tuple(
                        (
                            x.model_instance_id,
                            (
                                x.pose,
                                Pose.at(endpoint.position.x, endpoint.position.y, z),
                                endpoint,
                            ),
                        )
                        if self.elevated
                        else (x.model_instance_id, (x.pose, endpoint))
                        for x in placement.model_placements
                    )
                )
                propose(session, request, move_payload(session, request, witness=witness))
                self.carrier_moved = True
                return
            if context.unit_instance_id == PASSENGER:
                propose(
                    session,
                    request,
                    move_payload(
                        session,
                        request,
                        dy=-0.5 if state.battle_round >= 2 else 0,
                    ),
                )
                self.passenger_moved = state.battle_round >= 2
                return
        default_choice(session, request)

    def reach_later_move(self) -> DecisionRequest:
        for _ in range(100):
            request = pending_request(self.session)
            state = state_of(self.session)
            if (
                request.decision_type == "submit_movement_proposal"
                and request.actor_id == self.player
                and state.battle_round == 2
            ):
                context = MovementProposalRequest.from_decision_request_payload(request.payload)
                if context.unit_instance_id == PASSENGER:
                    return request
            self.handle(request)
        raise AssertionError("D06 later-own-turn move not reached")


def later_embark_scene(*, player: str, elevated: bool) -> EmbarkScene:
    session = LocalGameSession()
    session.start(embark_config(player=player, elevated=elevated))
    scene = EmbarkScene(session, player, elevated)
    scene.reach_later_move()
    return scene


def later_diagonal_embark_scene(*, player: str) -> EmbarkScene:
    """Predeclare both stable supports; retain ordinary catalog circular bases."""
    config = embark_config(player=player, elevated=True)
    assert config.mission_setup is not None
    upper = config.mission_setup.terrain_features[0]
    upper = replace(
        upper,
        floors=tuple(replace(floor, bottom_z_inches=9.4) for floor in upper.floors),
    )
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=18,
        center_y_inches=10,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    lower = replace(
        upper,
        feature_id="d06:lower-stable-floor",
        footprint_center_x_inches=18,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=tuple(
            replace(
                floor,
                floor_id="lower",
                center_x_inches=18,
                bottom_z_inches=7,
                width_inches=10,
                depth_inches=10,
            )
            for floor in upper.floors
        ),
    )
    mission = replace(config.mission_setup, terrain_features=(upper, lower))
    config = replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session = LocalGameSession()
    session.start(config)
    scene = EmbarkScene(
        session,
        player,
        elevated=True,
        deployment_height_inches=9.4,
        carrier_endpoint=Pose.at(16, 10, 7),
    )
    scene.reach_later_move()
    return scene
