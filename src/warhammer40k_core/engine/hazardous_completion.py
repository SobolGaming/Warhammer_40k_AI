"""Hazardous is one owned mandatory rule in the after-attacks timing batch."""

from __future__ import annotations

from functools import partial

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.attack_sequence_hazardous import (
    _resolve_hazardous_tests,
    validate_hazardous_mortal_wound_source_context,
)
from warhammer40k_core.engine.attack_sequence_model import HAZARDOUS_SOURCE_KIND
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.hazardous_retention import resume_retained_hazardous_destructions
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_resolution_request,
    mortal_wound_resolution_progress,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batch_from_event,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.weapon_abilities import HAZARDOUS_RULE_ID, has_weapon_keyword


def hazardous_candidates(
    context: AttackSequenceCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    sequence = context.attack_sequence
    if not any(
        has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
        for pool in sequence.attack_pools
    ):
        return ()
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"hazardous-completion:{sequence.sequence_id}",
                player_id=sequence.attacker_player_id,
                source_rule_id=HAZARDOUS_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
                payload={"sequence_id": sequence.sequence_id},
            ),
            activate=partial(_activate, context),
        ),
    )


def _activate(context: AttackSequenceCompletedContext) -> LifecycleStatus | None:
    resumed, status = resume_retained_hazardous_destructions(
        state=context.state, decisions=context.decisions, sequence=context.attack_sequence
    )
    if resumed:
        return status
    resolved = tuple(
        event
        for event in context.decisions.event_log.records
        if event.event_type
        in ("hazardous_test_resolved", "retained_shooting_hazardous_automatically_passed")
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == context.attack_sequence.sequence_id
    )
    if resolved:
        if len(resolved) != 1:
            raise GameLifecycleError("Hazardous completion was resolved twice.")
        return None
    return _resolve_hazardous_tests(
        state=context.state,
        decisions=context.decisions,
        manager=context.dice_manager,
        attack_sequence=context.attack_sequence,
    )


def is_hazardous_request(request: DecisionRequest) -> bool:
    if not is_mortal_wound_resolution_request(request):
        return False
    source = mortal_wound_resolution_progress(request).source_context
    return isinstance(source, dict) and source.get("source_kind") == HAZARDOUS_SOURCE_KIND


def hazardous_sequence_for_progress(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    progress: MortalWoundApplicationProgress,
) -> AttackSequence:
    source = progress.source_context
    if not isinstance(source, dict) or type(source.get("sequence_id")) is not str:
        raise GameLifecycleError("Hazardous completion requires a source sequence.")
    sequence_id = source["sequence_id"]
    if type(sequence_id) is not str:
        raise GameLifecycleError("Hazardous completion sequence identifier is malformed.")
    sequence = completed_attack_sequence(event_records=event_records, sequence_id=sequence_id)
    batches: dict[str, TimingBatch] = {}
    for event in event_records:
        if event.event_type == TIMING_BATCH_EVENT_TYPE:
            batch = timing_batch_from_event(event)
            if batch.batch_id in batches:
                del batches[batch.batch_id]
            batches[batch.batch_id] = batch
    selected = tuple(
        batch for batch in batches.values() if batch.selected_participant_id is not None
    )
    if (
        not selected
        or selected[-1].selected_participant_id != f"hazardous-completion:{sequence_id}"
        or progress.source_rule_id != HAZARDOUS_RULE_ID
        or progress.application_id != f"{sequence_id}:hazardous:mortal-wounds"
        or progress.target_unit_instance_id != sequence.attacking_unit_instance_id
        or progress.defender_player_id != sequence.attacker_player_id
    ):
        raise GameLifecycleError("Hazardous completion selected-rule authority drift.")
    validate_hazardous_mortal_wound_source_context(
        state=state,
        attack_sequence=sequence,
        source_context_payload=source,
        mortal_wounds=progress.mortal_wounds,
    )
    return sequence


def apply_hazardous_completion_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_sequence_group_selection import (
        _continue_hazardous_after_mortal_wound_feel_no_pain,
    )
    from warhammer40k_core.engine.attack_sequence_mortal_wound_logical_death import (
        resolve_attack_sequence_mortal_wound_feel_no_pain,
    )

    sequence = hazardous_sequence_for_progress(
        state=state,
        event_records=decisions.event_log.records,
        progress=mortal_wound_resolution_progress(request),
    )
    routed = resolve_attack_sequence_mortal_wound_feel_no_pain(
        state=state,
        decisions=decisions,
        attack_sequence=sequence,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    _sequence, _allocated, status = _continue_hazardous_after_mortal_wound_feel_no_pain(
        state=state,
        decisions=decisions,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        routed=routed,
    )
    return status
