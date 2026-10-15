from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase18b_opportunity_windows import (
    OPPORTUNITY_SUBMISSION_PAYLOAD_KEY,
    REACTION_DECISION_TYPE,
    BattlePhase,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    IntentMaterializationStatus,
    InterfaceIntent,
    JsonValue,
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
    OpportunityWindowError,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
    TriggerBatchingMode,
    WindowPassLedger,
    _intent,
    _opportunity_invalid_reason,
    _opportunity_window,
    _pass_action,
    _request_with_payload,
    _reroll_action,
    _result_with_submission,
    _smoke_action,
    _submission_with_action_drift,
    opportunity_submission_invalid_reason,
    pytest,
    replace,
)


def test_interface_intent_rejects_stale_expired_wrong_timing_and_target_drift() -> None:
    window = _opportunity_window(legal_actions=(_pass_action(), _smoke_action()))
    request = window.decision_request(
        request_id="phase18b-rejection-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
    )

    stale = replace(
        _intent(),
        based_on_state_hash="old-state-hash",
    ).materialize(
        window=window,
        request=request,
        current_sequence_number=12,
        result_id="phase18b-stale-result",
    )
    expired = replace(
        _intent(),
        expires_after_sequence=12,
    ).materialize(
        window=window,
        request=request,
        current_sequence_number=13,
        result_id="phase18b-expired-result",
    )
    wrong_timing = replace(
        _intent(),
        trigger_kind=TimingTriggerKind.END_PHASE,
    ).materialize(
        window=window,
        request=request,
        current_sequence_number=12,
        result_id="phase18b-wrong-timing-result",
    )
    target_drift = replace(
        _intent(),
        target_ids=("unit-99",),
    ).materialize(
        window=window,
        request=request,
        current_sequence_number=12,
        result_id="phase18b-target-drift-result",
    )

    assert stale.status is IntentMaterializationStatus.STALE_STATE_HASH
    assert expired.status is IntentMaterializationStatus.EXPIRED
    assert wrong_timing.status is IntentMaterializationStatus.WRONG_TIMING
    assert target_drift.status is IntentMaterializationStatus.TARGET_MISMATCH
    assert target_drift.to_payload()["result"] is None


__all__: list[str] = []
__all__ += ["BattlePhase", "DecisionOption", "DecisionRequest", "DecisionResult"]
__all__ += ["OPPORTUNITY_SUBMISSION_PAYLOAD_KEY", "InterfaceIntent", "JsonValue"]
__all__ += ["OpportunityActionKind", "OpportunityLegalAction", "OpportunityWindow"]
__all__ += ["OpportunityWindowError", "TimingWindow", "TimingWindowDescriptor"]
__all__ += ["TriggerBatchingMode", "WindowPassLedger", "_opportunity_invalid_reason"]
__all__ += ["_request_with_payload", "_reroll_action", "_result_with_submission"]
__all__ += ["_submission_with_action_drift", "cast", "opportunity_submission_invalid_reason"]
__all__ += ["pytest"]
