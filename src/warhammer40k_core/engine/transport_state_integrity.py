from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveStatus


def validate_transport_cargo_state_consistency(*, state: GameState) -> None:
    """Validate cargo ownership, capacity, reserve binding, and physical model state."""
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    embarked_unit_ids: set[str] = set()
    for cargo_state in state.transport_cargo_states:
        reserve_state = state.reserve_state_for_unit(cargo_state.transport_unit_instance_id)
        if reserve_state is not None and reserve_state.status is ReserveStatus.DESTROYED:
            raise GameLifecycleError(
                "transport_cargo_states destroyed reserve route must not retain current cargo."
            )
        transport = unit_by_id.get(cargo_state.transport_unit_instance_id)
        if transport is None:
            raise GameLifecycleError("transport_cargo_states transport unit is unknown.")
        if owner_by_unit_id[cargo_state.transport_unit_instance_id] != cargo_state.player_id:
            raise GameLifecycleError("transport_cargo_states player_id does not match owner.")
        if transport.datasheet_id != cargo_state.capacity_profile.transport_datasheet_id:
            raise GameLifecycleError("transport_cargo_states transport datasheet drift.")
        cargo_model_count = 0
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            embarked_unit = unit_by_id.get(embarked_unit_id)
            if embarked_unit is None:
                raise GameLifecycleError("transport_cargo_states embarked unit is unknown.")
            if owner_by_unit_id[embarked_unit_id] != cargo_state.player_id:
                raise GameLifecycleError("transport_cargo_states embarked unit owner drift.")
            if embarked_unit_id in embarked_unit_ids:
                raise GameLifecycleError("unit cannot be embarked in more than one Transport.")
            embarked_unit_ids.add(embarked_unit_id)
            if not cargo_state.capacity_profile.allows_unit(embarked_unit):
                raise GameLifecycleError("transport_cargo_states capacity profile rejects cargo.")
            if not any(model.is_alive for model in embarked_unit.own_models):
                raise GameLifecycleError(
                    "transport_cargo_states must not retain a wholly destroyed component."
                )
            cargo_model_count += sum(model.is_alive for model in embarked_unit.own_models)
        if cargo_model_count > cargo_state.capacity_profile.max_model_count:
            raise GameLifecycleError("transport_cargo_states capacity is exceeded.")
    for unarrived_route in state.reserve_states:
        if not unarrived_route.is_unarrived or not unarrived_route.embarked_unit_instance_ids:
            continue
        bound_cargo_state = state.transport_cargo_state_for_transport(
            unarrived_route.unit_instance_id
        )
        if (
            bound_cargo_state is None
            or bound_cargo_state.embarked_unit_instance_ids
            != unarrived_route.embarked_unit_instance_ids
        ):
            raise GameLifecycleError("transport_cargo_states unarrived reserve route cargo drift.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_unit_ids = {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for cargo_state in state.transport_cargo_states:
        reserve_state = state.reserve_state_for_unit(cargo_state.transport_unit_instance_id)
        unarrived_reserve_state = (
            reserve_state if reserve_state is not None and reserve_state.is_unarrived else None
        )
        if (
            unarrived_reserve_state is not None
            and unarrived_reserve_state.embarked_unit_instance_ids
            != cargo_state.embarked_unit_instance_ids
        ):
            raise GameLifecycleError("transport_cargo_states unarrived reserve route cargo drift.")
        if (
            cargo_state.transport_unit_instance_id not in placed_unit_ids
            and unarrived_reserve_state is None
        ):
            raise GameLifecycleError("transport_cargo_states transport unit must be placed.")
        if unarrived_reserve_state is not None:
            # Reserve-state validation owns the exact alive/dead physical partition for
            # the transport and every unit carried by this unarrived route.
            continue
        transport_model_ids = set(model_ids_by_unit_id[cargo_state.transport_unit_instance_id])
        if transport_model_ids & removed_model_ids:
            raise GameLifecycleError("transport_cargo_states transport models must not be removed.")
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            embarked_unit = unit_by_id[embarked_unit_id]
            model_ids = set(model_ids_by_unit_id[embarked_unit_id])
            alive_model_ids = {
                model.model_instance_id for model in embarked_unit.own_models if model.is_alive
            }
            dead_model_ids = model_ids - alive_model_ids
            if model_ids & placed_model_ids:
                raise GameLifecycleError("embarked unit models must not be placed.")
            if alive_model_ids & removed_model_ids:
                raise GameLifecycleError("living embarked unit models must not be removed.")
            if not dead_model_ids <= removed_model_ids:
                raise GameLifecycleError(
                    "destroyed embarked unit models must have exact removal state."
                )
