from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core import dice as dice_module
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    D3RollResult,
    DiceExpression,
    DiceRerollRecord,
    DiceRollComponent,
    DiceRollInstance,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSource,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    DiceRollStatePayload,
    ModifiedRollResult,
    RandomCharacteristicRoll,
    RandomCharacteristicTiming,
    RerollComponentSelectionPolicy,
    RerollDecisionRequest,
    RerollPermission,
    RerollRecord,
    RerollSelection,
    RollOffPlayerRoll,
    RollOffRequest,
    RollOffResult,
    RollOffRound,
    UnmodifiedRollResult,
)
from warhammer40k_core.engine.decision import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DiceRollManager,
)
from warhammer40k_core.engine.event_log import EventLog, EventLogError, EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_resources import (
    UnitResourceLedger,
    UnitResourceStatus,
    UnitStartingResourceAllocation,
    validate_starting_resource_allocations,
)


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


def _fixed_result(
    *,
    roll_id: str = "roll-contract",
    values: tuple[int, ...] = (2, 4),
    sides: int = 6,
    modifier: int = 0,
    roll_type: str = "test_roll",
    actor_id: str | None = "player-a",
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=DiceRollSpec(
            expression=DiceExpression(quantity=len(values), sides=sides, modifier=modifier),
            reason="Dice validation contract",
            roll_type=roll_type,
            actor_id=actor_id,
        ),
        values=values,
        source="fixed",
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


def test_one_d6_result_override_round_trips_without_consuming_rng() -> None:
    manager = DiceRollManager("aspect-token-seed")
    state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Aspect Shrine Token Hit roll",
            roll_type="attack_sequence.hit",
            actor_id="player-aeldari",
        )
    )
    event_count = len(manager.event_log.records)

    overridden = state.with_result_override(
        decision_id="decision-result-aspect-token",
        request_id="decision-request-aspect-token",
        source_rule_id="source:aeldari:aspect-shrine-token",
        replacement_value=6,
    )

    assert overridden.current_values == (6,)
    assert overridden.current_total == 6
    assert overridden.result_override is not None
    assert overridden.result_override.previous_values == state.current_values
    assert DiceRollState.from_payload(overridden.to_payload()) == overridden
    assert len(manager.event_log.records) == event_count


def test_result_override_forbids_later_rerolls_and_second_overrides() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Aspect Shrine Token Wound roll",
        roll_type="attack_sequence.wound",
        actor_id="player-aeldari",
    )
    original = DiceRollResult.from_values(
        roll_id="roll-aspect-token",
        spec=spec,
        values=[2],
        source="rng",
    )
    state = DiceRollState.from_result(original).with_result_override(
        decision_id="decision-result-aspect-token",
        request_id="decision-request-aspect-token",
        source_rule_id="source:aeldari:aspect-shrine-token",
        replacement_value=6,
    )
    replacement = DiceRollResult.from_values(
        roll_id="roll-aspect-token-reroll",
        spec=spec,
        values=[4],
        source="rng",
    )

    with pytest.raises(DiceRollSpecError, match="cannot be rerolled"):
        state.with_reroll(
            decision_id="decision-result-reroll",
            request_id="decision-request-reroll",
            selected_indices=(0,),
            replacement_result=replacement,
        )
    with pytest.raises(DiceRollSpecError, match="at most once"):
        state.with_result_override(
            decision_id="decision-result-second",
            request_id="decision-request-second",
            source_rule_id="source:aeldari:aspect-shrine-token",
            replacement_value=6,
        )


