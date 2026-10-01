"""Rejected ordinary setup requests retain their engine source authority."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.model_ownership_history import (
    historical_model_ids_by_physical_unit,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_reserve_arrival_integrity import (
    validate_primary_reserve_arrival_request_chain,
    validate_primary_reserve_arrival_request_source,
    validate_primary_reserve_invalid_placement_event,
    validate_primary_reserve_placement_request_authority,
)
from warhammer40k_core.engine.reserves import (
    ReservePlacementViolation,
    ReservePlacementViolationPayload,
)
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportOperationViolationPayload,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_model_authority_history import ModelAuthorityTimeline
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_reserve_entry_provider import (
        PrimaryReserveEntryLifecycleOccurrence,
    )


def validate_failed_placement_authority(
    *,
    state: GameState,
    proposal: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    rejected: DecisionRecord,
    action: DecisionRecord,
    invalid: EventRecord,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    event_index: dict[str, int],
    rollback_order: int,
    model_history: ModelAuthorityTimeline | None,
) -> None:
    """Share reserve authority and close the distinct Disembark producer schema."""
    if rejected.request != proposal.to_decision_request():
        raise GameLifecycleError("Failed setup proposal decision envelope authority drift.")
    if model_history is None:
        raise GameLifecycleError("Failed setup requires authenticated model history.")
    historical_inventory = _validate_failed_setup_physical_authority(
        state=state,
        proposal=proposal,
        submitted=submitted,
        events=events,
        records=records,
        event_index=event_index,
        model_history=model_history,
    )
    if proposal.proposal_kind is ProposalKind.DISEMBARK:
        _validate_disembark_authority(
            state=state,
            proposal=proposal,
            submitted=submitted,
            rejected=rejected,
            action=action,
            invalid=invalid,
            events=events,
            records=records,
            event_index=event_index,
            rollback_order=rollback_order,
            model_history=model_history,
        )
        return
    validate_primary_reserve_placement_request_authority(
        state=state,
        proposal_request=proposal,
        submitted=submitted,
        expected_owner_id=proposal.actor_id,
        historical_living_model_ids_by_component=historical_inventory,
    )
    validate_primary_reserve_arrival_request_chain(
        proposal_request=proposal,
        placement_decision=rejected,
        expected_owner_id=proposal.actor_id,
        ingress_use=None,
        event_records=events,
        decision_records=records,
        event_index_by_id=event_index,
    )
    recorded = _exact_event(events, "decision_recorded", validate_json_value(rejected.to_payload()))
    validate_primary_reserve_invalid_placement_event(
        previous_proposal=proposal,
        rejected_submission=submitted,
        rejected_result_id=rejected.result.result_id,
        expected_owner_id=proposal.actor_id,
        ingress_use=None,
        event_records=events,
        event_index_by_id=event_index,
        predecessor_recorded_order=event_index[recorded.event_id],
        placement_request_order=rollback_order,
    )
    _validate_reserve_diagnostic(proposal=proposal, submitted=submitted, invalid=invalid)


def _validate_reserve_diagnostic(
    *,
    proposal: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    invalid: EventRecord,
) -> None:
    payload = invalid.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Failed reserve diagnostic requires an object.")
    models = {
        model.model_instance_id
        for model in submitted.resolved_rules_unit_placement().model_placements
    }
    violations = payload["violations"]
    if not isinstance(violations, list):
        raise GameLifecycleError("Failed reserve diagnostic violations are malformed.")
    for violation in violations:
        if not isinstance(violation, dict):
            raise GameLifecycleError("Failed reserve diagnostic violation is malformed.")
        try:
            typed = ReservePlacementViolation.from_payload(
                cast(ReservePlacementViolationPayload, violation)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError("Failed reserve diagnostic violation is malformed.") from exc
        if violation != typed.to_payload() or (
            typed.model_instance_id is not None and typed.model_instance_id not in models
        ):
            raise GameLifecycleError("Failed reserve diagnostic violation authority drift.")
    raw_coherency = payload["coherency_result"]
    if not isinstance(raw_coherency, dict):
        raise GameLifecycleError("Failed reserve coherency diagnostic is malformed.")
    try:
        coherency = UnitCoherencyResult.from_payload(
            cast(UnitCoherencyResultPayload, raw_coherency)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Failed reserve coherency diagnostic is malformed.") from exc
    if (
        raw_coherency != coherency.to_payload()
        or coherency.unit_instance_id != proposal.unit_instance_id
        or set(coherency.model_instance_ids) != models
    ):
        raise GameLifecycleError("Failed reserve coherency diagnostic authority drift.")


def _validate_failed_setup_physical_authority(
    *,
    state: GameState,
    proposal: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    event_index: dict[str, int],
    model_history: ModelAuthorityTimeline,
) -> dict[str, frozenset[str]]:
    views = current_rules_unit_views_for_identity(
        state=state, unit_instance_id=proposal.unit_instance_id
    )
    lineage = {component_id for view in views for component_id in view.component_unit_instance_ids}
    physical = {
        unit.unit_instance_id: (army, unit)
        for army in state.army_definitions
        for unit in army.units
    }
    placement = submitted.resolved_rules_unit_placement()
    context = proposal.context or {}
    model_ids = {model.model_instance_id for model in placement.model_placements}
    requested = _exact_event(
        events,
        "decision_requested",
        validate_json_value(proposal.to_decision_request().to_payload()),
    )
    historical_ids = historical_model_ids_by_physical_unit(state)
    expected_by_component = {
        component_id: {
            model_id
            for model_id in historical_ids[component_id]
            if model_history.has_living_model_before_event(
                model_instance_id=model_id,
                event_index=event_index[requested.event_id],
            )
        }
        for component_id in lineage
    }
    expected_components = {
        component_id for component_id, ids in expected_by_component.items() if ids
    }
    expected_models = {model_id for ids in expected_by_component.values() for model_id in ids}
    if (
        placement.rules_unit_instance_id != proposal.unit_instance_id
        or placement.player_id != proposal.actor_id
        or {view.owner_player_id for view in views} != {proposal.actor_id}
        or context.get("component_unit_instance_ids") != list(placement.component_unit_instance_ids)
        or context.get("model_instance_ids") != sorted(model_ids)
        or not model_ids
        or set(placement.component_unit_instance_ids) != expected_components
        or model_ids != expected_models
    ):
        raise GameLifecycleError("Failed setup physical inventory authority drift.")
    for component in placement.component_unit_placements:
        if component.unit_instance_id not in lineage:
            raise GameLifecycleError("Failed setup component lineage authority drift.")
        army = physical[component.unit_instance_id][0]
        if (
            component.army_id != army.army_id
            or component.player_id != army.player_id
            or army.player_id != proposal.actor_id
            or {model.model_instance_id for model in component.model_placements}
            != expected_by_component[component.unit_instance_id]
        ):
            raise GameLifecycleError("Failed setup physical model/owner authority drift.")
    return {
        component_id: frozenset(ids) for component_id, ids in expected_by_component.items() if ids
    }


def validate_failed_reserve_setup_sources(
    *,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    event_index: dict[str, int],
    reserve_entry_occurrences: tuple[PrimaryReserveEntryLifecycleOccurrence, ...],
) -> None:
    """Use the lifecycle owner's authenticated historical reserve entry inventory."""
    by_result = {record.result.result_id: record for record in records}
    for event in events:
        if event.event_type != "movement_setup_failed":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Failed setup source receipt requires an object.")
        result_id = event.payload.get("result_id")
        if not isinstance(result_id, str) or result_id not in by_result:
            raise GameLifecycleError("Failed setup source receipt lacks its rejected decision.")
        rejected = by_result[result_id]
        proposal = MovementProposalRequest.from_decision_request_payload(rejected.request.payload)
        if proposal.proposal_kind is ProposalKind.DISEMBARK:
            continue
        requested = _exact_event(
            events, "decision_requested", validate_json_value(rejected.request.to_payload())
        )
        validate_primary_reserve_arrival_request_source(
            proposal_request=proposal,
            expected_owner_id=proposal.actor_id,
            placement_request_order=event_index[requested.event_id],
            reserve_entry_occurrences=reserve_entry_occurrences,
            event_records=events,
            event_index_by_id=event_index,
        )


