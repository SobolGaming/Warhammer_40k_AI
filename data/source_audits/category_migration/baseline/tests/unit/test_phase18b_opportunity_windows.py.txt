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


def test_opportunity_window_builds_batched_request_with_stable_fingerprint() -> None:
    window = _opportunity_window(
        legal_actions=(
            _pass_action(),
            _reroll_action(),
            _smoke_action(),
        )
    )

    request = window.decision_request(
        request_id="phase18b-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
        handler_payload={"host": "shooting_defensive_window"},
    )
    request_payload = cast(dict[str, object], request.payload)
    opportunity_payload = cast(dict[str, object], request_payload["opportunity_window"])
    option_payload = cast(dict[str, object], request.option_by_id("use_smoke").payload)
    action_payload = cast(dict[str, object], option_payload["action"])

    assert request.decision_type == REACTION_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert tuple(option.option_id for option in request.options) == (
        "pass",
        "reroll_failed_save",
        "use_smoke",
    )
    assert opportunity_payload["window_id"] == "phase18b-opportunity-window"
    assert option_payload["submission_kind"] == "opportunity_action"
    assert action_payload["batching_mode"] == TriggerBatchingMode.WHOLE_GROUP.value
    assert OpportunityWindow.from_payload(window.to_payload()) == window

    reordered = replace(
        window,
        legal_actions=(
            _smoke_action(),
            _pass_action(),
            _reroll_action(),
        ),
    )
    assert reordered.legal_action_fingerprint("player-b") == window.legal_action_fingerprint(
        "player-b"
    )


def test_window_pass_ledger_suppresses_only_unchanged_revision_and_actions() -> None:
    window = _opportunity_window(legal_actions=(_pass_action(), _smoke_action()))
    ledger = WindowPassLedger()

    assert ledger.should_prompt(window=window, player_id="player-b") is True
    recorded = ledger.record_pass(window=window, player_id="player-b")

    assert ledger.should_prompt(window=window, player_id="player-b") is False
    assert WindowPassLedger.from_payload(ledger.to_payload()).passes == (recorded,)

    revised = replace(window, revision=2)
    assert ledger.should_prompt(window=revised, player_id="player-b") is True

    changed_actions = replace(
        window,
        legal_actions=(
            _pass_action(),
            _reroll_action(),
            _smoke_action(),
        ),
    )
    assert ledger.should_prompt(window=changed_actions, player_id="player-b") is True


def test_interface_intent_materializes_as_normal_decision_result_only_for_current_window() -> None:
    window = _opportunity_window(legal_actions=(_pass_action(), _smoke_action()))
    request = window.decision_request(
        request_id="phase18b-current-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
    )
    intent = InterfaceIntent(
        intent_id="phase18b-smoke-intent",
        player_id="player-b",
        action_id="use_smoke",
        source_id="core:smoke",
        target_ids=("unit-17",),
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        created_sequence_number=11,
        expires_after_sequence=30,
        based_on_state_hash="state-hash-001",
        payload={"client_surface": "reaction_tray"},
    )

    materialized = intent.materialize(
        window=window,
        request=request,
        current_sequence_number=12,
        result_id="phase18b-result",
    )

    assert materialized.status is IntentMaterializationStatus.MATERIALIZED
    assert materialized.result is not None
    assert materialized.result.selected_option_id == "use_smoke"
    materialized.result.validate_for_request(request)
    assert InterfaceIntent.from_payload(intent.to_payload()) == intent

    unrelated_request = DecisionRequest(
        request_id="phase18b-unrelated-request",
        decision_type=REACTION_DECISION_TYPE,
        actor_id="player-b",
        payload={"not": "an opportunity window"},
        options=(DecisionOption(option_id="use_smoke", label="Use Smoke", payload=None),),
    )
    rejected = intent.materialize(
        window=window,
        request=unrelated_request,
        current_sequence_number=12,
        result_id="phase18b-unrelated-result",
    )

    assert rejected.status is IntentMaterializationStatus.REQUEST_MISMATCH
    assert rejected.result is None


def test_interface_intent_rejects_stale_window_object_with_same_window_id() -> None:
    stale_window = _opportunity_window(legal_actions=(_pass_action(), _smoke_action()))
    current_window = replace(
        stale_window,
        legal_actions=(
            _pass_action(),
            OpportunityLegalAction(
                action_id="use_smoke",
                source_id="core:smoke",
                action_kind=OpportunityActionKind.STRATAGEM,
                controller_id="player-b",
                label="Use Smoke Elsewhere",
                cost=({"resource": "cp", "amount": 1},),
                target_ids=("unit-99",),
                target_spec={"unit_instance_id": "unit-99"},
                batching_mode=TriggerBatchingMode.WHOLE_GROUP,
                payload={"stratagem_id": "smoke", "target_unit_instance_id": "unit-99"},
            ),
        ),
    )
    request = current_window.decision_request(
        request_id="phase18b-current-window-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
    )

    rejected = _intent().materialize(
        window=stale_window,
        request=request,
        current_sequence_number=12,
        result_id="phase18b-stale-window-intent",
    )

    assert rejected.status is IntentMaterializationStatus.REQUEST_MISMATCH
    assert rejected.result is None
    diagnostic = cast(dict[str, object], rejected.diagnostic)
    assert diagnostic["reason"] == "window_payload_mismatch"


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


