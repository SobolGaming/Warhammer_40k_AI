from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    D3RollResult,
    D3RollResultPayload,
    DiceExpression,
    DiceRollComponent,
    DiceRollInstance,
    DiceRollResult,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
    RerollComponentSelectionPolicy,
    RerollDecisionRequest,
    RerollPermission,
    RerollRecord,
    RerollSelection,
    RollOffRequest,
    RollOffResult,
    RollOffResultPayload,
    random_characteristic_timing_from_token,
    reroll_component_selection_policy_from_token,
)
from warhammer40k_core.core.modified_dice import ModifiedRollResult, UnmodifiedRollResult
from warhammer40k_core.core.modifiers import RollModifier, RollModifierOperation
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager as ExportedDiceRollManager
from warhammer40k_core.engine.event_log import JsonValue


def _spec(
    *,
    quantity: int,
    reason: str,
    roll_type: str,
    actor_id: str | None = None,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=quantity, sides=6),
        reason=reason,
        roll_type=roll_type,
        actor_id=actor_id,
    )


def test_d3_records_source_d6_and_rounded_up_result() -> None:
    manager = DiceRollManager("seed")

    result = manager.roll_d3_fixed(
        reason="Random damage for thunder hammer",
        roll_type="random_damage",
        actor_id="unit-captain",
        source_d6_value=5,
    )
    payload = cast(
        D3RollResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )

    assert result.source_d6_result.values == (5,)
    assert result.value == 3
    assert result.source_d6_result.spec.expression == DiceExpression(quantity=1, sides=6)
    assert payload["source_d6_result"]["values"] == [5]
    assert payload["value"] == 3
    assert manager.event_log.records[-1].event_type == "d3_roll_resolved"


def test_roll_off_ties_repeat_until_there_is_a_winner() -> None:
    request = RollOffRequest(
        request_id="roll-off-attacker-defender",
        purpose="determine_attacker_defender",
        player_ids=("player-a", "player-b"),
        resolving_decision_id="setup-determine-attacker",
    )
    injected = (
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=DiceRollManager.roll_off_spec(request, round_number=1, player_id="player-a"),
            values=[4],
            source="rng",
        ),
        DiceRollResult.from_values(
            roll_id="roll-000002",
            spec=DiceRollManager.roll_off_spec(request, round_number=1, player_id="player-b"),
            values=[4],
            source="rng",
        ),
        DiceRollResult.from_values(
            roll_id="roll-000003",
            spec=DiceRollManager.roll_off_spec(request, round_number=2, player_id="player-a"),
            values=[2],
            source="rng",
        ),
        DiceRollResult.from_values(
            roll_id="roll-000004",
            spec=DiceRollManager.roll_off_spec(request, round_number=2, player_id="player-b"),
            values=[6],
            source="rng",
        ),
    )
    manager = DiceRollManager("different-seed", injected_results=injected)

    result = manager.roll_off(request)
    payload = cast(
        RollOffResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )

    assert result.winner_player_id == "player-b"
    assert tuple(round_result.is_tie for round_result in result.rounds) == (True, False)
    assert [roll.value for roll in result.rounds[0].player_rolls] == [4, 4]
    assert payload["request"]["resolving_decision_id"] == "setup-determine-attacker"
    assert manager.event_log.records[-1].event_type == "roll_off_resolved"


def test_roll_offs_reject_rerolls_and_modifier_attempts() -> None:
    request = RollOffRequest(
        request_id="roll-off-sequencing",
        purpose="sequencing_conflict",
        player_ids=("player-a", "player-b"),
        resolving_decision_id="sequencing-start-round",
    )
    manager = DiceRollManager("seed")
    result = manager.roll_off(request)
    first_roll_state = DiceRollState.from_result(result.rounds[0].player_rolls[0].roll_result)

    with pytest.raises(DecisionError):
        manager.request_reroll(first_roll_state, allowed_selections=((0,),))

    unmodified = UnmodifiedRollResult.from_state(first_roll_state)
    with pytest.raises(DiceRollSpecError):
        ModifiedRollResult.from_unmodified(
            unmodified,
            modifiers=(
                RollModifier(
                    modifier_id="illegal-roll-off-bonus",
                    source_id="unsupported-rule",
                    operand=1,
                ),
            ),
        )


def test_single_d6_reroll_records_original_replacement_and_final_unmodified_value() -> None:
    replacement_spec = _spec(
        quantity=1,
        reason="Reroll selected dice for Advance roll for Tactical Squad",
        roll_type="advance_roll.reroll",
        actor_id="unit-tactical",
    )
    replacement = DiceRollResult.from_values(
        roll_id="roll-000002",
        spec=replacement_spec,
        values=[6],
        source="rng",
    )
    manager = DiceRollManager("seed", injected_results=(replacement,))
    state = manager.roll_fixed(
        _spec(
            quantity=1,
            reason="Advance roll for Tactical Squad",
            roll_type="advance_roll",
            actor_id="unit-tactical",
        ),
        [1],
    )
    permission = RerollPermission(
        source_id="stratagem-command-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="advance_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.request_reroll(state, permission=permission)
    decision = DecisionResult.for_request(
        result_id="decision-result-reroll-advance",
        request=request,
        selected_option_id="reroll:0",
    )

    updated = manager.resolve_reroll(state, request=request, result=decision)
    unmodified = UnmodifiedRollResult.from_state(updated)

    assert updated.original_result.values == (1,)
    assert updated.rerolls[0].replacement_result.values == (6,)
    assert updated.current_values == (6,)
    assert unmodified.value == 6
    request_payload = cast(dict[str, JsonValue], request.payload)
    permission_payload = cast(dict[str, JsonValue], request_payload["permission"])
    assert permission_payload["source_id"] == "stratagem-command-reroll"


def test_whole_roll_permission_rerolls_every_die_for_multi_dice_rolls_by_default() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=2,
            reason="Charge distance for Assault Squad",
            roll_type="charge_roll",
            actor_id="unit-assault",
        ),
        [1, 2],
    )
    permission = RerollPermission(
        source_id="stratagem-command-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.request_reroll(state, permission=permission)

    assert tuple(option.option_id for option in request.options) == ("decline", "reroll:0,1")
    with pytest.raises(DiceRollSpecError):
        permission.validate_selection(state, RerollSelection(indices=(0,)))


def test_partial_multi_dice_reroll_requires_explicit_component_selection_permission() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=2,
            reason="Hit roll pool for Devastator Squad",
            roll_type="hit_roll",
            actor_id="unit-devastators",
        ),
        [1, 4],
    )
    permission = RerollPermission(
        source_id="captain-reroll-aura",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="hit_roll",
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )

    request = manager.request_reroll(state, permission=permission)

    assert tuple(option.option_id for option in request.options) == ("decline", "reroll:0")
    assert RerollPermission.from_payload(permission.to_payload()) == permission


