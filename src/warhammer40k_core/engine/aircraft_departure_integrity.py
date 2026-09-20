"""Authenticate automatic Aircraft reserve entries against their timing occurrence."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.aircraft_rules import MOVEMENT_SOURCE_ID
from warhammer40k_core.engine.aircraft_turn_end import AIRCRAFT_RETURN_EVENT
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import reserve_entry_evidence_payload
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batch_from_event,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_battlefield_departure import (
        PrimaryBattlefieldDepartureState,
    )


def validate_aircraft_departure_source(
    *,
    state: GameState,
    departure: PrimaryBattlefieldDepartureState,
    mutation: EventRecord,
    reserve_entry: dict[str, JsonValue],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    source_index = event_index_by_id.get(departure.source_id)
    if source_index is None or source_index >= event_index_by_id[mutation.event_id]:
        raise GameLifecycleError("Aircraft departure lacks its prior turn-end source event.")
    source = event_records[source_index]
    payload = source.payload
    expected = {
        "game_id": state.game_id,
        "battle_round": departure.battle_round,
        "active_player_id": departure.active_player_id,
        "player_id": departure.owner_player_id,
        "phase": BattlePhase.FIGHT.value,
        "source_rule_id": MOVEMENT_SOURCE_ID,
        "unit_instance_id": departure.rules_unit_instance_id,
        "component_unit_instance_ids": list(departure.component_unit_instance_ids),
        "model_instance_ids": list(departure.removed_model_instance_ids),
    }
    if (
        source.event_type != AIRCRAFT_RETURN_EVENT
        or not isinstance(payload, dict)
        or set(payload) != {*expected, "reserve_state"}
        or any(payload[key] != value for key, value in expected.items())
        or departure.occurrence_id != source.event_id
        or departure.owner_player_id == departure.active_player_id
        or departure.phase != BattlePhase.FIGHT.value
    ):
        raise GameLifecycleError("Aircraft departure turn or source identity drift.")
    raw_reserve = payload["reserve_state"]
    if not isinstance(raw_reserve, dict):
        raise GameLifecycleError("Aircraft departure reserve source is malformed.")
    reserve = ReserveState.from_payload(cast(ReserveStatePayload, raw_reserve))
    if (
        reserve_entry_evidence_payload(reserve) != reserve_entry
        or reserve.source_rule_ids != (MOVEMENT_SOURCE_ID,)
        or reserve.required_arrival_battle_round is not None
    ):
        raise GameLifecycleError("Aircraft departure reserve source drift.")
    component_ids = set(departure.component_unit_instance_ids)
    if not any(
        "AIRCRAFT" in model.keywords
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    ):
        raise GameLifecycleError("Aircraft departure has no AIRCRAFT source model.")
    window_id = (
        f"timing-window:{state.game_id}:round-{departure.battle_round:02d}"
        f":turn:{departure.active_player_id}:end"
    )
    participant_id = f"{window_id}:{MOVEMENT_SOURCE_ID}:{departure.owner_player_id}"
    batches = tuple(
        timing_batch_from_event(record)
        for record in event_records[:source_index]
        if record.event_type == TIMING_BATCH_EVENT_TYPE
    )
    applicable = tuple(batch for batch in batches if batch.context.conflict_id == window_id)
    if not applicable or applicable[-1].selected_participant_id != participant_id:
        raise GameLifecycleError("Aircraft departure lacks its selected mandatory timing rule.")
