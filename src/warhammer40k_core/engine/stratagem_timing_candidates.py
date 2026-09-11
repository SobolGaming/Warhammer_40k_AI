from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    create_stratagem_use_decision_request,
    stratagem_decline_option,
    stratagem_selection_from_decision_result,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def stratagem_timing_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    cost_modifiers: StratagemCostModifierRegistry,
    requested_event_type: str,
) -> tuple[TimingRuleCandidate, ...]:
    """Enumerate each available Stratagem as its owner's optional rule occurrence."""
    if context.timing_window_id is None:
        raise GameLifecycleError("Stratagem timing candidates require a trigger occurrence ID.")
    options = stratagem_use_options_from_index(
        state=state,
        index=index,
        context=context,
        stratagem_cost_modifier_registry=cost_modifiers,
    )
    candidates: list[TimingRuleCandidate] = []
    for record in index.records_for(context.trigger_kind):
        participant_id = (
            f"stratagem:{context.timing_window_id}:{context.player_id}:{record.record_id}"
        )
        if any(
            isinstance(decision.request.payload, dict)
            and decision.request.payload.get("timing_participant_id") == participant_id
            for decision in decisions.records
        ):
            continue
        record_payload = record.to_payload()
        eligible = tuple(
            option
            for option in options
            if isinstance(option.payload, dict)
            and option.payload.get("catalog_record") == record_payload
        )
        if not eligible:
            continue
        candidates.append(
            TimingRuleCandidate(
                participant=_participant(record, context),
                activate=partial(
                    _activate,
                    state=state,
                    decisions=decisions,
                    context=context,
                    options=eligible,
                    participant_id=participant_id,
                    requested_event_type=requested_event_type,
                ),
            )
        )
    return tuple(candidates)


def _participant(
    record: StratagemCatalogRecord, context: StratagemEligibilityContext
) -> SequencingParticipant:
    return SequencingParticipant(
        participant_id=f"stratagem:{context.timing_window_id}:{context.player_id}:{record.record_id}",
        player_id=context.player_id,
        source_rule_id=record.definition.source_id,
        requirement=SequencingRequirement.OPTIONAL,
        label=record.definition.name,
        payload=validate_json_value(
            {"catalog_record_id": record.record_id, "context": context.to_payload()}
        ),
    )


def validate_timing_stratagem_source(
    *,
    request: DecisionRequest,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    events: tuple[EventRecord, ...],
    decisions: tuple[DecisionRecord, ...],
    requested_index: int,
) -> TimingBatch | None:
    from warhammer40k_core.engine.timing_batch_runtime import (
        TIMING_BATCH_EVENT_TYPE,
        timing_batch_from_event,
        timing_batches_from_records,
    )

    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem timing request payload must be an object.")
    expected = _participant(record, context)
    batches: dict[str, TimingBatch] = {}
    for event in events[:requested_index]:
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        batch = timing_batch_from_event(event)
        if batch.batch_id in batches:
            del batches[batch.batch_id]
        batches[batch.batch_id] = batch
    selected = tuple(
        batch for batch in batches.values() if batch.selected_participant_id is not None
    )
    identifier = payload.get("timing_participant_id")
    if identifier is None:
        if any(batch.selected_participant_id == expected.participant_id for batch in selected):
            raise GameLifecycleError("Stratagem timing request lost its selected participant.")
        return None
    if identifier != expected.participant_id or not selected:
        raise GameLifecycleError("Stratagem timing source identity drifted.")
    current = selected[-1]
    if current.selected_participant_id != identifier or expected not in current.participants:
        raise GameLifecycleError("Stratagem timing source owner or selected rule drifted.")
    history = timing_batches_from_records(
        events=events[:requested_index],
        records=decisions,
        context=current.context,
    )
    if not history or history[-1] != current:
        raise GameLifecycleError("Stratagem timing source history drifted.")
    return current


def validate_pending_timing_stratagem_request(
    *, decisions: DecisionController, request: DecisionRequest
) -> TimingBatch | None:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Pending Stratagem request must have an object payload.")
    if "timing_participant_id" in payload and set(payload) != {
        "stratagem_context",
        "finite",
        "timing_participant_id",
    }:
        raise GameLifecycleError("Pending Stratagem timing request shape drifted.")
    matches = tuple(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Pending Stratagem request lacks its exact occurrence.")
    choices = tuple(
        option
        for option in request.options
        if isinstance(option.payload, dict) and "catalog_record" in option.payload
    )
    if not choices:
        raise GameLifecycleError("Pending Stratagem request has no source-backed use option.")
    current: TimingBatch | None = None
    for option in choices:
        selection = stratagem_selection_from_decision_result(
            DecisionResult.for_request(
                request=request,
                result_id="stratagem-timing-validation",
                selected_option_id=option.option_id,
            )
        )
        if selection is None:
            raise GameLifecycleError("Pending Stratagem use option has no typed selection.")
        context, record, _, _ = selection
        validated = validate_timing_stratagem_source(
            request=request,
            record=record,
            context=context,
            events=decisions.event_log.records,
            decisions=decisions.records,
            requested_index=matches[0],
        )
        if validated is not None:
            if current is not None and current != validated:
                raise GameLifecycleError("Pending Stratagem options cross timing batches.")
            current = validated
    return current


def _activate(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    options: tuple[DecisionOption, ...],
    participant_id: str,
    requested_event_type: str,
) -> LifecycleStatus:
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
        payload_extra={"timing_participant_id": participant_id},
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        requested_event_type,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": context.phase.value,
            "player_id": context.player_id,
            "stratagem_context": context.to_payload(),
            "request_id": request.request_id,
            "timing_participant_id": participant_id,
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": context.phase.value,
            "phase_body_status": "attack_completion_stratagem_pending",
        },
    )
