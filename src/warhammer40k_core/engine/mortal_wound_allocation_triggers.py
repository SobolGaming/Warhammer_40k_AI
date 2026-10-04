"""Shared Select Model boundary and source-permission prevention execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.mortal_wound_allocation_permissions import (
    MORTAL_WOUND_ALLOCATION_RULE_APPLIED_EVENT_TYPE,
    mortal_wound_allocation_preventions,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        MortalWoundAllocationOccurrence,
        MortalWoundAllocationPriority,
    )


def record_mortal_wound_allocation_occurrence(
    *,
    state: GameState,
    decisions: DecisionController,
    application_id: str,
    wound_index: int,
    target_unit_instance_id: str,
    legal_model_ids: tuple[str, ...],
    priority_tier: MortalWoundAllocationPriority,
    selected_model_id: str,
    parent_request_id: str | None = None,
    parent_result_id: str | None = None,
    destruction_evidence: MortalWoundDestructionEvidence | None = None,
) -> tuple[MortalWoundAllocationOccurrence, tuple[FeelNoPainSource, ...], bool]:
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
        MortalWoundAllocationOccurrence,
        MortalWoundSelectionDisposition,
        mortal_wound_feel_no_pain_decline_allowed,
        mortal_wound_feel_no_pain_sources,
    )

    bindings = mortal_wound_allocation_preventions(state=state, model_instance_id=selected_model_id)
    sources = mortal_wound_feel_no_pain_sources(
        state=state,
        model_instance_id=selected_model_id,
        destruction_evidence=destruction_evidence,
    )
    decline_allowed = mortal_wound_feel_no_pain_decline_allowed(
        state=state, model_instance_id=selected_model_id
    )
    occurrence = MortalWoundAllocationOccurrence(
        occurrence_id=f"{application_id}:allocation:{wound_index:06d}",
        application_id=application_id,
        wound_index=wound_index,
        target_unit_instance_id=target_unit_instance_id,
        priority_tier=priority_tier,
        legal_model_ids=legal_model_ids,
        selected_model_id=selected_model_id,
        selection_disposition=(
            MortalWoundSelectionDisposition.SOLE_LEGAL_MODEL
            if parent_request_id is None
            else MortalWoundSelectionDisposition.PLAYER_DECISION
        ),
        parent_request_id=parent_request_id,
        parent_result_id=parent_result_id,
        feel_no_pain_sources=sources,
        feel_no_pain_decline_allowed=decline_allowed,
    )
    if any(
        event.event_type == MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("occurrence_id") == occurrence.occurrence_id
        for event in decisions.event_log.records
    ):
        raise GameLifecycleError("Mortal-wound allocation occurrence already exists.")
    decisions.event_log.append(MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE, occurrence.to_payload())
    executed_sources: list[FeelNoPainSource] = []
    for binding in bindings:
        decisions.event_log.append(
            MORTAL_WOUND_ALLOCATION_RULE_APPLIED_EVENT_TYPE,
            {
                "allocation_occurrence_id": occurrence.occurrence_id,
                "trigger_kind": TimingTriggerKind.MORTAL_WOUND_ALLOCATED.value,
                "permission_effect_id": binding.permission.effect_id,
                "source_rule_id": binding.permission.source_rule_id,
                "permission": binding.permission.to_payload(),
                "selected_model_id": selected_model_id,
                "feel_no_pain_source": binding.source.to_payload(),
            },
        )
        executed_sources.append(binding.source)
    base_sources = mortal_wound_feel_no_pain_sources(
        state=state,
        model_instance_id=selected_model_id,
        destruction_evidence=destruction_evidence,
        include_allocation_permissions=False,
    )
    resolved_sources = tuple(sorted((*base_sources, *executed_sources), key=lambda s: s.source_id))
    if resolved_sources != sources:
        raise GameLifecycleError("Mortal-wound allocation prevention execution drift.")
    return occurrence, resolved_sources, decline_allowed
