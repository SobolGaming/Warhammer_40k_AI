"""Core finite embark contract for a source-owned no-movement occasion.

Source providers own when the permission is issued. This module does not load
the named ability or infer its timing from the Core FAQ.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import (
    DecisionApplier,
    DecisionDispatchHandler,
    DecisionPreValidator,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import (
    DECLINE_EMBARK_OPTION_ID,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
)
from warhammer40k_core.engine.transport_embark_context import (
    NoMovementEmbarkContext,
    NoMovementEmbarkContextPayload,
)
from warhammer40k_core.engine.transports import (
    EmbarkSelection,
    EmbarkSelectionPayload,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
)

NO_MOVEMENT_EMBARK_PERMISSION_EFFECT_KIND = "no_movement_embark_permission"


def validate_source_embark_selection(
    *,
    selection: EmbarkSelection,
    persisting_effects: tuple[PersistingEffect, ...],
    turn_player_id: str,
) -> None:
    context = selection.source_context
    if context is None:
        raise GameLifecycleError("Source Embark requires its source context.")
    matches = tuple(
        effect for effect in persisting_effects if effect.effect_id == context.permission_effect_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Source Embark requires its current permission effect.")
    (effect,) = matches
    payload = effect.effect_payload
    if (
        not isinstance(payload, dict)
        or set(payload) != {"effect_kind", "source_context", "allow_after_disembark"}
        or payload["effect_kind"] != NO_MOVEMENT_EMBARK_PERMISSION_EFFECT_KIND
        or _context(payload["source_context"]) != context
        or effect.owner_player_id != selection.player_id
        or effect.source_rule_id != context.source_rule_id
        or effect.target_unit_instance_ids != (selection.unit_instance_id,)
        or effect.started_battle_round != context.battle_round
        or effect.started_phase is not context.phase
        or context.turn_player_id != turn_player_id
        or type(payload["allow_after_disembark"]) is not bool
    ):
        raise GameLifecycleError("Source Embark permission/context authority drift.")
    expected_overrides = (
        (
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                source_rule_id=context.source_rule_id,
            ),
        )
        if payload["allow_after_disembark"]
        else ()
    )
    if selection.restriction_overrides != expected_overrides:
        raise GameLifecycleError("Source Embark post-disembark permission drift.")


def no_movement_embark_permission_effect(
    *,
    context: NoMovementEmbarkContext,
    owner_player_id: str,
    allow_after_disembark: bool,
) -> PersistingEffect:
    if type(context) is not NoMovementEmbarkContext or type(allow_after_disembark) is not bool:
        raise GameLifecycleError("No-movement Embark requires typed source permission.")
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
            "effect_kind": NO_MOVEMENT_EMBARK_PERMISSION_EFFECT_KIND,
            "source_context": validate_json_value(context.to_payload()),
            "allow_after_disembark": allow_after_disembark,
        },
    )


def current_source_embark_context(
    *,
    state: GameState,
    unit_instance_id: str,
) -> NoMovementEmbarkContext | None:
    contexts: list[NoMovementEmbarkContext] = []
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != (
            NO_MOVEMENT_EMBARK_PERMISSION_EFFECT_KIND
        ):
            continue
        if set(payload) != {"effect_kind", "source_context", "allow_after_disembark"}:
            raise GameLifecycleError("No-movement Embark permission schema drift.")
        context = _context(payload["source_context"])
        if (
            context.permission_effect_id != effect.effect_id
            or context.source_rule_id != effect.source_rule_id
            or effect.target_unit_instance_ids != (context.unit_instance_id,)
            or type(payload["allow_after_disembark"]) is not bool
        ):
            raise GameLifecycleError("No-movement Embark permission identity drift.")
        if (
            context.battle_round == state.battle_round
            and context.turn_player_id == state.active_player_id
            and context.phase is state.current_battle_phase
        ):
            contexts.append(context)
    if len(contexts) > 1:
        raise GameLifecycleError("No-movement Embark requires one permitting source occasion.")
    return contexts[0] if contexts else None


def _options(
    *,
    state: GameState,
    context: NoMovementEmbarkContext,
) -> tuple[DecisionOption, ...]:
    from warhammer40k_core.engine.phases.movement_fall_back_embark import (
        _post_move_embark_options,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if (
        state.stage is not GameLifecycleStage.BATTLE
        or current_source_embark_context(
            state=state,
            unit_instance_id=context.unit_instance_id,
        )
        != context
    ):
        return ()
    (effect,) = tuple(
        effect
        for effect in state.persisting_effects_for_unit(context.unit_instance_id)
        if effect.effect_id == context.permission_effect_id
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=context.unit_instance_id)
    if effect.owner_player_id != unit.owner_player_id:
        raise GameLifecycleError("No-movement Embark permission owner drift.")
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    overrides = (
        (
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                source_rule_id=context.source_rule_id,
            ),
        )
        if payload["allow_after_disembark"]
        else ()
    )
    return _post_move_embark_options(
        state=state,
        unit_instance_id=context.unit_instance_id,
        movement_phase_action=TransportMovementStatus.NOT_MOVED,
        source_context=context,
        restriction_overrides=overrides,
    )


def request_source_embark(
    *,
    state: GameState,
    decisions: DecisionController,
    context: NoMovementEmbarkContext,
) -> LifecycleStatus | None:
    """Issue the shared finite request at an explicit source-provider occasion."""
    options = _options(state=state, context=context)
    if not options:
        return None
    selection = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, options[0].payload))
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        actor_id=selection.player_id,
        decision_type=SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": context.phase.value,
            "unit_instance_id": context.unit_instance_id,
            "source_context": validate_json_value(context.to_payload()),
            "spatial_context_hash": state.physical_proposal_context_hash(),
        },
        options=(
            DecisionOption(
                option_id=DECLINE_EMBARK_OPTION_ID,
                label="Decline Embark",
                payload={
                    "transport_decision": DECLINE_EMBARK_OPTION_ID,
                    "unit_instance_id": context.unit_instance_id,
                },
            ),
            *options,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": context.phase.value,
            "phase_body_status": "embark_choice_required",
            "unit_instance_id": context.unit_instance_id,
        },
    )


def _source_request(request: DecisionRequest) -> bool:
    return isinstance(request.payload, dict) and "source_context" in request.payload


def source_embark_dispatch_handler(
    *,
    state_provider: Callable[[], GameState],
    decisions: DecisionController,
    advance: Callable[[], LifecycleStatus],
    ordinary_validator: DecisionPreValidator,
    ordinary_applier: DecisionApplier,
) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        if not _source_request(request):
            return ordinary_validator(request, result)
        result.validate_for_request(request)
        state = state_provider()
        payload = cast(dict[str, JsonValue], request.payload)
        context = _context(payload["source_context"])
        options = _options(state=state, context=context)
        offered = tuple(
            option for option in request.options if option.option_id != DECLINE_EMBARK_OPTION_ID
        )
        if (
            not options
            or offered != options
            or payload["spatial_context_hash"] != state.physical_proposal_context_hash()
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Source Embark eligibility changed.",
                payload={"invalid_reason": "source_embark_context_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        if not _source_request(record.request):
            return ordinary_applier(record, result)
        from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
        from warhammer40k_core.engine.phases.movement_rules_units import (
            representative_movement_placement,
            rules_unit_placement_for_movement,
        )
        from warhammer40k_core.engine.transport_embark_mutation import apply_embark_mutation
        from warhammer40k_core.engine.transports import resolve_embark

        state = state_provider()
        request_payload = cast(dict[str, JsonValue], record.request.payload)
        context = _context(request_payload["source_context"])
        if result.selected_option_id == DECLINE_EMBARK_OPTION_ID:
            decisions.event_log.append(
                "source_embark_declined",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": context.phase.value,
                    "unit_instance_id": context.unit_instance_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "source_context": validate_json_value(context.to_payload()),
                },
            )
        else:
            selection = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, result.payload))
            scenario = battlefield_scenario_for_state(state=state)
            _, placement = rules_unit_placement_for_movement(
                state=state,
                scenario=scenario,
                unit_instance_id=context.unit_instance_id,
            )
            cargo = state.transport_cargo_state_for_transport(selection.transport_unit_instance_id)
            if cargo is None or state.active_player_id is None:
                raise GameLifecycleError("Source Embark cargo/turn authority is missing.")
            from warhammer40k_core.engine.phases.movement_fall_back_embark import (
                _embark_persisting_effects,  # pyright: ignore[reportPrivateUsage]
            )

            resolution = resolve_embark(
                scenario=scenario,
                movement_history=tuple(state.phase_movement_history),
                turn_player_id=state.active_player_id,
                cargo_state=cargo,
                selection=selection,
                unit_placement=representative_movement_placement(placement),
                transport_placement=scenario.battlefield_state.unit_placement_by_id(
                    selection.transport_unit_instance_id
                ),
                persisting_effects=_embark_persisting_effects(
                    state=state, unit_instance_id=context.unit_instance_id
                ),
            )
            if not resolution.is_valid:
                raise GameLifecycleError("Accepted source Embark resolution drift.")
            apply_embark_mutation(
                state=state, decisions=decisions, embark=resolution, result=result
            )
            movement = state.movement_phase_state
            if (
                movement is not None
                and movement.active_selection is not None
                and (movement.active_selection.unit_instance_id == context.unit_instance_id)
            ):
                state.replace_movement_phase_state(
                    movement.with_activation_complete(
                        context.unit_instance_id,
                        maximum_model_distance_inches=0.0,
                        maximum_model_horizontal_distance_inches=0.0,
                    )
                )
        state.remove_persisting_effects_by_id(effect_ids=(context.permission_effect_id,))
        return advance()

    return DecisionDispatchHandler(
        decision_type=SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        pre_validator=validate,
        applier=apply,
    )


def _context(value: JsonValue) -> NoMovementEmbarkContext:
    if not isinstance(value, dict):
        raise GameLifecycleError("No-movement Embark context must be an object.")
    return NoMovementEmbarkContext.from_payload(cast(NoMovementEmbarkContextPayload, value))
