"""Small serialization layer; ordinary clause cases never load a full game."""

import json
from typing import cast

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.game_state import GameState, GameStatePayload


def test_native_minimal_checkpoint_roundtrip_keeps_isolated_state(
    section01_definitions: Section02Definitions,
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    payload = state.to_payload()
    restored = GameState.from_payload(cast(GameStatePayload, json.loads(json.dumps(payload))))
    assert restored.to_payload() == payload
    restored.battle_shocked_unit_ids.append(unit.unit_instance_id)
    assert state.battle_shocked_unit_ids == []
    assert restored.army_definitions[0].units[0] is not unit
    assert (
        restored.army_definitions[0].units[0].datasheet_abilities[0].rule_ir_payload
        is not unit.datasheet_abilities[0].rule_ir_payload
    )