def _validate_disembark_authority(
    *,
    state: GameState,
    proposal: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    rejected: DecisionRecord,
    action: DecisionRecord,
    invalid: EventRecord,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    event_index: dict[str, int],
    rollback_order: int,
    model_history: ModelAuthorityTimeline,
) -> None:
    context = proposal.context or {}
    expected_keys = {
        "transport_unit_instance_id",
        "component_unit_instance_ids",
        "model_instance_ids",
        "disembark_mode",
        "allowed_disembark_modes",
        "transport_movement_status",
        "restriction_overrides",
    }
    if context.get("disembark_mode") == DisembarkModeKind.SHOCK_DISEMBARK.value:
        expected_keys.add("start_engaged_enemy_unit_instance_ids")
    action_payload = action.result.payload
    allowed_modes = (
        [DisembarkModeKind.TACTICAL_DISEMBARK.value, DisembarkModeKind.COMBAT_DISEMBARK.value]
        if context.get("disembark_mode") == DisembarkModeKind.TACTICAL_DISEMBARK.value
        else [context.get("disembark_mode")]
    )
    if (
        set(context) != expected_keys
        or proposal.placement_kinds != (BattlefieldPlacementKind.DISEMBARK,)
        or not isinstance(action_payload, dict)
        or context.get("allowed_disembark_modes") != allowed_modes
        or any(
            context.get(key) != action_payload.get(key)
            for key in ("transport_unit_instance_id", "disembark_mode", "transport_movement_status")
        )
        or context.get("restriction_overrides") != action_payload.get("restriction_overrides", [])
    ):
        raise GameLifecycleError("Failed Disembark request context authority drift.")
    recorded = _exact_event(events, "decision_recorded", validate_json_value(rejected.to_payload()))
    selected = _exact_event(
        events,
        "disembark_unit_selected",
        {
            "game_id": proposal.game_id,
            "battle_round": proposal.battle_round,
            "active_player_id": proposal.actor_id,
            "phase": proposal.phase,
            "unit_instance_id": proposal.unit_instance_id,
            "transport_unit_instance_id": context["transport_unit_instance_id"],
            "disembark_mode": context["disembark_mode"],
            "transport_movement_status": context["transport_movement_status"],
            "request_id": action.request.request_id,
            "result_id": action.result.result_id,
            "selected_move_type": "disembark",
            "phase_body_status": "disembark_unit_selected",
        },
    )
    _validate_disembark_request_chain(
        state=state,
        proposal=proposal,
        rejected=rejected,
        events=events,
        records=records,
        event_index=event_index,
        selected_order=event_index[selected.event_id],
        model_history=model_history,
    )
    status = (
        "combat_disembark_placement_invalid"
        if submitted.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK
        else "disembark_placement_invalid"
    )
    _validate_disembark_diagnostic(
        proposal=proposal,
        rejected=rejected,
        invalid=invalid,
        status=status,
    )
    if not event_index[recorded.event_id] < event_index[invalid.event_id] < rollback_order:
        raise GameLifecycleError("Failed Disembark diagnostic ordering drift.")


