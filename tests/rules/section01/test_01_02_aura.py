"""Parsed allegiance/other/indefinite unit grants reach each physical model."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state, place_units
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("a friendly", {"source", "peer"}),
        ("an enemy", {"enemy"}),
        ("a", {"source", "peer", "enemy"}),
        ("another friendly", {"peer"}),
    ],
)
def test_01_02_allegiance_other_and_indefinite_targets(
    section01_definitions: Section02Definitions, subject: str, expected: set[str]
) -> None:
    source = section01_definitions.unit(identity="source")
    peer = section01_definitions.unit(identity="peer")
    enemy = section01_definitions.unit(LORD_EXULTANT, identity="enemy", army_id="enemy-army")
    state = minimal_state(section01_definitions, source, peer)
    state.army_definitions.append(
        replace(
            state.army_definitions[0],
            army_id="enemy-army",
            player_id="opponent",
            units=(enemy,),
        )
    )
    place_units(state)
    ir = core_rule(
        f'Aura: while {subject} unit is within 100" of this unit, subtract 1 from wound rolls.'
    )
    result = execute_rule_ir(
        rule_ir=ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="owner",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="owner",
            timing_window_id="aura",
            source_unit_instance_id=source.unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    (evaluation,) = result.aura_evaluations
    affected_ids = evaluation["affected_unit_instance_ids"]
    assert isinstance(affected_ids, list)
    assert all(isinstance(unit_id, str) for unit_id in affected_ids)
    assert set(affected_ids) == {
        u.unit_instance_id
        for u in (source, peer, enemy)
        if u.unit_instance_id.rsplit(":", 1)[1] in expected
    }
    assert source.datasheet_id == peer.datasheet_id
