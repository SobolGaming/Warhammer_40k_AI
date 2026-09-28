"""Modifier selections owned by one active movement or Charge activation."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import Modifier, RollModifier
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
    modifier_inventory_payload,
    select_modifiers,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.movement_model import PendingMovementActionSelection
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

_EFFECT_KIND = "movement_modifier_evaluation"


def _active_scope(state: GameState, unit_id: str, kind: ModifierIgnoreKind) -> str | None:
    if kind is ModifierIgnoreKind.CHARGE_ROLL:
        charge = state.charge_phase_state
        selection = None if charge is None else charge.active_selection
        if (
            state.current_battle_phase is not BattlePhase.CHARGE
            or selection is None
            or selection.unit_instance_id != unit_id
        ):
            return None
        return selection.result_id
    movement = state.movement_phase_state
    movement_selection = None if movement is None else movement.active_selection
    if (
        state.current_battle_phase is not BattlePhase.MOVEMENT
        or movement_selection is None
        or movement_selection.unit_instance_id != unit_id
    ):
        return None
    return movement_selection.result_id


def movement_evaluation_ignored_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    kind: ModifierIgnoreKind,
    modifiers: tuple[Modifier | RollModifier, ...],
    model_instance_id: str | None = None,
) -> tuple[str, ...]:
    scope = _active_scope(state, unit_instance_id, kind)
    if scope is None:
        return ()
    subject = ModifierEvaluationSubject(unit_instance_id, kind, model_instance_id)
    selections = [
        effect.effect_payload
        for effect in state.persisting_effects_for_unit(unit_instance_id)
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == _EFFECT_KIND
        and effect.effect_payload.get("activation_result_id") == scope
        and effect.effect_payload.get("subject") == subject.to_payload()
    ]
    if not selections:
        return ()
    if len(selections) != 1:
        raise GameLifecycleError("Active movement modifier evaluation is duplicated.")
    selected = selections[0]
    if selected["modifiers"] != modifier_inventory_payload(modifiers):
        raise GameLifecycleError("Active movement modifier source operations drifted.")
    identifiers = selected["ignored_modifier_ids"]
    if not isinstance(identifiers, list) or any(type(item) is not str for item in identifiers):
        raise GameLifecycleError("Active movement modifier selection IDs drifted.")
    return tuple(cast(list[str], identifiers))


def _select_and_record(
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    subject: ModifierEvaluationSubject,
    modifiers: tuple[Modifier | RollModifier, ...],
    source_context: dict[str, JsonValue],
) -> LifecycleStatus | None:
    scope = _active_scope(state, subject.unit_instance_id, subject.kind)
    if scope is None:
        raise GameLifecycleError("Movement modifier choice lacks an active owning activation.")
    occurrence_id = f"{scope}:{subject.kind.value}:{subject.model_instance_id or 'unit'}"
    selected = select_modifiers(
        state=state,
        decisions=decisions,
        ability_index=ability_index,
        occurrence_id=occurrence_id,
        subject=subject,
        modifiers=modifiers,
        source_context=source_context,
    )
    if selected.pending_status is not None:
        return selected.pending_status
    if not selected.ignored_modifier_ids:
        return None
    phase = state.current_battle_phase
    if phase is None or state.active_player_id is None:
        raise GameLifecycleError("Movement selection requires an active phase.")
    effect = PersistingEffect(
        effect_id=f"{occurrence_id}:selected",
        source_rule_id="gw-11e-core-modifiers:ignore-individual-modifiers",
        owner_player_id=rules_unit_view_by_id(
            state=state, unit_instance_id=subject.unit_instance_id
        ).owner_player_id,
        target_unit_instance_ids=(subject.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=phase,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round, phase=phase, player_id=state.active_player_id
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": _EFFECT_KIND,
                "activation_result_id": scope,
                "subject": subject.to_payload(),
                "occurrence_id": occurrence_id,
                "modifiers": modifier_inventory_payload(modifiers),
                "ignored_modifier_ids": list(selected.ignored_modifier_ids),
            }
        ),
    )
    previous = tuple(
        item for item in state.persisting_effects if item.effect_id == effect.effect_id
    )
    if previous:
        if previous != (effect,):
            raise GameLifecycleError("Movement modifier selection effect drifted.")
    else:
        state.record_persisting_effect(effect)
        decisions.event_log.append(
            "modifier_ignores_selected",
            validate_json_value(
                {
                    "occurrence_id": occurrence_id,
                    "modifier_ignore_effect": effect.to_payload(),
                }
            ),
        )
    return None


def prepare_movement_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    ability_index: AbilityCatalogIndex,
    registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.movement_budget_modifiers import (
        MovementBudgetModifierContext,
        model_movement_characteristic,
        movement_characteristic_operations,
    )
    from warhammer40k_core.engine.phases.movement_model import MovementPhaseActionKind
    from warhammer40k_core.engine.runtime_modifiers import AdvanceRollModifierContext

    unit = rules_unit_view_by_id(state=state, unit_instance_id=pending.unit_instance_id)
    context: dict[str, JsonValue] = {
        "continuation": "phase",
        "action": validate_json_value(pending.to_payload()),
    }
    for model in unit.alive_models():
        operations = movement_characteristic_operations(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                movement=model_movement_characteristic(model),
            ),
            bindings=registry.movement_budget_modifier_bindings,
        )
        status = _select_and_record(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            subject=ModifierEvaluationSubject(
                unit.unit_instance_id,
                ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
                model.model_instance_id,
            ),
            modifiers=operations,
            source_context=context,
        )
        if status is not None:
            return status
    if pending.movement_phase_action is MovementPhaseActionKind.ADVANCE:
        operations_roll = registry.advance_roll_modifiers(
            AdvanceRollModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                current_roll_modifiers=(),
            ),
            apply_selection=False,
        )
        return _select_and_record(
            state=state,
            decisions=decisions,
            ability_index=ability_index,
            subject=ModifierEvaluationSubject(
                unit.unit_instance_id, ModifierIgnoreKind.ADVANCE_ROLL
            ),
            modifiers=operations_roll,
            source_context=context,
        )
    return None


def prepare_charge_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    unit_instance_id: str,
    modifiers: tuple[RollModifier, ...],
    source_context: dict[str, JsonValue],
) -> LifecycleStatus | None:
    return _select_and_record(
        state=state,
        decisions=decisions,
        ability_index=ability_index,
        subject=ModifierEvaluationSubject(unit_instance_id, ModifierIgnoreKind.CHARGE_ROLL),
        modifiers=modifiers,
        source_context=source_context,
    )
