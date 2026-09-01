from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine.attached_unit_reconciliation import (
    validate_attached_rules_unit_identity_after_destruction,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_string,
    selected_payload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def append_selected_target_event(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: Mapping[str, object],
    effects: tuple[dict[str, JsonValue], ...],
    event_type: str,
    phase: BattlePhase,
) -> None:
    use_ability = payload.get("use_ability", True)
    if type(use_ability) is not bool:
        raise GameLifecycleError("Catalog selected-target use_ability must be bool.")
    selected_target_id: str | None = None
    if use_ability:
        selected_target_id = payload_string(
            selected_payload(payload),
            key="target_unit_instance_id",
        )
        validate_attached_rules_unit_identity_after_destruction(
            state=state,
            rules_unit_instance_id=selected_target_id,
        )
    decisions.event_log.append(
        event_type,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": phase.value,
                "active_player_id": state.active_player_id,
                "player_id": result.actor_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "hook_id": payload_string(payload, key="hook_id"),
                "catalog_record_id": payload_string(payload, key="catalog_record_id"),
                "source_rule_id": payload_string(payload, key="source_rule_id"),
                "source_unit_instance_id": payload_string(
                    payload,
                    key="source_unit_instance_id",
                ),
                "source_model_instance_id": payload.get("source_model_instance_id"),
                "selection_clause_id": payload_string(payload, key="selection_clause_id"),
                "use_ability": use_ability,
                "target_unit_instance_id": selected_target_id,
                "attack_sequence_id": payload.get("attack_sequence_id"),
                "attack_sequence_completed_event_id": (
                    payload.get("attack_sequence_completed_event_id")
                ),
                "persisting_effects": list(effects),
            }
        ),
    )
