"""Highest present Toughness and attached bodyguard precedence on native physical models."""

from dataclasses import replace

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section05_fixtures import contract_characteristic
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence_geometry_targets import (
    _target_unit_toughness,
)
from warhammer40k_core.engine.damage_allocation import (
    AttackAllocationConstraint,
    allocation_context_for_unit,
    allocation_groups_for_context,
    destroy_model_by_rule,
    legal_allocation_group_orders,
)
from warhammer40k_core.engine.unit_strength_inventory import (
    starting_strength_records_for_army,
)


def test_attached_native_character_groups_and_toughness_contract(
    section05_definitions: Section02Definitions,
) -> None:
    d = section05_definitions
    body = d.unit(identity="body")
    body = replace(
        body,
        own_models=(
            contract_characteristic(body.own_models[0], Characteristic.TOUGHNESS, 6),
            *body.own_models[1:],
        ),
    )
    leaders = (
        d.unit(LORD_EXULTANT, identity="leader1"),
        d.unit(LORD_EXULTANT, identity="leader2"),
    )
    leaders = (
        replace(
            leaders[0],
            own_models=(
                replace(
                    contract_characteristic(leaders[0].own_models[0], Characteristic.TOUGHNESS, 9),
                    wounds_remaining=2,
                ),
            ),
        ),
        leaders[1],
    )
    state = minimal_state(d, body, *leaders)
    # Explicit two-leader Core grouping contract; no faction attachment permission claim.
    formation = AttachedUnitFormation(
        "attached-unit:section02:s05",
        body.unit_instance_id,
        tuple(u.unit_instance_id for u in leaders),
        component_unit_instance_ids=tuple(
            sorted((body.unit_instance_id, *(u.unit_instance_id for u in leaders)))
        ),
        source_id="constructed:s05:attachment",
        attachment_source_ids=("constructed:s05:two-leaders",),
    )
    army = replace(state.army_definitions[0], attached_units=(formation,))
    state.army_definitions[:] = [army]
    state.starting_strength_records[:] = starting_strength_records_for_army(army)
    place_units(state)
    target = formation.attached_unit_instance_id
    assert _target_unit_toughness(state=state, target_unit_instance_id=target) == 6
    context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target,
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=("constructed:s05:all-groups",),
            can_allocate_protected_characters=True,
        ),
    )
    groups = allocation_groups_for_context(
        state=state, allocation_context=context, include_priority_tiers=True
    )
    character_groups = [g for g in groups if g.character_model_ids]
    assert {g.model_ids for g in character_groups} == {u.own_model_ids() for u in leaders}
    orders = legal_allocation_group_orders(groups)
    assert len(orders) == 1
    assert not orders[0][0].character_model_ids
    assert orders[0][1].model_ids == leaders[0].own_model_ids()
    assert orders[0][2].model_ids == leaders[1].own_model_ids()
    destroy_model_by_rule(state=state, model_instance_id=body.own_model_ids()[0])
    assert _target_unit_toughness(state=state, target_unit_instance_id=target) == 4


def test_ordinary_unit_uses_highest_present_toughness(
    section05_definitions: Section02Definitions,
) -> None:
    d = section05_definitions
    unit = d.unit()
    unit = replace(
        unit,
        own_models=(
            contract_characteristic(unit.own_models[0], Characteristic.TOUGHNESS, 7),
            *unit.own_models[1:],
        ),
    )
    state = minimal_state(d, unit)
    place_units(state)
    assert _target_unit_toughness(state=state, target_unit_instance_id=unit.unit_instance_id) == 7
    destroy_model_by_rule(state=state, model_instance_id=unit.own_model_ids()[0])
    assert _target_unit_toughness(state=state, target_unit_instance_id=unit.unit_instance_id) == 4