def test_opportunity_submission_validator_rejects_supported_negative_paths() -> None:
    window = _opportunity_window(legal_actions=(_pass_action(), _smoke_action()))
    request = window.decision_request(
        request_id="phase18b-validator-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
    )
    result = DecisionResult.for_request(
        request=request,
        selected_option_id="use_smoke",
        result_id="phase18b-validator-result",
    )

    assert (
        _opportunity_invalid_reason(
            request=request,
            result=result,
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        is None
    )
    assert (
        _opportunity_invalid_reason(
            request=request,
            result=result,
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number + 1,
        )
        == "stale_opportunity_sequence"
    )
    assert (
        _opportunity_invalid_reason(
            request=request,
            result=replace(result, payload=None),
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "malformed_opportunity_submission"
    )
    assert (
        _opportunity_invalid_reason(
            request=request,
            result=replace(result, selected_option_id="pass"),
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "opportunity_action_mismatch"
    )
    assert (
        _opportunity_invalid_reason(
            request=request,
            result=_result_with_submission(
                result,
                _submission_with_action_drift(result, label="Changed Smoke"),
            ),
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "opportunity_action_drift"
    )
    assert (
        _opportunity_invalid_reason(
            request=request,
            result=_result_with_submission(
                result,
                window.submission_payload_for_action(
                    action=OpportunityLegalAction(
                        action_id="missing_action",
                        source_id="core:smoke",
                        action_kind=OpportunityActionKind.STRATAGEM,
                        controller_id="player-b",
                        label="Missing Action",
                    ),
                    player_id="player-b",
                    legal_action_fingerprint=window.legal_action_fingerprint("player-b"),
                ),
                selected_option_id="missing_action",
            ),
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "opportunity_action_unavailable"
    )
    assert (
        _opportunity_invalid_reason(
            request=_request_with_payload(
                request,
                {
                    **cast(dict[str, object], request.payload),
                    "legal_action_fingerprint": "phase18b-fingerprint-drift",
                },
            ),
            result=result,
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "opportunity_fingerprint_mismatch"
    )


def test_opportunity_submission_validator_rejects_wrong_player_action() -> None:
    window = _opportunity_window(
        legal_actions=(
            _pass_action(),
            OpportunityLegalAction(
                action_id="player_a_smoke",
                source_id="core:smoke",
                action_kind=OpportunityActionKind.STRATAGEM,
                controller_id="player-a",
                label="Player A Smoke",
                target_ids=("unit-17",),
            ),
        ),
        eligible_player_ids=("player-a", "player-b"),
        priority_order=("player-a", "player-b"),
    )
    request = window.decision_request(
        request_id="phase18b-wrong-player-request",
        actor_id="player-b",
        decision_type=REACTION_DECISION_TYPE,
    )
    result = DecisionResult(
        request_id=request.request_id,
        result_id="phase18b-wrong-player-result",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="player_a_smoke",
        payload=window.submission_payload_for_action(
            action=window.action_by_id("player_a_smoke"),
            player_id="player-a",
            legal_action_fingerprint=window.legal_action_fingerprint("player-b"),
        ),
    )

    assert (
        _opportunity_invalid_reason(
            request=request,
            result=result,
            current_state_hash=window.state_hash,
            current_sequence_number=window.sequence_number,
        )
        == "opportunity_action_wrong_player"
    )


def test_opportunity_window_fail_fast_validation() -> None:
    with pytest.raises(OpportunityWindowError, match="priority_order must cover"):
        _opportunity_window(
            eligible_player_ids=("player-a", "player-b"),
            priority_order=("player-a",),
        )

    with pytest.raises(OpportunityWindowError, match="default action must be a pass"):
        _opportunity_window(
            legal_actions=(_pass_action(), _smoke_action()),
            default_action_id="use_smoke",
        )

    with pytest.raises(OpportunityWindowError, match="duplicate action_id"):
        _opportunity_window(legal_actions=(_pass_action(), _pass_action()))

    with pytest.raises(OpportunityWindowError, match="Non-pass opportunity actions"):
        OpportunityLegalAction(
            action_id="controllerless_stratagem",
            source_id="core:bad",
            action_kind=OpportunityActionKind.STRATAGEM,
            controller_id=None,
            label="Controllerless Stratagem",
        )

    with pytest.raises(OpportunityWindowError, match="expiration must not precede creation"):
        replace(_intent(), expires_after_sequence=10)


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
