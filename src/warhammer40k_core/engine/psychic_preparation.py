"""Reconstruct original gathered Psychic preparation from authoritative journals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_sequence_psychic_modifiers import (
    DECISION_TYPE,
    _psychic_attack_modifier_ignore_request,
    _psychic_attack_modifier_ignore_selection_for_attack,
)
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_weapon_profiles import evaluate_attack_weapon_profile

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@dataclass(frozen=True, slots=True)
class PsychicPreparationFrontier:
    completed_context_ids: tuple[str, ...]
    pending_request: DecisionRequest | None


def psychic_preparation_frontier(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    records: tuple[DecisionRecord, ...],
    request_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> PsychicPreparationFrontier:
    """Return the first unfinished original occurrence, never a payload cursor.

    The stored gathered host remains at zero. Completed choices form an ordered
    prefix of the real current pool, followed by at most one partial occurrence.
    Random skill values are read from their existing evaluation evidence; this
    query cannot draw dice, allocate request IDs or change the controller.
    """
    if (
        sequence.is_complete
        or sequence.current_gathered_group is None
        or sequence.attack_index != 0
        or sequence.generated_hit_index != 0
        or sequence.current_hit_roll is not None
        or sequence.post_roll_attack_pools is not None
        or sequence.pending_grouped_damage is not None
    ):
        raise GameLifecycleError("Psychic preparation requires an original gathered pool.")
    pool = sequence.current_pool()
    contexts = tuple(
        replace(sequence, attack_index=index).attack_context_id() for index in range(pool.attacks)
    )
    context_set = frozenset(contexts)
    relevant_records: list[DecisionRecord] = []
    for record in records:
        if record.request.decision_type != DECISION_TYPE:
            continue
        payload = record.request.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("attack_context_id"), str):
            raise GameLifecycleError("Psychic preparation record lacks an occurrence identity.")
        if payload["attack_context_id"] in context_set:
            relevant_records.append(record)
    relevant = tuple(relevant_records)
    consumed: list[DecisionRecord] = []
    completed: list[str] = []
    for context in contexts:
        current_records = tuple(
            record
            for record in relevant
            if isinstance(record.request.payload, dict)
            and record.request.payload["attack_context_id"] == context
        )
        evaluated = evaluate_attack_weapon_profile(
            pool=pool,
            decisions=decisions,
            manager=None,
            attack_context_id=context,
            player_id=sequence.attacker_player_id,
            characteristics=(Characteristic.BALLISTIC_SKILL, Characteristic.WEAPON_SKILL),
        )
        # The existing closed parser checks every source cursor, option, actor
        # and answer within this occurrence. Bind its first request to the actual
        # pool and live source owners too, not merely to mutually agreeing claims.
        previous = _psychic_attack_modifier_ignore_selection_for_attack(
            decisions=decisions, attack_context_id=context, records=current_records
        )
        first = _psychic_attack_modifier_ignore_request(
            state=state,
            pool=evaluated,
            attacker_player_id=sequence.attacker_player_id,
            attacking_unit_instance_id=sequence.attacking_unit_instance_id,
            attack_context_id=context,
            source_phase=sequence.source_phase,
            runtime_modifier_registry=runtime_modifier_registry,
            request_id=current_records[0].request.request_id if current_records else request_id,
        )
        if current_records and (
            first is None
            or canonical_json(first.to_payload())
            != canonical_json(current_records[0].request.to_payload())
        ):
            raise GameLifecycleError("Psychic preparation source or occurrence drift.")
        consumed.extend(current_records)
        if tuple(consumed) != relevant[: len(consumed)]:
            raise GameLifecycleError("Psychic preparation occurrences are out of order.")
        if previous is not None and previous.complete:
            completed.append(context)
            continue
        pending = _psychic_attack_modifier_ignore_request(
            state=state,
            pool=evaluated,
            attacker_player_id=sequence.attacker_player_id,
            attacking_unit_instance_id=sequence.attacking_unit_instance_id,
            attack_context_id=context,
            source_phase=sequence.source_phase,
            runtime_modifier_registry=runtime_modifier_registry,
            previous_selection=previous,
            request_id=request_id,
        )
        if pending is not None:
            if tuple(consumed) != relevant:
                raise GameLifecycleError("Psychic preparation skips an unfinished occurrence.")
            return PsychicPreparationFrontier(tuple(completed), pending)
    return PsychicPreparationFrontier(tuple(completed), None)
