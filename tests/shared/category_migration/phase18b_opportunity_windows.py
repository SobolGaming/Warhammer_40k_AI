from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.opportunity_windows import (
    OPPORTUNITY_SUBMISSION_PAYLOAD_KEY,
    IntentMaterializationStatus,
    InterfaceIntent,
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
    OpportunityWindowError,
    TriggerBatchingMode,
    WindowPassLedger,
    opportunity_submission_invalid_reason,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reaction_queue import REACTION_DECISION_TYPE
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


def _opportunity_invalid_reason(
    *,
    request: DecisionRequest,
    result: DecisionResult,
    current_state_hash: str,
    current_sequence_number: int,
) -> str | None:
    return opportunity_submission_invalid_reason(
        request=request,
        result=result,
        current_state_hash=current_state_hash,
        current_sequence_number=current_sequence_number,
    )


def _result_with_submission(
    result: DecisionResult,
    submission: object,
    *,
    selected_option_id: str | None = None,
) -> DecisionResult:
    payload = {OPPORTUNITY_SUBMISSION_PAYLOAD_KEY: submission}
    return replace(
        result,
        selected_option_id=result.selected_option_id
        if selected_option_id is None
        else selected_option_id,
        payload=cast(JsonValue, payload),
    )


def _submission_with_action_drift(result: DecisionResult, *, label: str) -> dict[str, object]:
    payload = cast(dict[str, object], result.payload)
    if OPPORTUNITY_SUBMISSION_PAYLOAD_KEY in payload:
        submission = dict(cast(dict[str, object], payload[OPPORTUNITY_SUBMISSION_PAYLOAD_KEY]))
    else:
        submission = dict(payload)
    action = dict(cast(dict[str, object], submission["action"]))
    action["label"] = label
    submission["action"] = action
    return submission


def _request_with_payload(request: DecisionRequest, payload: object) -> DecisionRequest:
    return replace(request, payload=cast(JsonValue, payload))


def _intent() -> InterfaceIntent:
    return InterfaceIntent(
        intent_id="phase18b-intent",
        player_id="player-b",
        action_id="use_smoke",
        source_id="core:smoke",
        target_ids=("unit-17",),
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        created_sequence_number=11,
        expires_after_sequence=30,
        based_on_state_hash="state-hash-001",
    )


def _opportunity_window(
    *,
    legal_actions: tuple[OpportunityLegalAction, ...] = (),
    eligible_player_ids: tuple[str, ...] = ("player-b",),
    priority_order: tuple[str, ...] = ("player-b",),
    default_action_id: str = "pass",
) -> OpportunityWindow:
    actions = legal_actions or (_pass_action(), _smoke_action())
    timing_window = TimingWindow(
        window_id="phase18b-timing-window",
        descriptor=TimingWindowDescriptor(
            descriptor_id="phase18b-timing-descriptor",
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            source_rule_id="core:timing-source",
            phase=BattlePhase.SHOOTING,
        ),
        game_id="phase18b-game",
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.SHOOTING,
        trigger_event_id="event-000123",
    )
    return OpportunityWindow(
        window_id="phase18b-opportunity-window",
        timing_window=timing_window,
        state_hash="state-hash-001",
        sequence_number=12,
        revision=1,
        anchor_event_ids=("event-000123",),
        acting_player_id="player-a",
        eligible_player_ids=eligible_player_ids,
        priority_order=priority_order,
        legal_actions=actions,
        default_action_id=default_action_id,
        metadata={"roll_group_id": "roll-group-88"},
    )


def _pass_action() -> OpportunityLegalAction:
    return OpportunityLegalAction(
        action_id="pass",
        source_id="core:pass",
        action_kind=OpportunityActionKind.PASS,
        controller_id=None,
        label="Pass",
        payload={"pass": True},
    )


def _smoke_action() -> OpportunityLegalAction:
    return OpportunityLegalAction(
        action_id="use_smoke",
        source_id="core:smoke",
        action_kind=OpportunityActionKind.STRATAGEM,
        controller_id="player-b",
        label="Use Smoke",
        cost=({"resource": "cp", "amount": 1},),
        target_ids=("unit-17",),
        target_spec={"unit_instance_id": "unit-17"},
        batching_mode=TriggerBatchingMode.WHOLE_GROUP,
        payload={"stratagem_id": "smoke", "target_unit_instance_id": "unit-17"},
    )


def _reroll_action() -> OpportunityLegalAction:
    return OpportunityLegalAction(
        action_id="reroll_failed_save",
        source_id="core:command-reroll",
        action_kind=OpportunityActionKind.REROLL,
        controller_id="player-b",
        label="Reroll Failed Save",
        target_ids=("roll-000041",),
        target_spec={"roll_ids": ["roll-000041", "roll-000042"]},
        batching_mode=TriggerBatchingMode.ONE_OF,
        payload={"roll_id": "roll-000041"},
    )


__all__: list[str] = []
__all__ += ["BattlePhase", "DecisionOption", "DecisionRequest", "DecisionResult"]
__all__ += ["IntentMaterializationStatus", "InterfaceIntent", "JsonValue"]
__all__ += ["OPPORTUNITY_SUBMISSION_PAYLOAD_KEY", "OpportunityActionKind"]
__all__ += ["OpportunityLegalAction", "OpportunityWindow", "OpportunityWindowError"]
__all__ += ["REACTION_DECISION_TYPE", "TimingTriggerKind", "TimingWindow"]
__all__ += ["TimingWindowDescriptor", "TriggerBatchingMode", "WindowPassLedger", "_intent"]
__all__ += ["_opportunity_invalid_reason", "_opportunity_window", "_pass_action"]
__all__ += ["_request_with_payload", "_reroll_action", "_result_with_submission", "_smoke_action"]
__all__ += ["_submission_with_action_drift", "cast", "opportunity_submission_invalid_reason"]
__all__ += ["pytest", "replace"]
