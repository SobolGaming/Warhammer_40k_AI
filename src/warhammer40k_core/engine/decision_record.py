from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.event_log import canonical_json


class DecisionRecordPayload(TypedDict):
    record_id: str
    request: DecisionRequestPayload
    result: DecisionResultPayload


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    record_id: str
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("DecisionRecord record_id", self.record_id),
        )
        if type(self.request) is not DecisionRequest:
            raise DecisionError("DecisionRecord request must be a DecisionRequest.")
        if type(self.result) is not DecisionResult:
            raise DecisionError("DecisionRecord result must be a DecisionResult.")
        self.result.validate_for_request(self.request)

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def to_payload(self) -> DecisionRecordPayload:
        return {
            "record_id": self.record_id,
            "request": self.request.to_payload(),
            "result": self.result.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DecisionRecordPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            request=DecisionRequest.from_payload(payload["request"]),
            result=DecisionResult.from_payload(payload["result"]),
        )


_validate_identifier = IdentifierValidator(DecisionError)
