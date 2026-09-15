from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.charge_roll_flow import continue_charge_roll
from warhammer40k_core.engine.charge_target_continuation import continue_charge_move
from warhammer40k_core.engine.charge_targets import (
    charge_target_candidates as _charge_target_candidates,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.phases import charge as _charge
from warhammer40k_core.engine.phases import charge_modifier_ignore as _modifier_ignore
from warhammer40k_core.engine.phases.charge_move_completed_hooks import (
    resolve_charge_move_completed_hooks,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue


def begin_phase(
    self: _charge.ChargePhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None = None,
) -> LifecycleStatus:
    _charge._validate_charge_phase_state(state)
    charge_state = _charge._ensure_charge_phase_state(state=state)
    pending_distance_state = charge_state.move_pending_distance_state()
    if pending_distance_state is not None:
        return continue_charge_move(state=state, decisions=decisions, handler=self)
    if charge_state.active_selection is not None:
        status = continue_charge_roll(state=state, decisions=decisions, handler=self)
        if status is not None:
            return status
        charge_state = _charge._ensure_charge_phase_state(state=state)
    move_completed_status = resolve_charge_move_completed_hooks(
        state=state, decisions=decisions, handler=self, movement_action=_charge.CHARGE_MOVE_ACTION
    )
    if move_completed_status is not None:
        return move_completed_status
    from warhammer40k_core.engine.interrupted_charge import finish_interrupted_charge_if_complete

    interrupted = finish_interrupted_charge_if_complete(
        state=state, decisions=decisions, reaction_queue=reaction_queue
    )
    if interrupted is not None:
        return interrupted
    if charge_state.phase_complete:
        return _charge._complete_charge_phase_or_request_heroic_intervention(
            handler=self, state=state, decisions=decisions, reaction_queue=reaction_queue
        )
    legal_unit_ids = _charge._legal_charging_unit_ids(
        state=state,
        charge_state=charge_state,
        ruleset_descriptor=_charge._ruleset_descriptor_for_handler(self),
        charge_target_restriction_hooks=self.charge_target_restriction_hooks,
    )
    if not legal_unit_ids:
        state.replace_charge_phase_state(charge_state.with_phase_complete())
        interrupted = finish_interrupted_charge_if_complete(
            state=state, decisions=decisions, reaction_queue=reaction_queue
        )
        if interrupted is not None:
            return interrupted
        return _charge._complete_charge_phase_or_request_heroic_intervention(
            handler=self, state=state, decisions=decisions, reaction_queue=reaction_queue
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=_charge.SELECT_CHARGING_UNIT_DECISION_TYPE,
        actor_id=_charge._active_player_id(state),
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": _charge._active_player_id(state),
            }
        ),
        options=_modifier_ignore.charging_unit_options_with_modifier_ignore_choices(
            state=state,
            unit_ids=legal_unit_ids,
            include_complete=charge_state.interruption is None,
            ruleset_descriptor=_charge._ruleset_descriptor_for_handler(self),
            ability_index=_charge._ability_index_for_player(
                self.ability_indexes_by_player_id, player_id=_charge._active_player_id(state)
            ),
            runtime_modifier_registry=self.runtime_modifier_registry,
            active_player_id=_charge._active_player_id(state),
            unit_lookup=_charge._unit_by_id,
            target_candidate_provider=_charge_target_candidates,
            charge_target_restriction_hooks=self.charge_target_restriction_hooks,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "charging_unit_selection_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _charge._active_player_id(state),
                "phase": BattlePhase.CHARGE.value,
                "request_id": request.request_id,
                "legal_unit_count": len(legal_unit_ids),
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "battle_round": state.battle_round,
            "active_player_id": _charge._active_player_id(state),
            "legal_unit_count": len(legal_unit_ids),
        },
    )
