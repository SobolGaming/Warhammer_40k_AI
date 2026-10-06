from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock_state_history import (
    battle_shock_state_authority_before_event,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_event_decision_authority import (
    validate_primary_mission_movement_event_decision_authority,
    validate_primary_mission_shooting_event_decision_authority,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_mission_boundary_unit_history_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    prior_events = event_records[:checkpoint_index]
    advanced_ids, fell_back_ids = _movement_history_ids(
        event_records=prior_events,
        decision_records=decision_records,
        checkpoint=checkpoint,
    )
    if _is_post_cleanup_scoring_checkpoint(
        state=state,
        event_records=event_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    ):
        # Accepted movement remains authenticated above. Turn-end scoring commits
        # follow cleanup, unlike the earlier control and turn-end rule snapshots.
        advanced_ids.clear()
        fell_back_ids.clear()
    checkpoint_advanced_ids = _unit_ids_from_state_jsons(checkpoint.advanced_unit_state_jsons)
    checkpoint_fell_back_ids = _unit_ids_from_state_jsons(checkpoint.fell_back_unit_state_jsons)
    if advanced_ids != checkpoint_advanced_ids:
        raise GameLifecycleError("Primary mission boundary Advance state lacks exact authority.")
    if fell_back_ids != checkpoint_fell_back_ids:
        raise GameLifecycleError("Primary mission boundary Fall Back state lacks exact authority.")
    _validate_battle_shock_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    declared_shot_ids = _shooting_declaration_ids(
        event_records=prior_events,
        decision_records=decision_records,
        checkpoint=checkpoint,
    )
    if declared_shot_ids != set(checkpoint.shot_unit_instance_ids):
        raise GameLifecycleError("Primary mission boundary shooting state lacks exact authority.")


def _movement_history_ids(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[set[str], set[str]]:
    advanced: set[str] = set()
    fell_back: set[str] = set()
    for event_index, event in enumerate(event_records):
        if event.event_type != "movement_activation_completed":
            continue
        payload = _event_payload(event, context="movement activation")
        validate_primary_mission_movement_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            payload=payload,
        )
        if not _same_game(payload=payload, checkpoint=checkpoint):
            continue
        if payload.get("battle_round") != checkpoint.battle_round:
            continue
        if payload.get("active_player_id") != checkpoint.player_id:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            raise GameLifecycleError("Primary mission movement history phase drifted.")
        unit_id = _payload_string(payload, key="unit_instance_id", context="movement activation")
        action = _payload_string(
            payload, key="movement_phase_action", context="movement activation"
        )
        if action == "advance":
            advanced.add(unit_id)
        elif action == "fall_back":
            fell_back.add(unit_id)
    return advanced, fell_back


def _is_post_cleanup_scoring_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> bool:
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
    from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
        PRIMARY_SCORING_COMMIT_BOUNDARY_KIND,
        PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    )

    if checkpoint.boundary_kind != PRIMARY_SCORING_COMMIT_BOUNDARY_KIND:
        return False
    event = event_records[checkpoint_index]
    payload = _event_payload(event, context="scoring commit")
    if (
        event.event_type != PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
        or payload.get("checkpoint") != checkpoint.to_payload()
    ):
        raise GameLifecycleError("Primary mission scoring commit checkpoint authority drifted.")
    records = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == payload.get("objective_control_record_id")
    )
    if len(records) != 1:
        raise GameLifecycleError("Primary mission scoring commit control authority drifted.")
    if records[0].timing is not ObjectiveControlTiming.TURN_END:
        return False
    cleanups = tuple(
        cleanup
        for cleanup in state.end_turn_cleanup_states
        if cleanup.battle_round == checkpoint.battle_round
        and cleanup.active_player_id == checkpoint.active_player_id
        and cleanup.phase == checkpoint.phase
    )
    if len(cleanups) > 1:
        raise GameLifecycleError("Primary mission scoring commit turn cleanup authority drifted.")
    # Supported state-backed scoring may commit before native cleanup.
    # Its checkpoint still carries the authenticated turn-action restrictions.
    return bool(cleanups)


def _validate_battle_shock_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    authority = battle_shock_state_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=checkpoint_index,
    )
    if authority.battle_shocked_unit_ids != tuple(checkpoint.battle_shocked_unit_instance_ids):
        raise GameLifecycleError("Primary mission Battle-shock state lacks result authority.")


def _shooting_declaration_ids(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> set[str]:
    if checkpoint.phase != BattlePhase.SHOOTING.value:
        return set()
    declared: set[str] = set()
    for event_index, event in enumerate(event_records):
        if event.event_type != "shooting_declaration_accepted":
            continue
        payload = _event_payload(event, context="shooting declaration")
        validate_primary_mission_shooting_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            payload=payload,
        )
        if not _same_game(payload=payload, checkpoint=checkpoint):
            continue
        if payload.get("battle_round") != checkpoint.battle_round:
            continue
        if payload.get("active_player_id") != checkpoint.player_id:
            continue
        if payload.get("phase") != BattlePhase.SHOOTING.value:
            raise GameLifecycleError("Primary mission shooting history phase drifted.")
        declared.add(
            _payload_string(payload, key="unit_instance_id", context="shooting declaration")
        )
        ineligible = payload.get("ineligible_unit_instance_ids")
        if not isinstance(ineligible, list) or any(type(value) is not str for value in ineligible):
            raise GameLifecycleError("Primary mission shooting causal inventory is invalid.")
        # Firing Deck restricts passengers; they did not themselves shoot.
    return declared


def _same_game(
    *,
    payload: dict[str, JsonValue],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> bool:
    game_id = payload.get("game_id")
    if type(game_id) is not str:
        raise GameLifecycleError("Primary mission causal-history game identity is invalid.")
    if game_id != checkpoint.game_id:
        raise GameLifecycleError("Primary mission causal-history game identity drifted.")
    return True


def _event_payload(event: EventRecord, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError(f"Primary mission {context} event payload is invalid.")
    return event.payload


def _payload_string(
    payload: dict[str, JsonValue],
    *,
    key: str,
    context: str,
) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Primary mission {context} {key} is invalid.")
    return value


def _unit_ids_from_state_jsons(values: tuple[str, ...]) -> set[str]:
    unit_ids: set[str] = set()
    for value in values:
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GameLifecycleError("Primary mission movement-state JSON is invalid.") from exc
        if not isinstance(decoded, dict):
            raise GameLifecycleError("Primary mission movement-state payload is invalid.")
        raw = cast(dict[object, object], decoded)
        unit_id = raw.get("unit_instance_id")
        if type(unit_id) is not str:
            raise GameLifecycleError("Primary mission movement-state unit identity is invalid.")
        unit_ids.add(unit_id)
    return unit_ids


__all__ = ("validate_primary_mission_boundary_unit_history_authority",)
