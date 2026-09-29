"""Direct evidence for attack dice and wounded allocation-group precedence."""

from dataclasses import replace

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    _shooting_lifecycle,
)

from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_wound
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.damage_allocation import (
    AllocationGroup,
    AllocationGroupRole,
    AttackAllocationRuleContext,
    build_allocation_order_request,
    legal_allocation_group_orders,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.interpreted_dice import CriticalRollThreshold


def test_hit_and_wound_rolls_each_request_one_six_sided_die() -> None:
    for factory in (attack_sequence_hit_roll_spec, attack_sequence_wound_roll_spec):
        spec = factory(
            weapon_profile_id="order97:weapon",
            attack_context_id="order97:attack",
            attacker_player_id="player-a",
        )
        assert spec.expression.quantity == 1
        assert spec.expression.sides == 6


@pytest.mark.parametrize(
    ("roll", "modifier", "success", "critical"),
    [(1, 1, False, False), (6, -1, True, True), (3, 1, True, False), (4, -1, False, False)],
)
def test_real_wound_roll_respects_unmodified_extremes_and_modified_threshold(
    roll: int, modifier: int, success: bool, critical: bool
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    weapon = _first_weapon_profile(lifecycle, units["intercessor-1"])
    pool = _attack_pool_for_test(
        attacker=units["intercessor-1"], defender=units["enemy"], weapon_profile=weapon, attacks=1
    )
    spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon.profile_id,
        attack_context_id="order97:wound",
        attacker_player_id="player-a",
    )
    manager = DiceRollManager(
        "order97:wound",
        injected_results=(_fixed_roll_result(roll_id="order97:die", spec=spec, value=roll),),
    )
    result = _roll_wound(
        manager=manager,
        pool=pool,
        toughness=weapon.strength_for_interaction(),
        attacker_player_id="player-a",
        attack_context_id="order97:wound",
        critical_threshold=CriticalRollThreshold(value=6, inclusive=True),
        wound_modifier=modifier,
    )
    assert result.successful is success
    assert result.critical is critical
    assert result.target_number == 4


def test_all_wounded_noncharacter_groups_precede_unwounded_groups() -> None:
    first = AllocationGroup(
        group_id="order97:first",
        target_unit_instance_id="order97:target",
        model_ids=("order97:a",),
        role=AllocationGroupRole.BODYGUARD,
        wounds=2,
        save=3,
        invulnerable_save=None,
        wounded_model_ids=("order97:a",),
    )
    second = replace(
        first,
        group_id="order97:second",
        model_ids=("order97:b",),
        save=4,
        wounded_model_ids=("order97:b",),
    )
    unwounded = replace(
        first,
        group_id="order97:unwounded",
        model_ids=("order97:c",),
        wounds=3,
        wounded_model_ids=(),
    )
    orders = legal_allocation_group_orders((unwounded, second, first))
    assert len(orders) == 2
    assert {order[:2] for order in orders} == {(first, second), (second, first)}
    assert all(order[-1] == unwounded for order in orders)

    request = build_allocation_order_request(
        request_id="order97:order",
        defender_player_id="player-b",
        attack_context={"attack_context_id": "order97:attack"},
        allocation_context=AttackAllocationRuleContext(
            target_unit_instance_id="order97:target",
            alive_model_ids=("order97:a", "order97:b", "order97:c"),
        ),
        allocation_groups=(unwounded, second, first),
    )
    assert request.actor_id == "player-b"
    assert len(request.options) == 2


@pytest.mark.parametrize("characteristic", ["wounds", "save", "invulnerable_save"])
def test_noncharacter_allocation_groups_split_each_defensive_characteristic(
    characteristic: str,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _replace_unit_instance_in_state, _state

    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.engine.damage_allocation import allocation_groups_for_context

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    model = defender.own_models[0]
    kind = Characteristic(characteristic)
    replacement = CharacteristicValue.from_raw(kind, 3 if kind is Characteristic.WOUNDS else 4)
    model = replace(
        model,
        characteristics=(
            *(value for value in model.characteristics if value.characteristic is not kind),
            replacement,
        ),
    )
    if kind is Characteristic.WOUNDS:
        model = replace(model, starting_wounds=3, wounds_remaining=3)
    defender = replace(defender, own_models=(model, *defender.own_models[1:]))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    groups = allocation_groups_for_context(
        state=state,
        allocation_context=AttackAllocationRuleContext(
            target_unit_instance_id=defender.unit_instance_id,
            alive_model_ids=tuple(m.model_instance_id for m in defender.own_models),
        ),
    )
    assert len(groups) == 2
    assert any(group.model_ids == (model.model_instance_id,) for group in groups)


def test_zero_damage_still_reaches_resolve_damage_without_losing_wounds() -> None:
    from tests.order58_failed_save_damage_timing_helpers import (
        defender_wounds,
        order58_registry,
        order58_shooting_lifecycle,
        resolve_order58_attack,
    )

    lifecycle, units = order58_shooting_lifecycle()
    defender = units["enemy"]
    before = defender.own_models[0].current_wounds
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=units["intercessor-1"],
        defender=defender,
        sequence_id="order97:damage-zero",
        registry=order58_registry(source_unit_instance_id=defender.unit_instance_id),
    )
    damage = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "damage"
    ]
    assert len(damage) == 1
    assert defender_wounds(lifecycle, defender) == before


def test_retained_destruction_resolves_deferred_deadly_demise_at_cleanup() -> None:
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.retained_attack_helpers import pending_retained_attack

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, model_id = pending_retained_attack(deadly_demise=True)
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order97:retain-demise",
        option_id="order-30-fight-on-death",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    for _ in range(60):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Retained source did not finish cleanup.")
    events = session.lifecycle.decision_controller.event_log.records
    demise_indices = [
        i
        for i, event in enumerate(events)
        if event.event_type == "destruction_reaction_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == model_id
        and event.payload.get("selected_reaction_kind") == "deadly_demise"
    ]
    removal_indices = [
        i
        for i, event in enumerate(events)
        if event.event_type == "model_destroyed"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == model_id
    ]
    assert len(demise_indices) == 1
    assert len(removal_indices) == 1
    assert demise_indices[0] < removal_indices[0]
