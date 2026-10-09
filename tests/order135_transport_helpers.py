"""Pregame cargo scenes using public setup and disembark decisions.

The optional FRAME cylinder is explicitly synthetic Core geometry. These scenes
do not certify faction roster admission or official model measurements.
"""

from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order85_overhang_helpers import footprint
from tests.order128_helpers import evidence
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    ModelGeometryCatalogRecord,
    ModelHeightDefinition,
)
from warhammer40k_core.engine.army_mustering import (
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose

PASSENGER = "army-alpha:passenger"
CARRIER = "army-alpha:transport"


def transport_config(*, frame_height: float | None = None, manifest: bool = True) -> GameConfig:
    config = phase11c_config(
        game_id="order135-native-cargo",
        player_a_units=tuple(
            unit_selection(
                unit_selection_id=name,
                datasheet_id=sheet,
                model_profile_id=sheet,
                model_count=1,
            )
            for name, sheet in (
                ("passenger", "core-character-leader"),
                ("transport", "core-transport"),
            )
        ),
        player_b_units=(
            unit_selection(
                unit_selection_id="enemy",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    keywords=(
                        *sheet.keywords.keywords,
                        *(
                            ("DEDICATED TRANSPORT",)
                            if sheet.datasheet_id == "core-transport"
                            else ()
                        ),
                        *(
                            ("FRAME",)
                            if frame_height is not None
                            and sheet.datasheet_id == "core-character-leader"
                            else ()
                        ),
                    ),
                ),
            )
            for sheet in config.army_catalog.datasheets
        ),
    )
    geometries = None
    if frame_height is not None:
        profile = catalog.datasheet_by_id("core-character-leader").model_profiles[0]
        assert profile.base_size.diameter_mm is not None
        diameter = profile.base_size.diameter_mm / 25.4
        body = evidence(
            "order135-cargo-body", GeometryMeasurementKind.FOOTPRINT, "diameter", diameter
        )
        base = evidence(
            "order135-cargo-base", GeometryMeasurementKind.SUPPORT_BASE, "diameter", diameter
        )
        height = evidence(
            "order135-cargo-height", GeometryMeasurementKind.HEIGHT, "height", frame_height
        )
        geometries = (
            ModelGeometryCatalogRecord(
                model_geometry_id="order135-cargo-frame",
                model_profile_id=profile.model_profile_id,
                rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
                footprint=footprint("order135-cargo-body", body),
                support_base=footprint("order135-cargo-base", base),
                z_offset=None,
                height=ModelHeightDefinition.from_evidence(height),
                evidence=(body, base, height),
                source_ids=("order128-fixture:analytical-cylinder",),
            ),
        )
    declaration = DedicatedTransportManifest(
        transport_unit_selection_id="transport",
        embarked_unit_selection_ids=("passenger",),
        capacity_profile=DedicatedTransportCapacityProfile(
            transport_datasheet_id="core-transport",
            max_model_count=12,
            allowed_keywords=("INFANTRY",),
            source_id="order135-cargo:declared-capacity",
        ),
        source_id="order135-cargo:pregame-manifest",
    )
    alpha, beta = config.army_muster_requests
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
    )
    return replace(
        config,
        army_catalog=catalog,
        army_muster_requests=(
            replace(alpha, dedicated_transport_manifests=(declaration,) if manifest else ()),
            beta,
        ),
        model_geometries=geometries,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )


def starting_cargo_session(
    *, frame_height: float | None = None, manifest: bool = True
) -> LocalGameSession:
    session = LocalGameSession()
    session.start(transport_config(frame_height=frame_height, manifest=manifest))
    pending_request(session)
    return session


def submit_transport_choice(session: LocalGameSession, request: DecisionRequest) -> None:
    result_id = f"{request.request_id}:order135-cargo"
    if request.decision_type == "submit_deployment_placement":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _i, owner, _model: Pose.at(
                    10 if owner == "player-a" else 50, 10
                ),
            ),
        )
    elif any(option.option_id == PASSENGER for option in request.options):
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=PASSENGER
        )
    elif any(option.option_id == "disembark" for option in request.options):
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id="disembark"
        )
    else:
        submit_fixture_request(session, request)
        return
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def reach_disembark(session: LocalGameSession) -> DecisionRequest:
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "submit_placement_proposal":
            return request
        submit_transport_choice(session, request)
    raise AssertionError("Native starting-cargo disembark request was not reached.")


def cargo_proposal(session: LocalGameSession) -> PlacementProposalPayload:
    request = pending_request(session)
    assert request.decision_type == "submit_placement_proposal"
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER)
    center = state.battlefield_state.unit_placement_by_id(CARRIER).model_placements[0].pose.position
    return PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=UnitPlacement(
            unit_instance_id=PASSENGER,
            army_id="army-alpha",
            player_id="player-a",
            model_placements=tuple(
                ModelPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id=PASSENGER,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(center.x + 3.5, center.y),
                )
                for model in passenger.own_models
            ),
        ),
        transport_unit_instance_id=CARRIER,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=(),
    )
