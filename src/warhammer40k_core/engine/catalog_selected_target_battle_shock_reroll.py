from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    apply_battle_shock_reroll_resolution_decision,
    is_battle_shock_reroll_request,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    complete_catalog_selected_target_remaining_battle_shock_reroll,
    retain_catalog_selected_target_battle_shock_continuation,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND = "catalog_selected_target_effect"


def is_catalog_selected_target_battle_shock_reroll_request(
    request: DecisionRequest,
) -> bool:
    return is_battle_shock_reroll_request(
        request,
        source_kind=CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND,
    )


def apply_catalog_selected_target_battle_shock_reroll_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        continue_selected_target_effect_records,
        selected_target_json_object_tuple,
    )
    from warhammer40k_core.engine.catalog_selected_target_effects_support import (
        payload_int,
        payload_object,
        payload_string,
    )
    from warhammer40k_core.engine.catalog_selected_target_event import (
        append_selected_target_event,
    )

    battle_shock_resolution = apply_battle_shock_reroll_resolution_decision(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=battle_shock_hooks,
        expected_source_kind=CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND,
        expected_passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
    )
    complete_catalog_selected_target_remaining_battle_shock_reroll(
        state=state,
        decisions=decisions,
        result=result,
    )
    resolved_payload = battle_shock_resolution.resolved_payload
    if resolved_payload is None:
        raise GameLifecycleError("Selected-target Battle-shock reroll did not resolve.")
    try:
        phase = BattlePhase(payload_string(resolved_payload, key="phase"))
    except ValueError as exc:
        raise GameLifecycleError("Selected-target Battle-shock phase is unsupported.") from exc
    final_event_type = payload_string(
        resolved_payload,
        key="selected_target_final_event_type",
    )
    if battle_shock_resolution.pending_status is not None:
        return retain_catalog_selected_target_battle_shock_continuation(
            state=state,
            decisions=decisions,
            battle_shock_hooks=battle_shock_hooks,
            resolution=battle_shock_resolution,
            phase=phase,
            final_event_type=final_event_type,
        )
    original_result = DecisionResult.from_payload(
        cast(
            DecisionResultPayload,
            payload_object(resolved_payload.get("selected_target_decision_result")),
        )
    )
    selected_payload = payload_object(resolved_payload.get("selected_target_payload"))
    recorded_effects = list(
        selected_target_json_object_tuple(
            resolved_payload,
            key="selected_target_recorded_effects_before_battle_shock",
        )
    )
    recorded_effects.append(resolved_payload)
    remaining_records = selected_target_json_object_tuple(
        resolved_payload,
        key="selected_target_remaining_effect_records_after_battle_shock",
    )
    if remaining_records:
        recording = continue_selected_target_effect_records(
            state=state,
            decisions=decisions,
            result=original_result,
            payload=selected_payload,
            effect_records=remaining_records,
            phase=phase,
            event_type=final_event_type,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            initial_recorded=tuple(recorded_effects),
            effect_index_offset=payload_int(
                resolved_payload,
                key="selected_target_remaining_effect_start_index",
            ),
        )
        if recording.pending_status is not None:
            return recording.pending_status
        effects = recording.effects
    else:
        effects = tuple(recorded_effects)
    append_selected_target_event(
        state=state,
        decisions=decisions,
        result=original_result,
        payload=selected_payload,
        effects=effects,
        event_type=final_event_type,
        phase=phase,
    )
    return None


__all__ = (
    "CATALOG_SELECTED_TARGET_BATTLE_SHOCK_SOURCE_KIND",
    "apply_catalog_selected_target_battle_shock_reroll_decision",
    "is_catalog_selected_target_battle_shock_reroll_request",
)
