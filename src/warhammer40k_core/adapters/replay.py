from __future__ import annotations

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionError,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


def submit_replay_record(
    *,
    session: AdapterGameSession,
    record: DecisionRecord,
) -> LifecycleStatus:
    if type(record) is not DecisionRecord:
        raise GameLifecycleError("Replay adapter requires a DecisionRecord.")
    result = record.result
    try:
        result.validate_for_request(record.request)
    except DecisionError as exc:
        raise GameLifecycleError("Replay adapter record/result pair is invalid.") from exc
    return submit_replay_result(session=session, result=result)


def submit_replay_result(
    *,
    session: AdapterGameSession,
    result: DecisionResult,
) -> LifecycleStatus:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Replay adapter requires a DecisionResult.")
    if result.selected_option_id == PARAMETERIZED_DECISION_OPTION_ID:
        return session.submit_parameterized_payload(
            request_id=result.request_id,
            payload=result.payload,
            result_id=result.result_id,
        )
    return session.submit_option(
        request_id=result.request_id,
        option_id=result.selected_option_id,
        result_id=result.result_id,
    )
