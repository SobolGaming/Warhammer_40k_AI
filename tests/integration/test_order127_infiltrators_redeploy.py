from __future__ import annotations

import json

import pytest
from tests.order127_helpers import (
    canonical_attached_redeploy_session,
    redeploy_payload,
    redeploy_session,
)

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def assert_checkpoint(session: LocalGameSession) -> None:
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    fork = session.fork()
    for recovered in (restored, fork):
        assert recovered.lifecycle.to_payload() == session.lifecycle.to_payload()
        assert recovered.to_persistence_payload() == checkpoint
        for role in PrincipalRole:
            for player_id in (
                ("player-a", "player-b")
                if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
                else (None,)
            ):
                viewer = ViewerContext(
                    principal_id=f"order127:{role}:{player_id}",
                    role=role,
                    viewer_player_id=player_id,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert recovered.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert recovered.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order127-redeploy"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.integration
@pytest.mark.parametrize("player_id", ["player-a", "player-b"])
@pytest.mark.parametrize(("x", "y"), [(31, 3), (30, 22)], ids=["midfield", "nonblocking-objective"])
def test_catalog_infiltrators_redeploy_outside_zone_restores_and_replays(
    player_id: str, x: float, y: float
) -> None:
    session, request = redeploy_session(player_id=player_id)
    state = session.lifecycle.state
    assert state is not None
    army_id = "army-alpha" if player_id == "player-a" else "army-beta"
    unit_id = f"{army_id}:rangers"
    assert rules_unit_has_infiltrators(
        state=state, view=rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    )
    if y == 22:
        assert state.mission_setup is not None
        assert not next(
            marker
            for marker in state.mission_setup.objective_markers
            if marker.x_inches == x and marker.y_inches == y
        ).blocks_placement
    assert_checkpoint(session)
    before = session.lifecycle.to_payload()
    fork = session.fork()
    status = fork.submit_parameterized_payload(
        request_id=request.request_id,
        payload=redeploy_payload(fork, request, tuple(Pose.at(x, y + i * 1.8) for i in range(5))),
        result_id="place-redeploy",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    state = fork.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert (
        state.battlefield_state.unit_placement_by_id(unit_id).model_placements[0].pose.position.x
        == x
    )
    record = next(
        record for record in state.prebattle_action_records if record.unit_instance_id == unit_id
    )
    assert record.source_rule_id != "core_rules:redeploy"
    assert isinstance(record.payload, dict)
    assert record.payload["removal_batch"] is not None
    assert record.payload["placement_batch"] is not None
    assert any(
        event.event_type == "prebattle_redeploy_completed"
        for event in fork.lifecycle.decision_controller.event_log.records
    )
    assert_checkpoint(fork)


@pytest.mark.integration
def test_catalog_noninfiltrators_remain_zone_bound_and_invalid_placement_is_atomic() -> None:
    session, request = redeploy_session(target="yriel")
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    records = tuple(state.prebattle_action_records)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=redeploy_payload(session, request, (Pose.at(31, 3),)),
        result_id="invalid-zone",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == battlefield
    assert tuple(state.prebattle_action_records) == records
    assert "deployment_zone_violation" in json.dumps(status.payload)
    assert_checkpoint(session)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("x", "y", "spacing", "enemy_midfield", "code"),
    [
        (31, 12, 1.8, True, "infiltrators_enemy_unit_distance"),
        (50, 3, 1.8, False, "infiltrators_enemy_zone_distance"),
        (0, 3, 1.8, False, "battlefield_edge_crossed"),
        (31, 3, 0, False, "model_overlap"),
        (31, 3, 4, False, "unit_coherency_broken"),
    ],
)
def test_catalog_infiltrator_geometry_rejection_preserves_state_and_retry(
    x: float, y: float, spacing: float, enemy_midfield: bool, code: str
) -> None:
    session, request = redeploy_session(enemy_midfield=enemy_midfield)
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    records = tuple(state.prebattle_action_records)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=redeploy_payload(
            session, request, tuple(Pose.at(x, y + i * spacing) for i in range(5))
        ),
        result_id="invalid-geometry",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert code in json.dumps(status.payload)
    assert state.battlefield_state == battlefield
    assert tuple(state.prebattle_action_records) == records
    assert_checkpoint(session)
    retry = session.advance_until_decision_or_terminal().decision_request
    assert retry is not None
    # A legal wholly-in-zone retry retains Infiltrators' ordinary distance rules.
    status = session.submit_parameterized_payload(
        request_id=retry.request_id,
        payload=redeploy_payload(session, retry, tuple(Pose.at(3, 3 + i * 1.8) for i in range(5))),
        result_id="retry-geometry",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert_checkpoint(session)


@pytest.mark.integration
@pytest.mark.parametrize("all_infiltrators", [True, False])
def test_attached_redeploy_requires_infiltrators_on_every_component(all_infiltrators: bool) -> None:
    session, request = canonical_attached_redeploy_session(all_infiltrators=all_infiltrators)
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=redeploy_payload(
            session, request, tuple(Pose.at(31, 3 + i * 1.5) for i in range(6))
        ),
        result_id="attached-redeploy",
    )
    if all_infiltrators:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        payload = state.prebattle_action_records[-1].payload
        assert isinstance(payload, dict)
        proposal = payload["proposal"]
        assert isinstance(proposal, dict)
        placements = proposal["model_placements"]
        assert isinstance(placements, list)
        assert len(placements) == 6
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "infiltrators_keyword_required" in json.dumps(status.payload)
        assert state.battlefield_state == battlefield
    assert_checkpoint(session)
