"""Validate explicit OC subset evidence carried by an immutable boundary checkpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
)
from warhammer40k_core.engine.nonattack_profile_modifiers import (
    selected_nonattack_profile_modifiers,
)
from warhammer40k_core.engine.objective_control_selection_scope import (
    registry_with_objective_control_scope,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.profile_modifiers import resolved_profile_with_modifier_trace
from warhammer40k_core.engine.profile_snapshot import profile_snapshot_from_json

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
        PrimaryMissionBoundaryCheckpoint,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def validate_checkpoint_modifier_selections(
    *,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    decision_records: tuple[DecisionRecord, ...],
) -> tuple[tuple[str, CharacteristicModifierTrace], ...]:
    traces: list[tuple[str, CharacteristicModifierTrace]] = []
    for row in checkpoint.model_states:
        value = profile_snapshot_from_json(row.resolved_objective_control_json)
        if not isinstance(value, CharacteristicValue) or value.modifier_trace is None:
            continue
        trace = value.modifier_trace
        scope_id = checkpoint.objective_control_modifier_scope_id
        if scope_id is None:
            if trace.ignored_modifier_ids:
                raise GameLifecycleError("OC checkpoint subset lacks its evaluation occurrence.")
            continue
        selected = selected_nonattack_profile_modifiers(
            decision_records=decision_records,
            occurrence_id=f"{scope_id}:objective-control:{row.model_instance_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=row.rules_unit_instance_id,
                model_instance_id=row.model_instance_id,
                kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
            ),
            modifiers=trace.modifiers,
            source_trace=resolved_profile_with_modifier_trace(
                profile_snapshot_from_json(row.source_objective_control_json)
            ).modifier_trace,
        )
        ignored = tuple(
            sorted(item.modifier_id for item in trace.modifiers if item not in selected)
        )
        if ignored != trace.ignored_modifier_ids:
            raise GameLifecycleError("OC checkpoint modifier subset differs from its decisions.")
        traces.append((row.model_instance_id, trace))
    return tuple(traces)


def registry_for_checkpoint_selections(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    decision_records: tuple[DecisionRecord, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> RuntimeModifierRegistry:
    traces = validate_checkpoint_modifier_selections(
        checkpoint=checkpoint, decision_records=decision_records
    )
    scope_id = checkpoint.objective_control_modifier_scope_id
    if scope_id is None:
        return runtime_modifier_registry
    existing = runtime_modifier_registry.objective_control_selection_scope
    if existing is not None:
        if existing.occurrence_id != scope_id:
            raise GameLifecycleError("OC checkpoint received a different evaluation scope.")
        return runtime_modifier_registry
    if state.game_id != checkpoint.game_id:
        raise GameLifecycleError("OC checkpoint modifier scope belongs to another game.")
    return registry_with_objective_control_scope(
        runtime_modifier_registry,
        occurrence_id=scope_id,
        traces=traces,
        decision_records=decision_records,
    )
