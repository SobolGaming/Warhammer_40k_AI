from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase17n_primary_mission_helpers import (
    phase17n_action_opportunity_fixture,
    phase17n_consecrate_pending_fixture,
    phase17n_direct_action_pending_fixture,
    phase17n_locate_pending_fixture,
    phase17n_punishment_pending_fixture,
    phase17n_sensor_pending_fixture,
)

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_pending_request_integrity import (
    validate_primary_mission_pending_request_integrity,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

type PendingFixture = tuple[GameState, DecisionController, DecisionRequest]


@pytest.fixture(scope="module")
def action_opportunity() -> PendingFixture:
    return phase17n_action_opportunity_fixture()


@pytest.fixture(scope="module")
def direct_action() -> PendingFixture:
    return phase17n_direct_action_pending_fixture()


@pytest.fixture(scope="module")
def locate_choice() -> PendingFixture:
    return phase17n_locate_pending_fixture()


@pytest.fixture(scope="module")
def punishment_choice() -> PendingFixture:
    return phase17n_punishment_pending_fixture()


@pytest.fixture(scope="module")
def consecrate_choice() -> PendingFixture:
    return phase17n_consecrate_pending_fixture()


@pytest.fixture(scope="module")
def sensor_choice() -> PendingFixture:
    return phase17n_sensor_pending_fixture()


def test_pending_step4_families_accept_exact_authoritative_requests(
    action_opportunity: PendingFixture,
    direct_action: PendingFixture,
    locate_choice: PendingFixture,
    punishment_choice: PendingFixture,
    consecrate_choice: PendingFixture,
    sensor_choice: PendingFixture,
) -> None:
    for state, decisions, request in (
        action_opportunity,
        direct_action,
        locate_choice,
        punishment_choice,
        consecrate_choice,
        sensor_choice,
    ):
        _validate(state=state, decisions=decisions)
        restored = GameLifecycle.from_payload(
            GameLifecycle(decision_controller=decisions, state=state).to_payload()
        )
        assert restored.decision_controller.queue.pending_requests == (request,)


def test_restore_rejects_pending_step4_request_without_requested_event(
    action_opportunity: PendingFixture,
) -> None:
    state, decisions, _request = action_opportunity
    payload = GameLifecycle(
        decision_controller=decisions,
        state=state,
    ).to_payload()
    payload["decisions"]["event_log"] = [
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] != "decision_requested"
    ]

    with pytest.raises(
        GameLifecycleError,
        match="Primary mission Action checkpoint is orphaned",
    ):
        GameLifecycle.from_payload(payload)


def test_pending_primary_choice_rejects_missing_lifecycle_request_event(
    punishment_choice: PendingFixture,
) -> None:
    state, decisions, _request = punishment_choice
    payload = decisions.to_payload()
    payload["event_log"] = [
        event
        for event in payload["event_log"]
        if event["event_type"] != "primary_mission_choice_requested"
    ]
    forged_decisions = DecisionController.from_payload(payload)

    with pytest.raises(GameLifecycleError, match="impossible request event suffix"):
        _validate(state=state, decisions=forged_decisions)


def test_pending_step4_request_rejects_queue_event_inventory_drift(
    direct_action: PendingFixture,
) -> None:
    state, decisions, request = direct_action
    assert len(request.options) == 1
    forged_option = replace(request.options[0], label="Forged pending Action option")
    forged = replace(request, options=(forged_option,))
    forged_decisions = _controller_with_pending_request(
        decisions=decisions,
        request=forged,
        synchronize_requested_event=False,
    )

    with pytest.raises(
        GameLifecycleError,
        match="requires one exact decision_requested event",
    ):
        _validate(state=state, decisions=forged_decisions)

    synchronized = _controller_with_pending_request(
        decisions=decisions,
        request=forged,
        synchronize_requested_event=True,
    )
    with pytest.raises(
        GameLifecycleError,
        match="drifted from its authoritative inventory",
    ):
        _validate(state=state, decisions=synchronized)

    checkpointless_payload = deepcopy(decisions.to_payload())
    checkpointless_payload["event_log"] = [
        event
        for event in checkpointless_payload["event_log"]
        if event["event_type"] != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    ]
    for index, event in enumerate(checkpointless_payload["event_log"], start=1):
        event["event_id"] = f"event-{index:06d}"
    checkpointless = DecisionController.from_payload(checkpointless_payload)
    with pytest.raises(GameLifecycleError, match="boundary checkpoint event"):
        _validate(state=state, decisions=checkpointless)


def test_pending_action_opportunity_rejects_disappeared_opportunity(
    action_opportunity: PendingFixture,
) -> None:
    state, decisions, _request = action_opportunity
    forged_state = deepcopy(state)
    shooting_state = forged_state.shooting_phase_state
    assert shooting_state is not None
    forged_state.replace_shooting_phase_state(
        shooting_state.with_mission_action_opportunity_declined()
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"checkpoint context drifted|drifted from its authoritative inventory",
    ):
        _validate(state=forged_state, decisions=decisions)


def test_pending_action_rejects_battle_context_drift(
    action_opportunity: PendingFixture,
) -> None:
    state, decisions, _request = action_opportunity
    forged_state = deepcopy(state)
    forged_state.battle_round += 1
    shooting_state = forged_state.shooting_phase_state
    assert shooting_state is not None
    forged_state.replace_shooting_phase_state(
        replace(shooting_state, battle_round=forged_state.battle_round)
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"checkpoint context drifted|drifted from its authoritative inventory",
    ):
        _validate(state=forged_state, decisions=decisions)


