"""Gathered original rolls precede later-step choices through public authority."""

from typing import cast

from tests.lethal_hits_helpers import complete_attack
from tests.order128_helpers import assert_checkpoint
from tests.order135_gathered_step_helpers import native_gathered_shooting_request
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


def test_native_gathered_hit_and_wound_steps_precede_reroll_choices() -> None:
    session, request = native_gathered_shooting_request()
    proposal = proposal_from_request(
        request=request, target_unit_id="army-beta:scalar"
    ).to_payload()
    proposal["declarations"] = proposal["declarations"][:1]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="independent-multiattack-declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    checked_hit = False
    checked_wound = False
    for _ in range(80):
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        request = pending
        rolls = [
            cast(dict[str, JsonValue], event.payload)
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "dice_rolled"
        ]
        hits = [
            row
            for row in rolls
            if cast(dict[str, JsonValue], row["spec"])["roll_type"] == "attack_sequence.hit"
        ]
        wounds = [
            row
            for row in rolls
            if cast(dict[str, JsonValue], row["spec"])["roll_type"] == "attack_sequence.wound"
        ]
        if hits and not checked_hit:
            assert len(hits) == 3, "All gathered original Hits must exist before a Hit choice."
            assert not wounds
            assert_checkpoint(session)
            checked_hit = True
        if wounds:
            assert len(hits) == 3, "No Wound or wound reroll may precede another gathered Hit."
            hit_steps = [
                event.payload
                for event in session.lifecycle.decision_controller.event_log.records
                if event.event_type == "attack_sequence_step"
                and isinstance(event.payload, dict)
                and event.payload.get("step") == "hit"
            ]
            successful_hits = sum(
                cast(dict[str, JsonValue], row["payload"])["successful"] is True
                for row in hit_steps
            )
            assert len(wounds) == successful_hits
            assert_checkpoint(session)
            checked_wound = True
            break
        submit_fixture_request(session, request)
    assert checked_hit
    assert checked_wound
    complete_attack(session)
    assert_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    original_hits = [
        index
        for index, event in enumerate(events)
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.hit"
    ]
    original_wounds = [
        index
        for index, event in enumerate(events)
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.wound"
    ]
    assert len(original_hits) == 3
    assert max(original_hits) < min(original_wounds)
