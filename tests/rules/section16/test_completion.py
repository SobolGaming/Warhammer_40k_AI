"""16.01 move/departure interruption and immutable completion state transitions."""

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_fixtures import action, checkpoint

from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
)
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize("kind", list(ModelDisplacementKind))
def test_every_move_kind_interrupts_except_pile_in_and_consolidation(
    section16_definitions: Section02Definitions, kind: ModelDisplacementKind
) -> None:
    _state, unit = checkpoint(section16_definitions)
    started = action(unit)
    before = started.to_payload()
    result = interrupt_mission_action_for_displacement(started, displacement_kind=kind)
    if kind in {ModelDisplacementKind.PILE_IN, ModelDisplacementKind.CONSOLIDATE}:
        assert result is None
        completed = started.complete_without_award(
            battle_round=1, phase="fight", completion_timing="turn_end"
        )
        assert completed.status is MissionActionStatus.COMPLETED
    else:
        assert result is not None
        assert result.status is MissionActionStatus.INTERRUPTED
        assert result.interrupted_reason == "unit_moved"
        with pytest.raises(GameLifecycleError, match="Only started"):
            result.complete_without_award(
                battle_round=1, phase="fight", completion_timing="turn_end"
            )
    assert started.to_payload() == before


def test_leaving_battlefield_prevents_completion_and_roundtrips(
    section16_definitions: Section02Definitions,
) -> None:
    _state, unit = checkpoint(section16_definitions)
    interrupted = interrupt_mission_action_for_battlefield_departure(action(unit))
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert interrupted.interrupted_reason == "unit_left_battlefield"
    assert MissionActionState.from_payload(interrupted.to_payload()) == interrupted
    with pytest.raises(GameLifecycleError, match="Only started"):
        interrupted.complete_without_award(
            battle_round=1, phase="fight", completion_timing="turn_end"
        )


def test_completion_requires_exact_timing_and_is_single_use(
    section16_definitions: Section02Definitions,
) -> None:
    _state, unit = checkpoint(section16_definitions)
    started = action(unit)
    with pytest.raises(GameLifecycleError, match="timing drift"):
        started.complete_without_award(
            battle_round=1, phase="shooting", completion_timing="phase_end"
        )
    completed = started.complete_without_award(
        battle_round=1, phase="fight", completion_timing="turn_end"
    )
    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.completed_phase == "fight"
    assert completed.completed_battle_round == 1
    assert MissionActionState.from_payload(completed.to_payload()) == completed
    with pytest.raises(GameLifecycleError, match="Only started"):
        completed.complete_without_award(
            battle_round=1, phase="fight", completion_timing="turn_end"
        )
