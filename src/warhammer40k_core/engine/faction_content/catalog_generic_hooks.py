from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_hooks import AdvanceMoveHookBinding
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_command_restoration_runtime import (
    catalog_command_restoration_bindings,
)
from warhammer40k_core.engine.catalog_conditional_leading_runtime import (
    catalog_conditional_leading_advance_move_bindings,
    catalog_conditional_leading_weapon_profile_bindings,
)
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookBinding
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierBinding


def command_start(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[CommandPhaseStartHookBinding, ...]:
    return catalog_command_restoration_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


def advance(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AdvanceMoveHookBinding, ...]:
    return catalog_conditional_leading_advance_move_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


def weapon_modifiers(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[WeaponProfileModifierBinding, ...]:
    return catalog_conditional_leading_weapon_profile_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


__all__ = ("advance", "command_start", "weapon_modifiers")
