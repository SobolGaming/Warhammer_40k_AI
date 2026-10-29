"""Already-permitted native attachment at engaged Fight boundary; no admission claim."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section12_fixtures import LORD, add_native, engaged_case

from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.pose import Pose


def attached_case(
    d: Section02Definitions,
) -> tuple[GameState, UnitInstance, UnitInstance, UnitInstance, AttachedUnitFormation]:
    s, u, e = engaged_case(d)
    leader = d.unit(LORD, identity="leader")
    add_native(s, leader, (Pose.at(10, 12.5),))
    f = AttachedUnitFormation(
        "attached-unit:section02:section12",
        u.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((u.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:section12:attachment-permission",
        attachment_source_ids=("constructed:section12:attachment-permission",),
    )
    s.army_definitions[:] = [
        replace(a, attached_units=(f,)) if a.player_id == "owner" else a for a in s.army_definitions
    ]
    s.starting_attached_unit_records[:] = [
        r for a in s.army_definitions for r in starting_attached_unit_records_for_army(a)
    ]
    s.starting_strength_records[:] = [
        r for a in s.army_definitions for r in starting_strength_records_for_army(a)
    ]
    return s, u, leader, e, f
