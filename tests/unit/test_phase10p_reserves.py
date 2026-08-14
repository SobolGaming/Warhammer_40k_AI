from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_state,
    submit_handler_movement_proposal,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
)
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import (
    MissionPolicyDescriptor,
    MovementMode,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_REINFORCEMENTS_OPTION_ID,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure_integrity import (
    validate_non_destroyed_battlefield_departure_provenance,
)
from warhammer40k_core.engine.primary_reserve_arrival_integrity import (
    validate_primary_reserve_arrival_ingress_use_authority,
    validate_primary_reserve_arrival_placement_authority,
    validate_primary_reserve_arrival_request_chain,
    validate_primary_reserve_arrival_request_source,
)
from warhammer40k_core.engine.primary_reserve_entry_lifecycle_integrity import (
    validate_primary_reserve_entry_lifecycle_integrity,
)
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserve_declarations import (
    apply_reserve_declaration_decision,
    invalid_reserve_declaration_status,
    reserve_declaration_request_for_player,
)
from warhammer40k_core.engine.reserve_restriction_integrity import (
    reserve_arrival_restriction_expiry_is_proven,
)
from warhammer40k_core.engine.reserves import (
    LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
    BattlefieldEdge,
    LargeModelReservePlacementException,
    ReinforcementPlacement,
    ReserveArrivalCandidate,
    ReserveDestructionResult,
    ReserveDestructionResultPayload,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReservePlacementViolation,
    ReservePlacementViolationCode,
    ReservePostArrivalRestriction,
    ReserveState,
    ReserveStatus,
    ReserveUnitPointValue,
    StrategicReserveDeclaration,
    StrategicReserveRule,
    apply_reinforcement_placement_to_battlefield,
    apply_reserve_destruction_to_battlefield,
    battle_phase_token,
    battlefield_edge_from_token,
    reserve_kind_from_token,
    reserve_origin_from_token,
    reserve_placement_violation_code_from_token,
    reserve_post_arrival_restriction_from_token,
    reserve_status_from_token,
    resolve_reserve_arrival,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    request_stratagem_target_proposal,
)
from warhammer40k_core.engine.stratagems_model import (
    GENERIC_INGRESS_MOVE_HANDLER_ID,
    StratagemCatalogIndex,
    StratagemTargetProposalPayload,
    StratagemUseRecord,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_coherency import UnitCoherencyResult
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_movement_phase_requests_reserve_arrivals_inside_move_units() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    placed_unit_id = "army-alpha:intercessor-unit-2"
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=(placed_unit_id,),
        moved_unit_ids=(placed_unit_id,),
    )
    decisions = DecisionController()

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=decisions,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    payload = cast(dict[str, object], status.payload)
    assert payload["step"] == MovementPhaseStepKind.MOVE_UNITS.value
    assert payload["phase_body_status"] == "move_units_waiting_for_arrival_choice"
    assert payload["unarrived_reserve_count"] == 1
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    request_payload = cast(dict[str, object], status.decision_request.payload)
    assert request_payload["step"] == MovementPhaseStepKind.MOVE_UNITS.value
    assert {option.option_id for option in status.decision_request.options} == {
        COMPLETE_REINFORCEMENTS_OPTION_ID,
        reserve_state.unit_instance_id,
    }
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.step is MovementPhaseStepKind.MOVE_UNITS
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_reinforcements_valid_strategic_reserves_arrival_mutates_state_atomically() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=3,
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id="phase10p-select-strategic",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    placement_proposal = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    assert placement_proposal.proposal_kind is ProposalKind.STRATEGIC_RESERVES

    result_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
        result_id="phase10p-place-strategic",
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)

    assert result_status.status_kind is LifecycleStatusKind.ADVANCED
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(reserve_unit.unit_instance_id)
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert arrived_state.arrived_phase == BattlePhase.MOVEMENT.value
    assert state.movement_phase_state is not None
    assert reserve_state.unit_instance_id in state.movement_phase_state.moved_unit_ids
    arrival_event = _last_event_payload(decisions, "reinforcement_unit_arrived")
    assert arrival_event["placement_kind"] == BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    transition_batch = arrival_event["transition_batch"]
    assert isinstance(transition_batch, dict)
    placements = cast(list[dict[str, object]], transition_batch["placements"])
    assert placements[0]["placement_kind"] == BattlefieldPlacementKind.STRATEGIC_RESERVES.value


def test_declared_reserve_arrival_round_trip_rejects_route_event_tamper() -> None:
    lifecycle = _declared_reserve_arrival_lifecycle()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    restored = GameLifecycle.from_payload(payload)

    assert restored.state is not None
    restored_reserve = restored.state.reserve_state_for_unit("army-alpha:intercessor-unit-1")
    assert restored_reserve is not None
    assert restored_reserve.status is ReserveStatus.ARRIVED

    forged_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    matching_arrivals = tuple(
        event
        for event in forged_payload["decisions"]["event_log"]
        if event["event_type"] == "reinforcement_unit_arrived"
    )
    assert len(matching_arrivals) == 1
    arrival_payload = matching_arrivals[0]["payload"]
    assert isinstance(arrival_payload, dict)
    arrival_payload["phase_body_status"] = "forged_initial_arrival_status"

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival route event authority drift",
    ):
        GameLifecycle.from_payload(forged_payload)


def test_aircraft_edge_departure_arrives_next_turn_and_round_trips() -> None:
    lifecycle, aircraft = _aircraft_edge_departure_lifecycle()
    state = lifecycle.state
    assert state is not None
    reserve_state = state.reserve_state_for_unit(aircraft.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.DURING_BATTLE_OTHER
    assert reserve_state.required_arrival_battle_round == 2
    assert reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
    (departure,) = state.primary_battlefield_departure_states
    assert departure.rules_unit_instance_id == aircraft.unit_instance_id
    assert departure.removal_kind is BattlefieldRemovalKind.INTO_RESERVES
    assert departure.removed_model_instance_ids == aircraft.own_model_ids()

    departure_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored_departure = GameLifecycle.from_payload(departure_payload)
    assert restored_departure.to_payload() == lifecycle.to_payload()
    departure_state = restored_departure.state
    assert departure_state is not None
    departure_decisions = restored_departure.decision_controller
    departure_events = departure_decisions.event_log.records
    departure_states = tuple(departure_state.primary_battlefield_departure_states)
    mutation_event = next(
        event for event in departure_events if event.event_type == "primary_reserve_entry_mutated"
    )

    def events_with_mutation_payload(payload: dict[str, object]) -> tuple[EventRecord, ...]:
        return tuple(
            replace(event, payload=validate_json_value(payload))
            if event.event_id == mutation_event.event_id
            else event
            for event in departure_events
        )

    def mutation_payload() -> dict[str, object]:
        assert isinstance(mutation_event.payload, dict)
        return cast(
            dict[str, object],
            json.loads(json.dumps(mutation_event.payload, sort_keys=True)),
        )

    provider_payload = mutation_payload()
    provider_payload["provider"] = {}
    with pytest.raises(
        GameLifecycleError,
        match="Aircraft reserve-entry mutation names an ability provider",
    ):
        validate_non_destroyed_battlefield_departure_provenance(
            state=departure_state,
            departures=departure_states,
            event_records=events_with_mutation_payload(provider_payload),
            decision_records=departure_decisions.records,
        )

    missing_transition_payload = mutation_payload()
    missing_transition_payload["transition_batch"] = None
    with pytest.raises(
        GameLifecycleError,
        match="Provider-free reserve-entry mutation requires an Aircraft transition",
    ):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=departure_state,
            event_records=events_with_mutation_payload(missing_transition_payload),
            decision_records=departure_decisions.records,
            stratagem_indexes_by_player_id=None,
            ability_indexes_by_player_id=None,
        )

    origin_payload = mutation_payload()
    origin_state = cast(dict[str, object], origin_payload["reserve_entry_state"])
    origin_state["reserve_origin"] = ReserveOrigin.DECLARE_BATTLE_FORMATIONS.value
    with pytest.raises(GameLifecycleError, match="Aircraft reserve-entry origin drift"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=departure_state,
            event_records=events_with_mutation_payload(origin_payload),
            decision_records=departure_decisions.records,
            stratagem_indexes_by_player_id=None,
            ability_indexes_by_player_id=None,
        )

    non_removal_payload = mutation_payload()
    non_removal_transition = cast(dict[str, object], non_removal_payload["transition_batch"])
    non_removal_transition["placements"] = [{"forged": True}]
    with pytest.raises(
        GameLifecycleError,
        match="Aircraft reserve transition contains non-removal mutation",
    ):
        validate_non_destroyed_battlefield_departure_provenance(
            state=departure_state,
            departures=departure_states,
            event_records=events_with_mutation_payload(non_removal_payload),
            decision_records=departure_decisions.records,
        )

    removal_drift_payload = mutation_payload()
    removal_drift_transition = cast(dict[str, object], removal_drift_payload["transition_batch"])
    removals = cast(list[dict[str, object]], removal_drift_transition["removals"])
    removals[0]["source_phase"] = BattlePhase.SHOOTING.value
    with pytest.raises(
        GameLifecycleError,
        match="Aircraft reserve transition removal identity drift",
    ):
        validate_non_destroyed_battlefield_departure_provenance(
            state=departure_state,
            departures=departure_states,
            event_records=events_with_mutation_payload(removal_drift_payload),
            decision_records=departure_decisions.records,
        )

    removed_model_drift_payload = mutation_payload()
    removed_model_transition = cast(
        dict[str, object], removed_model_drift_payload["transition_batch"]
    )
    removed_model_transition["removals"] = []
    with pytest.raises(
        GameLifecycleError,
        match="Aircraft reserve transition removed-model identity drift",
    ):
        validate_non_destroyed_battlefield_departure_provenance(
            state=departure_state,
            departures=departure_states,
            event_records=events_with_mutation_payload(removed_model_drift_payload),
            decision_records=departure_decisions.records,
        )

    with pytest.raises(
        GameLifecycleError,
        match="Primary Aircraft reserve departure lacks its accepted movement decision",
    ):
        validate_non_destroyed_battlefield_departure_provenance(
            state=departure_state,
            departures=departure_states,
            event_records=departure_events,
            decision_records=tuple(
                decision
                for decision in departure_decisions.records
                if decision.result.result_id != departure.source_id
            ),
        )

    decisions = lifecycle.decision_controller
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    _set_movement_ready_for_reinforcements(state=state, battle_round=2)
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert selection_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=aircraft.unit_instance_id,
            result_id="phase10p-aircraft-arrival-select",
        )
    )
    diameter_mm = aircraft.own_models[0].base_size.diameter_mm
    assert diameter_mm is not None
    status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=aircraft,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=aircraft,
            pose=_south_edge_touching_pose(base_diameter_mm=diameter_mm, x=15.0),
        ),
        result_id="phase10p-aircraft-arrival-place",
    )
    if status is None:
        status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    arrived_state = state.reserve_state_for_unit(aircraft.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert arrived_state.arrived_battle_round == 2
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)

    arrival_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored_arrival = GameLifecycle.from_payload(arrival_payload)
    assert restored_arrival.to_payload() == lifecycle.to_payload()


