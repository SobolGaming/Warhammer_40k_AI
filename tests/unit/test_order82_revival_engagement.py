from __future__ import annotations

import json
from typing import cast

import pytest
from tests.order82_revival_helpers import revival_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose


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
