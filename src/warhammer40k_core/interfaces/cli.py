from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


class CliDecisionOptionPayload(TypedDict):
    index: int
    option_id: str
    label: str
    payload: JsonValue


class CliDecisionPromptPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str | None
    is_parameterized: bool
    prompt: str
    options: list[CliDecisionOptionPayload]


def render_decision_request_for_cli(request: DecisionRequest) -> CliDecisionPromptPayload:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("CLI decision rendering requires a DecisionRequest.")
    return {
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
        "is_parameterized": request.is_parameterized_submission_request(),
        "prompt": _prompt_text(request),
        "options": [
            {
                "index": index,
                "option_id": option.option_id,
                "label": option.label,
                "payload": option.payload,
            }
            for index, option in enumerate(request.options, start=1)
        ],
    }


def finite_option_submission_from_cli_choice(
    *,
    request: DecisionRequest,
    choice: str,
    result_id: str,
) -> FiniteOptionSubmission:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("CLI finite choice requires a DecisionRequest.")
    if request.is_parameterized_submission_request():
        raise GameLifecycleError("CLI finite choice cannot answer a parameterized request.")
    selected_option_id = _option_id_for_cli_choice(request=request, choice=choice)
    return FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=selected_option_id,
        result_id=result_id,
    )


def parameterized_submission_from_cli_payload(
    *,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> ParameterizedSubmission:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("CLI parameterized payload requires a DecisionRequest.")
    if not request.is_parameterized_submission_request():
        raise GameLifecycleError("CLI parameterized payload requires a parameterized request.")
    return ParameterizedSubmission(
        request_id=request.request_id,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def submit_cli_choice(
    *,
    lifecycle: GameLifecycle,
    choice: str,
    result_id: str,
) -> LifecycleStatus:
    request = _pending_request(lifecycle)
    submission = finite_option_submission_from_cli_choice(
        request=request,
        choice=choice,
        result_id=result_id,
    )
    return lifecycle.submit_decision(submission.to_result(request))


def submit_cli_payload(
    *,
    lifecycle: GameLifecycle,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus:
    request = _pending_request(lifecycle)
    submission = parameterized_submission_from_cli_payload(
        request=request,
        payload=payload,
        result_id=result_id,
    )
    return lifecycle.submit_decision(submission.to_result(request))


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest:
    if type(lifecycle) is not GameLifecycle:
        raise GameLifecycleError("CLI submission requires a GameLifecycle.")
    pending_requests = lifecycle.decision_controller.queue.pending_requests
    if not pending_requests:
        raise GameLifecycleError("CLI submission requires a pending DecisionRequest.")
    return pending_requests[0]


def _option_id_for_cli_choice(*, request: DecisionRequest, choice: str) -> str:
    normalized = _validate_cli_choice(choice)
    option_by_id = {option.option_id: option for option in request.options}
    if normalized in option_by_id:
        return normalized
    if normalized.isdecimal():
        option_index = int(normalized)
        if option_index < 1 or option_index > len(request.options):
            raise GameLifecycleError("CLI finite choice option index is out of range.")
        return request.options[option_index - 1].option_id
    raise GameLifecycleError("CLI finite choice does not match a pending option.")


def _prompt_text(request: DecisionRequest) -> str:
    actor = "unassigned actor" if request.actor_id is None else request.actor_id
    return f"{actor}: {request.decision_type}"


def _validate_cli_choice(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("CLI choice must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("CLI choice must not be empty.")
    return stripped
