from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import RerollPermission
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_leading_roll_reroll_permission,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_charge_roll_reroll_permission_for_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def charge_reroll_permission_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    ability_index: AbilityCatalogIndex,
) -> RerollPermission | None:
    unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
    permissions = tuple(
        permission
        for permission in (
            catalog_charge_roll_reroll_permission_for_unit(
                ability_index=ability_index,
                unit=unit,
                current_model_instance_ids=current_model_instance_ids_for_charge_unit(
                    state=state,
                    unit=unit,
                ),
                player_id=player_id,
            ),
            source_backed_reroll_permission_for_unit(
                state=state,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                roll_type="charge_roll",
                timing_window="after_charge_roll",
            ),
            conditional_leading_roll_reroll_permission(
                state=state,
                rules_unit_instance_id=unit_instance_id,
                player_id=player_id,
                rule_roll_type="charge_roll",
                eligible_roll_type="charge_roll",
                timing_window="after_charge_roll",
            ),
        )
        if permission is not None
    )
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple charge reroll permissions are available.")
    return permissions[0] if permissions else None


def current_model_instance_ids_for_charge_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Charge roll current model evidence requires a UnitInstance.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge roll current model evidence requires battlefield_state.")
    placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    known_model_ids = {model.model_instance_id for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        if model_placement.model_instance_id not in known_model_ids:
            raise GameLifecycleError("Charge roll unit placement contains unknown models.")
        current_ids.append(model_placement.model_instance_id)
    if not current_ids:
        raise GameLifecycleError("Charge roll current model evidence must not be empty.")
    return tuple(sorted(current_ids))


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Charge unit_instance_id is unknown.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
