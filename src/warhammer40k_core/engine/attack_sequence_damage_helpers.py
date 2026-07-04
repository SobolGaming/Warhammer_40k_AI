from __future__ import annotations

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec


def no_save_damage_order_roll_spec(
    *,
    player_id: str,
    allocated_model_id: str,
    attack_context_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"No-save damage order die for {allocated_model_id} from {attack_context_id}",
        roll_type="attack_sequence.allocation_order.no_save",
        actor_id=player_id,
    )
