from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.catalog_poisoned_status_support import (
    CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
    clause_is_poisoned_command_mortal_wounds_status,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookBinding,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id

CATALOG_POISONED_COMMAND_MORTAL_WOUNDS_SOURCE_KIND = "catalog_poisoned_command_mortal_wounds"
CATALOG_POISONED_COMMAND_ROLLED_EVENT = "catalog_poisoned_command_mortal_wounds_rolled"
CATALOG_POISONED_COMMAND_PENDING_EVENT = "catalog_poisoned_command_mortal_wounds_pending"
CATALOG_POISONED_COMMAND_RESOLVED_EVENT = "catalog_poisoned_command_mortal_wounds_resolved"

_EXPECTED_POISON_PARAMETERS: dict[str, JsonValue] = {
    "command_phase_mortal_wounds": "D3",
    "command_phase_roll_threshold": 4,
    "command_phase_timing": "start_each_players_command_phase",
    "status": "poisoned",
}


def catalog_poisoned_command_start_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[CommandPhaseStartHookBinding, ...]:
    if not _has_poisoned_status_records(ability_indexes_by_player_id):
        return ()
    return (
        CommandPhaseStartHookBinding(
            hook_id=CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
            source_id=CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
            effect_handler=resolve_catalog_poisoned_command_mortal_wounds,
        ),
    )


def catalog_poisoned_mortal_wound_feel_no_pain_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
    if not _has_poisoned_status_records(ability_indexes_by_player_id):
        return ()
    return (
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id=CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
            source_id=CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
            source_kind=CATALOG_POISONED_COMMAND_MORTAL_WOUNDS_SOURCE_KIND,
            handler=apply_catalog_poisoned_mortal_wound_feel_no_pain_decision,
        ),
    )


def resolve_catalog_poisoned_command_mortal_wounds(
    context: CommandPhaseStartEffectContext,
) -> LifecycleStatus | None:
    if type(context) is not CommandPhaseStartEffectContext:
        raise GameLifecycleError("Catalog poisoned status requires command effect context.")
    processed_target_ids = _processed_target_ids(context)
    for target, effects in _current_poisoned_targets(context):
        if target.unit_instance_id in processed_target_ids:
            continue
        status = _resolve_poisoned_target(context=context, target=target, effects=effects)
        if status is not None:
            return status
    return None


def apply_catalog_poisoned_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError("Catalog poisoned Feel No Pain requires continuation context.")
    source_context = _payload_object(context.source_context)
    if source_context.get("source_kind") != CATALOG_POISONED_COMMAND_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Catalog poisoned Feel No Pain source kind drifted.")
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=context.state,
        decisions=context.decisions,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    if routed.request is not None:
        context.decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": _payload_string(source_context, "source_rule_id"),
                "target_unit_instance_id": _payload_string(
                    source_context,
                    "target_unit_instance_id",
                ),
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Catalog poisoned Feel No Pain did not finish routing.")
    context.decisions.event_log.append(
        CATALOG_POISONED_COMMAND_RESOLVED_EVENT,
        validate_json_value(
            {
                **source_context,
                "mortal_application": routed.application.to_payload(),
                "feel_no_pain_result_id": context.result.result_id,
            }
        ),
    )
    return None


