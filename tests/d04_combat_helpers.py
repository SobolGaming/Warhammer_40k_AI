"""The retained D04 public narrow-platform recipe; analytical cargo, no faction claim."""

from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order135_transport_helpers import (
    cargo_proposal,
    submit_transport_choice,
    transport_config,
)
from tests.phase11c_command_phase_helpers import unit_selection
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition


def combat_session(
    *, game_id: str = "order135-combat-platform", cargo_config: GameConfig | None = None
) -> LocalGameSession:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        feature_id="order135-combat-platform",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="carrier-top",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=5.5,
                width_inches=4,
                depth_inches=4,
                thickness_inches=0.12,
            ),
        ),
    )
    config = transport_config() if cargo_config is None else cargo_config
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        deployment_map_id="order135-custom-platform-deployment",
        terrain_layout_id="order135-custom-platform-terrain",
        terrain_features=(feature,),
    )
    session = LocalGameSession()
    session.start(
        replace(
            config,
            game_id=game_id,
            mission_setup=mission,
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "submit_placement_proposal":
            return session
        if request.decision_type == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:platform",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, owner, _model: Pose.at(
                        10 if owner == "player-a" else 50,
                        10,
                        5.5 if owner == "player-a" else 0,
                    ),
                ),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        elif request.decision_type == "select_movement_unit":
            state = session.lifecycle.state
            assert state is not None
            cargo = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passenger")
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order135-cargo",
                option_id=cargo.unit_instance_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            submit_transport_choice(session, request)
    raise AssertionError("D04 public disembark boundary not reached")


def canonical_mob_cargo_config() -> GameConfig:
    """Canonical ten one-wound models; the original analytical capacity declaration."""
    config = transport_config()
    alpha, beta = config.army_muster_requests
    passenger = unit_selection(
        unit_selection_id="passenger",
        datasheet_id="core-boyz-like-infantry",
        model_profile_id="core-boyz-like",
        model_count=10,
    )
    return replace(
        config,
        army_muster_requests=(
            replace(alpha, unit_selections=(passenger, alpha.unit_selections[1])),
            beta,
        ),
    )


def canonical_attached_cargo_config() -> GameConfig:
    """Canonical leader and five bodyguards; both components declared aboard pre-start."""
    config = transport_config()
    alpha, beta = config.army_muster_requests
    bodyguard = unit_selection(
        unit_selection_id="bodyguard",
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )
    manifest = replace(
        alpha.dedicated_transport_manifests[0],
        embarked_unit_selection_ids=("passenger", "bodyguard"),
    )
    return replace(
        config,
        army_muster_requests=(
            replace(
                alpha,
                unit_selections=(*alpha.unit_selections, bodyguard),
                attachment_declarations=(
                    AttachmentDeclaration(
                        source_unit_selection_id="passenger",
                        bodyguard_unit_selection_id="bodyguard",
                    ),
                ),
                dedicated_transport_manifests=(manifest,),
            ),
            beta,
        ),
    )


def combat_proposal(session: LocalGameSession) -> PlacementProposalPayload:
    proposal = cargo_proposal(session)
    assert proposal.attempted_placement is not None
    return replace(
        proposal,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        attempted_placement=replace(
            proposal.attempted_placement,
            model_placements=tuple(
                replace(row, pose=Pose.at(15.8, 10, 0))
                for row in proposal.attempted_placement.model_placements
            ),
        ),
    )


def canonical_cargo_proposal(session: LocalGameSession) -> PlacementProposalPayload:
    """One complete coherent group on the ground beside the retained platform."""
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    army = state.army_definition_for_player(view.owner_player_id)
    assert army is not None
    count = len(view.alive_models())
    rows = (count + 1) // 2
    placements: list[UnitPlacement] = []
    index = 0
    for component in sorted(view.living_components, key=lambda c: c.unit.unit_instance_id):
        models: list[ModelPlacement] = []
        for model in component.unit.own_models:
            if not model.is_alive:
                continue
            models.append(
                ModelPlacement(
                    army_id=army.army_id,
                    player_id=view.owner_player_id,
                    unit_instance_id=component.unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(
                        13.2 + (index % 2) * 1.45, 10 + (index // 2 - (rows - 1) / 2) * 1.45
                    ),
                )
            )
            index += 1
        placements.append(
            UnitPlacement(
                unit_instance_id=component.unit.unit_instance_id,
                army_id=army.army_id,
                player_id=view.owner_player_id,
                model_placements=tuple(models),
            )
        )
    return PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=view.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_rules_unit_placement=RulesUnitPlacement(
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_placements=tuple(placements),
        ),
        transport_unit_instance_id="army-alpha:transport",
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )


def finish_to_next_own_movement(session: LocalGameSession) -> None:
    """Only normal advertised decisions; no phase, dice or state replacement."""
    from tests.order128_helpers import assert_checkpoint
    from tests.order135_transport_helpers import PASSENGER
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    saw_opponent_turn = False
    for index in range(100):
        status = session.advance_until_decision_or_terminal()
        state = session.lifecycle.state
        assert state is not None
        if (
            state.battle_round == 2
            and state.active_player_id == "player-a"
            and (state.current_battle_phase is BattlePhase.MOVEMENT)
        ):
            assert saw_opponent_turn
            return
        if state.active_player_id == "player-b" and not saw_opponent_turn:
            # The charge restriction has expired; the source-backed status has not.
            assert state.battle_shocked_unit_ids == [PASSENGER]
            assert not state.disembarked_unit_states
            assert_checkpoint(session)
            saw_opponent_turn = True
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"d04:cycle:{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id.startswith(("complete_", "end_", "decline", "skip"))
                or option.option_id == "remain_stationary"
            )
            option = options[0] if options else request.options[0]
            result = session.submit_option(
                request_id=request.request_id,
                result_id=f"d04:cycle:{index}",
                option_id=option.option_id,
            )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    raise AssertionError("D04 did not reach the next ordinary own Movement phase")
