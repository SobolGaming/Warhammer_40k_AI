from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.attached_unit_reconciliation import (
    attached_rules_unit_split_survivor_ids,
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.fight_on_death import (
    fight_on_death_model_ids_for_activation,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightPhaseState,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    defer_attached_split_from_rule_destruction_context,
)
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(error_factory=GameLifecycleError)


def active_fight_activation_surviving_component(
    *,
    state: GameState,
    activation: FightActivationSelection,
) -> UnitInstance | None:
    rules_unit = current_placed_alive_rules_unit_view_for_identity(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    if rules_unit is None:
        return None
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight activation survivor resolution requires battlefield_state.")
    placed_model_ids = frozenset(battlefield_state.placed_model_ids())
    placed_alive_components = tuple(
        component.unit
        for component in rules_unit.components
        if any(
            model.is_alive and model.model_instance_id in placed_model_ids
            for model in component.unit.own_models
        )
    )
    original_components = tuple(
        unit
        for unit in placed_alive_components
        if unit.unit_instance_id == activation.unit_instance_id
    )
    if original_components:
        if len(original_components) != 1:
            raise GameLifecycleError(
                "Active fight activation resolves to duplicate physical components."
            )
        return original_components[0]
    if len(placed_alive_components) != 1:
        raise GameLifecycleError(
            "Active fight activation requires exactly one surviving placed physical component."
        )
    return placed_alive_components[0]


def active_fight_on_death_melee_component(
    *,
    state: GameState,
    activation: FightActivationSelection,
) -> UnitInstance | None:
    awaiting_model_ids = fight_on_death_model_ids_for_activation(
        state=state,
        activation_result_id=activation.result_id,
    )
    if awaiting_model_ids is None:
        return None
    if not awaiting_model_ids:
        raise GameLifecycleError("Fight On Death activation has no awaiting models.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight On Death melee activation requires battlefield_state.")
    placed_model_ids = frozenset(battlefield_state.placed_model_ids())
    if not set(awaiting_model_ids).issubset(placed_model_ids):
        raise GameLifecycleError("Fight On Death awaiting model is not placed.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    awaiting_model_id_set = frozenset(awaiting_model_ids)
    matching_components = tuple(
        component.unit
        for component in rules_unit.components
        if awaiting_model_id_set.intersection(
            model.model_instance_id for model in component.unit.own_models
        )
    )
    matched_model_ids = frozenset(
        model.model_instance_id
        for unit in matching_components
        for model in unit.own_models
        if model.model_instance_id in awaiting_model_id_set
    )
    if matched_model_ids != awaiting_model_id_set:
        raise GameLifecycleError("Fight On Death awaiting model is outside its activation unit.")
    if len(matching_components) != 1:
        raise GameLifecycleError(
            "Fight On Death melee activation requires exactly one physical component."
        )
    return matching_components[0]


def record_active_fight_activation_unit_alias(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    activation: FightActivationSelection,
    unit_instance_id: str,
) -> FightPhaseState:
    if fight_state.active_activation != activation:
        raise GameLifecycleError("Fight activation unit alias active activation drift.")
    selected_unit_ids = fight_state.fight_order_state.selected_to_fight_unit_ids
    if activation.unit_instance_id not in selected_unit_ids:
        if (
            fight_on_death_model_ids_for_activation(
                state=state,
                activation_result_id=activation.result_id,
            )
            is None
        ):
            raise GameLifecycleError(
                "Fight activation unit alias source was not selected to fight."
            )
        return fight_state
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if requested_unit_id in selected_unit_ids:
        raise GameLifecycleError("Fight activation unit alias was already selected to fight.")
    updated = replace(
        fight_state,
        fight_order_state=replace(
            fight_state.fight_order_state,
            selected_to_fight_unit_ids=(*selected_unit_ids, requested_unit_id),
        ),
    )
    state.replace_fight_phase_state(updated)
    return updated


def reconcile_fight_phase_state_after_attached_split(
    *,
    state: GameState,
    attached_unit_instance_id: str,
    surviving_unit_instance_ids: tuple[str, ...],
) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None or not surviving_unit_instance_ids:
        return
    attached_unit_id = _validate_identifier(
        "attached_unit_instance_id",
        attached_unit_instance_id,
    )
    survivor_ids = tuple(
        sorted(
            _validate_identifier("surviving_unit_instance_id", unit_id)
            for unit_id in surviving_unit_instance_ids
        )
    )
    if len(set(survivor_ids)) != len(survivor_ids):
        raise GameLifecycleError("Attached-unit split survivor ids must be unique.")
    active_activation = fight_state.active_activation
    if active_activation is not None and active_activation.unit_instance_id == attached_unit_id:
        raise GameLifecycleError("Attached-unit split cannot replace an active fight identity.")
    order_state = fight_state.fight_order_state
    fights_first_sources = tuple(
        replace(source, unit_instance_id=survivor_id)
        for source in order_state.fights_first_registry.sources
        for survivor_id in (
            survivor_ids
            if source.unit_instance_id == attached_unit_id
            else (source.unit_instance_id,)
        )
    )
    updated_order_state = replace(
        order_state,
        engaged_at_fight_step_start_unit_ids=_replace_fight_unit_identity(
            order_state.engaged_at_fight_step_start_unit_ids,
            attached_unit_id=attached_unit_id,
            survivor_ids=survivor_ids,
        ),
        selected_to_fight_unit_ids=_replace_fight_unit_identity(
            order_state.selected_to_fight_unit_ids,
            attached_unit_id=attached_unit_id,
            survivor_ids=survivor_ids,
        ),
        eligible_passes=tuple(
            replace(
                eligible_pass,
                eligible_unit_ids=_replace_fight_unit_identity(
                    eligible_pass.eligible_unit_ids,
                    attached_unit_id=attached_unit_id,
                    survivor_ids=survivor_ids,
                ),
            )
            for eligible_pass in order_state.eligible_passes
        ),
        fights_first_registry=replace(
            order_state.fights_first_registry,
            sources=fights_first_sources,
        ),
    )
    pile_in_state = fight_state.pile_in_state
    updated_pile_in_state = (
        None
        if pile_in_state is None
        else replace(
            pile_in_state,
            completed_unit_ids=_replace_fight_unit_identity(
                pile_in_state.completed_unit_ids,
                attached_unit_id=attached_unit_id,
                survivor_ids=survivor_ids,
            ),
        )
    )
    consolidate_state = fight_state.consolidate_state
    updated_consolidate_state = (
        None
        if consolidate_state is None
        else replace(
            consolidate_state,
            completed_unit_ids=_replace_fight_unit_identity(
                consolidate_state.completed_unit_ids,
                attached_unit_id=attached_unit_id,
                survivor_ids=survivor_ids,
            ),
        )
    )
    state.replace_fight_phase_state(
        replace(
            fight_state,
            fight_order_state=updated_order_state,
            pile_in_state=updated_pile_in_state,
            consolidate_state=updated_consolidate_state,
        )
    )


def split_attached_rules_unit_after_fight_activation(
    *,
    state: GameState,
    event_log: EventLog,
    rules_unit_instance_id: str,
) -> None:
    surviving_unit_ids = split_attached_rules_unit_if_required(
        state=state,
        event_log=event_log,
        rules_unit_instance_id=rules_unit_instance_id,
    )
    reconcile_fight_phase_state_after_attached_split(
        state=state,
        attached_unit_instance_id=rules_unit_instance_id,
        surviving_unit_instance_ids=surviving_unit_ids,
    )


def finalize_rule_destruction_after_fight_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    context: dict[str, JsonValue],
    rules_unit_instance_id: str,
) -> LifecycleStatus | None:
    surviving_unit_ids = attached_rules_unit_split_survivor_ids(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
    )
    split_is_deferred = defer_attached_split_from_rule_destruction_context(context)
    status = rule_model_destruction.finalize_rule_model_destruction(
        state=state,
        decisions=decisions,
        context=context,
    )
    if split_is_deferred:
        split_survivor_ids = split_attached_rules_unit_if_required(
            state=state,
            event_log=decisions.event_log,
            rules_unit_instance_id=rules_unit_instance_id,
        )
        if split_survivor_ids != surviving_unit_ids:
            raise GameLifecycleError("Deferred attached-unit split survivor drift.")
    reconcile_fight_phase_state_after_attached_split(
        state=state,
        attached_unit_instance_id=rules_unit_instance_id,
        surviving_unit_instance_ids=surviving_unit_ids,
    )
    return status


def _replace_fight_unit_identity(
    unit_instance_ids: tuple[str, ...],
    *,
    attached_unit_id: str,
    survivor_ids: tuple[str, ...],
) -> tuple[str, ...]:
    replaced: list[str] = []
    for unit_id in unit_instance_ids:
        replacements = survivor_ids if unit_id == attached_unit_id else (unit_id,)
        for replacement in replacements:
            if replacement not in replaced:
                replaced.append(replacement)
    return tuple(replaced)


__all__ = (
    "active_fight_activation_surviving_component",
    "active_fight_on_death_melee_component",
    "finalize_rule_destruction_after_fight_activation",
    "reconcile_fight_phase_state_after_attached_split",
    "record_active_fight_activation_unit_alias",
    "split_attached_rules_unit_after_fight_activation",
)
