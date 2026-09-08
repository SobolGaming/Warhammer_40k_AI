from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackSequenceHooks,
    AttackSequencePayload,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
    pending_cause_for_model,
    replace_retained_destruction,
    retained_destruction_for_model,
    retained_destructions,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def begin_retained_destruction_cleanup(
    *,
    state: GameState,
    decisions: DecisionController,
    reason: str,
    unit_instance_id: str | None = None,
    model_instance_id: str | None = None,
) -> LifecycleStatus | None:
    if reason not in ("phase_end", "unit_fight_completed", "model_shoot_completed"):
        raise GameLifecycleError("Retained destruction cleanup boundary is unsupported.")
    if (unit_instance_id is None) != (reason == "phase_end"):
        raise GameLifecycleError("Retained destruction cleanup unit boundary drift.")
    if (model_instance_id is not None) != (reason == "model_shoot_completed"):
        raise GameLifecycleError("Retained destruction cleanup model boundary drift.")
    unit_model_ids = (
        None
        if unit_instance_id is None
        else {
            model.model_instance_id
            for model in rules_unit_view_by_id(
                state=state, unit_instance_id=unit_instance_id
            ).own_models
        }
    )
    for record in retained_destructions(state=state):
        if record.stage is not RetainedDestructionStage.WAITING:
            continue
        if unit_model_ids is not None and record.model_instance_id not in unit_model_ids:
            continue
        if model_instance_id is not None and record.model_instance_id != model_instance_id:
            continue
        if (
            reason == "unit_fight_completed"
            and record.selected_action is not RetainedAttackAction.FIGHT
        ):
            continue
        if (
            reason == "model_shoot_completed"
            and record.selected_action is not RetainedAttackAction.SHOOT
        ):
            raise GameLifecycleError(
                "Retained destruction shooting completion has no shooting grant."
            )
        updated = replace(record, stage=RetainedDestructionStage.READY, completion_reason=reason)
        replace_retained_destruction(state=state, original=record, updated=updated)
        decisions.event_log.append(
            "fight_on_death_destruction_ready",
            {
                "cause_id": record.cause_id,
                "model_instance_id": record.model_instance_id,
                "reason": reason,
                "unit_instance_id": unit_instance_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": None
                if state.current_battle_phase is None
                else state.current_battle_phase.value,
            },
        )
    return continue_retained_destruction_cleanup(state=state, decisions=decisions)


def continue_retained_destruction_cleanup(
    *, state: GameState, decisions: DecisionController
) -> LifecycleStatus | None:
    while True:
        ready = tuple(
            record
            for record in retained_destructions(state=state)
            if record.stage is RetainedDestructionStage.READY
        )
        if not ready:
            return None
        record = ready[0]
        resolving = replace(record, stage=RetainedDestructionStage.RESOLVING)
        replace_retained_destruction(state=state, original=record, updated=resolving)
        if resolving.owner_kind is DestructionOwnerKind.RULE:
            from warhammer40k_core.engine.retained_destruction_rule import (
                resume_retained_rule_destruction,
            )

            status = resume_retained_rule_destruction(
                state=state, decisions=decisions, record=resolving
            )
        elif resolving.owner_kind is DestructionOwnerKind.ATTACK:
            from warhammer40k_core.engine.attack_sequence_destruction_boundary import (
                resolve_pending_attack_destruction_until_blocked,
            )

            sequence = attack_sequence_for_retained_destruction(resolving)
            updated_sequence, status = resolve_pending_attack_destruction_until_blocked(
                state=state,
                decisions=decisions,
                manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
                attack_sequence=sequence,
                hooks=AttackSequenceHooks.empty(),
            )
            if (
                status is None
                and updated_sequence.pending_destroyed_transport_disembark is not None
            ):
                updated_sequence, status = continue_retained_transport_cleanup(
                    state=state,
                    decisions=decisions,
                    sequence=updated_sequence,
                )
            if status is not None:
                current = retained_destruction_for_model(
                    state=state, model_instance_id=resolving.model_instance_id
                )
                if current is None:
                    raise GameLifecycleError("Retained destruction lost its interrupted owner.")
                record_retained_attack_progress(
                    state=state,
                    decisions=decisions,
                    record=current,
                    sequence=updated_sequence,
                )
        else:
            from warhammer40k_core.engine.retained_destruction_attack import (
                resume_retained_attack_collateral,
            )

            updated_collateral_sequence, status = resume_retained_attack_collateral(
                state=state,
                decisions=decisions,
                record=resolving,
                attack_sequence=attack_sequence_for_retained_destruction(resolving),
            )
            if status is not None:
                current = retained_destruction_for_model(
                    state=state, model_instance_id=resolving.model_instance_id
                )
                if current is None or updated_collateral_sequence is None:
                    raise GameLifecycleError("Retained collateral lost its interrupted owner.")
                record_retained_attack_progress(
                    state=state,
                    decisions=decisions,
                    record=current,
                    sequence=updated_collateral_sequence,
                )
        if status is not None:
            return status
        complete_removed_retained_destructions(state=state, decisions=decisions)