def test_rapid_ingress_arrival_uses_authenticated_stratagem_history() -> None:
    lifecycle = _rapid_ingress_arrival_lifecycle()
    state = lifecycle.state
    assert state is not None
    reserve_state = state.reserve_state_for_unit("army-alpha:intercessor-unit-1")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.ARRIVED
    replay_lifecycle = GameLifecycle(
        state=state,
        decision_controller=lifecycle.decision_controller,
    )
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(replay_lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == replay_lifecycle.to_payload()

    decisions = lifecycle.decision_controller
    events = decisions.event_log.records
    use = state.stratagem_use_records[0]
    target_decision = next(
        decision
        for decision in decisions.records
        if decision.request.request_id == use.request_id
        and decision.result.result_id == use.result_id
    )
    arrival_event = next(
        event
        for event in events
        if event.event_type == "reinforcement_unit_arrived"
        and isinstance(event.payload, dict)
        and event.payload.get("stratagem_use") == use.to_payload()
    )
    arrival_event_payload = cast(dict[str, JsonValue], arrival_event.payload)
    placement_decision = next(
        decision
        for decision in decisions.records
        if decision.request.request_id == arrival_event_payload["request_id"]
        and decision.result.result_id == arrival_event_payload["result_id"]
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_decision.request.payload
    )
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, placement_decision.result.payload)
    )
    transition_payload = cast(
        BattlefieldTransitionBatchPayload,
        arrival_event_payload["transition_batch"],
    )
    transition = BattlefieldTransitionBatch.from_payload(transition_payload)
    event_index_by_id = {event.event_id: index for index, event in enumerate(events)}
    placement_requested_event = next(
        event
        for event in events
        if event.event_type == "decision_requested"
        and event.payload == placement_decision.request.to_payload()
    )
    placement_request_order = event_index_by_id[placement_requested_event.event_id]

    validate_primary_reserve_arrival_ingress_use_authority(
        state=state,
        use=use,
        proposal_request=proposal_request,
        event_records=events,
        decision_records=decisions.records,
        event_index_by_id=event_index_by_id,
        placement_request_order=placement_request_order,
        stratagem_indexes_by_player_id=None,
    )

    with pytest.raises(
        GameLifecycleError,
        match="Ingress use lacks one accepted Stratagem decision",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=use,
            proposal_request=proposal_request,
            event_records=events,
            decision_records=tuple(
                decision
                for decision in decisions.records
                if decision.record_id != target_decision.record_id
            ),
            event_index_by_id=event_index_by_id,
            placement_request_order=placement_request_order,
            stratagem_indexes_by_player_id=None,
        )

    malformed_selection_use = replace(
        use,
        request_id=placement_decision.request.request_id,
        result_id=placement_decision.result.result_id,
    )
    with pytest.raises(
        GameLifecycleError,
        match="Ingress use Stratagem selection is malformed",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=malformed_selection_use,
            proposal_request=proposal_request,
            event_records=events,
            decision_records=decisions.records,
            event_index_by_id=event_index_by_id,
            placement_request_order=placement_request_order,
            stratagem_indexes_by_player_id=None,
        )

    with pytest.raises(
        GameLifecycleError,
        match="Ingress use accepted Stratagem authority drift: effect resolution",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=replace(
                use,
                effects_resolved=False,
                unresolved_reason="phase10p-integrity-drift",
                command_point_cost=0,
                command_point_transaction_id=None,
            ),
            proposal_request=proposal_request,
            event_records=events,
            decision_records=decisions.records,
            event_index_by_id=event_index_by_id,
            placement_request_order=placement_request_order,
            stratagem_indexes_by_player_id=None,
        )

    without_use_event = tuple(event for event in events if event.event_type != "stratagem_used")
    with pytest.raises(GameLifecycleError, match="Ingress use decision/event closure drift"):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=use,
            proposal_request=proposal_request,
            event_records=without_use_event,
            decision_records=decisions.records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(without_use_event)
            },
            placement_request_order=next(
                index
                for index, event in enumerate(without_use_event)
                if event.event_id == placement_requested_event.event_id
            ),
            stratagem_indexes_by_player_id=None,
        )

    use_event = next(event for event in events if event.event_type == "stratagem_used")
    reordered_events = tuple(event for event in events if event.event_id != use_event.event_id)
    placement_index = next(
        index
        for index, event in enumerate(reordered_events)
        if event.event_id == placement_requested_event.event_id
    )
    reordered_events = (
        *reordered_events[: placement_index + 1],
        use_event,
        *reordered_events[placement_index + 1 :],
    )
    with pytest.raises(GameLifecycleError, match="Ingress use decision/event ordering drift"):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=use,
            proposal_request=proposal_request,
            event_records=reordered_events,
            decision_records=decisions.records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(reordered_events)
            },
            placement_request_order=placement_index,
            stratagem_indexes_by_player_id=None,
        )

    target_result_payload = cast(dict[str, JsonValue], target_decision.result.payload)
    source_target_proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, target_result_payload["proposal"])
    )

    def ingress_variant(
        *,
        handler_id: str,
        effect_payload: JsonValue,
    ) -> tuple[
        StratagemUseRecord,
        MovementProposalRequest,
        DecisionRecord,
        tuple[EventRecord, ...],
        StratagemCatalogIndex,
    ]:
        catalog_record = replace(
            source_target_proposal.catalog_record,
            definition=replace(
                source_target_proposal.catalog_record.definition,
                handler_id=handler_id,
                effect_payload=effect_payload,
            ),
        )
        selected_proposal = replace(
            source_target_proposal,
            catalog_record=catalog_record,
        )
        selected_decision = replace(
            target_decision,
            result=replace(
                target_decision.result,
                payload=validate_json_value({"proposal": selected_proposal.to_payload()}),
            ),
        )
        selected_use = replace(
            use,
            handler_id=handler_id,
            effect_payload=effect_payload,
        )
        raw_context = dict(proposal_request.context or {})
        raw_context["stratagem_handler_id"] = handler_id
        raw_context["stratagem_use"] = validate_json_value(selected_use.to_payload())
        if handler_id == GENERIC_INGRESS_MOVE_HANDLER_ID:
            raw_context.update(
                {
                    "from_start_of_battle": True,
                    "placement_scope": "strategic_reserves_only",
                    "mark_movement_phase_reinforcement_arrival": False,
                }
            )
        selected_request = replace(
            proposal_request,
            context=cast(dict[str, JsonValue], validate_json_value(raw_context)),
        )
        selected_events = tuple(
            replace(event, payload=validate_json_value(selected_decision.to_payload()))
            if event.event_type == "decision_recorded"
            and event.payload == target_decision.to_payload()
            else (
                replace(event, payload=validate_json_value(selected_use.to_payload()))
                if event.event_type == "stratagem_used" and event.payload == use.to_payload()
                else event
            )
            for event in events
        )
        return (
            selected_use,
            selected_request,
            selected_decision,
            selected_events,
            StratagemCatalogIndex.from_records((catalog_record,)),
        )

    disabled_record = replace(source_target_proposal.catalog_record, disabled=True)
    disabled_proposal = replace(
        source_target_proposal,
        catalog_record=disabled_record,
    )
    disabled_decision = replace(
        target_decision,
        result=replace(
            target_decision.result,
            payload=validate_json_value({"proposal": disabled_proposal.to_payload()}),
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Ingress active Stratagem catalog authority drift",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=use,
            proposal_request=proposal_request,
            event_records=events,
            decision_records=tuple(
                disabled_decision if decision.record_id == target_decision.record_id else decision
                for decision in decisions.records
            ),
            event_index_by_id=event_index_by_id,
            placement_request_order=placement_request_order,
            stratagem_indexes_by_player_id=None,
        )

    generic_effect: JsonValue = {
        "effect_kind": "ingress_move",
        "from_start_of_battle": True,
        "placement_scope": "strategic_reserves_only",
    }
    generic_use, generic_request, generic_decision, generic_events, generic_index = ingress_variant(
        handler_id=GENERIC_INGRESS_MOVE_HANDLER_ID,
        effect_payload=generic_effect,
    )
    generic_decisions = tuple(
        generic_decision if decision.record_id == target_decision.record_id else decision
        for decision in decisions.records
    )
    generic_event_indexes = {event.event_id: index for index, event in enumerate(generic_events)}
    with pytest.raises(
        GameLifecycleError,
        match="Ingress requires active runtime Stratagem catalog authority",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=generic_use,
            proposal_request=generic_request,
            event_records=generic_events,
            decision_records=generic_decisions,
            event_index_by_id=generic_event_indexes,
            placement_request_order=generic_event_indexes[placement_requested_event.event_id],
            stratagem_indexes_by_player_id=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Ingress lacks its active player Stratagem index",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=generic_use,
            proposal_request=generic_request,
            event_records=generic_events,
            decision_records=generic_decisions,
            event_index_by_id=generic_event_indexes,
            placement_request_order=generic_event_indexes[placement_requested_event.event_id],
            stratagem_indexes_by_player_id={},
        )

    generic_indexes = {"player-a": generic_index}
    generic_context = dict(generic_request.context or {})
    generic_context["mark_movement_phase_reinforcement_arrival"] = True
    with pytest.raises(
        GameLifecycleError,
        match="Generic ingress proposal context authority drift",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=generic_use,
            proposal_request=replace(
                generic_request,
                context=cast(
                    dict[str, JsonValue],
                    validate_json_value(generic_context),
                ),
            ),
            event_records=generic_events,
            decision_records=generic_decisions,
            event_index_by_id=generic_event_indexes,
            placement_request_order=generic_event_indexes[placement_requested_event.event_id],
            stratagem_indexes_by_player_id=generic_indexes,
        )

    invalid_effect_cases: tuple[tuple[JsonValue, str], ...] = (
        (None, "Ingress move effect must be an object"),
        ({"effect_kind": "forged"}, "Ingress move effect authority drift"),
    )
    for invalid_effect, message in invalid_effect_cases:
        invalid_use, invalid_request, invalid_decision, invalid_events, invalid_index = (
            ingress_variant(
                handler_id=GENERIC_INGRESS_MOVE_HANDLER_ID,
                effect_payload=invalid_effect,
            )
        )
        invalid_decisions = tuple(
            invalid_decision if decision.record_id == target_decision.record_id else decision
            for decision in decisions.records
        )
        invalid_event_indexes = {
            event.event_id: index for index, event in enumerate(invalid_events)
        }
        with pytest.raises(GameLifecycleError, match=message):
            validate_primary_reserve_arrival_ingress_use_authority(
                state=state,
                use=invalid_use,
                proposal_request=invalid_request,
                event_records=invalid_events,
                decision_records=invalid_decisions,
                event_index_by_id=invalid_event_indexes,
                placement_request_order=invalid_event_indexes[placement_requested_event.event_id],
                stratagem_indexes_by_player_id={"player-a": invalid_index},
            )

    validate_primary_reserve_arrival_ingress_use_authority(
        state=state,
        use=generic_use,
        proposal_request=generic_request,
        event_records=generic_events,
        decision_records=generic_decisions,
        event_index_by_id=generic_event_indexes,
        placement_request_order=generic_event_indexes[placement_requested_event.event_id],
        stratagem_indexes_by_player_id=generic_indexes,
    )

    (
        unsupported_use,
        unsupported_request,
        unsupported_decision,
        unsupported_events,
        unsupported_index,
    ) = ingress_variant(
        handler_id="phase10p:unsupported-ingress",
        effect_payload=None,
    )
    unsupported_decisions = tuple(
        unsupported_decision if decision.record_id == target_decision.record_id else decision
        for decision in decisions.records
    )
    unsupported_event_indexes = {
        event.event_id: index for index, event in enumerate(unsupported_events)
    }
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival uses an unsupported ingress handler",
    ):
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=unsupported_use,
            proposal_request=unsupported_request,
            event_records=unsupported_events,
            decision_records=unsupported_decisions,
            event_index_by_id=unsupported_event_indexes,
            placement_request_order=unsupported_event_indexes[placement_requested_event.event_id],
            stratagem_indexes_by_player_id={"player-a": unsupported_index},
        )

    validate_primary_reserve_arrival_placement_authority(
        state=state,
        proposal_request=proposal_request,
        submitted=submitted,
        transition=transition,
        expected_owner_id="player-a",
    )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival placement submission is malformed",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=state,
            proposal_request=proposal_request,
            submitted=cast(PlacementProposalPayload, object()),
            transition=transition,
            expected_owner_id="player-a",
        )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival transition is malformed",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=state,
            proposal_request=proposal_request,
            submitted=submitted,
            transition=cast(BattlefieldTransitionBatch, object()),
            expected_owner_id="player-a",
        )

    context_without_reserve = dict(proposal_request.context or {})
    context_without_reserve.pop("reserve_state")
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request lacks ReserveState authority",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=state,
            proposal_request=replace(
                proposal_request,
                context=cast(
                    dict[str, JsonValue],
                    validate_json_value(context_without_reserve),
                ),
            ),
            submitted=submitted,
            transition=transition,
            expected_owner_id="player-a",
        )

    invalid_reserve_context = dict(proposal_request.context or {})
    invalid_reserve_context["reserve_state"] = {"status": "forged"}
    invalid_reserve_request = replace(
        proposal_request,
        context=cast(
            dict[str, JsonValue],
            validate_json_value(invalid_reserve_context),
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request ReserveState is invalid",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=state,
            proposal_request=invalid_reserve_request,
            submitted=submitted,
            transition=transition,
            expected_owner_id="player-a",
        )

    malformed_context = dict(proposal_request.context or {})
    malformed_context["component_unit_instance_ids"] = None
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request component IDs must be an identifier list",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=state,
            proposal_request=replace(
                proposal_request,
                context=cast(
                    dict[str, JsonValue],
                    validate_json_value(malformed_context),
                ),
            ),
            submitted=submitted,
            transition=transition,
            expected_owner_id="player-a",
        )

    battlefield_drift_state = GameState.from_payload(state.to_payload())
    battlefield_drift_state.battlefield_state = None
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival final battlefield placement drift",
    ):
        validate_primary_reserve_arrival_placement_authority(
            state=battlefield_drift_state,
            proposal_request=proposal_request,
            submitted=submitted,
            transition=transition,
            expected_owner_id="player-a",
        )

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request ReserveState source is invalid",
    ):
        validate_primary_reserve_arrival_request_source(
            proposal_request=invalid_reserve_request,
            expected_owner_id="player-a",
            placement_request_order=placement_request_order,
            reserve_entry_occurrences=(),
            event_records=events,
            event_index_by_id=event_index_by_id,
        )
    without_initial_source = tuple(
        event for event in events if event.event_type != "reserve_unit_declared"
    )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request lacks one initial ReserveState source",
    ):
        validate_primary_reserve_arrival_request_source(
            proposal_request=proposal_request,
            expected_owner_id="player-a",
            placement_request_order=placement_request_order,
            reserve_entry_occurrences=(),
            event_records=without_initial_source,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(without_initial_source)
            },
        )

    without_placement_request = tuple(
        event for event in events if event.event_id != placement_requested_event.event_id
    )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival placement request event closure drift",
    ):
        validate_primary_reserve_arrival_request_chain(
            proposal_request=proposal_request,
            placement_decision=placement_decision,
            expected_owner_id="player-a",
            ingress_use=use,
            event_records=without_placement_request,
            decision_records=decisions.records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(without_placement_request)
            },
        )

    source_event = next(
        event
        for event in events
        if event.event_type == "placement_proposal_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == proposal_request.request_id
    )
    assert isinstance(source_event.payload, dict)

    def events_with_source_payload(payload: dict[str, JsonValue]) -> tuple[EventRecord, ...]:
        return tuple(
            replace(event, payload=payload) if event.event_id == source_event.event_id else event
            for event in events
        )

    malformed_retry_payload = dict(source_event.payload)
    malformed_retry_payload["previous_proposal_request_id"] = 0
    malformed_retry_events = events_with_source_payload(malformed_retry_payload)
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival previous placement request must be an identifier",
    ):
        validate_primary_reserve_arrival_request_chain(
            proposal_request=proposal_request,
            placement_decision=placement_decision,
            expected_owner_id="player-a",
            ingress_use=use,
            event_records=malformed_retry_events,
            decision_records=decisions.records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(malformed_retry_events)
            },
        )

    invalid_retry_payload = dict(source_event.payload)
    invalid_retry_payload["previous_proposal_request_id"] = target_decision.request.request_id
    invalid_retry_payload["rejected_result_id"] = target_decision.result.result_id
    invalid_retry_events = events_with_source_payload(invalid_retry_payload)
    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival retry predecessor is invalid",
    ):
        validate_primary_reserve_arrival_request_chain(
            proposal_request=proposal_request,
            placement_decision=placement_decision,
            expected_owner_id="player-a",
            ingress_use=use,
            event_records=invalid_retry_events,
            decision_records=decisions.records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(invalid_retry_events)
            },
        )

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival placement source handler is unsupported",
    ):
        validate_primary_reserve_arrival_request_chain(
            proposal_request=unsupported_request,
            placement_decision=placement_decision,
            expected_owner_id="player-a",
            ingress_use=unsupported_use,
            event_records=events,
            decision_records=decisions.records,
            event_index_by_id=event_index_by_id,
        )