def _validate_disembark_request_chain(
    *,
    state: GameState,
    proposal: MovementProposalRequest,
    rejected: DecisionRecord,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    event_index: dict[str, int],
    selected_order: int,
    model_history: ModelAuthorityTimeline,
) -> None:
    """Walk retained Tactical-available retries without recursive history parsing."""
    upper_order = len(events)
    while True:
        context = proposal.context or {}
        requested = _exact_event(
            events, "decision_requested", validate_json_value(rejected.request.to_payload())
        )
        recorded = _exact_event(
            events, "decision_recorded", validate_json_value(rejected.to_payload())
        )
        sources = tuple(
            event
            for event in events
            if event.event_type == "placement_proposal_requested"
            and isinstance(event.payload, dict)
            and event.payload.get("request_id") == proposal.request_id
        )
        if len(sources) != 1:
            raise GameLifecycleError("Failed Disembark lacks one placement source event.")
        source = sources[0]
        payload = cast(dict[str, JsonValue], source.payload)
        expected: dict[str, JsonValue] = {
            "game_id": proposal.game_id,
            "battle_round": proposal.battle_round,
            "active_player_id": proposal.actor_id,
            "phase": proposal.phase,
            "unit_instance_id": proposal.unit_instance_id,
            "transport_unit_instance_id": context["transport_unit_instance_id"],
            "proposal_kind": proposal.proposal_kind.value,
            "placement_kinds": [kind.value for kind in proposal.placement_kinds],
            "request_id": proposal.request_id,
            "source_decision_request_id": proposal.source_decision_request_id,
            "source_decision_result_id": proposal.source_decision_result_id,
            "phase_body_status": "placement_proposal_required",
        }
        is_retry = "previous_proposal_request_id" in payload or "rejected_result_id" in payload
        predecessor_link: tuple[MovementProposalRequest, DecisionRecord] | None = None
        if is_retry:
            predecessors = tuple(
                record
                for record in records
                if record.request.request_id == payload.get("previous_proposal_request_id")
                and record.result.result_id == payload.get("rejected_result_id")
            )
            if len(predecessors) != 1:
                raise GameLifecycleError("Failed Disembark retry lacks one rejected predecessor.")
            predecessor = predecessors[0]
            previous = MovementProposalRequest.from_decision_request_payload(
                predecessor.request.payload
            )
            prior_submission = PlacementProposalPayload.from_payload(
                cast(PlacementProposalPayloadPayload, predecessor.result.payload)
            )
            if (
                replace(
                    previous,
                    request_id=proposal.request_id,
                    spatial_context_hash=proposal.spatial_context_hash,
                )
                != proposal
                or prior_submission.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK
                or not prior_submission.validation_result_for_request(previous).is_valid
                or predecessor.request.actor_id != proposal.actor_id
                or predecessor.request != previous.to_decision_request()
            ):
                raise GameLifecycleError("Failed Disembark retry predecessor authority drift.")
            _validate_failed_setup_physical_authority(
                state=state,
                proposal=previous,
                submitted=prior_submission,
                events=events,
                records=records,
                event_index=event_index,
                model_history=model_history,
            )
            expected.update(
                {
                    "spatial_context_hash": proposal.spatial_context_hash,
                    "previous_proposal_request_id": previous.request_id,
                    "rejected_result_id": predecessor.result.result_id,
                    "transport_movement_status": context["transport_movement_status"],
                }
            )
            predecessor_link = previous, predecessor
        else:
            expected.update(
                {
                    "disembark_mode": context["disembark_mode"],
                    "allowed_disembark_modes": context["allowed_disembark_modes"],
                    "restriction_overrides": context["restriction_overrides"],
                    "start_engaged_enemy_unit_instance_ids": context.get(
                        "start_engaged_enemy_unit_instance_ids", []
                    ),
                }
            )
        if payload != expected:
            raise GameLifecycleError("Failed Disembark placement source authority drift.")
        request_order = event_index[requested.event_id]
        if (
            not selected_order
            < request_order
            < event_index[source.event_id]
            < event_index[recorded.event_id]
            < upper_order
        ):
            raise GameLifecycleError("Failed Disembark placement source ordering drift.")
        if predecessor_link is None:
            return
        previous, predecessor = predecessor_link
        diagnostics = tuple(
            event
            for event in events
            if event.event_type == "combat_disembark_tactical_available"
            and isinstance(event.payload, dict)
            and event.payload.get("request_id") == previous.request_id
            and event.payload.get("result_id") == predecessor.result.result_id
        )
        if len(diagnostics) != 1:
            raise GameLifecycleError(
                "Failed Disembark retry lacks one Tactical-available diagnostic."
            )
        diagnostic = diagnostics[0]
        _validate_disembark_diagnostic(
            proposal=previous,
            rejected=predecessor,
            invalid=diagnostic,
            status="combat_disembark_tactical_available",
        )
        prior_recorded = _exact_event(
            events, "decision_recorded", validate_json_value(predecessor.to_payload())
        )
        if (
            not event_index[prior_recorded.event_id]
            < event_index[diagnostic.event_id]
            < request_order
        ):
            raise GameLifecycleError("Failed Disembark retry diagnostic ordering drift.")
        upper_order = event_index[diagnostic.event_id]
        proposal, rejected = previous, predecessor


