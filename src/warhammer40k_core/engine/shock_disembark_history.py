"""Authenticate Shock's passenger engagements independently of saved queue copies."""

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.fight_historical_eligibility import (
    historical_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_disembark_state import DisembarkModeKind


def validate_shock_disembark_engagement_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    for index, event in enumerate(event_records):
        if event.event_type != "unit_disembarked" or not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if payload.get("disembark_mode") != DisembarkModeKind.SHOCK_DISEMBARK.value:
            continue
        unit_id = payload.get("unit_instance_id")
        if not isinstance(unit_id, str):
            raise GameLifecycleError("Shock Disembark historical passenger identity is invalid.")
        if payload.get("start_engaged_enemy_unit_instance_ids") != []:
            raise GameLifecycleError("Embarked Shock passengers cannot inherit start engagements.")
        expected = historical_engaged_enemy_rules_unit_ids(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index=index + 1,
            unit_instance_id=unit_id,
        )
        if payload.get("post_engaged_enemy_unit_instance_ids") != list(expected):
            raise GameLifecycleError("Shock Disembark post-placement engagement history drift.")
