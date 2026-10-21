"""Colocated FAQ52: own abilities survive cargo, external geometry does not."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import AVENGERS, transport_scene
from warhammer40k_core.engine.ability_presence import (
    AbilitySpatialRelationship,
    ability_presence,
    ability_spatial_relationship,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model


def test_faq52_embarked_native_abilities_and_equipment_keep_physical_ownership(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=AVENGERS)
    cargo = rules_unit_view_by_id(state=s.state, unit_instance_id=s.passenger.unit_instance_id)
    carrier = rules_unit_view_by_id(state=s.state, unit_instance_id=s.transport.unit_instance_id)
    assert s.passenger.datasheet_abilities
    assert ability_presence(state=s.state, rules_unit=cargo).off_battlefield_model_ids == tuple(
        sorted(s.passenger.own_model_ids())
    )
    assert (
        ability_spatial_relationship(state=s.state, source=cargo, target=cargo)
        is AbilitySpatialRelationship.OWN_ABILITY
    )
    assert (
        ability_spatial_relationship(state=s.state, source=cargo, target=carrier)
        is AbilitySpatialRelationship.OFF_BATTLEFIELD
    )
    assert (
        ability_spatial_relationship(state=s.state, source=carrier, target=cargo)
        is AbilitySpatialRelationship.OFF_BATTLEFIELD
    )
    passenger_weapons = {
        w.weapon_instance_id
        for m in s.passenger.own_models
        for w in equipped_weapon_instances_for_model(m)
    }
    carrier_weapons = {
        w.weapon_instance_id
        for m in s.transport.own_models
        for w in equipped_weapon_instances_for_model(m)
    }
    assert passenger_weapons
    assert carrier_weapons
    assert passenger_weapons.isdisjoint(carrier_weapons)
    # The native Wave Serpent has no borrowed passenger weapon by default.
    # Firing Deck's distinct temporary weapon-owner consumer is a targeted
    # dependency control; this fixture invents no native Firing Deck grant.
