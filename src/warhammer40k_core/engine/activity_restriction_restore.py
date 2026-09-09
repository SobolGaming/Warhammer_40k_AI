"""Authenticate the live activity-effect inventory once at lifecycle restoration."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import msgspec

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatePayload
from warhammer40k_core.engine.activity_restriction_history import CompletedAttackModels
from warhammer40k_core.engine.activity_restrictions import (
    activity_restriction_payload,
    build_activity_restriction,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.model_attack_history import (
    MODELS_ATTACKED_EVENT_TYPE,
    validate_declared_model_attack_completions,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.objective_control_boundary_history_integrity import (
    completed_phase_objective_control_context,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_identity_ids

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState


def validate_activity_restriction_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    expected = activity_restrictions_from_history(
        state=state, event_records=event_records, decision_records=decision_records
    )
    actual = tuple(
        sorted(
            (
                effect
                for effect in state.persisting_effects
                if activity_restriction_payload(effect) is not None
            ),
            key=lambda effect: effect.effect_id,
        )
    )
    if actual != expected:
        raise GameLifecycleError(
            "Activity restriction inventory differs from accepted activity "
            "and completed boundary history."
        )


def activity_restrictions_from_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> tuple[PersistingEffect, ...]:
    """Reconstruct exact subjects and lifetimes; never used by hot eligibility queries."""
    model_owners = {
        model.model_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    validate_declared_model_attack_completions(event_records=event_records)
    decisions = {record.result.result_id: record for record in decision_records}
    participations: dict[str, CompletedAttackModels] = {}
    seen: set[str] = set()
    live: dict[str, PersistingEffect] = {}
    for event in event_records:
        if event.event_type == MODELS_ATTACKED_EVENT_TYPE:
            try:
                row = msgspec.convert(event.payload, type=CompletedAttackModels)
            except msgspec.ValidationError as exc:
                raise GameLifecycleError(
                    "Activity restriction completion history is malformed."
                ) from exc
            participations[row.sequence_id] = row
        elif event.event_type == "attack_sequence_completed":
            payload = _object(event.payload)
            sequence_id = payload.get("sequence_id")
            if type(sequence_id) is not str or sequence_id not in participations:
                raise GameLifecycleError(
                    "Activity restriction completion lacks model participation."
                )
            row = participations[sequence_id]
            if row.attack_phase != BattlePhase.SHOOTING.value:
                continue
            if not row.model_instance_ids or not set(row.model_instance_ids) <= model_owners.keys():
                raise GameLifecycleError("Activity restriction model ownership is invalid.")
            owner_ids = {model_owners[model_id] for model_id in row.model_instance_ids}
            if (
                len(owner_ids) != 1
                or payload
                != {
                    "sequence_id": row.sequence_id,
                    "attacker_player_id": next(iter(owner_ids)),
                    "attacking_unit_instance_id": row.attacking_unit_instance_id,
                }
                or row.game_id != state.game_id
            ):
                raise GameLifecycleError(
                    "Activity restriction completion owner or subject drifted."
                )
            effect = build_activity_restriction(
                owner_player_id=next(iter(owner_ids)),
                target_unit_instance_ids=tuple(
                    sorted(
                        rules_unit_identity_ids(
                            state=state, unit_instance_id=row.attacking_unit_instance_id
                        )
                    )
                ),
                activity="completed_shooting",
                activity_id=row.sequence_id,
                battle_round=row.battle_round,
                phase=BattlePhase(row.phase),
                expiration=EffectExpiration.end_phase(
                    battle_round=row.battle_round,
                    phase=BattlePhase(row.phase),
                    player_id=row.active_player_id,
                ),
            )
            _add(live, seen, effect)
        elif event.event_type == "mission_action_started":
            payload = _object(event.payload)
            action = MissionActionState.from_payload(
                cast(MissionActionStatePayload, _object(payload.get("mission_action_state")))
            )
            result_id = action.action_id.removeprefix("mission-action:")
            decision = decisions.get(result_id)
            if decision is None or decision.request.decision_type != "start_mission_action":
                raise GameLifecycleError(
                    "Activity restriction Action lacks an accepted start decision."
                )
            choice = _object(
                decision.request.option_by_id(decision.result.selected_option_id).payload
            )
            if (
                action.action_id != f"mission-action:{decision.result.result_id}"
                or decision.request.actor_id != action.player_id
                or choice.get("unit_instance_id") != action.unit_instance_id
                or choice.get("battle_round") != action.battle_round_started
                or choice.get("phase") != action.phase_started
                or choice.get("mission_action_id") != action.mission_action_id
                or payload.get("game_id") != state.game_id
                or payload.get("player_id") != action.player_id
                or payload.get("battle_round") != action.battle_round_started
                or payload.get("phase") != action.phase_started
            ):
                raise GameLifecycleError(
                    "Activity restriction Action decision subject or timing drifted."
                )
            effect = build_activity_restriction(
                owner_player_id=action.player_id,
                target_unit_instance_ids=tuple(
                    sorted(
                        rules_unit_identity_ids(
                            state=state, unit_instance_id=action.unit_instance_id
                        )
                    )
                ),
                activity="started_action",
                activity_id=action.action_id,
                battle_round=action.battle_round_started,
                phase=BattlePhase(action.phase_started),
                expiration=EffectExpiration.end_turn(
                    battle_round=action.battle_round_started, player_id=action.player_id
                ),
            )
            _add(live, seen, effect)
        elif event.event_type == "battle_phase_completed":
            round_number, player_id, phase = completed_phase_objective_control_context(
                state=state, event=event
            )
            boundary = EffectExpirationBoundary.phase_end(
                battle_round=round_number, player_id=player_id, phase=BattlePhase(phase)
            )
            live = {key: effect for key, effect in live.items() if not effect.expires_at(boundary)}
    # Turn-end preparation is itself the engine-owned expiry boundary, before
    # the next turn is entered. The existing OC authority validates these records.
    for record in state.objective_control_records:
        if record.timing is ObjectiveControlTiming.TURN_END:
            boundary = EffectExpirationBoundary.turn_end(
                battle_round=record.battle_round, player_id=record.active_player_id
            )
            live = {key: effect for key, effect in live.items() if not effect.expires_at(boundary)}
    return tuple(sorted(live.values(), key=lambda effect: effect.effect_id))


def _add(live: dict[str, PersistingEffect], seen: set[str], effect: PersistingEffect) -> None:
    if effect.effect_id in seen:
        raise GameLifecycleError("Activity restriction history repeats an activity.")
    seen.add(effect.effect_id)
    live[effect.effect_id] = effect


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Activity restriction history requires an object.")
    return value
