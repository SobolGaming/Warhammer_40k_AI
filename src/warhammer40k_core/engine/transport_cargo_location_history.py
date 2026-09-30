"""Close an independently authenticated cargo boundary through recorded mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    PlacementError,
)
from warhammer40k_core.engine.destroyed_transport_rules_unit_disembark import (
    DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_EVENT_FIELD,
    DestroyedTransportRulesUnitDisembarkEvidence,
    emergency_disembark_omitted_model_evidence_from_event_payload,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_model_authority_history import build_model_authority_timeline
from warhammer40k_core.engine.healing import HealingStep, HealingStepKind, HealingStepPayload
from warhammer40k_core.engine.model_ownership_history import historical_model_ids_by_physical_unit
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DestroyedTransportHazardRolls,
    DestroyedTransportHazardRollsPayload,
    DisembarkModeKind,
    TransportCargoState,
    TransportCargoStatePayload,
    TransportMovementStatus,
    disembarked_unit_state_from_event_payload,
)
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


def validate_transport_cargo_location_suffix(
    *,
    boundary_state: GameState,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    initial_event_count: int,
    affected_unit_instance_ids: frozenset[str],
) -> None:
    """Project physical carrier identity, preserving death and receiving-unit revival.

    The caller supplies a state reproduced by the shared engine and its exact event
    prefix. Existing restore owners authenticate reserve status, physical transitions,
    Embark departures and healing provenance. Cargo snapshots alone never authorize
    a transfer: each mutation must continue the projected membership and living
    physical inventory. Phase resets and loaded-carrier arrival preserve identity.
    """
    tracked = set[str]()
    for unit_id in affected_unit_instance_ids:
        tracked.update(_components(boundary_state, unit_id))
    for cargo in boundary_state.transport_cargo_states:
        if cargo.transport_unit_instance_id in tracked:
            for unit_id in cargo.embarked_unit_instance_ids:
                tracked.update(_components(boundary_state, unit_id))
    carriers: dict[str, str | None] = {
        unit.unit_instance_id: None for army in state.army_definitions for unit in army.units
    }
    for cargo in boundary_state.transport_cargo_states:
        for unit_id in cargo.embarked_unit_instance_ids:
            carriers[unit_id] = cargo.transport_unit_instance_id
    inventory = historical_model_ids_by_physical_unit(state)
    timeline = build_model_authority_timeline(
        state=state, event_records=event_records, decision_records=decision_records
    )
    terminal_living_ids = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if model.is_alive
    }

    def living_ids(component_ids: set[str], event_index: int) -> set[str]:
        return {
            model_id
            for unit_id in component_ids
            for model_id in inventory[unit_id]
            if (
                model_id in terminal_living_ids
                if event_index == len(event_records)
                else timeline.has_living_model_before_event(
                    model_instance_id=model_id, event_index=event_index
                )
            )
        }

    used_results: set[str] = set()
    for index in range(initial_event_count, len(event_records)):
        event = event_records[index]
        if event.event_type in {"unit_embarked", "unit_disembarked"}:
            payload = _object(event.payload)
            unit_id = _identifier(payload, "unit_instance_id")
            components = _components(state, unit_id)
            # Other units still contribute to the carrier's exact membership snapshot.
            record = _mutation_decision(event, index, event_records, decision_records)
            if record.result.result_id in used_results:
                raise GameLifecycleError("Cargo location mutation result is duplicated.")
            used_results.add(record.result.result_id)
            cargo = _cargo(payload.get("updated_cargo_state"))
            carrier_id = _identifier(payload, "transport_unit_instance_id")
            if cargo.transport_unit_instance_id != carrier_id:
                raise GameLifecycleError("Cargo location mutation carrier identity drift.")
            transition = _transition(payload.get("transition_batch"))
            expected_models = living_ids(components, index)
            if event.event_type == "unit_disembarked":
                _validate_disembark(record, payload, transition, expected_models)
                departed = {i for i in components if living_ids({i}, index)}
                if any(carriers.get(i) != carrier_id for i in departed):
                    raise GameLifecycleError("Cargo location Disembark prior carrier drift.")
                for component_id in departed:
                    carriers[component_id] = None
            else:
                removed_ids = {row.model_instance_id for row in transition.removals}
                if (
                    record.request.decision_type != "select_embark_transport"
                    or record.result.selected_option_id != carrier_id
                    or transition.placements
                    or transition.displacements
                    or removed_ids != expected_models
                    or any(
                        row.removal_kind is not BattlefieldRemovalKind.EMBARK
                        or row.destination_id != carrier_id
                        for row in transition.removals
                    )
                ):
                    raise GameLifecycleError("Cargo location Embark mutation authority drift.")
                entered = {i for i in components if living_ids({i}, index)}
                if any(carriers.get(i) is not None for i in entered):
                    raise GameLifecycleError("Cargo location Embark prior location drift.")
                for component_id in entered:
                    carriers[component_id] = carrier_id
            if set(cargo.embarked_unit_instance_ids) != {
                i for i, carrier in carriers.items() if carrier == carrier_id
            }:
                raise GameLifecycleError("Cargo location mutation membership drift.")
        elif event.event_type == "healing_step_resolved":
            payload = _object(event.payload)
            step = HealingStep.from_payload(cast(HealingStepPayload, _object(payload.get("step"))))
            if step.step_kind is HealingStepKind.REVIVE_MODEL_EMBARKED:
                record = _mutation_decision(
                    event,
                    index,
                    event_records,
                    decision_records,
                    request_id=step.request_id,
                    result_id=step.result_id,
                )
                location = _object(_object(record.request.payload).get("revival_location"))
                cargo = _cargo(location.get("cargo_state"))
                carrier_id = cargo.transport_unit_instance_id
                target = _components(state, _identifier(payload, "target_unit_instance_id"))
                receiving = {i for i in target if living_ids({i}, index)}
                if not receiving or any(carriers.get(i) != carrier_id for i in receiving):
                    raise GameLifecycleError("Cargo location revival receiving carrier drift.")
                if set(cargo.embarked_unit_instance_ids) != {
                    i for i, carrier in carriers.items() if carrier == carrier_id
                }:
                    raise GameLifecycleError("Cargo location revival prior membership drift.")
                returned = {
                    unit_id for unit_id, ids in inventory.items() if step.model_instance_id in ids
                }
                if len(returned) != 1 or not returned <= target:
                    raise GameLifecycleError("Cargo location revival physical component drift.")
                carriers[next(iter(returned))] = carrier_id
        # The casualty owner prunes only the final living model of a physical
        # component. Historical liveness retains intervening death/revival boundaries.
        for component_id, current_carrier_id in tuple(carriers.items()):
            if current_carrier_id is not None and not living_ids({component_id}, index + 1):
                carriers[component_id] = None

    # Reserve deadline destruction removes a loaded route's cargo without changing
    # its model wounds. The existing reserve owners authenticate this terminal status.
    destroyed_routes = {
        reserve.unit_instance_id
        for reserve in state.reserve_states
        if reserve.status is ReserveStatus.DESTROYED
    }
    for component_id in tracked:
        expected_carrier = carriers.get(component_id)
        if expected_carrier in destroyed_routes:
            expected_carrier = None
        terminal_cargo = state.transport_cargo_state_for_embarked_unit(component_id)
        actual_carrier = (
            None if terminal_cargo is None else terminal_cargo.transport_unit_instance_id
        )
        if actual_carrier != expected_carrier:
            raise GameLifecycleError("Failed setup terminal cargo location authority drift.")


def _components(state: GameState, unit_id: str) -> set[str]:
    component_ids = {
        component_id
        for view in current_rules_unit_views_for_identity(state=state, unit_instance_id=unit_id)
        for component_id in view.component_unit_instance_ids
    }
    for attached in state.starting_attached_unit_records:
        if attached.attached_unit_instance_id == unit_id:
            component_ids.update(attached.component_unit_instance_ids)
    return component_ids


def _mutation_decision(
    event: EventRecord,
    index: int,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    *,
    request_id: str | None = None,
    result_id: str | None = None,
) -> DecisionRecord:
    payload = _object(event.payload)
    request_id = _identifier(payload, "request_id") if request_id is None else request_id
    result_id = _identifier(payload, "result_id") if result_id is None else result_id
    matches = tuple(
        record
        for record in records
        if record.request.request_id == request_id and record.result.result_id == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Cargo location mutation decision authority drift.")
    record = matches[0]
    requested = tuple(
        i
        for i, value in enumerate(events[:index])
        if value.event_type == "decision_requested" and value.payload == record.request.to_payload()
    )
    recorded = tuple(
        i
        for i, value in enumerate(events[:index])
        if value.event_type == "decision_recorded" and value.payload == record.to_payload()
    )
    if len(requested) != 1 or len(recorded) != 1 or requested[0] >= recorded[0]:
        raise GameLifecycleError("Cargo location mutation decision event authority drift.")
    return record


def _validate_disembark(
    record: DecisionRecord,
    payload: dict[str, JsonValue],
    transition: BattlefieldTransitionBatch,
    expected_models: set[str],
) -> None:
    if record.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Cargo location Disembark decision authority drift.")
    proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, _object(record.result.payload))
    )
    disembarked = disembarked_unit_state_from_event_payload(payload)
    omitted: set[str] = set()
    if proposal.context is not None and proposal.context.get("destruction_timing") == (
        "destroyed_transport"
    ):
        omitted = _destroyed_disembark_omissions(
            proposal, submitted, payload, transition, expected_models
        )
    if (
        not submitted.validation_result_for_request(proposal).is_valid
        or proposal.proposal_kind is not ProposalKind.DISEMBARK
        or proposal.unit_instance_id != payload.get("unit_instance_id")
        or proposal.actor_id != disembarked.player_id
        or disembarked.turn_player_id != payload.get("active_player_id")
        or proposal.game_id != payload.get("game_id")
        or proposal.battle_round != payload.get("battle_round")
        or proposal.phase != payload.get("phase")
        or submitted.transport_unit_instance_id != payload.get("transport_unit_instance_id")
        or submitted.disembark_mode is None
        or submitted.disembark_mode.value != payload.get("disembark_mode")
        or transition.removals
        or transition.displacements
        or {row.model_instance_id for row in transition.placements} != expected_models - omitted
    ):
        raise GameLifecycleError("Cargo location Disembark mutation authority drift.")
    placements = {
        row.model_instance_id: row
        for row in submitted.resolved_rules_unit_placement().model_placements
    }
    for row in transition.placements:
        placement = placements.get(row.model_instance_id)
        if (
            placement is None
            or placement.pose != row.pose
            or row.placement_kind != submitted.placement_kind
        ):
            raise GameLifecycleError("Cargo location Disembark accepted placement drift.")


def _destroyed_disembark_omissions(
    proposal: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    payload: dict[str, JsonValue],
    transition: BattlefieldTransitionBatch,
    expected_models: set[str],
) -> set[str]:
    context = _object(proposal.context)
    evidence = emergency_disembark_omitted_model_evidence_from_event_payload(payload)
    if (
        evidence is None
        or evidence.player_id != proposal.actor_id
        or evidence.rules_unit_instance_id != proposal.unit_instance_id
        or context.get("surviving_model_instance_ids") != sorted(expected_models)
        or context.get("transport_unit_instance_id") != payload.get("transport_unit_instance_id")
        or context.get("disembark_mode") != DisembarkModeKind.EMERGENCY_DISEMBARK.value
        or context.get("transport_movement_status") != TransportMovementStatus.NOT_MOVED.value
        or payload.get("disembark_mode") != DisembarkModeKind.EMERGENCY_DISEMBARK.value
        or set(evidence.placed_model_instance_ids) | set(evidence.destroyed_model_instance_ids)
        != expected_models
    ):
        raise GameLifecycleError("Cargo location destroyed Transport inventory authority drift.")
    try:
        hazard = DestroyedTransportHazardRolls.from_payload(
            cast(DestroyedTransportHazardRollsPayload, _object(context.get("hazard_rolls")))
        )
        if (
            hazard.player_id != proposal.actor_id
            or hazard.battle_round != proposal.battle_round
            or hazard.unit_instance_id != proposal.unit_instance_id
            or hazard.transport_unit_instance_id != payload.get("transport_unit_instance_id")
            or hazard.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK
            or set(hazard.component_unit_instance_ids) != set(evidence.component_unit_instance_ids)
        ):
            raise GameLifecycleError("Cargo location destroyed Transport hazard context drift.")
        grouped = payload.get(DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_EVENT_FIELD)
        if grouped is not None:
            resolution = DestroyedTransportRulesUnitDisembarkEvidence.from_payload(grouped)
            if (
                resolution.hazard_rolls != hazard
                or resolution.attempted_placement != submitted.resolved_rules_unit_placement()
            ):
                raise GameLifecycleError(
                    "Cargo location destroyed Transport hazard authority drift."
                )
        else:
            physical = DestroyedTransportDisembark.from_payload(
                cast(
                    DestroyedTransportDisembarkPayload,
                    _object(payload.get("destroyed_transport_disembark")),
                )
            )
            if (
                not physical.placement.is_valid
                or physical.player_id != proposal.actor_id
                or physical.battle_round != proposal.battle_round
                or physical.unit_instance_id != proposal.unit_instance_id
                or physical.transport_unit_instance_id != payload.get("transport_unit_instance_id")
                or physical.model_rolls != hazard.model_rolls
                or physical.roll_threshold != hazard.roll_threshold
                or physical.mortal_wounds_per_failed_roll != hazard.mortal_wounds_per_failed_roll
                or physical.placement.selection.attempted_placement
                != submitted.require_unit_placement()
                or physical.placement.transition_batch != transition
                or physical.placement.updated_cargo_state
                != _cargo(payload.get("updated_cargo_state"))
                or physical.disembarked_unit_state
                != disembarked_unit_state_from_event_payload(payload)
            ):
                raise GameLifecycleError(
                    "Cargo location destroyed Transport mutation authority drift."
                )
    except (GeometryError, PlacementError, KeyError, TypeError, ValueError) as exc:
        raise GameLifecycleError(
            "Cargo location destroyed Transport evidence is malformed."
        ) from exc
    return set(evidence.destroyed_model_instance_ids)


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Cargo location authority requires an object.")
    return value


def _identifier(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GameLifecycleError("Cargo location authority requires an identifier.")
    return value


def _cargo(value: JsonValue) -> TransportCargoState:
    try:
        return TransportCargoState.from_payload(cast(TransportCargoStatePayload, _object(value)))
    except (KeyError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Cargo location state is malformed.") from exc


def _transition(value: JsonValue) -> BattlefieldTransitionBatch:
    try:
        return BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, _object(value))
        )
    except (GeometryError, PlacementError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Cargo location transition is malformed.") from exc