def test_reinforcements_valid_deep_strike_uses_deep_strike_placement_record() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    state.army_definitions = list(
        _with_replaced_unit(tuple(state.army_definitions), deep_strike_unit)
    )
    deep_strike_state = replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE)
    state.replace_reserve_state(deep_strike_state)
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=1,
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=deep_strike_state.unit_instance_id,
        result_id="phase10p-select-deep-strike",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    result_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=deep_strike_unit,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=deep_strike_unit,
            pose=Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0),
        ),
        result_id="phase10p-place-deep-strike",
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)

    assert result_status.status_kind is LifecycleStatusKind.ADVANCED
    arrival_event = _last_event_payload(decisions, "reinforcement_unit_arrived")
    transition_batch = arrival_event["transition_batch"]
    assert isinstance(transition_batch, dict)
    placements = cast(list[dict[str, object]], transition_batch["placements"])
    assert placements[0]["placement_kind"] == BattlefieldPlacementKind.DEEP_STRIKE.value
    assert placements[0]["source_rule_id"] == "deep_strike"


def test_reinforcements_invalid_arrival_does_not_mutate_state() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    before_battlefield = state.battlefield_state.to_payload() if state.battlefield_state else None
    before_reserve_state = reserve_state
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=1,
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id="phase10p-select-invalid",
    )
    placement_request = _decision_request(placement_status)

    invalid_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
        result_id="phase10p-place-invalid",
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == before_reserve_state


