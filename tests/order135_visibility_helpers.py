"""Native setup with explicitly synthetic geometry declared before start.

The analytical eight-inch body on a 120mm support base is not a provider
measurement certificate. The complete config is replay-rooted; no state injection,
cloned helper globals or replaced decision controller supplies the result.
"""

from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order128_helpers import setup_config
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition


def edge_shooting_boundary() -> tuple[LocalGameSession, DecisionRequest]:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=9.5,
        center_y_inches=22,
        width_inches=0.1,
        depth_inches=44,
        display_template_id=None,
    )
    wall = TerrainFeatureDefinition(
        feature_id="order135-analytical-edge-wall",
        feature_kind=TerrainFeatureKind.HILLS_AND_SEALED_BUILDINGS,
        footprint_center_x_inches=9.5,
        footprint_center_y_inches=22,
        footprint_width_inches=0.1,
        footprint_depth_inches=44,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="solid",
                center_x_inches=9.5,
                center_y_inches=22,
                bottom_z_inches=0,
                width_inches=0.1,
                depth_inches=44,
                height_inches=10,
            ),
        ),
        source_id="order135-fixture:declared-analytical-wall",
    )
    config = setup_config(body_diameter=8, reserves=True)
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=(wall,))
    session = LocalGameSession()
    session.start(
        replace(
            config,
            mission_setup=mission,
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )
    ingress = False
    for index in range(200):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        kind = request.decision_type
        if (
            ingress
            and state.battle_round == 2
            and state.active_player_id == "player-b"
            and state.current_battle_phase is BattlePhase.SHOOTING
            and kind == "select_shooting_unit"
        ):
            status = session.submit_option(
                request_id=request.request_id,
                option_id="army-beta:large",
                result_id="order135:opponent-shooter",
            )
            assert status.decision_request is not None
            assert status.decision_request.decision_type == "select_shooting_type"
            return session, status.decision_request
        if kind == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _i, _owner, _model: Pose.at(52, 11.5),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id=f"order135:deploy:{index}"
            )
        elif kind == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=stratagem_decline_payload(),
                result_id=f"order135:decline:{index}",
            )
        elif kind == "submit_placement_proposal":
            assert not ingress
            assert request.actor_id == "player-a"
            assert state.battle_round == 2
            context = MovementProposalRequest.from_decision_request_payload(request.payload)
            army = state.army_definition_for_player("player-a")
            assert army is not None
            unit = army.unit_by_id(context.unit_instance_id)
            placement = UnitPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                model_placements=(
                    ModelPlacement(
                        army_id="army-alpha",
                        player_id="player-a",
                        unit_instance_id=unit.unit_instance_id,
                        model_instance_id=unit.own_models[0].model_instance_id,
                        pose=Pose.at(5, 2.5),
                    ),
                ),
            )
            proposal = PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=context.unit_instance_id,
                placement_kind=context.placement_kinds[0],
                attempted_placement=placement,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=validate_json_value(proposal.to_payload()),
                result_id="order135:legal-ingress",
            )
            ingress = True
        else:
            if kind == "select_secondary_missions":
                option = "fixed:assassination:bring_it_down"
            elif kind == "select_reserve_declaration":
                option = (
                    "declare_strategic_reserves:army-alpha:large"
                    if request.actor_id == "player-a"
                    else "complete_reserve_declarations"
                )
            elif (
                kind == "select_movement_unit"
                and state.battle_round == 2
                and request.actor_id == "player-a"
                and not ingress
            ):
                option = next(
                    o.option_id for o in request.options if "army-alpha:large" in o.option_id
                )
            elif kind == "select_movement_action":
                option = (
                    "ingress"
                    if state.battle_round == 2 and request.actor_id == "player-a" and not ingress
                    else "remain_stationary"
                )
            else:
                option = next(
                    (
                        o.option_id
                        for o in request.options
                        if o.option_id.startswith(("complete_", "end_", "decline", "skip"))
                    ),
                    request.options[0].option_id,
                )
            status = session.submit_option(
                request_id=request.request_id, option_id=option, result_id=f"order135:setup:{index}"
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Native edge scene did not reach opponent Shooting boundary.")
