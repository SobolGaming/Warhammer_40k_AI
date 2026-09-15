"""Persistent per-model distances, derived once from accepted movement evidence."""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING, cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class ModelMovementDistance(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    event_id: str
    battle_round: int
    turn_player_id: str
    model_instance_id: str
    distance_inches: float

    def __post_init__(self) -> None:
        for name in ("event_id", "turn_player_id", "model_instance_id"):
            IdentifierValidator(GameLifecycleError)(name, getattr(self, name))
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Movement history requires a positive battle round.")
        if (
            type(self.distance_inches) not in {int, float}
            or not isfinite(self.distance_inches)
            or self.distance_inches < 0
        ):
            raise GameLifecycleError("Movement history requires a finite nonnegative distance.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "event_id": self.event_id,
            "battle_round": self.battle_round,
            "turn_player_id": self.turn_player_id,
            "model_instance_id": self.model_instance_id,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, value: object) -> ModelMovementDistance:
        try:
            return msgspec.convert(value, type=cls, strict=True)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Invalid model movement history payload.") from exc


def distances_from_completion(
    event: EventRecord, *, turn_player_id: str
) -> tuple[ModelMovementDistance, ...]:
    """Consume each completion once; setup and stationary choices have no traveled path."""
    from warhammer40k_core.engine.move_completion_triggers import MOVE_COMPLETION_EVENT_TYPES

    if event.event_type not in MOVE_COMPLETION_EVENT_TYPES:
        return ()
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Movement distance source requires an object.")
    if event.event_type in {"reinforcement_unit_arrived", "unit_disembarked"}:
        return ()
    if event.event_type == "movement_activation_completed" and payload.get(
        "movement_phase_action"
    ) in {"remain_stationary", "ingress", "disembark", "combat_disembark"}:
        return ()
    source = payload["resolution"] if event.event_type == "fight_movement_completed" else payload
    if not isinstance(source, dict):
        raise GameLifecycleError("Movement distance resolution is missing.")
    results = source.get("path_validation_results")
    if not isinstance(results, list):
        raise GameLifecycleError("Movement distance source lacks path results.")
    rows: list[ModelMovementDistance] = []
    for result in results:
        if not isinstance(result, dict):
            raise GameLifecycleError("Movement distance path result is invalid.")
        raw = result.get("movement_distance_witness")
        if not isinstance(raw, dict):
            raise GameLifecycleError("Accepted movement requires model distance evidence.")
        witness = MovementDistanceWitness.from_payload(cast(MovementDistanceWitnessPayload, raw))
        rows.append(
            ModelMovementDistance(
                event_id=event.event_id,
                battle_round=cast(int, payload["battle_round"]),
                turn_player_id=turn_player_id,
                model_instance_id=witness.model_id,
                distance_inches=witness.total_distance_inches,
            )
        )
    if len({row.model_instance_id for row in rows}) != len(rows):
        raise GameLifecycleError("Movement history contains duplicate model distances.")
    return tuple(sorted(rows, key=lambda row: row.model_instance_id))


def validate_model_movement_history(state: GameState, events: tuple[EventRecord, ...]) -> None:
    from warhammer40k_core.engine.interrupted_charge import charge_turn_owner_at_event
    from warhammer40k_core.engine.move_completion_triggers import MOVE_COMPLETION_EVENT_TYPES

    expected: list[ModelMovementDistance] = []
    for index, event in enumerate(events):
        if event.event_type not in MOVE_COMPLETION_EVENT_TYPES:
            continue
        if not isinstance(event.payload, dict) or not isinstance(
            event.payload.get("active_player_id"), str
        ):
            raise GameLifecycleError("Movement history requires a turn owner.")
        owner = cast(str, event.payload["active_player_id"])
        if event.event_type == "charge_move_completed":
            owner = charge_turn_owner_at_event(
                event_records=events, event_index=index, actor_id=owner
            )
        expected.extend(distances_from_completion(event, turn_player_id=owner))
    if state.model_movement_history != expected:
        raise GameLifecycleError("Model movement history differs from accepted movement evidence.")


def models_within_turn_distance(
    *, state: GameState, model_ids: tuple[str, ...], maximum_inches: float
) -> bool:
    totals = dict.fromkeys(model_ids, 0.0)
    for row in state.model_movement_history:
        if (
            row.battle_round == state.battle_round
            and row.turn_player_id == state.active_player_id
            and row.model_instance_id in totals
        ):
            totals[row.model_instance_id] += row.distance_inches
    return all(distance <= maximum_inches + 1e-9 for distance in totals.values())


def validate_history_state(state: GameState) -> None:
    rows = state.model_movement_history
    if type(rows) is not list or any(type(row) is not ModelMovementDistance for row in rows):
        raise GameLifecycleError("Movement history requires typed per-model records.")
    keys = {(row.event_id, row.model_instance_id) for row in rows}
    if len(keys) != len(rows) or any(
        row.turn_player_id not in state.player_ids or row.battle_round > state.battle_round
        for row in rows
    ):
        raise GameLifecycleError("Movement history identity or turn drift.")