def test_reinforcements_completion_choice_leaves_reserve_unarrived_and_advances_phase() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    _set_movement_ready_for_reinforcements(state=state, battle_round=3)
    flow = BattleRoundFlow(phase_handlers={BattlePhase.MOVEMENT: handler})
    selection_status = flow.advance(state=state, decisions=decisions)
    selection_request = _decision_request(selection_status)

    decision_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
        result_id="phase10p-complete-reinforcements",
    )
    assert decision_status is None
    advanced_status = flow.advance(state=state, decisions=decisions)

    assert advanced_status.status_kind is LifecycleStatusKind.ADVANCED
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_oversized_strategic_reserve_model_can_touch_required_edge() -> None:
    state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert result.is_valid
    assert result.transition_batch is not None
    assert {record.placement_kind for record in result.transition_batch.placements} == {
        BattlefieldPlacementKind.STRATEGIC_RESERVES
    }
    arrived_state = result.arrived_reserve_state()
    assert arrived_state.large_model_exception_used
    assert set(arrived_state.post_arrival_restrictions) == set(
        LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS
    )
    assert state.battlefield_state is not None
    updated_battlefield = apply_reinforcement_placement_to_battlefield(
        battlefield_state=state.battlefield_state,
        placement=result,
    )
    assert updated_battlefield.unit_placement_by_id(reserve_unit.unit_instance_id) == placement


def test_attached_rules_unit_strategic_reserve_arrival_adds_every_component_atomically() -> None:
    config = _config(ruleset_descriptor=_ruleset())
    mustered_armies = _mustered_armies(config)
    alpha = mustered_armies[0]
    bodyguard = replace(
        alpha.unit_by_id("army-alpha:intercessor-unit-1"),
        own_models=alpha.unit_by_id("army-alpha:intercessor-unit-1").own_models[:1],
    )
    leader = replace(
        alpha.unit_by_id("army-alpha:intercessor-unit-2"),
        own_models=alpha.unit_by_id("army-alpha:intercessor-unit-2").own_models[:1],
    )
    attached_id = "attached-unit:army-alpha:reserve-unit"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="test:phase10p-attached-reserve",
        attachment_source_ids=("test:phase10p-attached-reserve-eligibility",),
    )
    alpha = replace(
        alpha,
        units=(bodyguard, leader),
        attached_units=(formation,),
    )
    armies = (alpha, mustered_armies[1])
    placed = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-attached-reserve-battlefield",
        armies=armies,
    ).battlefield_state
    battlefield = placed
    for unit in (*alpha.units, *armies[1].units):
        battlefield = battlefield.without_unit_placement(unit.unit_instance_id)
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield)
    reserve_state = ReserveState.declared_before_battle(
        player_id=alpha.player_id,
        unit_instance_id=attached_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _ruleset().mission_policy
        ),
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.record_reserve_state(reserve_state)

    assert state.reserve_state_for_unit(attached_id) == reserve_state
    assert state.reserve_state_for_unit(bodyguard.unit_instance_id) == reserve_state
    assert state.reserve_state_for_unit(leader.unit_instance_id) == reserve_state

    grouped_placement = RulesUnitPlacement(
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            _single_model_reserve_placement(
                reserve_unit=bodyguard,
                pose=Pose.at(x=15.0, y=0.75, z=0.0, facing_degrees=0.0),
            ),
            _single_model_reserve_placement(
                reserve_unit=leader,
                pose=Pose.at(x=16.5, y=0.75, z=0.0, facing_degrees=0.0),
            ),
        ),
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=grouped_placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )

    assert result.is_valid
    assert ReserveArrivalCandidate.from_payload(result.candidate.to_payload()) == result.candidate
    assert result.candidate.attempted_rules_unit_placement == grouped_placement
    updated_battlefield = apply_reinforcement_placement_to_battlefield(
        battlefield_state=battlefield,
        placement=result,
    )
    assert all(
        not battlefield.is_unit_placed(component_id)
        for component_id in formation.component_unit_instance_ids
    )
    assert all(
        updated_battlefield.is_unit_placed(component_id)
        for component_id in formation.component_unit_instance_ids
    )
    assert (
        updated_battlefield.unit_placement_by_id(bodyguard.unit_instance_id)
        == grouped_placement.component_unit_placements[0]
    )
    assert (
        updated_battlefield.unit_placement_by_id(leader.unit_instance_id)
        == grouped_placement.component_unit_placements[1]
    )

    arrived_state = result.arrived_reserve_state()
    state.replace_battlefield_state(updated_battlefield)
    state.replace_reserve_state(arrived_state)
    assert state.reserve_state_for_unit(bodyguard.unit_instance_id) == arrived_state
    assert state.reserve_state_for_unit(leader.unit_instance_id) == arrived_state


