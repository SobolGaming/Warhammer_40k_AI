from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import TYPE_CHECKING, Protocol

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.move_completed_stratagem_candidates import (
    charge_move_stratagem_candidates,
)
from warhammer40k_core.engine.move_completion_rule_hooks import MoveCompletionRuleRegistry
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_hooks,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


class ChargeMoveCompletedHookProvider(Protocol):
    @property
    def stratagem_index(self) -> StratagemCatalogIndex: ...

    @property
    def stratagem_cost_modifier_registry(self) -> StratagemCostModifierRegistry: ...

    @property
    def move_completion_rule_registry(self) -> MoveCompletionRuleRegistry: ...

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
    return resolve_unit_move_completed_hooks(
        state=state,
        decisions=decisions,
        registry=handler.unit_move_completed_mortal_wound_hooks,
        additional_candidates=partial(charge_handler_move_candidates, handler),
        battle_shock_move_hooks=handler.unit_move_completed_battle_shock_hooks,
        battle_shock_hooks=handler.battle_shock_hooks,
        ruleset_descriptor=ruleset_descriptor,
        runtime_modifier_registry=handler.runtime_modifier_registry,
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=(movement_action,),
        ability_indexes_by_player_id=handler.ability_indexes_by_player_id,
    )


def charge_handler_move_candidates(
    handler: ChargeMoveCompletedHookProvider,
    context: UnitMoveCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    return (
        *handler.move_completion_rule_registry.candidates_for(context),
        *charge_move_stratagem_candidates(
            context,
            stratagem_index=handler.stratagem_index,
            cost_modifiers=handler.stratagem_cost_modifier_registry,
        ),
    )


def validate_charge_move_completed_hook_provider(
    handler: ChargeMoveCompletedHookProvider,
) -> None:
    if type(handler.move_completion_rule_registry) is not MoveCompletionRuleRegistry:
        raise GameLifecycleError("ChargePhaseHandler move rules must be a registry.")
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
