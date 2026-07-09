from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    catalog_rule_clauses_from_record,
    catalog_rule_ir_consumers_for_clause,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIRError,
    parameter_payload,
)

CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE = "catalog_ir.battle_shock_failed_heal_d3"
CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT = "catalog_battle_shock_failed_heal_resolved"
CATALOG_BATTLE_SHOCK_FAILED_HEAL_NO_EFFECT_EVENT = "catalog_battle_shock_failed_heal_no_effect"


def catalog_battle_shock_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleShockHookBinding, ...]:
    if not _has_catalog_battle_shock_records(
        ability_indexes_by_player_id=ability_indexes_by_player_id
    ):
        return ()
    _validate_armies(armies)
    return (
        BattleShockHookBinding(
            hook_id=CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
            source_id=CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
            forced_test_handler=catalog_forced_battle_shock_unit_ids,
        ),
        BattleShockHookBinding(
            hook_id=CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
            source_id=CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
            outcome_handler=resolve_catalog_battle_shock_failed_heal,
        ),
    )


def catalog_forced_battle_shock_unit_ids(
    context: BattleShockForcedTestContext,
) -> tuple[str, ...]:
    if type(context) is not BattleShockForcedTestContext:
        raise GameLifecycleError("Catalog Battle-shock forced tests require context.")
    if context.phase is not BattlePhase.COMMAND:
        return ()
    active_army = context.state.army_definition_for_player(context.active_player_id)
    if active_army is None:
        raise GameLifecycleError("Catalog Battle-shock forced tests require active army.")
    forced_ids: set[str] = set()
    for unit in active_army.units:
        for effect in context.state.persisting_effects_for_unit(unit.unit_instance_id):
            if effect.owner_player_id == context.active_player_id:
                continue
            if _persisted_forced_battle_shock_effect(effect):
                forced_ids.add(unit.unit_instance_id)
    return tuple(sorted(forced_ids))


def resolve_catalog_battle_shock_failed_heal(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Catalog Battle-shock heal requires outcome context.")
    if context.phase is not BattlePhase.COMMAND:
        return
    result = context.result
    if result.passed:
        return
    target_unit_id = result.request.unit_instance_id
    for effect in context.state.persisting_effects_for_unit(target_unit_id):
        if effect.owner_player_id == result.request.player_id:
            continue
        if not _persisted_failed_battle_shock_heal_effect(effect):
            continue
        _resolve_failed_battle_shock_heal_effect(context=context, effect=effect)


def _resolve_failed_battle_shock_heal_effect(
    *,
    context: BattleShockOutcomeContext,
    effect: PersistingEffect,
) -> None:
    source_unit_id = _generic_effect_source_unit_id(effect)
    source_unit = _unit_by_id(tuple(context.state.army_definitions), source_unit_id)
    current_model_ids = _placed_model_ids_for_unit(
        context=context,
        unit_instance_id=source_unit.unit_instance_id,
    )
    if not current_model_ids:
        context.decisions.event_log.append(
            CATALOG_BATTLE_SHOCK_FAILED_HEAL_NO_EFFECT_EVENT,
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.phase.value,
                "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                "battle_shock_result_id": context.result.result_id,
                "persisting_effect_id": effect.effect_id,
                "source_unit_instance_id": source_unit.unit_instance_id,
                "no_effect_reason": "source_unit_not_placed",
            },
        )
        return
    d3_result = _roll_d3(
        context=context,
        reason="Catalog Battle-shock failed heal",
        actor_id=source_unit.unit_instance_id,
    )
    healing_effect = HealingEffect(
        effect_id=f"{effect.effect_id}:battle-shock-failed-heal:{context.result.result_id}",
        target_unit_instance_id=source_unit.unit_instance_id,
        amount=d3_result.value,
        opposing_player_id=context.result.request.player_id,
        selection_actor_player_id=effect.owner_player_id,
        source_rule_id=effect.source_rule_id,
        source_context=validate_json_value(
            {
                "source_kind": "generic_rule_ir_battle_shock_failed_heal",
                "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                "battle_shock_result_id": context.result.result_id,
                "persisting_effect": validate_json_value(effect.to_payload()),
                "d3_result": validate_json_value(d3_result.to_payload()),
            }
        ),
        phase_start_model_ids=current_model_ids,
    )
    resolved, pending = resolve_healing_until_blocked(
        state=context.state,
        decisions=context.decisions,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        effect=healing_effect,
    )
    if pending is not None:
        raise GameLifecycleError(
            "Catalog Battle-shock failed heal unexpectedly requested a choice."
        )
    context.decisions.event_log.append(
        CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
            "battle_shock_result_id": context.result.result_id,
            "player_id": effect.owner_player_id,
            "source_unit_instance_id": source_unit.unit_instance_id,
            "target_unit_instance_id": context.result.request.unit_instance_id,
            "persisting_effect_id": effect.effect_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(resolved.to_payload()),
        },
    )


