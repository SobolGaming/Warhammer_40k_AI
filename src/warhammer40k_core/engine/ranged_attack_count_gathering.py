"""Gather per-weapon random Attacks after the native group choice."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.engine.attack_sequence_model import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    GatheredAttackContribution,
    GatheredAttackGroup,
)
from warhammer40k_core.engine.command_reroll_windows import request_command_reroll_if_available
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.native_attack_gathering import (
    _pool_digest,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

RANGED_ATTACK_COUNTS_GATHERED = "ranged_attack_counts_gathered"
RANGED_ATTACK_COUNT_SCOPE_CONTEXT_KEY = "ranged_attack_count_scope_id"
_ATTACK_COUNT_ROLL = "number_of_attacks_roll"


def gather_ranged_attack_counts(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    sequence: AttackSequence,
    stratagem_index: StratagemCatalogIndex | None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    group = sequence.current_gathered_group
    if group is None or not group.counts_pending:
        return sequence, None
    if sequence.source_phase is not BattlePhase.SHOOTING or state.out_of_phase_shooting_state:
        raise GameLifecycleError("Deferred attack counts require ordinary Shooting.")
    selection_index = _selected_group_event_index(
        decisions.event_log.records, sequence.sequence_id, group
    )
    rows: list[dict[str, JsonValue]] = []
    for index in group.pool_indices:
        pool = sequence.attack_pools[index]
        if pool.pending_attack_count_bonus is None:
            continue
        scope, spec = _count_roll_spec(
            sequence.sequence_id, sequence.attacker_player_id, index, pool
        )
        events = decisions.event_log.records_since(selection_index + 1)
        original = _original_count_roll(events, scope, spec)
        if original is None:
            original = manager.roll(spec)
            roll = RandomCharacteristicRoll(
                characteristic=Characteristic.ATTACKS,
                timing=RandomCharacteristicTiming.PER_WEAPON,
                scope_id=scope,
                roll_state=original,
                value=original.current_total,
            )
            decisions.event_log.append("random_characteristic_rolled", roll.to_payload())
            events = decisions.event_log.records_since(selection_index + 1)
        current = _current_count_roll(events, original)
        status = request_command_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=current,
            affected_unit_instance_id=sequence.attacking_unit_instance_id,
            source_phase=sequence.source_phase,
            stratagem_index=stratagem_index,
            phase_body_status="await_ranged_attack_count_reroll",
            trigger_context_extra={RANGED_ATTACK_COUNT_SCOPE_CONTEXT_KEY: scope},
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if status is not None:
            return sequence, status
        rows.append(
            {
                "pool_index": index,
                "roll_id": original.original_result.roll_id,
                "attacks": _resolved_count(pool, current),
            }
        )
    evidence = validate_json_value(
        {"sequence_id": sequence.sequence_id, "group_id": group.group_id, "counts": rows}
    )
    pools, resolved_group = apply_ranged_attack_count_evidence(
        evidence=evidence,
        sequence_id=sequence.sequence_id,
        actor_id=sequence.attacker_player_id,
        pools=sequence.attack_pools,
        group=group,
        preceding_events=decisions.event_log.records,
    )
    updated = replace(sequence, attack_pools=pools, current_gathered_group=resolved_group)
    decisions.event_log.append(RANGED_ATTACK_COUNTS_GATHERED, evidence)
    return updated, None


def apply_ranged_attack_count_evidence(
    *,
    evidence: JsonValue,
    sequence_id: str,
    actor_id: str,
    pools: tuple[RangedAttackPool, ...],
    group: GatheredAttackGroup,
    preceding_events: tuple[EventRecord, ...],
) -> tuple[tuple[RangedAttackPool, ...], GatheredAttackGroup]:
    """Authenticate one selected group's transition from planned to gathered."""
    if not group.counts_pending:
        raise GameLifecycleError("Attack-count evidence requires a pending group.")
    from warhammer40k_core.engine.attack_sequence_validation import (
        _validate_gathered_group_matches_attack_pools,
    )

    _validate_gathered_group_matches_attack_pools(
        attack_pools=pools, used_pool_indices=(), gathered_group=group
    )
    selection_index = _selected_group_event_index(preceding_events, sequence_id, group)
    count_events = preceding_events[selection_index + 1 :]
    updated = list(pools)
    contributions: list[GatheredAttackContribution] = []
    rows: list[dict[str, JsonValue]] = []
    for contribution in group.contributions:
        index = contribution.pool_index
        pool = pools[index]
        if pool.pending_attack_count_bonus is not None:
            scope, spec = _count_roll_spec(sequence_id, actor_id, index, pool)
            original = _original_count_roll(count_events, scope, spec)
            if original is None:
                raise GameLifecycleError("Gathered attack count has no physical roll.")
            current = _current_count_roll(count_events, original)
            count = _resolved_count(pool, current)
            rows.append(
                {"pool_index": index, "roll_id": original.original_result.roll_id, "attacks": count}
            )
            updated[index] = replace(pool, attacks=count, pending_attack_count_bonus=None)
            contribution = replace(contribution, attacks=count)
        contributions.append(contribution)
    expected = {"sequence_id": sequence_id, "group_id": group.group_id, "counts": rows}
    if not rows or canonical_json(evidence) != canonical_json(validate_json_value(expected)):
        raise GameLifecycleError("Gathered attack count evidence drifted.")
    return tuple(updated), replace(
        group,
        total_attacks=sum(contribution.attacks for contribution in contributions),
        contributions=tuple(contributions),
        native_snapshots=tuple(
            replace(snapshot, pool_sha256=_pool_digest(updated[snapshot.pool_index]))
            for snapshot in group.native_snapshots
        ),
    )