def _validate_disembark_diagnostic(
    *,
    proposal: MovementProposalRequest,
    rejected: DecisionRecord,
    invalid: EventRecord,
    status: str,
) -> None:
    context = proposal.context or {}
    payload = invalid.payload
    expected: dict[str, JsonValue] = {
        "game_id": proposal.game_id,
        "battle_round": proposal.battle_round,
        "active_player_id": proposal.actor_id,
        "phase": proposal.phase,
        "unit_instance_id": proposal.unit_instance_id,
        "transport_unit_instance_id": context["transport_unit_instance_id"],
        "request_id": rejected.request.request_id,
        "result_id": rejected.result.result_id,
        "phase_body_status": status,
    }
    if not isinstance(payload, dict):
        raise GameLifecycleError("Failed Disembark diagnostic requires an object.")
    violations = payload.get("violations")
    if not isinstance(violations, list) or not violations:
        raise GameLifecycleError("Failed Disembark diagnostic lacks violations.")
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, rejected.result.payload)
    )
    placement = submitted.resolved_rules_unit_placement()
    models = {model.model_instance_id for model in placement.model_placements}
    units = {proposal.unit_instance_id, *placement.component_unit_instance_ids}
    ordinary_codes = {
        TransportOperationViolationCode.TRANSPORT_KEYWORD_REQUIRED,
        TransportOperationViolationCode.TRANSPORT_DATASHEET_MISMATCH,
        TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
        TransportOperationViolationCode.UNIT_NOT_EMBARKED,
        TransportOperationViolationCode.UNIT_DID_NOT_START_PHASE_EMBARKED,
        TransportOperationViolationCode.DISEMBARK_DISTANCE,
        TransportOperationViolationCode.RAPID_DISEMBARK_INGRESS_RESTRICTION,
        TransportOperationViolationCode.TRANSPORT_ADVANCED_OR_FELL_BACK,
        TransportOperationViolationCode.ASSAULT_DISEMBARK_PERMISSION_REQUIRED,
        TransportOperationViolationCode.SHOCK_DISEMBARK_PERMISSION_REQUIRED,
        TransportOperationViolationCode.SHOCK_DISEMBARK_ENGAGEMENT_SNAPSHOT_DRIFT,
        TransportOperationViolationCode.TRANSPORT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.MODEL_OVERLAP,
        TransportOperationViolationCode.BATTLEFIELD_EDGE_CROSSED,
        TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
        TransportOperationViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP,
        TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
        TransportOperationViolationCode.UNIT_COHERENCY_BROKEN,
    }
    transport_codes = {
        TransportOperationViolationCode.TRANSPORT_KEYWORD_REQUIRED,
        TransportOperationViolationCode.TRANSPORT_DATASHEET_MISMATCH,
        TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
    }
    for violation in violations:
        if not isinstance(violation, dict):
            raise GameLifecycleError("Failed Disembark diagnostic violation is malformed.")
        try:
            typed = TransportOperationViolation.from_payload(
                cast(TransportOperationViolationPayload, violation)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError("Failed Disembark diagnostic violation is malformed.") from exc
        if violation != typed.to_payload():
            raise GameLifecycleError("Failed Disembark diagnostic violation schema drift.")
        if status != "combat_disembark_tactical_available" and (
            typed.violation_code not in ordinary_codes
            or (typed.model_instance_id is not None and typed.model_instance_id not in models)
            or (
                typed.unit_instance_id is not None
                and typed.unit_instance_id
                not in (
                    (context["transport_unit_instance_id"],)
                    if typed.violation_code in transport_codes
                    else tuple(units)
                )
            )
        ):
            raise GameLifecycleError("Failed Disembark diagnostic producer authority drift.")
        if status == "combat_disembark_tactical_available" and (
            len(violations) != 1
            or typed.violation_code
            is not TransportOperationViolationCode.COMBAT_DISEMBARK_TACTICAL_AVAILABLE
            or typed.unit_instance_id != proposal.unit_instance_id
            or typed.blocker_id != context["transport_unit_instance_id"]
            or typed.model_instance_id is not None
            or typed.source_rule_id is not None
        ):
            raise GameLifecycleError(
                "Failed Disembark Tactical-available diagnostic authority drift."
            )
    expected["violations"] = violations
    if invalid.event_type != status or payload != expected:
        raise GameLifecycleError("Failed Disembark diagnostic authority drift.")


def _exact_event(
    events: tuple[EventRecord, ...], event_type: str, payload: JsonValue
) -> EventRecord:
    matches = tuple(
        event for event in events if event.event_type == event_type and event.payload == payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(f"Failed setup requires one exact {event_type} source event.")
    return matches[0]
