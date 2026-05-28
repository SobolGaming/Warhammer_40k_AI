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
    ModifiedRollResult,
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
    UnmodifiedRollResult,
    random_characteristic_timing_from_token,
    reroll_component_selection_policy_from_token,
)
from warhammer40k_core.core.modifiers import RollModifier
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
            unmodified=UnmodifiedRollResult.from_state(state),
            modifiers=(RollModifier(modifier_id="bonus", operand=1),),
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
