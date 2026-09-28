"""Occurrence-scoped OC selections prepared before control and scoring queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers
from warhammer40k_core.engine.nonattack_profile_modifiers import (
    selected_nonattack_profile_modifiers,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    model_objective_control_characteristic,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.random_objective_control import prepare_objective_control
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import ObjectiveControlModifierContext


@dataclass(frozen=True, slots=True)
class ObjectiveControlModifierEvaluation:
    context: ObjectiveControlContext
    pending_status: LifecycleStatus | None = None


def evaluate_objective_control_modifiers(
    context: ObjectiveControlContext,
    *,
    decisions: DecisionController,
    occurrence_id: str,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    additional_subjects: tuple[tuple[str, str], ...] = (),
    source_context: dict[str, JsonValue] | None = None,
    prepare_random_profiles: bool = True,
) -> ObjectiveControlModifierEvaluation:
    """Prepare each contributing model once; querying the result is pure."""
    state = context.state
    if state is None:
        raise GameLifecycleError("OC modifier choices require authoritative GameState.")
    if prepare_random_profiles:
        context = prepare_objective_control(context, decisions=decisions, scope_id=occurrence_id)
    contributors = {
        contribution.model_instance_id: contribution.unit_instance_id
        for result in resolve_objective_control(context).results
        for contribution in result.contributors
        if not contribution.battle_shocked
    }
    contributors.update({model_id: unit_id for unit_id, model_id in additional_subjects})
    traces: list[tuple[str, CharacteristicModifierTrace]] = []
    for model_id, unit_id in sorted(contributors.items()):
        unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        source, operations = _model_inventory(context, model_id=model_id, unit=unit)
        if not operations:
            continue
        ability_index = ability_indexes_by_player_id.get(unit.owner_player_id)
        if ability_index is None:
            raise GameLifecycleError("OC contributor lacks loaded ability authority.")
        selected = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            occurrence_id=f"{occurrence_id}:objective-control:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
            ),
            modifiers=operations,
            source_context=source_context
            if source_context is not None
            else {
                "continuation": "phase",
                "source_kind": "objective_control",
                "boundary_id": occurrence_id,
                "timing": context.timing.value,
                "phase": context.phase,
            },
        )
        if selected.pending_status is not None:
            return ObjectiveControlModifierEvaluation(context, selected.pending_status)
        retained = selected_nonattack_profile_modifiers(
            decision_records=decisions.records,
            occurrence_id=f"{occurrence_id}:objective-control:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
            ),
            modifiers=operations,
            source_trace=model_objective_control_characteristic(
                unit.model_by_id(model_id), battle_shocked=False
            ).modifier_trace,
        )
        traces.append(
            (
                model_id,
                CharacteristicModifierTrace(
                    characteristic=Characteristic.OBJECTIVE_CONTROL,
                    source_value=source,
                    modifiers=operations,
                    ignored_modifier_ids=tuple(
                        sorted(item.modifier_id for item in operations if item not in retained)
                    ),
                ),
            )
        )
    from warhammer40k_core.engine.objective_control_selection_scope import (
        registry_with_objective_control_scope,
    )

    registry = registry_with_objective_control_scope(
        context.runtime_modifier_registry,
        occurrence_id=occurrence_id,
        traces=tuple(traces),
        decision_records=decisions.records,
    )
    return ObjectiveControlModifierEvaluation(
        replace(
            context,
            runtime_modifier_registry=registry,
            modifier_traces=tuple(traces),
            modifier_occurrence_id=occurrence_id if traces else None,
            modifier_decision_records=decisions.records if traces else (),
        )
    )


def validate_objective_control_modifier_traces(context: ObjectiveControlContext) -> None:
    """Authenticate selected operations against the explicit occurrence and its decisions."""
    if not context.modifier_traces:
        if context.modifier_occurrence_id is not None or context.modifier_decision_records:
            raise GameLifecycleError("Empty OC modifier evaluation has unexpected evidence.")
        return
    state = context.state
    if state is None or context.modifier_occurrence_id is None:
        raise GameLifecycleError(
            "Selected OC operations require live source and occurrence authority."
        )
    for model_id, trace in context.modifier_traces:
        unit = next(
            view
            for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
            if model_id in {model.model_instance_id for model in view.own_models}
        )
        model = unit.model_by_id(model_id)
        original = model_objective_control_characteristic(model, battle_shocked=False)
        source_trace = original.modifier_trace
        source = original.final if source_trace is None else source_trace.source_value
        inventory = (
            *(() if source_trace is None else source_trace.modifiers),
            *context.runtime_modifier_registry.objective_control_operations(
                ObjectiveControlModifierContext(
                    state=state,
                    unit_instance_id=unit.component_unit_id_for_model(model_id),
                    model_instance_id=model_id,
                    base_objective_control=original.final,
                    current_objective_control=original.final,
                ),
                value=original,
            ),
        )
        if trace.source_value != source or trace.modifiers != inventory:
            raise GameLifecycleError("Selected OC source or operation inventory drifted.")
        selected = selected_nonattack_profile_modifiers(
            decision_records=context.modifier_decision_records,
            occurrence_id=f"{context.modifier_occurrence_id}:objective-control:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
            ),
            modifiers=inventory,
            source_trace=source_trace,
        )
        ignored = tuple(sorted(item.modifier_id for item in inventory if item not in selected))
        if ignored != trace.ignored_modifier_ids:
            raise GameLifecycleError("Selected OC operation history drifted.")


def require_objective_control_without_choices(context: ObjectiveControlContext) -> None:
    """A convenience snapshot without a decision owner cannot skip player choices."""
    state = context.state
    if state is None:
        raise GameLifecycleError("OC source validation requires authoritative state.")
    subjects = {
        (contribution.unit_instance_id, contribution.model_instance_id)
        for result in resolve_objective_control(context).results
        for contribution in result.contributors
        if not contribution.battle_shocked
    }
    for unit_id, model_id in sorted(subjects):
        unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        _source, operations = _model_inventory(context, model_id=model_id, unit=unit)
        if operations and modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=context.runtime_modifier_registry.modifier_permission_index(
                unit.owner_player_id
            ),
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
        ):
            raise GameLifecycleError(
                "Objective Control modifier choices require DecisionController."
            )


def _model_inventory(
    context: ObjectiveControlContext, *, model_id: str, unit: RulesUnitView
) -> tuple[int, tuple[Modifier, ...]]:
    state = context.state
    if state is None:
        raise GameLifecycleError("OC source inventory requires authoritative state.")
    value = model_objective_control_characteristic(unit.model_by_id(model_id), battle_shocked=False)
    existing = value.modifier_trace
    source = value.final if existing is None else existing.source_value
    operations = (
        *(() if existing is None else existing.modifiers),
        *context.runtime_modifier_registry.objective_control_operations(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=unit.component_unit_id_for_model(model_id),
                model_instance_id=model_id,
                base_objective_control=value.final,
                current_objective_control=value.final,
            ),
            value=value,
        ),
    )
    return source, operations