def test_rules_unit_placement_fail_fast_guards_cover_group_identity_and_boundaries() -> None:
    _state, scenario, _reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
        reserve_model_count=2,
    )
    placement = _reserve_placement(
        reserve_unit=reserve_unit,
        poses=(
            Pose.at(x=15.0, y=0.75, z=0.0, facing_degrees=0.0),
            Pose.at(x=16.5, y=0.75, z=0.0, facing_degrees=0.0),
        ),
    )
    view = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=reserve_unit.unit_instance_id,
    )

    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        RulesUnitPlacement(
            rules_unit_instance_id=reserve_unit.unit_instance_id,
            component_unit_placements=cast(tuple[UnitPlacement, ...], [placement]),
        )
    with pytest.raises(GameLifecycleError, match="at least one"):
        RulesUnitPlacement(
            rules_unit_instance_id=reserve_unit.unit_instance_id,
            component_unit_placements=(),
        )
    with pytest.raises(GameLifecycleError, match="must be UnitPlacement"):
        RulesUnitPlacement(
            rules_unit_instance_id=reserve_unit.unit_instance_id,
            component_unit_placements=cast(tuple[UnitPlacement, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="component unit IDs must be unique"):
        RulesUnitPlacement(
            rules_unit_instance_id="attached-unit:army-alpha:duplicate",
            component_unit_placements=(placement, placement),
        )
    with pytest.raises(GameLifecycleError, match=r"Single-component.*identity"):
        RulesUnitPlacement(
            rules_unit_instance_id="army-alpha:other-unit",
            component_unit_placements=(placement,),
        )
    with pytest.raises(GameLifecycleError, match="Single rules-unit placement"):
        RulesUnitPlacement.single(cast(UnitPlacement, object()))

    other_model_placements = tuple(
        replace(
            model_placement,
            unit_instance_id="army-alpha:other-unit",
            model_instance_id=model_placement.model_instance_id.replace(
                reserve_unit.unit_instance_id,
                "army-alpha:other-unit",
            ),
        )
        for model_placement in placement.model_placements
    )
    other_placement = replace(
        placement,
        unit_instance_id="army-alpha:other-unit",
        model_placements=other_model_placements,
    )
    with pytest.raises(GameLifecycleError, match="attached-unit identity"):
        RulesUnitPlacement(
            rules_unit_instance_id=reserve_unit.unit_instance_id,
            component_unit_placements=(placement, other_placement),
        )

    grouped = RulesUnitPlacement.single(placement)
    grouped.validate_for_view(view)
    with pytest.raises(GameLifecycleError, match="requires RulesUnitView"):
        grouped.validate_for_view(cast(RulesUnitView, object()))
    wrong_owner_placement = replace(
        placement,
        player_id="player-b",
        model_placements=tuple(
            replace(model_placement, player_id="player-b")
            for model_placement in placement.model_placements
        ),
    )
    with pytest.raises(GameLifecycleError, match="owner drift"):
        RulesUnitPlacement.single(wrong_owner_placement).validate_for_view(view)
    incomplete_placement = replace(
        placement,
        model_placements=(placement.model_placements[0],),
    )
    with pytest.raises(GameLifecycleError, match="every alive model"):
        RulesUnitPlacement.single(incomplete_placement).validate_for_view(view)

    with pytest.raises(GameLifecycleError, match="requires RulesUnitView"):
        RulesUnitPlacement.from_battlefield(
            view=cast(RulesUnitView, object()),
            battlefield_state=scenario.battlefield_state,
        )
    with pytest.raises(GameLifecycleError, match="requires BattlefieldRuntimeState"):
        RulesUnitPlacement.from_battlefield(
            view=view,
            battlefield_state=cast(BattlefieldRuntimeState, object()),
        )
    with pytest.raises(GameLifecycleError, match="must be on the battlefield"):
        RulesUnitPlacement.from_battlefield(
            view=view,
            battlefield_state=scenario.battlefield_state,
        )
    with pytest.raises(GameLifecycleError, match="removal requires"):
        grouped.without_from_battlefield(cast(BattlefieldRuntimeState, object()))
    with pytest.raises(GameLifecycleError, match="placement requires"):
        grouped.add_to_battlefield(cast(BattlefieldRuntimeState, object()))
    with pytest.raises(GameLifecycleError, match="geometry requires"):
        grouped.geometry_models(cast(BattlefieldScenario, object()))


def test_oversized_strategic_reserve_exception_still_rejects_enemy_distance() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    pose = _south_edge_touching_pose(base_diameter_mm=200.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(x=15.0, y=16.0, z=0.0, facing_degrees=180.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert not result.is_valid
    assert _violation_codes(result) == (ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,)


def test_strategic_reserves_enemy_distance_message_is_limit_agnostic() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    reserve_pose = _south_edge_touching_pose(base_diameter_mm=32.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=reserve_pose.position.x + (radius * 2.0) + 0.25,
            y=reserve_pose.position.y,
            z=10.0,
            facing_degrees=180.0,
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=reserve_pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        strategic_reserve_rule=StrategicReserveRule(enemy_horizontal_distance_inches=0.5),
    )

    distance_violations = tuple(
        violation
        for violation in result.violations
        if violation.violation_code is ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE
    )
    assert len(distance_violations) == 1
    assert distance_violations[0].message == (
        "Reserve placement is within the configured reserve enemy-distance limit."
    )


def test_strategic_reserves_reject_setup_within_enemy_engagement_range() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    reserve_pose = _south_edge_touching_pose(base_diameter_mm=32.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=reserve_pose.position.x + (radius * 2.0) + 0.75,
            y=reserve_pose.position.y,
            z=3.0,
            facing_degrees=180.0,
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=reserve_pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        strategic_reserve_rule=StrategicReserveRule(enemy_horizontal_distance_inches=0.5),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ENEMY_ENGAGEMENT_RANGE in codes
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE not in codes


def test_oversized_exception_preserves_other_placement_limits() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=200.0,
        reserve_model_count=2,
    )
    large_pose = _south_edge_touching_pose(base_diameter_mm=200.0, x=15.0)
    blocker_model_id = (
        scenario.army_by_id("army-alpha")
        .unit_by_id("army-alpha:intercessor-unit-2")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=blocker_model_id,
        pose=large_pose,
    )
    placement = _reserve_placement(
        reserve_unit=reserve_unit,
        poses=(
            large_pose,
            _south_edge_touching_pose(base_diameter_mm=32.0, x=50.0),
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        enemy_deployment_zones=(
            DeploymentZone.rectangle(
                "enemy-south-zone",
                "player-b",
                min_x=0.0,
                min_y=0.0,
                max_x=60.0,
                max_y=10.0,
            ),
        ),
        terrain_features=(_blocking_wall_feature(x=15.0, y=large_pose.position.y),),
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE in codes
    assert ReservePlacementViolationCode.MODEL_OVERLAP in codes
    assert ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL in codes
    assert ReservePlacementViolationCode.UNIT_COHERENCY_BROKEN in codes


def test_model_that_fits_cannot_use_large_model_exception_for_extra_positioning() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=Pose.at(x=15.0, y=6.5 + radius, z=0.0, facing_degrees=0.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert not result.is_valid
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_MODEL_CAN_FIT in set(
        _violation_codes(result)
    )


def test_large_model_exception_records_all_turn_restrictions() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert set(result.post_arrival_restrictions) == {
        ReservePostArrivalRestriction.NO_NORMAL_MOVE,
        ReservePostArrivalRestriction.NO_ADVANCE,
        ReservePostArrivalRestriction.NO_FALL_BACK,
        ReservePostArrivalRestriction.NO_REMAIN_STATIONARY,
        ReservePostArrivalRestriction.NO_RANGED_ATTACKS,
        ReservePostArrivalRestriction.NO_CHARGE,
    }


def test_rapid_ingress_restriction_expiry_uses_arrival_active_player_turn() -> None:
    state, _scenario, _reserve_state, _reserve_unit = _battle_state_with_reserve()
    state.battle_round = 3
    state.active_player_id = "player-a"

    assert not reserve_arrival_restriction_expiry_is_proven(
        state=state,
        arrival_active_player_id="player-a",
        restriction_battle_round=3,
    )

    # P2's Rapid Ingress during active P1's turn expires when P1's turn ends,
    # even though the reserve owner is P2 and the battle round has not changed.
    state.active_player_id = "player-b"
    assert reserve_arrival_restriction_expiry_is_proven(
        state=state,
        arrival_active_player_id="player-a",
        restriction_battle_round=3,
    )


def test_core_policy_destroys_unarrived_reserves_only_at_end_of_battle() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    policy = ReserveDestructionTimingPolicy.from_mission_policy(_ruleset().mission_policy)

    round_three = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=3,
        end_of_battle=False,
    )
    end_battle = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=5,
        end_of_battle=True,
    )

    assert round_three.destroyed_unit_instance_ids == ()
    assert end_battle.destroyed_unit_instance_ids == (reserve_state.unit_instance_id,)
    assert policy.source_id == (
        "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:20.01.02-strategic-reserves"
    )


def test_chapter_approved_policy_destroys_declare_battle_formation_reserves_at_br3() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    policy = ReserveDestructionTimingPolicy.from_mission_policy(
        _chapter_approved_ruleset().mission_policy
    )

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=3,
        end_of_battle=False,
    )

    assert result.destroyed_unit_instance_ids == (reserve_state.unit_instance_id,)
    assert result.updated_reserve_states[0].destroyed_battle_round == 3


def test_chapter_approved_policy_destroys_embarked_units_in_unarrived_transport() -> None:
    state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    embarked_unit_id = "army-alpha:intercessor-unit-2"
    scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(embarked_unit_id),
    )
    reserve_state = replace(
        reserve_state,
        embarked_unit_instance_ids=(embarked_unit_id,),
    )
    state.replace_reserve_state(reserve_state)

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _chapter_approved_ruleset().mission_policy
        ),
        battle_round=3,
        end_of_battle=False,
    )

    assert set(result.destroyed_unit_instance_ids) == {
        reserve_state.unit_instance_id,
        embarked_unit_id,
    }


def test_chapter_approved_policy_exempts_during_battle_strategic_reserves_at_br3() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    during_battle_state = replace(
        reserve_state,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        declared_during_step=None,
        entered_reserves_battle_round=2,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
    )

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(during_battle_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _chapter_approved_ruleset().mission_policy
        ),
        battle_round=3,
        end_of_battle=False,
    )

    assert result.destroyed_unit_instance_ids == ()
    assert result.updated_reserve_states == (during_battle_state,)


