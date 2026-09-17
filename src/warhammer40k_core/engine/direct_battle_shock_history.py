"""Reconstruct source-backed direct status changes without Leadership-test events."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battle_shock_state import (
    BATTLE_SHOCK_STATE_ALREADY,
    BATTLE_SHOCK_STATE_RECORDED,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.move_ability_choices import CHOICE_KEY, choice_descriptor
from warhammer40k_core.engine.move_keyword_completion import validate_completion_roll_event
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def replay_direct_battle_shock(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    replayed_states: dict[str, BattleShockedUnitState],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
) -> None:
    payload, roll = validate_completion_roll_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=event_index,
    )
    unit_id = cast(str, payload["unit_instance_id"])
    player_id = cast(str, payload["player_id"])
    if owner_by_unit_id.get(unit_id) != player_id or unit_id not in model_ids_by_unit_id:
        raise GameLifecycleError("Direct Battle-shock historical owner or model inventory drift.")
    descriptor = choice_descriptor(payload[CHOICE_KEY])
    alive_ids = {
        row.model_instance_id
        for row in physical_model_authority_before_event(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index=event_index,
        )
        if row.wounds_remaining > 0
    }
    applies = roll.current_total in descriptor.battle_shocked_roll_values and bool(
        alive_ids.intersection(model_ids_by_unit_id[unit_id])
    )
    expected = (
        (BATTLE_SHOCK_STATE_ALREADY if unit_id in replayed_states else BATTLE_SHOCK_STATE_RECORDED)
        if applies
        else "not_required"
    )
    if payload.get("state_update") != expected:
        raise GameLifecycleError("Direct Battle-shock historical mutation drift.")
    if expected == BATTLE_SHOCK_STATE_RECORDED:
        replayed_states[unit_id] = BattleShockedUnitState(
            player_id=player_id,
            unit_instance_id=unit_id,
            model_instance_ids=model_ids_by_unit_id[unit_id],
            source_result_id=cast(str, payload["result_id"]),
            battle_round_started=cast(int, payload["battle_round"]),
        )
