"""Terrain membership and visibility belong to physical models of attached units."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import placement, scenario
from tests.support.section13_fixtures import area, scene
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.terrain_hidden import terrain_hidden_model_ids
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("leader_inside", [False, True])
def test_attached_terrain_hidden_and_cover_check_each_physical_owner(
    section13_definitions: Section02Definitions, leader_inside: bool
) -> None:
    d = section13_definitions
    s, attacker, body = scene(d, target_x=20, areas=(area(x=20, width=4, depth=4),))
    leader = d.unit(LORD_EXULTANT, army_id="enemy", identity="leader")
    formation = AttachedUnitFormation(
        "attached-unit:enemy:s13",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:s13:attachment-permission",
        attachment_source_ids=("constructed:s13:attachment-permission",),
    )
    # Explicit already-permitted attachment checkpoint; no named roster admission.
    s.army_definitions[:] = [
        replace(a, units=(*a.units, leader), attached_units=(formation,))
        if a.player_id == "opponent"
        else a
        for a in s.army_definitions
    ]
    s.starting_attached_unit_records[:] = [
        r for a in s.army_definitions for r in starting_attached_unit_records_for_army(a)
    ]
    s.starting_strength_records[:] = [
        r for a in s.army_definitions for r in starting_strength_records_for_army(a)
    ]
    assert s.battlefield_state is not None
    assert s.mission_setup is not None
    s.replace_battlefield_state(
        replace(
            s.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=(
                        *a.unit_placements,
                        placement(
                            leader, (Pose.at(20, 11.5 if leader_inside else 20),), enemy=True
                        ),
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in s.battlefield_state.placed_armies
            ),
        )
    )
    hidden = terrain_hidden_model_ids(
        state=s,
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        unit_instance_id=formation.attached_unit_instance_id,
    )
    assert set(hidden) == set(
        body.own_model_ids() + (leader.own_model_ids() if leader_inside else ())
    )
    rules_unit = rules_unit_view_by_id(
        state=s, unit_instance_id=formation.attached_unit_instance_id
    )
    assert rules_unit.model_by_id(body.own_model_ids()[0]) is body.own_models[0]
    assert rules_unit.model_by_id(leader.own_model_ids()[0]) is leader.own_models[0]
    result = shooting_target_candidate_for_model(
        scenario=scenario(s),
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=d.weapon("000000593:avenger-shuriken-catapult"),
        target_unit_id=formation.attached_unit_instance_id,
        terrain_areas=s.mission_setup.terrain_areas,
    )
    assert result.is_legal
    assert ("core-rules:benefit-of-cover" in result.targeting_rule_ids) is leader_inside
    assert set(result.target_in_range_model_ids) == set(
        body.own_model_ids() + leader.own_model_ids()
    )
    assert body.own_model_ids() != leader.own_model_ids()
