from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathBindingKind,
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundLogicalDeathRecorder,
    append_mortal_wound_damage_logical_death_event,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_resolution_request,
    mortal_wound_resolution_source_context,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    rule_deadly_demise_secondary_source_result_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        DestructionReactionSource,
        MortalWoundApplicationProgress,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND = "rule_model_destruction_deadly_demise"


def is_rule_model_destruction_mortal_wound_request(request: DecisionRequest) -> bool:
    if not is_mortal_wound_resolution_request(request):
        return False
    source_context = mortal_wound_resolution_source_context(request)
    return isinstance(source_context, dict) and source_context.get("source_kind") == (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND
    )


def rule_deadly_demise_source_context(request: DecisionRequest) -> dict[str, JsonValue]:
    source_context = mortal_wound_resolution_source_context(request)
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Rule destruction mortal-wound source context must be an object.")
    if source_context.get("source_kind") != RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND:
        raise GameLifecycleError("Rule destruction mortal-wound source kind drift.")
    return source_context


def rule_deadly_demise_logical_death_binding() -> MortalWoundLogicalDeathCauseBinding:
    return MortalWoundLogicalDeathCauseBinding.per_model(
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
    )


def rule_deadly_demise_logical_death_recorder(
    *,
    state: GameState,
    decisions: DecisionController,
    parent_root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    progress: MortalWoundApplicationProgress | None = None,
) -> MortalWoundLogicalDeathRecorder:
    if progress is not None:
        binding = progress.logical_death_cause_binding
        if (
            binding is None
            or binding.binding_kind is not MortalWoundLogicalDeathBindingKind.PER_MODEL_PRODUCER
            or binding.cause_kind is not ModelDestructionCauseKind.RULE_EFFECT
        ):
            raise GameLifecycleError("Rule Deadly Demise logical-death binding drift.")

    def record(
        *,
        damage_application: DamageApplication,
        destroyed_model_placement: ModelPlacement,
        placement_retained: bool,
    ) -> EventRecord:
        if not placement_retained:
            raise GameLifecycleError("Rule Deadly Demise casualty must remain placed.")
        return append_mortal_wound_damage_logical_death_event(
            state=state,
            event_log=decisions.event_log,
            cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
            producer_id=rule_deadly_demise_secondary_source_result_id(
                parent_root_context=parent_root_context,
                source=source,
                model_instance_id=damage_application.model_instance_id,
            ),
            damage_application=damage_application,
            destroyed_model_placement=destroyed_model_placement,
            placement_retained=True,
        )

    return record


def rule_deadly_demise_mortal_wound_waiting_status(
    *,
    state: GameState,
    request: DecisionRequest,
) -> LifecycleStatus:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Rule destruction mortal wounds require a battle phase.")
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": phase.value,
                "decision_type": request.decision_type,
                "source_kind": RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
            }
        ),
    )


__all__ = (
    "RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND",
    "is_rule_model_destruction_mortal_wound_request",
    "rule_deadly_demise_logical_death_binding",
    "rule_deadly_demise_logical_death_recorder",
    "rule_deadly_demise_mortal_wound_waiting_status",
    "rule_deadly_demise_source_context",
)
