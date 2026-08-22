from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def split_attached_rules_unit_if_required(
    *,
    state: GameState,
    event_log: EventLog,
    rules_unit_instance_id: str,
) -> tuple[str, ...]:
    surviving_unit_ids = attached_rules_unit_split_survivor_ids(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
    )
    if not surviving_unit_ids:
        return ()
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    state.recover_starting_strength_after_attached_unit_split(
        player_id=rules_unit.owner_player_id,
        attached_unit_instance_id=rules_unit.unit_instance_id,
        surviving_unit_instance_ids=surviving_unit_ids,
        event_log=event_log,
    )
    return surviving_unit_ids


def attached_rules_unit_split_survivor_ids(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[str, ...]:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        return ()
    bodyguard_alive = any(
        model.is_alive
        for component in rules_unit.components
        if component.role == "bodyguard"
        for model in component.unit.own_models
    )
    leader_or_support_alive = any(
        model.is_alive
        for component in rules_unit.components
        if component.role in {"leader", "support"}
        for model in component.unit.own_models
    )
    if bodyguard_alive == leader_or_support_alive:
        return ()
    surviving_unit_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for component in rules_unit.components
            if any(model.is_alive for model in component.unit.own_models)
        )
    )
    if not surviving_unit_ids:
        raise GameLifecycleError("Attached-unit split requires surviving component units.")
    return surviving_unit_ids


def reconcile_after_attack_sequence(
    state: GameState,
    event_log: EventLog,
    attack_sequence: AttackSequence,
) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attached-unit reconciliation requires AttackSequence.")
    candidate_ids = {attack_sequence.attacking_unit_instance_id}
    for record in event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Model destroyed payload must be an object.")
        if payload.get("sequence_id") != attack_sequence.sequence_id:
            continue
        target_unit_id = payload.get("target_unit_instance_id")
        if type(target_unit_id) is not str or not target_unit_id:
            raise GameLifecycleError("Model destroyed payload requires target unit id.")
        candidate_ids.add(target_unit_id)
    reconciled_ids: set[str] = set()
    surviving_ids: set[str] = set()
    for candidate_id in sorted(candidate_ids):
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=candidate_id)
        if rules_unit.unit_instance_id in reconciled_ids:
            continue
        reconciled_ids.add(rules_unit.unit_instance_id)
        surviving_ids.update(
            split_attached_rules_unit_if_required(
                state=state,
                event_log=event_log,
                rules_unit_instance_id=rules_unit.unit_instance_id,
            )
        )
    return tuple(sorted(surviving_ids))


__all__ = (
    "attached_rules_unit_split_survivor_ids",
    "reconcile_after_attack_sequence",
    "split_attached_rules_unit_if_required",
)