def _selected_group_event_index(
    events: tuple[EventRecord, ...], sequence_id: str, group: GatheredAttackGroup
) -> int:
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if event.event_type != "decision_recorded" or not isinstance(event.payload, dict):
            continue
        result = event.payload.get("result")
        if (
            isinstance(result, dict)
            and result.get("decision_type") == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE
            and result.get("selected_option_id") == group.group_id
            and isinstance(selection := result.get("payload"), dict)
            and selection.get("sequence_id") == sequence_id
            and selection.get("gathered_group") == group.to_payload()
        ):
            return index
    raise GameLifecycleError("Random ranged attacks require a recorded group selection.")


def _count_roll_spec(
    sequence_id: str, actor_id: str, index: int, pool: RangedAttackPool
) -> tuple[str, DiceRollSpec]:
    expression = pool.weapon_profile.attack_profile.dice_expression
    if expression is None:
        raise GameLifecycleError("Pending ranged attack count has no dice expression.")
    scope = f"ranged-gather:{sequence_id}:pool-{index + 1:03d}:{pool.weapon_instance_id}"
    return scope, DiceRollSpec(
        expression=expression,
        reason=f"Gather random Attacks for {pool.weapon_profile_id} ({scope})",
        roll_type=_ATTACK_COUNT_ROLL,
        actor_id=actor_id,
    )


def _original_count_roll(
    events: tuple[EventRecord, ...], scope: str, spec: DiceRollSpec
) -> DiceRollState | None:
    recorded = [
        value
        for event in events
        if event.event_type == "random_characteristic_rolled"
        and isinstance(value := event.payload, dict)
        and value.get("scope_id") == scope
    ]
    physical = [
        value
        for event in events
        if event.event_type == "dice_rolled"
        and isinstance(value := event.payload, dict)
        and isinstance(raw_spec := value.get("spec"), dict)
        and raw_spec.get("roll_type") == spec.roll_type
        and raw_spec.get("reason") == spec.reason
    ]
    if not recorded and not physical:
        return None
    if len(recorded) != 1 or len(physical) != 1:
        raise GameLifecycleError("Ranged attack count needs one physical and one derived roll.")
    roll = RandomCharacteristicRoll.from_payload(cast(RandomCharacteristicRollPayload, recorded[0]))
    original = roll.roll_state.original_result
    if (
        roll.characteristic is not Characteristic.ATTACKS
        or roll.timing is not RandomCharacteristicTiming.PER_WEAPON
        or roll.roll_state != DiceRollState.from_result(original)
        or original.spec != spec
        or physical[0] != original.to_payload()
    ):
        raise GameLifecycleError("Ranged attack count roll evidence drifted.")
    return roll.roll_state


def _current_count_roll(events: tuple[EventRecord, ...], original: DiceRollState) -> DiceRollState:
    updates: list[DiceRollState] = []
    for event in events:
        if event.event_type != "command_reroll_resolved" or not isinstance(event.payload, dict):
            continue
        raw = event.payload.get("updated_roll_state")
        source = raw.get("original_result") if isinstance(raw, dict) else None
        if (
            not isinstance(source, dict)
            or source.get("roll_id") != original.original_result.roll_id
        ):
            continue
        updates.append(DiceRollState.from_payload(cast(DiceRollStatePayload, raw)))
    if not updates:
        return original
    if (
        len(updates) != 1
        or updates[0].original_result != original.original_result
        or updates[0].result_override is not None
        or len(updates[0].rerolled_indices()) != 1
    ):
        raise GameLifecycleError("Ranged attack count requires one Command Re-roll component.")
    return updates[0]


def _resolved_count(pool: RangedAttackPool, roll: DiceRollState) -> int:
    bonus = pool.pending_attack_count_bonus
    if bonus is None:
        raise GameLifecycleError("Ranged attack count is already committed.")
    return pool.weapon_profile.attack_profile.resolve_value(roll.current_total) + bonus
