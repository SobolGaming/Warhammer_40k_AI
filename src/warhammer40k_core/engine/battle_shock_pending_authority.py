from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestRequest,
    battle_shock_leadership_target_for_rules_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    PendingBattleShockRerollAuthority,
    parse_pending_battle_shock_reroll_authority,
)
from warhammer40k_core.engine.battle_shock_source_family_authority import (
    validate_pending_battle_shock_source_family_authority,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_unit_geometry import (
    placed_alive_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


def validate_live_pending_battle_shock_reroll_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_request: DecisionRequest,
    runtime_content_bundle: RuntimeContentBundle,
) -> PendingBattleShockRerollAuthority:
    authority = parse_pending_battle_shock_reroll_authority(pending_request)
    if (
        state.game_id != authority.test_request.game_id
        or state.battle_round != authority.test_request.battle_round
        or state.active_player_id != authority.active_player_id
        or state.current_battle_phase is not authority.phase
    ):
        raise GameLifecycleError("Pending Battle-shock live occurrence drifted.")
    request_payload = validate_json_value(authority.test_request.to_payload())
    request_events = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_payload
    )
    if len(request_events) != 1:
        raise GameLifecycleError("Pending Battle-shock request occurrence is ambiguous.")
    request_event_index, request_event = request_events[0]
    expected_request_context = {
        **authority.base_payload,
        "battle_shock_test_request": request_payload,
    }
    if request_event.payload != validate_json_value(expected_request_context):
        raise GameLifecycleError("Pending Battle-shock request event drifted.")
    roll_events = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "dice_rolled"
        and event.payload == authority.initial_roll_state.original_result.to_payload()
    )
    pending_events = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested"
        and event.payload == pending_request.to_payload()
    )
    if (
        len(roll_events) != 1
        or len(pending_events) != 1
        or not request_event_index < roll_events[0][0] < pending_events[0][0]
        or any(
            record.request.request_id == pending_request.request_id for record in decision_records
        )
        or any(
            _decision_recorded_request_id(event) == pending_request.request_id
            for event in event_records
        )
    ):
        raise GameLifecycleError("Pending Battle-shock decision occurrence drifted.")
    expected_request = _expected_live_test_request(
        state=state,
        authority=authority,
        runtime_content_bundle=runtime_content_bundle,
    )
    if authority.test_request != expected_request:
        raise GameLifecycleError("Pending Battle-shock request semantics drifted.")
    validate_pending_battle_shock_source_family_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        authority=authority,
        runtime_content_bundle=runtime_content_bundle,
    )
    expected_permission = runtime_content_bundle.battle_shock_hook_registry.reroll_permission_for(
        BattleShockRerollPermissionContext(
            state=state,
            request=authority.test_request,
            active_player_id=authority.active_player_id,
            phase=authority.phase,
            phase_start_battle_shocked_unit_ids=(authority.phase_start_battle_shocked_unit_ids),
        )
    )
    if expected_permission is None or authority.permission != expected_permission:
        raise GameLifecycleError("Pending Battle-shock reroll permission drifted.")
    return authority


def invalid_live_pending_battle_shock_reroll_status(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_request: DecisionRequest,
    result: DecisionResult,
    runtime_content_bundle: RuntimeContentBundle,
) -> LifecycleStatus | None:
    if not (
        isinstance(pending_request.payload, dict)
        and "battle_shock_context" in pending_request.payload
    ):
        return None
    try:
        validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=pending_request,
            runtime_content_bundle=runtime_content_bundle,
        )
        result.validate_for_request(pending_request)
    except (
        DecisionError,
        GameLifecycleError,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Battle-shock reroll submission is no longer authoritative.",
            payload={"invalid_reason": "battle_shock_reroll_authority_drift"},
        )
    return None


def _expected_live_test_request(
    *,
    state: GameState,
    authority: PendingBattleShockRerollAuthority,
    runtime_content_bundle: RuntimeContentBundle,
) -> BattleShockTestRequest:
    retained = authority.test_request
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=retained.unit_instance_id,
    )
    if rules_unit.owner_player_id != retained.player_id:
        raise GameLifecycleError("Pending Battle-shock target owner drifted.")
    current_model_ids = tuple(
        sorted(
            model.model_id
            for model in placed_alive_geometry_models_for_rules_unit(
                state=state,
                unit_instance_id=rules_unit.unit_instance_id,
            )
        )
    )
    if not current_model_ids:
        raise GameLifecycleError("Pending Battle-shock target is no longer placed.")
    ability_index = runtime_content_bundle.ability_indexes_by_player_id.get(retained.player_id)
    if ability_index is None:
        raise GameLifecycleError("Pending Battle-shock target lacks ability authority.")
    dice_expression = runtime_content_bundle.battle_shock_hook_registry.dice_expression_for(
        BattleShockDiceExpressionContext(
            state=state,
            player_id=retained.player_id,
            unit_instance_id=retained.unit_instance_id,
            reason=retained.reason,
            active_player_id=authority.active_player_id,
            phase=authority.phase,
            default_expression=DiceExpression(quantity=2, sides=6),
            phase_start_battle_shocked_unit_ids=(authority.phase_start_battle_shocked_unit_ids),
        )
    )
    return replace(
        retained,
        leadership_target=battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=current_model_ids,
            ability_index=ability_index,
            state=state,
            runtime_modifier_registry=runtime_content_bundle.runtime_modifier_registry,
        ),
        below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
            rules_unit=rules_unit,
            starting_strength=state.starting_strength_record_for_unit(rules_unit.unit_instance_id),
            current_model_ids=current_model_ids,
        ),
        spec=replace(retained.spec, expression=dice_expression),
    )


def _decision_recorded_request_id(event: EventRecord) -> str | None:
    if event.event_type != "decision_recorded" or not isinstance(event.payload, dict):
        return None
    request = event.payload.get("request")
    if not isinstance(request, dict):
        return None
    request_id = request.get("request_id")
    return request_id if type(request_id) is str else None


__all__ = (
    "invalid_live_pending_battle_shock_reroll_status",
    "validate_live_pending_battle_shock_reroll_authority",
)
