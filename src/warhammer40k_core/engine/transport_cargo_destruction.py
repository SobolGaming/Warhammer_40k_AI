from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_cargo_membership import reserve_state_with_updated_cargo

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_validate_identifier = IdentifierValidator(GameLifecycleError)


def reconcile_transport_cargo_after_model_destruction(
    *,
    state: GameState,
    model_instance_id: str,
) -> None:
    """Remove a wholly destroyed physical component from current cargo authority.

    Attached-unit lineage remains immutable, but TransportCargoState represents the
    physical component units that are currently embarked. Start-of-phase cargo
    history remains unchanged, and an unarrived Transport's ReserveState is updated
    because its embarked IDs are also current route authority until arrival.
    """
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    component_unit_id = state.unit_instance_id_for_model(requested_model_id)
    component_units = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == component_unit_id
    )
    if len(component_units) != 1:
        raise GameLifecycleError(
            "Destroyed embarked-component reconciliation requires one physical unit."
        )
    if any(model.is_alive for model in component_units[0].own_models):
        return

    cargo_state = state.transport_cargo_state_for_embarked_unit(component_unit_id)
    if cargo_state is None:
        return
    remaining_embarked_ids = tuple(
        unit_id
        for unit_id in cargo_state.embarked_unit_instance_ids
        if unit_id != component_unit_id
    )
    updated_cargo_state = replace(
        cargo_state,
        embarked_unit_instance_ids=remaining_embarked_ids,
    )

    updated_reserve_state = reserve_state_with_updated_cargo(
        state=state, before=cargo_state, after=updated_cargo_state
    )

    state.replace_transport_cargo_state(updated_cargo_state)
    if updated_reserve_state is not None:
        state.replace_reserve_state(updated_reserve_state)


__all__ = ("reconcile_transport_cargo_after_model_destruction",)
