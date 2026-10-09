"""Recover the unresolved dice occurrence without trusting a submitted cursor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, cast

from warhammer40k_core.core.dice import DiceRollResult, DiceRollResultPayload
from warhammer40k_core.engine.attack_sequence_model import (
    HitRoll,
    HitRollPayload,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence


@dataclass(frozen=True, slots=True)
class DiceResolutionOccurrence:
    sequence: AttackSequence
    step: Literal["hit", "wound"]
    physical: DiceRollResult


def unresolved_dice_occurrence(
    *, sequence: AttackSequence, events: tuple[EventRecord, ...]
) -> DiceResolutionOccurrence:
    """Use completed rule steps, including automatic/generated hits, as the cursor.

    Physical dice can already exist for every member of a gathered stage. A
    constructed fixture can also preload dice; neither fact advances a step.
    Only its ordered completed journal advances the resolution frontier.
    """
    if (
        sequence.is_complete
        or sequence.post_roll_attack_pools is not None
        or (sequence.pending_grouped_damage is not None)
    ):
        raise GameLifecycleError("Dice override requires an unresolved attack pool.")
    pool = sequence.current_pool()
    hit_rows = _steps(sequence, events, "hit")
    wound_rows = _steps(sequence, events, "wound")
    if sequence.current_gathered_group is None:
        current = sequence
        step: Literal["hit", "wound"] = (
            "wound"
            if sequence.generated_hit_index
            or any(row.get("attack_context_id") == sequence.attack_context_id() for row in hit_rows)
            else "hit"
        )
        if any(row.get("attack_context_id") == current.attack_context_id() for row in wound_rows):
            raise GameLifecycleError("Dice override occurrence is already completed.")
    else:
        if sequence.attack_index != 0 or sequence.generated_hit_index != 0:
            raise GameLifecycleError("Gathered dice resolution requires its original host.")
        originals = tuple(replace(sequence, attack_index=i) for i in range(pool.attacks))
        _validate_prefix(hit_rows, originals)
        if len(hit_rows) < len(originals):
            if wound_rows:
                raise GameLifecycleError("Wounds precede the completed gathered Hit stage.")
            current, step = originals[len(hit_rows)], "hit"
        else:
            wounds: list[AttackSequence] = []
            for original, row in zip(originals, hit_rows, strict=True):
                raw = row.get("payload")
                if not isinstance(raw, dict):
                    raise GameLifecycleError("Gathered Hit evidence must be an object.")
                hit = HitRoll.from_payload(cast(HitRollPayload, raw))
                if not hit.successful:
                    continue
                generated = original
                for index in range(hit.generated_hits):
                    if index:
                        generated = generated.advanced_after_generated_hit(hit)
                    wounds.append(generated)
            _validate_prefix(wound_rows, tuple(wounds))
            if len(wound_rows) == len(wounds):
                raise GameLifecycleError("Dice override has no unfinished Wound occurrence.")
            current, step = wounds[len(wound_rows)], "wound"
    physical = _physical_roll(current, events, step)
    return DiceResolutionOccurrence(current, step, physical)


def _steps(
    sequence: AttackSequence, events: tuple[EventRecord, ...], step: str
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        event.payload
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
        and event.payload.get("pool_index") == sequence.pool_index
        and event.payload.get("step") == step
    )


def _validate_prefix(
    rows: tuple[dict[str, JsonValue], ...], occurrences: tuple[AttackSequence, ...]
) -> None:
    if len(rows) > len(occurrences):
        raise GameLifecycleError("Dice resolution has excess completed occurrences.")
    for row, current in zip(rows, occurrences, strict=False):
        if (
            type(row.get("pool_index")) is not int
            or type(row.get("attack_index")) is not int
            or row.get("attack_index") != current.attack_index
            or row.get("attack_context_id") != current.attack_context_id()
        ):
            raise GameLifecycleError("Dice resolution completed occurrences are out of order.")


def _physical_roll(
    sequence: AttackSequence, events: tuple[EventRecord, ...], step: Literal["hit", "wound"]
) -> DiceRollResult:
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _hit_reroll_forbidden_rule_ids,
    )
    from warhammer40k_core.engine.weapon_abilities import (
        FIRE_OVERWATCH_RULE_ID,
        SNAP_SHOOTING_RULE_ID,
    )

    pool = sequence.current_pool()
    if step == "hit":
        spec = attack_sequence_hit_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=sequence.attack_context_id(),
            attacker_player_id=sequence.attacker_player_id,
            reroll_forbidden_rule_ids=_hit_reroll_forbidden_rule_ids(
                is_snap_shooting=bool(
                    {FIRE_OVERWATCH_RULE_ID, SNAP_SHOOTING_RULE_ID} & set(pool.targeting_rule_ids)
                ),
                targeting_rule_ids=pool.targeting_rule_ids,
            ),
        )
    else:
        spec = attack_sequence_wound_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=sequence.attack_context_id(),
            attacker_player_id=sequence.attacker_player_id,
        )
    physical = tuple(
        DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        for event in events
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and event.payload.get("spec") == spec.to_payload()
    )
    if len(physical) != 1:
        raise GameLifecycleError("Dice override requires one physical roll for its occurrence.")
    return physical[0]