def test_raw_allowed_selections_cannot_partially_reroll_multi_dice_roll() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=2,
            reason="Charge distance raw reroll fixture",
            roll_type="charge_roll",
            actor_id="unit-assault",
        ),
        [1, 4],
    )

    with pytest.raises(DecisionError, match="whole roll"):
        manager.request_reroll(state, allowed_selections=((0,),))


def test_raw_allowed_selections_cannot_offer_already_rerolled_die() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=1,
            reason="Advance roll raw reroll fixture",
            roll_type="advance_roll",
            actor_id="unit-tactical",
        ),
        [1],
    ).with_reroll(
        decision_id="decision-result-first-reroll",
        request_id="decision-request-first-reroll",
        selected_indices=(0,),
        replacement_result=DiceRollResult.from_values(
            roll_id="roll-raw-reroll-replacement",
            spec=_spec(
                quantity=1,
                reason="Reroll selected dice for Advance roll raw reroll fixture",
                roll_type="advance_roll.reroll",
                actor_id="unit-tactical",
            ),
            values=[4],
            source="fixed",
        ),
    )

    with pytest.raises(DecisionError, match="already-rerolled"):
        manager.request_reroll(state, allowed_selections=((0,),))


def test_reroll_request_rejects_stale_current_values() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=1,
            reason="Advance roll stale request fixture",
            roll_type="advance_roll",
            actor_id="unit-tactical",
        ),
        [1],
    )
    request = manager.request_reroll(state, allowed_selections=((0,),))
    decision = DecisionResult.for_request(
        result_id="decision-result-stale-reroll",
        request=request,
        selected_option_id="reroll:0",
    )
    changed_state = state.with_reroll(
        decision_id="decision-result-prior-reroll",
        request_id="decision-request-prior-reroll",
        selected_indices=(0,),
        replacement_result=DiceRollResult.from_values(
            roll_id="roll-stale-request-replacement",
            spec=_spec(
                quantity=1,
                reason="Reroll selected dice for Advance roll stale request fixture",
                roll_type="advance_roll.reroll",
                actor_id="unit-tactical",
            ),
            values=[5],
            source="fixed",
        ),
    )

    with pytest.raises(DecisionError, match="current_values"):
        manager.resolve_reroll(changed_state, request=request, result=decision)


def test_reroll_request_rejects_roll_type_drift() -> None:
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=1,
            reason="Advance roll roll type drift fixture",
            roll_type="advance_roll",
            actor_id="unit-tactical",
        ),
        [1],
    )
    request = manager.request_reroll(state, allowed_selections=((0,),))
    payload = dict(cast(dict[str, JsonValue], request.payload))
    payload["roll_type"] = "wound_roll"
    drifted_request = DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=payload,
        options=request.options,
    )
    decision = DecisionResult.for_request(
        result_id="decision-result-roll-type-drift",
        request=drifted_request,
        selected_option_id="reroll:0",
    )

    with pytest.raises(DecisionError, match="roll_type"):
        manager.resolve_reroll(state, request=drifted_request, result=decision)


def test_no_die_component_can_be_rerolled_twice() -> None:
    spec = _spec(
        quantity=1,
        reason="Wound roll for plasma pistol",
        roll_type="wound_roll",
        actor_id="unit-sergeant",
    )
    first_replacement_spec = _spec(
        quantity=1,
        reason="Reroll selected dice for Wound roll for plasma pistol",
        roll_type="wound_roll.reroll",
        actor_id="unit-sergeant",
    )
    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=spec,
            values=[1],
            source="fixed",
        )
    ).with_reroll(
        decision_id="decision-result-first",
        request_id="decision-request-first",
        selected_indices=(0,),
        replacement_result=DiceRollResult.from_values(
            roll_id="roll-000002",
            spec=first_replacement_spec,
            values=[2],
            source="fixed",
        ),
    )

    with pytest.raises(DiceRollSpecError):
        state.with_reroll(
            decision_id="decision-result-second",
            request_id="decision-request-second",
            selected_indices=(0,),
            replacement_result=DiceRollResult.from_values(
                roll_id="roll-000003",
                spec=first_replacement_spec,
                values=[6],
                source="fixed",
            ),
        )


