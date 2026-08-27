from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockModifierApplication,
    battle_shock_modifier_applications_from_modifiers,
)
from warhammer40k_core.engine.battle_shock_test_service import (
    STRATAGEM_BATTLE_SHOCK_SOURCE_KIND,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionResult,
    RuleExecutionStatus,
    execute_rule_ir,
    scoped_rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.stratagem_use_history_authority import (
    FiniteStratagemUseHistoryAuthority,
    StratagemUseHistoryAuthority,
    validate_loaded_stratagem_use_provider,
    validate_stratagem_use_history,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    generic_rule_ir_execution_target_unit_ids,
)
from warhammer40k_core.engine.stratagems_model import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)
from warhammer40k_core.engine.stratagems_targeting import (
    destroyed_target_unit_ids_from_context,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class StratagemBattleShockSourceAuthority:
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority
    source_payload: dict[str, JsonValue]
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...]


def validate_stratagem_battle_shock_source_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request: BattleShockTestRequest,
    request_base: dict[str, JsonValue],
    runtime_content_bundle: RuntimeContentBundle,
) -> StratagemBattleShockSourceAuthority:
    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Stratagem Battle-shock authority requires a request.")
    if request_base.get("source_kind") != STRATAGEM_BATTLE_SHOCK_SOURCE_KIND:
        raise GameLifecycleError("Stratagem Battle-shock source kind drifted.")
    raw_use = _object(request_base.get("source_stratagem_use"), "source use")
    try:
        use = StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, raw_use))
    except KeyError as exc:
        raise GameLifecycleError("Stratagem Battle-shock source use is incomplete.") from exc
    history = validate_stratagem_use_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        use_record=use,
        mutation_index=request_event_index,
    )
    validate_loaded_stratagem_use_provider(
        authority=history,
        runtime_content_bundle=runtime_content_bundle,
        built_in_handler_ids=frozenset({GENERIC_RULE_IR_STRATAGEM_HANDLER_ID}),
    )
    if (
        request.reason is not BattleShockTestReason.FORCED_BY_STRATAGEM
        or request.battle_round != use.battle_round
        or request.player_id == use.player_id
        or request.request_id != f"{use.use_id}:battle-shock:{request.unit_instance_id}"
        or request.unit_instance_id not in use.affected_unit_instance_ids
        or request_base.get("battle_round") != use.battle_round
        or request_base.get("phase") != use.phase.value
        or request_base.get("active_player_id") != use.active_player_id
    ):
        raise GameLifecycleError("Stratagem Battle-shock occurrence binding drifted.")
    effect_payload = _object(request_base.get("generic_rule_effect"), "generic rule effect")
    expected_effects = _generic_effect_payloads(
        state=state,
        history=history,
    )
    if sum(candidate == effect_payload for candidate in expected_effects) != 1:
        raise GameLifecycleError("Stratagem Battle-shock RuleIR effect authority drifted.")
    expected_keys = frozenset(
        {
            "game_id",
            "battle_round",
            "active_player_id",
            "phase",
            "source_kind",
            "source_stratagem_use",
            "generic_rule_effect",
        }
    )
    if frozenset(request_base) != expected_keys:
        raise GameLifecycleError("Stratagem Battle-shock source payload shape drifted.")
    applications = _generic_additional_modifier_applications(
        history=history,
        request=request,
        effect_payload=effect_payload,
    )
    return StratagemBattleShockSourceAuthority(
        history=history,
        source_payload={
            "source_stratagem_use": validate_json_value(use.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
        additional_modifier_applications=applications,
    )


def _generic_effect_payloads(
    *,
    state: GameState,
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> tuple[dict[str, JsonValue], ...]:
    return historical_stratagem_generic_rule_execution_result(
        state=state,
        history=history,
    ).effect_payloads


def historical_stratagem_generic_rule_execution_result(
    *,
    state: GameState,
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> RuleExecutionResult:
    """Re-execute one authenticated loaded generic Stratagem in producer mode."""

    use = history.use_record
    context = _history_context(history)
    definition = history.catalog_record.definition
    trigger_payload: dict[str, JsonValue] = {}
    if isinstance(context.trigger_payload, dict):
        trigger_payload.update(context.trigger_payload)
    elif context.trigger_payload is not None:
        trigger_payload["source_trigger_payload"] = context.trigger_payload
    trigger_payload.update(
        {
            "stratagem_id": definition.stratagem_id,
            "stratagem_use_id": use.use_id,
            "effect_selection": use.effect_selection,
            "stratagem_context": validate_json_value(context.to_payload()),
        }
    )
    result = execute_rule_ir(
        rule_ir=scoped_rule_ir_from_execution_payload(definition.effect_payload),
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            timing_window_id=context.timing_window_id,
            source_unit_instance_id=(
                use.targeted_unit_instance_ids[0]
                if len(use.targeted_unit_instance_ids) == 1
                else None
            ),
            target_unit_instance_ids=generic_rule_ir_execution_target_unit_ids(
                state=state,
                use_record=use,
            ),
            target_player_id=(_history_target_binding(history).target_player_id),
            trigger_payload=validate_json_value(trigger_payload),
            state=state,
            event_log=None,
            record_persisting_effects=False,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        raise GameLifecycleError("Stratagem Battle-shock RuleIR no longer applies.")
    return replace(
        result,
        effect_payloads=tuple(
            _producer_effect_payload(effect) for effect in result.effect_payloads
        ),
        event_records=tuple(_producer_event_record(event) for event in result.event_records),
    )


def _producer_effect_payload(effect_payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    context = _object(effect_payload.get("context"), "generic rule context")
    if context.get("record_persisting_effects") is not False:
        raise GameLifecycleError("Stratagem Battle-shock authority execution mode drifted.")
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **effect_payload,
                "context": {**context, "record_persisting_effects": True},
            }
        ),
    )


def _producer_event_record(event: EventRecord) -> EventRecord:
    payload = event.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("context"), dict):
        return event
    return replace(event, payload=_producer_effect_payload(payload))


def _generic_additional_modifier_applications(
    *,
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
    request: BattleShockTestRequest,
    effect_payload: dict[str, JsonValue],
) -> tuple[BattleShockModifierApplication, ...]:
    operand = _optional_int_parameter(effect_payload, "modifier_if_destroyed_target")
    if operand is None or request.unit_instance_id not in destroyed_target_unit_ids_from_context(
        _history_context(history)
    ):
        return ()
    source_id = effect_payload.get("source_id")
    if type(source_id) is not str or not source_id:
        raise GameLifecycleError("Stratagem Battle-shock modifier source is invalid.")
    suffix = _optional_string_parameter(effect_payload, "modifier_source_suffix")
    modifier = RollModifier(
        modifier_id=(f"{history.use_record.use_id}:{suffix or 'battle-shock-modifier'}"),
        source_id=source_id,
        operand=operand,
    )
    return battle_shock_modifier_applications_from_modifiers(
        provider_id=history.use_record.handler_id,
        modifiers=(modifier,),
    )


def _history_context(
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> StratagemEligibilityContext:
    if isinstance(history, FiniteStratagemUseHistoryAuthority):
        return history.context
    return history.submitted_proposal.context


def _history_target_binding(
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> StratagemTargetBinding:
    if isinstance(history, FiniteStratagemUseHistoryAuthority):
        return history.target_binding
    target_binding = history.submitted_proposal.target_binding
    if target_binding is None:
        raise GameLifecycleError("Stratagem Battle-shock target binding is missing.")
    return target_binding


def _optional_int_parameter(payload: dict[str, JsonValue], key: str) -> int | None:
    value = _parameter(payload, key)
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError("Stratagem Battle-shock modifier operand is invalid.")
    return value


def _optional_string_parameter(payload: dict[str, JsonValue], key: str) -> str | None:
    value = _parameter(payload, key)
    if value is None:
        return None
    if type(value) is not str or not value:
        raise GameLifecycleError("Stratagem Battle-shock modifier suffix is invalid.")
    return value


def _parameter(payload: dict[str, JsonValue], key: str) -> JsonValue:
    effect = _object(payload.get("effect"), "generic effect")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list) or any(
        not isinstance(parameter, dict) for parameter in parameters
    ):
        raise GameLifecycleError("Stratagem Battle-shock effect parameters are invalid.")
    matches = tuple(
        parameter.get("value")
        for parameter in parameters
        if isinstance(parameter, dict) and parameter.get("key") == key
    )
    if len(matches) > 1:
        raise GameLifecycleError("Stratagem Battle-shock effect parameter is duplicated.")
    return None if not matches else matches[0]


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Stratagem Battle-shock {context} must be an object.")
    return value


__all__ = (
    "StratagemBattleShockSourceAuthority",
    "historical_stratagem_generic_rule_execution_result",
    "validate_stratagem_battle_shock_source_authority",
)
