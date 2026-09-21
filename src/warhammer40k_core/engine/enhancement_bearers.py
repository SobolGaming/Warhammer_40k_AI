"""Resolve roster enhancement provenance to the current bearer model owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    EnhancementAssignment,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.roster_model_identity import selected_roster_model
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactoryError, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeEnhancementAssignment
    from warhammer40k_core.engine.game_state import GameState


def runtime_assignment_for_current_bearer(
    *,
    state: GameState,
    player_id: str,
    assignments: tuple[RuntimeEnhancementAssignment, ...],
    unit_instance_id: str,
) -> RuntimeEnhancementAssignment | None:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise GameLifecycleError("Enhancement bearer player army is missing.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Enhancement bearer rules-unit owner drift.")
    matches = tuple(
        assignment
        for assignment in assignments
        if assignment.player_id == army.player_id
        and current_enhancement_bearer(
            army, source_unit_instance_id=assignment.bearer_unit_instance_id
        ).unit_instance_id
        in rules_unit.component_unit_instance_ids
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise GameLifecycleError("Enhancement bearer assignment is ambiguous.")
    return matches[0]


def enhancement_bearer_unit(
    army: ArmyDefinition, *, assignment: EnhancementAssignment
) -> UnitInstance:
    if assignment not in army.enhancement_assignments:
        raise GameLifecycleError("Enhancement assignment is not in the owning army.")
    return current_enhancement_bearer(
        army, source_unit_instance_id=f"{army.army_id}:{assignment.target_unit_selection_id}"
    )


def current_enhancement_bearer(
    army: ArmyDefinition, *, source_unit_instance_id: str
) -> UnitInstance:
    """Keep the explicitly selected model bearer stable across partitions.

    Source inventory supplies identity only. The returned unit and model state
    always come from the live inventory authenticated by ArmyDefinition lineage.
    """
    try:
        source = army.source_unit_by_id(source_unit_instance_id)
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Enhancement assignment references unknown bearer unit.") from exc
    assignments = tuple(
        row
        for row in army.enhancement_assignments
        if f"{army.army_id}:{row.target_unit_selection_id}" == source_unit_instance_id
    )
    if len(assignments) != 1:
        raise GameLifecycleError("Enhancement source requires a unique roster assignment.")
    assignment = assignments[0]
    try:
        bearer_model_id = selected_roster_model(
            source,
            model_profile_id=assignment.model_profile_id,
            model_index=assignment.model_index,
        ).model_instance_id
    except UnitFactoryError as exc:
        raise GameLifecycleError(
            "Enhancement selected model is absent from source inventory."
        ) from exc
    matches = tuple(
        unit
        for unit in army.units
        if unit.source_unit_instance_id == source_unit_instance_id
        and bearer_model_id in unit.own_model_ids()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Enhancement bearer lacks unique current model ownership.")
    return matches[0]


def enhancement_bearer_model(
    army: ArmyDefinition, *, assignment: EnhancementAssignment
) -> ModelInstance:
    unit = enhancement_bearer_unit(army, assignment=assignment)
    source = army.source_unit_by_id(f"{army.army_id}:{assignment.target_unit_selection_id}")
    model_id = selected_roster_model(
        source,
        model_profile_id=assignment.model_profile_id,
        model_index=assignment.model_index,
    ).model_instance_id
    return unit.own_model_by_id(model_id)
