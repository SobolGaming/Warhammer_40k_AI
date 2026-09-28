"""Explicit, resumable modifier choices at non-attack test boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier, RollModifier
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_leadership_modifiers import (
    catalog_leadership_modifiers_for_rules_unit,
)
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
    select_modifiers,
)
from warhammer40k_core.engine.nonattack_profile_modifiers import (
    selected_nonattack_profile_modifiers,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.profile_modifiers import resolved_profile_with_modifier_trace
from warhammer40k_core.engine.random_profile_evaluation import evaluate_unit_profile_characteristics
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class LeadershipModifierEvaluation:
    """No target or dice may be consumed while a choice is pending."""

    characteristic_traces: tuple[tuple[str, CharacteristicModifierTrace], ...]
    roll_modifiers: tuple[RollModifier, ...]
    pending_status: LifecycleStatus | None

    @property
    def leadership_target(self) -> int:
        if self.pending_status is not None or not self.characteristic_traces:
            raise GameLifecycleError("Leadership requires completed modifier choices.")
        return min(trace.resolve().final for _model_id, trace in self.characteristic_traces)


def evaluate_leadership_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    occurrence_id: str,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    roll_modifiers: tuple[RollModifier, ...],
    roll_kind: ModifierIgnoreKind = ModifierIgnoreKind.LEADERSHIP_ROLL,
    model_instance_ids: tuple[str, ...] | None = None,
    roll_model_instance_id: str | None = None,
    source_context: dict[str, JsonValue],
) -> LeadershipModifierEvaluation:
    """Resolve each model's characteristic, then the unit's test-roll inventory."""
    if roll_kind not in {ModifierIgnoreKind.LEADERSHIP_ROLL, ModifierIgnoreKind.BATTLE_SHOCK_ROLL}:
        raise GameLifecycleError("Leadership evaluation requires a Leadership test roll kind.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    model_ids = model_instance_ids
    if model_ids is None:
        model_ids = tuple(model.model_instance_id for model in unit.alive_models())
    if roll_model_instance_id is not None and roll_model_instance_id not in model_ids:
        raise GameLifecycleError("Leadership roll model is outside the evaluated test models.")
    if not model_ids:
        raise GameLifecycleError("Leadership evaluation requires surviving test models.")
    evaluate_unit_profile_characteristics(
        state=state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        scope_id=occurrence_id,
        characteristics=(Characteristic.LEADERSHIP,),
        model_instance_ids=model_ids,
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    traces: list[tuple[str, CharacteristicModifierTrace]] = []
    for model_id, source, operations in leadership_modifier_inventories(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_ids=model_ids,
    ):
        selection = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            occurrence_id=f"{occurrence_id}:leadership:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC,
            ),
            modifiers=operations,
            source_context=source_context,
        )
        if selection.pending_status is not None:
            return LeadershipModifierEvaluation(tuple(traces), (), selection.pending_status)
        selected = selected_nonattack_profile_modifiers(
            decision_records=decisions.records,
            occurrence_id=f"{occurrence_id}:leadership:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC,
            ),
            modifiers=operations,
            source_trace=resolved_profile_with_modifier_trace(
                unit.model_by_id(model_id).characteristic(Characteristic.LEADERSHIP)
            ).modifier_trace,
        )
        trace = CharacteristicModifierTrace(
            characteristic=Characteristic.LEADERSHIP,
            source_value=source,
            modifiers=operations,
            ignored_modifier_ids=tuple(
                sorted(item.modifier_id for item in operations if item not in selected)
            ),
        )
        traces.append((model_id, trace))
    selected_roll = select_modifiers(
        state=state,
        decisions=decisions,
        ability_index=ability_index,
        occurrence_id=f"{occurrence_id}:test-roll",
        subject=ModifierEvaluationSubject(
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=roll_model_instance_id,
            kind=roll_kind,
        ),
        modifiers=roll_modifiers,
        source_context=source_context,
    )
    return LeadershipModifierEvaluation(
        tuple(traces),
        selected_roll.modifiers,
        selected_roll.pending_status,
    )


def leadership_modifier_inventories(
    *,
    state: GameState,
    unit_instance_id: str,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    model_instance_ids: tuple[str, ...],
) -> tuple[tuple[str, int, tuple[Modifier, ...]], ...]:
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    inventories: list[tuple[str, int, tuple[Modifier, ...]]] = []
    source_model_ids = tuple(
        sorted(
            {
                *model_instance_ids,
                *(
                    model_id
                    for component in unit.components
                    for model_id in catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                        state=state,
                        unit=component.unit,
                    )
                ),
            }
        )
    )
    catalog_modifiers = catalog_leadership_modifiers_for_rules_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=source_model_ids,
    )
    for model_id in sorted(model_instance_ids):
        model = unit.model_by_id(model_id)
        profile = model.characteristic(Characteristic.LEADERSHIP)
        characteristic = resolved_profile_with_modifier_trace(profile)
        existing_trace = characteristic.modifier_trace
        source = characteristic.final if existing_trace is None else existing_trace.source_value
        profile_modifiers = () if existing_trace is None else existing_trace.modifiers
        context = UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=characteristic.final,
            current_value=characteristic.final,
        )
        operations = (
            *profile_modifiers,
            *catalog_modifiers,
            *runtime_modifier_registry.unit_characteristic_operations(context),
        )
        inventories.append((model_id, source, operations))
    return tuple(inventories)


def leadership_target_from_modifier_history(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    unit_instance_id: str,
    occurrence_id: str,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    model_instance_ids: tuple[str, ...],
) -> int:
    targets: list[int] = []
    for model_id, source, operations in leadership_modifier_inventories(
        state=state,
        unit_instance_id=unit_instance_id,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_ids=model_instance_ids,
    ):
        selected = selected_nonattack_profile_modifiers(
            decision_records=decision_records,
            occurrence_id=f"{occurrence_id}:leadership:{model_id}",
            subject=ModifierEvaluationSubject(
                unit_instance_id=unit_instance_id,
                model_instance_id=model_id,
                kind=ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC,
            ),
            modifiers=operations,
            source_trace=resolved_profile_with_modifier_trace(
                rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
                .model_by_id(model_id)
                .characteristic(Characteristic.LEADERSHIP)
            ).modifier_trace,
        )
        targets.append(
            CharacteristicModifierTrace(
                Characteristic.LEADERSHIP,
                source,
                selected,
            )
            .resolve()
            .final
        )
    if not targets:
        raise GameLifecycleError("Historical Leadership requires current test models.")
    return min(targets)
