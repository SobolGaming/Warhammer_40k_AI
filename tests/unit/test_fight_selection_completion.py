"""04.03.05: consuming a Fight selection does not itself mean a unit fought."""

from __future__ import annotations

from typing import cast

import pytest
from tests.fight_completion_helpers import (
    assert_completion_round_trip,
    completion_session,
    drive_to_completion,
    engaging_completion_session,
    submit_completion_request,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.damage_allocation import SELECT_FEEL_NO_PAIN_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import FIGHT_INTERRUPT_DECISION_TYPE
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destructions,
)


@pytest.mark.parametrize("armed", [False, True])
@pytest.mark.parametrize("window", ["interrupt", "counteroffensive"])
def test_selection_completion_records_only_actual_fights_and_preserves_timing(
    armed: bool, window: str
) -> None:
    session = completion_session(
        armed=armed, interrupt=window == "interrupt", counteroffensive=window == "counteroffensive"
    )
    drive_to_completion(session, unit_id="army-alpha:subject")
    events = session.lifecycle.decision_controller.event_log.records
    fought = [event for event in events if event.event_type == "unit_has_fought"]
    assert len(fought) == int(armed)
    completed = [event for event in events if event.event_type == "fight_selection_completed"]
    assert len(completed) == 1
    assert isinstance(completed[0].payload, dict)
    assert completed[0].payload["has_fought"] is armed
    assert (completed[0].payload["attack_sequence_id"] is not None) is armed
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.fight_order_state.selected_to_fight_unit_ids == (
        "army-alpha:subject",
    )
    request = pending_request(session)
    expected = (
        FIGHT_INTERRUPT_DECISION_TYPE
        if window == "interrupt"
        else "submit_stratagem_target_proposal"
    )
    assert (request.decision_type == expected) is armed
    if armed:
        openings = [event for event in events if event.event_type == "reaction_window_opened"]
        assert openings or request.decision_type == expected
    restored = assert_completion_round_trip(session)
    for _ in range(30):
        state = restored.lifecycle.state
        assert state is not None
        if (
            state.fight_phase_state is None
            or state.fight_phase_state.current_step.value == "consolidate"
        ):
            break
        submit_completion_request(restored)
    selected = [
        event
        for event in restored.lifecycle.decision_controller.event_log.records
        if event.event_type in {"fight_activation_selected", "fight_interrupt_activation_selected"}
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("activation_selection"), dict)
        and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
            "unit_instance_id"
        )
        == "army-alpha:subject"
    ]
    assert len(selected) == 1
    assert_completion_round_trip(restored)


