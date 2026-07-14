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
from warhammer40k_core.engine.catalog_fight_end_triggered_movement_runtime import (
    catalog_fight_end_triggered_movement_hook_bindings,
)
from warhammer40k_core.engine.catalog_once_per_battle_runtime import (
    CatalogOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_reserve_arrival_restrictions import (
    CatalogReserveArrivalRestrictionRuntime,
)
from warhammer40k_core.engine.catalog_return_on_death_runtime import (
    catalog_return_on_death_phase_end_hook_bindings,
    catalog_return_on_death_unit_destroyed_hook_bindings,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
    catalog_selected_target_attack_sequence_completed_hook_bindings,
)
from warhammer40k_core.engine.catalog_shadow_form_runtime import (
    catalog_shadow_form_battle_round_start_hook_bindings,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import (
    catalog_tracked_target_battle_round_start_hook_bindings,
    catalog_tracked_target_unit_destroyed_hook_bindings,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_phase_end_hooks import FightPhaseEndHookBinding
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartHookBinding,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalRestrictionHookRegistry,
)
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
    once_per_battle = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )
    selected_target = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )
    if not (
        once_per_battle.fight_phase_start_bindings() or selected_target.fight_phase_start_bindings()
    ):
        return ()

    def request_handler(context: FightPhaseStartRequestContext) -> DecisionRequest | None:
        request = once_per_battle.fight_phase_start_request(context)
        if request is not None:
            return request
        return selected_target.fight_phase_start_request(context)

    def result_handler(context: FightPhaseStartResultContext) -> bool | LifecycleStatus:
        handled = once_per_battle.apply_fight_phase_start_result(context)
        if handled is not False:
            return handled
        return selected_target.apply_fight_phase_start_result(context)

    return (
        FightPhaseStartHookBinding(
            hook_id="catalog-ir:fight-phase-start",
            source_id="catalog-ir:fight-phase-start",
            request_handler=request_handler,
            result_handler=result_handler,
        ),
    )


def fight_end_hooks(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FightPhaseEndHookBinding, ...]:
    return catalog_fight_end_triggered_movement_hook_bindings(
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


def reserve_arrival_restriction_hook_registry(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> ReserveArrivalRestrictionHookRegistry:
    runtime = CatalogReserveArrivalRestrictionRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    )
    return ReserveArrivalRestrictionHookRegistry.from_bindings(runtime.bindings())