def test_pending_locate_rejects_omitted_terrain_combination(
    locate_choice: PendingFixture,
) -> None:
    state, decisions, request = locate_choice
    assert len(request.options) > 1
    forged = replace(request, options=request.options[:-1])
    forged_decisions = _controller_with_pending_request(
        decisions=decisions,
        request=forged,
        synchronize_requested_event=True,
    )

    with pytest.raises(
        GameLifecycleError,
        match="drifted from its authoritative inventory",
    ):
        _validate(state=state, decisions=forged_decisions)


def test_pending_punishment_rejects_fallback_policy_drift(
    punishment_choice: PendingFixture,
) -> None:
    state, decisions, request = punishment_choice
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    assert not choice.used_fallback_candidates
    forged_choice = replace(choice, used_fallback_candidates=True)
    forged_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                replace(
                    PrimaryMissionChoiceData.from_payload(option.payload),
                    used_fallback_candidates=True,
                ).to_payload()
            ),
        )
        for option in request.options
    )
    forged = replace(
        request,
        payload=validate_json_value(forged_choice.to_payload()),
        options=forged_options,
    )
    forged_decisions = _controller_with_pending_request(
        decisions=decisions,
        request=forged,
        synchronize_requested_event=True,
    )

    with pytest.raises(
        GameLifecycleError,
        match="drifted from its authoritative inventory",
    ):
        _validate(state=state, decisions=forged_decisions)


def test_pending_consecrate_rejects_request_without_active_designation(
    consecrate_choice: PendingFixture,
) -> None:
    state, decisions, _request = consecrate_choice
    forged_state = deepcopy(state)
    progress = forged_state.primary_mission_progress_state
    assert progress.consecration_designations
    forged_state.primary_mission_progress_state = replace(
        progress,
        consecration_designations=(),
    )

    with pytest.raises(GameLifecycleError, match=r"Consecrate.*authority|drifted"):
        _validate(state=forged_state, decisions=decisions)


def test_pending_sensor_rejects_omitted_legal_marker(
    sensor_choice: PendingFixture,
) -> None:
    state, decisions, request = sensor_choice
    assert len(request.options) > 1
    removed_option = request.options[-1]
    removed_choice = PrimaryMissionChoiceData.from_payload(removed_option.payload)
    assert len(removed_choice.selected_target_ids) == 1
    omitted_marker_id = removed_choice.selected_target_ids[0]
    request_choice = PrimaryMissionChoiceData.from_payload(request.payload)
    forged_choice = replace(
        request_choice,
        legal_target_ids=tuple(
            marker_id
            for marker_id in request_choice.legal_target_ids
            if marker_id != omitted_marker_id
        ),
    )
    forged_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                replace(
                    PrimaryMissionChoiceData.from_payload(option.payload),
                    legal_target_ids=forged_choice.legal_target_ids,
                ).to_payload()
            ),
        )
        for option in request.options[:-1]
    )
    forged = replace(
        request,
        payload=validate_json_value(forged_choice.to_payload()),
        options=forged_options,
    )
    forged_decisions = _controller_with_pending_request(
        decisions=decisions,
        request=forged,
        synchronize_requested_event=True,
    )

    with pytest.raises(
        GameLifecycleError,
        match="drifted from its authoritative inventory",
    ):
        _validate(state=state, decisions=forged_decisions)


def test_pending_step4_rejects_two_request_queue(
    direct_action: PendingFixture,
) -> None:
    state, decisions, request = direct_action
    payload = decisions.to_payload()
    payload["queue"]["pending_requests"].append(
        replace(request, request_id="decision-request-impossible-second").to_payload()
    )
    forged_decisions = DecisionController.from_payload(payload)

    with pytest.raises(GameLifecycleError, match="sole authoritative queue head"):
        _validate(state=state, decisions=forged_decisions)


def test_pending_step4_rejects_existing_record_and_post_request_mutation(
    direct_action: PendingFixture,
) -> None:
    state, decisions, request = direct_action
    result = DecisionResult.for_request(
        result_id=f"{request.request_id}:forged-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    record = DecisionRecord(
        record_id="decision-record-000001",
        request=request,
        result=result,
    )
    recorded_payload = decisions.to_payload()
    recorded_payload["records"] = [record.to_payload()]
    recorded = DecisionController.from_payload(recorded_payload)
    with pytest.raises(GameLifecycleError, match="already has a DecisionRecord"):
        _validate(state=state, decisions=recorded)

    mutated = deepcopy(decisions)
    mutated.event_log.append(
        "mission_action_started",
        {
            "game_id": state.game_id,
            "request_id": request.request_id,
            "forged": True,
        },
    )
    with pytest.raises(GameLifecycleError, match="impossible post-request event suffix"):
        _validate(state=state, decisions=mutated)


def _validate(*, state: GameState, decisions: DecisionController) -> None:
    validate_primary_mission_pending_request_integrity(
        state=state,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )


def _controller_with_pending_request(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
    synchronize_requested_event: bool,
) -> DecisionController:
    payload = deepcopy(decisions.to_payload())
    payload["queue"]["pending_requests"] = [request.to_payload()]
    if synchronize_requested_event:
        original_request_id = decisions.queue.pending_requests[0].request_id
        for event in payload["event_log"]:
            if event["event_type"] != "decision_requested":
                continue
            event_payload = event["payload"]
            if not isinstance(event_payload, dict):
                continue
            if event_payload.get("request_id") == original_request_id:
                event["payload"] = cast(JsonValue, request.to_payload())
    return DecisionController.from_payload(payload)


__all__ = ()
