from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_battle_shock_hooks,
    resolve_unit_move_completed_mortal_wound_hooks,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class ChargeMoveCompletedHookProvider(Protocol):
    @property
    def ruleset_descriptor(self) -> RulesetDescriptor | None: ...

    @property
    def unit_move_completed_mortal_wound_hooks(
        self,
    ) -> UnitMoveCompletedMortalWoundHookRegistry: ...

    @property
    def unit_move_completed_battle_shock_hooks(
        self,
    ) -> UnitMoveCompletedBattleShockHookRegistry: ...

    @property
    def battle_shock_hooks(self) -> BattleShockHookRegistry: ...

    @property
    def ability_indexes_by_player_id(self) -> Mapping[str, AbilityCatalogIndex]: ...

    @property
    def runtime_modifier_registry(self) -> RuntimeModifierRegistry: ...


def resolve_charge_move_completed_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
    handler: ChargeMoveCompletedHookProvider,
    movement_action: str,
) -> LifecycleStatus | None:
    ruleset_descriptor = _ruleset_descriptor_for_handler(handler)
    move_completed_status = resolve_unit_move_completed_mortal_wound_hooks(
        state=state,
        decisions=decisions,
        registry=handler.unit_move_completed_mortal_wound_hooks,
        ruleset_descriptor=ruleset_descriptor,
        runtime_modifier_registry=handler.runtime_modifier_registry,
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=(movement_action,),
        ability_indexes_by_player_id=handler.ability_indexes_by_player_id,
    )
    if move_completed_status is not None:
        return move_completed_status
    resolve_unit_move_completed_battle_shock_hooks(
        state=state,
        decisions=decisions,
        registry=handler.unit_move_completed_battle_shock_hooks,
        battle_shock_hooks=handler.battle_shock_hooks,
        ruleset_descriptor=ruleset_descriptor,
        runtime_modifier_registry=handler.runtime_modifier_registry,
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=(movement_action,),
        ability_indexes_by_player_id=handler.ability_indexes_by_player_id,
    )
    return None


def validate_charge_move_completed_hook_provider(
    handler: ChargeMoveCompletedHookProvider,
) -> None:
    if (
        type(handler.unit_move_completed_mortal_wound_hooks)
        is not UnitMoveCompletedMortalWoundHookRegistry
    ):
        raise GameLifecycleError(
            "ChargePhaseHandler unit_move_completed_mortal_wound_hooks must be a registry."
        )
    if (
        type(handler.unit_move_completed_battle_shock_hooks)
        is not UnitMoveCompletedBattleShockHookRegistry
    ):
        raise GameLifecycleError(
            "ChargePhaseHandler unit_move_completed_battle_shock_hooks must be a registry."
        )
    if type(handler.battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError("ChargePhaseHandler battle_shock_hooks must be a registry.")


def _ruleset_descriptor_for_handler(
    handler: ChargeMoveCompletedHookProvider,
) -> RulesetDescriptor:
    ruleset_descriptor = handler.ruleset_descriptor
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Charge move completed hooks require a RulesetDescriptor.")
    return ruleset_descriptor
