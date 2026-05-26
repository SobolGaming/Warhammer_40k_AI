from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_queue import DecisionQueue, DecisionQueuePayload
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload


def _select_unit_request(request_id: str = "decision-request-1") -> DecisionRequest:
    return DecisionRequest(
        request_id=request_id,
        decision_type="select_unit",
        actor_id="player-a",
        payload={"phase": "movement"},
        options=(
            DecisionOption(
                option_id="unit-b",
                label="Unit B",
                payload={"selected_unit_id": "unit-b"},
            ),
            DecisionOption(
                option_id="unit-a",
                label="Unit A",
                payload={"selected_unit_id": "unit-a"},
            ),
        ),
    )


def test_decision_request_action_space_is_finite_deterministic_and_serializable() -> None:
    request = _select_unit_request()
    payload = cast(
        DecisionRequestPayload,
        json.loads(json.dumps(request.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert tuple(option.option_id for option in request.options) == ("unit-a", "unit-b")
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert DecisionRequest.from_payload(payload).to_payload() == request.to_payload()

    with pytest.raises(DecisionError):
        DecisionRequest(
            request_id="empty-options",
            decision_type="select_unit",
            actor_id=None,
            payload={},
            options=(),
        )
    with pytest.raises(DecisionError):
        DecisionRequest(
            request_id="duplicate-options",
            decision_type="select_unit",
            actor_id=None,
            payload={},
            options=(
                DecisionOption(option_id="unit-a", label="Unit A", payload={}),
                DecisionOption(option_id="unit-a", label="Unit A again", payload={}),
            ),
        )
    with pytest.raises(DecisionError):
        DecisionRequest(
            request_id="bad-option-type",
            decision_type="select_unit",
            actor_id=None,
            payload={},
            options=(cast(DecisionOption, "unit-a"),),
        )


def test_decision_result_must_select_one_request_option() -> None:
    request = _select_unit_request()
    result = DecisionResult.for_request(
        result_id="decision-result-1",
        request=request,
        selected_option_id="unit-a",
    )
    payload = cast(
        DecisionResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )

    result.validate_for_request(request)
    assert result.payload == {"selected_unit_id": "unit-a"}
    assert DecisionResult.from_payload(payload).to_payload() == result.to_payload()

    with pytest.raises(DecisionError):
        DecisionResult.for_request(
            result_id="decision-result-2",
            request=request,
            selected_option_id="missing",
        )
    with pytest.raises(DecisionError):
        DecisionResult(
            result_id="decision-result-3",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="unit-a",
            payload={"selected_unit_id": "unit-b"},
        ).validate_for_request(request)


def test_decision_queue_is_fifo_serializable_and_rejects_duplicate_requests() -> None:
    first = _select_unit_request("decision-request-1")
    second = _select_unit_request("decision-request-2")
    queue = DecisionQueue()

    queue.append(second)
    queue.append(first)
    payload = cast(
        DecisionQueuePayload,
        json.loads(json.dumps(queue.to_payload(), sort_keys=True)),
    )

    assert queue.peek_next() == second
    assert queue.request_by_id("decision-request-1") == first
    assert DecisionQueue.from_payload(payload).to_payload() == queue.to_payload()
    assert queue.pop_next() == second
    assert queue.remove_by_id("decision-request-1") == first

    with pytest.raises(DecisionError):
        queue.pop_next()

    queue.append(first)
    with pytest.raises(DecisionError):
        queue.append(first)


def test_decision_record_round_trips_and_rejects_mismatched_result() -> None:
    request = _select_unit_request()
    result = DecisionResult.for_request(
        result_id="decision-result-1",
        request=request,
        selected_option_id="unit-a",
    )
    record = DecisionRecord(record_id="decision-record-000001", request=request, result=result)
    payload = cast(
        DecisionRecordPayload,
        json.loads(json.dumps(record.to_payload(), sort_keys=True)),
    )

    assert DecisionRecord.from_payload(payload).to_payload() == record.to_payload()
    assert record.history_token()

    with pytest.raises(DecisionError):
        DecisionRecord(
            record_id="decision-record-000002",
            request=request,
            result=DecisionResult(
                result_id="decision-result-2",
                request_id="other-request",
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id="unit-a",
                payload={"selected_unit_id": "unit-a"},
            ),
        )


def test_decision_controller_validates_records_and_uses_one_engine_path() -> None:
    request = _select_unit_request()
    result = DecisionResult.for_request(
        result_id="decision-result-1",
        request=request,
        selected_option_id="unit-b",
    )
    controller = DecisionController()

    controller.request_decision(request)
    record = controller.submit_result(result)
    payload = cast(
        DecisionControllerPayload,
        json.loads(json.dumps(controller.to_payload(), sort_keys=True)),
    )

    assert record.record_id == "decision-record-000001"
    assert record.result == result
    assert controller.queue.pending_requests == ()
    assert tuple(event.event_type for event in controller.event_log.records) == (
        "decision_requested",
        "decision_recorded",
    )
    assert DecisionController.from_payload(payload).to_payload() == controller.to_payload()

    with pytest.raises(DecisionError):
        controller.submit_result(result)


def test_decision_controller_rejects_out_of_order_result_submission() -> None:
    first = _select_unit_request("decision-request-1")
    second = _select_unit_request("decision-request-2")
    controller = DecisionController()
    controller.request_decision(first)
    controller.request_decision(second)
    second_result = DecisionResult.for_request(
        result_id="decision-result-2",
        request=second,
        selected_option_id="unit-a",
    )

    with pytest.raises(DecisionError):
        controller.submit_result(second_result)

    assert controller.queue.peek_next() == first


def test_decision_controller_rejects_non_sequential_record_payloads() -> None:
    request = _select_unit_request()
    result = DecisionResult.for_request(
        result_id="decision-result-1",
        request=request,
        selected_option_id="unit-a",
    )
    record = DecisionRecord(record_id="decision-record-000002", request=request, result=result)

    with pytest.raises(DecisionError):
        DecisionController.from_payload(
            {
                "queue": {"pending_requests": []},
                "records": [record.to_payload()],
                "event_log": [],
            }
        )
