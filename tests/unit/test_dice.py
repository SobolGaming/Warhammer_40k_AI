from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRerollRecord,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSource,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.engine.decision import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DiceRollManager,
)
from warhammer40k_core.engine.event_log import EventLog, EventLogError, EventRecord, JsonValue


def _select_unit_request(request_id: str = "decision-request-branch") -> DecisionRequest:
    return DecisionRequest(
        request_id=request_id,
        decision_type="select_unit",
        actor_id=None,
        payload={"phase": "movement"},
        options=(
            DecisionOption(
                option_id="unit-a",
                label="Unit A",
                payload={"selected_unit_id": "unit-a"},
            ),
            DecisionOption(
                option_id="unit-b",
                label="Unit B",
                payload={"selected_unit_id": "unit-b"},
            ),
        ),
    )


def test_same_seed_determinism_for_dice_rolls_and_events() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Intercessor unit advances",
        roll_type="advance_roll",
        actor_id="unit-intercessors",
    )
    left = DiceRollManager("seed")
    right = DiceRollManager("seed")

    left_state = left.roll(spec)
    right_state = right.roll(spec)

    assert left_state.to_payload() == right_state.to_payload()
    assert left.event_log.to_payload() == right.event_log.to_payload()


def test_branch_decision_history_affects_dice_deterministically() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=100_000),
        reason="Advance after branch choice",
        roll_type="advance_roll",
    )
    left = DiceRollManager("seed")
    right = DiceRollManager("seed")
    request = _select_unit_request()

    left.record_decision(
        request=request,
        result=DecisionResult.for_request(
            result_id="decision-result-branch-a",
            request=request,
            selected_option_id="unit-a",
        ),
    )
    right.record_decision(
        request=request,
        result=DecisionResult.for_request(
            result_id="decision-result-branch-b",
            request=request,
            selected_option_id="unit-b",
        ),
    )

    assert left.roll(spec).current_values == (84072,)
    assert right.roll(spec).current_values == (31999,)


def test_reconstructed_decision_record_history_affects_next_dice_roll() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=100_000),
        reason="Roll after decision reconstruction",
        roll_type="advance_roll",
    )
    request = _select_unit_request("decision-request-1")
    original = DiceRollManager("seed")
    original.record_decision(
        request=request,
        result=DecisionResult.for_request(
            result_id="decision-result-1",
            request=request,
            selected_option_id="unit-a",
        ),
    )
    saved_history = original.event_log.to_payload()
    original_next = original.roll(spec)

    reconstructed = DiceRollManager("seed", event_log=EventLog.from_payload(saved_history))
    reconstructed_next = reconstructed.roll(spec)

    assert reconstructed.decision_records == original.decision_records
    assert reconstructed_next.to_payload() == original_next.to_payload()


def test_reconstructed_decision_records_advance_record_id_counter() -> None:
    first_request = _select_unit_request("decision-request-1")
    original = DiceRollManager("seed")
    original.record_decision(
        request=first_request,
        result=DecisionResult.for_request(
            result_id="decision-result-1",
            request=first_request,
            selected_option_id="unit-a",
        ),
    )
    reconstructed = DiceRollManager(
        "seed",
        event_log=EventLog.from_payload(original.event_log.to_payload()),
    )
    second_request = _select_unit_request("decision-request-2")
    reconstructed.record_decision(
        request=second_request,
        result=DecisionResult.for_request(
            result_id="decision-result-2",
            request=second_request,
            selected_option_id="unit-b",
        ),
    )

    assert reconstructed.decision_records[-1].record_id == "decision-record-000002"


def test_reconstructed_pending_decision_request_history_affects_next_dice_roll() -> None:
    fixed_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Fixed roll before pending reroll request",
        roll_type="advance_roll",
    )
    next_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=100_000),
        reason="Roll after pending decision request reconstruction",
        roll_type="battle_shock_roll",
    )
    original = DiceRollManager("seed")
    state = original.roll_fixed(fixed_spec, [2])
    original.request_reroll(state, allowed_selections=((0,),))
    saved_history = original.event_log.to_payload()
    original_next = original.roll(next_spec)

    reconstructed = DiceRollManager("seed", event_log=EventLog.from_payload(saved_history))
    reconstructed_next = reconstructed.roll(next_spec)

    assert reconstructed_next.to_payload() == original_next.to_payload()


