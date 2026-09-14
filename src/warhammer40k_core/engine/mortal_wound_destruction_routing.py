"""Retain rule-effect casualties until shared destruction reactions finish."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_authority import ModelDestructionCauseKind
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundApplicationCompletionContext,
    MortalWoundFeelNoPainContinuationHookRegistry,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
    fixed_mortal_wound_logical_death_recorder,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    MortalWoundApplicationProgressPayload,
    continue_mortal_wound_application,
    mortal_wound_progress_from_payload,
    mortal_wound_progress_to_payload,
    mortal_wound_resolution_progress,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
    retained_destruction_for_model,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_application_authority import (
        MortalWoundApplicationAuthority,
    )

EVIDENCE_KEY = "rule_mortal_wound_destruction_evidence"
STARTED = "rule_mortal_wound_destructions_started"
MODEL_COMPLETED = "rule_mortal_wound_model_destruction_completed"
COMPLETED = "rule_mortal_wound_destructions_completed"


def prepare_rule_mortal_wound_progress(
    progress: MortalWoundApplicationProgress,
) -> MortalWoundApplicationProgress:
    if progress.destruction_evidence is None or not isinstance(progress.source_context, dict):
        raise GameLifecycleError("Rule mortal wounds require destruction evidence and context.")
    if EVIDENCE_KEY in progress.source_context:
        raise GameLifecycleError("Rule mortal wound destruction routing was configured twice.")
    return replace(
        progress,
        destruction_evidence=None,
        logical_death_cause_binding=_binding(progress),
        source_context={
            **progress.source_context,
            EVIDENCE_KEY: validate_json_value(progress.destruction_evidence.to_payload()),
        },
    )


def validate_rule_mortal_wound_progress(progress: MortalWoundApplicationProgress) -> None:
    if (
        progress.destruction_evidence is not None
        or progress.logical_death_cause_binding != _binding(progress)
    ):
        raise GameLifecycleError("Rule mortal wound destruction binding drifted.")
    _evidence(progress)


def _binding(progress: MortalWoundApplicationProgress) -> MortalWoundLogicalDeathCauseBinding:
    return MortalWoundLogicalDeathCauseBinding.fixed(
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT, producer_id=progress.application_id
    )


def _evidence(progress: MortalWoundApplicationProgress) -> MortalWoundDestructionEvidence:
    if not isinstance(progress.source_context, dict):
        raise GameLifecycleError("Rule mortal wound destruction requires context.")
    payload = progress.source_context.get(EVIDENCE_KEY)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Rule mortal wound destruction evidence is missing.")
    return MortalWoundDestructionEvidence.from_payload(
        cast(MortalWoundDestructionEvidencePayload, payload)
    )


def continue_rule_mortal_wound_application(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    progress: MortalWoundApplicationProgress,
    dice_manager: DiceRollManager,
) -> MortalWoundRoutingResult:
    progress = prepare_rule_mortal_wound_progress(progress)
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=request_id,
        progress=progress,
        dice_manager=dice_manager,
        remove_destroyed_models=False,
        logical_death_recorder=fixed_mortal_wound_logical_death_recorder(
            state=state, event_log=decisions.event_log, binding=_binding(progress)
        ),
    )
    return _finish_routing(state=state, decisions=decisions, routed=routed)


def resolve_rule_mortal_wound_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    next_request_id: str,
    dice_manager: DiceRollManager,
) -> MortalWoundRoutingResult:
    progress = mortal_wound_resolution_progress(request)
    validate_rule_mortal_wound_progress(progress)
    routed = resolve_mortal_wound_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        next_request_id=next_request_id,
        dice_manager=dice_manager,
        remove_destroyed_models=False,
        logical_death_recorder=fixed_mortal_wound_logical_death_recorder(
            state=state, event_log=decisions.event_log, binding=_binding(progress)
        ),
    )
    return _finish_routing(state=state, decisions=decisions, routed=routed)


def queue_rule_mortal_wound_request(
    decisions: DecisionController, request: DecisionRequest
) -> None:
    if not decisions.queue.pending_requests:
        decisions.request_decision(request)
    elif decisions.queue.pending_requests != (request,):
        raise GameLifecycleError("Rule mortal wound routing has a different pending request.")


def _finish_routing(
    *, state: GameState, decisions: DecisionController, routed: MortalWoundRoutingResult
) -> MortalWoundRoutingResult:
    if routed.request is not None:
        return routed
    progress = routed.progress
    if routed.application != progress.to_application():
        raise GameLifecycleError("Rule mortal wound completed application drifted.")
    decisions.event_log.append(
        STARTED,
        {
            "progress": validate_json_value(mortal_wound_progress_to_payload(progress)),
            "application": validate_json_value(progress.to_application().to_payload()),
        },
    )
    status = _resume_destructions(state=state, decisions=decisions, progress=progress)
    if status is None:
        return routed
    if status.decision_request is None:
        raise GameLifecycleError("Rule mortal wound destruction must suspend on a request.")
    return MortalWoundRoutingResult(progress=progress, request=status.decision_request)


def _resume_destructions(
    *, state: GameState, decisions: DecisionController, progress: MortalWoundApplicationProgress
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
        continue_applied_mortal_wound_destruction_with_rule_reactions,
    )

    validate_rule_mortal_wound_progress(progress)
    evidence = _evidence(progress)
    for damage in progress.applications:
        if not damage.destroyed:
            continue
        if (
            retained_destruction_for_model(state=state, model_instance_id=damage.model_instance_id)
            is not None
        ):
            continue
        completed = [
            event
            for event in decisions.event_log.records
            if event.event_type == MODEL_COMPLETED
            and isinstance(event.payload, dict)
            and event.payload.get("application_id") == progress.application_id
            and event.payload.get("model_instance_id") == damage.model_instance_id
        ]
        if len(completed) > 1:
            raise GameLifecycleError("Rule mortal wound casualty completed twice.")
        if completed:
            continue
        outcome = continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=decisions,
            damage_application=damage,
            rules_unit_instance_id=progress.target_unit_instance_id,
            source_rule_id=progress.source_rule_id,
            source_result_id=progress.application_id,
            completion_event_type=MODEL_COMPLETED,
            completion_event_payload={
                "application_id": progress.application_id,
                "model_instance_id": damage.model_instance_id,
            },
            destruction_evidence=evidence,
        )
        if outcome.status is not None:
            return outcome.status
    decisions.event_log.append(COMPLETED, {"application_id": progress.application_id})
    return None


def pending_rule_mortal_wound_destructions(
    events: tuple[EventRecord, ...],
) -> tuple[MortalWoundApplicationProgress, ...]:
    pending: dict[str, MortalWoundApplicationProgress] = {}
    seen: set[str] = set()
    model_completions: set[tuple[str, str]] = set()
    retained_completions: set[tuple[str, str]] = set()
    retained_logical_events: set[str] = set()
    for event in events:
        if event.event_type == MODEL_COMPLETED:
            payload = event.payload
            if not isinstance(payload, dict):
                raise GameLifecycleError("Rule mortal wound casualty completion is malformed.")
            application_id = payload.get("application_id")
            model_id = payload.get("model_instance_id")
            if not isinstance(application_id, str) or not isinstance(model_id, str):
                raise GameLifecycleError("Rule mortal wound casualty completion IDs are malformed.")
            if (
                application_id not in pending
                and (application_id, model_id) not in retained_completions
            ) or (application_id, model_id) in model_completions:
                raise GameLifecycleError("Rule mortal wound casualty completion order drifted.")
            model_completions.add((application_id, model_id))
        elif event.event_type == "fight_on_death_retention_opened":
            from warhammer40k_core.engine.retained_destruction_state import RetainedModelDestruction

            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Rule mortal wound retained destruction is malformed.")
            retained = RetainedModelDestruction.from_payload(event.payload.get("destruction"))
            retained_logical_events.add(retained.logical_death_event_id)
        if event.event_type == STARTED:
            progress = progress_from_destruction_start(event)
            if progress.remaining_mortal_wounds or progress.application_id in seen:
                raise GameLifecycleError(
                    "Rule mortal wound destruction start is incomplete or duplicated."
                )
            pending[progress.application_id] = progress
            seen.add(progress.application_id)
        elif event.event_type == COMPLETED:
            if not isinstance(event.payload, dict) or set(event.payload) != {"application_id"}:
                raise GameLifecycleError("Rule mortal wound destruction completion is malformed.")
            application_id = event.payload["application_id"]
            if not isinstance(application_id, str) or application_id not in pending:
                raise GameLifecycleError("Rule mortal wound destruction completion has no start.")
            progress = pending[application_id]
            from warhammer40k_core.engine.model_logical_death import (
                model_logical_death_record_from_event,
            )

            for logical_event in progress.logical_death_events:
                record = model_logical_death_record_from_event(logical_event)
                if (application_id, record.model_instance_id) not in model_completions:
                    if logical_event.event_id not in retained_logical_events:
                        raise GameLifecycleError(
                            "Rule mortal wound destruction completed before its casualties."
                        )
                    # Retention now owns this casualty. Its completion receipt
                    # may follow the packet's handoff, once its reaction finishes.
                    retained_completions.add((application_id, record.model_instance_id))
            del pending[application_id]
    return tuple(reversed(pending.values()))


def progress_from_destruction_start(event: EventRecord) -> MortalWoundApplicationProgress:
    if event.event_type != STARTED:
        raise GameLifecycleError("Rule mortal wound destruction event kind drifted.")
    if not isinstance(event.payload, dict) or set(event.payload) != {
        "progress",
        "application",
    }:
        raise GameLifecycleError("Rule mortal wound destruction start is malformed.")
    raw = event.payload["progress"]
    if not isinstance(raw, dict):
        raise GameLifecycleError("Rule mortal wound destruction progress is malformed.")
    progress = mortal_wound_progress_from_payload(cast(MortalWoundApplicationProgressPayload, raw))
    validate_rule_mortal_wound_progress(progress)
    if event.payload["application"] != progress.to_application().to_payload():
        raise GameLifecycleError("Rule mortal wound completed application drifted.")
    return progress


def rule_mortal_wound_completion_events(
    authority: MortalWoundApplicationAuthority, events: tuple[EventRecord, ...]
) -> tuple[EventRecord, ...]:
    matches: list[EventRecord] = []
    for event in events:
        if event.event_type != STARTED or not isinstance(event.payload, dict):
            continue
        raw = event.payload.get("progress")
        if not isinstance(raw, dict) or raw.get("application_id") != authority.application_id:
            continue
        progress = mortal_wound_progress_from_payload(
            cast(MortalWoundApplicationProgressPayload, raw)
        )
        validate_rule_mortal_wound_progress(progress)
        if (
            progress.source_rule_id != authority.source_rule_id
            or progress.source_context != authority.source_context
            or progress.target_unit_instance_id != authority.target_unit_instance_id
            or progress.defender_player_id != authority.defender_player_id
            or progress.mortal_wounds != authority.mortal_wounds
            or progress.spill_over != authority.spill_over
            or progress.priority_model_ids != authority.priority_model_ids
            or progress.target_lineage != authority.target_lineage
            or progress.remaining_mortal_wounds
            or event.payload.get("application") != progress.to_application().to_payload()
        ):
            raise GameLifecycleError("Rule mortal wound completion authority drifted.")
        matches.append(event)
    return tuple(matches)


def advance_rule_mortal_wound_destructions(
    *,
    state: GameState,
    decisions: DecisionController,
    registry_provider: Callable[[], MortalWoundFeelNoPainContinuationHookRegistry],
) -> LifecycleStatus | None:
    if decisions.queue.pending_requests:
        return None
    pending = pending_rule_mortal_wound_destructions(decisions.event_log.records)
    if not pending:
        return None
    progress = pending[0]
    status = _resume_destructions(state=state, decisions=decisions, progress=progress)
    if status is not None:
        return status
    return registry_provider().complete_application(
        MortalWoundApplicationCompletionContext(
            state=state,
            decisions=decisions,
            progress=progress,
            application=progress.to_application(),
        )
    )


def pending_rule_mortal_wound_logical_deaths(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
    authenticated_retained_destructions: tuple[RetainedModelDestruction, ...],
) -> tuple[EventRecord, ...]:
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.model_logical_death import (
        DamageApplicationLogicalDeathTransition,
        model_logical_death_record_from_event,
    )
    from warhammer40k_core.engine.mortal_wound_application_authority import (
        mortal_wound_application_authority_inventory,
        validate_pending_mortal_wound_application_authority,
    )

    pending = pending_rule_mortal_wound_destructions(event_records)
    claimed = {
        authority.logical_death_event.event_id
        for authority in state.model_destruction_cause_authorities
    }
    inventory = mortal_wound_application_authority_inventory(
        event_records=event_records, game_id=state.game_id
    )
    result: list[EventRecord] = []
    for progress in pending:
        # Retained requests identify a retention record, not their damage packet.
        # Its owning restore service has authenticated the cause, source context,
        # event history and exact offered request or accepted reaction decision.
        retained_owner = any(
            record.owner_kind is DestructionOwnerKind.RULE
            and (record.stage is RetainedDestructionStage.OFFERED or record.is_retained)
            and record.owner_context.get("source_result_id") == progress.application_id
            and record.owner_context.get("source_rule_id") == progress.source_rule_id
            and record.logical_death_event_id
            in {event.event_id for event in progress.logical_death_events}
            for record in authenticated_retained_destructions
        )
        if not retained_owner and not any(
            _has_source_result_reference(request.payload, progress.application_id)
            for request in pending_decision_requests
        ):
            raise GameLifecycleError(
                "Rule mortal wound destruction lacks its pending continuation."
            )
        start = next(
            event
            for event in event_records
            if event.event_type == STARTED
            and progress_from_destruction_start(event).application_id == progress.application_id
        )
        validate_pending_mortal_wound_application_authority(
            state=state,
            event_records=event_records,
            progress=progress,
            request_event=start,
            inventory=inventory,
        )
        for event in progress.logical_death_events:
            if event.event_id in claimed:
                continue
            record = model_logical_death_record_from_event(event)
            damage = [
                entry
                for entry in progress.applications
                if entry.destroyed and entry.model_instance_id == record.model_instance_id
            ]
            battlefield = state.battlefield_state
            if (
                len(damage) != 1
                or not isinstance(record.transition, DamageApplicationLogicalDeathTransition)
                or record.transition.damage_application != damage[0].to_payload()
                or not record.placement_retained
                or model_by_id(state=state, model_instance_id=record.model_instance_id).is_alive
                or battlefield is None
                or battlefield.model_placement_or_none(record.model_instance_id)
                != record.destroyed_model_placement
                or record.rules_unit_instance_id != progress.target_unit_instance_id
                or progress.target_lineage is None
                or record.physical_unit_instance_id
                not in progress.target_lineage.component_unit_instance_ids
            ):
                raise GameLifecycleError("Pending rule mortal wound casualty authority drifted.")
            result.append(event)
    return tuple(result)


def _has_source_result_reference(value: JsonValue, application_id: str) -> bool:
    if isinstance(value, dict):
        return value.get("source_result_id") == application_id or any(
            _has_source_result_reference(child, application_id) for child in value.values()
        )
    if isinstance(value, list):
        return any(_has_source_result_reference(child, application_id) for child in value)
    return False
