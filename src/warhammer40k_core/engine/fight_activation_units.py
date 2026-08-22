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
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    defer_attached_split_from_rule_destruction_context,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(error_factory=GameLifecycleError)


def active_fight_activation_rules_unit(
    *,
    state: GameState,
    activation: FightActivationSelection,
) -> RulesUnitView | None:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    awaiting_model_ids = fight_on_death_model_ids_for_activation(
        state=state,
        activation_result_id=activation.result_id,
    )
    rules_unit_model_ids = frozenset(model.model_instance_id for model in rules_unit.own_models)
    if awaiting_model_ids is not None and not set(awaiting_model_ids).issubset(
        rules_unit_model_ids
    ):
        raise GameLifecycleError("Fight On Death awaiting model is outside its activation unit.")
    present_model_ids = frozenset(
        model.model_instance_id
        for model in rules_unit.own_models
        if model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        )
    )
    if not present_model_ids:
        return None
    missing_alive_ids = tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.own_models
            if model.is_alive and model.model_instance_id not in present_model_ids
        )
    )
    if missing_alive_ids:
        raise GameLifecycleError("Active fight rules unit has unplaced living models.")
    if awaiting_model_ids is not None and not set(awaiting_model_ids).issubset(present_model_ids):
        raise GameLifecycleError("Fight On Death awaiting model is not placed.")
    return rules_unit


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
    "active_fight_activation_rules_unit",
    "finalize_rule_destruction_after_fight_activation",
    "reconcile_fight_phase_state_after_attached_split",
    "split_attached_rules_unit_after_fight_activation",
)
