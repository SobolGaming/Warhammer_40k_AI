from __future__ import annotations

from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    unit_owner_player_id,
)
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import GameLifecycleError


def start_hazardous_mortal_wound_application(
    *,
    state: GameState,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    target_unit_instance_id: str,
    destroying_player_id: str,
    mortal_wounds: int,
    source_step: str,
) -> MortalWoundApplicationProgress:
    action_phase = state.current_battle_phase
    if action_phase is None:
        raise GameLifecycleError("Hazardous mortal wounds require a battle phase.")
    return MortalWoundApplicationProgress.start(
        application_id=application_id,
        source_rule_id=source_rule_id,
        source_context=source_context,
        target_unit_instance_id=target_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=target_unit_instance_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_state(
            state=state,
            destroying_player_id=destroying_player_id,
            source_rules_unit_instance_id=None,
            destruction_source_kind=DestructionSourceKind.HAZARDOUS,
            action_phase=action_phase,
            source_step=source_step,
        ),
    )


__all__ = ("start_hazardous_mortal_wound_application",)