def test_reserve_origin_source_serializes_for_replay() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    during_battle_state = ReserveState(
        player_id="player-b",
        unit_instance_id="army-beta:intercessor-unit-3",
        reserve_origin=ReserveOrigin.DURING_BATTLE_STRATAGEM,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        declared_during_step=None,
        entered_reserves_battle_round=2,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
    )
    state.record_reserve_state(during_battle_state)
    payload = state.to_payload()
    decoded = cast(GameStatePayload, json.loads(json.dumps(payload, sort_keys=True)))

    restored = GameState.from_payload(decoded)

    restored_declared_state = restored.reserve_state_for_unit(reserve_state.unit_instance_id)
    restored_during_battle_state = restored.reserve_state_for_unit(
        during_battle_state.unit_instance_id
    )
    assert restored_declared_state is not None
    assert restored_during_battle_state is not None
    assert restored_declared_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS
    assert restored_during_battle_state.reserve_origin is ReserveOrigin.DURING_BATTLE_STRATAGEM
    assert restored_during_battle_state.entered_reserves_battle_round == 2


def test_phase10p_reserve_payloads_round_trip_without_object_repr() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    assert result.is_valid
    arrived_state = result.arrived_reserve_state()
    destroyed_state = reserve_state.mark_destroyed(battle_round=3)
    declaration = StrategicReserveDeclaration.for_unit(
        unit=reserve_unit,
        player_id="player-a",
        unit_points=100,
        embarked_unit_points=25,
        points_limit=200,
        embarked_unit_instance_ids=("army-alpha:intercessor-unit-2",),
    )
    violation = ReservePlacementViolation(
        violation_code=ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,
        message="enemy-distance",
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        blocker_id="enemy-model",
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    policy_payload = ReserveDestructionTimingPolicy.chapter_approved_2026_27().to_payload()
    assert (
        ReserveDestructionTimingPolicy.from_payload(policy_payload).to_payload() == policy_payload
    )
    assert ReserveState.from_payload(arrived_state.to_payload()).to_payload() == (
        arrived_state.to_payload()
    )
    assert ReserveState.from_payload(destroyed_state.to_payload()).to_payload() == (
        destroyed_state.to_payload()
    )
    assert StrategicReserveDeclaration.from_payload(declaration.to_payload()).to_payload() == (
        declaration.to_payload()
    )
    assert (
        declaration.to_reserve_state(
            destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default()
        ).reserve_kind
        is ReserveKind.STRATEGIC_RESERVES
    )
    assert (
        LargeModelReservePlacementException.from_payload(large_exception.to_payload()).to_payload()
        == large_exception.to_payload()
    )
    assert ReservePlacementViolation.from_payload(violation.to_payload()).to_payload() == (
        violation.to_payload()
    )
    assert ReserveArrivalCandidate.from_payload(result.candidate.to_payload()).to_payload() == (
        result.candidate.to_payload()
    )
    destruction_payload = cast(
        ReserveDestructionResultPayload,
        json.loads(json.dumps(destruction.to_payload(), sort_keys=True)),
    )
    assert destruction_payload == destruction.to_payload()
    encoded = json.dumps(result.to_payload(), sort_keys=True)
    assert "object at 0x" not in encoded
    assert "<" not in encoded


def test_phase10p_reserve_domain_validators_are_fail_fast() -> None:
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
    )

    with pytest.raises(GameLifecycleError, match="must not set battle_round"):
        ReserveDestructionTimingPolicy(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE,
            battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="requires battle_round"):
        ReserveDestructionTimingPolicy(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            battle_round=None,
        )
    with pytest.raises(GameLifecycleError, match="must not have arrival fields"):
        replace(reserve_state, arrived_battle_round=2, arrived_phase=BattlePhase.MOVEMENT.value)
    with pytest.raises(GameLifecycleError, match="Arrived ReserveState requires arrival fields"):
        replace(reserve_state, status=ReserveStatus.ARRIVED)
    with pytest.raises(GameLifecycleError, match="Destroyed ReserveState requires"):
        replace(reserve_state, status=ReserveStatus.DESTROYED)
    with pytest.raises(GameLifecycleError, match="must not keep restrictions"):
        replace(
            reserve_state,
            status=ReserveStatus.DESTROYED,
            destroyed_battle_round=3,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
            restriction_battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="restrictions require"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )
    with pytest.raises(GameLifecycleError, match="Large-model ReserveState"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            large_model_exception_used=True,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
            restriction_battle_round=3,
        )


def test_phase10p_strategic_reserve_declaration_rejects_forbidden_inputs() -> None:
    _state, _scenario, _reserve_state, reserve_unit = _battle_state_with_reserve()

    with pytest.raises(GameLifecycleError, match="FORTIFICATIONS"):
        StrategicReserveDeclaration(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step="declare_battle_formations",
            unit_points=100,
            embarked_unit_points=0,
            points_limit=200,
            has_fortification_keyword=True,
        )
    with pytest.raises(GameLifecycleError, match="exceeds points limit"):
        StrategicReserveDeclaration(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step="declare_battle_formations",
            unit_points=175,
            embarked_unit_points=50,
            points_limit=200,
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        StrategicReserveDeclaration.for_unit(
            unit=cast(UnitInstance, object()),
            player_id="player-a",
            unit_points=100,
            embarked_unit_points=0,
            points_limit=200,
        )


def test_phase10p_reserve_token_parsers_reject_unsupported_tokens() -> None:
    with pytest.raises(GameLifecycleError, match="ReserveKind token must be a string"):
        reserve_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveKind"):
        reserve_kind_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReserveOrigin token must be a string"):
        reserve_origin_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveOrigin"):
        reserve_origin_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReserveStatus token must be a string"):
        reserve_status_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveStatus"):
        reserve_status_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="BattlefieldEdge token must be a string"):
        battlefield_edge_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported BattlefieldEdge"):
        battlefield_edge_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReservePostArrivalRestriction token"):
        reserve_post_arrival_restriction_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReservePostArrivalRestriction"):
        reserve_post_arrival_restriction_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReservePlacementViolationCode token"):
        reserve_placement_violation_code_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReservePlacementViolationCode"):
        reserve_placement_violation_code_from_token("unknown")


def test_phase10p_reserve_arrival_invalid_state_and_edge_paths_are_typed() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )

    br1_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    kind_mismatch_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.RESERVES),
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    destroyed_state_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state.mark_destroyed(battle_round=3),
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    missing_exception_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=3.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id="missing-reserve-model",
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )
    contact_missing_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=5.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )

    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in set(
        _violation_codes(br1_result)
    )
    assert ReservePlacementViolationCode.RESERVE_KIND_MISMATCH in set(
        _violation_codes(kind_mismatch_result)
    )
    assert ReservePlacementViolationCode.RESERVE_STATE_NOT_UNARRIVED in set(
        _violation_codes(destroyed_state_result)
    )
    assert ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT in set(
        _violation_codes(missing_exception_result)
    )
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_CONTACT_MISSING in set(
        _violation_codes(contact_missing_result)
    )
    with pytest.raises(GameLifecycleError, match="cannot mark arrival"):
        br1_result.arrived_reserve_state()
    with pytest.raises(GameLifecycleError, match="Invalid reserve placement"):
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            placement=br1_result,
        )


def test_phase10p_regular_models_must_remain_wholly_inside_edge_band() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    edge_crossing_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=radius - 0.1, y=radius, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    unneeded_exception_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=3.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )
    outside_band_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=8.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )

    assert ReservePlacementViolationCode.BATTLEFIELD_EDGE_CROSSED in set(
        _violation_codes(edge_crossing_result)
    )
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_UNNEEDED in set(
        _violation_codes(unneeded_exception_result)
    )
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_EDGE_DISTANCE in set(
        _violation_codes(outside_band_result)
    )


def test_phase10p_deep_strike_requires_keyword_and_uses_same_arrival_path() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_state = replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    missing_keyword = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=deep_strike_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    valid = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=deep_strike_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.DEEP_STRIKE_KEYWORD_REQUIRED in set(
        _violation_codes(missing_keyword)
    )
    assert valid.is_valid
    assert valid.transition_batch is not None
    assert {record.source_rule_id for record in valid.transition_batch.placements} == {
        "deep_strike"
    }


def test_chapter_approved_declared_deep_strike_cannot_arrive_in_battle_round_1() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    result = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE),
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=deep_strike_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in set(
        _violation_codes(result)
    )


def test_chapter_approved_declared_strategic_reserves_cannot_arrive_in_battle_round_1() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in codes
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in codes


def test_chapter_approved_during_battle_strategic_reserves_arrival_exemption_is_honored() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    during_battle_state = replace(
        reserve_state,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        declared_during_step=None,
        entered_reserves_battle_round=1,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=during_battle_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN not in codes
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in codes


def test_core_rules_deep_strike_has_no_mission_pack_battle_round_1_block() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    result = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE),
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=deep_strike_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN not in set(
        _violation_codes(result)
    )
    assert result.is_valid


def test_reserve_arrival_with_embarked_units_is_deferred_until_transport_cargo_state() -> None:
    state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    cargo_reserve_state = replace(
        reserve_state,
        embarked_unit_instance_ids=("army-alpha:intercessor-unit-2",),
    )
    state.replace_reserve_state(cargo_reserve_state)
    before_battlefield = state.battlefield_state.to_payload() if state.battlefield_state else None

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=cargo_reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert ReservePlacementViolationCode.RESERVE_EMBARKED_CARGO_UNSUPPORTED in set(
        _violation_codes(result)
    )
    assert not result.is_valid
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.reserve_state_for_unit(cargo_reserve_state.unit_instance_id) == cargo_reserve_state