def test_dice_components_and_roll_instances_reject_invalid_structural_state() -> None:
    component_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"index": cast(int, True)}, "index must be an integer"),
        ({"index": -1}, "index must not be negative"),
        ({"sides": cast(int, True)}, "sides must be an integer"),
        ({"sides": 1}, "sides must be at least 2"),
        ({"value": cast(int, True)}, "value must be an integer"),
        ({"value": 7}, "outside die bounds"),
        ({"rerolled": cast(bool, 1)}, "rerolled must be a bool"),
    )
    for changes, message in component_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            DiceRollComponent(
                component_id="roll:component-0",
                index=changes.get("index", 0),
                sides=changes.get("sides", 6),
                value=changes.get("value", 3),
                rerolled=changes.get("rerolled", False),
            )

    result = _fixed_result(values=(2, 4))
    normalized_result = DiceRollResult(
        roll_id=result.roll_id,
        spec=result.spec,
        values=cast(tuple[int, ...], [2, 4]),
        total=6,
        source="fixed",
    )
    assert normalized_result.values == (2, 4)
    instance = DiceRollInstance.from_result(result)
    normalized_instance = DiceRollInstance(
        roll_id=instance.roll_id,
        spec=instance.spec,
        components=cast(tuple[DiceRollComponent, ...], list(instance.components)),
        total=instance.total,
        source=instance.source,
    )
    assert normalized_instance.components == instance.components

    invalid_instance_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"spec": cast(DiceRollSpec, object())}, "spec must be"),
        ({"source": cast(DiceRollSource, "unknown")}, "source is invalid"),
        ({"components": ()}, "component count"),
        ({"components": cast(tuple[DiceRollComponent, ...], (object(), object()))}, "must contain"),
        (
            {
                "components": (
                    replace(instance.components[0], index=1),
                    instance.components[1],
                )
            },
            "indexes must be sequential",
        ),
        (
            {
                "components": (
                    replace(instance.components[0], sides=8),
                    instance.components[1],
                )
            },
            "sides must match",
        ),
        ({"total": 99}, "total does not match"),
    )
    for changes, message in invalid_instance_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(instance, **changes)


def test_d3_results_reject_non_d6_sources_and_drifted_values() -> None:
    source = _fixed_result(values=(5,))
    valid = D3RollResult.from_source_d6_result(source)
    assert valid.value == 3

    invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"source_d6_result": cast(DiceRollResult, object())}, "must be a DiceRollResult"),
        ({"source_d6_result": _fixed_result(values=(5,), modifier=1)}, "unmodified D6"),
        ({"value": cast(int, True)}, "value must be an integer"),
        ({"value": 2}, "rounded up"),
    )
    for changes, message in invalid_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(valid, **changes)


def test_roll_off_value_objects_reject_identity_sequence_and_winner_drift() -> None:
    request = RollOffRequest(
        request_id="roll-off-request",
        purpose="Determine first turn",
        player_ids=("player-a", "player-b"),
        resolving_decision_id="decision:first-turn",
    )

    def player_roll(player_id: str, value: int, suffix: str) -> RollOffPlayerRoll:
        result = _fixed_result(
            roll_id=f"roll:{suffix}:{player_id}",
            values=(value,),
            roll_type="roll_off",
            actor_id=player_id,
        )
        return RollOffPlayerRoll(player_id=player_id, roll_result=result, value=value)

    tied_round = RollOffRound(
        round_number=1,
        player_rolls=(player_roll("player-a", 3, "tie"), player_roll("player-b", 3, "tie")),
    )
    winning_round = RollOffRound(
        round_number=1,
        player_rolls=(player_roll("player-a", 5, "win"), player_roll("player-b", 2, "win")),
    )
    valid_result = RollOffResult(
        request=request,
        rounds=(winning_round,),
        winner_player_id="player-a",
    )
    assert RollOffResult.from_payload(valid_result.to_payload()) == valid_result

    player_roll_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"roll_result": cast(DiceRollResult, object())}, "must be a DiceRollResult"),
        ({"roll_result": _fixed_result(values=(1, 2), roll_type="roll_off")}, "unmodified D6"),
        ({"roll_result": _fixed_result(values=(3,), roll_type="test_roll")}, "roll_type"),
        (
            {"roll_result": _fixed_result(values=(3,), roll_type="roll_off", actor_id="other")},
            "actor_id",
        ),
        ({"value": 4}, "value must match"),
    )
    valid_player_roll = player_roll("player-a", 3, "valid")
    for changes, message in player_roll_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(valid_player_roll, **changes)

    round_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"round_number": cast(int, True)}, "round_number must be an integer"),
        ({"round_number": 0}, "at least 1"),
        ({"player_rolls": (valid_player_roll,)}, "at least two"),
        (
            {"player_rolls": cast(tuple[RollOffPlayerRoll, ...], (object(), object()))},
            "must contain RollOffPlayerRoll",
        ),
        ({"player_rolls": (valid_player_roll, valid_player_roll)}, "unique by player"),
    )
    for changes, message in round_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(tied_round, **changes)
    drifted_tie_payload = tied_round.to_payload()
    drifted_tie_payload["is_tie"] = False
    with pytest.raises(DiceRollSpecError, match="tie status drifted"):
        RollOffRound.from_payload(drifted_tie_payload)

    second_winning_round = replace(winning_round, round_number=2)
    result_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"request": cast(RollOffRequest, object())}, "request must be"),
        ({"rounds": ()}, "must not be empty"),
        ({"rounds": cast(tuple[RollOffRound, ...], (object(),))}, "must contain RollOffRound"),
        ({"rounds": (second_winning_round,)}, "numbers must be sequential"),
        (
            {
                "rounds": (
                    RollOffRound(
                        round_number=1,
                        player_rolls=(
                            player_roll("player-a", 5, "wrong-players"),
                            player_roll("player-c", 2, "wrong-players"),
                        ),
                    ),
                )
            },
            "player IDs must match",
        ),
        ({"rounds": (winning_round, second_winning_round)}, "cannot continue"),
        ({"rounds": (tied_round,)}, "final round must have a winner"),
        ({"winner_player_id": "player-b"}, "does not match"),
    )
    for changes, message in result_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(valid_result, **changes)