def test_modifiers_apply_after_rerolls_and_preserve_unmodified_value() -> None:
    spec = _spec(
        quantity=1,
        reason="Battle-shock roll for Intercessors",
        roll_type="battle_shock_roll",
        actor_id="unit-intercessors",
    )
    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=spec,
            values=[1],
            source="fixed",
        )
    ).with_reroll(
        decision_id="decision-result-reroll",
        request_id="decision-request-reroll",
        selected_indices=(0,),
        replacement_result=DiceRollResult.from_values(
            roll_id="roll-000002",
            spec=_spec(
                quantity=1,
                reason="Reroll selected dice for Battle-shock roll for Intercessors",
                roll_type="battle_shock_roll.reroll",
                actor_id="unit-intercessors",
            ),
            values=[5],
            source="fixed",
        ),
    )
    unmodified = UnmodifiedRollResult.from_state(state)
    modified = ModifiedRollResult.from_unmodified(
        unmodified,
        modifiers=(
            RollModifier(
                modifier_id="shadow-of-chaos-penalty",
                source_id="army-rule-shadow-of-chaos",
                operand=1,
            ),
        ),
    )

    assert unmodified.value == 5
    assert modified.final_value == 6
    assert modified.applied_modifier_ids == ("shadow-of-chaos-penalty",)


@pytest.mark.parametrize(
    ("roll_type", "raw", "modifier", "expected"),
    [
        ("battle_shock_roll", 2, -10, 1),
        ("charge_roll", 12, 5, 12),
        ("advance_roll", 6, 5, 11),
        ("hit_roll", 4, 10, 5),
        ("wound_roll", 1, -10, 1),
    ],
)
def test_order27_modified_dice_limits(
    roll_type: str,
    raw: int,
    modifier: int,
    expected: int,
) -> None:
    result = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult("roll-limits", roll_type, raw, (raw,)),
        modifiers=(RollModifier("effect", modifier),),
    )
    assert result.unmodified.value == raw
    assert result.final_value == expected
    assert ModifiedRollResult.from_payload(result.to_payload()) == result


def test_random_move_characteristic_is_rolled_once_for_the_whole_unit() -> None:
    manager = DiceRollManager("seed")

    first = manager.roll_random_characteristic_fixed(
        characteristic=Characteristic.MOVEMENT,
        timing=RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE,
        scope_id="unit-possessed",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Random Move for Possessed",
        values=[3],
    )
    second = manager.roll_random_characteristic_fixed(
        characteristic=Characteristic.MOVEMENT,
        timing=RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE,
        scope_id="unit-possessed",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Random Move for Possessed",
        values=[6],
    )
    payload = cast(
        RandomCharacteristicRollPayload,
        json.loads(json.dumps(first.to_payload(), sort_keys=True)),
    )

    assert second == first
    assert first.value == 3
    assert payload["timing"] == "unit_when_selected_to_move"


def test_random_attacks_and_damage_characteristics_roll_at_required_use_timing() -> None:
    manager = DiceRollManager("seed")

    first_attack = manager.roll_random_characteristic_fixed(
        characteristic=Characteristic.ATTACKS,
        timing=RandomCharacteristicTiming.PER_WEAPON,
        scope_id="weapon-mutant-claws",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Random attacks for mutant claws",
        values=[1],
    )
    second_attack = manager.roll_random_characteristic_fixed(
        characteristic=Characteristic.ATTACKS,
        timing=RandomCharacteristicTiming.PER_WEAPON,
        scope_id="weapon-mutant-claws",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Random attacks for mutant claws",
        values=[4],
    )
    damage = manager.roll_random_characteristic_fixed(
        characteristic=Characteristic.DAMAGE,
        timing=RandomCharacteristicTiming.PER_ATTACK,
        scope_id="weapon-lascannon:attack-1",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Random damage for lascannon attack 1",
        values=[5],
    )

    assert first_attack.value == 1
    assert second_attack.value == 4
    assert (
        first_attack.roll_state.original_result.roll_id
        != second_attack.roll_state.original_result.roll_id
    )
    assert damage.value == 5


def test_replay_load_rejects_reroll_record_drift() -> None:
    spec = _spec(
        quantity=1,
        reason="Save roll for Terminator",
        roll_type="save_roll",
        actor_id="unit-terminators",
    )
    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=spec,
            values=[1],
            source="fixed",
        )
    ).with_reroll(
        decision_id="decision-result-reroll-save",
        request_id="decision-request-reroll-save",
        selected_indices=(0,),
        replacement_result=DiceRollResult.from_values(
            roll_id="roll-000002",
            spec=_spec(
                quantity=1,
                reason="Reroll selected dice for Save roll for Terminator",
                roll_type="save_roll.reroll",
                actor_id="unit-terminators",
            ),
            values=[6],
            source="fixed",
        ),
    )
    payload = state.to_payload()
    payload["current_values"] = [5]
    payload["current_total"] = 5

    with pytest.raises(DiceRollSpecError):
        DiceRollState.from_payload(payload)


