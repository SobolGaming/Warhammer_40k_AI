"""Core dice contracts through production dice, reroll and result consumers."""

from dataclasses import replace

import pytest

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
    RollOffRequest,
)
from warhammer40k_core.core.modified_dice import (
    ModifiedRollResult,
    UnmodifiedRollResult,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.interpreted_dice import (
    CriticalRollThreshold,
    validate_interpreted_d6,
)


@pytest.mark.parametrize("face", range(1, 7))
def test_01_05_d6_and_d3_faces(face: int) -> None:
    manager = DiceRollManager("section01")
    spec = DiceRollSpec(DiceExpression(1, 6), "Core faces", "core_faces")
    roll = manager.roll_fixed(spec, (face,))
    assert roll.current_values == (face,)
    d3 = manager.roll_d3_fixed(reason="Core D3", roll_type="core_d3", source_d6_value=face)
    assert d3.value == (face + 1) // 2
    assert d3.source_d6_result.values == (face,)


@pytest.mark.parametrize("face", [-1, 0, 7, 99])
def test_01_05_physical_d6_rejects_nonfaces(face: int) -> None:
    with pytest.raises(DiceRollSpecError):
        DiceRollManager("section01").roll_fixed(
            DiceRollSpec(DiceExpression(1, 6), "invalid", "core"), (face,)
        )


@pytest.mark.parametrize("quantity", [1, 2, 3, 6])
@pytest.mark.parametrize("constant", [-1, 0, 3])
def test_01_05_sums_and_constants(quantity: int, constant: int) -> None:
    values = tuple(range(1, quantity + 1))
    result = DiceRollManager("sum").roll_fixed(
        DiceRollSpec(DiceExpression(quantity, 6, constant), "sum", "core"), values
    )
    assert result.current_total == sum(values) + constant


@pytest.mark.parametrize("quantity", [1, 2, 3])
def test_01_05_02_whole_roll_rerolls_all_before_modifiers_once(quantity: int) -> None:
    spec = DiceRollSpec(DiceExpression(quantity, 6), "reroll", "core")
    replacement = DiceRollResult.from_values(
        roll_id="roll-000002",
        spec=DiceRollSpec(
            DiceExpression(quantity, 6), "Reroll selected dice for reroll", "core.reroll"
        ),
        values=(6,) * quantity,
        source="rng",
    )
    manager = DiceRollManager("reroll", injected_results=(replacement,))
    original = manager.roll_fixed(spec, (1,) * quantity)
    permission = RerollPermission(
        source_id="core:01.05.02",
        timing_window="after_roll_before_modifiers",
        owning_player_id="owner",
        eligible_roll_type="core",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.request_reroll(original, permission=permission)
    all_dice = "reroll:" + ",".join(map(str, range(quantity)))
    assert tuple(o.option_id for o in request.options) == ("decline", all_dice)
    choice = DecisionResult.for_request(
        result_id="chosen", request=request, selected_option_id=all_dice
    )
    if quantity > 1:
        before = manager.event_log.to_payload()
        with pytest.raises(DecisionError):
            manager.resolve_reroll(
                original,
                request=request,
                result=replace(
                    choice, selected_option_id="reroll:0", payload={"selected_indices": [0]}
                ),
            )
        assert manager.event_log.to_payload() == before
        with pytest.raises(DecisionError, match="whole roll"):
            manager.request_reroll(original, allowed_selections=((0,),))
    updated = manager.resolve_reroll(original, request=request, result=choice)
    assert updated.rerolls[0].selected_indices == tuple(range(quantity))
    assert updated.rerolls[0].replacement_result == replacement
    assert updated.current_values == (6,) * quantity
    assert original.current_values == (1,) * quantity
    modified = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult.from_state(updated),
        modifiers=(RollModifier(modifier_id="bonus", source_id="core", operand=2),),
    )
    assert modified.final_value == 6 * quantity + 2
    with pytest.raises(DiceRollSpecError, match="die twice"):
        manager.request_reroll(updated, permission=permission)
    if quantity == 1:
        validate_interpreted_d6(state=updated, value=6)
        assert CriticalRollThreshold().matches(updated.current_total)


@pytest.mark.parametrize("assigned", [1, 5, 6, 7, 12])
def test_01_05_08_assigned_value_drives_result_predicates(assigned: int) -> None:
    state = DiceRollManager("assigned").roll_fixed(
        DiceRollSpec(DiceExpression(1, 6), "assigned", "hit_roll"), (2,)
    )

    result = state.with_result_override(
        decision_id="decision",
        request_id="request",
        source_rule_id="core:01.05.08",
        replacement_value=assigned,
    )
    validate_interpreted_d6(state=result, value=assigned)
    assert result.current_total == assigned
    assert CriticalRollThreshold().matches(result.current_total) is (assigned == 6)
    assert CriticalRollThreshold(5, True).matches(result.current_total) is (assigned >= 5)
    assert result.original_result.values == (2,)
    assert DiceRollState.from_payload(result.to_payload()) == result


@pytest.mark.parametrize("winner", ["owner", "opponent"])
def test_01_05_05_tied_rolloff_repeats_both_dice(winner: str) -> None:
    request = RollOffRequest("rolloff", "core_rolloff", ("owner", "opponent"), "resolve")
    specs = tuple(
        DiceRollManager.roll_off_spec(request=request, round_number=round_number, player_id=player)
        for round_number in (1, 2)
        for player in request.player_ids
    )
    faces = (4, 4, 6, 1) if winner == "owner" else (4, 4, 1, 6)
    injected = tuple(
        DiceRollResult.from_values(
            roll_id=f"roll-{i + 1:06d}", spec=spec, values=(face,), source="rng"
        )
        for i, (spec, face) in enumerate(zip(specs, faces, strict=True))
    )
    result = DiceRollManager("rolloff", injected_results=injected).roll_off(request)
    assert len(result.rounds) == 2
    assert result.rounds[0].is_tie
    assert result.winner_player_id == winner


@pytest.mark.parametrize("quantity", [2, 3])
def test_01_05_02_explicit_component_permission_rerolls_only_selected_die(quantity: int) -> None:
    spec = DiceRollSpec(DiceExpression(quantity, 6), "component", "core")
    replacement = DiceRollResult.from_values(
        roll_id="roll-000002",
        spec=DiceRollSpec(
            DiceExpression(1, 6), "Reroll selected dice for component", "core.reroll"
        ),
        values=(6,),
        source="rng",
    )
    manager = DiceRollManager("component", injected_results=(replacement,))
    original = manager.roll_fixed(spec, (1,) * quantity)
    permission = RerollPermission(
        source_id="constructed:explicit-component",
        timing_window="after_roll_before_modifiers",
        owning_player_id="owner",
        eligible_roll_type="core",
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )
    request = manager.request_reroll(original, permission=permission)
    assert tuple(o.option_id for o in request.options) == ("decline", "reroll:0")
    updated = manager.resolve_reroll(
        original,
        request=request,
        result=DecisionResult.for_request(
            result_id="component-choice",
            request=request,
            selected_option_id="reroll:0",
        ),
    )
    assert updated.current_values == (6,) + (1,) * (quantity - 1)
    assert updated.current_total == quantity + 5
    assert updated.rerolls[0].selected_indices == (0,)
    assert original.current_values == (1,) * quantity
    with pytest.raises(DiceRollSpecError, match="die twice"):
        manager.request_reroll(updated, permission=permission)