def test_reconstructed_event_history_affects_next_dice_roll() -> None:
    fixed_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Existing event history fixture",
        roll_type="advance_roll",
    )
    next_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Roll after existing event history",
        roll_type="battle_shock_roll",
    )
    original_manager = DiceRollManager("seed")
    original_manager.roll_fixed(fixed_spec, [4])
    saved_history = original_manager.event_log.to_payload()
    original_next = original_manager.roll(next_spec)

    reconstructed = DiceRollManager(
        "seed",
        event_log=EventLog.from_payload(saved_history),
    )
    reconstructed_next = reconstructed.roll(next_spec)

    assert reconstructed_next.to_payload() == original_next.to_payload()


def test_reconstructed_rng_event_history_restores_next_random_roll_after_rng_roll() -> None:
    first_spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Initial random charge roll",
        roll_type="charge_roll",
    )
    next_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Next random advance roll",
        roll_type="advance_roll",
    )

    original = DiceRollManager("seed")
    original.roll(first_spec)
    saved_history = original.event_log.to_payload()
    original_next = original.roll(next_spec)

    reconstructed = DiceRollManager(
        "seed",
        event_log=EventLog.from_payload(saved_history),
    )
    reconstructed_next = reconstructed.roll(next_spec)

    assert reconstructed.rng.draw_count == 3
    assert reconstructed_next.to_payload() == original_next.to_payload()


def test_reconstructed_rng_dice_event_advances_draw_count() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6),
        reason="Initial random battle-shock roll",
        roll_type="battle_shock_roll",
    )
    original = DiceRollManager("seed")
    original.roll(spec)

    reconstructed = DiceRollManager(
        "seed",
        event_log=EventLog.from_payload(original.event_log.to_payload()),
    )

    assert reconstructed.rng.draw_count == 3


def test_reconstructed_fixed_dice_event_does_not_advance_draw_count() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6),
        reason="Fixed reconstruction fixture",
        roll_type="advance_roll",
    )
    original = DiceRollManager("seed")
    original.roll_fixed(spec, [1, 2, 3])

    reconstructed = DiceRollManager(
        "seed",
        event_log=EventLog.from_payload(original.event_log.to_payload()),
    )

    assert reconstructed.rng.draw_count == 0


def test_reconstructed_injected_dice_event_does_not_advance_draw_count() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Injected reconstruction fixture",
        roll_type="advance_roll",
    )
    event_log = EventLog()
    event_log.append(
        "dice_rolled",
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=spec,
            values=[4, 5],
            source="injected",
        ).to_payload(),
    )

    reconstructed = DiceRollManager("seed", event_log=event_log)

    assert reconstructed.rng.draw_count == 0


def test_reconstructed_dice_history_validates_complete_dice_result_payload() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Corrupted reconstruction fixture",
        roll_type="advance_roll",
    )
    corrupted = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=spec,
        values=[4, 5],
        source="rng",
    ).to_payload()
    corrupted["total"] = 99
    event_log = EventLog.from_payload(
        [
            {
                "event_id": "event-000001",
                "event_type": "dice_rolled",
                "payload": cast(JsonValue, corrupted),
            }
        ]
    )

    with pytest.raises(DiceRollSpecError):
        DiceRollManager("seed", event_log=event_log)


def test_reroll_selection_is_an_explicit_decision() -> None:
    manager = DiceRollManager("seed")
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Charge distance for Assault Intercessors",
        roll_type="charge_roll",
        actor_id="unit-assault-intercessors",
    )
    state = manager.roll_fixed(spec, [1, 4])
    permission = RerollPermission(
        source_id="test-partial-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )
    request = manager.request_reroll(state, permission=permission)

    rejected = DecisionResult(
        result_id="decision-result-bad",
        request_id="wrong-request",
        decision_type="select_dice_reroll",
        actor_id="unit-assault-intercessors",
        selected_option_id="reroll:0",
        payload={"selected_indices": [0]},
    )
    with pytest.raises(DecisionError):
        manager.resolve_reroll(state, request=request, result=rejected)

    accepted = DecisionResult.for_request(
        result_id="decision-result-reroll-low-die",
        request=request,
        selected_option_id="reroll:0",
    )
    updated = manager.resolve_reroll(state, request=request, result=accepted)

    assert manager.decision_records[0].result == accepted
    assert updated.rerolls[0].decision_id == accepted.result_id
    assert updated.rerolls[0].selected_indices == (0,)
    assert updated.current_values[1] == 4


def test_reroll_forbidden_roll_spec_rejects_reroll_request() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Indirect Fire hit roll with forbidden rerolls",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
        reroll_forbidden_rule_ids=("weapon-ability:indirect-fire:no-hit-rerolls",),
    )
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(spec, [4])

    with pytest.raises(DecisionError, match="forbid rerolls"):
        manager.request_reroll(state, allowed_selections=((0,),))

    assert state.original_result.spec.to_payload()["reroll_forbidden_rule_ids"] == [
        "weapon-ability:indirect-fire:no-hit-rerolls"
    ]


