"""Catalog-mustered setup fixtures with explicitly synthetic measured geometry."""

from __future__ import annotations

import json
from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order85_overhang_helpers import footprint
from tests.order127_helpers import YRIEL, redeploy_catalog
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.reserves import ReserveUnitPointValue
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def evidence(
    label: str, kind: GeometryMeasurementKind, dimension: str, value: float
) -> ModelGeometrySourceEvidence:
    return ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"order128-fixture:{label}",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=kind,
        source_id="order128-fixture:analytical-cylinder",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=((dimension, value),),
        document_reference="Explicit synthetic analytical setup cylinder with declared dimensions.",
    )


def setup_config(
    *,
    body_diameter: float = 8,
    zone_width: float = 18,
    reserves: bool = False,
    redeploy: bool = False,
) -> GameConfig:
    units = (
        unit_selection(
            unit_selection_id="large",
            datasheet_id="core-vehicle-monster",
            model_profile_id="core-vehicle-monster",
            model_count=1,
        ),
    )
    config = phase11c_config(game_id="order128-setup", player_a_units=units, player_b_units=units)
    profile_id = "core-vehicle-monster"
    base_diameter_mm = 120.0
    if redeploy:
        catalog = redeploy_catalog()
        profile = catalog.datasheet_by_id(YRIEL).model_profiles[0]
        profile_id = profile.model_profile_id
        assert profile.base_size.diameter_mm is not None
        base_diameter_mm = profile.base_size.diameter_mm
        config = replace(
            config,
            allow_legacy_non_strict_rosters=True,
            army_catalog=catalog,
            army_muster_requests=tuple(
                ArmyMusterRequest(
                    army_id=army_id,
                    player_id=owner,
                    catalog_id=catalog.catalog_id,
                    source_package_id=catalog.source_package_id,
                    ruleset_id=catalog.ruleset_id,
                    detachment_selection=DetachmentSelection(
                        faction_id="AE", detachment_ids=("corsair-coterie",)
                    ),
                    force_disposition_id=disposition,
                    unit_selections=(
                        UnitMusterSelection(
                            unit_selection_id="large",
                            datasheet_id=YRIEL,
                            model_profile_selections=(ModelProfileSelection(profile_id, 1),),
                        ),
                    ),
                )
                for owner, army_id, disposition in (
                    ("player-a", "army-alpha", "take-and-hold"),
                    ("player-b", "army-beta", "purge-the-foe"),
                )
            ),
        )
    body = evidence("order128-body", GeometryMeasurementKind.FOOTPRINT, "diameter", body_diameter)
    base = evidence(
        "order128-base", GeometryMeasurementKind.SUPPORT_BASE, "diameter", base_diameter_mm / 25.4
    )
    height = evidence("order128-height", GeometryMeasurementKind.HEIGHT, "height", 2)
    geometry = ModelGeometryCatalogRecord(
        model_geometry_id="order128-synthetic-body",
        model_profile_id=profile_id,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
        footprint=footprint("order128-body", body),
        support_base=footprint("order128-base", base),
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(body, base, height),
        source_ids=("order128-fixture:analytical-cylinder",),
    )
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        battlefield_layout_id=None,
        deployment_map_id="order128-custom-deployment",
        terrain_layout_id="order128-custom-terrain",
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
        deployment_zones=(
            DeploymentZone.rectangle(
                "order128-a", "player-a", min_x=0, min_y=0, max_x=zone_width, max_y=44
            ),
            DeploymentZone.rectangle(
                "order128-b", "player-b", min_x=60 - zone_width, min_y=0, max_x=60, max_y=44
            ),
        ),
    )
    return replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
        model_geometries=(geometry,),
        reserve_unit_points=tuple(
            ReserveUnitPointValue(f"{army}:large", 10, "fixture:points")
            for army in ("army-alpha", "army-beta")
        )
        if reserves
        else (),
    )


