"""Actual opponent model choice and mandatory saves despite impossible first armour."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from tests.support.section05_fixtures import contract_characteristic
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.attack_sequence_group_selection import (
    apply_damage_allocation_model_decision,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_result import DecisionResult


@pytest.mark.parametrize("impossible_first", [False, True])
def test_opponent_choice_and_faq09_later_better_save(
    section05_definitions: Section02Definitions, impossible_first: bool
) -> None:
    d = section05_definitions
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    if impossible_first:
        target = replace(
            target,
            own_models=(
                replace(
                    contract_characteristic(target.own_models[0], Characteristic.SAVE, 6),
                    wounds_remaining=1,
                ),
                *(
                    contract_characteristic(m, Characteristic.SAVE, 2)
                    for m in target.own_models[1:]
                ),
            ),
        )
    state, target, sequence = native_sequence(d, target=target, attacks=2)
    if impossible_first:
        pool = sequence.attack_pools[0]
        # Explicit AP boundary: first model needs 8+, later models need 4+.
        sequence = replace(
            sequence,
            attack_pools=(
                replace(
                    pool,
                    weapon_profile=replace(
                        pool.weapon_profile,
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -2
                        ),
                    ),
                ),
            ),
        )
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6, 6), (6, 6), (1, 6))
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    request = status.decision_request
    assert request.actor_id == "opponent"
    assert request.decision_type == "select_damage_allocation_model"
    assert len(request.options) == len(target.own_models) - (1 if impossible_first else 0)
    result = DecisionResult.for_request(
        result_id="s05:allocate",
        request=request,
        selected_option_id=request.options[-1].option_id,
    )
    decisions.submit_result(result)
    remaining, _, status = apply_damage_allocation_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=remaining,
        result=result,
        already_allocated_model_ids=(),
    )
    assert status is None
    steps = payloads(decisions, "attack_sequence_step")
    assert len([s for s in steps if s["step"] == "save"]) == 2
    assert model_by_id(
        state=state, model_instance_id=target.own_model_ids()[-1]
    ).current_wounds == (2 if impossible_first else 1)
    if impossible_first:
        assert not model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).is_alive
        rolls = payloads(decisions, "dice_rolled")
        assert len(rolls) == 6
        assert len(payloads(decisions, "model_destroyed")) == 1