def test_armed_retained_fight_cleanup_preserves_completion_across_restore() -> None:
    armed = True
    session = completion_session(armed=armed, retained=True)
    subject_id = "army-beta:enemy"
    cleanup_seen = False
    for _ in range(100):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "fight_on_death_destruction_ready" for event in events):
            cleanup_seen = True
            state = session.lifecycle.state
            assert state is not None
            assert state.fight_phase_state is not None
            assert state.fight_phase_state.active_activation is not None
            assert state.fight_phase_state.active_activation.unit_instance_id == subject_id
            request = pending_request(session)
            assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            assert isinstance(request.payload, dict)
            lost_wound = request.payload["lost_wound_context"]
            assert isinstance(lost_wound, dict)
            assert lost_wound["source_rule_id"] == "order102-demise"
            assert lost_wound["target_unit_instance_id"] == "army-alpha:observer"
            source_context = lost_wound["source_context"]
            assert isinstance(source_context, dict)
            assert source_context["source_kind"] == "deadly_demise"
            assert (
                len(
                    [
                        event
                        for event in events
                        if event.event_type == "fight_selection_completed"
                        and isinstance(event.payload, dict)
                        and event.payload.get("activation_selection")
                        == state.fight_phase_state.active_activation.to_payload()
                    ]
                )
                == 1
            )
            assert not any(
                event.event_type == "fight_activation_completed"
                and isinstance(event.payload, dict)
                and event.payload.get("unit_instance_id") == subject_id
                for event in events
            )
            session = assert_completion_round_trip(session)
            assert pending_request(session) == request
            break
        submit_completion_request(session)
    assert cleanup_seen
    drive_to_completion(session, unit_id=subject_id)
    events = session.lifecycle.decision_controller.event_log.records
    fought = [
        event
        for event in events
        if event.event_type == "unit_has_fought"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("activation_selection"), dict)
        and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
            "unit_instance_id"
        )
        == subject_id
    ]
    assert len(fought) == int(armed)
    completions = [
        event
        for event in events
        if event.event_type == "fight_selection_completed"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("activation_selection"), dict)
        and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
            "unit_instance_id"
        )
        == subject_id
    ]
    assert len(completions) == 1
    assert isinstance(completions[0].payload, dict)
    assert completions[0].payload["has_fought"] is armed
    final_completions = [
        event
        for event in events
        if event.event_type == "fight_activation_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == subject_id
    ]
    assert len(final_completions) == 1
    cleanup_completed = [
        event for event in events if event.event_type == "fight_on_death_destruction_completed"
    ]
    assert len(cleanup_completed) == 1
    assert events.index(completions[0]) < events.index(cleanup_completed[0])
    assert events.index(cleanup_completed[0]) < events.index(final_completions[0])
    assert (
        len(
            [
                event
                for event in events
                if event.event_type == "fight_activation_selected"
                and isinstance(event.payload, dict)
                and isinstance(event.payload.get("activation_selection"), dict)
                and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
                    "unit_instance_id"
                )
                == subject_id
            ]
        )
        == 1
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.removed_model_ids
    assert_completion_round_trip(session)


def test_empty_retained_selection_waits_for_phase_end_cleanup_across_restore() -> None:
    session = completion_session(armed=False, retained=True)
    subject_id = "army-beta:enemy"
    drive_to_completion(session, unit_id=subject_id)
    state = session.lifecycle.state
    assert state is not None
    records = retained_destructions(state=state)
    assert len(records) == 1
    assert records[0].stage is RetainedDestructionStage.WAITING
    assert state.battlefield_state is not None
    assert records[0].model_instance_id not in state.battlefield_state.removed_model_ids
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.active_activation is None
    assert subject_id in state.fight_phase_state.fight_order_state.selected_to_fight_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(event.event_type == "fight_on_death_destruction_ready" for event in events)
    session = assert_completion_round_trip(session)
    # Continue the remaining Fight play through the existing end-of-phase owner.
    for _ in range(100):
        events = session.lifecycle.decision_controller.event_log.records
        ready = [
            event for event in events if event.event_type == "fight_on_death_destruction_ready"
        ]
        if ready:
            assert len(ready) == 1
            assert isinstance(ready[0].payload, dict)
            assert ready[0].payload["reason"] == "phase_end"
            request = pending_request(session)
            assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
            assert isinstance(request.payload, dict)
            wound = request.payload["lost_wound_context"]
            assert isinstance(wound, dict)
            assert wound["source_rule_id"] == "order102-demise"
            assert wound["target_unit_instance_id"] == "army-alpha:observer"
            session = assert_completion_round_trip(session)
            assert pending_request(session) == request
            break
        state = session.lifecycle.state
        assert state is not None
        assert retained_destructions(state=state)[0].stage is RetainedDestructionStage.WAITING
        submit_completion_request(session)
    else:
        raise AssertionError("Empty retained selection did not reach phase-end cleanup.")
    for _ in range(30):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "fight_on_death_destruction_completed" for event in events):
            break
        submit_completion_request(session)
    else:
        raise AssertionError("Phase-end cleanup did not complete.")
    selected = [
        event
        for event in events
        if event.event_type == "fight_activation_selected"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("activation_selection"), dict)
        and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
            "unit_instance_id"
        )
        == subject_id
    ]
    completions = [
        event
        for event in events
        if event.event_type == "fight_selection_completed"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("activation_selection"), dict)
        and cast(dict[str, JsonValue], event.payload["activation_selection"]).get(
            "unit_instance_id"
        )
        == subject_id
    ]
    final = [
        event
        for event in events
        if event.event_type == "fight_activation_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == subject_id
    ]
    assert len(selected) == len(completions) == len(final) == 1
    assert isinstance(completions[0].payload, dict)
    assert completions[0].payload["has_fought"] is False
    assert not any(
        event.event_type == "unit_has_fought"
        and isinstance(event.payload, dict)
        and event.payload.get("activation_selection")
        == completions[0].payload["activation_selection"]
        for event in events
    )
    cleanup = [
        event for event in events if event.event_type == "fight_on_death_destruction_completed"
    ]
    assert len(cleanup) == 1
    assert events.index(final[0]) < events.index(ready[0]) < events.index(cleanup[0])
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert records[0].model_instance_id in state.battlefield_state.removed_model_ids
    assert_completion_round_trip(session)


