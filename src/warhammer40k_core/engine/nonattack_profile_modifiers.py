"""Preserve profile selections until an owning occurrence records a new subset."""

from warhammer40k_core.core.modifiers import Modifier
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
    selected_modifiers_for_occurrence,
    selection_history,
)


def selected_nonattack_profile_modifiers(
    *,
    decision_records: tuple[DecisionRecord, ...],
    occurrence_id: str,
    subject: ModifierEvaluationSubject,
    modifiers: tuple[Modifier, ...],
    source_trace: CharacteristicModifierTrace | None,
) -> tuple[Modifier, ...]:
    selected = selected_modifiers_for_occurrence(
        decision_records=decision_records,
        occurrence_id=occurrence_id,
        subject=subject,
        modifiers=modifiers,
    )
    if source_trace is None or not source_trace.ignored_modifier_ids:
        return selected
    if (
        selection_history(
            decision_records=decision_records, occurrence_id=occurrence_id, subject=subject
        )
        is not None
    ):
        return selected
    return tuple(
        modifier
        for modifier in selected
        if modifier.modifier_id not in source_trace.ignored_modifier_ids
    )
