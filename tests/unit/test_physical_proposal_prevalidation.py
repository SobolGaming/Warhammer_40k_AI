"""C03-04: prevalidation must preserve replayable authority and typed diagnostics."""

from __future__ import annotations

import copy
import json

import pytest
from tests.physical_proposal_prevalidation_helpers import FAMILIES, proposal_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.network import submit_network_parameterized_payload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("change", ["empty", "kind", "unit", "request", "shape", "nested"])
def test_malformed_physical_proposal_is_typed_and_leaves_all_authority_unchanged(
    family: str,
    change: str,
) -> None:
    session, request, payload = proposal_session(family)
    malformed: JsonValue = copy.deepcopy(payload)
    assert isinstance(malformed, dict)
    if change == "empty":
        malformed = {}
    elif change == "shape":
        malformed = []
    elif change == "nested":
        malformed["attempted_placement" if family == "placement" else "witness"] = {
            "model_paths": [None]
        }
    else:
        malformed[
            {"kind": "proposal_kind", "unit": "unit_instance_id", "request": "proposal_request_id"}[
                change
            ]
        ] = "not-the-pending-value"
    before = copy.deepcopy(session.lifecycle.to_payload())
    views = {viewer: session.view(viewer_player_id=viewer) for viewer in ("player-a", "player-b")}
    deltas = {
        viewer: session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        for viewer in views
    }
    outcome = submit_network_parameterized_payload(
        session,
        {
            "request_id": request.request_id,
            "result_id": "order76-malformed",
            "payload": malformed,
        },
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    json.dumps(outcome.to_payload(), allow_nan=False)
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    for viewer in views:
        assert session.view(viewer_player_id=viewer) == views[viewer]
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer) == deltas[viewer]


@pytest.mark.parametrize("family", FAMILIES)
def test_rejected_physical_proposal_restores_and_replays_before_and_after_valid_retry(
    family: str,
) -> None:
    session, request, payload = proposal_session(family)
    malformed = {**payload, "proposal_kind": "not-a-kind"}
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, payload=malformed, result_id="order76-reject"
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    for stage in ("rejected", "retried"):
        if stage == "retried":
            outcome = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id="order76-retry"
            )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID
        replay = ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"order76-{family}-{stage}")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()
        checkpoint = json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("change", ["empty", "kind", "unit"])
def test_destroyed_transport_prevalidation_preserves_replay_and_defender_request(
    change: str,
) -> None:
    from tests.emergency_geometry_helpers import emergency_geometry_session

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    session, proposal = emergency_geometry_session(attached=True, rectangular=False)
    # Activate runtime-content audit through the canonical loader, as the
    # attack-executor fixture predates the session's normal startup path.
    session = LocalGameSession(GameLifecycle.from_payload(session.lifecycle.to_payload()))
    # This canonical fixture starts after the destroying attack, including its
    # recorded decisions. Capture that boundary as this test's replay origin.
    session._initial_replay_lifecycle_payload = session.lifecycle.to_payload()  # pyright: ignore[reportPrivateUsage]
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.actor_id == "player-b"
    payload = validate_json_value(proposal.to_payload())
    assert isinstance(payload, dict)
    malformed = (
        {}
        if change == "empty"
        else {**payload, "proposal_kind" if change == "kind" else "unit_instance_id": "not-pending"}
    )
    before = copy.deepcopy(session.lifecycle.to_payload())
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, payload=malformed, result_id="order76-invalid-emergency"
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="emergency-rejected"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    assert LocalGameSession.from_persistence_payload(checkpoint).lifecycle.to_payload() == before
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-emergency-retry"
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="emergency-retried"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("family", ["surge", "charge", "normal", "placement", "fight"])
def test_spatial_drift_diagnostic_is_pure_and_retry_replays_after_context_is_restored(
    family: str,
) -> None:
    from warhammer40k_core.geometry.pose import Pose

    session, request, payload = proposal_session(family)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    original = state.battlefield_state
    # Deliberately drift real authoritative geometry at this boundary; restore it
    # before replay, which must never contain this fixture-only change.
    placement = next(
        placement for army in original.placed_armies for placement in army.unit_placements
    )
    moved = placement.with_model_placements(
        tuple(
            model.with_pose(
                Pose.at(model.pose.position.x + 0.01, model.pose.position.y, model.pose.position.z)
            )
            for model in placement.model_placements
        )
    )
    state.replace_battlefield_state(original.with_unit_placement(moved))
    before = copy.deepcopy(session.lifecycle.to_payload())
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-spatial-drift"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(invalid.payload, dict)
    assert "spatial_context_drift" in json.dumps(invalid.payload)
    assert session.lifecycle.to_payload() == before
    state.replace_battlefield_state(original)
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-spatial-retry"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="spatial-retry")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("malformation", ["witness_null", "coordinate", "pose", "model_movements"])
def test_surge_nested_payload_errors_have_typed_diagnostics(malformation: str) -> None:
    session, request, payload = proposal_session("surge")
    if malformation == "witness_null":
        payload["witness"] = None
    elif malformation == "model_movements":
        payload["model_movements"] = 123
    else:
        witness = payload["witness"]
        assert isinstance(witness, dict)
        paths = witness["model_paths"]
        assert isinstance(paths, list)
        first = paths[0]
        assert isinstance(first, dict)
        if malformation == "pose":
            first["poses"] = [{"position": {}}]
        else:
            first["poses"] = [{"position": {"x": "bad", "y": 0, "z": 0}, "facing": {"degrees": 0}}]
    before = copy.deepcopy(session.lifecycle.to_payload())
    result = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-nested"
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_headless_malformed_submission_uses_the_same_pure_boundary() -> None:
    from dataclasses import dataclass

    from warhammer40k_core.adapters.headless import submit_headless_decision
    from warhammer40k_core.adapters.projection import GameViewPayload
    from warhammer40k_core.engine.decision_request import DecisionRequest

    @dataclass(frozen=True)
    class Producer:
        payload: JsonValue

        def choose_option(self, *, request: DecisionRequest, view: GameViewPayload) -> str:
            return request.options[0].option_id

        def generate_payload(self, *, request: DecisionRequest, view: GameViewPayload) -> JsonValue:
            return self.payload

    session, request, _ = proposal_session("surge")
    status = session.advance_until_decision_or_terminal()
    before = copy.deepcopy(session.lifecycle.to_payload())
    producer = Producer({})
    assert request.actor_id is not None
    result = submit_headless_decision(
        session=session,
        status=status,
        viewer_player_id=request.actor_id,
        result_id="order76-headless",
        finite_option_ranker=producer,
        parameterized_payload_generator=producer,
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
