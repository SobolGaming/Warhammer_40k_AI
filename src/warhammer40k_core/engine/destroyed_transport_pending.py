from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    PendingDestroyedTransportDisembark,
    PendingDestroyedTransportDisembarkPayload,
)
from warhammer40k_core.engine.attack_sequence_validation import (
    _validate_destroyed_transport_disembark_tuple,
    _validate_destruction_reaction_source_tuple,
    _validate_identifier,
    _validate_identifier_tuple,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    FeelNoPainResolution,
    model_by_id,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.lifecycle_state_queries import (
    active_attack_sequence_for_state,
)
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    DestroyedTransportDisembark,
    DestroyedTransportHazardRolls,
    TransportHazardMortalWounds,
    TransportHazardMortalWoundsPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_pending_destroyed_transport_disembark(
    pending: PendingDestroyedTransportDisembark,
) -> None:
    attack_context = validate_json_value(pending.attack_context)
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Pending destroyed Transport attack_context must be an object.")
    object.__setattr__(
        pending,
        "attack_context",
        cast(AttackResolutionContextPayload, attack_context),
    )
    if type(pending.damage_application) is not DamageApplication:
        raise GameLifecycleError(
            "Pending destroyed Transport damage_application must be DamageApplication."
        )
    if not pending.damage_application.destroyed:
        raise GameLifecycleError("Pending destroyed Transport requires destroyed damage.")
    if (
        pending.damage_application.target_unit_instance_id
        != pending.attack_context["target_unit_instance_id"]
    ):
        raise GameLifecycleError("Pending destroyed Transport damage target drift.")
    object.__setattr__(
        pending,
        "saving_throw_payload",
        validate_json_value(pending.saving_throw_payload),
    )
    if type(pending.feel_no_pain) is not FeelNoPainResolution:
        raise GameLifecycleError(
            "Pending destroyed Transport feel_no_pain must be FeelNoPainResolution."
        )
    object.__setattr__(
        pending,
        "destroyed_model_controller_player_id",
        _validate_identifier(
            "Pending destroyed Transport controller",
            pending.destroyed_model_controller_player_id,
        ),
    )
    object.__setattr__(
        pending,
        "transport_unit_instance_id",
        _validate_identifier(
            "Pending destroyed Transport transport_unit_instance_id",
            pending.transport_unit_instance_id,
        ),
    )
    object.__setattr__(
        pending,
        "pending_unit_instance_ids",
        _validate_identifier_tuple(
            "Pending destroyed Transport unit ids",
            pending.pending_unit_instance_ids,
        ),
    )
    object.__setattr__(
        pending,
        "resolved_disembarks",
        _validate_destroyed_transport_disembark_tuple(pending.resolved_disembarks),
    )
    if (
        pending.current_hazard_rolls is not None
        and type(pending.current_hazard_rolls) is not DestroyedTransportHazardRolls
    ):
        raise GameLifecycleError("Pending destroyed Transport current hazard rolls are invalid.")
    surviving_model_ids = pending.current_hazard_surviving_model_instance_ids
    if surviving_model_ids is not None:
        surviving_model_ids = _validate_identifier_tuple(
            "Pending destroyed Transport hazard survivor ids",
            surviving_model_ids,
        )
        object.__setattr__(
            pending,
            "current_hazard_surviving_model_instance_ids",
            surviving_model_ids,
        )
    object.__setattr__(
        pending,
        "hazard_destroyed_unit_instance_ids",
        _validate_identifier_tuple(
            "Pending destroyed Transport hazard-destroyed unit ids",
            pending.hazard_destroyed_unit_instance_ids,
        ),
    )
    object.__setattr__(
        pending,
        "pending_sources",
        _validate_destruction_reaction_source_tuple(
            "Pending destroyed Transport pending_sources",
            pending.pending_sources,
        ),
    )
    resolved_unit_ids = {disembark.unit_instance_id for disembark in pending.resolved_disembarks}
    hazard_destroyed_unit_ids = set(pending.hazard_destroyed_unit_instance_ids)
    if (
        resolved_unit_ids & set(pending.pending_unit_instance_ids)
        or hazard_destroyed_unit_ids & set(pending.pending_unit_instance_ids)
        or resolved_unit_ids & hazard_destroyed_unit_ids
    ):
        raise GameLifecycleError("Pending destroyed Transport unit appears in both states.")
    for disembark in pending.resolved_disembarks:
        if disembark.transport_unit_instance_id != pending.transport_unit_instance_id:
            raise GameLifecycleError("Pending destroyed Transport disembark transport drift.")
        if disembark.battle_round < 1:
            raise GameLifecycleError("Pending destroyed Transport disembark round drift.")
    hazard_rolls = pending.current_hazard_rolls
    if hazard_rolls is None:
        if surviving_model_ids is not None:
            raise GameLifecycleError(
                "Pending destroyed Transport survivors require current hazard rolls."
            )
        return
    if pending.next_unit_instance_id not in hazard_rolls.component_unit_instance_ids:
        raise GameLifecycleError("Pending destroyed Transport current hazard unit drift.")
    component_count = len(hazard_rolls.component_unit_instance_ids)
    if tuple(sorted(pending.pending_unit_instance_ids[:component_count])) != (
        hazard_rolls.component_unit_instance_ids
    ):
        raise GameLifecycleError("Pending destroyed Transport current hazard component drift.")
    if hazard_rolls.transport_unit_instance_id != pending.transport_unit_instance_id:
        raise GameLifecycleError("Pending destroyed Transport current hazard transport drift.")
    if surviving_model_ids is not None and not set(surviving_model_ids) <= set(
        hazard_rolls.model_instance_ids
    ):
        raise GameLifecycleError("Pending destroyed Transport hazard survivor inventory drift.")


def pending_with_resolved_disembark(
    pending: PendingDestroyedTransportDisembark,
    *,
    disembark: DestroyedTransportDisembark,
    retain_current_hazard: bool,
) -> PendingDestroyedTransportDisembark:
    if type(disembark) is not DestroyedTransportDisembark:
        raise GameLifecycleError("Resolved destroyed Transport disembark is invalid.")
    if pending.next_unit_instance_id != disembark.unit_instance_id:
        raise GameLifecycleError("Resolved destroyed Transport disembark unit drift.")
    hazard_rolls = pending.current_hazard_rolls
    survivor_ids = pending.current_hazard_surviving_model_instance_ids
    if hazard_rolls is None or survivor_ids is None:
        raise GameLifecycleError(
            "Resolved destroyed Transport disembark requires completed hazard casualties."
        )
    if type(retain_current_hazard) is not bool:
        raise GameLifecycleError("Resolved destroyed Transport hazard retention must be bool.")
    component_model_ids = {roll.model_instance_id for roll in disembark.model_rolls}
    if (
        not component_model_ids
        or not component_model_ids <= set(hazard_rolls.model_instance_ids)
        or disembark.unit_instance_id not in hazard_rolls.component_unit_instance_ids
    ):
        raise GameLifecycleError("Resolved destroyed Transport disembark hazard snapshot drift.")
    component_survivor_ids = set(survivor_ids) & component_model_ids
    if component_survivor_ids != {
        placement.model_instance_id
        for placement in disembark.placement.selection.attempted_placement.model_placements
    } | set(disembark.destroyed_model_instance_ids):
        raise GameLifecycleError("Resolved destroyed Transport disembark survivor snapshot drift.")
    return replace(
        pending,
        pending_unit_instance_ids=pending.pending_unit_instance_ids[1:],
        resolved_disembarks=(*pending.resolved_disembarks, disembark),
        current_hazard_rolls=hazard_rolls if retain_current_hazard else None,
        current_hazard_surviving_model_instance_ids=(
            survivor_ids if retain_current_hazard else None
        ),
    )


def pending_with_hazard_destroyed_current_unit(
    pending: PendingDestroyedTransportDisembark,
    *,
    retain_current_hazard: bool,
) -> PendingDestroyedTransportDisembark:
    unit_instance_id = pending.next_unit_instance_id
    hazard_rolls = pending.current_hazard_rolls
    survivor_ids = pending.current_hazard_surviving_model_instance_ids
    if unit_instance_id is None or hazard_rolls is None or survivor_ids is None:
        raise GameLifecycleError(
            "Pending destroyed Transport destroyed cargo requires zero survivors."
        )
    if type(retain_current_hazard) is not bool:
        raise GameLifecycleError("Pending destroyed Transport hazard retention must be bool.")
    if unit_instance_id not in hazard_rolls.component_unit_instance_ids:
        raise GameLifecycleError("Pending destroyed Transport destroyed cargo hazard unit drift.")
    if len(hazard_rolls.component_unit_instance_ids) == 1 and survivor_ids != ():
        raise GameLifecycleError(
            "Pending destroyed Transport destroyed cargo requires zero survivors."
        )
    return replace(
        pending,
        pending_unit_instance_ids=pending.pending_unit_instance_ids[1:],
        current_hazard_rolls=hazard_rolls if retain_current_hazard else None,
        current_hazard_surviving_model_instance_ids=(
            survivor_ids if retain_current_hazard else None
        ),
        hazard_destroyed_unit_instance_ids=(
            *pending.hazard_destroyed_unit_instance_ids,
            unit_instance_id,
        ),
    )


def pending_with_resolved_rules_unit_disembark(
    pending: PendingDestroyedTransportDisembark,
    *,
    disembark: object,
) -> PendingDestroyedTransportDisembark:
    from warhammer40k_core.engine.destroyed_transport_rules_unit_disembark import (
        DestroyedTransportRulesUnitDisembark,
    )

    if type(disembark) is not DestroyedTransportRulesUnitDisembark:
        raise GameLifecycleError("Resolved destroyed Transport rules-unit disembark is invalid.")
    hazard_rolls = pending.current_hazard_rolls
    survivor_ids = pending.current_hazard_surviving_model_instance_ids
    if hazard_rolls is None or survivor_ids is None:
        raise GameLifecycleError(
            "Resolved destroyed Transport rules-unit disembark requires hazard survivors."
        )
    if disembark.hazard_rolls != hazard_rolls or not disembark.is_valid:
        raise GameLifecycleError("Resolved destroyed Transport rules-unit hazard drift.")
    placed_ids = {
        placement.model_instance_id
        for placement in disembark.placement.selection.attempted_placement.model_placements
    }
    if placed_ids | set(disembark.destroyed_model_instance_ids) != set(survivor_ids):
        raise GameLifecycleError("Resolved destroyed Transport rules-unit survivor drift.")
    component_count = len(hazard_rolls.component_unit_instance_ids)
    if tuple(sorted(pending.pending_unit_instance_ids[:component_count])) != (
        hazard_rolls.component_unit_instance_ids
    ):
        raise GameLifecycleError("Resolved destroyed Transport rules-unit component drift.")
    return replace(
        pending,
        pending_unit_instance_ids=pending.pending_unit_instance_ids[component_count:],
        current_hazard_rolls=None,
        current_hazard_surviving_model_instance_ids=None,
    )


def pending_with_hazard_destroyed_rules_unit(
    pending: PendingDestroyedTransportDisembark,
) -> PendingDestroyedTransportDisembark:
    hazard_rolls = pending.current_hazard_rolls
    survivor_ids = pending.current_hazard_surviving_model_instance_ids
    if hazard_rolls is None or survivor_ids != ():
        raise GameLifecycleError(
            "Pending destroyed Transport rules-unit destruction requires zero survivors."
        )
    component_ids = hazard_rolls.component_unit_instance_ids
    component_count = len(component_ids)
    if tuple(sorted(pending.pending_unit_instance_ids[:component_count])) != component_ids:
        raise GameLifecycleError("Destroyed Transport rules-unit component drift.")
    return replace(
        pending,
        pending_unit_instance_ids=pending.pending_unit_instance_ids[component_count:],
        current_hazard_rolls=None,
        current_hazard_surviving_model_instance_ids=None,
        hazard_destroyed_unit_instance_ids=(
            *pending.hazard_destroyed_unit_instance_ids,
            *component_ids,
        ),
    )


def validate_pending_destroyed_transport_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Bind a pending placement to exact hazard, model, and request evidence."""

    attack_sequence = active_attack_sequence_for_state(state)
    pending = (
        None if attack_sequence is None else attack_sequence.pending_destroyed_transport_disembark
    )
    if (
        pending is None
        or pending.current_hazard_rolls is None
        or pending.current_hazard_surviving_model_instance_ids is None
    ):
        return
    hazard_rolls = pending.current_hazard_rolls
    matches = tuple(
        TransportHazardMortalWounds.from_payload(
            cast(TransportHazardMortalWoundsPayload, event.payload)
        )
        for event in event_records
        if event.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("disembark") == hazard_rolls.to_payload()
    )
    if len(matches) != 1 or matches[0].disembark != hazard_rolls:
        raise GameLifecycleError(
            "Pending destroyed Transport requires exact hazard completion evidence."
        )
    completion = matches[0]
    application = completion.mortal_wound_application
    if hazard_rolls.mortal_wound_count > 0 and application is None:
        raise GameLifecycleError(
            "Pending destroyed Transport requires exact hazard completion evidence."
        )
    destroyed_model_ids = {
        damage.model_instance_id
        for damage in (() if application is None else application.applications)
        if damage.destroyed
    }
    hazard_model_ids = set(hazard_rolls.model_instance_ids)
    if {
        state.unit_instance_id_for_model(model_instance_id)
        for model_instance_id in hazard_model_ids
    } != set(hazard_rolls.component_unit_instance_ids):
        raise GameLifecycleError("Pending destroyed Transport hazard component inventory drift.")
    if not destroyed_model_ids <= hazard_model_ids:
        raise GameLifecycleError("Pending destroyed Transport hazard completion casualty drift.")
    expected_survivor_ids = tuple(sorted(hazard_model_ids - destroyed_model_ids))
    if pending.current_hazard_surviving_model_instance_ids != expected_survivor_ids:
        raise GameLifecycleError(
            "Pending destroyed Transport requires exact hazard survivor inventory."
        )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Pending destroyed Transport hazard restore requires battlefield state."
        )
    removed_model_ids = set(battlefield.removed_model_ids)
    authoritative_survivor_ids = tuple(
        sorted(
            model_instance_id
            for model_instance_id in hazard_rolls.model_instance_ids
            if model_by_id(state=state, model_instance_id=model_instance_id).is_alive
        )
    )
    if authoritative_survivor_ids != expected_survivor_ids or any(
        model_instance_id in removed_model_ids
        or battlefield.model_placement_or_none(model_instance_id) is not None
        for model_instance_id in expected_survivor_ids
    ):
        raise GameLifecycleError(
            "Pending destroyed Transport requires exact hazard survivor inventory."
        )
    if any(model_instance_id not in removed_model_ids for model_instance_id in destroyed_model_ids):
        raise GameLifecycleError(
            "Pending destroyed Transport hazard casualty removal evidence drift."
        )
    _validate_pending_destroyed_transport_placement_request(
        state=state,
        pending=pending,
        pending_decision_requests=pending_decision_requests,
    )


def _validate_pending_destroyed_transport_placement_request(
    *,
    state: GameState,
    pending: PendingDestroyedTransportDisembark,
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    unit_instance_id = pending.next_unit_instance_id
    hazard_rolls = pending.current_hazard_rolls
    survivor_ids = pending.current_hazard_surviving_model_instance_ids
    if unit_instance_id is None or hazard_rolls is None or survivor_ids is None:
        raise GameLifecycleError(
            "Pending destroyed Transport placement restore context is incomplete."
        )
    request_unit_instance_id = hazard_rolls.unit_instance_id
    matching_requests: list[MovementProposalRequest] = []
    for request in pending_decision_requests:
        if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
            continue
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        if (proposal.context or {}).get("destruction_timing") == "destroyed_transport":
            matching_requests.append(proposal)
    if len(matching_requests) != 1:
        raise GameLifecycleError("Pending destroyed Transport requires one placement request.")
    proposal = matching_requests[0]
    context = proposal.context or {}
    if (
        proposal.unit_instance_id != request_unit_instance_id
        or proposal.proposal_kind is not ProposalKind.DISEMBARK
        or context.get("transport_unit_instance_id") != pending.transport_unit_instance_id
        or context.get("surviving_model_instance_ids") != list(survivor_ids)
        or context.get("hazard_rolls") != hazard_rolls.to_payload()
    ):
        raise GameLifecycleError(
            "Pending destroyed Transport placement request survivor inventory drift."
        )


def pending_destroyed_transport_disembark_to_payload(
    pending: PendingDestroyedTransportDisembark,
) -> PendingDestroyedTransportDisembarkPayload:
    return {
        "attack_context": pending.attack_context,
        "damage_application": pending.damage_application.to_payload(),
        "saving_throw": pending.saving_throw_payload,
        "feel_no_pain": pending.feel_no_pain.to_payload(),
        "destroyed_model_controller_player_id": (pending.destroyed_model_controller_player_id),
        "transport_unit_instance_id": pending.transport_unit_instance_id,
        "pending_unit_instance_ids": list(pending.pending_unit_instance_ids),
        "resolved_disembarks": [
            disembark.to_payload() for disembark in pending.resolved_disembarks
        ],
        "current_hazard_rolls": (
            None
            if pending.current_hazard_rolls is None
            else pending.current_hazard_rolls.to_payload()
        ),
        "current_hazard_surviving_model_instance_ids": (
            None
            if pending.current_hazard_surviving_model_instance_ids is None
            else list(pending.current_hazard_surviving_model_instance_ids)
        ),
        "hazard_destroyed_unit_instance_ids": list(pending.hazard_destroyed_unit_instance_ids),
        "pending_sources": [source.to_payload() for source in pending.pending_sources],
    }
