"""Keep current cargo and an unarrived carrier's route membership consistent."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveState
from warhammer40k_core.engine.transports import TransportCargoState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView


def reserve_state_with_updated_cargo(
    *, state: GameState, before: TransportCargoState, after: TransportCargoState
) -> ReserveState | None:
    """Validate the old route before preparing its replacement, without mutation."""
    if before.transport_unit_instance_id != after.transport_unit_instance_id:
        raise GameLifecycleError("Cargo membership update changed carrier identity.")
    reserve = state.reserve_state_for_unit(before.transport_unit_instance_id)
    if reserve is None or not reserve.is_unarrived:
        return None
    if reserve.embarked_unit_instance_ids != before.embarked_unit_instance_ids:
        raise GameLifecycleError("Cargo membership update found reserve cargo drift.")
    return replace(reserve, embarked_unit_instance_ids=after.embarked_unit_instance_ids)


def rules_unit_retains_phase_start_cargo(
    *, cargo: TransportCargoState, rules_unit: RulesUnitView
) -> bool:
    """A returned component inherits its receiving unit's embarked phase history."""
    components = rules_unit.component_unit_instance_ids
    return any(cargo.unit_started_phase_embarked(i) for i in components) and not any(
        cargo.unit_disembarked_this_phase(i) for i in components
    )
