from __future__ import annotations

from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    unit_owner_player_id,
)
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
)
from warhammer40k_core.engine.mortal_wound_target_lineage import (
    FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY,
    MortalWoundTargetLineage,
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
    target_lineage: MortalWoundTargetLineage | None = None,
) -> MortalWoundApplicationProgress:
    action_phase = state.current_battle_phase
    if action_phase is None:
        raise GameLifecycleError("Hazardous mortal wounds require a battle phase.")
    embedded_target = (
        target_lineage is not None
        and target_lineage.policy == FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY
    )
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
        destruction_evidence=(
            None
            if embedded_target
            else MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id=destroying_player_id,
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.HAZARDOUS,
                action_phase=action_phase,
                source_step=source_step,
            )
        ),
        logical_death_cause_binding=(
            MortalWoundLogicalDeathCauseBinding.fixed(
                cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
                producer_id=application_id,
            )
            if embedded_target
            else None
        ),
        target_lineage=target_lineage,
    )


__all__ = ("start_hazardous_mortal_wound_application",)
