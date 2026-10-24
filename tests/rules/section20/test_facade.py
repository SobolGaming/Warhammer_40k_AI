"""Public ingress authority: no preceding setup or unrelated phases."""

import json

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import events
from tests.support.section20_fixtures import SPAWN, ingress_request, reserve_scene, submit_ingress
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.ingress_lifetimes import ingress_movement_locked
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("sheet", ["000004193", SPAWN])
def test_public_ingress_rejects_malformed_then_bad_geometry_and_commits_fresh_retry(
    section20_definitions: Section02Definitions, sheet: str
) -> None:
    s = reserve_scene(section20_definitions, sheet=sheet)
    session = s.session()
    request = ingress_request(session, s.unit)
    before = s.state.to_payload()
    records = session.lifecycle.decision_controller.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s20:malformed",
        payload={"proposal_request_id": request.request_id},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == records
    invalid = submit_ingress(
        session,
        request,
        s.unit,
        tuple(Pose.at(20, 15 + i * 2.5) for i in range(len(s.unit.own_models))),
        result_id="s20:bad-strip",
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.battlefield_state is not None
    assert s.state.battlefield_state.unit_placement_or_none(s.unit.unit_instance_id) is None
    assert s.state.reserve_states[0].status is ReserveStatus.IN_RESERVES
    assert not s.state.phase_movement_history
    retry = session.lifecycle.pending_decision_request()
    assert retry is not None
    assert retry.decision_type == "select_movement_unit"
    status = session.submit_option(
        request_id=retry.request_id, result_id="s20:retry-select", option_id=s.unit.unit_instance_id
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s20:retry-ingress",
        option_id="ingress",
    )
    assert status.decision_request is not None
    status = submit_ingress(
        session,
        status.decision_request,
        s.unit,
        tuple(Pose.at(2, 15 + i * 2.5) for i in range(len(s.unit.own_models))),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    arrived = s.state.reserve_state_for_unit(s.unit.unit_instance_id)
    assert arrived is not None
    assert arrived.status is ReserveStatus.ARRIVED
    assert (
        tuple(
            p.model_instance_id
            for p in s.state.battlefield_state.unit_placement_by_id(
                s.unit.unit_instance_id
            ).model_placements
        )
        == s.unit.own_model_ids()
    )
    history = s.state.phase_movement_history[-1]
    assert history.is_ingress
    assert history.setup_kind is not None
    assert history.model_instance_ids == s.unit.own_model_ids()
    assert (
        events(session, "reinforcement_unit_arrived")[-1]["unit_instance_id"]
        == s.unit.unit_instance_id
    )
    for phase, locked in (
        (BattlePhase.MOVEMENT, True),
        (BattlePhase.SHOOTING, True),
        (BattlePhase.CHARGE, False),
        (BattlePhase.FIGHT, False),
    ):
        s.state.battle_phase_index = s.state.battle_phase_sequence.index(phase)
        assert ingress_movement_locked(s.state, s.unit.unit_instance_id) is locked
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    for viewer in ("owner", "opponent"):
        view = session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view
    assert (
        json.loads(json.dumps(session.lifecycle.decision_controller.to_payload()))
        == session.lifecycle.decision_controller.to_payload()
    )


def test_supported_core_checkpoint_ingress_preserves_restore_and_exact_replay() -> None:
    from tests.order63_reserve_transport_helpers import reserve_transport_session
    from tests.order63_reserve_transport_helpers import submit_ingress as canonical_ingress

    # The native clause kernel deliberately has no admitted complete roster.
    # Keep strict restoration assertions at an existing supported Core checkpoint,
    # retaining the separate native-provider/roster and Q18-01 qualifications.
    session = reserve_transport_session()
    initial = session.lifecycle.to_payload()
    canonical_ingress(session)
    final = session.lifecycle.to_payload()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == final
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="s20:ingress",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
