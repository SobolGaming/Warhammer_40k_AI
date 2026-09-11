from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
)
from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
    default_primary_reserve_entry_occurrence_validators,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_turn_start_recorded_events(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    event_index = {event.event_id: index for index, event in enumerate(event_records)}
    creations = tuple(
        occurrence
        for validator in default_primary_reserve_entry_occurrence_validators()
        for occurrence in validator(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index_by_id=event_index,
        )
        if occurrence.creates_unit
    )
    objective_states_by_occurrence = {
        (value.game_id, value.active_player_id, value.battle_round): value
        for value in state.primary_objective_turn_start_states
    }
    snapshots_by_occurrence = {
        (value.game_id, value.active_player_id, value.battle_round): value
        for value in state.primary_rules_unit_turn_start_snapshots
    }
    if len(objective_states_by_occurrence) != len(state.primary_objective_turn_start_states) or len(
        snapshots_by_occurrence
    ) != len(state.primary_rules_unit_turn_start_snapshots):
        raise GameLifecycleError("Primary turn-start evidence occurrence is duplicated.")
    if set(objective_states_by_occurrence) != set(snapshots_by_occurrence):
        raise GameLifecycleError(
            "Primary turn-start objective and position evidence occurrences are unpaired."
        )
    events_by_occurrence: dict[tuple[str, str, int], list[EventRecord]] = {}
    for record in event_records:
        if record.event_type != PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary turn-start evidence")
        game_id = payload.get("game_id")
        active_player_id = payload.get("active_player_id")
        battle_round = payload.get("battle_round")
        if (
            type(game_id) is not str
            or type(active_player_id) is not str
            or type(battle_round) is not int
        ):
            raise GameLifecycleError(
                "Primary turn-start recorded event occurrence identity is malformed."
            )
        occurrence = (game_id, active_player_id, battle_round)
        events_by_occurrence.setdefault(occurrence, []).append(record)
    if set(events_by_occurrence) != set(objective_states_by_occurrence):
        raise GameLifecycleError(
            "Primary turn-start evidence requires one authoritative recorded event."
        )
    for occurrence, objective_state in objective_states_by_occurrence.items():
        matching = events_by_occurrence[occurrence]
        if len(matching) != 1:
            raise GameLifecycleError(
                "Primary turn-start evidence requires exactly one recorded event."
            )
        snapshot = snapshots_by_occurrence[occurrence]
        expected_payload: dict[str, JsonValue] = {
            "game_id": objective_state.game_id,
            "battle_round": objective_state.battle_round,
            "active_player_id": objective_state.active_player_id,
            "primary_objective_turn_start_state": cast(
                dict[str, JsonValue], objective_state.to_payload()
            ),
            "primary_rules_unit_turn_start_snapshot": cast(
                dict[str, JsonValue], snapshot.to_payload()
            ),
        }
        recorded_payload = _event_payload(matching[0], event_name="primary turn-start evidence")
        recorded_snapshot = PrimaryRulesUnitTurnStartSnapshot.from_payload(
            recorded_payload.get("primary_rules_unit_turn_start_snapshot")
        )
        for creation in creations:
            if creation.event_order <= event_index[matching[0].event_id]:
                continue
            recorded_snapshot = primary_rules_unit_turn_start_snapshots_with_created_unit(
                [recorded_snapshot],
                unit_instance_id=creation.historical_unit_instance_id,
            )[0]
        reconstructed_payload = {
            **recorded_payload,
            "primary_rules_unit_turn_start_snapshot": recorded_snapshot.to_payload(),
        }
        if reconstructed_payload != expected_payload:
            raise GameLifecycleError("Primary turn-start recorded-event payload drift.")


def _event_payload(record: EventRecord, *, event_name: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{event_name} event payload must be an object.")
    return record.payload
