from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.battle_round_hooks import BattleRoundStartHookBinding
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookBinding
from warhammer40k_core.engine.catalog_battle_shock_runtime import (
    catalog_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_return_on_death_runtime import (
    catalog_return_on_death_phase_end_hook_bindings,
    catalog_return_on_death_unit_destroyed_hook_bindings,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    catalog_selected_target_attack_sequence_completed_hook_bindings,
    catalog_selected_target_fight_phase_start_hook_bindings,
)
from warhammer40k_core.engine.catalog_shadow_form_runtime import (
    catalog_shadow_form_battle_round_start_hook_bindings,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import (
    catalog_tracked_target_battle_round_start_hook_bindings,
    catalog_tracked_target_unit_destroyed_hook_bindings,
)
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartHookBinding
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookBinding,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookBinding


def battle_round_start_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleRoundStartHookBinding, ...]:
    return (
        *catalog_tracked_target_battle_round_start_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        ),
        *catalog_shadow_form_battle_round_start_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        ),
    )


def battle_shock_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleShockHookBinding, ...]:
    return catalog_battle_shock_hook_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


def unit_destroyed_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitDestroyedHookBinding, ...]:
    return (
        *catalog_return_on_death_unit_destroyed_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        ),
        *catalog_tracked_target_unit_destroyed_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        ),
    )


def phase_end_objective_control_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
    return catalog_return_on_death_phase_end_hook_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


def fight_phase_start_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FightPhaseStartHookBinding, ...]:
    return catalog_selected_target_fight_phase_start_hook_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )


def attack_sequence_completed_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AttackSequenceCompletedHookBinding, ...]:
    return catalog_selected_target_attack_sequence_completed_hook_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )
