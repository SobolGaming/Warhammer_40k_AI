from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    retained_destruction_for_model,
    retained_destructions,
    validate_retained_placement,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


def retained_model_ids(*, state: GameState) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Retained destruction presence snapshot requires battlefield_state."
        )
    retained = tuple(record for record in retained_destructions(state=state) if record.is_retained)
    for record in retained:
        validate_retained_placement(state=state, record=record)
    return tuple(sorted(record.model_instance_id for record in retained))


def model_is_present_on_battlefield(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    model, _unit = _model_and_unit_by_id(state=state, model_instance_id=requested_model_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Battlefield presence query requires battlefield_state.")
    if battlefield.model_placement_or_none(requested_model_id) is None:
        return False
    retained = retained_destruction_for_model(state=state, model_instance_id=requested_model_id)
    if retained is not None and retained.is_retained:
        validate_retained_placement(state=state, record=retained)
        return True
    return model.is_alive


def retained_model_ids_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    model_ids = {
        model.model_instance_id
        for component in view.components
        for model in component.unit.own_models
    }
    return tuple(model_id for model_id in retained_model_ids(state=state) if model_id in model_ids)


def retained_pending_rule_source_effect_ids(*, state: GameState) -> tuple[str, ...]:
    source_effect_ids: set[str] = set()
    for record in retained_destructions(state=state):
        if record.owner_kind is not DestructionOwnerKind.RULE:
            continue
        values = record.owner_context.get("source_effect_ids")
        if not isinstance(values, list):
            raise GameLifecycleError("Retained rule destruction source liabilities are invalid.")
        source_effect_ids.update(
            _validate_identifier("Retained rule destruction source_effect_id", value)
            for value in values
        )
    return tuple(sorted(source_effect_ids))


def _model_and_unit_by_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[ModelInstance, UnitInstance]:
    model, unit, _army_id, _player_id = _model_unit_and_owner_by_id(
        state=state,
        model_instance_id=model_instance_id,
    )
    return model, unit


def _model_unit_and_owner_by_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[ModelInstance, UnitInstance, str, str]:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model, unit, army.army_id, army.player_id
    raise GameLifecycleError("Retained destruction model_instance_id is unknown.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