def test_reroll_permissions_and_state_transitions_fail_closed() -> None:
    original = _fixed_result(values=(2, 4), roll_type="attack.hit")
    state = DiceRollState.from_result(original)
    whole_roll = RerollPermission(
        source_id="source:reroll",
        timing_window="attack.hit",
        owning_player_id="player-a",
        eligible_roll_type="attack.hit",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    component_permission = RerollPermission(
        source_id="source:component-reroll",
        timing_window="attack.hit",
        owning_player_id="player-a",
        eligible_roll_type="attack.hit",
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,), (1,)),
    )
    assert component_permission.legal_selections_for_state(state) == ((0,), (1,))
    assert component_permission.validate_selection(
        state, RerollSelection(indices=(0,))
    ).indices == (0,)

    with pytest.raises(DiceRollSpecError, match="must not supply component selections"):
        replace(whole_roll, allowed_component_selections=((0,),))
    with pytest.raises(DiceRollSpecError, match="require explicit selections"):
        RerollPermission(
            source_id="source:missing-selections",
            timing_window="attack.hit",
            owning_player_id="player-a",
            eligible_roll_type="attack.hit",
            component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        )
    with pytest.raises(DiceRollSpecError, match="state must be a DiceRollState"):
        whole_roll.legal_selections_for_state(cast(DiceRollState, object()))
    with pytest.raises(DiceRollSpecError, match="does not match roll"):
        replace(whole_roll, eligible_roll_type="attack.wound").legal_selections_for_state(state)
    with pytest.raises(DiceRollSpecError, match="outside the roll"):
        replace(
            component_permission,
            allowed_component_selections=((2,),),
        ).legal_selections_for_state(state)
    with pytest.raises(DiceRollSpecError, match="selection must be a RerollSelection"):
        component_permission.validate_selection(state, cast(RerollSelection, object()))
    with pytest.raises(DiceRollSpecError, match="not legal"):
        component_permission.validate_selection(state, RerollSelection(indices=(0, 1)))

    rerolled = state.with_reroll(
        decision_id="decision:reroll",
        request_id="request:reroll",
        selected_indices=(0,),
        replacement_result=_fixed_result(
            roll_id="roll:replacement",
            values=(5,),
            roll_type="attack.hit",
        ),
    )
    with pytest.raises(DiceRollSpecError, match="cannot reroll a die twice"):
        whole_roll.legal_selections_for_state(rerolled)
    with pytest.raises(DiceRollSpecError, match="die size does not match"):
        state.with_reroll(
            decision_id="decision:wrong-sides",
            request_id="request:wrong-sides",
            selected_indices=(0,),
            replacement_result=_fixed_result(
                roll_id="roll:wrong-sides",
                values=(5,),
                sides=8,
                roll_type="attack.hit",
            ),
        )
    with pytest.raises(DiceRollSpecError, match="outside the current dice"):
        state.with_reroll(
            decision_id="decision:outside",
            request_id="request:outside",
            selected_indices=(2,),
            replacement_result=_fixed_result(
                roll_id="roll:outside",
                values=(5,),
                roll_type="attack.hit",
            ),
        )

    request = RerollDecisionRequest.from_state(state, component_permission)
    assert RerollDecisionRequest.from_payload(request.to_payload()) == request
    with pytest.raises(DiceRollSpecError, match="permission must be"):
        replace(request, permission=cast(RerollPermission, object()))
    with pytest.raises(DiceRollSpecError, match="request_id must not be empty"):
        DiceRerollRecord(
            decision_id="decision:reroll",
            request_id=" ",
            selected_indices=(0,),
            replacement_result=_fixed_result(values=(4,), roll_type="attack.hit"),
        )
    with pytest.raises(DiceRollSpecError, match="indices must not be empty"):
        RerollSelection(indices=())
    with pytest.raises(DiceRollSpecError, match="original_result must be"):
        replace(state, original_result=cast(DiceRollResult, object()))
    with pytest.raises(DiceRollSpecError, match="must contain DiceRerollRecord"):
        replace(state, rerolls=cast(tuple[DiceRerollRecord, ...], (object(),)))
    with pytest.raises(DiceRollSpecError, match="result_override must be typed"):
        replace(state, result_override=cast(Any, object()))


