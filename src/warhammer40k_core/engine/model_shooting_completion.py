"""Release model-shot rules using the existing authenticated participation journal."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.model_attack_completion import MODEL_COMPLETION_STATE_EVENT
from warhammer40k_core.engine.model_attack_history import (
    MODELS_ATTACKED_EVENT_TYPE,
    validate_retained_model_attack_history,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler


def model_completion_boundary(
    events: tuple[EventRecord, ...],
    event_id: str,
) -> tuple[AttackSequence, tuple[str, ...], dict[str, JsonValue]]:
    matches = tuple((i, event) for i, event in enumerate(events) if event.event_id == event_id)
    if len(matches) != 1:
        raise GameLifecycleError("Model completion requires one authenticated event.")
    index, event = matches[0]
    payload = event.payload
    if (
        event.event_type != MODELS_ATTACKED_EVENT_TYPE
        or not isinstance(payload, dict)
        or index == 0
        or events[index - 1].event_type != MODEL_COMPLETION_STATE_EVENT
    ):
        raise GameLifecycleError("Model completion lacks its executor journal.")
    ids = payload.get("model_instance_ids")
    if not isinstance(ids, list) or not ids or any(type(value) is not str for value in ids):
        raise GameLifecycleError("Model completion requires physical participants.")
    model_ids = tuple(cast(list[str], ids))
    validate_retained_model_attack_history(
        event_records=events[: index + 1],
        model_instance_ids=frozenset(model_ids),
    )
    raw = events[index - 1].payload
    if not isinstance(raw, dict):
        raise GameLifecycleError("Model completion executor must be an object.")
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, raw))
    return sequence, model_ids, payload


def source_model_completion_event_id(
    events: tuple[EventRecord, ...],
    *,
    sequence_id: str,
    model_id: str,
) -> str | None:
    matches = tuple(
        event.event_id
        for event in events
        if event.event_type == MODELS_ATTACKED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence_id
        and isinstance(event.payload.get("model_instance_ids"), list)
        and model_id in cast(list[JsonValue], event.payload["model_instance_ids"])
    )
    if len(matches) > 1:
        raise GameLifecycleError("Model completion is duplicated.")
    return matches[0] if matches else None


def before_shooting_gathering(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_completion_sequencing import (
        resolve_attack_completion_candidates,
    )
    from warhammer40k_core.engine.model_attack_completion import resolved_model_ids
    from warhammer40k_core.engine.shooting_target_replacement import (
        request_shooting_target_replacement,
    )

    # Final model and unit candidates belong to the same existing timing batch.
    declared = frozenset(pool.attacker_model_instance_id for pool in sequence.attack_pools)
    if (
        state.current_battle_phase is BattlePhase.SHOOTING
        and sequence.attacker_player_id == state.active_player_id
        and resolved_model_ids(sequence, event_records=decisions.event_log.records) != declared
        and any(
            b.supports_model_completion for b in handler.attack_sequence_completed_hooks.bindings
        )
    ):
        for event in decisions.event_log.records:
            if (
                event.event_type != MODELS_ATTACKED_EVENT_TYPE
                or not isinstance(event.payload, dict)
                or event.payload.get("sequence_id") != sequence.sequence_id
                or not event.payload.get("model_instance_ids")
            ):
                continue
            completed, model_ids, _ = model_completion_boundary(
                decisions.event_log.records, event.event_id
            )
            context = AttackSequenceCompletedContext(
                state=state,
                decisions=decisions,
                dice_manager=DiceRollManager(state.private_rng_seed, event_log=decisions.event_log),
                runtime_modifier_registry=handler.runtime_modifier_registry,
                source_phase=sequence.source_phase,
                attack_sequence=completed,
                attack_sequence_completed_event_id=event.event_id,
                completed_model_instance_ids=model_ids,
            )
            registry = handler.attack_sequence_completed_hooks
            if not registry.candidates_for(context):
                continue
            status = resolve_attack_completion_candidates(
                context, partial(registry.candidates_for, context)
            )
            if status is not None:
                return status
    return request_shooting_target_replacement(
        handler=handler, state=state, decisions=decisions, sequence=sequence
    )
