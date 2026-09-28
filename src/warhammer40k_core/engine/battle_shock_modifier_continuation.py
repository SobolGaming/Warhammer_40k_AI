"""A pre-roll Battle-shock continuation retains the already-applied source action."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierApplication,
    BattleShockModifierApplicationPayload,
)
from warhammer40k_core.engine.battle_shock_modifier_evaluation import prepare_battle_shock_modifiers
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    BattleShockResolutionResult,
    resolve_battle_shock_test_with_optional_reroll,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_battle_shock_after_modifier_choices(
    *,
    state: GameState,
    decisions: DecisionController,
    request: BattleShockTestRequest,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    battle_shock_hooks: BattleShockHookRegistry,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    passed_state_policy: BattleShockPassedStatePolicy,
    source_kind: str,
    base_payload: dict[str, JsonValue],
    resolved_event_types: tuple[str, ...],
    pending_phase_body_status: str,
    requested_event_types: tuple[str, ...] = ("battle_shock_test_requested",),
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...] = (),
) -> BattleShockResolutionResult:
    execution = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "request": request.to_payload(),
                "active_player_id": active_player_id,
                "phase": phase.value,
                "phase_start_battle_shocked_unit_ids": list(phase_start_battle_shocked_unit_ids),
                "passed_state_policy": passed_state_policy.value,
                "source_kind": source_kind,
                "base_payload": base_payload,
                "resolved_event_types": list(resolved_event_types),
                "pending_phase_body_status": pending_phase_body_status,
                "requested_event_types": list(requested_event_types),
                "additional_modifier_applications": [
                    application.to_payload() for application in additional_modifier_applications
                ],
            }
        ),
    )
    prepared = prepare_battle_shock_modifiers(
        state=state,
        decisions=decisions,
        request=request,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        battle_shock_hooks=battle_shock_hooks,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        additional_modifier_applications=additional_modifier_applications,
        source_context={"continuation": "battle_shock_modifiers", "execution": execution},
    )
    if prepared.pending_status is not None:
        return BattleShockResolutionResult(
            resolved_payload=None, pending_status=prepared.pending_status
        )
    request = prepared.request
    for event_type in requested_event_types:
        decisions.event_log.append(
            event_type,
            {
                **base_payload,
                "battle_shock_test_request": validate_json_value(request.to_payload()),
            },
        )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    return resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=battle_shock_hooks,
        request=request,
        roll_state=manager.roll(request.spec),
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        passed_state_policy=passed_state_policy,
        source_kind=source_kind,
        base_payload=base_payload,
        resolved_event_types=resolved_event_types,
        pending_phase_body_status=pending_phase_body_status,
        additional_modifier_applications=additional_modifier_applications,
    )


def resume_battle_shock_modifier_choices(
    *,
    state: GameState,
    decisions: DecisionController,
    context: dict[str, JsonValue],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    runtime_modifier_registry: RuntimeModifierRegistry,
    battle_shock_hooks: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    execution = context["execution"]
    if not isinstance(execution, dict):
        raise GameLifecycleError("Battle-shock modifier continuation execution must be an object.")
    expected = {
        "request",
        "active_player_id",
        "phase",
        "phase_start_battle_shocked_unit_ids",
        "passed_state_policy",
        "source_kind",
        "base_payload",
        "resolved_event_types",
        "pending_phase_body_status",
        "requested_event_types",
        "additional_modifier_applications",
    }
    if set(execution) != expected:
        raise GameLifecycleError("Battle-shock modifier execution fields drifted.")
    request_payload, base = execution["request"], execution["base_payload"]
    applications = execution["additional_modifier_applications"]
    if (
        not isinstance(request_payload, dict)
        or not isinstance(base, dict)
        or not isinstance(applications, list)
    ):
        raise GameLifecycleError("Battle-shock modifier execution payloads are invalid.")
    request = BattleShockTestRequest.from_payload(
        cast(BattleShockTestRequestPayload, request_payload)
    )
    if request.battle_round != state.battle_round or request.game_id != state.game_id:
        raise GameLifecycleError("Battle-shock modifier execution occurrence drifted.")
    source_kind = _string(execution, "source_kind")
    resolution = resolve_battle_shock_after_modifier_choices(
        state=state,
        decisions=decisions,
        request=request,
        ability_index=ability_indexes_by_player_id[request.player_id],
        runtime_modifier_registry=runtime_modifier_registry,
        battle_shock_hooks=battle_shock_hooks,
        active_player_id=_string(execution, "active_player_id"),
        phase=BattlePhase(_string(execution, "phase")),
        phase_start_battle_shocked_unit_ids=_strings(
            execution, "phase_start_battle_shocked_unit_ids"
        ),
        passed_state_policy=BattleShockPassedStatePolicy(_string(execution, "passed_state_policy")),
        source_kind=source_kind,
        base_payload=base,
        resolved_event_types=_strings(execution, "resolved_event_types"),
        pending_phase_body_status=_string(execution, "pending_phase_body_status"),
        requested_event_types=_strings(execution, "requested_event_types"),
        additional_modifier_applications=tuple(
            BattleShockModifierApplication.from_payload(
                cast(BattleShockModifierApplicationPayload, value)
            )
            for value in applications
        ),
    )
    if source_kind == "catalog_selected_target_effect":
        from warhammer40k_core.engine.catalog_selected_target_battle_shock_reroll import (
            continue_catalog_selected_target_battle_shock_resolution,
        )

        return continue_catalog_selected_target_battle_shock_resolution(
            state=state,
            decisions=decisions,
            battle_shock_resolution=resolution,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
        )
    if source_kind in {"desperate_escape_battle_shock", "forced_desperate_escape_battle_shock"}:
        from warhammer40k_core.engine.phases.movement_battle_shock_continuation import (
            record_desperate_escape_battle_shock_resolution,
        )

        return record_desperate_escape_battle_shock_resolution(
            state=state,
            decisions=decisions,
            battle_shock_hooks=battle_shock_hooks,
            resolution=resolution,
            reroll_result_id=None,
            defer_completion=True,
        )
    return resolution.pending_status


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload[key]
    if type(value) is not str or not value:
        raise GameLifecycleError("Battle-shock modifier execution string is invalid.")
    return value


def _strings(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    values = payload[key]
    if not isinstance(values, list) or any(type(value) is not str for value in values):
        raise GameLifecycleError("Battle-shock modifier execution string list is invalid.")
    return tuple(cast(list[str], values))


def battle_shock_modifier_execution(request: DecisionRequest) -> dict[str, JsonValue] | None:
    from warhammer40k_core.engine.modifier_evaluation import SELECT_MODIFIER_IGNORES_DECISION_TYPE

    if request.decision_type != SELECT_MODIFIER_IGNORES_DECISION_TYPE:
        return None
    payload = request.payload
    if not isinstance(payload, dict) or not isinstance(payload["source_context"], dict):
        raise GameLifecycleError("Battle-shock modifier request lacks source context.")
    context = payload["source_context"]
    if context.get("continuation") != "battle_shock_modifiers":
        return None
    execution = context["execution"]
    if not isinstance(execution, dict):
        raise GameLifecycleError("Battle-shock modifier request execution is invalid.")
    return execution
