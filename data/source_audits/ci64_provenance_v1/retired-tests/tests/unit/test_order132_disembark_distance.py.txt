"""Inclusive authoritative circular containment and real disembark continuation."""

from __future__ import annotations

import json
from dataclasses import replace
from math import cos, radians, sin
from typing import cast

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID
from tests.order97_gap_probes_18_25 import disembark_band_resolution
from tests.order132_disembark_helpers import (
    boundary_proposal,
    boundary_session,
    move_transport,
    move_unit,
    select_options,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.transport_disembark_geometry import (
    _model_wholly_within_any_transport_model,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.transports import TransportOperationViolationCode
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.measurement import (
    DistanceMeasurementContext,
    DistancePredicateEvaluator,
    WhollyWithinPredicate,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("mode", ["rapid_disembark", "tactical_disembark"])
@pytest.mark.parametrize("distance", [2.99, 3, 3.01])
def test_retained_probe_now_accepts_inclusive_boundary(mode: str, distance: float) -> None:
    result = disembark_band_resolution(mode, distance)
    assert result.is_valid is (distance <= 3), result.violations
    assert (
        TransportOperationViolationCode.DISEMBARK_DISTANCE
        in {violation.violation_code for violation in result.violations}
    ) is (distance > 3)


@pytest.mark.parametrize("angle", [0, 17, 30, 90, 137, 270])
@pytest.mark.parametrize("delta", [-1e-7, 0, 1e-7])
def test_shared_disk_geometry_uses_analytic_radii(angle: float, delta: float) -> None:
    source = Model("source", Pose.at(10, 10), CircularBase(2), ModelVolume(1))
    radius = 4.5 + delta
    target = Model(
        "target",
        base=CircularBase(0.5),
        volume=ModelVolume(1),
        pose=Pose.at(10 + radius * cos(radians(angle)), 10 + radius * sin(radians(angle))),
    )
    context = DistanceMeasurementContext.from_models(source, target)
    assert context.target_wholly_within_distance(3, horizontal_only=True) is (delta <= 0)
    assert DistancePredicateEvaluator(context).evaluate(WhollyWithinPredicate(3)) is (delta <= 0)
    assert DistanceMeasurementContext.from_payload(
        context.to_payload()
    ).target_wholly_within_distance(3) is (delta <= 0)


@pytest.mark.parametrize("frame_source", [False, True])
@pytest.mark.parametrize("frame_target", [False, True])
@pytest.mark.parametrize("distance", [2.99, 3, 3.01])
def test_circular_frame_parts_keep_whole_height_and_horizontal_rules(
    frame_source: bool, frame_target: bool, distance: float
) -> None:
    source = Model(
        "source",
        Pose.at(10, 10),
        CircularBase(2),
        ModelVolume(1),
        measures_every_part=frame_source,
    )
    target = Model(
        "target",
        Pose.at(10 + 2 + distance - 0.5, 10),
        CircularBase(0.5),
        ModelVolume(1),
        measures_every_part=frame_target,
    )
    context = DistanceMeasurementContext.from_models(source, target)
    assert context.target_wholly_within_distance(3, horizontal_only=True) is (distance <= 3)
    assert context.target_wholly_within_distance(3) is (distance <= 3)
    elevated = DistanceMeasurementContext.from_models(
        source, replace(target, pose=Pose.at(target.pose.position.x, target.pose.position.y, 10))
    )
    assert elevated.target_wholly_within_distance(3) is False
    assert elevated.target_wholly_within_distance(3, horizontal_only=True) is (distance <= 3)


@pytest.mark.parametrize("distance_limit", [3, 6])
@pytest.mark.parametrize("delta", [-0.01, 0, 0.01])
def test_every_disembark_distance_band_uses_each_transport_model(
    distance_limit: float, delta: float
) -> None:
    source = Model("transport", Pose.at(10, 10), CircularBase(2), ModelVolume(1))
    remote = replace(source, model_id="remote", pose=Pose.at(40, 40))
    target = Model(
        "passenger",
        Pose.at(10 + 1.5 + distance_limit + delta, 10),
        CircularBase(0.5),
        ModelVolume(1),
    )
    assert _model_wholly_within_any_transport_model(
        target,
        transport_models=(remote, source),
        distance_inches=distance_limit,
    ) is (delta <= 0)
    assert (
        _model_wholly_within_any_transport_model(
            target,
            transport_models=(remote,),
            distance_inches=distance_limit,
        )
        is False
    )


@pytest.mark.parametrize("delta", [-0.01, 0, 0.01])
def test_marker_context_shared_with_cult_ambush_keeps_inclusive_boundary(delta: float) -> None:
    marker_radius = 40 / 50.8
    target = Model(
        "returning-model",
        Pose.at(10 + marker_radius + 3 - 0.5 + delta, 10),
        CircularBase(0.5),
        ModelVolume(1),
    )
    context = DistanceMeasurementContext.from_objective_marker_to_model(
        marker_id="marker",
        marker_pose=Pose.at(10, 10),
        model=target,
    )
    assert context.target_wholly_within_distance(3, horizontal_only=True) is (delta <= 0)


def test_large_coordinate_roundoff_cannot_authorize_material_outside_gap() -> None:
    source = Model("source", Pose.at(1e20, 1e20), CircularBase(2), ModelVolume(1))
    target = Model(
        "target",
        Pose.at(1e20 + 16384, 1e20),
        CircularBase(0.5),
        ModelVolume(1),
    )
    assert (
        DistanceMeasurementContext.from_models(source, target).target_wholly_within_distance(
            3, horizontal_only=True
        )
        is False
    )


@pytest.mark.parametrize("rapid", [False, True])
def test_facade_invalid_atomicity_retry_restore_fork_views_events_replay(rapid: bool) -> None:
    session = boundary_session(rapid=False)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    if rapid:
        move_transport(session)
    select_options(session, (PASSENGER_ID, "disembark"), prefix="order132:first")
    pending = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(pending).to_payload() == pending
    state = session.lifecycle.state
    assert state is not None
    battlefield, cargo = state.battlefield_state, tuple(state.transport_cargo_states)
    invalid = boundary_proposal(session, distance=3.01, rapid=rapid)
    stale = replace(invalid, proposal_request_id="order132:stale")
    stale_result = session.submit_parameterized_payload(
        request_id=invalid.proposal_request_id,
        result_id="order132:stale-attempt",
        payload=validate_json_value(stale.to_payload()),
    )
    assert stale_result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == pending
    result = session.submit_parameterized_payload(
        request_id=invalid.proposal_request_id,
        result_id="order132:outside",
        payload=validate_json_value(invalid.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == battlefield
    assert tuple(state.transport_cargo_states) == cargo
    assert pending_request(session).decision_type == "select_movement_unit"
    failed = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(failed).to_payload() == failed
    select_options(session, (PASSENGER_ID, "disembark"), prefix="order132:retry")
    proposal = boundary_proposal(session, distance=3, rapid=rapid)
    fork = session.fork()
    fork_before = fork.lifecycle.to_payload()
    result = session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="order132:exact",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    assert state.battlefield_state is not None
    assert (
        state.battlefield_state.unit_placement_by_id(PASSENGER_ID) == proposal.attempted_placement
    )
    assert not state.transport_cargo_states[0].contains_unit(PASSENGER_ID)
    assert fork.lifecycle.to_payload() == fork_before
    restored = LocalGameSession.from_persistence_payload(
        cast(JsonValue, json.loads(json.dumps(session.to_persistence_payload())))
    )
    snapshot = session.lifecycle.to_payload()
    assert restored.lifecycle.to_payload() == snapshot
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
    for role in PrincipalRole:
        context = ViewerContext(
            principal_id=f"order132:{role.value}",
            role=role,
            viewer_player_id="player-a"
            if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
            else None,
            policy=ROLE_POLICY_BY_ROLE[role],
        )
        assert session.view_for_context(viewer=context) == restored.view_for_context(viewer=context)
        assert session.events_since_for_context(
            EventStreamCursor(), viewer=context
        ) == restored.events_since_for_context(EventStreamCursor(), viewer=context)
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order132",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
    fork_proposal = replace(
        proposal,
        attempted_placement=boundary_proposal(fork, distance=2.99, rapid=rapid).attempted_placement,
    )
    assert (
        fork.submit_parameterized_payload(
            request_id=fork_proposal.proposal_request_id,
            result_id="order132:fork:inside",
            payload=validate_json_value(fork_proposal.to_payload()),
        ).status_kind
        is not LifecycleStatusKind.INVALID
    )
    assert session.lifecycle.to_payload() == snapshot
    if rapid:
        select_options(
            restored,
            ("army-alpha:remaining-unit", "remain_stationary"),
            prefix="order132:continued",
        )
    else:
        select_options(restored, ("normal_move",), prefix="order132:tactical:followup")
        move_unit(restored, unit_id=PASSENGER_ID, prefix="order132:continued", dy=0.1)
        request = pending_request(restored)
        if request.decision_type == "select_embark_transport":
            select_options(restored, ("decline_embark",), prefix="order132:continued:decline")
    continued = restored.lifecycle.to_payload()
    assert GameLifecycle.from_payload(continued).to_payload() == continued
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order132:continuation",
            initial_lifecycle_payload=initial,
            final_lifecycle=restored.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
    assert session.lifecycle.to_payload() == snapshot
