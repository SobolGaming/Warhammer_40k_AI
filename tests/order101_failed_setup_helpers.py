"""Canonical failed setup continuation and historical-authority corruption probes."""

from copy import deepcopy
from typing import cast

from tests.phase10p_reserves_helpers import decision_request, submit_handler_decision
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecyclePayload
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler


def reselect_failed_ingress(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    unit_id: str,
    result_id_prefix: str,
) -> DecisionRequest:
    movement = state.movement_phase_state
    assert movement is not None
    assert unit_id not in movement.selected_unit_ids
    assert unit_id not in movement.moved_unit_ids
    assert movement.active_selection is None
    request = decisions.queue.peek_next()
    assert request.decision_type == "select_movement_unit"
    assert unit_id in {option.option_id for option in request.options}
    assert (
        submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=request,
            option_id=unit_id,
            result_id=f"{result_id_prefix}-reselect-unit",
        )
        is None
    )
    action = decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action.decision_type == "select_movement_action"
    assert "ingress" in {option.option_id for option in action.options}
    return decision_request(
        submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=action,
            option_id="ingress",
            result_id=f"{result_id_prefix}-reselect-ingress",
        )
    )


def corrupt_failed_setup_authority(payload: GameLifecyclePayload, *, tamper: str) -> None:
    """Preserve ledger/event closure while testing the rejected attempt's authority."""
    events = payload["decisions"]["event_log"]
    receipt = next(event for event in events if event["event_type"] == "movement_setup_failed")
    authority = receipt["payload"]
    assert isinstance(authority, dict)
    record = next(
        record
        for record in payload["decisions"]["records"]
        if record["result"]["result_id"] == authority["result_id"]
    )
    invalid = next(event for event in events if event["event_id"] == authority["invalid_event_id"])
    diagnostic = invalid["payload"]
    assert isinstance(diagnostic, dict)
    request = record["request"]
    original_request_id = request["request_id"]
    if tamper == "missing_predecessor":
        record["result"]["result_id"] = "forged-rejected-result"
    elif tamper == "predecessor_authority":
        request["actor_id"] = "forged-owner"
        record["result"]["actor_id"] = "forged-owner"
    elif tamper == "predecessor_order":
        recorded = next(
            event
            for event in events
            if event["event_type"] == "decision_recorded" and event["payload"] == record
        )
        recorded["event_type"], receipt["event_type"] = (
            receipt["event_type"],
            recorded["event_type"],
        )
        recorded["payload"], receipt["payload"] = receipt["payload"], recorded["payload"]
    elif tamper == "missing_invalid_event":
        invalid["event_type"] = "forged-invalid-event"
    elif tamper == "invalid_event_order":
        invalid["event_type"], receipt["event_type"] = receipt["event_type"], invalid["event_type"]
        invalid["payload"], receipt["payload"] = receipt["payload"], invalid["payload"]
    elif tamper == "empty_violations":
        diagnostic["violations"] = []
    elif tamper == "malformed_violations":
        diagnostic["violations"] = ["not-a-typed-violation"]
    elif tamper == "empty_coherency":
        diagnostic["coherency_result"] = {}
    elif tamper == "outer_request_id":
        request["request_id"] = "forged-outer-request"
        record["result"]["request_id"] = request["request_id"]
        authority["request_id"] = request["request_id"]
        diagnostic["request_id"] = request["request_id"]
    elif tamper == "invalid_event_authority":
        diagnostic["game_id"] = "forged-game"
    elif tamper == "missing_source_event":
        source = next(
            event
            for event in events
            if event["event_type"] == "placement_proposal_requested"
            and isinstance(event["payload"], dict)
            and event["payload"].get("request_id") == request["request_id"]
        )
        source["event_type"] = "forged-placement-source"
    else:
        proposal = request["payload"]
        assert isinstance(proposal, dict)
        proposal_request = proposal["proposal_request"]
        assert isinstance(proposal_request, dict)
        context = proposal_request["context"]
        assert isinstance(context, dict)
        if tamper == "extra_proposal_context":
            context["forged_authority"] = True
        elif tamper == "wrong_carried_reserve_round":
            reserve = context["reserve_state"]
            assert isinstance(reserve, dict)
            reserve["entered_reserves_battle_round"] = 99
        elif tamper in {"physical_model_ids", "physical_owner"}:
            submitted = record["result"]["payload"]
            assert isinstance(submitted, dict)
            attempted = submitted.get("attempted_placement")
            components: list[JsonValue]
            if isinstance(attempted, dict):
                components = [attempted]
            else:
                rules_unit = submitted["attempted_rules_unit_placement"]
                assert isinstance(rules_unit, dict)
                raw_components = rules_unit["component_unit_placements"]
                assert isinstance(raw_components, list)
                components = raw_components
            forged_models: list[str] = []
            for component in components:
                assert isinstance(component, dict)
                models = component["model_placements"]
                assert isinstance(models, list)
                if tamper == "physical_owner":
                    component["player_id"] = "forged-owner"
                for index, model in enumerate(models):
                    assert isinstance(model, dict)
                    if tamper == "physical_owner":
                        model["player_id"] = "forged-owner"
                    else:
                        model["model_instance_id"] = (
                            f"{component['unit_instance_id']}:model-forged-{index}"
                        )
                        forged_id = model["model_instance_id"]
                        assert isinstance(forged_id, str)
                        forged_models.append(forged_id)
            if tamper == "physical_model_ids":
                context["model_instance_ids"] = validate_json_value(sorted(forged_models))
        else:
            raise AssertionError(f"Unknown authority probe: {tamper}")
    for event in events:
        event_payload = event["payload"]
        if not isinstance(event_payload, dict):
            continue
        if (
            event["event_type"] == "decision_requested"
            and event_payload.get("request_id") == original_request_id
        ):
            event["payload"] = cast(JsonValue, deepcopy(request))
        elif (
            event["event_type"] == "decision_recorded"
            and event_payload.get("record_id") == record["record_id"]
        ):
            event["payload"] = cast(JsonValue, deepcopy(record))
