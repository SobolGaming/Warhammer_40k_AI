# pyright: reportPrivateUsage=false
"""Consumed RULE/FIGHT/REMOVED restoration and six preserved trust-boundary negatives."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from tests.support.section05_rule_effect_retention import (
    _daemonic_patrons_session,
    _install_daemonic_patrons_resume_runtime,
    _pending_daemonic_patrons_fight_on_death_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import DECLINE_FEEL_NO_PAIN_OPTION_ID
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind


def test_order_30_rule_cleanup_resumes_after_feel_no_pain_and_restores() -> None:
    state, decisions, runtime, _source, model_id, request_id, option_id = (
        _pending_daemonic_patrons_fight_on_death_fixture(cleanup_fnp=True)
    )
    session, config = _daemonic_patrons_session(state=state, decisions=decisions)
    _install_daemonic_patrons_resume_runtime(session=session, config=config, runtime=runtime)
    status = session.submit_option(
        request_id=request_id, option_id=option_id, result_id="accept-rule-retention"
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_feel_no_pain"
    checkpoint = session.lifecycle.to_payload()
    restored = GameLifecycle.from_payload(checkpoint)
    assert restored.to_payload() == checkpoint
    session = LocalGameSession(lifecycle=restored)
    _install_daemonic_patrons_resume_runtime(session=session, config=config, runtime=runtime)
    resumed = session.submit_option(
        request_id=status.decision_request.request_id,
        option_id=DECLINE_FEEL_NO_PAIN_OPTION_ID,
        result_id="decline-rule-cleanup-fnp",
    )
    assert resumed.status_kind is not LifecycleStatusKind.INVALID
    final_state = session.lifecycle.state
    assert final_state is not None
    assert final_state.battlefield_state is not None
    assert model_id in final_state.battlefield_state.removed_model_ids
    assert not any(
        effect.effect_id.startswith(("retained-destruction:", "daemonic-patrons-"))
        for effect in final_state.persisting_effects
    )
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "root_identity",
        "source",
        "missing_retention",
        "missing_request_event",
        "duplicate_request_event",
        "premature_finalization",
    ],
)
def test_order_30_rule_cleanup_restore_rejects_mortal_continuation_drift(
    mutation: str,
) -> None:
    state, decisions, runtime, _source, model_id, request_id, option_id = (
        _pending_daemonic_patrons_fight_on_death_fixture(cleanup_fnp=True)
    )
    session, config = _daemonic_patrons_session(state=state, decisions=decisions)
    _install_daemonic_patrons_resume_runtime(session=session, config=config, runtime=runtime)
    status = session.submit_option(
        request_id=request_id, option_id=option_id, result_id="accept-rule-retention"
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_feel_no_pain"
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    altered = cast(dict[str, Any], json.loads(json.dumps(checkpoint)))
    pending = next(
        request
        for request in altered["decisions"]["queue"]["pending_requests"]
        if request["request_id"] == status.decision_request.request_id
    )
    events = altered["decisions"]["event_log"]
    source_context = pending["payload"]["lost_wound_context"]["source_context"]
    root_context = source_context["root_context"]
    if mutation == "root_identity":
        root_context["target_unit_instance_id"] = "wrong-physical-unit"
    elif mutation == "source":
        source_context["source"]["optional"] = True
    elif mutation == "missing_retention":
        altered["state"]["persisting_effects"] = [
            effect
            for effect in altered["state"]["persisting_effects"]
            if not effect["effect_id"].startswith("retained-destruction:")
        ]
    elif mutation == "missing_request_event":
        event = next(
            event
            for event in events
            if event["event_type"] == "decision_requested"
            and event["payload"]["request_id"] == pending["request_id"]
        )
        event["event_type"] = "removed-request-evidence"
    elif mutation == "duplicate_request_event":
        events.append(
            {
                "event_id": f"event-{len(events) + 1:06d}",
                "event_type": "decision_requested",
                "payload": pending,
            }
        )
    else:
        assert mutation == "premature_finalization"
        destroyed = next(
            event
            for event in events
            if event["event_type"] == "model_destroyed"
            and event["payload"]["model_instance_id"] == model_id
        )
        events.append(
            {
                "event_id": f"event-{len(events) + 1:06d}",
                "event_type": "rule_model_destruction_finalized",
                "payload": {
                    "game_id": root_context["game_id"],
                    "battle_round": destroyed["payload"]["battle_round"],
                    "phase": root_context["phase"],
                    "model_destroyed_event_id": destroyed["event_id"],
                    "model_instance_id": model_id,
                    "physical_unit_instance_id": root_context["target_unit_instance_id"],
                    "rules_unit_instance_id": root_context["rules_unit_instance_id"],
                    "completion_kind": root_context["completion_kind"],
                },
            }
        )
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(Any, altered))
