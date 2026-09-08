from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    MortalWoundApplication,
    MortalWoundApplicationPayload,
)
from warhammer40k_core.engine.emergency_disembark import (
    transport_hazard_mortal_wound_application_id,
    transport_hazard_mortal_wounds_from_completion_event,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.mortal_wound_application_authority import (
    MORTAL_WOUND_APPLICATION_STARTED_EVENT,
    completion_events_for_authority,
    direct_mortal_wound_damage_snapshot_from_event,
    mortal_wound_application_authority_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_fight_on_death_physical_history import (
    PhysicalAuthorityState,
)
from warhammer40k_core.engine.transports import DestroyedTransportHazardRolls


def apply_logical_death_physical_authority(
    *, authority: dict[str, PhysicalAuthorityState], event: EventRecord
) -> None:
    from warhammer40k_core.engine.model_logical_death import (
        model_logical_death_record_from_event,
    )

    record = model_logical_death_record_from_event(event)
    prior = authority.get(record.model_instance_id)
    placement = record.destroyed_model_placement
    if prior is not None and prior.pose is not None and prior.pose != placement.pose:
        raise GameLifecycleError("Logical-death physical placement history is discontinuous.")
    authority[record.model_instance_id] = PhysicalAuthorityState(
        presence="battlefield" if record.placement_retained else "destroyed",
        pose=placement.pose if record.placement_retained else None,
        wounds_remaining=0,
    )


def _nonlethal_snapshot(
    snapshot: tuple[str, tuple[DamageApplication, ...]],
) -> tuple[str, tuple[DamageApplication, ...]]:
    application_id, applications = snapshot
    dead_ids = {damage.model_instance_id for damage in applications if damage.destroyed}
    return application_id, tuple(
        damage for damage in applications if damage.model_instance_id not in dead_ids
    )


def physical_mortal_wound_damage_snapshot_from_event(
    event: EventRecord, *, event_records: tuple[EventRecord, ...]
) -> tuple[str, tuple[DamageApplication, ...], str] | None:
    """Include deferred death-trigger damage after a physical boundary checkpoint.

    The application owner authenticates these events before physical history is
    replayed. Correlation uses that owner's exact start/completion relationship.
    """
    snapshot = direct_mortal_wound_damage_snapshot_from_event(event)
    if snapshot is not None:
        application_id, applications = _nonlethal_snapshot(snapshot)
        return application_id, applications, "battlefield"
    transport_hazard = transport_hazard_mortal_wounds_from_completion_event(event)
    if (
        transport_hazard is not None
        and type(transport_hazard.disembark) is DestroyedTransportHazardRolls
        and transport_hazard.mortal_wound_application is not None
    ):
        return (
            transport_hazard_mortal_wound_application_id(
                unit_instance_id=transport_hazard.disembark.unit_instance_id,
                disembark_mode=transport_hazard.disembark.disembark_mode,
                battle_round=transport_hazard.disembark.battle_round,
            ),
            transport_hazard.mortal_wound_application.applications,
            "embarked",
        )
    if event.event_type == "decision_requested":
        from warhammer40k_core.engine.decision_request import (
            DecisionRequest,
            DecisionRequestPayload,
        )
        from warhammer40k_core.engine.mortal_wound_model_allocation import (
            is_mortal_wound_resolution_request,
            mortal_wound_resolution_progress,
        )

        request = DecisionRequest.from_payload(cast(DecisionRequestPayload, event.payload))
        if is_mortal_wound_resolution_request(request):
            progress = mortal_wound_resolution_progress(request)
            from warhammer40k_core.engine.mortal_wound_target_lineage import (
                FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY,
            )

            embedded = (
                progress.target_lineage is not None
                and progress.target_lineage.policy == FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY
            )
            application_id, applications = _nonlethal_snapshot(
                (progress.application_id, progress.applications)
            )
            return application_id, applications, "embarked" if embedded else "battlefield"
        return None
    if event.event_type != "deadly_demise_mortal_wounds_applied":
        return None
    matches = tuple(
        authority
        for start in event_records
        if start.event_type == MORTAL_WOUND_APPLICATION_STARTED_EVENT
        for authority in (mortal_wound_application_authority_from_event(start),)
        if event in completion_events_for_authority(authority=authority, event_records=(event,))
    )
    if len(matches) != 1:
        raise GameLifecycleError("Deadly Demise physical history lacks one application authority.")
    payload = event.payload
    if not isinstance(payload, dict) or not isinstance(
        payload.get("mortal_wound_application"), dict
    ):
        raise GameLifecycleError("Deadly Demise physical history application is invalid.")
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, payload["mortal_wound_application"])
    )
    destroyed_ids = {
        damage.model_instance_id for damage in application.applications if damage.destroyed
    }
    return (
        matches[0].application_id,
        tuple(
            damage
            for damage in application.applications
            if damage.model_instance_id not in destroyed_ids
        ),
        "battlefield",
    )
