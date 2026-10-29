"""Cheap open-ray native mixed body checkpoint; attachment permission constructed.

The engaged enemy is behind both attackers; the outside enemy is to their right.
No intervening bodies, terrain, geometry substitution or visibility mocks are used.
"""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section04_fixtures import add_enemy
from tests.support.section09_fixtures import add_unit
from tests.support.section10_fixtures import LORD, WRAITHLORD, shooting_mission, shooting_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.pose import Pose


def mixed_case(
    definitions: Section02Definitions,
) -> tuple[LocalGameSession, GameState, UnitInstance, UnitInstance, AttachedUnitFormation]:
    body = definitions.unit(WRAITHLORD)
    leader = definitions.unit(LORD, identity="leader")
    engaged = definitions.unit(LORD, identity="target", army_id="enemy")
    state = native_state(
        definitions, body, (Pose.at(10, 10),), enemy=engaged, enemy_poses=(Pose.at(7, 11.7),)
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    add_unit(state, leader, (Pose.at(10, 13.4),))
    add_enemy(definitions, state, identity="outside", x=20, y=11.7)
    # An explicitly already-permitted mixed attachment, not a named faction grant.
    formation = AttachedUnitFormation(
        "attached-unit:section02:section10-mixed",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:section10:mixed-permission",
        attachment_source_ids=("constructed:section10:mixed-permission",),
    )
    state.army_definitions[:] = [
        replace(a, attached_units=(formation,)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    # Actual post-attack reconciliation requires the already-formed unit's
    # battle-start identity. Derive only these frozen records, no setup traversal.
    state.starting_attached_unit_records[:] = [
        record
        for army in state.army_definitions
        for record in starting_attached_unit_records_for_army(army)
    ]
    state.starting_strength_records[:] = [
        record
        for army in state.army_definitions
        for record in starting_strength_records_for_army(army)
    ]
    return shooting_session(definitions, state, shooting_mission()), state, body, leader, formation
