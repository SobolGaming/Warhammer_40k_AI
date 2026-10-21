"""Actual mission discovery and commit at the turn boundary, with full source layout."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_turn_end_sequencing import (
    mission_turn_end_candidates,
    request_mission_turn_end_rules,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sequencing import SequencingRuleOrigin


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_actual_eligible_mission_commits_and_achieved_condition_at_turn_end(
    section07_definitions: Section02Definitions, section07_mission: MissionSetup, active: str
) -> None:
    state = boundary_state(
        section07_definitions,
        phase=BattlePhase.FIGHT,
        active=active,
        battle_round=2,
        mission=section07_mission,
    )
    registry = RuntimeModifierRegistry.empty()
    decisions = DecisionController()
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=registry
    )
    candidates = mission_turn_end_candidates(
        state=state, decisions=decisions, runtime_modifier_registry=registry
    )
    assert candidates
    assert all(c.participant.origin is SequencingRuleOrigin.MISSION for c in candidates)
    assert any(c.participant.player_id == active for c in candidates)
    assert (
        request_mission_turn_end_rules(
            state=state, decisions=decisions, runtime_modifier_registry=registry
        )
        is None
    )
    assert any(
        evidence.scoring_player_id == active
        and evidence.objective_control_record_id == record.record_id
        for evidence in state.primary_scoring_state_evidence_records
    )
    # Reconnaissance's real no-enemy-operation-markers condition is achieved in
    # this minimal boundary scene. No scoring outcome is supplied to the engine.
    if active == "opponent":
        assert state.victory_point_ledger_for_player(active).victory_points > 0
    before = state.to_payload(), decisions.to_payload()
    assert (
        request_mission_turn_end_rules(
            state=state, decisions=decisions, runtime_modifier_registry=registry
        )
        is None
    )
    assert (state.to_payload(), decisions.to_payload()) == before
