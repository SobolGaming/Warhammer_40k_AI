"""Source rule 04.03.04/05: a bearer completes only its own resolved attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence_model import (
    AttackSequencePayload,
    HitRoll,
    HitRollPayload,
    WoundRoll,
    WoundRollPayload,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState

MODEL_COMPLETION_STATE_EVENT = "attack_sequence_model_completion_state_recorded"
_identifier = IdentifierValidator(GameLifecycleError)


def completed_model_ids(sequence: AttackSequence) -> frozenset[str]:
    """Discharge physical contributions retained in the typed pending inventory."""
    declared = {pool.attacker_model_instance_id for pool in sequence.attack_pools}
    group = sequence.current_gathered_group
    group_indices = () if group is None else group.pool_indices
    unresolved = {
        pool.attacker_model_instance_id
        for index, pool in enumerate(sequence.attack_pools)
        if index not in sequence.used_pool_indices
        and index not in group_indices
        and not sequence.is_complete
    }
    if group is not None:
        group_models = {
            sequence.attack_pools[index].attacker_model_instance_id for index in group.pool_indices
        }
        pending = sequence.pending_grouped_damage
        post_roll = sequence.post_roll_attack_pools
        if group.native_snapshots and (pending is not None or post_roll is not None):
            # All hit/wound steps have finished. Only surviving physical contexts
            # can still own saves/damage, including unselected modified pools.
            remaining_contexts = (
                ()
                if pending is None
                else tuple(
                    die["attack_context"] for die in pending.sorted_save_dice[pending.next_index :]
                )
            )
            if post_roll is not None:
                pending_ids = {
                    context_id
                    for pool in post_roll.unresolved_pools
                    for context_id in pool.attack_context_ids
                }
                if pending is None and post_roll.selected_pool is not None:
                    pending_ids.update(post_roll.selected_pool.attack_context_ids)
                remaining_contexts = (
                    *remaining_contexts,
                    *(
                        context
                        for context in sequence.post_roll_attack_contexts
                        if context["attack_context_id"] in pending_ids
                    ),
                )
            unresolved.update(
                context["attacker_model_instance_id"] for context in remaining_contexts
            )
        else:
            unresolved.update(group_models)
    pending_transport = sequence.pending_destroyed_transport_disembark
    if pending_transport is not None and not sequence.is_complete:
        unresolved.add(pending_transport.attack_context["attacker_model_instance_id"])
    unresolved.update(row.source_model_instance_id for row in sequence.deferred_mortal_wounds)
    return frozenset(declared - unresolved)


def resolved_model_ids(
    sequence: AttackSequence, *, event_records: tuple[EventRecord, ...]
) -> frozenset[str]:
    """Use finalized physical roll steps before a gathered group has pending state.

    The native gatherer resumes from this same journal. Original hit steps are
    final only after all reroll choices; each generated hit needs its own failed
    wound or completed damage step. Deferred and interrupted work stays owned.
    """
    complete = completed_model_ids(sequence)
    group = sequence.current_gathered_group
    if group is None or not group.native_snapshots:
        return complete
    steps = {
        (event.payload["attack_context_id"], event.payload["step"]): event.payload["payload"]
        for event in event_records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
        and event.payload.get("pool_index") == group.primary_pool_index
    }
    unresolved = {
        pool.attacker_model_instance_id
        for index, pool in enumerate(sequence.attack_pools)
        if index not in sequence.used_pool_indices and index not in group.pool_indices
    }
    offset = 0
    for contribution in group.contributions:
        model_id = sequence.attack_pools[contribution.pool_index].attacker_model_instance_id
        for ordinal in range(offset + 1, offset + contribution.attacks + 1):
            context_id = (
                f"{sequence.sequence_id}:pool-{group.primary_pool_index + 1:03d}"
                f":attack-{ordinal:03d}"
            )
            hit = steps.get((context_id, "hit"))
            if not isinstance(hit, dict):
                unresolved.add(model_id)
                continue
            finalized_hit = HitRoll.from_payload(cast(HitRollPayload, hit))
            if not finalized_hit.successful:
                continue
            for generated in range(1, finalized_hit.generated_hits + 1):
                generated_id = (
                    context_id if generated == 1 else f"{context_id}:generated-hit-{generated:03d}"
                )
                wound = steps.get((generated_id, "wound"))
                if isinstance(wound, dict):
                    wound_payload = cast(WoundRollPayload, wound)
                    raw_roll_state = wound_payload["roll_state"]
                    finalized_wound = WoundRoll(
                        strength=wound_payload["strength"],
                        toughness=wound_payload["toughness"],
                        target_number=wound_payload["target_number"],
                        roll_state=None
                        if raw_roll_state is None
                        else DiceRollState.from_payload(raw_roll_state),
                        unmodified_roll=wound_payload["unmodified_roll"],
                        modifier=wound_payload["modifier"],
                        capped_modifier=wound_payload["capped_modifier"],
                        final_roll=wound_payload["final_roll"],
                        successful=wound_payload["successful"],
                        critical=wound_payload["critical"],
                        critical_threshold=wound_payload["critical_threshold"],
                        critical_is_threshold=wound_payload["critical_is_threshold"],
                        skipped=wound_payload["skipped"],
                    )
                    if not finalized_wound.successful:
                        continue
                if (generated_id, "damage") not in steps:
                    unresolved.add(model_id)
        offset += contribution.attacks
    pending = sequence.pending_grouped_damage
    if pending is not None:
        unresolved.update(
            die["attack_context"]["attacker_model_instance_id"]
            for die in pending.sorted_save_dice[pending.next_index :]
        )
    unresolved.update(row.source_model_instance_id for row in sequence.deferred_mortal_wounds)
    pending_transport = sequence.pending_destroyed_transport_disembark
    if pending_transport is not None:
        unresolved.add(pending_transport.attack_context["attacker_model_instance_id"])
    declared = {pool.attacker_model_instance_id for pool in sequence.attack_pools}
    # A finalized damage event alone does not discharge an interrupted die's
    # remaining post-damage/deferred work. Journal misses can finish before a
    # sibling's wound/save choice, while typed pending contexts stay unresolved.
    group_models = {
        sequence.attack_pools[index].attacker_model_instance_id for index in group.pool_indices
    }
    return (complete - group_models) | frozenset(declared - unresolved)


def all_attacks_resolved(sequence: AttackSequence) -> bool:
    """Target post-attack reactions do not delay the attacking unit having shot."""
    return (
        bool(sequence.attack_pools) and sequence.is_complete and not sequence.deferred_mortal_wounds
    )


def model_completion_evidence(
    *,
    event_records: tuple[EventRecord, ...],
    index: int,
    declaration: dict[str, JsonValue],
    declaration_event: EventRecord,
    previously_completed: frozenset[str],
) -> frozenset[str]:
    """Require the exact engine boundary beside each incremental participation."""
    if index == 0 or event_records[index - 1].event_type != MODEL_COMPLETION_STATE_EVENT:
        raise GameLifecycleError("Model attack history is missing its completed attacks evidence.")
    payload = event_records[index - 1].payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Model attack completion state must be an object.")
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, payload))
    if (
        sequence.sequence_id != declaration["sequence_id"]
        or sequence.attacking_unit_instance_id != declaration["attacking_unit_instance_id"]
        or sequence.source_phase.value != declaration["attack_phase"]
        or sorted({pool.attacker_model_instance_id for pool in sequence.attack_pools})
        != declaration["model_instance_ids"]
    ):
        raise GameLifecycleError(
            "Model attack history completion state differs from its declaration."
        )
    origin = declaration_event.payload
    if not isinstance(origin, dict):
        raise GameLifecycleError("Model attack completion declaration must be an object.")
    if declaration_event.event_type == "melee_declaration_accepted":
        request = origin.get("proposal_request")
        if not isinstance(request, dict):
            raise GameLifecycleError("Model attack history requires its melee request.")
        attacker = request.get("actor_id")
    elif declaration_event.event_type == "out_of_phase_shooting_declaration_accepted":
        attacker = origin.get("player_id")
    else:
        attacker = origin.get("active_player_id")
    if sequence.attacker_player_id != attacker:
        raise GameLifecycleError(
            "Model attack history completion attacker differs from its declaration."
        )
    if "attack_pools" in origin:
        from warhammer40k_core.engine.shooting_target_replacement_authority import (
            validate_recorded_sequence_authority,
        )

        validate_recorded_sequence_authority(
            event_records=event_records[:index],
            sequence=sequence,
            result_id=cast(str, origin["result_id"]),
        )
        complete = resolved_model_ids(sequence, event_records=event_records[: index - 1])
        if not previously_completed <= complete:
            raise GameLifecycleError("Model attack history completion boundary regressed.")
        return complete - previously_completed
    entries = origin.get("attack_pools")
    if declaration_event.event_type == "melee_declaration_accepted":
        proposal = origin.get("proposal")
        if not isinstance(proposal, dict):
            raise GameLifecycleError("Model attack completion requires its melee proposal.")
        entries = proposal.get("declarations")
    if not isinstance(entries, list):
        raise GameLifecycleError("Model attack completion requires declared weapons.")
    if declaration_event.event_type == "melee_declaration_accepted":
        expanded: list[JsonValue] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("target_allocations"), list):
                raise GameLifecycleError("Model attack completion melee allocations drifted.")
            for allocation in cast(list[JsonValue], entry["target_allocations"]):
                if not isinstance(allocation, dict):
                    raise GameLifecycleError("Model attack completion melee target drifted.")
                expanded.append(
                    {**entry, "target_unit_instance_id": allocation.get("target_unit_instance_id")}
                )
        entries = expanded
    fields = (
        "attacker_model_instance_id",
        "weapon_profile_id",
        "wargear_id",
        "target_unit_instance_id",
    )
    if [
        tuple(cast(dict[str, JsonValue], pool.to_payload())[field] for field in fields)
        for pool in sequence.attack_pools
    ] != [
        tuple(entry.get(field) for field in fields) for entry in entries if isinstance(entry, dict)
    ]:
        raise GameLifecycleError("Model attack completion weapon declaration drifted.")
    for pool, entry in zip(sequence.attack_pools, entries, strict=True):
        if (
            isinstance(entry, dict)
            and "weapon_instance_id" in entry
            and (entry["weapon_instance_id"] != pool.weapon_instance_id)
        ):
            raise GameLifecycleError("Model attack history physical weapon declaration drifted.")
    complete = resolved_model_ids(sequence, event_records=event_records[: index - 1])
    if not previously_completed <= complete:
        raise GameLifecycleError("Model attack completion boundary regressed.")
    return complete - previously_completed


def validate_shot_unit_inventory(*, state: GameState, events: tuple[EventRecord, ...]) -> None:
    """Ordinary has-shot state follows authenticated all-attacks evidence."""
    shooting = state.shooting_phase_state
    if shooting is None:
        return
    completed: set[str] = set()
    for index, event in enumerate(events):
        if event.event_type != MODEL_COMPLETION_STATE_EVENT or not isinstance(event.payload, dict):
            continue
        sequence = AttackSequence.from_payload(cast(AttackSequencePayload, event.payload))
        if sequence.attack_pools and resolved_model_ids(
            sequence, event_records=events[:index]
        ) == frozenset(pool.attacker_model_instance_id for pool in sequence.attack_pools):
            completed.add(sequence.sequence_id)
    expected = {
        _identifier("Completed shooting unit", event.payload.get("unit_instance_id"))
        for event in events
        if event.event_type == "shooting_declaration_accepted"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_round") == shooting.battle_round
        and event.payload.get("active_player_id") == shooting.active_player_id
        and event.payload.get("attack_pools")
        and f"attack-sequence:{event.payload.get('result_id')}" in completed
    }
    if set(shooting.shot_unit_ids) != expected:
        raise GameLifecycleError("Shooting has-shot inventory differs from completed attacks.")