def deployment_session(
    *, player_id: str = "player-a", impossible: bool = False
) -> tuple[LocalGameSession, DecisionRequest]:
    session = LocalGameSession()
    session.start(setup_config(zone_width=6 if impossible else 18))
    for i in range(20):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_deployment_placement":
            if request.actor_id == player_id:
                return session, request
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _i, owner, _id: Pose.at(
                    (3 if owner == "player-a" else 57)
                    if impossible
                    else (8 if owner == "player-a" else 52),
                    30,
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id=f"setup:{i}"
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            option = (
                "fixed:assassination:bring_it_down"
                if request.decision_type == "select_secondary_missions"
                else request.options[0].option_id
            )
            session.submit_option(
                request_id=request.request_id, option_id=option, result_id=f"setup:{i}"
            )
    raise AssertionError("Deployment boundary not reached")


def assert_checkpoint(session: LocalGameSession) -> None:
    checkpoint = session.to_persistence_payload()
    for recovered in (
        LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint))),
        session.fork(),
    ):
        assert recovered.lifecycle.to_payload() == session.lifecycle.to_payload()
        assert recovered.to_persistence_payload() == checkpoint
        for role in PrincipalRole:
            for player in (
                ("player-a", "player-b")
                if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
                else (None,)
            ):
                viewer = ViewerContext(
                    principal_id=f"order128:{role}:{player}",
                    role=role,
                    viewer_player_id=player,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert recovered.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert recovered.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order128-setup"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


def reserve_session(
    *, body_diameter: float = 8, player_id: str = "player-a", enemy: bool = False
) -> tuple[LocalGameSession, DecisionRequest]:
    session = LocalGameSession()
    session.start(setup_config(body_diameter=body_diameter, reserves=True))
    for index in range(120):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        if request.decision_type == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _index, _owner, _id: Pose.at(52, 11.5),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id=f"reserve-deploy:{index}"
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
            continue
        if (
            request.decision_type == "select_movement_unit"
            and state.battle_round == 2
            and request.actor_id == player_id
        ):
            army = "army-alpha" if player_id == "player-a" else "army-beta"
            option = next(o.option_id for o in request.options if f"{army}:large" in o.option_id)
        elif request.decision_type == "select_movement_action":
            option = (
                "ingress"
                if state.battle_round == 2 and request.actor_id == player_id
                else "remain_stationary"
            )
        elif request.decision_type == "submit_placement_proposal":
            assert state.battle_round == 2
            assert request.actor_id == player_id
            return session, request
        elif request.decision_type == "select_secondary_missions":
            option = "fixed:assassination:bring_it_down"
        elif request.decision_type == "select_reserve_declaration":
            army = "army-alpha" if request.actor_id == "player-a" else "army-beta"
            target = f"declare_strategic_reserves:{army}:large"
            option = (
                target
                if (not enemy or request.actor_id == player_id)
                and any(o.option_id == target for o in request.options)
                else "complete_reserve_declarations"
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
            request_id=request.request_id, option_id=option, result_id=f"reserve-setup:{index}"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Reserve ingress boundary not reached")


def redeploy_session(*, impossible: bool) -> tuple[LocalGameSession, DecisionRequest]:
    """Actual Prince Yriel catalog ability, with synthetic geometry declared up front."""
    session = LocalGameSession()
    session.start(setup_config(zone_width=6 if impossible else 18, redeploy=True))
    for index in range(30):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_redeploy_placement":
            return session, request
        if request.decision_type == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _i, owner, _id: Pose.at(
                    (4 if owner == "player-a" else 56)
                    if impossible
                    else (8 if owner == "player-a" else 52),
                    30,
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id=f"redeploy-setup:{index}"
            )
        else:
            option = (
                "fixed:assassination:bring_it_down"
                if request.decision_type == "select_secondary_missions"
                else next(
                    (o.option_id for o in request.options if o.option_id.startswith("redeploy:")),
                    request.options[0].option_id,
                )
            )
            status = session.submit_option(
                request_id=request.request_id, option_id=option, result_id=f"redeploy-setup:{index}"
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Normal redeploy boundary not reached")
