"""Core consumer of an explicit source-owned reserve-removal permission.

The provider owns Stratagem use, timing, targeting and the choice of effect.
This consumer does not grant those permissions or load named faction rules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from warhammer40k_core.engine.battlefield_presence import rules_unit_has_placed_alive_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_reposition_context import (
    MovementRepositionContext,
    MovementRepositionContextPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.primary_historical_events import (
    primary_reserve_entry_source_terminal_bindings_payload,
    record_primary_reserve_entry_provider_terminal_event,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

SELECT_SOURCE_REPOSITION_DECISION_TYPE = "select_source_reposition"
SOURCE_REPOSITION_PERMISSION_EFFECT_KIND = "movement_reposition_permission"
SOURCE_REPOSITION_PROVIDER_ID = "core:movement:source-reposition"
SOURCE_REPOSITION_RESOLVED_EVENT = "source_reposition_resolved"
DECLINE_SOURCE_REPOSITION_OPTION_ID = "decline_source_reposition"
USE_SOURCE_REPOSITION_OPTION_ID = "enter_strategic_reserves"


def context_from_value(value: JsonValue) -> MovementRepositionContext:
    if not isinstance(value, dict):
        raise GameLifecycleError("Movement reposition context must be an object.")
    return MovementRepositionContext.from_payload(cast(MovementRepositionContextPayload, value))


def movement_reposition_permission_effect(
    *,
    context: MovementRepositionContext,
    owner_player_id: str,
) -> PersistingEffect:
    if type(context) is not MovementRepositionContext:
        raise GameLifecycleError("Movement reposition requires typed source permission.")
    return PersistingEffect(
        effect_id=context.permission_effect_id,
        source_rule_id=context.source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(context.unit_instance_id,),
        started_battle_round=context.battle_round,
        started_phase=context.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=context.battle_round,
            phase=context.phase,
            player_id=context.turn_player_id,
        ),
        effect_payload={
            "effect_kind": SOURCE_REPOSITION_PERMISSION_EFFECT_KIND,
            "source_context": validate_json_value(context.to_payload()),
        },
    )


def current_source_reposition_context(
    *,
    state: GameState,
    unit_instance_id: str,
) -> MovementRepositionContext | None:
    contexts: list[MovementRepositionContext] = []
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != (
            SOURCE_REPOSITION_PERMISSION_EFFECT_KIND
        ):
            continue
        if set(payload) != {"effect_kind", "source_context"}:
            raise GameLifecycleError("Movement reposition permission schema drift.")
        context = context_from_value(payload["source_context"])
        if effect != movement_reposition_permission_effect(
            context=context,
            owner_player_id=effect.owner_player_id,
        ):
            raise GameLifecycleError("Movement reposition permission identity drift.")
        if (
            context.battle_round == state.battle_round
            and context.turn_player_id == state.active_player_id
            and context.phase is state.current_battle_phase
        ):
            contexts.append(context)
    if len(contexts) > 1:
        raise GameLifecycleError("Movement reposition requires one source occasion.")
    return contexts[0] if contexts else None


def _options(*, state: GameState, context: MovementRepositionContext) -> tuple[DecisionOption, ...]:
    if state.stage is not GameLifecycleStage.BATTLE:
        return ()
    if current_source_reposition_context(
        state=state, unit_instance_id=context.unit_instance_id
    ) != (context):
        return ()
    view = rules_unit_view_by_id(state=state, unit_instance_id=context.unit_instance_id)
    effect = next(
        e for e in state.persisting_effects if e.effect_id == context.permission_effect_id
    )
    if effect.owner_player_id != view.owner_player_id:
        raise GameLifecycleError("Movement reposition permission owner drift.")
    if not rules_unit_has_placed_alive_model(state=state, rules_unit=view):
        return ()
    return (
        DecisionOption(
            option_id=DECLINE_SOURCE_REPOSITION_OPTION_ID,
            label="Decline reposition",
            payload={"reposition": False},
        ),
        DecisionOption(
            option_id=USE_SOURCE_REPOSITION_OPTION_ID,
            label="Enter Strategic Reserves",
            payload={"reposition": True},
        ),
    )


def request_source_reposition(
    *,
    state: GameState,
    decisions: DecisionController,
    context: MovementRepositionContext,
) -> LifecycleStatus | None:
    options = _options(state=state, context=context)
    if not options:
        return None
    view = rules_unit_view_by_id(state=state, unit_instance_id=context.unit_instance_id)
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        actor_id=view.owner_player_id,
        decision_type=SELECT_SOURCE_REPOSITION_DECISION_TYPE,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": context.phase.value,
            "source_context": validate_json_value(context.to_payload()),
            "spatial_context_hash": state.physical_proposal_context_hash(),
        },
        options=options,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage, decision_request=decisions.queue.peek_next()
    )


def request_current_source_reposition(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
) -> LifecycleStatus | None:
    context = current_source_reposition_context(state=state, unit_instance_id=unit_instance_id)
    if context is None:
        return None
    return request_source_reposition(state=state, decisions=decisions, context=context)


def validate_source_reposition_provider(
    *,
    provider: PrimaryReserveEntryProvider,
    record: DecisionRecord,
) -> MovementRepositionContext:
    if not isinstance(record.request.payload, dict):
        raise GameLifecycleError("Source reposition request must be an object.")
    context = context_from_value(record.request.payload["source_context"])
    if (
        record.request.decision_type != SELECT_SOURCE_REPOSITION_DECISION_TYPE
        or record.result.selected_option_id != USE_SOURCE_REPOSITION_OPTION_ID
        or record.result.payload != {"reposition": True}
        or provider.source_rule_id != context.source_rule_id
        or provider.target_rules_unit_instance_id != context.unit_instance_id
        or provider.player_id != record.request.actor_id
        or provider.player_id != record.result.actor_id
    ):
        raise GameLifecycleError("Source reposition accepted authority drift.")
    return context


def validate_source_reposition_terminal(
    *,
    provider: PrimaryReserveEntryProvider,
    record: DecisionRecord,
    terminal: EventRecord,
) -> None:
    context = validate_source_reposition_provider(provider=provider, record=record)
    if not isinstance(terminal.payload, dict) or terminal.payload.get("source_context") != (
        validate_json_value(context.to_payload())
    ):
        raise GameLifecycleError("Source reposition terminal context drift.")


def source_reposition_dispatch_handler(
    *,
    state_provider: Callable[[], GameState],
    decisions: DecisionController,
    advance: Callable[[], LifecycleStatus],
) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        result.validate_for_request(request)
        if not isinstance(request.payload, dict):
            raise GameLifecycleError("Source reposition request must be an object.")
        state = state_provider()
        context = context_from_value(request.payload["source_context"])
        if (
            request.options != _options(state=state, context=context)
            or request.payload["spatial_context_hash"] != state.physical_proposal_context_hash()
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Source reposition eligibility changed.",
                payload={"invalid_reason": "source_reposition_context_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        state = state_provider()
        payload = cast(dict[str, JsonValue], record.request.payload)
        context = context_from_value(payload["source_context"])
        if result.selected_option_id == USE_SOURCE_REPOSITION_OPTION_ID:
            if result.actor_id is None:
                raise GameLifecycleError("Source reposition requires an owning player.")
            provider = PrimaryReserveEntryProvider(
                provider_kind=PrimaryReserveEntryProviderKind.SOURCE_STRATAGEM_PERMISSION,
                provider_id=SOURCE_REPOSITION_PROVIDER_ID,
                player_id=result.actor_id,
                source_rule_id=context.source_rule_id,
                target_rules_unit_instance_id=context.unit_instance_id,
                decision_record_id=record.record_id,
                decision_request_id=result.request_id,
                decision_result_id=result.result_id,
                stratagem_use_id=None,
                source_terminal_event_type=SOURCE_REPOSITION_RESOLVED_EVENT,
            )
            reserve = state.reposition_unit_to_strategic_reserves(
                decisions=decisions,
                player_id=result.actor_id,
                unit_instance_id=context.unit_instance_id,
                provider=provider,
                reserve_origin=provider.reserve_origin,
                source_rule_ids=(context.source_rule_id,),
            )
            terminal = decisions.event_log.append(
                SOURCE_REPOSITION_RESOLVED_EVENT,
                {
                    "game_id": state.game_id,
                    "battle_round": context.battle_round,
                    "active_player_id": context.turn_player_id,
                    "phase": context.phase.value,
                    "player_id": result.actor_id,
                    "source_context": validate_json_value(context.to_payload()),
                    "reserve_state": validate_json_value(reserve.to_payload()),
                    **primary_reserve_entry_source_terminal_bindings_payload(
                        ((provider, reserve),)
                    ),
                },
            )
            record_primary_reserve_entry_provider_terminal_event(
                event_log=decisions.event_log,
                provider=provider,
                reserve_state=reserve,
                source_terminal_event=terminal,
            )
        else:
            decisions.event_log.append(
                "source_reposition_declined",
                {
                    "source_context": validate_json_value(context.to_payload()),
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                },
            )
        state.remove_persisting_effects_by_id(effect_ids=(context.permission_effect_id,))
        return advance()

    return DecisionDispatchHandler(
        decision_type=SELECT_SOURCE_REPOSITION_DECISION_TYPE,
        pre_validator=validate,
        applier=apply,
    )
