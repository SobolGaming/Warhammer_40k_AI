from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine import catalog_turn_end_reserves, generic_rule_lifecycle_hooks
from warhammer40k_core.engine import runtime_event_phase_hooks as _runtime_event_phase_hooks
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle_validation import (
    contribution_values as _contribution_values,
)
from warhammer40k_core.engine.faction_content.events import RuntimeContentEventIndex
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_execution_2026_27

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution


def phase_end_registry(
    *,
    activation: RuntimeContentActivation,
    records: tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    validated_armies: tuple[ArmyDefinition, ...],
    validated_contributions: tuple[RuntimeContentContribution, ...],
    event_index: RuntimeContentEventIndex,
) -> TurnEndHookRegistry:
    from warhammer40k_core.engine.catalog_return_on_death_runtime import (
        catalog_return_on_death_phase_end_hook_bindings,
    )

    return TurnEndHookRegistry.from_bindings(
        (
            *catalog_return_on_death_phase_end_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=validated_armies,
            ),
            *_runtime_event_phase_hooks.end_bindings(event_index),
            *catalog_turn_end_reserves.catalog_turn_end_reserve_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=validated_armies,
            ),
            *generic_rule_lifecycle_hooks.turn_end_hook_bindings(
                activation=activation,
                execution_records=records,
            ),
            *_contribution_values(
                validated_contributions,
                lambda contribution: contribution.turn_end_hook_bindings,
            ),
        )
    )