def _persisted_forced_battle_shock_effect(effect: PersistingEffect) -> bool:
    rule_effect = _generic_rule_effect_or_none(effect)
    if rule_effect is None or rule_effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(rule_effect.parameters)
    return (
        parameters.get("status") == "battle_shock_forced_below_starting_strength"
        and parameters.get("rules_context") == "battle_shock"
        and parameters.get("force_battle_shock_below_starting_strength") is True
    )


def _persisted_failed_battle_shock_heal_effect(effect: PersistingEffect) -> bool:
    rule_effect = _generic_rule_effect_or_none(effect)
    if rule_effect is None or rule_effect.kind is not RuleEffectKind.RESTORE_LOST_WOUNDS:
        return False
    parameters = parameter_payload(rule_effect.parameters)
    return (
        parameters.get("amount") == "D3"
        and parameters.get("trigger") == "target_failed_battle_shock"
        and parameters.get("source_reference") == "aura_source"
    )


def _generic_rule_effect_or_none(effect: PersistingEffect) -> RuleEffectSpec | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Catalog Battle-shock generic effect payload is missing effect.")
    try:
        return RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, effect_payload))
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog Battle-shock generic effect payload is invalid.") from exc


def _generic_effect_source_unit_id(effect: PersistingEffect) -> str:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog Battle-shock heal requires generic effect payload.")
    context_payload = payload.get("context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Catalog Battle-shock heal requires generic context payload.")
    source_unit_id = context_payload.get("source_unit_instance_id")
    if type(source_unit_id) is not str:
        raise GameLifecycleError("Catalog Battle-shock heal requires source unit context.")
    return source_unit_id


def _roll_d3(
    *,
    context: BattleShockOutcomeContext,
    reason: str,
    actor_id: str,
) -> D3RollResult:
    roll_state = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=reason,
            roll_type=CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
            actor_id=actor_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _placed_model_ids_for_unit(
    *,
    context: BattleShockOutcomeContext,
    unit_instance_id: str,
) -> tuple[str, ...]:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Catalog Battle-shock heal requires battlefield state.")
    try:
        placement = battlefield.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Catalog Battle-shock heal source unit is not placed.") from exc
    return tuple(placement.model_instance_id for placement in placement.model_placements)


def _unit_by_id(armies: tuple[ArmyDefinition, ...], unit_instance_id: str) -> UnitInstance:
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise GameLifecycleError("Catalog Battle-shock heal source unit is unknown.")


def _has_catalog_battle_shock_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    relevant_consumer_ids = {
        CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    }
    for index in ability_indexes_by_player_id.values():
        for record in index.all_records():
            if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if set(catalog_rule_ir_consumers_for_clause(clause)) & relevant_consumer_ids:
                    return True
    return False


def _validate_armies(armies: tuple[ArmyDefinition, ...]) -> None:
    if type(armies) is not tuple:
        raise GameLifecycleError("Catalog Battle-shock runtime armies must be a tuple.")
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog Battle-shock runtime armies are invalid.")
