from __future__ import annotations

import json
from typing import cast

import pytest
from tests.order82_revival_helpers import revival_session
from tests.order83_revival_helpers import revival_proposal, sequential_revival_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose


def test_separate_revivals_preserve_actual_phase_start_coherency_anchors() -> None:
    session, removed = sequential_revival_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order83-illegal-chain",
        payload=revival_proposal(request, removed, Pose.at(10, 19)),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    for viewer in ("player-a", "player-b"):
        assert session.view(viewer_player_id=viewer)["pending_proposal"] is not None
    checkpoint = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert session.to_persistence_payload() == checkpoint
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order83-legal-retry",
        payload=revival_proposal(request, removed, Pose.at(8.5, 14)),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order83")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached_target", [False, True])
@pytest.mark.parametrize("attached_enemy", [False, True])
@pytest.mark.parametrize("retained_enemy", [False, True])
def test_revival_can_engage_another_model_in_an_already_engaged_enemy_unit(
    attached_target: bool,
    attached_enemy: bool,
    retained_enemy: bool,
) -> None:
    session, payload = revival_session(
        attached_target=attached_target,
        attached_enemy=attached_enemy,
        retained_enemy=retained_enemy,
    )
    session.advance_until_decision_or_terminal()
    checkpoint = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    for player in ("player-a", "player-b"):
        assert session.view(viewer_player_id=player)["pending_proposal"] is not None
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    result = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order82-revival", payload=payload
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    for player in ("player-a", "player-b"):
        delta = session.events_since(EventStreamCursor(), viewer_player_id=player)
        assert any(event["event_type"] == "healing_step_resolved" for event in delta["events"])
    final = session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(final).to_persistence_payload() == final
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order82"))
    assert replay.run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("case", ["new-enemy", "removed-anchor"])
def test_new_enemy_unit_is_rejected_atomically_then_legal_retry_replays(case: str) -> None:
    session, payload = revival_session(
        second_enemy=case == "new-enemy",
        destroyed_enemy=case == "removed-anchor",
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    before = session.lifecycle.to_payload()
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="illegal-engagement",
        payload=payload,
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    for player in ("player-a", "player-b"):
        assert session.view(viewer_player_id=player)["pending_proposal"] is not None
    placement = cast(dict[str, JsonValue], payload["attempted_placement"])
    models = cast(list[dict[str, JsonValue]], placement["model_placements"])
    models[0]["pose"] = cast(JsonValue, Pose.at(8.5, 15).to_payload())
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="legal-retry",
        payload=payload,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order82-retry"))
    assert replay.run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize(
    "corruption",
    ["before", "returned", "source", "missing", "unit-type", "duplicates", "extra", "legacy"],
)
def test_restored_revival_rejects_forged_or_ambiguous_engagement_history(corruption: str) -> None:
    session, proposal = revival_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="history-revival",
        payload=proposal,
    )
    raw = json.loads(json.dumps(session.lifecycle.to_payload()))
    events = raw["decisions"]["event_log"]
    event = next(e for e in events if e["event_type"] == "healing_step_resolved")
    if corruption == "before":
        event["payload"]["revival_engagement"]["engaged_enemy_rules_unit_ids_before"] = []
    elif corruption == "returned":
        event["payload"]["revival_engagement"]["returned_model_engaged_enemy_rules_unit_ids"] = []
    elif corruption == "source":
        event["payload"]["revival_engagement"]["source_package_hash"] = "0" * 64
    elif corruption == "missing":
        del event["payload"]["revival_engagement"]
    elif corruption == "unit-type":
        event["payload"]["revival_engagement"]["engaged_enemy_rules_unit_ids_before"] = [False]
    elif corruption == "duplicates":
        event["payload"]["revival_engagement"]["engaged_enemy_rules_unit_ids_before"] *= 2
    elif corruption == "extra":
        event["payload"]["revival_engagement"]["unreviewed_authority"] = True
    else:
        record = next(
            r for r in raw["decisions"]["records"] if r["result"]["result_id"] == "history-revival"
        )
        record["request"]["payload"]["effect"]["phase_start_enemy_engagement_model_ids"] = []
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("corruption", ["models", "round", "turn", "source", "missing", "window"])
def test_revival_phase_start_history_rejects_forged_evidence(
    completed: bool, corruption: str
) -> None:
    session, proposal = revival_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    if completed:
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id="phase-start-history", payload=proposal
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    raw = json.loads(json.dumps(session.lifecycle.to_payload()))
    if completed:
        payload = next(
            e["payload"]
            for e in raw["decisions"]["event_log"]
            if e["event_type"] == "healing_step_resolved"
        )
    else:
        payload = raw["decisions"]["queue"]["pending_requests"][0]["payload"]
    evidence = payload["revival_phase_start"]
    if corruption == "models":
        evidence["model_ids"] = []
    elif corruption == "round":
        evidence["battle_round"] += 1
    elif corruption == "turn":
        evidence["turn_owner_player_id"] = "player-b"
    elif corruption == "source":
        evidence["source_package_hash"] = "0" * 64
    elif corruption == "missing":
        del payload["revival_phase_start"]
    else:
        evidence["phase_start_window_id"] += ":forged"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


