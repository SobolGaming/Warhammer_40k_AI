"""Unrestricted parsed grants cover native Infantry, Character, Beast and Vehicle models."""

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state
from tests.support.section02_fixtures import (
    CHAOS_SPAWN,
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.stealth import stealth_source_inventory


@pytest.mark.parametrize("datasheet", [INFRACTORS, LORD_EXULTANT, CHAOS_SPAWN, MAULERFIEND])
@pytest.mark.parametrize("spelling", ["Stealth", "stealth"])
def test_01_02_07_11_grant_to_unit_is_grant_to_every_native_model(
    section01_definitions: Section02Definitions, datasheet: str, spelling: str
) -> None:
    unit = section01_definitions.unit(datasheet)
    state = minimal_state(section01_definitions, unit)
    rule = core_rule(f"This unit gains {spelling} until the end of the phase.")
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="owner",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="owner",
            source_unit_instance_id=unit.unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    native, covered, commitments = stealth_source_inventory(
        state=state, target_unit_instance_id=unit.unit_instance_id
    )
    assert set(native) == set(unit.own_model_ids())
    assert covered == set(unit.own_model_ids())
    assert commitments