def test_roll_result_views_and_random_characteristics_validate_derived_values() -> None:
    original = _fixed_result(values=(4,), roll_type="characteristic")
    state = DiceRollState.from_result(original)
    selection = RerollSelection(indices=(0,))
    replacement = _fixed_result(
        roll_id="roll:view-replacement",
        values=(5,),
        roll_type="characteristic",
    )
    record = RerollRecord(
        decision_id="decision:view",
        request_id="request:view",
        permission=None,
        selection=selection,
        original_values=(4,),
        replacement_result=replacement,
        final_values=(5,),
        final_unmodified_value=5,
    )
    assert RerollRecord.from_payload(record.to_payload()) == record

    record_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"permission": cast(RerollPermission, object())}, "permission must be"),
        ({"selection": cast(RerollSelection, object())}, "selection must be"),
        ({"replacement_result": cast(DiceRollResult, object())}, "replacement_result must be"),
        ({"final_unmodified_value": cast(int, True)}, "must be an integer"),
        ({"final_unmodified_value": 4}, "must match final value sum"),
    )
    for changes, message in record_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(record, **changes)

    unmodified = UnmodifiedRollResult.from_state(state)
    with pytest.raises(DiceRollSpecError, match="state must be a DiceRollState"):
        UnmodifiedRollResult.from_state(cast(DiceRollState, object()))
    with pytest.raises(DiceRollSpecError, match="value must be an integer"):
        replace(unmodified, value=cast(int, True))
    modified = ModifiedRollResult.from_unmodified(unmodified)
    with pytest.raises(DiceRollSpecError, match="unmodified must be"):
        replace(modified, unmodified=cast(UnmodifiedRollResult, object()))
    with pytest.raises(DiceRollSpecError, match="must contain RollModifier"):
        replace(modified, modifiers=cast(Any, (object(),)))
    with pytest.raises(DiceRollSpecError, match="final_value does not match"):
        replace(modified, final_value=99)
    with pytest.raises(DiceRollSpecError, match="applied_modifier_ids do not match"):
        replace(modified, applied_modifier_ids=("wrong",))

    random_roll = RandomCharacteristicRoll(
        characteristic=Characteristic.MOVEMENT,
        timing=RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE,
        scope_id="unit:test",
        roll_state=state,
        value=state.current_total,
    )
    assert RandomCharacteristicRoll.from_payload(random_roll.to_payload()) == random_roll
    random_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"roll_state": cast(DiceRollState, object())}, "roll_state must be"),
        ({"value": cast(int, True)}, "value must be an integer"),
        ({"value": 3}, "value must match"),
        ({"characteristic": Characteristic.TOUGHNESS}, "only valid for Movement"),
    )
    for changes, message in random_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            replace(random_roll, **changes)


