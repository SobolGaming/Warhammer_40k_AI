"""Native Cavalcade opening unit selection through the shared engine authority."""

import json

import pytest

from tests.support.cross_worker_fixture_cache import load_native_command_checkpoint
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.opening_movement_unit import (
    OPENING_MOVEMENT_UNIT_POLICY_ID,
    opening_movement_unit_registration,
)
from warhammer40k_core.ai.opening_shadow_form import opening_shadow_form_registration
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, PolicyRouter
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunBoundary, RunLimits, RunnerError
from warhammer40k_core.engine.decision_request import DecisionOptionPayload
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner


def test_opening_movement_selects_an_issued_unit_before_any_action(
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
) -> None:
    checkpoint = load_native_command_checkpoint(
        tmp_path_factory=tmp_path_factory, pytestconfig=pytestconfig
    )
    session = LocalGameSession.from_persistence_payload(checkpoint)
    initial = session.lifecycle.to_payload()
    limits = RunLimits(policy_seed=19, max_decisions=8, max_seconds=60)
    assert session.decision_record_count() == 42
    forms = BoundedPolicyRunner(
        session=session,
        router=PolicyRouter(
            tuple(opening_shadow_form_registration(actor) for actor in ("player-a", "player-b"))
        ),
        limits=limits,
    ).run(stop_at=RunBoundary("battle", "movement"))
    assert [(attempt.route.actor_id, attempt.accepted) for attempt in forms.decisions] == [
        ("player-a", True),
        ("player-b", True),
    ]

    before = session.view(viewer_player_id="player-a")
    context = PlayerDecisionContext.from_view(before, choice_seed=19)
    assert context.route.decision_type == "select_movement_unit"
    request = context.request
    battlefield_options: list[tuple[int, DecisionOptionPayload]] = []
    for option in request["options"]:
        payload = option["payload"]
        assert isinstance(payload, dict)
        if payload["unit_location"] == "battlefield":
            models = payload["model_instance_ids"]
            assert isinstance(models, list)
            battlefield_options.append((len(models), option))
    _, expected = max(battlefield_options, key=lambda entry: entry[0])
    assert len(battlefield_options) > 1
    with pytest.raises(PolicyError, match="bound Player A round-one request"):
        opening_movement_unit_registration("different-view-request").policy.choose(context)

    registration = opening_movement_unit_registration(request["request_id"])
    assert registration.policy.choose(context).option_id == expected["option_id"]
    with pytest.raises(RunnerError, match="Unsupported exact policy route") as stopped:
        BoundedPolicyRunner(
            session=session, router=PolicyRouter((registration,)), limits=limits
        ).run()
    choice, action = stopped.value.report.decisions
    assert choice.route == context.route
    assert choice.viewer_request_id == request["request_id"]
    assert choice.policy_id == OPENING_MOVEMENT_UNIT_POLICY_ID
    assert choice.accepted
    assert choice.recorded_decisions == 1
    assert action.route.actor_id == "player-a"
    assert action.route.decision_type == "select_movement_action"
    assert action.failure_stage == "routing"
    assert session.decision_record_count() == 45

    record = session.lifecycle.decision_controller.records[-1]
    selected = record.result.payload
    assert selected == expected["payload"]
    assert isinstance(selected, dict)
    assert record.request.request_id == choice.request_id
    after = session.view(viewer_player_id="player-a")
    assert after["battlefield_state"] == before["battlefield_state"]
    pending = after["pending_decision"]
    assert pending is not None
    assert pending["request_id"] == action.viewer_request_id
    detail = pending["payload"]
    assert isinstance(detail, dict)
    assert detail["unit_instance_id"] == selected["unit_instance_id"]

    artifact = ReplayArtifact.capture(
        artifact_id="native-opening-movement-unit",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(json.loads(json.dumps(artifact.to_payload()))).run()
    assert replay.reproduced_exactly
    assert replay.reproduced_decision_count == 3
