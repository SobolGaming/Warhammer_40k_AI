from __future__ import annotations

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.event_log import EventLog


def test_dice_event_log_serialization_round_trips_exactly() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Advance roll for replayed Tactical Squad",
        roll_type="advance_roll",
        actor_id="unit-tactical-squad",
    )
    manager = DiceRollManager("seed")
    manager.roll(spec)

    payload = manager.event_log.to_payload()

    assert EventLog.from_payload(payload).to_payload() == payload
