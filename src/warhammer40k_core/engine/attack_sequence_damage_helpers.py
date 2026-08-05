from __future__ import annotations

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.damage_allocation import MortalWoundApplication
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.weapon_abilities import DEVASTATING_WOUNDS_RULE_ID


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


def emit_deferred_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_id: str,
    attack_context_ids: tuple[str, ...],
    mortal_wounds: int,
    application: MortalWoundApplication,
) -> None:
    decisions.event_log.append(
        "devastating_wounds_mortal_wounds_applied",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "target_unit_instance_id": target_unit_id,
            "attack_context_ids": list(attack_context_ids),
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": application.to_payload(),
            "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
        },
    )
