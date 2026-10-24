"""Constructed Core contact evidence expires on the actual turn authority boundary."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section01_geometry import witnessed_query
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from warhammer40k_core.engine.base_contact_authority import (
    contacts_for_validated_move,
    current_deemed_base_contacts,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldTransitionBatch
from warhammer40k_core.engine.model_movement_history import ModelMovementDistance
from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.movement_reachability import MovementGoal
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("boundary", ["cleanup", "next-turn", "next-round"])
def test_01_04_04_deemed_contact_expires_at_turn_end(
    section01_definitions: Section02Definitions, boundary: str
) -> None:
    unit = section01_definitions.unit(LORD_EXULTANT, identity="one")
    other = section01_definitions.unit(LORD_EXULTANT, identity="two", army_id="enemy")
    state = minimal_state(section01_definitions, unit)
    state.army_definitions.append(
        replace(
            state.army_definitions[0],
            army_id="enemy",
            player_id="opponent",
            units=(other,),
        )
    )
    place_units(state)
    # Explicit geometry contract, not a claim that the native Lord has this overhang.
    source = Model(unit.own_model_ids()[0], Pose.at(5, 10), CircularBase(0.5), ModelVolume(1))
    target = Model(
        other.own_model_ids()[0],
        Pose.at(10, 10),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(
            ModelBodyPart("body", CircularBase(1.5), 0, 0, 0, 1, "constructed:Core-overhang"),
        ),
    )
    query = witnessed_query(
        source,
        Pose.at(8, 10),
        4,
        MovementGoal(models=(target,), range_inches=0),
        (target,),
    )
    result = contacts_for_validated_move(
        path_context=query.path_context,
        terrain_context=query.terrain_context,
        path_result=query.path_context.validate(),
        terrain_result=query.terrain_context.validate(),
        query=query,
    )
    (contact,) = result.deemed_base_contacts
    state.model_movement_history.append(
        ModelMovementDistance(
            "constructed:validated-contact-boundary",
            1,
            "owner",
            source.model_id,
            3,
            (contact.to_payload(),),
        )
    )
    (current,) = current_deemed_base_contacts(state)
    assert current.to_payload() == contact.to_payload()
    if boundary == "cleanup":
        state.end_turn_cleanup_states.append(
            EndTurnCleanupState(
                "cleanup",
                state.game_id,
                1,
                "owner",
                "fight",
                (),
                (),
                BattlefieldTransitionBatch(),
            )
        )
    elif boundary == "next-turn":
        state.active_player_id = "opponent"
    else:
        state.battle_round = 2
    assert current_deemed_base_contacts(state) == ()