def test_reroll_request_uses_explicit_allowed_selections_not_power_set() -> None:
    manager = DiceRollManager("seed")
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Charge distance whole-test reroll fixture",
        roll_type="charge_roll",
    )
    state = manager.roll_fixed(spec, [1, 4])

    request = manager.request_reroll(state, allowed_selections=((0, 1),))
    payload = cast(dict[str, JsonValue], request.payload)

    assert tuple(option.option_id for option in request.options) == ("decline", "reroll:0,1")
    assert payload["allowed_selections"] == [[0, 1]]


def test_reroll_request_rejects_duplicate_or_out_of_range_selection() -> None:
    manager = DiceRollManager("seed")
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Reroll selection validation fixture",
        roll_type="charge_roll",
    )
    state = manager.roll_fixed(spec, [1, 4])

    with pytest.raises(DecisionError):
        manager.request_reroll(state, allowed_selections=((0,), (0,)))
    with pytest.raises(DecisionError):
        manager.request_reroll(state, allowed_selections=((0, 0),))
    with pytest.raises(DecisionError):
        manager.request_reroll(state, allowed_selections=((2,),))


def test_replay_injected_dice_reproduce_original_result() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6, modifier=1),
        reason="Battle-shock test for Terminator Squad",
        roll_type="battle_shock_roll",
        actor_id="unit-terminators",
    )
    original_manager = DiceRollManager("original-seed")
    original = original_manager.roll(spec).original_result

    replay_manager = DiceRollManager("different-seed", injected_results=[original.to_payload()])
    replayed = replay_manager.roll(spec).original_result

    assert replayed.to_payload() == original.to_payload()
    assert replay_manager.event_log.to_payload()[0]["payload"] == original.to_payload()


def test_fixed_dice_are_supported_and_serializable() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Fixed advance roll for replay fixture",
        roll_type="advance_roll",
    )
    state = DiceRollManager("seed").roll_fixed(spec, [6])

    assert state.original_result.source == "fixed"
    assert state.current_total == 6


def test_unlabeled_dice_request_is_invalid() -> None:
    with pytest.raises(DiceRollSpecError):
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="",
            roll_type="advance_roll",
        )

    with pytest.raises(DiceRollSpecError):
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="get_roll(D6)",
            roll_type="advance_roll",
        )

    with pytest.raises(DiceRollSpecError):
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Advance for Intercessors",
            roll_type="D6",
        )


def test_dice_result_and_state_serialization_round_trip_exactly() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6, modifier=1),
        reason="Charge distance for Outriders",
        roll_type="charge_roll",
    )
    result = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=spec,
        values=[3, 5],
        source="rng",
    )
    state = DiceRollState.from_result(result)

    result_payload = cast(
        DiceRollResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )
    state_payload = cast(
        DiceRollStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )

    assert DiceRollResult.from_payload(result_payload).to_payload() == result.to_payload()
    assert DiceRollState.from_payload(state_payload).to_payload() == state.to_payload()


def test_event_payload_rejects_object_reprs() -> None:
    with pytest.raises(EventLogError):
        DecisionResult(
            result_id="decision-result-1",
            request_id="decision-request-1",
            decision_type="select_unit",
            actor_id=None,
            selected_option_id="unit-a",
            payload={"bad": "<object object at 0x1234abcd>"},
        )


