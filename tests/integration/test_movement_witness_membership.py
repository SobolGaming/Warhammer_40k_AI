"""Wrong physical inventories cannot consume native movement decisions."""

import json
from dataclasses import replace

import pytest
from tests.movement_witness_membership_helpers import (
    native_movement_request,
    proposal_json,
    public_models,
    public_movement_proposal,
    quiet_choice,
)

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import ModelPath, PathWitness


def _viewers() -> tuple[ViewerContext, ...]:
    return tuple(
        ViewerContext(
            principal_id=f"witness:{role}:{player}",
            role=role,
            viewer_player_id=player,
            policy=ROLE_POLICY_BY_ROLE[role],
        )
        for role in PrincipalRole
        for player in (
            ("player-a", "player-b")
            if role in (PrincipalRole.PLAYER, PrincipalRole.COACH)
            else (None,)
        )
    )


def _assert_same_views(left: LocalGameSession, right: LocalGameSession) -> None:
    for viewer in _viewers():
        assert left.view_for_context(viewer=viewer) == right.view_for_context(viewer=viewer)
        assert left.events_since_for_context(
            EventStreamCursor(), viewer=viewer
        ) == right.events_since_for_context(EventStreamCursor(), viewer=viewer)


def _assert_replay(session: LocalGameSession) -> None:
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="witness:exact-replay")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance", "fall_back"])
@pytest.mark.integration
@pytest.mark.replay
def test_native_wrong_witness_inventory_is_atomic_with_legal_retry_and_continuation(
    player: str, attached: bool, action: str
) -> None:
    session, request = native_movement_request(player=player, attached=attached, action=action)
    dx = (-3 if player == "player-a" else 3) if action == "fall_back" else 0.5
    proposal = public_movement_proposal(session, request, dx=dx)
    paths = proposal.witness.model_paths
    models = public_models(session, player)
    assert len(paths) == (
        (2 if attached else 1) if action == "fall_back" else (6 if attached else 5)
    )
    assert len({models[key]["unit_instance_id"] for key, _poses in paths}) == (2 if attached else 1)
    original = json.loads(json.dumps(session.to_persistence_payload()))
    before = json.loads(json.dumps(session.lifecycle.to_payload()))
    restored = LocalGameSession.from_persistence_payload(original)
    fork = session.fork()
    assert restored.lifecycle.to_payload() == fork.lifecycle.to_payload() == before
    _assert_same_views(session, restored)
    _assert_same_views(session, fork)
    foreign = next(
        row["model_instance_id"]
        for row in models.values()
        if row["owner_player_id"] != player and row["state"] == "placed"
    )
    invalid_paths: dict[str, tuple[ModelPath, ...]] = {
        "foreign": ((foreign, paths[0][1]), *paths[1:]),
        "unknown": (("witness:unknown-model", paths[0][1]), *paths[1:]),
        "extra": (*paths, (foreign, paths[0][1])),
    }
    if len(paths) > 1:
        invalid_paths["missing"] = paths[1:]
    else:
        # Complete omission fails the existing nonempty PathWitness wire contract.
        empty_payload = proposal_json(proposal)
        assert isinstance(empty_payload, dict)
        empty_payload["witness"] = {"model_paths": []}
        empty_status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="witness:empty-inventory",
            payload=empty_payload,
        )
        assert empty_status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
        assert session.to_persistence_payload() == original
    if attached:
        leader_ids = {
            key for key, _poses in paths if models[key]["unit_instance_id"].endswith(":leader")
        }
        assert len(leader_ids) == 1
        invalid_paths["missing_leader_component"] = tuple(
            item for item in paths if item[0] not in leader_ids
        )
        invalid_paths["missing_bodyguard_component"] = tuple(
            item for item in paths if item[0] in leader_ids
        )
    for label, invalid in invalid_paths.items():
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"witness:invalid:{label}",
            payload=proposal_json(replace(proposal, witness=PathWitness.for_paths(invalid))),
        )
        assert status.status_kind is LifecycleStatusKind.INVALID, status
        assert isinstance(status.payload, dict)
        diagnostic = status.payload["proposal_validation"]
        assert isinstance(diagnostic, dict)
        assert diagnostic["violations"] == [
            {
                "violation_code": "movement_witness_model_inventory_mismatch",
                "message": "Movement witness must match every placed rules-unit model.",
                "field": "witness",
            }
        ]
        # Includes pending queue, records, events, RNG, gameplay and result counters.
        assert session.lifecycle.to_payload() == before
        assert session.to_persistence_payload() == original
        _assert_same_views(session, restored)
        _assert_same_views(session, fork)
    accepted = fork.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="witness:legal-retry",
        payload=proposal_json(proposal),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload() == before
    for other in (session, restored):
        status = other.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="witness:legal-retry",
            payload=proposal_json(proposal),
        )
        assert status.to_payload() == accepted.to_payload()
        assert other.lifecycle.to_payload() == fork.lifecycle.to_payload()
        _assert_same_views(other, fork)
    placed = public_models(session, player)
    assert all(placed[key]["pose"] != models[key]["pose"] for key, _poses in paths)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    loaded = LocalGameSession.from_persistence_payload(checkpoint)
    assert loaded.lifecycle.to_payload() == session.lifecycle.to_payload()
    _assert_same_views(session, loaded)
    _assert_replay(session)
    for other in (fork, session, restored, loaded):
        continuation = other.advance_until_decision_or_terminal().decision_request
        assert continuation is not None
        quiet_choice(other, continuation)
    assert fork.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        restored.lifecycle.to_payload()
        == loaded.lifecycle.to_payload()
        == session.lifecycle.to_payload()
    )
    _assert_same_views(session, loaded)
    _assert_replay(loaded)


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.integration
def test_native_rule_invalid_geometry_still_records_attempt_and_emits_fresh_retry(
    attached: bool,
) -> None:
    session, request = native_movement_request(attached=attached)
    proposal = public_movement_proposal(session, request, dx=200)
    records = session.decision_record_count()
    before_models = public_models(session, "player-a")
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="witness:rule-invalid-distance",
        payload=proposal_json(proposal),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert session.decision_record_count() == records + 1
    assert public_models(session, "player-a") == before_models
    retry = session.advance_until_decision_or_terminal().decision_request
    assert retry is not None
    assert retry.decision_type == request.decision_type
    assert retry.request_id != request.request_id
    legal = session.submit_parameterized_payload(
        request_id=retry.request_id,
        result_id="witness:geometry-legal-retry",
        payload=proposal_json(public_movement_proposal(session, retry)),
    )
    assert legal.status_kind is not LifecycleStatusKind.INVALID, legal
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    _assert_replay(restored)
