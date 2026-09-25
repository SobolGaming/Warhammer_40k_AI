"""Source-linked Core highest/lowest choices through the shared decision authority."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import msgspec

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.dice_extremum import (
    DiceExtremum,
    DiceExtremumSelection,
    extremum_indices,
)
from warhammer40k_core.engine.active_player_boundary_history import (
    active_player_authority_before_event,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_roll_history import latest_roll_state
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_dice_results_2026_09 import (
    HIGHEST_LOWEST_SOURCE_ID,
)

SELECT_DICE_EXTREMUM_DECISION_TYPE = "select_dice_extremum"


class ExtremumContext(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    roll_state: DiceRollStatePayload
    extremum: DiceExtremum
    referring_source_rule_id: str
    reference_id: str
    source_rule_id: str
    player_id: str
    secret: bool
    visibility_source: str
    battle_round: int
    turn_player_id: str | None
    battle_phase: str | None
    clock_event_id: str
    scope_request_ids: tuple[str, ...]


def _context(request: DecisionRequest) -> ExtremumContext:
    try:
        result = msgspec.convert(request.payload, type=ExtremumContext, strict=True)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("Malformed highest/lowest context.") from exc
    if (
        result.source_rule_id != HIGHEST_LOWEST_SOURCE_ID
        or not result.referring_source_rule_id.strip()
        or not result.reference_id.strip()
        or result.visibility_source != "dice_extremum"
    ):
        raise GameLifecycleError("Highest/lowest source identity drift.")
    return result


def _request(*, request_id: str, context: ExtremumContext) -> DecisionRequest:
    state = DiceRollState.from_payload(context.roll_state)
    indices = extremum_indices(state, context.extremum)
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_DICE_EXTREMUM_DECISION_TYPE,
        actor_id=context.player_id,
        payload=validate_json_value(msgspec.to_builtins(context)),
        options=tuple(
            DecisionOption(
                option_id=f"{state.original_result.roll_id}:component-{index}",
                label=(
                    f"{context.extremum.value.title()} die {index + 1}: "
                    f"{state.current_values[index]}"
                ),
                payload={
                    "component_index": index,
                    "component_id": f"{state.original_result.roll_id}:component-{index}",
                    "value": state.current_values[index],
                },
            )
            for index in indices
        ),
    )


def request_dice_extremum(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState,
    extremum: DiceExtremum,
    referring_source_rule_id: str,
    reference_id: str,
) -> DiceExtremumSelection | DecisionRequest:
    """Resolve one source's reference; a tie suspends its engine consumer.

    Callers resume by calling this owner with the same source and current roll.
    An equal numeric result never licenses choosing a physical die locally.
    """
    if type(referring_source_rule_id) is not str or not referring_source_rule_id.strip():
        raise GameLifecycleError("Highest/lowest reference requires its source rule ID.")
    if type(reference_id) is not str or not reference_id.strip():
        raise GameLifecycleError("Highest/lowest reference requires its occurrence ID.")
    current = latest_roll_state(decisions=decisions, roll_id=roll_state.original_result.roll_id)
    if current != roll_state:
        raise GameLifecycleError("Highest/lowest reference has stale dice state.")
    indices = extremum_indices(current, extremum)
    if len(indices) == 1:
        return DiceExtremumSelection(current, extremum, indices[0])
    for record in reversed(decisions.records):
        if record.request.decision_type != SELECT_DICE_EXTREMUM_DECISION_TYPE:
            continue
        previous = _context(record.request)
        if (
            previous.roll_state == current.to_payload()
            and previous.extremum is extremum
            and previous.referring_source_rule_id == referring_source_rule_id
            and previous.reference_id == reference_id
        ):
            selected = cast(dict[str, JsonValue], record.result.payload)
            return DiceExtremumSelection(current, extremum, cast(int, selected["component_index"]))
    player_id = state.effective_active_player_id()
    if player_id is None:
        raise GameLifecycleError("Tied dice require an effective active player.")
    authority = active_player_authority_before_event(
        state=state, decisions=decisions, event_index=len(decisions.event_log.records)
    )
    if (
        authority.effective_player_id != player_id
        or authority.battle_round != state.battle_round
        or authority.turn_player_id != state.active_player_id
        or authority.phase != _battle_phase(state)
        or authority.scopes != state.active_player_scopes
    ):
        raise GameLifecycleError(
            "Highest/lowest live active-player authority differs from history."
        )
    secret = _roll_is_secret(decisions, current, player_id)
    context = ExtremumContext(
        current.to_payload(),
        extremum,
        referring_source_rule_id,
        reference_id,
        HIGHEST_LOWEST_SOURCE_ID,
        player_id,
        secret,
        "dice_extremum",
        state.battle_round,
        state.active_player_id,
        _battle_phase(state),
        authority.clock_event_id,
        tuple(scope.selection_request_id for scope in authority.scopes),
    )
    for pending in decisions.queue.pending_requests:
        if (
            pending.decision_type == SELECT_DICE_EXTREMUM_DECISION_TYPE
            and _context(pending) == context
        ):
            return pending
    if decisions.queue.pending_requests:
        raise GameLifecycleError("Highest/lowest reference cannot bypass a pending decision.")
    request = _request(request_id=state.next_decision_request_id(), context=context)
    decisions.event_log.append("dice_extremum_referenced", _reference_payload(request))
    return decisions.request_decision(request)


def dice_extremum_dispatch_handler(
    *,
    state_provider: Callable[[], GameState],
    decisions: DecisionController,
    advance: Callable[[], LifecycleStatus],
) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = state_provider()
        try:
            result.validate_for_request(request)
            context = _context(request)
            current = latest_roll_state(
                decisions=decisions, roll_id=context.roll_state["original_result"]["roll_id"]
            )
            _validate_current_reference(state, decisions, request, context, current)
        except (DecisionError, GameLifecycleError, DiceRollSpecError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"invalid_reason": "dice_extremum_context_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        if validate(record.request, result) is not None:
            raise GameLifecycleError("Accepted highest/lowest decision failed revalidation.")
        decisions.event_log.append("dice_extremum_selected", _selection_payload(record))
        return advance()

    return DecisionDispatchHandler(SELECT_DICE_EXTREMUM_DECISION_TYPE, validate, apply)


def _validate_current_reference(
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    context: ExtremumContext,
    current: DiceRollState,
) -> None:
    authority = active_player_authority_before_event(
        state=state, decisions=decisions, event_index=len(decisions.event_log.records)
    )
    if (
        authority.scopes != state.active_player_scopes
        or context.clock_event_id != authority.clock_event_id
        or context.scope_request_ids
        != tuple(scope.selection_request_id for scope in authority.scopes)
        or request != _request(request_id=request.request_id, context=context)
        or current.to_payload() != context.roll_state
        or context.secret != _roll_is_secret(decisions, current, context.player_id)
        or context.player_id != state.effective_active_player_id()
        or context.battle_round != state.battle_round
        or context.turn_player_id != state.active_player_id
        or context.battle_phase != (_battle_phase(state))
        or len(extremum_indices(current, context.extremum)) < 2
    ):
        raise GameLifecycleError("Highest/lowest dice or active-player context drift.")
    references = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "dice_extremum_referenced"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request.request_id
    )
    if len(references) != 1 or references[0].payload != _reference_payload(request):
        raise GameLifecycleError("Highest/lowest reference lacks its engine source event.")


def _selection_payload(record: DecisionRecord) -> JsonValue:
    context = _context(record.request)
    return validate_json_value(
        {
            "request_id": record.request.request_id,
            "result_id": record.result.result_id,
            "context": msgspec.to_builtins(context),
            "selection": record.result.payload,
            "secret": context.secret,
            "player_id": context.player_id,
            "visibility_source": context.visibility_source,
        }
    )


def validate_dice_extremum_history(*, state: GameState, decisions: DecisionController) -> None:
    references = {
        cast(str, event.payload["request_id"]): event.payload
        for event in decisions.event_log.records
        if event.event_type == "dice_extremum_referenced" and isinstance(event.payload, dict)
    }
    selections = tuple(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "dice_extremum_selected"
    )
    records = tuple(
        record
        for record in decisions.records
        if record.request.decision_type == SELECT_DICE_EXTREMUM_DECISION_TYPE
    )
    if selections != tuple(_selection_payload(record) for record in records):
        raise GameLifecycleError("Highest/lowest decision history drift.")
    requests = tuple(record.request for record in records) + tuple(
        request
        for request in decisions.queue.pending_requests
        if request.decision_type == SELECT_DICE_EXTREMUM_DECISION_TYPE
    )
    reference_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "dice_extremum_referenced"
    )
    if len(references) != len(requests) or len(reference_events) != len(requests):
        raise GameLifecycleError("Highest/lowest reference inventory drift.")
    for request in requests:
        context = _context(request)
        if request != _request(request_id=request.request_id, context=context) or references.get(
            request.request_id
        ) != _reference_payload(request):
            raise GameLifecycleError("Highest/lowest recorded request drift.")
        # Validate against the roll history as it stood when the reference opened.
        prefix = DecisionController()
        for event in decisions.event_log.records:
            if (
                event.event_type == "dice_extremum_referenced"
                and event.payload == _reference_payload(request)
            ):
                break
            prefix.event_log.append(event.event_type, event.payload)
        authority = active_player_authority_before_event(
            state=state, decisions=decisions, event_index=len(prefix.event_log.records)
        )
        if (
            context.battle_round != authority.battle_round
            or context.turn_player_id != authority.turn_player_id
            or context.battle_phase != authority.phase
            or context.player_id != authority.effective_player_id
            or context.clock_event_id != authority.clock_event_id
            or context.scope_request_ids
            != tuple(scope.selection_request_id for scope in authority.scopes)
        ):
            raise GameLifecycleError("Highest/lowest historical active-player authority drift.")
        historical = latest_roll_state(
            decisions=prefix, roll_id=context.roll_state["original_result"]["roll_id"]
        )
        if (
            historical.to_payload() != context.roll_state
            or len(extremum_indices(historical, context.extremum)) < 2
            or context.secret != _roll_is_secret(prefix, historical, context.player_id)
        ):
            raise GameLifecycleError("Highest/lowest recorded dice history drift.")

    for request in decisions.queue.pending_requests:
        if request.decision_type == SELECT_DICE_EXTREMUM_DECISION_TYPE:
            context = _context(request)
            current = latest_roll_state(
                decisions=decisions, roll_id=context.roll_state["original_result"]["roll_id"]
            )
            _validate_current_reference(state, decisions, request, context, current)


def _reference_payload(request: DecisionRequest) -> JsonValue:
    context = _context(request)
    return validate_json_value(
        {
            **request.to_payload(),
            "secret": context.secret,
            "player_id": context.player_id,
            "visibility_source": context.visibility_source,
        }
    )


def _battle_phase(state: GameState) -> str | None:
    phase = state.current_battle_phase
    return None if phase is None else phase.value


def _roll_is_secret(decisions: DecisionController, current: DiceRollState, player_id: str) -> bool:
    rolled = tuple(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and event.payload.get("roll_id") == current.original_result.roll_id
    )
    if len(rolled) != 1:
        raise GameLifecycleError("Highest/lowest reference requires one physical roll event.")
    payload = rolled[0]
    assert isinstance(payload, dict)
    secret = payload.get("secret") is True
    if secret and payload.get("player_id") != player_id:
        raise GameLifecycleError("Active player cannot choose from another player's secret dice.")
    return secret