def test_newly_returned_anchor_cannot_be_forged_into_matching_pending_history() -> None:
    session, removed = sequential_revival_session()
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    raw = json.loads(json.dumps(session.lifecycle.to_payload()))
    payloads = [raw["decisions"]["queue"]["pending_requests"][0]["payload"]]
    payloads.extend(
        e["payload"]["payload"]
        for e in raw["decisions"]["event_log"]
        if e["event_type"] == "decision_requested"
        and e["payload"]["request_id"] == request.request_id
    )
    prior_return = removed.model_instance_id.replace("005", "004")
    assert prior_return != removed.model_instance_id
    for payload in payloads:
        payload["effect"]["phase_start_model_ids"].append(prior_return)
        payload["revival_phase_start"]["model_ids"].append(prior_return)
    with pytest.raises(GameLifecycleError, match="phase-start"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "source", "turn"])
def test_revival_requires_unique_canonical_phase_opening(corruption: str) -> None:
    from dataclasses import replace

    from warhammer40k_core.engine.revival_phase_start import revival_phase_start_evidence

    session, _ = revival_session()
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    events = list(decisions.event_log.records)
    index = next(i for i, event in enumerate(events) if event.event_type == "timing_window_opened")
    if corruption == "missing":
        events.pop(index)
    elif corruption == "duplicate":
        events.insert(index, replace(events[index], event_id="duplicate-phase-opening"))
    else:
        payload = json.loads(json.dumps(events[index].payload))
        if corruption == "source":
            payload["timing_window"]["descriptor"]["source_rule_id"] = "forged"
        else:
            payload["timing_window"]["active_player_id"] = "player-b"
        events[index] = replace(events[index], payload=payload)
    request = decisions.queue.peek_next()
    assert isinstance(request.payload, dict)
    effect = cast(dict[str, JsonValue], request.payload["effect"])
    with pytest.raises(GameLifecycleError, match="phase-start"):
        revival_phase_start_evidence(
            state=state,
            event_records=tuple(events),
            decision_records=decisions.records,
            target_unit_instance_id=cast(str, effect["target_unit_instance_id"]),
        )


def test_returned_model_cannot_count_itself_as_a_phase_start_neighbour() -> None:
    from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
    from warhammer40k_core.engine.revival_phase_start import validate_revival_anchor_coherency

    session, _ = revival_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit = state.army_definitions[0].units[0]
    model = next(model for model in unit.own_models if model.is_alive)
    geometry = geometry_model_for_placement(
        model=model,
        placement=state.battlefield_state.model_placement_by_id(model.model_instance_id),
    )
    with pytest.raises(GameLifecycleError, match="phase-start models"):
        validate_revival_anchor_coherency(
            returned=geometry,
            present_models=(geometry,),
            phase_start_model_ids=(model.model_instance_id,),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
