from __future__ import annotations

from warhammer40k_core.engine import catalog_fight_end_triggered_movement_support as _fight
from warhammer40k_core.engine import (
    catalog_movement_end_reactive_normal_move_support as _movement_end,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec


def registered_hook_ids() -> tuple[str, ...]:
    return (
        _fight.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
        _movement_end.CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
    )


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Triggered movement classification requires RuleClause.")
    consumer_ids: list[str] = []
    if _fight.clause_is_fight_end_triggered_movement(clause):
        consumer_ids.append(_fight.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID)
    if _movement_end.clause_is_movement_end_reactive_normal_move(clause):
        consumer_ids.append(_movement_end.CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID)
    return tuple(consumer_ids)


def consumer_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Triggered movement classification requires RuleEffectSpec.")
    if _fight.effect_is_fight_end_triggered_movement(effect):
        return (_fight.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,)
    if _movement_end.effect_is_movement_end_reactive_normal_move(effect):
        return (_movement_end.CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,)
    return ()