def test_dice_expression_validation_errors_are_fail_fast() -> None:
    with pytest.raises(DiceRollSpecError):
        DiceExpression(quantity=0, sides=6)
    with pytest.raises(DiceRollSpecError):
        DiceExpression(quantity=1, sides=1)

    expression = DiceExpression(quantity=1, sides=6, modifier=-1)
    assert expression.canonical() == "D6-1"

    with pytest.raises(DiceRollSpecError):
        expression.validate_values([])
    with pytest.raises(DiceRollSpecError):
        expression.validate_values([True])
    with pytest.raises(DiceRollSpecError):
        expression.validate_values([7])


def test_dice_result_validation_errors_are_fail_fast() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Advance for validation fixture",
        roll_type="advance_roll",
    )

    with pytest.raises(DiceRollSpecError):
        DiceRollSpec(
            expression=spec.expression,
            reason="Advance for validation fixture",
            roll_type="advance_roll",
            actor_id=" ",
        )
    with pytest.raises(DiceRollSpecError):
        DiceRollResult(
            roll_id=" ",
            spec=spec,
            values=(1,),
            total=1,
            source="rng",
        )
    with pytest.raises(DiceRollSpecError):
        DiceRollResult(
            roll_id="roll-000001",
            spec=spec,
            values=(1,),
            total=1,
            source=cast(DiceRollSource, "bad-source"),
        )
    with pytest.raises(DiceRollSpecError):
        DiceRollResult(
            roll_id="roll-000001",
            spec=spec,
            values=(1,),
            total=2,
            source="rng",
        )


def test_dice_reroll_state_validation_errors_are_fail_fast() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Charge validation roll",
        roll_type="charge_roll",
    )
    result = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=spec,
        values=[1, 2],
        source="rng",
    )
    state = DiceRollState.from_result(result)

    with pytest.raises(DiceRollSpecError):
        DiceRollState(original_result=result, current_values=(1, 2), current_total=99)
    with pytest.raises(DiceRollSpecError):
        DiceRerollRecord(
            decision_id=" ",
            request_id="decision-request-1",
            selected_indices=(0,),
            replacement_result=result,
        )
    with pytest.raises(DiceRollSpecError):
        state.with_reroll(
            decision_id="decision-result-1",
            request_id="decision-request-1",
            selected_indices=(0,),
            replacement_result=DiceRollResult.from_values(
                roll_id="roll-000002",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=2, sides=6),
                    reason="Replacement validation roll",
                    roll_type="charge_roll.reroll",
                ),
                values=[3, 4],
                source="rng",
            ),
        )
    with pytest.raises(DiceRollSpecError):
        state.with_reroll(
            decision_id="decision-result-1",
            request_id="decision-request-1",
            selected_indices=(0,),
            replacement_result=DiceRollResult.from_values(
                roll_id="roll-000002",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6, modifier=1),
                    reason="Replacement modifier validation roll",
                    roll_type="charge_roll.reroll",
                ),
                values=[3],
                source="rng",
            ),
        )
    with pytest.raises(DiceRollSpecError):
        state.with_reroll(
            decision_id="decision-result-1",
            request_id="decision-request-1",
            selected_indices=(2,),
            replacement_result=DiceRollResult.from_values(
                roll_id="roll-000002",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Replacement validation roll",
                    roll_type="charge_roll.reroll",
                ),
                values=[3],
                source="rng",
            ),
        )