def continue_retained_transport_cleanup(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import (
        _continue_pending_destroyed_transport_disembark,
    )

    updated, _allocated, status = _continue_pending_destroyed_transport_disembark(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=sequence,
        allocated_model_ids=(),
        hooks=AttackSequenceHooks.empty(),
    )
    if updated is None:
        raise GameLifecycleError("Retained Transport lost its cleanup sequence.")
    return updated, status


def active_retained_attack_destruction(*, state: GameState) -> RetainedModelDestruction | None:
    records = tuple(
        record
        for record in retained_destructions(state=state)
        if record.stage in (RetainedDestructionStage.RESOLVING, RetainedDestructionStage.REMOVED)
        and record.owner_kind
        in (DestructionOwnerKind.ATTACK, DestructionOwnerKind.ATTACK_COLLATERAL)
    )
    if not records:
        return None
    causes = {cause.cause_id: cause for cause in state.model_destruction_cause_authorities}
    record_ids = {record.cause_id for record in records}
    leaves = tuple(
        record
        for record in records
        if not any(record.cause_id in causes[other_id].parent_cause_ids for other_id in record_ids)
    )
    if len(leaves) != 1:
        raise GameLifecycleError("Retained attack cleanup has ambiguous active continuations.")
    return leaves[0]


def record_retained_attack_progress(
    *,
    state: GameState,
    decisions: DecisionController,
    record: RetainedModelDestruction,
    sequence: AttackSequence,
) -> None:
    progress = cast(dict[str, JsonValue], sequence.to_payload())
    updated = replace(record, owner_progress=progress)
    replace_retained_destruction(state=state, original=record, updated=updated)
    decisions.event_log.append(
        "fight_on_death_destruction_progressed",
        {
            "cause_id": record.cause_id,
            "model_instance_id": record.model_instance_id,
            "attack_sequence": progress,
            "pending_request_ids": [
                request.request_id for request in decisions.queue.pending_requests
            ],
        },
    )


def attack_sequence_for_retained_destruction(record: RetainedModelDestruction) -> AttackSequence:
    if record.owner_kind not in (
        DestructionOwnerKind.ATTACK,
        DestructionOwnerKind.ATTACK_COLLATERAL,
    ):
        raise GameLifecycleError("Retained destruction is not owned by an attack sequence.")
    original = (
        record.owner_context
        if record.owner_kind is DestructionOwnerKind.ATTACK
        else record.owner_context["attack_sequence"]
    )
    sequence = AttackSequence.from_payload(
        cast(
            AttackSequencePayload,
            original if record.owner_progress is None else record.owner_progress,
        )
    )
    if record.owner_kind is DestructionOwnerKind.ATTACK_COLLATERAL:
        return sequence
    pending = sequence.current_pending_attack_destruction
    if pending is None or pending.damage_application.model_instance_id != record.model_instance_id:
        raise GameLifecycleError("Retained attack destruction owner identity drift.")
    if sequence.attacks_resolved_event_id is None:
        raise GameLifecycleError("Retained attack destruction lacks one completed attack boundary.")
    return replace(sequence, pending_attack_destructions=(pending,))


def record_retained_destruction_completion(
    *, state: GameState, decisions: DecisionController, record: RetainedModelDestruction
) -> None:
    causes = tuple(
        cause
        for cause in state.model_destruction_cause_authorities
        if cause.cause_id == record.cause_id
    )
    if len(causes) != 1 or causes[0].model_destroyed_event is None:
        raise GameLifecycleError("Retained destruction completed without consuming its cause.")
    current = tuple(
        value for value in retained_destructions(state=state) if value.cause_id == record.cause_id
    )
    if len(current) != 1 or current[0].stage is not RetainedDestructionStage.REMOVED:
        raise GameLifecycleError("Completed retained destruction lacks its removal continuation.")
    if any(
        event.event_type == "fight_on_death_destruction_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("cause_id") == record.cause_id
        for event in decisions.event_log.records
    ):
        raise GameLifecycleError("Retained destruction completed twice.")
    state.remove_persisting_effects_by_id((record.effect_id,))
    decisions.event_log.append(
        "fight_on_death_destruction_completed",
        {
            "cause_id": record.cause_id,
            "model_instance_id": record.model_instance_id,
            "model_destroyed_event_id": causes[0].model_destroyed_event.event_id,
            "reason": record.completion_reason,
        },
    )


def complete_removed_retained_destructions(
    *, state: GameState, decisions: DecisionController
) -> None:
    for record in retained_destructions(state=state):
        if record.stage is RetainedDestructionStage.REMOVED:
            record_retained_destruction_completion(state=state, decisions=decisions, record=record)


def destruction_waits_for_retained_casualty(*, state: GameState, model_instance_id: str) -> bool:
    cause = pending_cause_for_model(state=state, model_instance_id=model_instance_id)
    causes = {record.cause_id: record for record in state.model_destruction_cause_authorities}
    for record in retained_destructions(state=state):
        if record.stage is not RetainedDestructionStage.WAITING:
            continue
        ancestors = list(causes[record.cause_id].parent_cause_ids)
        while ancestors:
            ancestor_id = ancestors.pop()
            if ancestor_id == cause.cause_id:
                return True
            ancestors.extend(causes[ancestor_id].parent_cause_ids)
    return False
