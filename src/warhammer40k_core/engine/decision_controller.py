from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.engine.decision_queue import DecisionQueue, DecisionQueuePayload
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, EventRecordPayload


class DecisionControllerPayload(TypedDict):
    queue: DecisionQueuePayload
    records: list[DecisionRecordPayload]
    event_log: list[EventRecordPayload]


def _new_decision_records() -> list[DecisionRecord]:
    return []


@dataclass(slots=True)
class DecisionController:
    queue: DecisionQueue = field(default_factory=DecisionQueue)
    event_log: EventLog = field(default_factory=EventLog)
    _records: list[DecisionRecord] = field(default_factory=_new_decision_records)

    @property
    def records(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._records)

    def request_decision(self, request: DecisionRequest) -> DecisionRequest:
        queued = self.queue.append(request)
        self.event_log.append("decision_requested", queued.to_payload())
        return queued

    def submit_result(self, result: DecisionResult) -> DecisionRecord:
        if type(result) is not DecisionResult:
            raise DecisionError("DecisionController result must be a DecisionResult.")
        request = self.queue.peek_next()
        if result.request_id != request.request_id:
            raise DecisionError("DecisionController must resolve the next queued request.")
        result.validate_for_request(request)
        self.queue.pop_next()
        record = DecisionRecord(
            record_id=f"decision-record-{len(self._records) + 1:06d}",
            request=request,
            result=result,
        )
        self._records.append(record)
        self.event_log.append("decision_recorded", record.to_payload())
        return record

    def to_payload(self) -> DecisionControllerPayload:
        return {
            "queue": self.queue.to_payload(),
            "records": [record.to_payload() for record in self._records],
            "event_log": self.event_log.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DecisionControllerPayload) -> Self:
        controller = cls(
            queue=DecisionQueue.from_payload(payload["queue"]),
            event_log=EventLog.from_payload(payload["event_log"]),
        )
        for expected_index, record_payload in enumerate(payload["records"], start=1):
            record = DecisionRecord.from_payload(record_payload)
            expected_record_id = f"decision-record-{expected_index:06d}"
            if record.record_id != expected_record_id:
                raise DecisionError("DecisionController records must be sequential.")
            controller._records.append(record)
        return controller
