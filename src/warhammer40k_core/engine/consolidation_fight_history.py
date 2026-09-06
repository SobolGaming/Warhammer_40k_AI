"""Authenticate consolidation response queues against movement and decision history."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, ConsolidationModeKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_historical_eligibility import (
    forced_fight_eligibility_contexts_before_event,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightActivationSelectionPayload,
    FightPhaseState,
    FightPhaseStatePayload,
)
from warhammer40k_core.engine.fight_resolution import fight_movement_proposal_from_payload
from warhammer40k_core.engine.forced_fight_context import (
    ForcedFightActivationContext,
    ForcedFightActivationContextPayload,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_identity_history_contains
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_fight_2026_09 import (
    CONSOLIDATION_SOURCE_ID,
    ONGOING_SOURCE_ID,
)


def validate_consolidation_fight_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    triggers = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "fight_movement_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("proposal_kind") == "consolidate"
    )
    if not triggers:
        return
    records_by_result = {record.result.result_id: record for record in decision_records}
    for trigger_index, trigger in triggers:
        payload = _object(trigger.payload)
        result_id = payload.get("result_id")
        if not isinstance(result_id, str) or result_id not in records_by_result:
            raise GameLifecycleError("Consolidation response lacks its movement decision.")
        proposal = fight_movement_proposal_from_payload(records_by_result[result_id].result.payload)
        if proposal.consolidation_mode not in {
            ConsolidationModeKind.ONGOING,
            ConsolidationModeKind.ENGAGING,
        }:
            continue
        resolution = _object(payload.get("resolution"))
        endpoint = _object(resolution.get("endpoint_witness"))
        engaged = _identifiers(endpoint.get("engaged_after_unit_ids"))
        selected = _prior_selected_ids(event_records[:trigger_index], payload)
        pending = tuple(
            unit_id
            for unit_id in engaged
            if not rules_unit_identity_history_contains(
                state=state,
                identity_ids=selected,
                unit_instance_id=unit_id,
            )
        )
        queue_events = tuple(
            (index, event)
            for index, event in enumerate(event_records)
            if event.event_type
            in {
                "forced_fight_activation_queue_started",
                "forced_fight_activation_queue_skipped",
            }
            and isinstance(event.payload, dict)
            and _trigger_id(event.payload) == trigger.event_id
        )
        if len(queue_events) != 1 or queue_events[0][0] != trigger_index + 1:
            raise GameLifecycleError("Consolidation requires one response boundary after movement.")
        start_index, start = queue_events[0]
        start_payload = _object(start.payload)
        expected_source = (
            ONGOING_SOURCE_ID
            if proposal.consolidation_mode is ConsolidationModeKind.ONGOING
            else CONSOLIDATION_SOURCE_ID
        )
        if not pending:
            if start.event_type != "forced_fight_activation_queue_skipped":
                raise GameLifecycleError("Consolidation cannot queue already-selected enemy units.")
            if start_payload != {
                "game_id": state.game_id,
                "battle_round": payload.get("battle_round"),
                "phase": "fight",
                "active_player_id": payload.get("active_player_id"),
                "phase_body_status": "forced_fight_activation_queue_skipped",
                "source_rule_id": expected_source,
                "trigger_event_id": trigger.event_id,
                "source_unit_instance_id": proposal.unit_instance_id,
                "engaged_enemy_unit_instance_ids": list(engaged),
                "already_selected_unit_instance_ids": list(selected),
            }:
                raise GameLifecycleError("Consolidation skipped-queue source or inventory drift.")
            continue
        if start.event_type != "forced_fight_activation_queue_started":
            raise GameLifecycleError(
                "Consolidation cannot skip outstanding forced-Fight activations."
            )
        context = ForcedFightActivationContext.from_payload(
            cast(
                ForcedFightActivationContextPayload,
                _object(start_payload.get("forced_activation_context")),
            )
        )
        if (
            context.context_id != f"forced-fight:{trigger.event_id}"
            or context.source_rule_id != expected_source
            or context.source_phase is not BattlePhaseKind.FIGHT
            or context.source_unit_instance_id != proposal.unit_instance_id
            or context.transport_unit_instance_id is not None
            or context.eligible_unit_instance_ids != tuple(sorted(pending))
        ):
            raise GameLifecycleError("Consolidation response source or eligible inventory drift.")
        suspended = FightPhaseState.from_payload(
            cast(
                FightPhaseStatePayload,
                _object(start_payload.get("suspended_state")),
            )
        )
        if (
            suspended.forced_activation_context is not None
            or suspended.suspended_state is not None
            or set(suspended.fight_order_state.selected_to_fight_unit_ids) != set(selected)
            or suspended.consolidate_state is None
            or proposal.unit_instance_id not in suspended.consolidate_state.completed_unit_ids
        ):
            raise GameLifecycleError("Consolidation suspended ordinary state drift.")
        _validate_queue_completion(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            start_index=start_index,
            context=context,
            suspended=suspended,
        )


def _validate_queue_completion(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    start_index: int,
    context: ForcedFightActivationContext,
    suspended: FightPhaseState,
) -> None:
    from warhammer40k_core.engine.lifecycle_state_validation import (
        authenticated_forced_fight_selections,
    )

    authenticated = authenticated_forced_fight_selections(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        battle_round=suspended.battle_round,
        active_player_id=suspended.active_player_id,
    )
    selections = tuple(
        selection
        for selection, index, source in authenticated
        if source == context and index > start_index
    )
    completions = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "forced_fight_activation_queue_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("forced_activation_context") == context.to_payload()
    )
    if len(completions) > 1:
        raise GameLifecycleError("Consolidation response queue completed more than once.")
    if not completions:
        current = state.fight_phase_state
        if current is None or current.forced_activation_context != context:
            raise GameLifecycleError("Consolidation lost its pending forced-Fight queue.")
        if current.suspended_state != suspended:
            raise GameLifecycleError("Consolidation suspended state differs from its start event.")
        if current.fight_order_state.activation_selections != selections:
            raise GameLifecycleError("Consolidation forced-Fight selections drifted.")
        return
    index, completion = completions[0]
    if index <= start_index or any(
        source == context and selection_index >= index
        for _selection, selection_index, source in authenticated
    ):
        raise GameLifecycleError("Consolidation response completed before it started.")
    if forced_fight_eligibility_contexts_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=index,
        battle_round=suspended.battle_round,
        context=context,
        prior_selections=selections,
        policy=state.runtime_ruleset_descriptor().fight_policy,
    ):
        raise GameLifecycleError(
            "Consolidation response omitted mandatory forced-Fight activations."
        )
    payload = _object(completion.payload)
    if payload.get("activation_selections") != [selection.to_payload() for selection in selections]:
        raise GameLifecycleError("Consolidation completed selection inventory drift.")
    resumed = FightPhaseState.from_payload(
        cast(
            FightPhaseStatePayload,
            _object(payload.get("resumed_state")),
        )
    )
    expected_order = replace(
        suspended.fight_order_state,
        selected_to_fight_unit_ids=(
            *suspended.fight_order_state.selected_to_fight_unit_ids,
            *(selection.unit_instance_id for selection in selections),
        ),
        activation_selections=(*suspended.fight_order_state.activation_selections, *selections),
    )
    if (
        resumed.fight_order_state != expected_order
        or replace(
            resumed,
            fight_order_state=suspended.fight_order_state,
            allocated_model_ids_this_phase=suspended.allocated_model_ids_this_phase,
            overrun_pile_in_completed_activation_result_ids=suspended.overrun_pile_in_completed_activation_result_ids,
        )
        != suspended
    ):
        raise GameLifecycleError("Consolidation resumed ordinary Fight state drift.")
    if not set(suspended.allocated_model_ids_this_phase).issubset(
        resumed.allocated_model_ids_this_phase
    ):
        raise GameLifecycleError("Consolidation lost prior damage allocation history.")


def _prior_selected_ids(
    events: tuple[EventRecord, ...], trigger: dict[str, JsonValue]
) -> tuple[str, ...]:
    selected: set[str] = set()
    for event in events:
        if event.event_type != "fight_activation_selected" or not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if payload.get("battle_round") != trigger.get("battle_round") or payload.get(
            "active_player_id"
        ) != trigger.get("active_player_id"):
            continue
        forced = payload.get("forced_activation_context")
        if isinstance(forced, dict) and forced.get("source_phase") != "fight":
            continue
        selection = FightActivationSelection.from_payload(
            cast(
                FightActivationSelectionPayload,
                _object(payload.get("activation_selection")),
            )
        )
        selected.add(selection.unit_instance_id)
    return tuple(sorted(selected))


def _trigger_id(payload: dict[str, JsonValue]) -> JsonValue:
    context = payload.get("forced_activation_context")
    return (
        context.get("trigger_event_id")
        if isinstance(context, dict)
        else payload.get("trigger_event_id")
    )


def _object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Consolidation response history requires an object payload.")
    return cast(dict[str, JsonValue], value)


def _identifiers(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        type(item) is not str for item in cast(list[object], value)
    ):
        raise GameLifecycleError("Consolidation response engagement inventory is malformed.")
    return tuple(cast(list[str], value))
