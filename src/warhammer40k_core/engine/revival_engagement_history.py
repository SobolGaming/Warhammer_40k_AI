"""Authenticate revival engagement against the pre-return physical history."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    healing_effect_from_request,
)
from warhammer40k_core.engine.healing_revival import (
    SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    healing_effect_from_revival_request,
)
from warhammer40k_core.engine.movement_proposals import (
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.revival_engagement import (
    validate_revival_engagement_geometry,
    validated_revival_engagement_payload,
)
from warhammer40k_core.engine.revival_phase_start import (
    revival_phase_start_evidence,
    revival_phase_start_for_request,
    validate_revival_anchor_coherency,
    validate_revival_selection_phase_start,
    validated_revival_phase_start_payload,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.volume import Model


def validate_revival_engagement_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    requests = (*pending_decision_requests, *(row.request for row in decision_records))
    for request in requests:
        if request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
            effect = healing_effect_from_request(request=request)
            if request in pending_decision_requests:
                validate_revival_selection_phase_start(
                    state=state,
                    event_records=event_records,
                    decision_records=decision_records,
                    request=request,
                    target_unit_instance_id=effect.target_unit_instance_id,
                    phase_start_model_ids=effect.phase_start_model_ids,
                )
        elif request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
            effect = healing_effect_from_revival_request(request=request)
            expected = revival_phase_start_for_request(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                request=request,
                target_unit_instance_id=effect.target_unit_instance_id,
            )
            if not isinstance(request.payload, dict):
                raise GameLifecycleError("Revival request must be an object.")
            if (
                request.payload.get("revival_phase_start") != expected
                or tuple(expected["model_ids"]) != effect.phase_start_model_ids
            ):
                raise GameLifecycleError("Revival phase-start request history drifted.")
            if request in pending_decision_requests and expected != revival_phase_start_evidence(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                target_unit_instance_id=effect.target_unit_instance_id,
            ):
                raise GameLifecycleError("Pending revival phase-start occurrence is stale.")
    completions: set[str] = set()
    for index, event in enumerate(event_records):
        if event.event_type != "healing_step_resolved":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("step"), dict):
            raise GameLifecycleError("Revival history requires a typed healing step.")
        step = cast(dict[str, JsonValue], payload["step"])
        if step.get("step_kind") != "revive_model":
            continue
        request_id, result_id = step.get("request_id"), step.get("result_id")
        if not isinstance(request_id, str) or not isinstance(result_id, str):
            raise GameLifecycleError("Revival history requires placement decision authority.")
        if result_id in completions:
            raise GameLifecycleError("Revival history repeats a placement decision.")
        record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=index,
            request_id=request_id,
            result_id=result_id,
        )
        _validate_completed_revival(
            state=state,
            events=event_records,
            records=decision_records,
            index=index,
            record=record,
            payload=payload,
        )
        completions.add(result_id)
    expected_completions = {
        record.result.result_id
        for record in decision_records
        if record.request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE
    }
    if completions != expected_completions:
        raise GameLifecycleError("Revival placement decisions and mutations are not one-to-one.")


def _validate_completed_revival(
    *,
    state: GameState,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    index: int,
    record: DecisionRecord,
    payload: dict[str, JsonValue],
) -> None:
    effect = healing_effect_from_revival_request(request=record.request)
    record.result.validate_for_request(record.request)
    raw = record.result.payload
    if not isinstance(raw, dict):
        raise GameLifecycleError("Revival historical proposal must be an object.")
    proposal = PlacementProposalPayload.from_payload(cast(PlacementProposalPayloadPayload, raw))
    placements = proposal.require_unit_placement().model_placements
    if (
        len(placements) != 1
        or proposal.proposal_kind is not ProposalKind.HEALING_REVIVAL
        or proposal.proposal_request_id != record.request.request_id
        or proposal.placement_kind is not BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD
    ):
        raise GameLifecycleError("Revival historical placement context drifted.")
    placement = placements[0]
    target = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    if (
        target.unit_instance_id != effect.target_unit_instance_id
        or target.owner_player_id != record.request.actor_id
        or target.component_unit_id_for_model(placement.model_instance_id)
        != placement.unit_instance_id
    ):
        raise GameLifecycleError("Revival historical rules-unit ownership drifted.")
    physical = physical_model_authority_before_event(
        state=state,
        event_records=events,
        decision_records=records,
        event_index=index,
    )
    identities = {
        model.model_instance_id: (army, unit, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    geometry: dict[str, Model] = {}
    for row in physical:
        if row.presence not in {"battlefield", "retained_destroyed"}:
            continue
        if row.pose is None or row.model_instance_id not in identities:
            raise GameLifecycleError("Revival historical geometry is incomplete.")
        army, unit, model = identities[row.model_instance_id]
        geometry[row.model_instance_id] = geometry_model_for_placement(
            model=model,
            placement=ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=row.pose,
                split_origin=unit.split_origin,
            ),
        )
    if placement.model_instance_id not in identities:
        raise GameLifecycleError("Revival historical returned model is unknown.")
    before = tuple(row for row in physical if row.model_instance_id == placement.model_instance_id)
    if len(before) != 1 or before[0].presence != "destroyed" or before[0].wounds_remaining != 0:
        raise GameLifecycleError("Revival history requires a removed destroyed model.")
    expected = validate_revival_engagement_geometry(
        target_unit_instance_id=target.unit_instance_id,
        existing_models=tuple(
            geometry[model.model_instance_id]
            for model in target.own_models
            if model.model_instance_id in geometry
        ),
        enemies={
            enemy.unit_instance_id: tuple(
                geometry[model.model_instance_id]
                for model in enemy.own_models
                if model.model_instance_id in geometry
            )
            for enemy in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
            if enemy.owner_player_id != target.owner_player_id
        },
        returned_model=geometry_model_for_placement(
            model=identities[placement.model_instance_id][2],
            placement=placement,
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    actual = validated_revival_engagement_payload(
        payload.get("revival_engagement"), target_unit_instance_id=target.unit_instance_id
    )
    if actual != expected:
        raise GameLifecycleError("Revival engagement evidence differs from physical history.")
    phase_start = revival_phase_start_for_request(
        state=state,
        event_records=events,
        decision_records=records,
        request=record.request,
        target_unit_instance_id=target.unit_instance_id,
    )
    if validated_revival_phase_start_payload(payload.get("revival_phase_start")) != phase_start:
        raise GameLifecycleError(
            "Revival phase-start event evidence differs from physical history."
        )
    validate_revival_anchor_coherency(
        returned=geometry_model_for_placement(
            model=identities[placement.model_instance_id][2], placement=placement
        ),
        present_models=tuple(
            geometry[model.model_instance_id]
            for model in target.own_models
            if model.model_instance_id in geometry
        ),
        phase_start_model_ids=tuple(phase_start["model_ids"]),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
