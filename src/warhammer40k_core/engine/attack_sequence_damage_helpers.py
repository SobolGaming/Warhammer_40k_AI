from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DestructionReactionSource,
    MortalWoundApplication,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    record_finalized_mortal_wound_model_destructions,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.weapon_abilities import DEVASTATING_WOUNDS_RULE_ID

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


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


def record_deadly_demise_secondary_destruction_finalization(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    source: DestructionReactionSource,
    secondary_damage: DamageApplication,
    model_destroyed_event_id: str,
    destroying_player_id: str,
) -> None:
    source_unit_id = state.unit_instance_id_for_model(source_damage.model_instance_id)
    source_rules_unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id=source_unit_id
    ).unit_instance_id
    record_finalized_mortal_wound_model_destructions(
        state=state,
        decisions=decisions,
        application_id=f"{model_destroyed_event_id}:deadly-demise-finalization",
        source_rule_id=source.source_rule_id,
        source_context=validate_json_value(
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_context["attack_context_id"],
                "model_destroyed_event_id": model_destroyed_event_id,
                "source_damage_application": source_damage.to_payload(),
                "deadly_demise_source": source.to_payload(),
            }
        ),
        target_unit_instance_id=secondary_damage.target_unit_instance_id,
        application_payload=validate_json_value({"applications": [secondary_damage.to_payload()]}),
        destroyed_model_instance_ids=(secondary_damage.model_instance_id,),
        evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=destroying_player_id,
            source_rules_unit_instance_id=source_rules_unit_id,
            source_model_instance_id=source_damage.model_instance_id,
            destruction_source_kind=DestructionSourceKind.DEADLY_DEMISE,
            action_phase=attack_sequence.source_phase,
            source_step="deadly_demise_collateral",
        ),
        existing_model_destroyed_event_ids=(model_destroyed_event_id,),
    )
