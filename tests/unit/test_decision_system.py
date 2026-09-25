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
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.interaction_metadata import interaction_descriptor_for_request
from warhammer40k_core.engine.phase import GameLifecycleError


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


def test_interaction_metadata_is_engine_authored_and_fail_closed() -> None:
    finite = DecisionRequest(
        request_id="interaction-finite-request",
        decision_type="select_movement_action",
        actor_id="player-a",
        payload={"unit_instance_id": "unit-a"},
        options=(DecisionOption(option_id="normal_move", label="Normal Move"),),
    )
    path = DecisionRequest(
        request_id="interaction-path-request",
        decision_type="submit_movement_proposal",
        actor_id="player-a",
        payload={
            "proposal_request": {
                "proposal_kind": "normal_move",
                "unit_instance_id": "unit-a",
                "maximum_distance_inches": 6,
            }
        },
        options=(parameterized_decision_option(),),
    )
    marker = DecisionRequest(
        request_id="interaction-marker-request",
        decision_type="submit_cult_ambush_marker_placement",
        actor_id="player-a",
        payload={
            "submission_kind": "cult_ambush_marker_placement",
            "marker_id": "marker-a",
            "replacement_unit_instance_id": "unit-a",
        },
        options=(parameterized_decision_option(),),
    )

    finite_descriptor = interaction_descriptor_for_request(finite)
    path_descriptor = interaction_descriptor_for_request(path)
    marker_descriptor = interaction_descriptor_for_request(marker)

    assert finite_descriptor["interaction_kind"] == "finite_option_list"
    assert finite_descriptor["selected_entity_ids"] == ["unit-a"]
    assert path_descriptor["interaction_kind"] == "path_editor"
    assert path_descriptor["constraints"]["maximum_distance_in"] == 6.0
    assert path_descriptor["constraints"]["may_enter_engagement_range"] is False
    assert marker_descriptor["interaction_kind"] == "battlefield_point_placement"
    assert marker_descriptor["proposal_kind"] == "cult_ambush_marker_placement"
    assert (
        marker_descriptor["constraints"]["submission_schema_ref"]
        == "parameterized-submission.schema.json"
    )
    assert marker_descriptor["constraints"]["proposal_schema_ref"] == (
        "proposal-payload.schema.json#/$defs/cult_ambush_marker_placement"
    )
    assert marker_descriptor["constraints"]["minimum_selections"] is None
    assert marker_descriptor["constraints"]["maximum_selections"] is None
    assert marker_descriptor["submission_variants"] == [
        {
            "variant_id": "place_marker",
            "interaction_kind": "battlefield_point_placement",
            "required_inputs": ["battlefield_point"],
            "proposal_schema_ref": ("proposal-payload.schema.json#/$defs/cult_ambush_marker_point"),
            "display_label": "Place Marker",
        },
        {
            "variant_id": "no_marker",
            "interaction_kind": "confirmation",
            "required_inputs": ["no_marker_reason"],
            "proposal_schema_ref": "proposal-payload.schema.json#/$defs/cult_ambush_no_marker",
            "display_label": "No Legal Marker Position",
        },
    ]

    with pytest.raises(GameLifecycleError, match="missing required engine-authored"):
        interaction_descriptor_for_request(_select_unit_request())


def test_order84_interpretation_evidence_does_not_perturb_unchanged_rng_history() -> None:
    from warhammer40k_core.core.dice import DiceExpression, DiceRollInstance, DiceRollSpec
    from warhammer40k_core.core.modified_dice import UnmodifiedRollResult
    from warhammer40k_core.engine.decision import (
        _rng_payload_history_token,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

    physical = DiceRollManager("order84-metadata").roll_fixed(
        DiceRollSpec(DiceExpression(1, 6), reason="Physical result", roll_type="hit"), (4,)
    )
    current = validate_json_value(
        {
            "instance": DiceRollInstance.from_state(physical).to_payload(),
            "unmodified": UnmodifiedRollResult.from_state(physical).to_payload(),
            "critical_is_threshold": False,
            "success_requires_exact": False,
        }
    )
    original = json.loads(json.dumps(current))
    del original["critical_is_threshold"]
    del original["success_requires_exact"]
    del original["unmodified"]["result_override"]
    del original["instance"]["result_override"]
    del original["instance"]["components"][0]["result_override"]
    assert _rng_payload_history_token(current) == _rng_payload_history_token(
        cast(JsonValue, original)
    )

    assigned = physical.with_result_override(
        decision_id="assignment",
        request_id="source",
        source_rule_id="core:test",
        replacement_value=7,
    )
    assert _rng_payload_history_token(
        validate_json_value(UnmodifiedRollResult.from_state(physical).to_payload())
    ) != _rng_payload_history_token(
        validate_json_value(UnmodifiedRollResult.from_state(assigned).to_payload())
    )
    assert assigned.result_override is not None
    assignment_payload = validate_json_value(assigned.result_override.to_payload())
    assert isinstance(assignment_payload, dict)
    prior_single_die_assignment = {
        key: value for key, value in assignment_payload.items() if key != "component_index"
    }
    assert _rng_payload_history_token(assignment_payload) == _rng_payload_history_token(
        prior_single_die_assignment
    )
    accepted_event = {
        "event_type": "out_of_phase_shooting_declaration_accepted",
        "payload": {"attack_sequence_id": "sequence-a", "unit_instance_id": "unit-a"},
    }
    assert _rng_payload_history_token(validate_json_value(accepted_event)) == (
        _rng_payload_history_token(
            {
                "event_type": "out_of_phase_shooting_declaration_accepted",
                "payload": {"unit_instance_id": "unit-a"},
            }
        )
    )
    # A chosen tied physical component remains a real player choice in RNG history.
    assert _rng_payload_history_token({"component_index": 0}) != _rng_payload_history_token(
        {"component_index": 1}
    )
