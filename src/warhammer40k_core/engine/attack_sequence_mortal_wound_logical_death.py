from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.model_destruction_cause_producers import (
    attack_damage_model_destruction_producer_id,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundLogicalDeathRecorder,
    fixed_mortal_wound_logical_death_recorder,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    mortal_wound_resolution_progress,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState


def attack_deadly_demise_logical_death_binding(
    attack_sequence: AttackSequence,
) -> MortalWoundLogicalDeathCauseBinding:
    return MortalWoundLogicalDeathCauseBinding.fixed(
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=attack_damage_model_destruction_producer_id(attack_sequence),
    )


def attack_deadly_demise_logical_death_recorder(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    progress: MortalWoundApplicationProgress | None = None,
) -> MortalWoundLogicalDeathRecorder:
    binding = attack_deadly_demise_logical_death_binding(attack_sequence)
    if progress is not None and progress.logical_death_cause_binding != binding:
        raise GameLifecycleError("Attack Deadly Demise logical-death binding drift.")
    return fixed_mortal_wound_logical_death_recorder(
        state=state,
        event_log=decisions.event_log,
        binding=binding,
    )


def resolve_attack_sequence_mortal_wound_feel_no_pain(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    request: DecisionRequest,
    result: DecisionResult,
    next_request_id: str,
    dice_manager: DiceRollManager,
) -> MortalWoundRoutingResult:
    progress = mortal_wound_resolution_progress(request)
    source_context = progress.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Mortal-wound source context must be an object.")
    is_deadly_demise = source_context.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
    recorder = (
        attack_deadly_demise_logical_death_recorder(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            progress=progress,
        )
        if is_deadly_demise
        else None
    )
    return resolve_mortal_wound_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        next_request_id=next_request_id,
        dice_manager=dice_manager,
        remove_destroyed_models=not is_deadly_demise,
        logical_death_recorder=recorder,
    )


__all__ = (
    "attack_deadly_demise_logical_death_binding",
    "attack_deadly_demise_logical_death_recorder",
    "resolve_attack_sequence_mortal_wound_feel_no_pain",
)
