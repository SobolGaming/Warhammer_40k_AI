"""Mandatory deployment and opponent-turn departure at explicit engine boundaries."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission
from tests.support.section23_fixtures import LORD, scene
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.aircraft_deployment import (
    apply_mandatory_aircraft_reserve_declarations,
)
from warhammer40k_core.engine.aircraft_turn_end import (
    AIRCRAFT_RETURN_EVENT,
    aircraft_turn_end_binding,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.reserves import ReserveKind, ReserveOrigin, ReserveUnitPointValue
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("fleet", [1, 2])
def test_all_aircraft_are_mandatory_strategic_reserves_once_with_owner_secret(
    section23_definitions: Section02Definitions, fleet: int
) -> None:
    d = section23_definitions
    state, aircraft, _ = scene(d, aircraft_attacker=True)
    add_unit(state, d.unit(LORD, identity="ground"), (Pose.at(12, 30),))
    aircraft_ids = [aircraft.unit_instance_id]
    if fleet == 2:
        extra = with_unit_keywords(
            d.unit(LORD, identity="aircraft2"), keywords=("AIRCRAFT", "FLY", "CHARACTER")
        )
        add_unit(state, extra, (Pose.at(20, 30),))
        aircraft_ids.append(extra.unit_instance_id)
    config = movement_session(d, state).lifecycle.config
    config = replace(
        config,
        reserve_unit_points=tuple(
            ReserveUnitPointValue(u.unit_instance_id, 100, "constructed:s23:price")
            for a in state.army_definitions
            for u in a.units
        ),
    )
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    state.battle_phase_index = None
    state.battlefield_state = None
    decisions = DecisionController()
    rows = apply_mandatory_aircraft_reserve_declarations(
        state=state, config=config, decisions=decisions
    )
    assert {r.unit_instance_id for r in rows} == set(aircraft_ids)
    assert all(r.reserve_origin is ReserveOrigin.AIRCRAFT_MANDATORY_RESERVE for r in rows)
    assert all(r.reserve_kind is ReserveKind.STRATEGIC_RESERVES and r.is_unarrived for r in rows)
    assert (
        apply_mandatory_aircraft_reserve_declarations(
            state=state, config=config, decisions=decisions
        )
        == ()
    )
    for viewer, expected in (("owner", fleet), ("opponent", 0)):
        events = EventStreamCursor().events_since(decisions.event_log, viewer_player_id=viewer)
        assert (
            len([e for e in events["events"] if e["event_type"] == "aircraft_reserve_declared"])
            == expected
        )


@pytest.mark.parametrize("turn_owner", ["owner", "opponent"])
@pytest.mark.parametrize("fleet", [1, 2])
def test_turn_end_returns_only_opponents_present_aircraft_once(
    section23_definitions: Section02Definitions, turn_owner: str, fleet: int
) -> None:
    d = section23_definitions
    state, aircraft, enemy = scene(d, aircraft_attacker=True)
    add_unit(state, d.unit(LORD, identity="ground"), (Pose.at(12, 30),))
    ids = [aircraft.unit_instance_id]
    if fleet == 2:
        extra = with_unit_keywords(d.unit(LORD, identity="extra"), keywords=("AIRCRAFT", "FLY"))
        add_unit(state, extra, (Pose.at(20, 30),))
        ids.append(extra.unit_instance_id)
    state.active_player_id = turn_owner
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    # Departure evidence is mission-owned. Supply only its required mission
    # checkpoint; do not traverse earlier phases or imply mission admission.
    attach_mission(state)
    decisions = DecisionController()
    context = TurnEndRequestContext(state, decisions, BattlePhase.FIGHT)
    binding = aircraft_turn_end_binding()
    assert binding.candidate_handler is not None
    candidates = binding.candidate_handler(context)
    assert len(candidates) == (turn_owner == "opponent")
    for candidate in candidates:
        candidate.activate()
    assert state.battlefield_state is not None
    assert state.battlefield_state.is_unit_placed(enemy.unit_instance_id)
    assert state.battlefield_state.is_unit_placed("section02:ground")
    for identity in ids:
        assert state.battlefield_state.is_unit_placed(identity) is (turn_owner == "owner")
        reserve = state.reserve_state_for_unit(identity)
        if turn_owner == "opponent":
            assert reserve is not None
            assert reserve.is_unarrived
            assert reserve.reserve_kind is ReserveKind.STRATEGIC_RESERVES
            assert reserve.entered_reserves_battle_round == state.battle_round
        else:
            assert reserve is None
    assert len(
        [e for e in decisions.event_log.records if e.event_type == AIRCRAFT_RETURN_EVENT]
    ) == (fleet if turn_owner == "opponent" else 0)
    assert not binding.candidate_handler(context)
    phase_end = replace(context, trigger_kind=TimingTriggerKind.END_PHASE)
    assert not binding.candidate_handler(phase_end)
