"""Authenticate suspended Charge sources, rolls and completion after restoration."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.charge_phase_state import (
    ChargeInterruption,
    ChargePhaseState,
    ChargePhaseStatePayload,
)
from warhammer40k_core.engine.heroic_intervention_rolls import heroic_charge_source
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagem_use_history_authority import validate_stratagem_use_history

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def validate_interrupted_charge_source(*, state: GameState, decisions: DecisionController) -> None:
    active: ChargeInterruption | None = None
    actor: str | None = None
    seen: set[str] = set()
    rolls: list[ChargeRollResult] = []
    for index, event in enumerate(decisions.event_log.records):
        payload = event.payload
        if event.event_type == "interrupted_charge_started":
            if (
                active is not None
                or not isinstance(payload, dict)
                or set(payload) != {"player_id", "source"}
            ):
                raise GameLifecycleError(
                    "Interrupted Charge source history shape or nesting drift."
                )
            active = ChargeInterruption.from_payload(payload["source"])
            if active.source_result_id in seen:
                raise GameLifecycleError("Interrupted Charge source was already consumed.")
            seen.add(active.source_result_id)
            matches = tuple(
                use
                for use in state.stratagem_use_records
                if use.result_id == active.source_result_id
            )
            if len(matches) != 1:
                raise GameLifecycleError("Interrupted Charge lost its Stratagem source.")
            use = matches[0]
            validate_stratagem_use_history(
                state=state,
                event_records=decisions.event_log.records,
                decision_records=decisions.records,
                use_record=use,
                mutation_index=index,
            )
            actor = use.player_id
            if (
                use.handler_id != "core:heroic-intervention"
                or payload["player_id"] != actor
                or use.phase is not BattlePhase.CHARGE
                or use.battle_round != active.suspended_phase.battle_round
                or use.active_player_id != active.suspended_phase.active_player_id
                or actor == use.active_player_id
                or heroic_charge_source(state=state, use=use, parent=active.suspended_phase)
                != active
            ):
                raise GameLifecycleError("Interrupted Charge source restrictions or owner drift.")
            rolls = []
        elif event.event_type == "charge_roll_resolved":
            if not isinstance(payload, dict) or not isinstance(payload.get("roll_result"), dict):
                raise GameLifecycleError("Charge roll history payload drift.")
            roll = ChargeRollResult.from_payload(
                cast(ChargeRollResultPayload, payload["roll_result"])
            )
            if active is not None:
                if (
                    roll.request.player_id != actor
                    or roll.request.unit_instance_id != active.unit_instance_id
                    or roll.request.battle_round != active.suspended_phase.battle_round
                    or roll.movement_budget.roll_limit != active.roll_limit
                    or any(
                        distance > active.target_range_inches
                        for distance in roll.reachable_target_distances_inches.values()
                    )
                    or (
                        active.allowed_target_ids is not None
                        and not set(roll.reachable_target_distances_inches).issubset(
                            active.allowed_target_ids
                        )
                    )
                ):
                    raise GameLifecycleError("Interrupted Charge roll source restrictions drift.")
                rolls.append(roll)
            elif roll.movement_budget.roll_limit is not None:
                raise GameLifecycleError("Charge roll limit has no active source.")
        elif event.event_type == "interrupted_charge_completed":
            if (
                active is None
                or not isinstance(payload, dict)
                or set(payload) != {"source", "resolved_charge_phase"}
            ):
                raise GameLifecycleError("Interrupted Charge completion lost its active source.")
            if payload["source"] != active.to_payload() or not isinstance(
                payload["resolved_charge_phase"], dict
            ):
                raise GameLifecycleError("Interrupted Charge completion source drift.")
            phase = ChargePhaseState.from_payload(
                cast(ChargePhaseStatePayload, payload["resolved_charge_phase"])
            )
            if (
                phase.interruption != active
                or phase.active_player_id != actor
                or phase.active_selection is not None
                or phase.move_pending_distance_state() is not None
                or (not phase.phase_complete and not phase.selected_unit_ids)
                or tuple(row.roll_result for row in phase.distance_states) != tuple(rolls)
            ):
                raise GameLifecycleError("Interrupted Charge completion state drift.")
            active, actor = None, None
    current_phase = state.charge_phase_state
    if (None if current_phase is None else current_phase.interruption) != active:
        raise GameLifecycleError("Interrupted Charge current source differs from its history.")
    if active is not None and (current_phase is None or current_phase.active_player_id != actor):
        raise GameLifecycleError("Interrupted Charge current actor drift.")
