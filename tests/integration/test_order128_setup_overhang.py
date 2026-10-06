from __future__ import annotations

import json

import pytest
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order128_helpers import assert_checkpoint, deployment_session, reserve_session

from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("body_diameter", [6.0, 8.0])
def test_cutout_zone_legal_impossible_body_fit_and_avoidable_retry(body_diameter: float) -> None:
    from dataclasses import replace

    from tests.order128_helpers import setup_config

    from warhammer40k_core.core.deployment_zones import (
        DeploymentZone,
        DeploymentZonePoint,
        DeploymentZonePolygonCutout,
        DeploymentZoneShape,
    )
    from warhammer40k_core.engine.mission_state_validation import (
        runtime_ruleset_descriptor_for_mission_setup,
    )

    config = setup_config(body_diameter=body_diameter)
    mission = config.mission_setup
    assert mission is not None
    shape = replace(
        DeploymentZoneShape.rectangle(min_x=0, min_y=18, max_x=14, max_y=32),
        cutouts=(
            DeploymentZonePolygonCutout(
                tuple(DeploymentZonePoint(x, y) for x, y in ((6, 18), (8, 18), (8, 32), (6, 32)))
            ),
        ),
    )
    mission = replace(
        mission,
        deployment_zones=(
            DeploymentZone("order128-cutout", "player-a", shape),
            mission.deployment_zones[1],
        ),
    )
    config = replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session, request = deployment_session(config=config)
    assert_checkpoint(session)
    assert session.lifecycle.state is not None
    before = session.lifecycle.state.battlefield_state
    payload = deployment_placement_payload_for_request(
        session.lifecycle,
        request=request,
        pose_factory=lambda _i, _owner, _id: Pose.at(11.5, 25),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="cutout-body"
    )
    if body_diameter == 6:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "deployment_zone_violation" in json.dumps(status.payload)
        assert session.lifecycle.state is not None
        assert session.lifecycle.state.battlefield_state == before
        assert_checkpoint(session)
        retry = session.advance_until_decision_or_terminal().decision_request
        assert retry is not None
        payload = deployment_placement_payload_for_request(
            session.lifecycle,
            request=retry,
            pose_factory=lambda _i, _owner, _id: Pose.at(11, 25),
        )
        status = session.submit_parameterized_payload(
            request_id=retry.request_id, payload=payload, result_id="cutout-retry"
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert_checkpoint(session)


@pytest.mark.parametrize(
    ("body_diameter", "enemy"),
    [(6.0, False), (8.0, False), (50.0, False), (8.0, True)],
    ids=["avoidable", "edge-band-impossible", "field-impossible", "enemy-distance"],
)
def test_catalog_strategic_reserve_whole_body_fit_and_impossible_exception(
    body_diameter: float,
    enemy: bool,
) -> None:
    from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalRequest,
        PlacementProposalPayload,
    )

    session, request = reserve_session(body_diameter=body_diameter, enemy=enemy)
    assert_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    army = state.army_definition_for_player("player-a")
    assert army is not None
    unit = army.unit_by_id(context.unit_instance_id)
    attempted = UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=Pose.at(52 if enemy else 5, 2.5),
            ),
        ),
    )
    payload = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=context.unit_instance_id,
        placement_kind=context.placement_kinds[0],
        attempted_placement=attempted,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(payload.to_payload()),
        result_id="reserve-body",
    )
    if body_diameter >= 8 and not enemy:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert ("reserve_enemy_distance" if enemy else "battlefield_edge_crossed") in json.dumps(
            status.payload
        )
        assert state.battlefield_state == before
        assert_checkpoint(session)
        retry_request = session.advance_until_decision_or_terminal().decision_request
        assert retry_request is not None
        request = retry_request
        if request.decision_type == "select_movement_unit":
            status = session.submit_option(
                request_id=request.request_id,
                option_id=unit.unit_instance_id,
                result_id="reserve-reselect",
            )
            retry_request = status.decision_request
            assert retry_request is not None
            request = retry_request
        if request.decision_type == "select_movement_action":
            status = session.submit_option(
                request_id=request.request_id,
                option_id="ingress",
                result_id="reserve-retry-ingress",
            )
            retry_request = status.decision_request
            assert retry_request is not None
            request = retry_request
        context = MovementProposalRequest.from_decision_request_payload(request.payload)
        attempted = attempted.with_model_placements(
            tuple(
                placement.with_pose(Pose.at(5, 2.5 if enemy else 3.5))
                for placement in attempted.model_placements
            )
        )
        payload = PlacementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=context.proposal_kind,
            unit_instance_id=context.unit_instance_id,
            placement_kind=context.placement_kinds[0],
            attempted_placement=attempted,
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=validate_json_value(payload.to_payload()),
            result_id="reserve-body-retry",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert_checkpoint(session)


