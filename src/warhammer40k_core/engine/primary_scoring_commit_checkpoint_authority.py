from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    validate_primary_mission_boundary_checkpoint_runtime_source_registry,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    validate_primary_mission_boundary_physical_authority,
)
from warhammer40k_core.engine.primary_mission_boundary_unit_history_authority import (
    validate_primary_mission_boundary_unit_history_authority,
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    validate_primary_mission_oc_effect_event_authority,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    build_primary_scoring_spatial_evidence,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


def authenticate_primary_scoring_commit_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Treat one scoring-commit checkpoint as an authenticated physical authority boundary."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring-commit authority requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Primary scoring-commit authority requires EventRecord history.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError(
            "Primary scoring-commit authority requires DecisionRecord history."
        )
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Primary scoring-commit authority requires a typed checkpoint.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary scoring-commit authority requires RuntimeModifierRegistry."
        )
    validate_primary_mission_boundary_physical_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_boundary_unit_history_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_boundary_checkpoint_runtime_source_registry(
        checkpoint=checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    validate_primary_mission_oc_effect_event_authority(
        state=state,
        event_records=event_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )


def validate_primary_scoring_spatial_rows_from_checkpoint(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
    model_placements: tuple[ModelPlacement, ...],
) -> None:
    """Rebuild spatial witnesses from authenticated scoring-commit placements."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring spatial checkpoint rebuild requires GameState.")
    if type(evidence) is not PrimaryScoringStateEvidence:
        raise GameLifecycleError(
            "Primary scoring spatial checkpoint rebuild requires typed evidence."
        )
    record = next(
        stored
        for stored in state.objective_control_records
        if stored.record_id == evidence.objective_control_record_id
    )
    expected = tuple(
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id=row.player_id,
            record=record,
            requested_condition_ids=row.requested_condition_ids,
            model_placements=model_placements,
        )
        for row in evidence.primary_scoring_spatial_evidence_by_player_id
    )
    if evidence.primary_scoring_spatial_evidence_by_player_id != expected:
        raise GameLifecycleError(
            "Primary scoring spatial evidence drifted from the authenticated scoring checkpoint."
        )


__all__ = (
    "authenticate_primary_scoring_commit_checkpoint",
    "validate_primary_scoring_spatial_rows_from_checkpoint",
)
