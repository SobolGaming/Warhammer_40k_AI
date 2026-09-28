"""An immutable OC evaluation passed only through its owning calculation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
)
from warhammer40k_core.engine.nonattack_profile_modifiers import (
    selected_nonattack_profile_modifiers,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.runtime_modifiers import (
        ObjectiveControlModifierContext,
        RuntimeModifierRegistry,
    )


@dataclass(frozen=True, slots=True)
class ObjectiveControlSelectionScope:
    occurrence_id: str
    traces: tuple[tuple[str, CharacteristicModifierTrace], ...]
    decision_records: tuple[DecisionRecord, ...]

    def __post_init__(self) -> None:
        if type(self.occurrence_id) is not str or not self.occurrence_id:
            raise GameLifecycleError("OC evaluation scope requires an occurrence.")
        if type(self.traces) is not tuple or len(dict(self.traces)) != len(self.traces):
            raise GameLifecycleError("OC evaluation scope model inventory drifted.")
        if any(
            type(trace) is not CharacteristicModifierTrace
            or trace.characteristic is not Characteristic.OBJECTIVE_CONTROL
            for _, trace in self.traces
        ):
            raise GameLifecycleError("OC evaluation scope requires typed OC traces.")

    def includes(self, model_instance_id: str) -> bool:
        return any(identifier == model_instance_id for identifier, _trace in self.traces)

    def resolve(
        self,
        *,
        registry: RuntimeModifierRegistry,
        context: ObjectiveControlModifierContext,
        value: CharacteristicValue,
    ) -> CharacteristicValue:
        traces = dict(self.traces)
        if context.model_instance_id not in traces:
            raise GameLifecycleError("OC model is outside the selected evaluation scope.")
        trace = traces[context.model_instance_id]
        source_trace = value.modifier_trace
        source = value.final if source_trace is None else source_trace.source_value
        inventory = (
            *(() if source_trace is None else source_trace.modifiers),
            *registry.objective_control_operations(context, value=value),
        )
        if source != trace.source_value or inventory != trace.modifiers:
            raise GameLifecycleError("OC evaluation scope source or modifiers drifted.")
        unit = rules_unit_view_by_id(state=context.state, unit_instance_id=context.unit_instance_id)
        selected = selected_nonattack_profile_modifiers(
            decision_records=self.decision_records,
            occurrence_id=f"{self.occurrence_id}:objective-control:{context.model_instance_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=context.model_instance_id,
                kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
            ),
            modifiers=inventory,
            source_trace=source_trace,
        )
        ignored = tuple(sorted(item.modifier_id for item in inventory if item not in selected))
        if ignored != trace.ignored_modifier_ids:
            raise GameLifecycleError("OC evaluation scope selection history drifted.")
        return trace.value()


def registry_with_objective_control_scope(
    registry: RuntimeModifierRegistry,
    *,
    occurrence_id: str,
    traces: tuple[tuple[str, CharacteristicModifierTrace], ...],
    decision_records: tuple[DecisionRecord, ...],
) -> RuntimeModifierRegistry:
    if registry.objective_control_selection_scope is not None:
        raise GameLifecycleError("OC evaluation scope cannot be implicitly replaced.")
    if not traces:
        return registry
    return replace(
        registry,
        objective_control_selection_scope=ObjectiveControlSelectionScope(
            occurrence_id=occurrence_id,
            traces=traces,
            decision_records=decision_records,
        ),
    )
