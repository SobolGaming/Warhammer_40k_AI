"""Rebuild activity effects for historical Action-request authority checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from warhammer40k_core.engine.activity_restrictions import (
    activity_restriction_payload,
    build_activity_restriction,
)
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.model_attack_history import (
    MODELS_ATTACKED_EVENT_TYPE,
    validate_retained_model_attack_history,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionPriorUseEvidence,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.rules_units import rules_unit_identity_ids

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class _CompletedModels(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    game_id: str
    battle_round: int
    active_player_id: str
    phase: str
    sequence_id: str
    attack_phase: str
    attacking_unit_instance_id: str
    model_instance_ids: tuple[str, ...]


def restore_checkpoint_activity_restrictions(
    *,
    state: GameState,
    prior_uses: tuple[MissionActionPriorUseEvidence, ...],
    event_records: tuple[EventRecord, ...],
    checkpoint_event_id: str,
) -> None:
    """Mutate only the reconstructed state, using the authenticated event prefix."""
    boundaries = [
        index
        for index, event in enumerate(event_records)
        if event.event_id == checkpoint_event_id
        and event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    ]
    if len(boundaries) != 1 or state.active_player_id is None:
        raise GameLifecycleError("Activity history requires one exact checkpoint boundary.")
    prior_events = event_records[: boundaries[0]]
    state.remove_persisting_effects_by_id(
        tuple(
            effect.effect_id
            for effect in state.persisting_effects
            if activity_restriction_payload(effect) is not None
        )
    )
    for action in prior_uses:
        if (
            action.battle_round_started != state.battle_round
            or action.player_id != state.active_player_id
        ):
            continue
        state.record_persisting_effect(
            build_activity_restriction(
                owner_player_id=action.player_id,
                target_unit_instance_ids=action.unit_identity_ids,
                activity="started_action",
                activity_id=action.action_id,
                battle_round=action.battle_round_started,
                phase=BattlePhase(action.phase_started),
                expiration=EffectExpiration.end_turn(
                    battle_round=action.battle_round_started, player_id=action.player_id
                ),
            )
        )
    model_owners = {
        model.model_instance_id: (army.player_id, unit.unit_instance_id)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    validate_retained_model_attack_history(
        event_records=prior_events, model_instance_ids=frozenset(model_owners)
    )
    completed_sequences: set[str] = set()
    for event in prior_events:
        if event.event_type != "attack_sequence_completed":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Completed shooting activity requires an event payload.")
        sequence_id = event.payload.get("sequence_id")
        if type(sequence_id) is not str or sequence_id in completed_sequences:
            raise GameLifecycleError("Completed shooting activity sequence identity drifted.")
        completed_sequences.add(sequence_id)
    for event in prior_events:
        if event.event_type != MODELS_ATTACKED_EVENT_TYPE:
            continue
        try:
            row = msgspec.convert(event.payload, type=_CompletedModels)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Completed shooting activity history is malformed.") from exc
        if row.game_id != state.game_id:
            raise GameLifecycleError("Completed shooting activity game identity drifted.")
        if (
            row.attack_phase != BattlePhase.SHOOTING.value
            or row.battle_round != state.battle_round
            or row.active_player_id != state.active_player_id
            or row.phase != BattlePhase.SHOOTING.value
            or row.sequence_id not in completed_sequences
        ):
            continue
        if not row.model_instance_ids or not set(row.model_instance_ids) <= model_owners.keys():
            raise GameLifecycleError("Completed shooting activity model identity drifted.")
        owners = {model_owners[model_id][0] for model_id in row.model_instance_ids}
        if len(owners) != 1:
            raise GameLifecycleError("Completed shooting activity model ownership drifted.")
        target_ids = {
            *rules_unit_identity_ids(state=state, unit_instance_id=row.attacking_unit_instance_id),
            *(model_owners[model_id][1] for model_id in row.model_instance_ids),
        }
        state.record_persisting_effect(
            build_activity_restriction(
                owner_player_id=next(iter(owners)),
                target_unit_instance_ids=tuple(sorted(target_ids)),
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
        )
