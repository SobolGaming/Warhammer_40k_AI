from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.adapters.contracts import (
    AdapterGameSession,
    FiniteOptionSubmission,
    ParameterizedSubmission,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
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
    session: AdapterGameSession,
    prompt: CliDecisionPromptPayload,
    choice: str,
    result_id: str,
) -> LifecycleStatus:
    option_id = _option_id_for_cli_prompt(prompt=prompt, choice=choice)
    return session.submit_option(
        request_id=_prompt_request_id(prompt),
        option_id=option_id,
        result_id=result_id,
    )


def submit_cli_payload(
    *,
    session: AdapterGameSession,
    request_id: str,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=request_id,
        payload=payload,
        result_id=result_id,
    )


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


def _option_id_for_cli_prompt(*, prompt: CliDecisionPromptPayload, choice: str) -> str:
    normalized = _validate_cli_choice(choice)
    options = prompt["options"]
    option_by_id = {option["option_id"]: option for option in options}
    if normalized in option_by_id:
        return normalized
    if normalized.isdecimal():
        option_index = int(normalized)
        if option_index < 1 or option_index > len(options):
            raise GameLifecycleError("CLI finite choice option index is out of range.")
        return options[option_index - 1]["option_id"]
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


def _prompt_request_id(prompt: CliDecisionPromptPayload) -> str:
    value = prompt["request_id"]
    if type(value) is not str:
        raise GameLifecycleError("CLI prompt request_id must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("CLI prompt request_id must not be empty.")
    return stripped