def test_same_seed_and_same_reroll_decision_reproduce_identical_final_result() -> None:
    spec = _spec(
        quantity=2,
        reason="Charge distance for replay determinism",
        roll_type="charge_roll",
        actor_id="unit-assault",
    )
    permission = RerollPermission(
        source_id="stratagem-command-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )

    left = DiceRollManager("seed")
    right = DiceRollManager("seed")
    left_state = left.roll(spec)
    right_state = right.roll(spec)
    left_request = left.request_reroll(left_state, permission=permission)
    right_request = right.request_reroll(right_state, permission=permission)
    left_decision = DecisionResult.for_request(
        result_id="decision-result-reroll-charge",
        request=left_request,
        selected_option_id="reroll:0,1",
    )
    right_decision = DecisionResult.for_request(
        result_id="decision-result-reroll-charge",
        request=right_request,
        selected_option_id="reroll:0,1",
    )

    left_updated = left.resolve_reroll(left_state, request=left_request, result=left_decision)
    right_updated = right.resolve_reroll(right_state, request=right_request, result=right_decision)

    assert left_updated.to_payload() == right_updated.to_payload()


def test_phase10j_record_payloads_round_trip() -> None:
    assert ExportedDiceRollManager is DiceRollManager
    manager = DiceRollManager("seed")
    state = manager.roll_fixed(
        _spec(
            quantity=2,
            reason="Round-trip charge roll",
            roll_type="charge_roll",
            actor_id="unit-round-trip",
        ),
        [2, 3],
    )
    instance = DiceRollInstance.from_result(state.original_result)
    state_instance = DiceRollInstance.from_state(state)
    d3 = manager.roll_d3_fixed(
        reason="Round-trip D3 damage",
        roll_type="random_damage",
        actor_id="unit-round-trip",
        source_d6_value=2,
    )
    roll_off = manager.roll_off(
        RollOffRequest(
            request_id="roll-off-round-trip",
            purpose="mission_choice",
            player_ids=("player-a", "player-b"),
            resolving_decision_id="mission-choice",
        )
    )
    permission = RerollPermission(
        source_id="round-trip-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id="player-a",
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    reroll_request = RerollDecisionRequest.from_state(state, permission)
    replacement = DiceRollResult.from_values(
        roll_id="roll-999999",
        spec=_spec(
            quantity=2,
            reason="Reroll selected dice for Round-trip charge roll",
            roll_type="charge_roll.reroll",
            actor_id="unit-round-trip",
        ),
        values=[4, 5],
        source="fixed",
    )
    updated = state.with_reroll(
        decision_id="decision-result-round-trip",
        request_id="decision-request-round-trip",
        selected_indices=(0, 1),
        replacement_result=replacement,
    )
    reroll_record = RerollRecord(
        decision_id="decision-result-round-trip",
        request_id="decision-request-round-trip",
        permission=permission,
        selection=RerollSelection(indices=(0, 1)),
        original_values=state.current_values,
        replacement_result=replacement,
        final_values=updated.current_values,
        final_unmodified_value=sum(updated.current_values),
    )
    unmodified = UnmodifiedRollResult.from_state(updated)
    modified = ModifiedRollResult.from_unmodified(
        unmodified,
        modifiers=(RollModifier(modifier_id="round-trip-bonus", operand=1),),
    )
    random_characteristic = manager.roll_random_characteristic(
        characteristic=Characteristic.DAMAGE,
        timing=RandomCharacteristicTiming.PER_USE,
        scope_id="weapon-round-trip",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Round-trip random damage",
    )

    assert DiceRollInstance.from_payload(instance.to_payload()) == instance
    assert DiceRollInstance.from_payload(state_instance.to_payload()) == state_instance
    assert D3RollResult.from_payload(d3.to_payload()) == d3
    assert RollOffResult.from_payload(roll_off.to_payload()) == roll_off
    assert RerollSelection.from_payload({"indices": [0, 1]}) == RerollSelection(indices=(0, 1))
    assert RerollDecisionRequest.from_payload(reroll_request.to_payload()) == reroll_request
    assert RerollRecord.from_payload(reroll_record.to_payload()) == reroll_record
    assert UnmodifiedRollResult.from_payload(unmodified.to_payload()) == unmodified
    assert ModifiedRollResult.from_payload(modified.to_payload()) == modified
    assert (
        RandomCharacteristicRoll.from_payload(random_characteristic.to_payload())
        == random_characteristic
    )
    assert random_characteristic_timing_from_token("per_use") is RandomCharacteristicTiming.PER_USE
    assert (
        reroll_component_selection_policy_from_token("whole_roll")
        is RerollComponentSelectionPolicy.WHOLE_ROLL
    )


def test_phase10j_records_fail_fast_on_invalid_shapes() -> None:
    spec = _spec(
        quantity=1,
        reason="Validation fixture roll",
        roll_type="validation_roll",
        actor_id="unit-validation",
    )
    result = DiceRollResult.from_values(
        roll_id="roll-000001",
        spec=spec,
        values=[3],
        source="fixed",
    )
    state = DiceRollState.from_result(result)

    invalid_cases = (
        lambda: DiceRollComponent(
            component_id="component",
            index=-1,
            sides=6,
            value=1,
        ),
        lambda: DiceRollInstance(
            roll_id="roll-000001",
            spec=spec,
            components=(),
            total=3,
            source="fixed",
        ),
        lambda: D3RollResult(source_d6_result=result, value=1),
        lambda: RollOffRequest(
            request_id="roll-off-invalid",
            purpose="mission",
            player_ids=("player-a",),
            resolving_decision_id="mission",
        ),
        lambda: RerollSelection(indices=()),
        lambda: RerollPermission(
            source_id="bad-permission",
            timing_window="after_roll_before_modifiers",
            owning_player_id="player-a",
            eligible_roll_type="validation_roll",
            component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        ),
        lambda: RerollDecisionRequest(
            roll_id="roll-000001",
            roll_type="validation_roll",
            permission=RerollPermission(
                source_id="bad-request",
                timing_window="after_roll_before_modifiers",
                owning_player_id="player-a",
                eligible_roll_type="validation_roll",
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
            allowed_selections=(),
            current_values=(3,),
        ),
        lambda: RerollRecord(
            decision_id="decision-result-invalid",
            request_id="decision-request-invalid",
            permission=None,
            selection=RerollSelection(indices=(0,)),
            original_values=(3,),
            replacement_result=result,
            final_values=(4,),
            final_unmodified_value=3,
        ),
        lambda: UnmodifiedRollResult(
            roll_id="roll-000001",
            roll_type="validation_roll",
            value=True,
            component_values=(3,),
        ),
        lambda: ModifiedRollResult(
            intrinsic_offset=0,
            unmodified=UnmodifiedRollResult.from_state(state),
            modifiers=(RollModifier(modifier_id="bonus", operand=1),),
            unbounded_value=4,
            modified_value=4,
            final_value=3,
            applied_modifier_ids=("bonus",),
        ),
        lambda: manager_roll_random_move_for_non_move(),
    )

    for invalid_case in invalid_cases:
        with pytest.raises(DiceRollSpecError):
            invalid_case()


def manager_roll_random_move_for_non_move() -> None:
    DiceRollManager("seed").roll_random_characteristic_fixed(
        characteristic=Characteristic.ATTACKS,
        timing=RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE,
        scope_id="unit-invalid",
        expression=DiceExpression(quantity=1, sides=6),
        reason="Invalid random move timing",
        values=[1],
    )


def test_roll_algebra_uses_exact_shared_order_and_zero_roll_replacement_is_not_terminal() -> None:
    modifiers = (
        RollModifier("subtract", 4, operation=RollModifierOperation.SUBTRACT),
        RollModifier("divide", 2, operation=RollModifierOperation.DIVIDE),
        RollModifier("add", 2),
        RollModifier("multiply", 3, operation=RollModifierOperation.MULTIPLY),
        RollModifier("replace", 5, operation=RollModifierOperation.SET),
    )
    result = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult("ordered-roll", "advance_roll", 6, (6,)),
        modifiers=modifiers,
    )
    assert result.final_value == 5
    assert result.applied_modifier_ids == ("replace", "multiply", "add", "divide", "subtract")
    assert ModifiedRollResult.from_payload(result.to_payload()) == result
    zero = ModifiedRollResult.from_unmodified(
        result.unmodified,
        modifiers=(
            RollModifier("zero", 0, operation=RollModifierOperation.SET),
            RollModifier("bonus", 4),
        ),
    )
    assert zero.final_value == 4


def test_roll_off_rejects_an_intrinsic_offset() -> None:
    with pytest.raises(DiceRollSpecError, match="Roll-off"):
        ModifiedRollResult.from_unmodified(
            UnmodifiedRollResult("roll-off", "roll_off", 3, (3,)),
            intrinsic_offset=1,
        )


@pytest.mark.parametrize("assigned", [1, 6, 7, 12])
def test_order84_assigned_result_preserves_physical_die_and_replay(assigned: int) -> None:
    original = DiceRollResult.from_values(
        roll_id="order84-roll",
        spec=_spec(quantity=2, reason="Core assigned die result", roll_type="charge_roll"),
        values=(2, 5),
        source="fixed",
    )
    state = DiceRollState.from_result(original).with_result_override(
        decision_id="order84-result",
        request_id="order84-request",
        source_rule_id="gw-11e-core-dice-results:treated-as-set-to",
        replacement_value=assigned,
        component_index=1,
    )
    assert state.original_result == original
    assert state.current_values == (2, assigned)
    assert state.current_total == 2 + assigned
    assert DiceRollState.from_payload(state.to_payload()) == state
    instance = DiceRollInstance.from_state(state)
    assert instance.components[1].component_id == "order84-roll:component-1"
    assert instance.components[1].value == 5
    assert instance.components[1].effective_value == assigned
    assert instance.total == state.current_total
    assert DiceRollInstance.from_payload(instance.to_payload()) == instance
    modified = ModifiedRollResult.from_unmodified(UnmodifiedRollResult.from_state(state))
    assert modified.unmodified.value == 2 + assigned
    assert modified.final_value == min(12, 2 + assigned)


def test_order84_raw_faces_and_unauthenticated_effective_values_remain_bounded() -> None:
    from dataclasses import replace

    original = DiceRollResult.from_values(
        roll_id="order84-raw",
        spec=_spec(quantity=1, reason="Core physical die bounds", roll_type="hit_roll"),
        values=(3,),
        source="fixed",
    )
    with pytest.raises(DiceRollSpecError):
        replace(original, values=(7,), total=7)
    with pytest.raises(DiceRollSpecError):
        replace(DiceRollState.from_result(original), current_values=(7,), current_total=7)


@pytest.mark.parametrize("kind", ["highest", "lowest"])
@pytest.mark.parametrize("secret", [False, True])
def test_order84_tied_physical_die_uses_active_player_facade_and_exact_replay(
    kind: str,
    secret: bool,
) -> None:
    from tests.dice_result_semantics_helpers import extremum_session

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.dice_extremum import DiceExtremum, DiceExtremumSelection
    from warhammer40k_core.engine.dice_extremum import request_dice_extremum
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_dice_results_2026_09 as dice_sources,
    )

    extremum = DiceExtremum(kind)
    session, roll, request = extremum_session(extremum=extremum, secret=secret)
    assert request.actor_id == "player-a"
    assert roll.original_result.spec.actor_id == ("player-a" if secret else "player-b")
    assert [option.option_id for option in request.options] == [
        f"{roll.original_result.roll_id}:component-0",
        f"{roll.original_result.roll_id}:component-1",
    ]
    checkpoint = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert session.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        view_text = json.dumps(session.view(viewer_player_id=viewer))
        delta_text = json.dumps(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        if secret and viewer == "player-b":
            assert "core_dice_reference" not in view_text + delta_text
            assert request.options[0].option_id not in view_text + delta_text
        else:
            assert request.options[0].option_id in view_text
    before_rolls = len(
        [
            event
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "dice_rolled"
        ]
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[1].option_id,
        result_id="order84-selected-second-die",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    # Read back the accepted physical identity, even though both choices have the same value.
    chosen = request_dice_extremum(
        state=state,
        decisions=session.lifecycle.decision_controller,
        roll_state=roll,
        extremum=extremum,
        referring_source_rule_id=dice_sources.HIGHEST_LOWEST_SOURCE_ID,
        reference_id="order84:reference",
    )
    assert isinstance(chosen, DiceExtremumSelection)
    assert chosen.component_index == 1
    assert (
        len(
            [
                event
                for event in session.lifecycle.decision_controller.event_log.records
                if event.event_type == "dice_rolled"
            ]
        )
        == before_rolls
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order84")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_order84_whole_roll_assignment_does_not_invent_physical_faces() -> None:
    original = DiceRollResult.from_values(
        roll_id="order84-total",
        spec=_spec(quantity=2, reason="Core assigned roll result", roll_type="battle_shock_roll"),
        values=(2, 3),
        source="fixed",
    )
    state = DiceRollState.from_result(original).with_result_override(
        decision_id="total-result",
        request_id="total-request",
        source_rule_id="gw-11e-core-dice-results:treated-as-set-to",
        replacement_value=14,
        component_index=None,
    )
    assert state.current_values == (2, 3)
    assert state.current_total == 14
    assert UnmodifiedRollResult.from_state(state).value == 14
    assert DiceRollInstance.from_state(state).total == 14
    assert DiceRollState.from_payload(state.to_payload()) == state
    unmodified = UnmodifiedRollResult.from_state(state)
    assert UnmodifiedRollResult.from_payload(unmodified.to_payload()) == unmodified


@pytest.mark.parametrize("case", ["actor", "option", "payload", "request", "roll"])
def test_order84_tied_die_rejects_invalid_submissions_atomically(case: str) -> None:
    from dataclasses import replace

    from tests.dice_result_semantics_helpers import extremum_session

    from warhammer40k_core.core.dice_extremum import DiceExtremum
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, roll, request = extremum_session(extremum=DiceExtremum.HIGHEST)
    result = DecisionResult.for_request(
        result_id="invalid-extremum",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    if case == "actor":
        result = replace(result, actor_id="player-b")
    elif case == "option":
        result = replace(result, selected_option_id=f"{roll.original_result.roll_id}:component-2")
    elif case == "payload":
        result = replace(result, payload={"component_index": True})
    elif case == "request":
        result = replace(result, request_id="obsolete-request")
    else:
        updated = roll.with_result_override(
            decision_id="intervening-result",
            request_id="intervening-request",
            source_rule_id="gw-11e-core-dice-results:treated-as-set-to",
            replacement_value=7,
            component_index=2,
        )
        session.lifecycle.decision_controller.event_log.append(
            "dice_result_overridden",
            {"updated_roll_state": updated.to_payload()},
        )
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("assigned", [1, 6, 7])
def test_order84_wound_save_and_hazard_consume_assigned_results(assigned: int) -> None:
    from warhammer40k_core.engine.attack_sequence import WoundRoll
    from warhammer40k_core.engine.hazard import failed_hazard_roll_indices
    from warhammer40k_core.engine.saves import SaveKind, SaveOption, resolve_saving_throw

    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="order84-consumer",
            spec=_spec(quantity=1, reason="Interpreted D6 consumer", roll_type="wound_roll"),
            values=(2,),
            source="fixed",
        )
    ).with_result_override(
        decision_id="consumer-result",
        request_id="consumer-request",
        source_rule_id="gw-11e-core-dice-results:treated-as-set-to",
        replacement_value=assigned,
    )
    wound = WoundRoll(
        strength=4,
        toughness=4,
        target_number=4,
        roll_state=state,
        unmodified_roll=assigned,
        modifier=-1,
        capped_modifier=-1,
        final_roll=max(1, assigned - 1),
        successful=assigned >= 6,
        critical=assigned == 6,
    )
    assert wound.unmodified_roll == assigned
    save = resolve_saving_throw(
        roll_state=state,
        option=SaveOption(SaveKind.ARMOUR, 7, 3, -4),
    )
    assert save.successful is (assigned == 7)
    assert failed_hazard_roll_indices(state) == ((0,) if assigned == 1 else ())


@pytest.mark.parametrize("inclusive", [False, True])
def test_order84_wound_threshold_predicate_distinguishes_six_from_six_plus(inclusive: bool) -> None:
    from warhammer40k_core.engine.interpreted_dice import CriticalRollThreshold

    rule = CriticalRollThreshold(6, inclusive)
    assert rule.matches(6)
    assert rule.matches(7) is inclusive
    assert not rule.matches(1)


def test_order84_component_identity_survives_reroll_before_assignment() -> None:
    original = DiceRollResult.from_values(
        roll_id="order84-rerolled",
        spec=_spec(quantity=2, reason="rerolled components", roll_type="test"),
        values=(2, 3),
        source="fixed",
    )
    replacement = DiceRollResult.from_values(
        roll_id="order84-replacement",
        spec=_spec(quantity=1, reason="replacement", roll_type="test"),
        values=(5,),
        source="fixed",
    )
    state = (
        DiceRollState.from_result(original)
        .with_reroll(
            decision_id="reroll-result",
            request_id="reroll-request",
            selected_indices=(1,),
            replacement_result=replacement,
        )
        .with_result_override(
            decision_id="assign-result",
            request_id="assign-request",
            source_rule_id="core:test",
            replacement_value=7,
            component_index=1,
        )
    )
    instance = DiceRollInstance.from_state(state)
    assert instance.components[1].component_id == "order84-rerolled:component-1"
    assert instance.components[1].value == 5
    assert instance.components[1].effective_value == 7
    assert DiceRollState.from_payload(state.to_payload()) == state
    with pytest.raises(DiceRollSpecError):
        state.with_reroll(
            decision_id="late-reroll",
            request_id="late-request",
            selected_indices=(0,),
            replacement_result=replacement,
        )


@pytest.mark.parametrize("kind", ["highest", "lowest"])
def test_order84_reference_retry_is_idempotent_and_unique_extrema_need_no_choice(kind: str) -> None:
    from tests.dice_result_semantics_helpers import extremum_session

    from warhammer40k_core.core.dice_extremum import DiceExtremum, DiceExtremumSelection
    from warhammer40k_core.engine.dice_extremum import request_dice_extremum
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_dice_results_2026_09 as sources,
    )

    session, roll, pending = extremum_session(extremum=DiceExtremum(kind))
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    before = session.lifecycle.to_payload()
    assert (
        request_dice_extremum(
            state=state,
            decisions=decisions,
            roll_state=roll,
            extremum=DiceExtremum(kind),
            referring_source_rule_id=sources.HIGHEST_LOWEST_SOURCE_ID,
            reference_id="order84:reference",
        )
        == pending
    )
    assert session.lifecycle.to_payload() == before
    unique = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_fixed(
        _spec(quantity=3, reason="Unique extremum", roll_type="test"), (2, 5, 3)
    )
    before = session.lifecycle.to_payload()
    selected = request_dice_extremum(
        state=state,
        decisions=decisions,
        roll_state=unique,
        extremum=DiceExtremum(kind),
        referring_source_rule_id=sources.HIGHEST_LOWEST_SOURCE_ID,
        reference_id="unique-reference",
    )
    assert isinstance(selected, DiceExtremumSelection)
    assert selected.component_index == (1 if kind == "highest" else 0)
    assert selected.value == (5 if kind == "highest" else 2)
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("target", ["reference", "selection", "visibility"])
def test_order84_restore_rejects_dice_reference_history_drift(target: str) -> None:
    from typing import cast

    from tests.dice_result_semantics_helpers import extremum_session

    from warhammer40k_core.core.dice_extremum import DiceExtremum
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, _roll, request = extremum_session(extremum=DiceExtremum.HIGHEST, secret=True)
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[1].option_id,
        result_id="order84-history-selection",
    )
    payload = session.lifecycle.to_payload()
    events = payload["decisions"]["event_log"]
    event = next(
        row
        for row in events
        if row["event_type"]
        == ("dice_extremum_selected" if target == "selection" else "dice_extremum_referenced")
    )
    data = cast(dict[str, JsonValue], event["payload"])
    if target == "reference":
        data["actor_id"] = "player-b"
    elif target == "selection":
        cast(dict[str, JsonValue], data["selection"])["component_index"] = 0
    else:
        data["secret"] = False
    with pytest.raises(GameLifecycleError, match="Highest/lowest"):
        GameLifecycle.from_payload(payload)


def test_order84_assigned_roll_cannot_reopen_reroll_or_mutate_manager() -> None:
    manager = DiceRollManager("order84-reroll-preflight")
    physical = manager.roll_fixed(
        _spec(quantity=1, reason="Original", roll_type="test", actor_id="player-a"), (1,)
    )
    request = manager.build_reroll_request(
        physical, request_id="before-assignment", allowed_selections=((0,),)
    )
    result = DecisionResult.for_request(
        request=request, result_id="stale-reroll", selected_option_id=request.options[-1].option_id
    )
    assigned = physical.with_result_override(
        decision_id="assigned",
        request_id="assignment",
        source_rule_id="core:test",
        replacement_value=1,
    )
    before = (manager.rng.to_payload(), manager.event_log.to_payload())
    with pytest.raises(DecisionError, match="assigned"):
        manager.request_reroll(assigned, allowed_selections=((0,),))
    with pytest.raises(DecisionError, match="assigned"):
        manager.resolve_reroll(assigned, request=request, result=result)
    assert (manager.rng.to_payload(), manager.event_log.to_payload()) == before


def test_order84_assignment_does_not_reopen_twin_linked_or_conditional_source_rerolls() -> None:
    from dataclasses import replace

    from tests.generic_modifier_helpers import generic_effect
    from tests.phase13b_shooting_declaration_helpers import (
        _attack_pool_for_test,
        _first_weapon_profile,
        _shooting_lifecycle,
        _state,
    )

    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.attack_sequence import WoundRoll
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
        _request_source_backed_hit_reroll_if_available,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _reroll_wound_for_twin_linked_if_needed,
    )
    from warhammer40k_core.engine.phase import BattlePhase

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, defender = units["intercessor-1"], units["enemy"]
    profile = replace(
        _first_weapon_profile(lifecycle, attacker), keywords=(WeaponKeyword.TWIN_LINKED,)
    )
    pool = _attack_pool_for_test(
        attacker=attacker, defender=defender, weapon_profile=profile, attacks=1
    )
    manager = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    physical = manager.roll_fixed(
        _spec(
            quantity=1,
            reason="Assignment before retry",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
        ),
        (6,),
    )
    assigned = physical.with_result_override(
        decision_id="assigned",
        request_id="assignment",
        source_rule_id="core:test",
        replacement_value=1,
    )
    wound_physical = manager.roll_fixed(
        _spec(quantity=1, reason="Assigned Wound", roll_type="attack_sequence.wound"), (6,)
    )
    assigned_wound = wound_physical.with_result_override(
        decision_id="assigned-wound",
        request_id="assignment-wound",
        source_rule_id="core:test",
        replacement_value=1,
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="order84:conditional-reroll",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="reroll_permission",
            parameters={
                "roll_type": "hit",
                "attack_role": "attacker",
                "reroll_unmodified_value": 1,
            },
        )
    )
    before = (manager.rng.to_payload(), lifecycle.to_payload())
    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=lifecycle.decision_controller,
            roll_state=assigned,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            attack_context_id="order84:attack",
            source_phase=BattlePhase.SHOOTING,
            weapon_profile_id=profile.profile_id,
        )
        is None
    )
    wound = WoundRoll(
        strength=4,
        toughness=4,
        target_number=4,
        roll_state=assigned_wound,
        unmodified_roll=1,
        modifier=0,
        capped_modifier=0,
        final_roll=1,
        successful=False,
        critical=False,
    )
    assert (
        _reroll_wound_for_twin_linked_if_needed(
            manager=manager,
            decisions=lifecycle.decision_controller,
            pool=pool,
            initial_wound_roll=wound,
            toughness=4,
            attacker_player_id="player-a",
            attack_context_id="order84:attack",
        )
        is wound
    )
    assert (manager.rng.to_payload(), lifecycle.to_payload()) == before