def test_replay_load_rejects_arrived_reserve_with_unaccounted_embarked_units() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    embarked_unit_id = "army-alpha:intercessor-unit-2"
    assert state.battlefield_state is not None
    parent_placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        embarked_unit_id
    ).with_added_unit_placement(parent_placement)
    state.replace_reserve_state(
        replace(
            reserve_state,
            embarked_unit_instance_ids=(embarked_unit_id,),
        ).mark_arrived(
            battle_round=3,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": None,
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": {"frames": []},
        },
    )

    with pytest.raises(GameLifecycleError, match="battlefield_state is invalid"):
        GameLifecycle.from_payload(payload)


def test_phase10p_reserve_destruction_application_marks_unplaced_models_removed() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    updated = apply_reserve_destruction_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        destruction=result,
    )
    unchanged = apply_reserve_destruction_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        destruction=resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=3,
            end_of_battle=False,
        ),
    )

    assert set(updated.removed_model_ids) == {
        model.model_instance_id for model in reserve_unit.own_models
    }
    assert unchanged is scenario.battlefield_state


def test_phase10p_reserve_type_guards_are_fail_fast() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    valid_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    transition_batch = valid_result.transition_batch
    assert transition_batch is not None
    violation = ReservePlacementViolation(
        violation_code=ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,
        message="enemy-distance",
    )

    with pytest.raises(GameLifecycleError, match="MissionPolicyDescriptor"):
        ReserveDestructionTimingPolicy.from_mission_policy(cast(MissionPolicyDescriptor, object()))
    with pytest.raises(GameLifecycleError, match="reserve_state must be a ReserveState"):
        ReserveDestructionTimingPolicy.core_rules_default().applies_to_reserve_state(
            cast(ReserveState, object())
        )
    with pytest.raises(GameLifecycleError, match="destruction_deadline_policy"):
        replace(
            reserve_state,
            destruction_deadline_policy=cast(ReserveDestructionTimingPolicy, object()),
        )
    with pytest.raises(GameLifecycleError, match="must not have destruction fields"):
        replace(reserve_state, destroyed_battle_round=3)
    with pytest.raises(GameLifecycleError, match="must not have destruction fields"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            destroyed_battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            post_arrival_restrictions=(
                ReservePostArrivalRestriction.NO_CHARGE,
                ReservePostArrivalRestriction.NO_CHARGE,
            ),
            restriction_battle_round=3,
        )
    arrived_state = valid_result.arrived_reserve_state()
    assert (
        arrived_state.clear_expired_post_arrival_restrictions(
            player_id="player-b",
            battle_round=2,
        )
        is arrived_state
    )
    assert (
        arrived_state.clear_expired_post_arrival_restrictions(
            player_id="player-b",
            battle_round=3,
        ).post_arrival_restrictions
        == ()
    )
    with pytest.raises(GameLifecycleError, match="battle_phase must be a string"):
        battle_phase_token(1)

    with pytest.raises(GameLifecycleError, match="ReserveArrivalCandidate reserve_state"):
        ReserveArrivalCandidate(
            reserve_state=cast(ReserveState, object()),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=RulesUnitPlacement.single(placement),
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="attempted_rules_unit_placement"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=cast(RulesUnitPlacement, object()),
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="placement unit drift"):
        ReserveArrivalCandidate(
            reserve_state=replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=RulesUnitPlacement.single(placement),
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="placement player drift"):
        ReserveArrivalCandidate(
            reserve_state=replace(reserve_state, player_id="player-b"),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=RulesUnitPlacement.single(placement),
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="qualifying_edges must be a tuple"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=RulesUnitPlacement.single(placement),
            qualifying_edges=cast(tuple[BattlefieldEdge, ...], [BattlefieldEdge.SOUTH]),
        )
    with pytest.raises(GameLifecycleError, match="qualifying_edges must not contain duplicates"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_rules_unit_placement=RulesUnitPlacement.single(placement),
            qualifying_edges=(BattlefieldEdge.SOUTH, BattlefieldEdge.SOUTH),
        )

    with pytest.raises(GameLifecycleError, match="ReinforcementPlacement candidate"):
        ReinforcementPlacement(
            candidate=cast(ReserveArrivalCandidate, object()),
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="coherency_result"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=cast(UnitCoherencyResult, object()),
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="transition_batch"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=cast(BattlefieldTransitionBatch, object()),
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="cannot have transitions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(violation,),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="requires transitions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=None,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="must apply all turn restrictions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=True,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )
    with pytest.raises(GameLifecycleError, match="restrictions require"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )

    with pytest.raises(GameLifecycleError, match="ReserveDestructionResult policy"):
        ReserveDestructionResult(
            policy=cast(ReserveDestructionTimingPolicy, object()),
            battle_round=3,
            end_of_battle=False,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=BattlefieldTransitionBatch(),
            updated_reserve_states=(),
        )
    with pytest.raises(GameLifecycleError, match="transition_batch"):
        ReserveDestructionResult(
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=3,
            end_of_battle=False,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=cast(BattlefieldTransitionBatch, object()),
            updated_reserve_states=(),
        )


def test_phase10p_reserve_resolution_type_guards_are_fail_fast() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    with pytest.raises(GameLifecycleError, match="scenario must be a scenario"):
        resolve_reserve_arrival(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="RulesetDescriptor"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="reserve_state must be ReserveState"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=cast(ReserveState, object()),
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="attempted_placement"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=cast(UnitPlacement, object()),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="battle_round must be at least 1"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=0,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_width_inches must be greater"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            battlefield_width_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_depth_inches must be a number"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            battlefield_depth_inches=True,
        )
    with pytest.raises(GameLifecycleError, match="terrain_features must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="terrain_features must contain"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="enemy_deployment_zones must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            enemy_deployment_zones=cast(tuple[DeploymentZone, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="enemy_deployment_zones must contain"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            enemy_deployment_zones=cast(tuple[DeploymentZone, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="large_model_exceptions must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            large_model_exceptions=cast(
                tuple[LargeModelReservePlacementException, ...],
                [large_exception],
            ),
        )
    with pytest.raises(GameLifecycleError, match="duplicate model IDs"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            large_model_exceptions=(large_exception, large_exception),
        )
    with pytest.raises(GameLifecycleError, match="strategic_reserve_rule"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            strategic_reserve_rule=cast(StrategicReserveRule, object()),
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )

    with pytest.raises(GameLifecycleError, match="reserve_states must be a tuple"):
        resolve_unarrived_reserve_destruction(
            reserve_states=cast(tuple[ReserveState, ...], [reserve_state]),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="ReserveState values"):
        resolve_unarrived_reserve_destruction(
            reserve_states=cast(tuple[ReserveState, ...], (object(),)),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="duplicate unit IDs"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state, reserve_state),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=cast(BattlefieldRuntimeState, object()),
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="policy must be"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=cast(ReserveDestructionTimingPolicy, object()),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=cast(tuple[ArmyDefinition, ...], [scenario.armies[0]]),
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="ArmyDefinition values"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=cast(tuple[ArmyDefinition, ...], (object(),)),
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="unknown unit"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        apply_reserve_destruction_to_battlefield(
            battlefield_state=cast(BattlefieldRuntimeState, object()),
            destruction=destruction,
        )
    with pytest.raises(GameLifecycleError, match="destruction must be"):
        apply_reserve_destruction_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            destruction=cast(ReserveDestructionResult, object()),
        )


def _battle_state_with_reserve(
    *,
    reserve_base_diameter_mm: float = 200.0,
    reserve_model_count: int = 1,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> tuple[GameState, BattlefieldScenario, ReserveState, UnitInstance]:
    config = _config(ruleset_descriptor=ruleset_descriptor or _ruleset())
    armies = _mustered_armies(config)
    armies = _with_reserve_unit_geometry(
        armies=armies,
        base_diameter_mm=reserve_base_diameter_mm,
        reserve_model_count=reserve_model_count,
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield_state)
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            (ruleset_descriptor or _ruleset()).mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, scenario, reserve_state, reserve_unit


def _aircraft_edge_departure_lifecycle() -> tuple[GameLifecycle, UnitInstance]:
    ruleset_descriptor = _ruleset()
    config = _config(ruleset_descriptor=ruleset_descriptor)
    armies = _mustered_armies(config)
    source_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    aircraft = replace(
        source_unit,
        own_models=(source_unit.own_models[0],),
        keywords=("AIRCRAFT", "FLY", "VEHICLE"),
    )
    armies = _with_replaced_unit(armies, aircraft)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-aircraft-battlefield",
        armies=armies,
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=aircraft.own_models[0].model_instance_id,
        pose=Pose.at(x=55.0, y=10.0, z=0.0, facing_degrees=0.0),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=ruleset_descriptor)
    decisions = DecisionController()
    unit_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert unit_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert (
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=unit_request,
            option_id=aircraft.unit_instance_id,
            result_id="phase10p-aircraft-select-move",
        )
        is None
    )
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    proposal_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase10p-aircraft-edge-departure",
        )
    )
    status = submit_handler_movement_proposal(
        handler=handler,
        state=state,
        decisions=decisions,
        request=proposal_request,
        result_id="phase10p-aircraft-edge-departure-proposal",
        unit_instance_id=aircraft.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_state(
            state,
            unit_instance_id=aircraft.unit_instance_id,
            dx=6.0,
        ),
    )
    assert status is None
    return (
        GameLifecycle(
            state=state,
            decision_controller=decisions,
            _movement_phase_handler=handler,
        ),
        aircraft,
    )


