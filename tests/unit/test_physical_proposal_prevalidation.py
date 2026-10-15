from __future__ import annotations

from tests.shared.category_migration.physical_proposal_prevalidation import (
    FAMILIES,
    EventStreamCursor,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    ReplayRunner,
    ReplayRunStatus,
    copy,
    json,
    proposal_session,
    pytest,
    submit_network_parameterized_payload,
)


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("change", ["empty", "kind", "unit", "coordinate", "overflow"])
def test_destroyed_transport_prevalidation_preserves_replay_and_defender_request(
    change: str,
    attached: bool,
) -> None:
    from tests.emergency_geometry_helpers import emergency_geometry_session

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    session, proposal = emergency_geometry_session(attached=attached, rectangular=False)
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
    malformed = copy.deepcopy(payload)
    if change == "empty":
        malformed = {}
    elif change in {"kind", "unit"}:
        malformed["proposal_kind" if change == "kind" else "unit_instance_id"] = "not-pending"
    else:
        placement = malformed[
            "attempted_rules_unit_placement" if attached else "attempted_placement"
        ]
        assert isinstance(placement, dict)
        if attached:
            components = placement["component_unit_placements"]
            assert isinstance(components, list)
            placement = components[0]
            assert isinstance(placement, dict)
        models = placement["model_placements"]
        assert isinstance(models, list)
        model = models[0]
        assert isinstance(model, dict)
        pose = model["pose"]
        assert isinstance(pose, dict)
        position = pose["position"]
        assert isinstance(position, dict)
        position["x"] = "bad" if change == "coordinate" else 10**400
    before = copy.deepcopy(session.lifecycle.to_payload())
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, payload=malformed, result_id="order76-invalid-emergency"
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    if change in {"coordinate", "overflow"}:
        assert "proposal_payload_malformed" in json.dumps(outcome.to_payload(), allow_nan=False)
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
    checkpoint = json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
    assert (
        LocalGameSession.from_persistence_payload(checkpoint).lifecycle.to_payload()
        == session.lifecycle.to_payload()
    )


@pytest.mark.parametrize(
    "malformation", ["witness_null", "coordinate", "overflow", "pose", "model_movements"]
)
def test_surge_nested_payload_errors_have_typed_diagnostics(malformation: str) -> None:
    session, request, valid_payload = proposal_session("surge")
    payload = copy.deepcopy(valid_payload)
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
            first["poses"] = [
                {
                    "position": {
                        "x": 10**400 if malformation == "overflow" else "bad",
                        "y": 0,
                        "z": 0,
                    },
                    "facing": {"degrees": 0},
                }
            ]
    before = copy.deepcopy(session.lifecycle.to_payload())
    result = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-nested"
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    if malformation in {"coordinate", "overflow"}:
        assert "proposal_payload_malformed" in json.dumps(result.to_payload(), allow_nan=False)
    for stage in ("rejected", "retried"):
        if stage == "retried":
            accepted = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=valid_payload,
                result_id="order76-nested-retry",
            )
            assert accepted.status_kind is not LifecycleStatusKind.INVALID
        replay = ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"surge-nested-{stage}")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()
        checkpoint = json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
        assert (
            LocalGameSession.from_persistence_payload(checkpoint).lifecycle.to_payload()
            == session.lifecycle.to_payload()
        )


@pytest.mark.parametrize("malformation", ["coordinate", "overflow", "pose", "ownership"])
def test_rapid_ingress_geometry_rejection_preserves_authority_and_retry(malformation: str) -> None:
    from tests.rapid_ingress_helpers import (
        ingress_placement,
        ingress_session,
        reach_ingress_window,
        submit_ingress_target,
    )

    from warhammer40k_core.engine.event_log import validate_json_value

    session = ingress_session(reacting_player="player-b", automatic_discount=False)
    # The canonical fixture starts in round two; capture its real replay origin.
    session._initial_replay_lifecycle_payload = session.lifecycle.to_payload()  # pyright: ignore[reportPrivateUsage]
    request = submit_ingress_target(session, reach_ingress_window(session)).decision_request
    assert request is not None
    payload = validate_json_value(ingress_placement(session, request).to_payload())
    assert isinstance(payload, dict)
    malformed = copy.deepcopy(payload)
    placement = malformed["attempted_placement"]
    assert isinstance(placement, dict)
    models = placement["model_placements"]
    assert isinstance(models, list)
    model = models[0]
    assert isinstance(model, dict)
    if malformation == "pose":
        model["pose"] = None
    elif malformation == "ownership":
        model["unit_instance_id"] = "different-unit"
    else:
        pose = model["pose"]
        assert isinstance(pose, dict)
        position = pose["position"]
        assert isinstance(position, dict)
        position["x"] = "bad" if malformation == "coordinate" else 10**400
    before = copy.deepcopy(session.lifecycle.to_payload())
    views = {viewer: session.view(viewer_player_id=viewer) for viewer in ("player-a", "player-b")}
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order76-invalid-ingress", payload=malformed
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "proposal_payload_malformed" in json.dumps(invalid.to_payload(), allow_nan=False)
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    assert {viewer: session.view(viewer_player_id=viewer) for viewer in views} == views
    for stage in ("rejected", "retried"):
        if stage == "retried":
            accepted = session.submit_parameterized_payload(
                request_id=request.request_id, result_id="order76-ingress-retry", payload=payload
            )
            assert accepted.status_kind is not LifecycleStatusKind.INVALID
        replay = ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"ingress-{stage}")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()
        checkpoint = json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
        assert (
            LocalGameSession.from_persistence_payload(checkpoint).lifecycle.to_payload()
            == session.lifecycle.to_payload()
        )


__all__: list[str] = []
__all__ += ["FAMILIES", "EventStreamCursor", "JsonValue", "submit_network_parameterized_payload"]