def _resolve_poisoned_target(
    *,
    context: CommandPhaseStartEffectContext,
    target: RulesUnitView,
    effects: tuple[PersistingEffect, ...],
) -> LifecycleStatus | None:
    state = context.state
    manager = DiceRollManager(state.game_id, event_log=context.decisions.event_log)
    trigger_roll = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Poisoned status for {target.unit_instance_id}",
            roll_type="catalog.poisoned_command.trigger",
            actor_id=target.owner_player_id,
        )
    )
    source_effect = effects[0]
    source_context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": context.active_player_id,
        "source_kind": CATALOG_POISONED_COMMAND_MORTAL_WOUNDS_SOURCE_KIND,
        "source_rule_id": source_effect.source_rule_id,
        "poison_effect_ids": [effect.effect_id for effect in effects],
        "target_unit_instance_id": target.unit_instance_id,
        "target_player_id": target.owner_player_id,
        "trigger_threshold": 4,
        "trigger_roll": validate_json_value(trigger_roll.to_payload()),
    }
    if trigger_roll.current_total < 4:
        context.decisions.event_log.append(
            CATALOG_POISONED_COMMAND_RESOLVED_EVENT,
            validate_json_value({**source_context, "mortal_wounds": 0, "mortal_application": None}),
        )
        return None
    d3_result = _roll_poisoned_d3(
        manager=manager,
        target=target,
    )
    source_context["mortal_wounds"] = d3_result.value
    source_context["d3_result"] = validate_json_value(d3_result.to_payload())
    context.decisions.event_log.append(
        CATALOG_POISONED_COMMAND_ROLLED_EVENT,
        validate_json_value(source_context),
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"catalog-poisoned:{state.battle_round}:{context.active_player_id}:"
            f"{target.unit_instance_id}"
        ),
        source_rule_id=source_effect.source_rule_id,
        source_context=source_context,
        target_unit_instance_id=target.unit_instance_id,
        defender_player_id=target.owner_player_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=context.active_player_id,
            source_rules_unit_instance_id=None,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.COMMAND,
            source_step="poisoned_command_mortal_wounds",
        ),
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=context.decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=manager,
    )
    if routed.request is not None:
        context.decisions.request_decision(routed.request)
        context.decisions.event_log.append(
            CATALOG_POISONED_COMMAND_PENDING_EVENT,
            validate_json_value({**source_context, "request_id": routed.request.request_id}),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": source_effect.source_rule_id,
                "target_unit_instance_id": target.unit_instance_id,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Catalog poisoned mortal wounds did not resolve.")
    context.decisions.event_log.append(
        CATALOG_POISONED_COMMAND_RESOLVED_EVENT,
        validate_json_value(
            {**source_context, "mortal_application": routed.application.to_payload()}
        ),
    )
    return None


def _current_poisoned_targets(
    context: CommandPhaseStartEffectContext,
) -> tuple[tuple[RulesUnitView, tuple[PersistingEffect, ...]], ...]:
    effects_by_target_id: dict[str, list[PersistingEffect]] = {}
    for effect in sorted(context.state.persisting_effects, key=lambda item: item.effect_id):
        if not _is_poisoned_effect(effect):
            continue
        for target_id in effect.target_unit_instance_ids:
            effects_by_target_id.setdefault(target_id, []).append(effect)
    targets: list[tuple[RulesUnitView, tuple[PersistingEffect, ...]]] = []
    for target_id, effects in sorted(effects_by_target_id.items()):
        target = rules_unit_view_by_id(state=context.state, unit_instance_id=target_id)
        if not _rules_unit_is_on_battlefield(context=context, target=target):
            continue
        targets.append((target, tuple(effects)))
    return tuple(targets)


def _is_poisoned_effect(effect: PersistingEffect) -> bool:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return False
    rule_effect = payload.get("effect")
    if not isinstance(rule_effect, dict) or rule_effect.get("kind") != "set_contextual_status":
        return False
    raw_parameters = rule_effect.get("parameters")
    if type(raw_parameters) is not list:
        return False
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if type(raw_parameter) is not dict or set(raw_parameter) != {"key", "value"}:
            return False
        key = raw_parameter["key"]
        if type(key) is not str or not key or key in parameters:
            return False
        parameters[key] = raw_parameter["value"]
    selected_target_id = parameters.pop("selected_target_unit_instance_id", None)
    return parameters == _EXPECTED_POISON_PARAMETERS and type(selected_target_id) is str


def _rules_unit_is_on_battlefield(
    *,
    context: CommandPhaseStartEffectContext,
    target: RulesUnitView,
) -> bool:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Catalog poisoned status requires battlefield state.")
    return any(
        model.is_alive and battlefield.model_placement_or_none(model.model_instance_id) is not None
        for model in target.alive_models()
    )


def _processed_target_ids(context: CommandPhaseStartEffectContext) -> set[str]:
    processed: set[str] = set()
    for event in context.decisions.event_log.records:
        if event.event_type not in {
            CATALOG_POISONED_COMMAND_PENDING_EVENT,
            CATALOG_POISONED_COMMAND_RESOLVED_EVENT,
        } or not isinstance(event.payload, dict):
            continue
        if (
            event.payload.get("game_id") != context.state.game_id
            or event.payload.get("battle_round") != context.state.battle_round
            or event.payload.get("active_player_id") != context.active_player_id
        ):
            continue
        target_id = event.payload.get("target_unit_instance_id")
        if type(target_id) is str:
            processed.add(target_id)
    return processed


def _roll_poisoned_d3(
    *,
    manager: DiceRollManager,
    target: RulesUnitView,
) -> D3RollResult:
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Poisoned mortal wounds for {target.unit_instance_id}",
            roll_type="catalog.poisoned_command.mortal_wounds_d3",
            actor_id=target.owner_player_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _has_poisoned_status_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    if not isinstance(cast(object, ability_indexes_by_player_id), Mapping):
        raise GameLifecycleError("Catalog poisoned status indexes must be a mapping.")
    return any(
        clause_is_poisoned_command_mortal_wounds_status(clause)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        for clause in catalog_rule_clauses_from_record(record)
    )


def _payload_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog poisoned status payload must be an object.")
    return payload


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog poisoned status payload {key} must be text.")
    return value
