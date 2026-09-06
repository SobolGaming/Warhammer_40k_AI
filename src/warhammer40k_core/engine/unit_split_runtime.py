"""Engine-owned setup split application and persistence authentication."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.unit_split_decisions import (
    SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE,
    replay_unit_split_decisions,
)
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army

UNIT_SPLIT_APPLIED_EVENT = "unit_split_applied"


def next_unit_split_request(
    *,
    state: GameState,
    decisions: DecisionController,
) -> DecisionRequest | None:
    if (
        state.stage is not GameLifecycleStage.SETUP
        or state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS
    ):
        raise GameLifecycleError("Unit splitting requires its source-authorized setup window.")
    armies, request = replay_unit_split_decisions(
        game_id=state.game_id,
        armies=tuple(state.army_definitions),
        records=decisions.records,
    )
    if armies != tuple(state.army_definitions):
        raise GameLifecycleError("Unit split state disagrees with recorded membership.")
    if request is not None:
        _validate_source_window_state(state)
    return request


def validate_unit_split_checkpoint(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    pending_request: DecisionRequest | None,
) -> None:
    if (
        pending_request is None
        or pending_request.decision_type != SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    ):
        return
    if (
        state.stage is not GameLifecycleStage.SETUP
        or state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS
    ):
        raise GameLifecycleError("Pending unit split has the wrong source window.")
    _validate_source_window_state(state)
    _, expected = replay_unit_split_decisions(
        game_id=state.game_id,
        armies=tuple(state.army_definitions),
        records=decision_records,
    )
    if pending_request != expected:
        raise GameLifecycleError(
            "Pending unit split does not match its source and decision history."
        )


def _validate_source_window_state(state: GameState) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Unit split setup requires a battlefield.")
    if battlefield.placed_model_ids() or state.reserve_states or state.transport_cargo_states:
        raise GameLifecycleError("Pre-battle split must precede setup and reserve declarations.")


def preview_unit_split_decision(
    *,
    state: GameState,
    records: tuple[DecisionRecord, ...],
) -> GameState | None:
    armies, _ = replay_unit_split_decisions(
        game_id=state.game_id,
        armies=tuple(state.army_definitions),
        records=records,
    )
    if armies == tuple(state.army_definitions):
        return None
    _validate_source_window_state(state)
    return replace(
        state,
        army_definitions=list(armies),
        starting_strength_records=[
            r for a in armies for r in starting_strength_records_for_army(a)
        ],
    )


def apply_unit_split_decision(*, state: GameState, decisions: DecisionController) -> None:
    candidate = preview_unit_split_decision(state=state, records=decisions.records)
    if candidate is None:
        return
    armies = candidate.army_definitions
    old_ids = {r.split_id for a in state.army_definitions for r in a.unit_splits}
    added = [(a.player_id, r) for a in armies for r in a.unit_splits if r.split_id not in old_ids]
    if len(added) != 1:
        raise GameLifecycleError("A unit split decision must apply exactly one partition.")
    player_id, record = added[0]
    state.replace_armies_after_unit_split(candidate.army_definitions)
    decisions.event_log.append(
        UNIT_SPLIT_APPLIED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "secret": True,
                "visibility_source": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "split_record": record.to_payload(),
            }
        ),
    )


def authenticated_split_armies(
    *,
    state: GameState,
    expected_armies: tuple[ArmyDefinition, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_records: tuple[EventRecord, ...],
) -> tuple[ArmyDefinition, ...]:
    game_id = state.game_id
    armies, pending = replay_unit_split_decisions(
        game_id=game_id,
        armies=expected_armies,
        records=decision_records,
    )
    declaration_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    if pending is not None and (
        state.stage is not GameLifecycleStage.SETUP
        or (state.setup_step_index is not None and state.setup_step_index > declaration_index)
    ):
        raise GameLifecycleError("Setup advanced past an unresolved unit split permission.")
    expected = [
        validate_json_value(
            {
                "game_id": game_id,
                "player_id": a.player_id,
                "secret": True,
                "visibility_source": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "split_record": r.to_payload(),
            }
        )
        for a in armies
        for r in a.unit_splits
    ]
    actual = [e.payload for e in event_records if e.event_type == UNIT_SPLIT_APPLIED_EVENT]
    if actual != expected:
        raise GameLifecycleError("Unit split events disagree with authenticated decisions.")
    return armies
