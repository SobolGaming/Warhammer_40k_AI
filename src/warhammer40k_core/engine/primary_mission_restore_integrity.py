from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import objective_control_record_authority as _ocra
from warhammer40k_core.engine import primary_mission_action_integrity as _pmai
from warhammer40k_core.engine import primary_mission_boundary_checkpoint as _pmbc
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_state_evidence_integrity import (
    validate_primary_scoring_position_event_authority,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    runtime_rule_ir_authority_index_from_bundle,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_mission_restore_integrity(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    """Run the source-aware Primary Action, boundary, and scoring restore graph."""
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary mission restore integrity requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Primary mission restore integrity requires DecisionController.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary mission restore integrity requires RuntimeModifierRegistry."
        )
    if (
        runtime_content_bundle is not None
        and type(runtime_content_bundle) is not RuntimeContentBundle
    ):
        raise GameLifecycleError("Primary mission restore integrity bundle is invalid.")

    event_records = decisions.event_log.records
    decision_records = decisions.records
    rule_ir_authority_index = (
        None
        if runtime_content_bundle is None
        else runtime_rule_ir_authority_index_from_bundle(runtime_content_bundle)
    )
    faction_rule_execution_registry = (
        None
        if runtime_content_bundle is None
        else runtime_content_bundle.faction_rule_execution_registry
    )
    runtime_content_activation = (
        None if runtime_content_bundle is None else runtime_content_bundle.activation
    )
    _pmai.validate_primary_mission_action_integrity(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    _pmbc.validate_primary_mission_boundary_checkpoint_source_registry(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=decisions.queue.pending_requests,
        runtime_modifier_registry=runtime_modifier_registry,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    _ocra.validate_objective_control_record_authority_lifecycle_integrity(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        runtime_modifier_registry=runtime_modifier_registry,
        phase_end_objective_control_hook_registry=(
            None
            if runtime_content_bundle is None
            else runtime_content_bundle.phase_end_objective_control_hook_registry
        ),
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    validate_primary_scoring_position_event_authority(
        state=state,
        event_records=event_records,
    )


__all__ = ("validate_primary_mission_restore_integrity",)
