"""Order106: source12.03 closest selected target and attainable engagement."""

import json
from typing import cast

import pytest
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _session(
    *,
    attached: bool,
    closest: bool = False,
    source_poses: tuple[Pose, ...] | None = None,
    other_pose: Pose | None = None,
    enemy_attached: bool = False,
) -> LocalGameSession:
    poses = (
        (Pose.at(10, 10), Pose.at(8.5, 10), Pose.at(8.5, 12), Pose.at(7, 10), Pose.at(7, 12))
        if closest
        else (
            Pose.at(10, 10),
            Pose.at(10, 13),
            Pose.at(8.5, 10),
            Pose.at(8.5, 13),
            Pose.at(7, 11.5),
        )
    )
    all_poses = {
        "source": poses if source_poses is None else source_poses,
        "enemy": (Pose.at(12, 10),),
    }
    specs = {"enemy": ("core-character-leader", "core-character-leader", 1)}
    if closest:
        all_poses["other"] = (Pose.at(10, 12.3) if other_pose is None else other_pose,)
        specs["other"] = specs["enemy"]
    if enemy_attached:
        all_poses["enemy"] = (
            Pose.at(10, 12.3),
            Pose.at(11.5, 12.3),
            Pose.at(13, 12.3),
            Pose.at(14.5, 12.3),
            Pose.at(13.5, 10.8),
        )
        all_poses["other"] = (Pose.at(12, 10),)
        specs["enemy"] = ("core-intercessor-like-infantry", "core-intercessor-like", 5)
    if attached:
        all_poses["leader"] = (Pose.at(5.5, 11.5),)
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("source", "leader") if attached else ("source",),
        enemy_unit_ids=("enemy", "other") if closest else ("enemy",),
        origins={key: value[0] for key, value in all_poses.items()},
        poses_by_unit_key=all_poses,
        enemy_unit_specs=specs,
        alpha_unit_specs={"leader": ("core-character-leader", "core-character-leader", 1)}
        if attached
        else None,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "source"),)
        if attached
        else (),
        enemy_attachment_declarations=(AttachmentDeclaration("other", "enemy"),)
        if enemy_attached
        else (),
        game_id=f"order106-{attached}-{closest}",
    )
    return LocalGameSession(lifecycle)


def _submit(
    session: LocalGameSession,
    *,
    closest: bool,
    engage: bool,
    ends: dict[int, Pose] | None = None,
    loop: bool = False,
    target_ids: tuple[str, ...] | None = None,
) -> LifecycleStatus:
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for unit_id in ("army-alpha:source", "army-alpha:leader"):
        if unit_id not in {u.unit_instance_id for a in state.army_definitions for u in a.units}:
            continue
        placement = state.battlefield_state.unit_placement_by_id(unit_id)
        for index, item in enumerate(placement.model_placements):
            end = item.pose
            if unit_id == "army-alpha:source":
                if ends is not None:
                    end = ends.get(index, item.pose)
                elif closest and index == 0:
                    end = Pose.at(10.1, 10.1) if engage else Pose.at(9.9, 10.8)
                elif not closest and index == 1:
                    end = Pose.at(11, 12.5) if engage else Pose.at(10.1, 13)
            poses: tuple[Pose, ...] = (item.pose, end)
            if loop and unit_id == "army-alpha:source" and index == 0:
                poses = (item.pose, Pose.at(10.1, 10), item.pose)
            paths.append((item.model_instance_id, poses))
    payload: dict[str, JsonValue] = {
        "proposal_request_id": move.request_id,
        "proposal_kind": move.proposal_kind.value,
        "unit_instance_id": move.unit_instance_id,
        "movement_phase_action": move.movement_phase_action,
        "movement_mode": "pile_in",
        "pile_in_target_unit_instance_ids": list(target_ids)
        if target_ids is not None
        else (["army-beta:enemy", "army-beta:other"] if closest else ["army-beta:enemy"]),
        "witness": cast(JsonValue, PathWitness.for_paths(tuple(paths)).to_payload()),
    }
    return session.submit_parameterized_payload(
        request_id=request.request_id, result_id=f"pile-{closest}-{engage}", payload=payload
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("closest", [False, True])
def test_pile_in_rejects_switching_target_or_avoidable_nonengagement(
    attached: bool, closest: bool
) -> None:
    session = _session(attached=attached, closest=closest)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    status = _submit(session, closest=closest, engage=False)
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert state.battlefield_state == before
    expected = (
        "moved_model_not_closer_to_closest_selected_unit"
        if closest
        else "pile_in_model_must_reach_required_endpoint"
    )
    assert expected in json.dumps(status.to_payload())
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert (
        _submit(session, closest=closest, engage=True).status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order106-retry"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("closest", [False, True])
def test_pile_in_legal_closest_engagement_restores_and_replays(
    attached: bool, closest: bool
) -> None:
    session = _session(attached=attached, closest=closest)
    session.advance_until_decision_or_terminal()
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    status = _submit(session, closest=closest, engage=True)
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    actual = state.battlefield_state.unit_placement_by_id("army-alpha:source")
    assert actual.model_placements[0 if closest else 1].pose == (
        Pose.at(10.1, 10.1) if closest else Pose.at(11, 12.5)
    )
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order106")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("loop", [False, True])
def test_pile_in_stationary_and_closed_loop_paths(attached: bool, loop: bool) -> None:
    session = _session(attached=attached)
    status = _submit(session, closest=False, engage=False, ends={}, loop=loop)
    if loop:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert "closed_loop_fight_movement" in json.dumps(status.to_payload())
    else:
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        assert (
            ReplayRunner.from_payload(session.replay_artifact(artifact_id="stationary"))
            .run()
            .status
            is ReplayRunStatus.REPRODUCED
        )


def test_pile_in_proven_unattainable_model_may_move_closer_without_engaging() -> None:
    session = _session(
        attached=False,
        source_poses=(
            Pose.at(10, 10),
            Pose.at(10, 13),
            Pose.at(8.3, 10),
            Pose.at(8.3, 13),
            Pose.at(5.5, 11.5),
        ),
    )
    status = _submit(session, closest=False, engage=False, ends={4: Pose.at(5.6, 11.5)})
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="unattainable")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_pile_in_coherency_unresolved_does_not_invent_unattainability() -> None:
    session = _session(
        attached=False,
        source_poses=(
            Pose.at(10, 10),
            Pose.at(7.3, 10),
            Pose.at(4.1, 10),
            Pose.at(4.1, 12),
            Pose.at(4.1, 8),
        ),
    )
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    status = _submit(session, closest=False, engage=False, ends={1: Pose.at(7.35, 10)})
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert "pile_in_reachability_unresolved" in json.dumps(status.to_payload())
    assert state.battlefield_state == before


def test_pile_in_tied_closest_targets_allow_either_target() -> None:
    session = _session(attached=False, closest=True, other_pose=Pose.at(10, 12))
    status = _submit(session, closest=True, engage=True, ends={0: Pose.at(9.9, 10.5)})
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="tied")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached", [False, True])
def test_pile_in_closest_identity_is_attached_target_unit_not_one_component(attached: bool) -> None:
    session = _session(attached=attached, closest=True, enemy_attached=True)
    status = _submit(
        session, closest=True, engage=False, target_ids=("attached-unit:army-beta:enemy",)
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="attached-target"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
