"""FAQ04: coherency casualty reaches mission physical-model evidence."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_cleanup import apply_chosen_cleanup, chosen_cleanup
from tests.support.section03_fixtures import native_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.secondary_model_destruction_history import (
    secondary_model_destructions_for_boundary,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("chosen_index", [0, 1])
@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_faq04_native_coherency_death_is_counted_in_mission_casualty_inventory(
    section03_definitions: Section02Definitions,
    section03_setup_mission: MissionSetup,
    chosen_index: int,
    turn_player: str,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    state = native_state(section03_definitions, unit, (Pose.at(10, 10), Pose.at(20, 10)))
    state.mission_setup = section03_setup_mission
    state.army_definitions = [
        replace(
            a,
            force_disposition_id=section03_setup_mission.primary_mission_assignment_for_player(
                a.player_id
            ).force_disposition_id,
        )
        for a in state.army_definitions
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.active_player_id = turn_player
    # Explicit authenticated post-choice input, not D13's automatic casualty path.
    decisions = DecisionController()
    cleanup = chosen_cleanup(state, unit, unit.own_model_ids()[chosen_index], decisions)
    assert decisions.records[0].request.actor_id == "owner"
    apply_chosen_cleanup(state, cleanup)
    # Explicit scoring-boundary contract; this test owns casualty evidence, not OC.
    record = ObjectiveControlRecord(
        "post-cleanup",
        state.game_id,
        1,
        turn_player,
        ObjectiveControlTiming.PHASE_END,
        "fight",
        "section03",
        (
            ObjectiveControlResult.from_contributors(
                objective_id="contract-objective", contributors=()
            ),
        ),
    )
    rows = secondary_model_destructions_for_boundary(state=state, record=record)
    removed = cleanup.removed_model_instance_ids
    assert removed == (unit.own_model_ids()[chosen_index],)
    assert tuple(m.model_instance_id for r in rows for m in r.destroyed_models) == removed
    assert rows[0].departure.owner_player_id == "owner"
    assert rows[0].destroyed_models[0].starting_wounds == unit.own_models[0].initial_wounds
    # Partial-unit casualty must not fabricate destruction of the surviving unit.
    assert not state.secondary_unit_destruction_states
