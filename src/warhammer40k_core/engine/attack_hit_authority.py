"""Bind resumable hit values to the attack's engine-recorded roll and sources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackSequencePayload,
    HitRoll,
    HitRollPayload,
    attack_sequence_hit_roll_spec,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_destruction_state import retained_destructions


def validate_attack_hit_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Validate every hit copy before restore or a decision can resume an attack.

    The recorded HIT is the historical threshold/source authority. Re-evaluating
    current effects would incorrectly apply later casualties or expired effects
    to an already resolved roll. Dice and weapon context bind that evidence to
    its owner; self-consistency of HitRoll alone cannot establish authority.
    """
    contexts = tuple(
        context
        for root in _attack_payload_roots(state, pending_decision_requests)
        for context in _hit_contexts(root)
    )
    if not contexts:
        return
    records: dict[tuple[str, int], list[dict[str, JsonValue]]] = {}
    identities: set[tuple[str, int, int]] = set()
    for event in event_records:
        if event.event_type != "attack_sequence_step":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or payload.get("step") != "hit":
            continue
        sequence_id, pool_index = payload.get("sequence_id"), payload.get("pool_index")
        attack_index = payload.get("attack_index")
        if (
            type(sequence_id) is not str
            or type(pool_index) is not int
            or type(attack_index) is not int
        ):
            raise GameLifecycleError("Recorded hit authority has invalid attack identity.")
        identity = (sequence_id, pool_index, attack_index)
        if identity in identities:
            raise GameLifecycleError("Hit authority has duplicate owning recorded hits.")
        identities.add(identity)
        records.setdefault((sequence_id, pool_index), []).append(payload)
    for context in contexts:
        _validate_hit_context(context, records)


def _attack_payload_roots(
    state: GameState, requests: tuple[DecisionRequest, ...]
) -> Iterator[JsonValue]:
    for host in (
        state.shooting_phase_state,
        state.fight_phase_state,
        state.out_of_phase_shooting_state,
    ):
        if host is not None and host.attack_sequence is not None:
            yield cast(JsonValue, host.attack_sequence.to_payload())
    # Retained casualties can suspend their parent attack while another host runs.
    for retained in retained_destructions(state=state):
        yield retained.owner_context
        if retained.owner_progress is not None:
            yield retained.owner_progress
    for request in requests:
        yield request.payload


def _hit_contexts(value: JsonValue) -> Iterator[dict[str, JsonValue]]:
    if isinstance(value, list):
        for child in value:
            yield from _hit_contexts(child)
    elif isinstance(value, dict):
        if "hit_roll" in value:
            yield value
        if value.get("current_hit_roll") is not None:
            sequence = AttackSequence.from_payload(cast(AttackSequencePayload, value))
            pool = sequence.current_pool()
            yield {
                "sequence_id": sequence.sequence_id,
                "pool_index": sequence.pool_index,
                "attack_index": sequence.attack_index,
                "generated_hit_index": sequence.generated_hit_index,
                "attack_context_id": sequence.attack_context_id(),
                "attacker_player_id": sequence.attacker_player_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "hit_roll": value["current_hit_roll"],
            }
        for child in value.values():
            yield from _hit_contexts(child)


def _validate_hit_context(
    context: dict[str, JsonValue],
    records: dict[tuple[str, int], list[dict[str, JsonValue]]],
) -> None:
    sequence_id = context.get("sequence_id")
    pool_index, attack_index = context.get("pool_index"), context.get("attack_index")
    generated_index = context.get("generated_hit_index")
    if (
        type(sequence_id) is not str
        or type(pool_index) is not int
        or type(attack_index) is not int
        or type(generated_index) is not int
    ):
        raise GameLifecycleError("Hit authority requires an owning attack context.")
    raw_hit = context.get("hit_roll")
    if not isinstance(raw_hit, dict):
        raise GameLifecycleError("Hit authority requires a recorded hit payload.")
    hit = HitRoll.from_payload(cast(HitRollPayload, raw_hit))
    candidates = records.get((sequence_id, pool_index), [])
    base_context_id = f"{sequence_id}:pool-{pool_index + 1:03d}:attack-{attack_index + 1:03d}"
    grouped = context.get("attack_context_id") == f"{sequence_id}:pool-{pool_index + 1:03d}:grouped"
    if not grouped:
        expected_context_id = base_context_id
        if generated_index > 0:
            expected_context_id += f":generated-hit-{generated_index + 1:03d}"
        if context.get("attack_context_id") != expected_context_id:
            raise GameLifecycleError("Hit authority attack context identity drift.")
        candidates = [record for record in candidates if record.get("attack_index") == attack_index]
        if len(candidates) != 1 or candidates[0].get("attack_context_id") != base_context_id:
            raise GameLifecycleError("Hit authority requires exactly one owning recorded hit.")
    # A grouped request copies its first wound's hit while replacing the attack
    # index with zero. Its original dice identity still binds it to this pool.
    matching = [record for record in candidates if _matches_recorded_hit(context, hit, record)]
    if not matching:
        raise GameLifecycleError(
            "Hit authority differs from the owning recorded hit or source context."
        )


def _matches_recorded_hit(
    context: dict[str, JsonValue],
    hit: HitRoll,
    record: dict[str, JsonValue],
) -> bool:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise GameLifecycleError("Recorded hit authority payload must be an object.")
    canonical_hit = cast(dict[str, JsonValue], hit.to_payload())
    recorded_hit = {key: payload.get(key) for key in canonical_hit}
    if canonical_json(canonical_hit) != canonical_json(recorded_hit):
        return False
    # The event records the profile that actually rolled, including gathered
    # weapon copies. A later post-roll profile is not the hit source. Torrent
    # has no dice; its complete automatic-hit payload is bound above.
    if hit.roll_state is not None:
        actor_id, weapon_id, attack_id = (
            context.get("attacker_player_id"),
            payload.get("weapon_profile_id"),
            record.get("attack_context_id"),
        )
        if type(actor_id) is not str or type(weapon_id) is not str or type(attack_id) is not str:
            raise GameLifecycleError("Recorded hit authority source context is invalid.")
        spec = hit.roll_state.original_result.spec
        expected = attack_sequence_hit_roll_spec(
            weapon_profile_id=weapon_id,
            attack_context_id=attack_id,
            attacker_player_id=actor_id,
            reroll_forbidden_rule_ids=spec.reroll_forbidden_rule_ids,
        )
        if spec != expected:
            return False
    return True
