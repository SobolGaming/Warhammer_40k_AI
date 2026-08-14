from __future__ import annotations

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    record_new_primary_turn_start_evidence_events,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.setup_flow import army_mustered_event_payload


def ensure_army_mustered_events_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
) -> None:
    armies_by_id = {army.army_id: army for army in state.army_definitions}
    players_requiring_provenance = {
        record.player_id for record in state.starting_attached_unit_records
    }
    recorded_army_ids: set[str] = set()
    for event in decisions.event_log.records:
        if event.event_type != "army_mustered":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or type(payload.get("army_id")) is not str:
            raise AssertionError("Fixture army_mustered event payload is malformed.")
        army_id = payload["army_id"]
        if army_id not in armies_by_id:
            raise AssertionError("Fixture army_mustered event references an unknown army.")
        if army_id in recorded_army_ids:
            raise AssertionError("Fixture army_mustered event is duplicated.")
        recorded_army_ids.add(army_id)
    for army in state.army_definitions:
        if army.player_id not in players_requiring_provenance or army.army_id in recorded_army_ids:
            continue
        decisions.event_log.append(
            "army_mustered",
            army_mustered_event_payload(state=state, army_definition=army),
        )


def record_primary_turn_start_evidence_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController | None = None,
) -> DecisionController:
    resolved_decisions = DecisionController() if decisions is None else decisions
    ensure_army_mustered_events_for_fixture(state, decisions=resolved_decisions)
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=resolved_decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    return resolved_decisions


def record_existing_primary_turn_start_evidence_events_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    if any(
        event.event_type == PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT
        for event in decisions.event_log.records
    ):
        raise AssertionError("Fixture primary turn-start evidence event is already recorded.")
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=(),
        snapshot_ids_before=(),
    )


def enter_battle_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController | None = None,
) -> DecisionController:
    resolved_decisions = DecisionController() if decisions is None else decisions
    ensure_army_mustered_events_for_fixture(state, decisions=resolved_decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    state.complete_final_setup_step_before_battle()
    state.enter_battle()
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=resolved_decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    return resolved_decisions