@pytest.mark.parametrize("field", ["player_id", "battle_round", "turn_player_id", "battle_phase"])
def test_order84_correlated_tie_context_forgery_cannot_change_historical_authority(
    field: str,
) -> None:
    from tests.dice_result_semantics_helpers import extremum_session

    from warhammer40k_core.core.dice_extremum import DiceExtremum
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, _roll, request = extremum_session(extremum=DiceExtremum.HIGHEST)
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[1].option_id,
        result_id="review-choice",
    )
    payload = session.lifecycle.to_payload()
    replacements: dict[str, JsonValue] = {
        "player_id": "player-b",
        "battle_round": 99,
        "turn_player_id": "player-b",
        "battle_phase": "made-up-phase",
    }
    replacement = replacements[field]

    def tamper(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("visibility_source") == "dice_extremum" and field in value:
                value[field] = replacement
            if (
                field == "player_id"
                and value.get("request_id") == request.request_id
                and "actor_id" in value
            ):
                value["actor_id"] = replacement
            for child in value.values():
                tamper(child)
        elif isinstance(value, list):
            for child in value:
                tamper(child)

    raw = cast(JsonValue, json.loads(json.dumps(payload)))
    assert isinstance(raw, dict)
    tamper(raw["decisions"])
    with pytest.raises(GameLifecycleError, match="Highest/lowest historical active-player"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


@pytest.mark.parametrize("kind", ["shooting", "charge"])
def test_order84_historical_chooser_tracks_real_out_of_turn_owner_and_completion(kind: str) -> None:
    from tests.charge_reroll_helpers import heroic_session
    from tests.dice_result_semantics_helpers import assert_active_player_history, open_phase
    from tests.fire_overwatch_helpers import (
        ENEMIES,
        choose_enemy,
        choose_shooter,
        finish_overwatch,
        overwatch_session,
        pending_overwatch,
    )
    from tests.heroic_intervention_helpers import add_heroic_modifier, use_heroic

    if kind == "shooting":
        session = overwatch_session(attacks=2)
        open_phase(session.lifecycle)
        status = choose_shooter(session, pending_overwatch(session))
        assert_active_player_history(session.lifecycle, expected_player="player-a")
        request = status.decision_request
        assert request is not None
        status = choose_enemy(session, request, ENEMIES[0])
        finish_overwatch(session, status)
    else:
        session, unit_id = heroic_session(natural=False)
        open_phase(session.lifecycle)
        add_heroic_modifier(session, unit_id, delta=20)
        declaration = use_heroic(session, unit_id)
        assert_active_player_history(session.lifecycle, expected_player="player-a")
        status = session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="order84-declare"
        )
        request = status.decision_request
        assert request is not None
        assert request.decision_type == "select_charge_targets"
        session.submit_option(
            request_id=request.request_id,
            option_id="decline_charge_targets",
            result_id="order84-decline",
        )
    assert_active_player_history(session.lifecycle, expected_player="player-b")


def test_order84_tie_cannot_borrow_a_future_decision_as_its_chooser_scope() -> None:
    from tests.dice_result_semantics_helpers import forged_future_shooting_scope_payload

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    with pytest.raises(GameLifecycleError, match="accepted source selection"):
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, forged_future_shooting_scope_payload())
        )


@pytest.mark.parametrize("reuse", [False, True])
def test_order84_chooser_scope_requires_an_unused_shooting_permission(reuse: bool) -> None:
    from tests.dice_result_semantics_helpers import forged_shooting_source_lifecycle

    from warhammer40k_core.engine.active_player_boundary_history import (
        active_player_authority_before_event,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle = forged_shooting_source_lifecycle(reuse=reuse)
    assert lifecycle.state is not None
    message = "boundary was reused" if reuse else "does not authorize out-of-phase shooting"
    with pytest.raises(GameLifecycleError, match=message):
        active_player_authority_before_event(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
            event_index=len(lifecycle.decision_controller.event_log.records),
        )
