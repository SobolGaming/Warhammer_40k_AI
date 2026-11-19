from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
class _PreparedMovementResult:
    record: DecisionRecord
    commit: Callable[[], DecisionRecord]
    committed: bool = False


@dataclass(slots=True)
class DecisionController:
    queue: DecisionQueue = field(default_factory=DecisionQueue)
    event_log: EventLog = field(default_factory=EventLog)
    _records: list[DecisionRecord] = field(default_factory=_new_decision_records)
    _prepared_movement: _PreparedMovementResult | None = field(
        default=None, init=False, repr=False, compare=False
    )

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

    @contextmanager
    def prepare_movement_result(
        self, result: DecisionResult, commit: Callable[[], DecisionRecord]
    ) -> Iterator[DecisionRecord]:
        if self._prepared_movement is not None:
            raise DecisionError("A movement result is already being prepared.")
        request = self.queue.peek_next()
        if result.request_id != request.request_id:
            raise DecisionError("DecisionController must resolve the next queued request.")
        result.validate_for_request(request)
        prepared = _PreparedMovementResult(
            record=DecisionRecord(
                record_id=f"decision-record-{len(self._records) + 1:06d}",
                request=request,
                result=result,
            ),
            commit=commit,
        )
        self._prepared_movement = prepared
        try:
            yield prepared.record
            if not prepared.committed:
                raise DecisionError("Movement resolution returned before committing its result.")
        finally:
            self._prepared_movement = None

    def commit_movement_result(self, result: DecisionResult) -> None:
        prepared = self._prepared_movement
        if prepared is None:
            # Direct phase application retains the caller's existing record ownership.
            return
        if prepared.record.result != result or prepared.committed:
            raise DecisionError("Movement result commit differs from its prepared decision.")
        if prepared.commit() != prepared.record:
            raise DecisionError("The committed movement record differs from its prepared record.")
        prepared.committed = True

    def movement_request_for_result(self, result: DecisionResult) -> DecisionRequest:
        prepared = self._prepared_movement
        if prepared is not None and not prepared.committed and prepared.record.result == result:
            return prepared.record.request
        return self.record_for_result(result).request

    def record_for_result(self, result: DecisionResult) -> DecisionRecord:
        if type(result) is not DecisionResult:
            raise DecisionError("DecisionController result must be a DecisionResult.")
        for record in reversed(self._records):
            if record.result == result:
                return record
        raise DecisionError("DecisionController has no record for the supplied result.")

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