def test_reroll_token_and_selection_boundaries_reject_ambiguous_inputs() -> None:
    assert (
        dice_module.reroll_component_selection_policy_from_token(
            RerollComponentSelectionPolicy.WHOLE_ROLL
        )
        is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert (
        dice_module.random_characteristic_timing_from_token(
            RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
        )
        is RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
    )
    for converter in (
        dice_module.reroll_component_selection_policy_from_token,
        dice_module.random_characteristic_timing_from_token,
    ):
        with pytest.raises(DiceRollSpecError, match="must be a string"):
            converter(1)
        with pytest.raises(DiceRollSpecError, match="Unsupported"):
            converter("not-supported")

    for indices, message in (
        ((cast(int, "0"),), "must be integers"),
        ((-1,), "must not be negative"),
        ((0, 0), "unique and ascending"),
    ):
        with pytest.raises(DiceRollSpecError, match=message):
            dice_module._validate_selected_indices(indices)
    selection_cases = (
        (cast(Any, [(0,)]), "must be a tuple"),
        ((cast(tuple[int, ...], [0]),), "must contain tuple selections"),
        (((),), "must not contain empty selections"),
        (((0,), (0,)), "must not contain duplicate selections"),
        ((), "must not be empty"),
    )
    for selections, message in selection_cases:
        with pytest.raises(DiceRollSpecError, match=message):
            dice_module._validate_selection_tuple(selections, field_name="selections")


def test_unit_resource_ledger_tracks_deterministic_initialization_and_spends() -> None:
    initialized = UnitResourceLedger.empty_for_unit(
        player_id="player-aeldari",
        unit_instance_id="army-aeldari:dire-avengers",
    ).initialize(
        resource_kind="aeldari:aspect-shrine-token",
        amount=2,
        source_rule_id="source:aeldari:aspect-shrine-token",
    )
    after_first, first = initialized.spend(
        battle_round=1,
        resource_kind="aeldari:aspect-shrine-token",
        amount=1,
        source_rule_id="source:aeldari:aspect-shrine-token",
        decision_request_id="decision-request-first-token",
        decision_result_id="decision-result-first-token",
    )
    exhausted, second = after_first.spend(
        battle_round=2,
        resource_kind="aeldari:aspect-shrine-token",
        amount=1,
        source_rule_id="source:aeldari:aspect-shrine-token",
        decision_request_id="decision-request-second-token",
        decision_result_id="decision-result-second-token",
    )
    unchanged, rejected = exhausted.spend(
        battle_round=3,
        resource_kind="aeldari:aspect-shrine-token",
        amount=1,
        source_rule_id="source:aeldari:aspect-shrine-token",
        decision_request_id="decision-request-overspend",
        decision_result_id="decision-result-overspend",
    )

    assert first.status is UnitResourceStatus.APPLIED
    assert second.status is UnitResourceStatus.APPLIED
    assert rejected.status is UnitResourceStatus.INSUFFICIENT
    assert unchanged is exhausted
    assert exhausted.starting_total("aeldari:aspect-shrine-token") == 2
    assert exhausted.total("aeldari:aspect-shrine-token") == 0
    assert [transaction.transaction_id for transaction in exhausted.transactions] == [
        "player-aeldari:army-aeldari:dire-avengers:aeldari:aspect-shrine-token:transaction-000001",
        "player-aeldari:army-aeldari:dire-avengers:aeldari:aspect-shrine-token:transaction-000002",
        "player-aeldari:army-aeldari:dire-avengers:aeldari:aspect-shrine-token:transaction-000003",
    ]
    assert UnitResourceLedger.from_payload(exhausted.to_payload()) == exhausted


def test_starting_unit_resources_reject_non_positive_and_duplicate_entries() -> None:
    with pytest.raises(GameLifecycleError, match="positive"):
        UnitStartingResourceAllocation(
            resource_kind="aeldari:aspect-shrine-token",
            amount=0,
        )
    allocation = UnitStartingResourceAllocation(
        resource_kind="aeldari:aspect-shrine-token",
        amount=1,
    )
    with pytest.raises(GameLifecycleError, match="duplicate"):
        validate_starting_resource_allocations(
            "starting_resources",
            (allocation, allocation),
        )
