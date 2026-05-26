from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    DecisionRequestPayload,
)


class DecisionQueuePayload(TypedDict):
    pending_requests: list[DecisionRequestPayload]


def _new_pending_requests() -> list[DecisionRequest]:
    return []


@dataclass(slots=True)
class DecisionQueue:
    _pending_requests: list[DecisionRequest] = field(default_factory=_new_pending_requests)

    @property
    def pending_requests(self) -> tuple[DecisionRequest, ...]:
        return tuple(self._pending_requests)

    def append(self, request: DecisionRequest) -> DecisionRequest:
        valid_request = _validate_request(request)
        if any(
            pending.request_id == valid_request.request_id for pending in self._pending_requests
        ):
            raise DecisionError("DecisionQueue already contains request_id.")
        self._pending_requests.append(valid_request)
        return valid_request

    def peek_next(self) -> DecisionRequest:
        if not self._pending_requests:
            raise DecisionError("DecisionQueue is empty.")
        return self._pending_requests[0]

    def pop_next(self) -> DecisionRequest:
        if not self._pending_requests:
            raise DecisionError("DecisionQueue is empty.")
        return self._pending_requests.pop(0)

    def request_by_id(self, request_id: object) -> DecisionRequest:
        requested_id = _validate_identifier("request_id", request_id)
        for request in self._pending_requests:
            if request.request_id == requested_id:
                return request
        raise DecisionError("DecisionQueue request_id was not found.")

    def remove_by_id(self, request_id: object) -> DecisionRequest:
        requested_id = _validate_identifier("request_id", request_id)
        for index, request in enumerate(self._pending_requests):
            if request.request_id == requested_id:
                return self._pending_requests.pop(index)
        raise DecisionError("DecisionQueue request_id was not found.")

    def to_payload(self) -> DecisionQueuePayload:
        return {"pending_requests": [request.to_payload() for request in self._pending_requests]}

    @classmethod
    def from_payload(cls, payload: DecisionQueuePayload) -> Self:
        queue = cls()
        for request_payload in payload["pending_requests"]:
            queue.append(DecisionRequest.from_payload(request_payload))
        return queue


def _validate_request(request: object) -> DecisionRequest:
    if type(request) is not DecisionRequest:
        raise DecisionError("DecisionQueue request must be a DecisionRequest.")
    return request


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DecisionError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DecisionError(f"{field_name} must not be empty.")
    return stripped
