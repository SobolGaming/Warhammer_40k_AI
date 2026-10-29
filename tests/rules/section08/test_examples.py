"""Exact uncommon source examples, explicitly constructed native-body contracts."""

from dataclasses import replace

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import contract_characteristic
from tests.support.section08_fixtures import mark_shocked, requests
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model


def test_constructed_three_model_full_strength_shocked_example(
    section08_definitions: Section02Definitions,
) -> None:
    native = section08_definitions.unit("000000592")
    unit = replace(native, own_models=native.own_models[:3])
    state = minimal_state(section08_definitions, unit)
    place_units(state)
    assert requests(state) == ()
    mark_shocked(state)
    (request,) = requests(state)
    assert request.below_half_strength_context.starting_model_count == 3
    assert request.below_half_strength_context.current_model_count == 3
    assert not request.below_half_strength_context.is_at_or_below_half_strength


def test_constructed_eleven_wound_vehicle_at_three_wounds_example(
    section08_definitions: Section02Definitions,
) -> None:
    native = section08_definitions.unit("000000968")
    model = contract_characteristic(native.own_models[0], Characteristic.WOUNDS, 11)
    unit = replace(native, own_models=(model,))
    state = minimal_state(section08_definitions, unit)
    place_units(state)
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=8,
        damage_kind=DamageKind.NORMAL,
    )
    (request,) = requests(state)
    context = request.below_half_strength_context
    assert context.starting_model_count == 1
    assert context.single_model_starting_wounds == 11
    assert context.single_model_wounds_remaining == 3
    assert context.is_below_half_strength
