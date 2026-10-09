"""Later gathered occurrences use one authority at submission/application/restore."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from typing import Any, cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_override_helpers import (
    decline_choice,
    native_override_session,
    next_override,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_result_override_validation import (
    invalid_dice_result_override_status,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind


def _reach(*, generated: bool = False) -> tuple[LocalGameSession, DecisionRequest]:
    session = native_override_session()
    for index in range(20):
        request = next_override(session)
        payload = request.payload
        assert isinstance(payload, dict)
        if (not generated and payload["roll_type"] == "hit" and payload["attack_index"] == 1) or (
            generated and ":generated-hit-" in str(payload["attack_context_id"])
        ):
            return session, request
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"override:preceding:{index}",
            option_id="use" if generated and index == 0 else "decline",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Expected later occurrence not reached.")


def _complete(session: LocalGameSession) -> None:
    for _ in range(80):
        if any(
            event.event_type == "attack_sequence_completed"
            for event in (session.lifecycle.decision_controller.event_log.records)
        ):
            return
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        decline_choice(session, request)
    raise AssertionError("Gathered attack did not complete.")


@pytest.mark.parametrize(
    ("generated", "choice"), [(False, "decline"), (False, "use"), (True, "use")]
)
def test_later_native_override_continues_identically_across_persistence(
    generated: bool, choice: str
) -> None:
    session, request = _reach(generated=generated)
    state = session.lifecycle.state
    assert state is not None
    host = active_attack_sequence_for_state(state)
    assert host is not None
    assert host.attack_index == 0
    assert host.generated_hit_index == 0
    assert isinstance(request.payload, dict)
    assert request.payload["attack_context_id"] != host.attack_context_id()
    assert_checkpoint(session)
    branches = (
        session,
        LocalGameSession.from_persistence_payload(session.to_persistence_payload()),
        session.fork(),
    )
    for branch in branches:
        status = branch.submit_option(
            request_id=request.request_id,
            result_id="override:later-choice",
            option_id=choice,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        _complete(branch)
        assert_checkpoint(branch)
    assert branches[0].lifecycle.to_payload() == branches[1].lifecycle.to_payload()
    assert branches[0].lifecycle.to_payload() == branches[2].lifecycle.to_payload()
    records = session.lifecycle.decision_controller.records
    assert sum(row.request.request_id == request.request_id for row in records) == 1
    events = session.lifecycle.decision_controller.event_log.records
    if choice == "use":
        overrides = [
            event.payload for event in events if event.event_type == "dice_result_overridden"
        ]
        assert any(
            isinstance(row, dict) and row.get("request_id") == request.request_id
            for row in overrides
        )
        _assert_completed_association_guards(session, request)


def _assert_completed_association_guards(
    session: LocalGameSession, request: DecisionRequest
) -> None:
    original = session.lifecycle.to_payload()
    for fault in ("effect", "spend", "owning-step"):
        payload = cast(dict[str, Any], deepcopy(original))
        changed = False
        for event in payload["decisions"]["event_log"]:
            raw = event["payload"]
            if (
                fault == "effect"
                and event["event_type"] == "dice_result_overridden"
                and (raw["request_id"] == request.request_id)
            ):
                raw["roll_id"] = "roll-999999"
                changed = True
            elif (
                fault == "spend"
                and event["event_type"] == "unit_resource_spent"
                and (raw["decision_request_id"] == request.request_id)
            ):
                raw["source_rule_id"] = "wrong:historical-source"
                changed = True
            elif (
                fault == "owning-step"
                and event["event_type"] == "attack_sequence_step"
                and (
                    raw["attack_context_id"]
                    == cast(dict[str, Any], request.payload)["attack_context_id"]
                    and raw["step"] == cast(dict[str, Any], request.payload)["roll_type"]
                )
            ):
                raw["attack_index"] = 999
                changed = True
        assert changed
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
        assert session.lifecycle.to_payload() == original


def test_pending_later_override_rejects_coordinated_identity_drift_atomically() -> None:
    session, request = _reach()
    state = session.lifecycle.state
    assert state is not None
    host = active_attack_sequence_for_state(state)
    assert host is not None
    before = session.lifecycle.to_payload()
    faults: tuple[tuple[str, JsonValue], ...] = (
        ("attack_index", 2),
        ("attack_index", True),
        ("attack_context_id", host.attack_context_id()),
        ("attack_context_id", replace(host, attack_index=2).attack_context_id()),
        ("roll_id", "roll-000001"),
        ("source_rule_id", "wrong:source"),
        ("current_count", 100),
        ("critical_trigger_markers", []),
    )
    for key, value in faults:
        raw = cast(dict[str, Any], deepcopy(request.to_payload()))
        payload = raw["payload"]
        payload[key] = value
        body = {name: item for name, item in payload.items() if name != "context_fingerprint"}
        payload["context_fingerprint"] = sha256(canonical_json(body).encode()).hexdigest()
        for option in raw["options"]:
            option["payload"]["context_fingerprint"] = payload["context_fingerprint"]
        forged = DecisionRequest.from_payload(cast(DecisionRequestPayload, raw))
        invalid = invalid_dice_result_override_status(
            state=state,
            decisions=session.lifecycle.decision_controller,
            request=forged,
            result=DecisionResult.for_request(
                request=forged, result_id="forged", selected_option_id="use"
            ),
        )
        assert invalid is not None
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
        restore = cast(dict[str, Any], deepcopy(before))
        restore["decisions"]["queue"]["pending_requests"][0] = raw
        for event in restore["decisions"]["event_log"]:
            if (
                event["event_type"] == "decision_requested"
                and event["payload"]["request_id"] == request.request_id
            ):
                event["payload"] = deepcopy(raw)
        with pytest.raises((GameLifecycleError, DecisionError)):
            GameLifecycle.from_payload(cast(GameLifecyclePayload, restore))
    status = session.submit_option(
        request_id=request.request_id,
        result_id="override:legal-retry",
        option_id="use",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    _complete(session)
    assert_checkpoint(session)


def test_pending_later_override_requires_the_completed_hit_prefix() -> None:
    session, request = _reach()
    before = session.lifecycle.to_payload()
    payload = cast(dict[str, Any], deepcopy(before))
    hits = [
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "attack_sequence_step" and event["payload"].get("step") == "hit"
    ]
    assert len(hits) == 1
    # Keep physical dice and the issued next request; corrupt only resolved occurrence authority.
    hits[0]["payload"]["attack_index"] = 1
    hits[0]["payload"]["attack_context_id"] = cast(dict[str, Any], request.payload)[
        "attack_context_id"
    ]
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
    assert session.lifecycle.to_payload() == before
    assert_checkpoint(session)
