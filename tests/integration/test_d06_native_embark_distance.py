"""Native Embark offer/mutation and persistence share the 3D distance owner."""

import json

import pytest
from tests.d06_embark_helpers import (
    choose,
    default_choice,
    later_diagonal_embark_scene,
    later_embark_scene,
    move_payload,
    propose,
    state_of,
)
from tests.order135_transport_helpers import CARRIER, PASSENGER
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def assert_preserved(session: LocalGameSession) -> None:
    payload = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(payload)))
    fork = session.fork()
    for other in (restored, fork):
        assert other.to_persistence_payload() == payload
        assert other.lifecycle.to_payload() == session.lifecycle.to_payload()
        for role in PrincipalRole:
            players = (
                ("player-a", "player-b")
                if role in (PrincipalRole.PLAYER, PrincipalRole.COACH)
                else (None,)
            )
            for player in players:
                viewer = ViewerContext(
                    principal_id=f"d06:{role}:{player}",
                    role=role,
                    viewer_player_id=player,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert other.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert other.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="d06:exact-replay")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("elevated", [True, False])
@pytest.mark.integration
@pytest.mark.replay
def test_native_distance_offer_atomic_rejection_retry_forks_and_continuation(
    player: str,
    elevated: bool,
) -> None:
    scene = later_embark_scene(player=player, elevated=elevated)
    session = scene.session
    request = pending_request(session)
    assert request.decision_type == "submit_movement_proposal"
    assert state_of(session).battle_round == 2
    assert_preserved(session)
    # A malformed echo is rejected through the genuine facade without consuming
    # the current movement request; the unchanged legal move can be retried.
    proposal = move_payload(session, request, dy=-0.5)
    assert isinstance(proposal, dict)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d06:invalid-echo",
        payload={**proposal, "unit_instance_id": CARRIER},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending_request(session) == request
    assert_preserved(session)

    fork = session.fork()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for active in (session, fork, restored):
        request = pending_request(active)
        propose(active, request, move_payload(active, request, dy=-0.5))
        offered = pending_request(active)
        state = state_of(active)
        assert state.battlefield_state is not None
        cargo = state.transport_cargo_state_for_transport(CARRIER)
        assert cargo is not None
        assert not cargo.contains_unit(PASSENGER)
        assert state.battlefield_state.unit_placement_or_none(PASSENGER) is not None
        if elevated:
            # Native distance > 8 inches between base planes: no Embark choice.
            assert offered.decision_type != "select_embark_transport"
        else:
            assert offered.decision_type == "select_embark_transport"
            assert CARRIER in tuple(option.option_id for option in offered.options)
            before = active.lifecycle.to_payload()
            # Forging geometry inside a finite selection cannot bypass the
            # offered canonical payload or alter manifest/ownership/queue.
            carrier_option = next(
                option for option in offered.options if option.option_id == CARRIER
            )
            assert isinstance(carrier_option.payload, dict)
            # The facade rejects the wrong submission kind before dispatching
            # a finite request. Preserve that typed contract rejection.
            with pytest.raises(GameLifecycleError, match="requires a parameterized request"):
                active.submit_parameterized_payload(
                    request_id=offered.request_id,
                    result_id="d06:invalid-embark-payload",
                    payload={**carrier_option.payload, "battle_round": 99},
                )
            assert active.lifecycle.to_payload() == before
            assert pending_request(active) == offered
            choose(active, offered, CARRIER)
            state = state_of(active)
            cargo = state.transport_cargo_state_for_transport(CARRIER)
            assert cargo is not None
            assert cargo.contains_unit(PASSENGER)
            assert state.battlefield_state is not None
            assert state.battlefield_state.unit_placement_or_none(PASSENGER) is None
            assert any(
                event.event_type == "unit_embarked"
                for event in active.lifecycle.decision_controller.event_log.records
            )
        assert_preserved(active)
        # Continue through the actual next phase in each independent session.
        for _ in range(30):
            current = pending_request(active)
            if current.decision_type == "select_shooting_unit":
                break
            default_choice(active, current)
        else:
            raise AssertionError("D06 native post-Embark continuation not reached")
        assert_preserved(active)
    assert (
        fork.lifecycle.to_payload()
        == restored.lifecycle.to_payload()
        == session.lifecycle.to_payload()
    )


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize(
    ("horizontal_gap", "expected"), [(1.799, True), (1.8, True), (1.801, False)]
)
@pytest.mark.integration
@pytest.mark.replay
def test_native_translated_diagonal_inclusive_boundary(
    player: str, horizontal_gap: float, expected: bool
) -> None:
    scene = later_diagonal_embark_scene(player=player)
    session = scene.session
    assert_preserved(session)
    request = pending_request(session)
    state = state_of(session)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(PASSENGER)
    # The unchanged catalog profiles have 40-mm and 100-mm circular bases.
    # Intended gaps 1.8 horizontally and 2.4 vertically give exactly 3 inches;
    # derive the expectation from that construction, not rounded backend output.
    radii_sum = 20 / 25.4 + 50 / 25.4
    endpoint = Pose.at(16 - radii_sum - horizontal_gap, 10, 9.4)
    witness = PathWitness.for_paths(
        tuple(
            (model.model_instance_id, (model.pose, endpoint))
            for model in placement.model_placements
        )
    )
    proposal = move_payload(session, request, witness=witness)
    assert isinstance(proposal, dict)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d06:diagonal-invalid-echo",
        payload={**proposal, "unit_instance_id": CARRIER},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending_request(session) == request
    propose(session, request, proposal)
    offered = pending_request(session)
    assert (offered.decision_type == "select_embark_transport") is expected
    assert_preserved(session)
    if expected:
        choose(session, offered, CARRIER)
        state = state_of(session)
        cargo = state.transport_cargo_state_for_transport(CARRIER)
        assert cargo is not None
        assert cargo.contains_unit(PASSENGER)
        assert state.battlefield_state is not None
        assert state.battlefield_state.unit_placement_or_none(PASSENGER) is None
        embarked = tuple(
            event
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "unit_embarked"
        )
        assert len(embarked) == 1
    else:
        state = state_of(session)
        cargo = state.transport_cargo_state_for_transport(CARRIER)
        assert cargo is not None
        assert not cargo.contains_unit(PASSENGER)
        assert state.battlefield_state is not None
        assert state.battlefield_state.unit_placement_or_none(PASSENGER) is not None
    for _ in range(30):
        current = pending_request(session)
        if current.decision_type == "select_shooting_unit":
            break
        default_choice(session, current)
    else:
        raise AssertionError("D06 diagonal continuation not reached")
    assert_preserved(session)