def test_decision_records_serialize_and_validate() -> None:
    request = DecisionRequest(
        request_id="decision-request-1",
        decision_type="select_dice_reroll",
        actor_id="unit-a",
        payload={"allowed_selections": [[0]]},
        options=(
            DecisionOption(
                option_id="reroll:0",
                label="Reroll die 0",
                payload={"selected_indices": [0]},
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id="decision-result-1",
        request=request,
        selected_option_id="reroll:0",
    )

    assert DecisionRequest.from_payload(request.to_payload()).to_payload() == request.to_payload()
    assert DecisionResult.from_payload(result.to_payload()).to_payload() == result.to_payload()
    assert request.history_token()
    assert result.history_token()

    with pytest.raises(DecisionError):
        DecisionRequest(
            request_id=" ",
            decision_type="select_dice_reroll",
            actor_id=None,
            payload={},
            options=(DecisionOption(option_id="decline", label="Decline", payload={}),),
        )
    with pytest.raises(DecisionError):
        DecisionRequest(
            request_id="decision-request-1",
            decision_type=" ",
            actor_id=None,
            payload={},
            options=(DecisionOption(option_id="decline", label="Decline", payload={}),),
        )
    with pytest.raises(DecisionError):
        DecisionResult(
            result_id="decision-result-1",
            request_id="decision-request-1",
            decision_type="select_dice_reroll",
            actor_id=" ",
            selected_option_id="decline",
            payload={},
        )


def test_reroll_decline_records_explicit_decision_without_new_roll() -> None:
    manager = DiceRollManager("seed")
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Command reroll decline fixture",
        roll_type="advance_roll",
    )
    state = manager.roll_fixed(spec, [2])
    request = manager.request_reroll(state, allowed_selections=((0,),))
    result = DecisionResult.for_request(
        result_id="decision-result-decline",
        request=request,
        selected_option_id="decline",
    )

    updated = manager.resolve_reroll(state, request=request, result=result)

    assert updated == state
    assert manager.event_log.records[-1].event_type == "dice_reroll_declined"


def test_reroll_rejects_disallowed_or_malformed_decisions() -> None:
    manager = DiceRollManager("seed")
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Command reroll malformed fixture",
        roll_type="advance_roll",
    )
    state = manager.roll_fixed(spec, [2])
    request = manager.request_reroll(state, allowed_selections=((0,),))

    with pytest.raises(DecisionError):
        manager.request_reroll(state, allowed_selections=((1,),))
    with pytest.raises(DecisionError):
        manager.resolve_reroll(
            state,
            request=request,
            result=DecisionResult(
                result_id="decision-result-wrong-type",
                request_id=request.request_id,
                decision_type="select_unit",
                actor_id=None,
                selected_option_id="reroll:0",
                payload={"selected_indices": [0]},
            ),
        )
    with pytest.raises(DecisionError):
        manager.resolve_reroll(
            state,
            request=request,
            result=DecisionResult(
                result_id="decision-result-disallowed",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=None,
                selected_option_id="reroll:1",
                payload={"selected_indices": [1]},
            ),
        )
    with pytest.raises(DecisionError):
        manager.resolve_reroll(
            state,
            request=request,
            result=DecisionResult(
                result_id="decision-result-malformed",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=None,
                selected_option_id="reroll:0",
                payload={"selected_indices": ["0"]},
            ),
        )


def test_injected_dice_must_match_requested_spec() -> None:
    original_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Original injected roll fixture",
        roll_type="advance_roll",
    )
    other_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Different injected roll fixture",
        roll_type="advance_roll",
    )
    injected = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=original_spec,
        values=[4],
        source="rng",
    )
    manager = DiceRollManager("seed", injected_results=[injected])

    with pytest.raises(DiceRollSpecError):
        manager.roll(other_spec)


def test_injected_dice_spec_mismatch_does_not_consume_replay_state() -> None:
    original_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Original injected state fixture",
        roll_type="advance_roll",
    )
    other_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Different injected state fixture",
        roll_type="advance_roll",
    )
    injected = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=original_spec,
        values=[4],
        source="rng",
    )
    manager = DiceRollManager("seed", injected_results=[injected])

    with pytest.raises(DiceRollSpecError):
        manager.roll(other_spec)

    assert manager.event_log.records == ()
    replayed = manager.roll(original_spec).original_result
    assert replayed.to_payload() == injected.to_payload()


def test_event_log_validation_errors_are_fail_fast() -> None:
    with pytest.raises(EventLogError):
        EventRecord(event_id=" ", event_type="dice_rolled", payload={})
    with pytest.raises(EventLogError):
        EventRecord(event_id="event-000001", event_type=" ", payload={})
    with pytest.raises(EventLogError):
        EventLog.from_payload(
            [
                {
                    "event_id": "event-000002",
                    "event_type": "dice_rolled",
                    "payload": {},
                }
            ]
        )
    with pytest.raises(EventLogError):
        EventLog().append("bad", {1: "not-json"})
    with pytest.raises(EventLogError):
        EventLog().append("bad", {"float": float("nan")})
    with pytest.raises(EventLogError):
        EventLog().append("bad", {"<object object at 0x1234abcd>": "bad"})


def test_event_log_tuple_payloads_normalize_to_lists() -> None:
    event_log = EventLog()
    record = event_log.append("tuple_payload", {"values": (1, 2, 3)})

    assert record.payload == {"values": [1, 2, 3]}