@pytest.mark.parametrize("player_id", ["player-a", "player-b"])
@pytest.mark.parametrize("impossible", [False, True])
def test_catalog_deployment_body_fit_atomic_retry_restore_fork_views_events_replay(
    player_id: str, impossible: bool
) -> None:
    session, request = deployment_session(player_id=player_id, impossible=impossible)
    assert_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    fork = session.fork()
    payload = deployment_placement_payload_for_request(
        fork.lifecycle,
        request=request,
        pose_factory=lambda _i, _owner, _id: Pose.at(2.5 if player_id == "player-a" else 57.5, 30),
    )
    status = fork.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="body-overhang"
    )
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.battlefield_state == before
    if impossible:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "deployment_zone_violation" in json.dumps(status.payload)
        assert fork.lifecycle.state is not None
        assert fork.lifecycle.state.battlefield_state == before
        assert_checkpoint(fork)
        retry_request = fork.advance_until_decision_or_terminal().decision_request
        assert retry_request is not None
        request = retry_request
        payload = deployment_placement_payload_for_request(
            fork.lifecycle,
            request=request,
            pose_factory=lambda _i, _owner, _id: Pose.at(8 if player_id == "player-a" else 52, 30),
        )
        status = fork.submit_parameterized_payload(
            request_id=request.request_id, payload=payload, result_id="body-fit-retry"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert any(
        event.event_type == "battlefield_models_placed"
        for event in fork.lifecycle.decision_controller.event_log.records
    )
    assert_checkpoint(fork)


@pytest.mark.parametrize("impossible", [False, True])
def test_normal_catalog_redeploy_consumes_body_fit_authority(impossible: bool) -> None:
    from tests.order127_helpers import redeploy_payload
    from tests.order128_helpers import redeploy_session

    session, request = redeploy_session(impossible=impossible)
    assert_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    owner = request.actor_id
    assert owner in {"player-a", "player-b"}
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=redeploy_payload(
            session,
            request,
            (
                Pose.at(
                    (4 if owner == "player-a" else 56)
                    if impossible
                    else (2.5 if owner == "player-a" else 57.5),
                    30,
                ),
            ),
        ),
        result_id="redeploy-body-overhang",
    )
    if impossible:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "deployment_zone_violation" in json.dumps(status.payload)
        assert state.battlefield_state == before
        assert_checkpoint(session)
        retry = session.advance_until_decision_or_terminal().decision_request
        assert retry is not None
        status = session.submit_parameterized_payload(
            request_id=retry.request_id,
            payload=redeploy_payload(
                session, retry, (Pose.at(8 if owner == "player-a" else 52, 30),)
            ),
            result_id="redeploy-body-retry",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert any(
        event.event_type == "prebattle_redeploy_completed"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    assert_checkpoint(session)


def test_body_exception_keeps_base_and_submission_boundaries_atomic() -> None:
    session, request = deployment_session(impossible=True)
    for label in ("base-outside", "stale", "wrong-owner", "malformed"):
        fork = session.fork()
        before = fork.to_persistence_payload()

        def boundary_pose(
            _index: int, _owner: str, _model_id: str, *, boundary: str = label
        ) -> Pose:
            return Pose.at(2 if boundary == "base-outside" else 3, 30)

        payload = deployment_placement_payload_for_request(
            fork.lifecycle,
            request=request,
            pose_factory=boundary_pose,
        )
        if label == "stale":
            payload["proposal_request_id"] = "stale-order128-request"
        elif label == "wrong-owner":
            payload["player_id"] = "player-b"
        elif label == "malformed":
            payload.pop("model_placements")
        status = fork.submit_parameterized_payload(
            request_id=request.request_id, payload=payload, result_id=f"boundary:{label}"
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert fork.lifecycle.state is not None
        assert session.lifecycle.state is not None
        assert fork.lifecycle.state.battlefield_state == session.lifecycle.state.battlefield_state
        if label != "base-outside":
            assert fork.to_persistence_payload() == before
        assert_checkpoint(fork)
