"""Authenticate retargeting against accepted declarations and recorded choices."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import msgspec

from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.target_replacement import (
    SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
    TargetReplacementContext,
    replacement_request,
    replacement_selection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler


class _ReplacementPool(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    pool_index: int
    attack_pool: dict[str, object]


class _Plan(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    pool_indices: tuple[int, ...]
    replacement_pools: tuple[_ReplacementPool, ...]
    forgone_pool_indices: tuple[int, ...]


def _pool(value: object) -> RangedAttackPool:
    if not isinstance(value, dict):
        raise GameLifecycleError("Recorded replacement pool must be an object.")
    return RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, value))


def _pool_tuple(value: object) -> tuple[RangedAttackPool, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Recorded replacement pools must be an array.")
    return tuple(_pool(item) for item in cast(list[object], value))


def accepted_pools(
    decisions: DecisionController,
    record: DecisionRecord,
) -> tuple[RangedAttackPool, ...]:
    return _accepted_pools(decisions.event_log.records, record)


def _accepted_pools(
    event_records: tuple[EventRecord, ...], record: DecisionRecord
) -> tuple[RangedAttackPool, ...]:
    events = [
        event
        for event in event_records
        if event.event_type
        in (
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
        )
        and isinstance(event.payload, dict)
        and event.payload.get("result_id") == record.result.result_id
    ]
    if len(events) != 1:
        raise GameLifecycleError("Replacement requires one accepted declaration event.")
    payload = events[0].payload
    if not isinstance(payload, dict) or "attack_pools" not in payload:
        raise GameLifecycleError("Accepted declaration pools are missing.")
    return _pool_tuple(payload["attack_pools"])


def validate_sequence_authority(
    decisions: DecisionController,
    record: DecisionRecord,
    sequence: AttackSequence,
) -> None:
    _validate_sequence_history(
        decisions.event_log.records, tuple(decisions.records), record, sequence
    )


def validate_completed_replacement_authority(
    *, event_records: tuple[EventRecord, ...], sequence: AttackSequence
) -> None:
    """Completion consumers authenticate the same pool changes as active owners."""
    records = tuple(
        DecisionRecord.from_payload(cast(DecisionRecordPayload, event.payload))
        for event in event_records
        if event.event_type == "decision_recorded"
    )
    declarations = tuple(
        record
        for record in records
        if sequence.sequence_id == f"out-of-phase-attack-sequence:{record.result.result_id}"
    )
    if len(declarations) != 1:
        raise GameLifecycleError("Completed replacement requires one declaration decision.")
    _validate_sequence_history(event_records, records, declarations[0], sequence)


def _validate_sequence_history(
    event_records: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    record: DecisionRecord,
    sequence: AttackSequence,
) -> None:
    expected = _accepted_pools(event_records, record)
    forgone: set[int] = set()
    records_by_result_id = {r.result.result_id: r for r in records}
    for event in event_records:
        if event.event_type != "target_replacement_resolved":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Replacement event must be an object.")
        context = TargetReplacementContext.from_payload(payload.get("context"))
        if context.action_id != sequence.sequence_id:
            continue
        result_id = payload.get("source_decision_result_id")
        if not isinstance(result_id, str) or result_id not in records_by_result_id:
            raise GameLifecycleError("Replacement event has no controlling-player record.")
        replacement = records_by_result_id[result_id]
        selected = replacement_selection(
            request=replacement.request,
            result=replacement.result,
            current=context,
        )
        if (
            context.actor_id != sequence.attacker_player_id
            or context.source_unit_instance_id != sequence.attacking_unit_instance_id
            or payload.get("source_decision_request_id") != replacement.request.request_id
            or payload.get("replacement_target_ids")
            != (None if selected is None else list(selected))
        ):
            raise GameLifecycleError("Replacement event source authority drift.")
        if selected is None:
            try:
                indices = msgspec.convert(
                    payload.get("pool_indices"), type=tuple[int, ...], strict=True
                )
            except msgspec.ValidationError as exc:
                raise GameLifecycleError("Replacement selection indices are invalid.") from exc
            updated = expected
            skipped = indices
        else:
            option = next(
                o for o in context.options if o.option_id == replacement.result.selected_option_id
            )
            try:
                plan = msgspec.convert(option.selection_payload, type=_Plan, strict=True)
            except msgspec.ValidationError as exc:
                raise GameLifecycleError("Replacement weapon plan schema is invalid.") from exc
            indices = plan.pool_indices
            skipped = plan.forgone_pool_indices
            changed = {
                entry.pool_index: _pool(entry.attack_pool) for entry in plan.replacement_pools
            }
            if (
                len(changed) != len(plan.replacement_pools)
                or set(changed).intersection(skipped)
                or set(changed) | set(skipped) != set(indices)
                or any(p.target_unit_instance_id not in selected for p in changed.values())
            ):
                raise GameLifecycleError("Replacement weapon plan partitions are invalid.")
            updated = tuple(changed.get(i, pool) for i, pool in enumerate(expected))
        if (
            not indices
            or len(set(indices)) != len(indices)
            or any(i < 0 or i >= len(expected) or i in forgone for i in indices)
            or context.selection_id != "weapons:" + ",".join(str(i) for i in indices)
            or set(context.original_target_ids)
            != {expected[i].target_unit_instance_id for i in indices}
        ):
            raise GameLifecycleError("Replacement changed its original weapon/target selection.")
        if payload.get("pool_indices") != list(indices) or payload.get(
            "forgone_pool_indices"
        ) != list(skipped):
            raise GameLifecycleError("Replacement event pool partitions drift.")
        if any(
            (
                old.weapon_instance_id,
                old.attacker_model_instance_id,
                old.wargear_id,
                old.weapon_profile_id,
                old.shooting_type,
                old.firing_deck_source_unit_instance_id,
                old.firing_deck_source_model_instance_id,
            )
            != (
                new.weapon_instance_id,
                new.attacker_model_instance_id,
                new.wargear_id,
                new.weapon_profile_id,
                new.shooting_type,
                new.firing_deck_source_unit_instance_id,
                new.firing_deck_source_model_instance_id,
            )
            for old, new in zip(expected, updated, strict=True)
        ):
            raise GameLifecycleError(
                "Replacement changed a committed physical weapon or shooting type."
            )
        if _pool_tuple(payload.get("attack_pools")) != updated:
            raise GameLifecycleError("Replacement event changed unselected attack pools.")
        forgone.update(skipped)
        expected = updated
    if sequence.attack_pools != expected or not forgone.issubset(sequence.used_pool_indices):
        raise GameLifecycleError("Replacement attack sequence differs from its decision history.")


def validate_restored_replacements(
    *,
    state: GameState,
    decisions: DecisionController,
    handler: ShootingPhaseHandler,
) -> None:
    from warhammer40k_core.engine.shooting_target_replacement import (
        active_shooting_sequence,
        declaration_record_for_sequence,
        next_shooting_target_replacement,
    )

    replacement_records = [
        record
        for record in decisions.records
        if record.request.decision_type == SELECT_TARGET_REPLACEMENT_DECISION_TYPE
    ]
    resolved_ids: list[JsonValue] = []
    for event in decisions.event_log.records:
        if event.event_type == "target_replacement_resolved":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Replacement resolution must be an object.")
            context = TargetReplacementContext.from_payload(event.payload.get("context"))
            result_id = event.payload.get("source_decision_result_id")
            matches = [r for r in replacement_records if r.result.result_id == result_id]
            if len(matches) != 1:
                raise GameLifecycleError("Replacement resolution has no unique decision.")
            replacement_selection(
                request=matches[0].request, result=matches[0].result, current=context
            )
            resolved_ids.append(result_id)
    if sorted(cast(list[str], resolved_ids)) != sorted(
        r.result.result_id for r in replacement_records
    ):
        raise GameLifecycleError("Replacement decision/resolution history is incomplete.")
    for pending in decisions.queue.pending_requests:
        if pending.decision_type != SELECT_TARGET_REPLACEMENT_DECISION_TYPE:
            continue
        current = next_shooting_target_replacement(
            handler=handler,
            state=state,
            decisions=decisions,
            sequence=active_shooting_sequence(state),
        )
        if (
            current is None
            or replacement_request(request_id=pending.request_id, context=current.context)
            != pending
        ):
            raise GameLifecycleError("Restored target replacement request drift.")
    for sequence in (
        None if state.shooting_phase_state is None else state.shooting_phase_state.attack_sequence,
        None
        if state.out_of_phase_shooting_state is None
        else state.out_of_phase_shooting_state.attack_sequence,
    ):
        if sequence is not None and replacement_records:
            record, _ = declaration_record_for_sequence(decisions, sequence)
            validate_sequence_authority(decisions, record, sequence)