def _rapid_ingress_arrival_lifecycle() -> GameLifecycle:
    config = _config(ruleset_descriptor=_ruleset())
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
        reserve_model_count=1,
    )
    reserve_state = replace(
        reserve_state,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=state.mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    state.replace_reserve_state(reserve_state)
    state.battle_round = 2
    state.active_player_id = "player-b"
    decisions = DecisionController()
    decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": reserve_state.player_id,
            "unit_instance_id": reserve_state.unit_instance_id,
            "reserve_state": reserve_state.to_payload(),
        },
    )
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase10p-rapid-ingress-command-point",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    rapid_ingress = next(
        record
        for record in eleventh_edition_stratagem_catalog_records()
        if record.definition.stratagem_id == "rapid-ingress"
    )
    target_proposal = StratagemTargetProposal.for_request(
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=rapid_ingress,
    )
    target_request = _decision_request(
        request_stratagem_target_proposal(
            state=state,
            decisions=decisions,
            proposal_request=target_proposal,
        )
    )
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _movement_phase_handler=MovementPhaseHandler(ruleset_descriptor=_ruleset()),
    )
    placement_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase10p-rapid-ingress-target",
            request_id=target_request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=target_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                {
                    "proposal": target_proposal.with_binding(
                        StratagemTargetBinding(
                            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                            target_player_id="player-a",
                            target_unit_instance_id=reserve_state.unit_instance_id,
                        )
                    ).to_payload()
                }
            ),
        )
    )
    placement_request = _decision_request(placement_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    diameter_mm = reserve_unit.own_models[0].base_size.diameter_mm
    assert diameter_mm is not None
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=diameter_mm, x=15.0),
    )
    arrival_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase10p-rapid-ingress-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                PlacementProposalPayload(
                    proposal_request_id=placement_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    unit_instance_id=reserve_state.unit_instance_id,
                    placement_kind=proposal_request.placement_kinds[0],
                    attempted_placement=placement,
                ).to_payload()
            ),
        )
    )
    assert arrival_status.status_kind is not LifecycleStatusKind.INVALID, arrival_status
    return lifecycle


def _declared_reserve_arrival_lifecycle() -> GameLifecycle:
    ruleset_descriptor = _chapter_approved_ruleset()
    reserve_unit_id = "army-alpha:intercessor-unit-1"
    config = replace(
        _config(ruleset_descriptor=ruleset_descriptor),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id=reserve_unit_id,
                points=400,
                source_id="phase10p:declared-arrival:points",
            ),
        ),
    )
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    decisions = DecisionController()
    declaration_request = reserve_declaration_request_for_player(
        state=state,
        config=config,
        player_id="player-a",
    )
    decisions.request_decision(declaration_request)
    declaration_result = DecisionResult.for_request(
        result_id="phase10p-declared-arrival-declare",
        request=declaration_request,
        selected_option_id=f"declare_strategic_reserves:{reserve_unit_id}",
    )
    assert (
        invalid_reserve_declaration_status(
            state=state,
            config=config,
            request=declaration_request,
            result=declaration_result,
        )
        is None
    )
    decisions.submit_result(declaration_result)
    apply_reserve_declaration_decision(
        state=state,
        config=config,
        request=declaration_request,
        result=declaration_result,
        decisions=decisions,
    )

    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-declared-arrival-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(
        scenario.battlefield_state.without_unit_placement(reserve_unit_id)
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 3
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=3,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-2",),
        moved_unit_ids=("army-alpha:intercessor-unit-2",),
    )
    handler = MovementPhaseHandler(ruleset_descriptor=ruleset_descriptor)
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_unit_id,
            result_id="phase10p-declared-arrival-select",
        )
    )
    reserve_unit = armies[0].unit_by_id(reserve_unit_id)
    base_diameter_mm = reserve_unit.own_models[0].base_size.diameter_mm
    if base_diameter_mm is None:
        raise AssertionError("declared reserve fixture requires circular model bases")
    _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_reserve_placement(
            reserve_unit=reserve_unit,
            poses=tuple(
                Pose.at(
                    x=10.0 + 2.0 * index,
                    y=_base_radius_inches(base_diameter_mm),
                    z=0.0,
                    facing_degrees=0.0,
                )
                for index in range(len(reserve_unit.own_models))
            ),
        ),
        result_id="phase10p-declared-arrival-place",
    )
    return GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _movement_phase_handler=handler,
    )


def _set_movement_ready_for_reinforcements(
    *,
    state: GameState,
    battle_round: int,
) -> None:
    placed_unit_id = "army-alpha:intercessor-unit-2"
    state.battle_round = battle_round
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=(placed_unit_id,),
        moved_unit_ids=(placed_unit_id,),
    )


def _enter_reinforcements_choice(
    *,
    state: GameState,
    battle_round: int,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    _set_movement_ready_for_reinforcements(state=state, battle_round=battle_round)
    handler = MovementPhaseHandler(ruleset_descriptor=ruleset_descriptor or _ruleset())
    decisions = DecisionController()
    status = handler.begin_phase(state=state, decisions=decisions)
    return handler, decisions, _decision_request(status)


def _submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _submit_reserve_placement_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    reserve_unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: UnitPlacement,
    result_id: str,
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = (),
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=reserve_unit.unit_instance_id,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
        large_model_exceptions=large_model_exceptions,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, object]:
    for record in reversed(decisions.event_log.records):
        if record.event_type == event_type:
            payload = record.payload
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)
    raise AssertionError(f"event {event_type} not found")


def _with_reserve_unit_geometry(
    *,
    armies: tuple[ArmyDefinition, ...],
    base_diameter_mm: float,
    reserve_model_count: int,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        base_size = BaseSizeDefinition.circular(base_diameter_mm)
        updated_models = tuple(
            replace(
                model,
                base_size=base_size if index == 0 else model.base_size,
                geometry=(
                    ModelGeometry.from_base_size(
                        base_size,
                        geometry_source_id="phase10p-oversized-base",
                        keywords=reserve_unit.keywords,
                    )
                    if index == 0
                    else model.geometry
                ),
            )
            for index, model in enumerate(reserve_unit.own_models[:reserve_model_count])
        )
        updated_unit = replace(reserve_unit, own_models=updated_models)
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return tuple(updated_armies)


def _with_replaced_unit(
    armies: tuple[ArmyDefinition, ...],
    updated_unit: UnitInstance,
) -> tuple[ArmyDefinition, ...]:
    return tuple(
        replace(
            army,
            units=tuple(
                updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                for unit in army.units
            ),
        )
        if any(unit.unit_instance_id == updated_unit.unit_instance_id for unit in army.units)
        else army
        for army in armies
    )


def _single_model_reserve_placement(*, reserve_unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return _reserve_placement(reserve_unit=reserve_unit, poses=(pose,))


def _reserve_placement(*, reserve_unit: UnitInstance, poses: tuple[Pose, ...]) -> UnitPlacement:
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def _south_edge_touching_pose(*, base_diameter_mm: float, x: float) -> Pose:
    return Pose.at(
        x=x,
        y=_base_radius_inches(base_diameter_mm),
        z=0.0,
        facing_degrees=0.0,
    )


def _base_radius_inches(base_diameter_mm: float) -> float:
    return (base_diameter_mm / 25.4) / 2.0


def _with_model_pose(
    scenario: BattlefieldScenario,
    *,
    model_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    model_placement = scenario.battlefield_state.model_placement_by_id(model_instance_id)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        model_placement.unit_instance_id
    )
    updated_model_placements = tuple(
        replace(placement, pose=pose)
        if placement.model_instance_id == model_instance_id
        else placement
        for placement in unit_placement.model_placements
    )
    updated_unit_placement = replace(
        unit_placement,
        model_placements=updated_model_placements,
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_unit_placement),
    )


def _blocking_wall_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase10p-wall",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
    )


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _violation_codes(
    result: ReinforcementPlacement,
) -> tuple[ReservePlacementViolationCode, ...]:
    return tuple(sorted(violation.violation_code for violation in result.violations))


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase10p-test")


def _chapter_approved_ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase10p-ca-test"
    )


def _config(*, ruleset_descriptor: RulesetDescriptor) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10p-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    _unit_selection(unit_selection_id="intercessor-unit-1"),
                    _unit_selection(unit_selection_id="intercessor-unit-2"),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_unit_selection(unit_selection_id="intercessor-unit-3"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=unit_selections,
    )


def _unit_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
