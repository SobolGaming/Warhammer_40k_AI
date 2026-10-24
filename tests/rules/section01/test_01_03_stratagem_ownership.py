"""The native Core Stratagem restriction owner keeps each player's uses separate."""

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagems_eligibility import _restriction_violation
from warhammer40k_core.engine.stratagems_model import (
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemUseRecord,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize("player", ["owner", "opponent"])
def test_01_03_01_stratagem_use_restricts_only_using_player(
    section01_definitions: Section02Definitions, player: str
) -> None:
    state = minimal_state(section01_definitions)
    definition = next(
        r.definition
        for r in eleventh_edition_core_stratagem_catalog_records()
        if r.definition.name == "Command Re-roll"
    )
    binding = StratagemTargetBinding(StratagemTargetKind.NONE)
    use = StratagemUseRecord(
        "use",
        "owner",
        definition.stratagem_id,
        definition.source_id,
        1,
        BattlePhase.COMMAND,
        "owner",
        None,
        "request",
        "result",
        "option",
        binding,
        (),
        (),
        definition.command_point_cost,
        None,
        definition.handler_id,
    )
    state.stratagem_use_records.append(use)
    context = StratagemEligibilityContext(
        state.game_id,
        player,
        1,
        BattlePhase.COMMAND,
        "owner",
        TimingTriggerKind.START_PHASE,
    )
    reason = _restriction_violation(
        state=state,
        player_id=player,
        definition=definition,
        context=context,
        target_binding=binding,
    )
    assert (reason is not None) is (player == "owner")
    assert state.stratagem_use_records_for_player(player) == ((use,) if player == "owner" else ())
