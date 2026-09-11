from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookRegistry
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle_validation import (
    contribution_values as _contribution_values,
)
from warhammer40k_core.engine.faction_content.events import RuntimeContentEventIndex
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartHookRegistry
from warhammer40k_core.engine.shooting_phase_start_hooks import ShootingPhaseStartHookRegistry
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_execution_2026_27

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution


@dataclass(frozen=True, slots=True)
class PhaseStartRegistries:
    command: CommandPhaseStartHookRegistry
    fight: FightPhaseStartHookRegistry
    shooting: ShootingPhaseStartHookRegistry


def phase_start_registries(
    *,
    activation: RuntimeContentActivation,
    records: tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    validated_armies: tuple[ArmyDefinition, ...],
    validated_contributions: tuple[RuntimeContentContribution, ...],
    event_index: RuntimeContentEventIndex,
) -> PhaseStartRegistries:
    from warhammer40k_core.engine import generic_rule_lifecycle_hooks
    from warhammer40k_core.engine import runtime_event_phase_hooks as _runtime_event_phase_hooks
    from warhammer40k_core.engine.faction_content import (
        catalog_generic_hooks,
        catalog_runtime_hooks,
    )

    command_phase_start_hook_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            *_runtime_event_phase_hooks.command_start_bindings(event_index),
            *catalog_generic_hooks.command_start(ability_indexes_by_player_id, validated_armies),
            *_contribution_values(
                validated_contributions,
                lambda contribution: contribution.command_phase_start_hook_bindings,
            ),
        )
    )
    fight_phase_start_hook_registry = FightPhaseStartHookRegistry.from_bindings(
        (
            *_runtime_event_phase_hooks.fight_start_bindings(event_index),
            *catalog_runtime_hooks.fight_phase_start_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=validated_armies,
            ),
            *generic_rule_lifecycle_hooks.fight_phase_start_hook_bindings(
                activation=activation,
                execution_records=records,
            ),
            *_contribution_values(
                validated_contributions,
                lambda contribution: contribution.fight_phase_start_hook_bindings,
            ),
        )
    )
    shooting_phase_start_hook_registry = ShootingPhaseStartHookRegistry.from_bindings(
        (
            *_runtime_event_phase_hooks.shooting_start_bindings(event_index),
            *catalog_runtime_hooks.shooting_phase_start_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=validated_armies,
            ),
            *_contribution_values(
                validated_contributions,
                lambda contribution: contribution.shooting_phase_start_hook_bindings,
            ),
        )
    )
    return PhaseStartRegistries(
        command_phase_start_hook_registry,
        fight_phase_start_hook_registry,
        shooting_phase_start_hook_registry,
    )