def test_armed_selection_without_a_melee_target_completes_without_fighting() -> None:
    session = completion_session(armed=True, no_target=True)
    drive_to_completion(session, unit_id="army-alpha:subject")
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(event.event_type == "attack_sequence_step" for event in events)
    assert not any(event.event_type == "unit_has_fought" for event in events)
    completed = [event for event in events if event.event_type == "fight_selection_completed"]
    assert len(completed) == 1
    assert isinstance(completed[0].payload, dict)
    assert completed[0].payload["has_fought"] is False
    assert_completion_round_trip(session)


@pytest.mark.parametrize("automatic_hit", [False, True], ids=["miss", "automatic-hit"])
def test_actual_melee_attempt_counts_even_when_it_misses_or_hits_automatically(
    automatic_hit: bool,
) -> None:
    session = completion_session(armed=True, automatic_hit=automatic_hit, miss=not automatic_hit)
    drive_to_completion(session, unit_id="army-alpha:subject")
    events = session.lifecycle.decision_controller.event_log.records
    hit_steps = [
        event
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
    ]
    assert len(hit_steps) == 1
    assert isinstance(hit_steps[0].payload, dict)
    hit = hit_steps[0].payload["payload"]
    assert isinstance(hit, dict)
    assert hit["successful"] is automatic_hit
    assert hit["skipped"] is automatic_hit
    assert len([event for event in events if event.event_type == "unit_has_fought"]) == 1
    assert len([event for event in events if event.event_type == "fight_selection_completed"]) == 1
    assert_completion_round_trip(session)


@pytest.mark.parametrize("fight_type", ["normal", "overrun"])
def test_engaging_response_preserves_empty_selection_and_resumes_once(fight_type: str) -> None:
    session = engaging_completion_session(fight_type=fight_type)
    events = session.lifecycle.decision_controller.event_log.records
    completed = [event for event in events if event.event_type == "fight_selection_completed"]
    assert len(completed) == 2
    assert isinstance(completed[0].payload, dict)
    assert completed[0].payload["has_fought"] is False
    assert isinstance(completed[1].payload, dict)
    assert completed[1].payload["has_fought"] is True
    assert len([event for event in events if event.event_type == "unit_has_fought"]) == 1
    assert len([event for event in events if event.event_type == "fight_activation_completed"]) == 2
    resumed = [
        event for event in events if event.event_type == "forced_fight_activation_queue_completed"
    ]
    assert len(resumed) == 1
    assert isinstance(resumed[0].payload, dict)
    assert resumed[0].payload["resumed_state"] is not None
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.forced_activation_context is None
    assert state.fight_phase_state.fight_order_state.selected_to_fight_unit_ids == (
        "army-alpha:subject",
        "army-beta:enemy",
    )
    assert_completion_round_trip(session)
