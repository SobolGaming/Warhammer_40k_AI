"""Per-model modifier subsets before the owning Fall Back proposal rolls dice."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.movement_model import DesperateEscapeRequirement


def prepare_desperate_escape_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    movement_proposal_result_id: str,
    requirements: tuple[DesperateEscapeRequirement, ...],
    modifiers: tuple[RollModifier, ...],
) -> LifecycleStatus | None:
    for requirement in requirements:
        selection = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            occurrence_id=desperate_escape_modifier_occurrence(
                movement_proposal_result_id, requirement.requirement_id
            ),
            subject=ModifierEvaluationSubject(
                unit_instance_id=rules_unit_view_by_id(
                    state=state, unit_instance_id=requirement.unit_instance_id
                ).unit_instance_id,
                model_instance_id=requirement.model_instance_id,
                kind=ModifierIgnoreKind.DESPERATE_ESCAPE_ROLL,
            ),
            modifiers=modifiers,
            source_context={
                "continuation": "movement_proposal",
                "movement_proposal_result_id": movement_proposal_result_id,
            },
        )
        if selection.pending_status is not None:
            return selection.pending_status
    return None


def desperate_escape_modifier_occurrence(result_id: str, requirement_id: str) -> str:
    return f"{result_id}:desperate-escape:{requirement_id}"
