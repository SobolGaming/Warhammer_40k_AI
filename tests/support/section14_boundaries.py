"""Minimal end-boundary scenes, built from native indexed definitions.

The mission is immutable mandatory control/scoring geometry only. No setup,
mustering, preceding phases, or full game replay is used to reach this rule.
"""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section09_fixtures import attach_mission
from tests.support.section14_fixtures import objective_state

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def move_checkpoint(state: GameState, unit: UnitInstance, x: float, y: float) -> None:
    """Construct an already-placed boundary; this does not execute movement."""
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            placement(
                unit,
                tuple(Pose.at(x, y + 1.5 * i) for i in range(len(unit.own_models))),
                enemy=unit.unit_instance_id.startswith("enemy:"),
            )
        )
    )


def boundary_case(
    definitions: Section02Definitions,
    *,
    phase: BattlePhase = BattlePhase.MOVEMENT,
    sheet: str = "000004078",
) -> tuple[GameState, UnitInstance, UnitInstance]:
    state, unit, enemy = objective_state(definitions, subject_sheet=sheet)
    attach_mission(state)
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    move_checkpoint(state, unit, marker.x_inches, marker.y_inches)
    move_checkpoint(state, enemy, marker.x_inches + 20, marker.y_inches)
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    return state, unit, enemy


def constructed_sticky(
    state: GameState, unit: UnitInstance, objective_id: str
) -> StickyObjectiveControlState:
    """Typed Secured checkpoint permission, never a claimed native grant."""
    phase = state.current_battle_phase
    assert phase is not None
    return StickyObjectiveControlState(
        state_id="constructed:s14:secured",
        game_id=state.game_id,
        player_id="owner",
        objective_id=objective_id,
        source_rule_id="constructed:s14:permission",
        source_event_id="constructed:s14:prior-event",
        battle_round=state.battle_round,
        phase=phase.value,
        active_player_id="owner",
        originating_unit_instance_id=unit.unit_instance_id,
        destroyed_unit_instance_id=unit.unit_instance_id,
    )
