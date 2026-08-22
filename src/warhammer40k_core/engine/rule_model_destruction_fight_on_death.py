from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def fight_on_death_activation_result_id_for_rule_destruction(
    *,
    state: GameState,
    context: dict[str, JsonValue],
    reaction_result_id: str,
) -> str:
    requested_result_id = _validate_identifier("reaction_result_id", reaction_result_id)
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.active_activation is None:
        return requested_result_id
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Active Fight On Death continuation requires the Fight phase.")
    activation = fight_state.active_activation
    target_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        context.get("rules_unit_instance_id"),
    )
    target_view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    active_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    if target_view.unit_instance_id != active_view.unit_instance_id:
        raise GameLifecycleError("Rule Fight On Death cannot replace an unrelated activation.")
    controller_player_id = _validate_identifier(
        "destroyed_model_controller_player_id",
        context.get("destroyed_model_controller_player_id"),
    )
    if activation.player_id != controller_player_id:
        raise GameLifecycleError("Rule Fight On Death active activation controller drift.")
    return activation.result_id


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = ("fight_on_death_activation_result_id_for_rule_destruction",)
