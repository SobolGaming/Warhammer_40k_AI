"""Defensive group construction, opponent order and wounded-model priority."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from tests.support.section04_fixtures import combat_state
from tests.support.section05_fixtures import contract_characteristic, replace_unit
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_sequence_geometry_targets import (
    _current_allocation_group_for_order,
    _legal_model_ids_for_allocation_group_damage,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    allocation_context_for_unit,
    allocation_groups_for_context,
    apply_damage_to_model,
    build_allocation_order_request,
    legal_allocation_group_orders,
    model_by_id,
)
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (Characteristic.WOUNDS, 3),
        (Characteristic.SAVE, 2),
        (Characteristic.INVULNERABLE_SAVE, 4),
    ],
)
def test_each_defensive_characteristic_splits_native_noncharacters(
    section05_definitions: Section02Definitions, kind: Characteristic, value: int
) -> None:
    d = section05_definitions
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    state = combat_state(d, d.unit(LORD_EXULTANT), target=target)
    original = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context_for_unit(
            state=state, target_unit_instance_id=target.unit_instance_id
        ),
        include_priority_tiers=True,
    )
    assert len(original) == 1
    variant = contract_characteristic(target.own_models[0], kind, value)
    target = replace(target, own_models=(variant, *target.own_models[1:]))
    replace_unit(state, target)
    groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context_for_unit(
            state=state, target_unit_instance_id=target.unit_instance_id
        ),
        include_priority_tiers=True,
    )
    assert len(groups) == 2
    assert {g.model_ids for g in groups} == {
        (variant.model_instance_id,),
        target.own_model_ids()[1:],
    }


def test_wounded_groups_order_and_current_group_advancement(
    section05_definitions: Section02Definitions,
) -> None:
    d = section05_definitions
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    # Two wounded profiles plus one unwounded profile; native Infractors provide the bodies.
    models = target.own_models
    target = replace(
        target,
        own_models=(
            replace(models[0], wounds_remaining=1),
            replace(
                contract_characteristic(models[1], Characteristic.SAVE, 2),
                wounds_remaining=1,
            ),
            *(contract_characteristic(m, Characteristic.SAVE, 4) for m in models[2:]),
        ),
    )
    state = combat_state(d, d.unit(LORD_EXULTANT), target=target)
    context = allocation_context_for_unit(
        state=state, target_unit_instance_id=target.unit_instance_id
    )
    groups = allocation_groups_for_context(
        state=state, allocation_context=context, include_priority_tiers=True
    )
    orders = legal_allocation_group_orders(groups)
    assert len(orders) == 2
    assert all([g.wounded for g in order] == [True, True, False] for order in orders)
    assert orders[0][:2] == tuple(reversed(orders[1][:2]))
    request = build_allocation_order_request(
        request_id="s05:order",
        defender_player_id="opponent",
        attack_context={"attack_context_id": "s05:attack"},
        allocation_context=context,
        allocation_groups=groups,
    )
    assert request.actor_id == "opponent"
    assert len(request.options) == 2
    order = orders[1]
    assert _current_allocation_group_for_order(state=state, allocation_groups=order) == order[0]
    for group in order:
        assert _current_allocation_group_for_order(state=state, allocation_groups=order) == group
        for mid in group.model_ids:
            outcome = apply_damage_to_model(
                state=state,
                target_unit_instance_id=target.unit_instance_id,
                model_instance_id=mid,
                damage=20,
                damage_kind=DamageKind.NORMAL,
            )
            assert outcome.destroyed
            assert outcome.final_wounds_remaining == 0
            assert outcome.excess_damage_lost == 20 - outcome.starting_wounds_remaining
    assert _current_allocation_group_for_order(state=state, allocation_groups=order) is None


def test_wounded_model_precedes_unwounded_and_dead_models_are_not_allocatable(
    section05_definitions: Section02Definitions,
) -> None:
    d = section05_definitions
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    state = combat_state(d, d.unit(LORD_EXULTANT), target=target)
    first, second = target.own_model_ids()[:2]
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=target.unit_instance_id,
        model_instance_id=second,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    assert damage.wounds_lost == 1
    context = allocation_context_for_unit(
        state=state, target_unit_instance_id=target.unit_instance_id
    )
    group = allocation_groups_for_context(
        state=state, allocation_context=context, include_priority_tiers=True
    )[0]
    assert _legal_model_ids_for_allocation_group_damage(state=state, allocation_group=group) == (
        second,
    )
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=target.unit_instance_id,
        model_instance_id=second,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    assert not model_by_id(state=state, model_instance_id=second).is_alive
    updated = allocation_context_for_unit(
        state=state, target_unit_instance_id=target.unit_instance_id
    )
    assert second not in updated.alive_model_ids
    assert second not in {
        m
        for g in allocation_groups_for_context(state=state, allocation_context=updated)
        for m in g.model_ids
    }
    assert first in _legal_model_ids_for_allocation_group_damage(
        state=state, allocation_group=group
    )
    with pytest.raises(GameLifecycleError, match="destroyed model"):
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=target.unit_instance_id,
            model_instance_id=second,
            damage=1,
            damage_kind=DamageKind.NORMAL,
        )
