"""Authenticate Hazardous casualties awaiting their individual destruction owner."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
    model_by_id,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    DamageApplicationLogicalDeathTransition,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.mortal_wound_application_authority import (
    completion_events_for_authority,
    mortal_wound_application_authority_inventory,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_shooting import retained_shooting_executions

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def pending_hazardous_logical_deaths(
    *, state: GameState, event_records: tuple[EventRecord, ...]
) -> tuple[EventRecord, ...]:
    from warhammer40k_core.engine.attack_sequence_hazardous import (
        validate_hazardous_mortal_wound_source_context,
    )
    from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state

    claimed = {
        authority.logical_death_event.event_id
        for authority in state.model_destruction_cause_authorities
    }
    hosts = (
        state.shooting_phase_state,
        state.fight_phase_state,
        state.out_of_phase_shooting_state,
        *(execution.suspended_shooting for execution in retained_shooting_executions(state=state)),
    )
    sequences = {
        host.attack_sequence.sequence_id: host.attack_sequence
        for host in hosts
        if host is not None and host.attack_sequence is not None
    }
    active = active_attack_sequence_for_state(state)
    if active is not None:
        sequences[active.sequence_id] = active
    applications = mortal_wound_application_authority_inventory(
        event_records=event_records, game_id=state.game_id
    )
    result: list[EventRecord] = []
    for _start, authority in applications.values():
        context = authority.source_context
        if (
            authority.destruction_evidence is not None
            or not isinstance(context, dict)
            or context.get("source_kind") != "hazardous"
        ):
            continue
        completions = completion_events_for_authority(
            authority=authority, event_records=event_records
        )
        if not completions:
            # An unfinished allocation is owned by its pending mortal-wound request.
            continue
        if len(completions) != 1 or not isinstance(completions[0].payload, dict):
            raise GameLifecycleError("Retained Hazardous application completion drift.")
        application = MortalWoundApplication.from_payload(
            cast(MortalWoundApplicationPayload, completions[0].payload["application"])
        )
        logical_events = tuple(
            event
            for event in event_records
            if event.event_type == MODEL_LOGICAL_DEATH_RECORDED_EVENT
            and event.event_id not in claimed
            and model_logical_death_record_from_event(event).producer_id == authority.application_id
        )
        if not logical_events:
            continue
        sequence_id = context.get("sequence_id")
        if type(sequence_id) is not str or sequence_id not in sequences:
            raise GameLifecycleError("Retained Hazardous casualties lost their attack host.")
        sequence = sequences[sequence_id]
        if not sequence.is_complete:
            raise GameLifecycleError("Retained Hazardous casualties precede completed attacks.")
        validate_hazardous_mortal_wound_source_context(
            state=state,
            attack_sequence=sequence,
            source_context_payload=context,
            mortal_wounds=authority.mortal_wounds,
        )
        for event in logical_events:
            record = model_logical_death_record_from_event(event)
            damage = [
                entry
                for entry in application.applications
                if entry.destroyed and entry.model_instance_id == record.model_instance_id
            ]
            model = model_by_id(state=state, model_instance_id=record.model_instance_id)
            battlefield = state.battlefield_state
            if (
                len(damage) != 1
                or not isinstance(record.transition, DamageApplicationLogicalDeathTransition)
                or record.transition.damage_application != damage[0].to_payload()
                or not record.placement_retained
                or model.is_alive
                or battlefield is None
                or battlefield.model_placement_or_none(record.model_instance_id)
                != record.destroyed_model_placement
                or record.rules_unit_instance_id != authority.target_unit_instance_id
                or record.physical_unit_instance_id
                not in authority.target_lineage.component_unit_instance_ids
                or record.cause_kind is not authority.initial_logical_death_cause_binding.cause_kind
            ):
                raise GameLifecycleError("Pending retained Hazardous casualty authority drift.")
            result.append(event)
    return tuple(result)
