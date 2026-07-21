from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
    catalog_movement_target_pair_move_completed_bindings,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_runtime import (
    catalog_unit_move_completed_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_unit_move_completed_mortal_wounds_runtime import (
    catalog_unit_move_completed_mortal_wound_hook_bindings,
)
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedMortalWoundHookBinding,
    UnitMoveCompletedMortalWoundHookRegistry,
)


class UnitMoveCompletedContribution(Protocol):
    @property
    def unit_move_completed_mortal_wound_hook_bindings(
        self,
    ) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]: ...


def unit_move_completed_mortal_wound_hook_registry(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    contributions: tuple[UnitMoveCompletedContribution, ...],
) -> UnitMoveCompletedMortalWoundHookRegistry:
    return UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        (
            *catalog_unit_move_completed_mortal_wound_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=armies,
            ),
            *catalog_movement_target_pair_move_completed_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=armies,
            ),
            *_unit_move_completed_mortal_wound_contribution_bindings(contributions),
        )
    )


def catalog_unit_move_completed_battle_shock_hook_registry(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> UnitMoveCompletedBattleShockHookRegistry:
    return UnitMoveCompletedBattleShockHookRegistry.from_bindings(
        catalog_unit_move_completed_battle_shock_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        )
    )


def _unit_move_completed_mortal_wound_contribution_bindings(
    contributions: tuple[UnitMoveCompletedContribution, ...],
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    return tuple(
        binding
        for contribution in contributions
        for binding in contribution.unit_move_completed_mortal_wound_hook_bindings
    )
