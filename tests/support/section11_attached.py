"""Already-permitted attachment checkpoint with native physical definitions."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import add_unit
from tests.support.section11_fixtures import LORD, SPAWN, state_case

from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.pose import Pose


def attached_case(
    definitions: Section02Definitions,
) -> tuple[GameState, UnitInstance, UnitInstance, UnitInstance, AttachedUnitFormation]:
    state, body, old_enemy = state_case(definitions)
    leader = definitions.unit(LORD, identity="leader")
    add_unit(state, leader, (Pose.at(10, 12.5),))
    enemy = definitions.unit(SPAWN, army_id="enemy", identity="target")
    state.army_definitions[:] = [
        replace(a, units=(enemy,)) if a.player_id == "opponent" else a
        for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=(
                        UnitPlacement(
                            "enemy",
                            "opponent",
                            enemy.unit_instance_id,
                            tuple(
                                ModelPlacement(
                                    "enemy",
                                    "opponent",
                                    enemy.unit_instance_id,
                                    m.model_instance_id,
                                    Pose.at(17, 10 + 2.5 * i),
                                )
                                for i, m in enumerate(enemy.own_models)
                            ),
                        ),
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    formation = AttachedUnitFormation(
        "attached-unit:section02:section11",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:section11:attachment-permission",
        attachment_source_ids=("constructed:section11:attachment-permission",),
    )
    state.army_definitions[:] = [
        replace(a, attached_units=(formation,)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    state.starting_attached_unit_records[:] = [
        r for a in state.army_definitions for r in starting_attached_unit_records_for_army(a)
    ]
    state.starting_strength_records[:] = [
        r for a in state.army_definitions for r in starting_strength_records_for_army(a)
    ]
    assert old_enemy.unit_instance_id == enemy.unit_instance_id
    return state, body, leader, enemy, formation
