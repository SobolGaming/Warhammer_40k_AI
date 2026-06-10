from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    create_empty_deployment_battlefield_state,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.prebattle import (
    SCOUT_MOVE_PROPOSAL_KIND,
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SELECT_REDEPLOY_UNIT_DECISION_TYPE,
    SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    PreBattlePlacementProposal,
    PreBattlePlacementProposalPayload,
    PreBattleProposalRequest,
    PreBattleProposalRequestPayload,
    PreBattleTimingWindowState,
    PreBattleViolationCode,
    ScoutAbilityInstance,
    ScoutMoveProposal,
    apply_scout_move,
    apply_scout_reserve_setup,
    dedicated_transport_scout_move_candidates_for_player,
    invalid_prebattle_proposal_status,
    prebattle_action_selection_request,
    prebattle_timing_state_for_state,
    prebattle_violation_code_from_token,
    resolve_prebattle_proposal,
    scout_distance_inches_for_model_ids,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    PreBattleActionRecord,
    prebattle_action_kind_from_token,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState, ReserveStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_phase16b_scout_duplicate_distance_selection_uses_lowest_shared_cap() -> None:
    model_ids = ("model-1", "model-2")

    assert (
        scout_distance_inches_for_model_ids(
            model_instance_ids=model_ids,
            ability_instances=(
                ScoutAbilityInstance(model_instance_id="model-1", distance_inches=6.0),
                ScoutAbilityInstance(model_instance_id="model-1", distance_inches=8.0),
                ScoutAbilityInstance(model_instance_id="model-2", distance_inches=6.0),
                ScoutAbilityInstance(model_instance_id="model-2", distance_inches=8.0),
            ),
        )
        == 8.0
    )
    assert (
        scout_distance_inches_for_model_ids(
            model_instance_ids=model_ids,
            ability_instances=(
                ScoutAbilityInstance(model_instance_id="model-1", distance_inches=6.0),
                ScoutAbilityInstance(model_instance_id="model-2", distance_inches=8.0),
            ),
        )
        == 6.0
    )
    with pytest.raises(GameLifecycleError, match="Every model must have a Scouts ability"):
        scout_distance_inches_for_model_ids(
            model_instance_ids=model_ids,
            ability_instances=(
                ScoutAbilityInstance(model_instance_id="model-1", distance_inches=8.0),
            ),
        )


def test_phase16b_redeploy_records_removal_and_placement_batches() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
        )
    )
    request = _decision_request(status)

    assert request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert "redeploy:army-beta:intercessor-unit-2" in _option_ids(request)

    proposal_status = _submit_option(
        lifecycle,
        request=request,
        option_id="redeploy:army-beta:intercessor-unit-2",
        result_id="phase16b-redeploy-select",
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE
    payload = _prebattle_placement_payload_for_request(
        lifecycle,
        request=proposal_request,
        pose_factory=lambda index: Pose.at(
            56.0 - ((index // 3) * 1.8),
            34.0 + ((index % 3) * 1.8),
            0.0,
            facing_degrees=180.0,
        ),
    )

    follow_up = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-redeploy-place",
            request_id=proposal_request.request_id,
            decision_type=proposal_request.decision_type,
            actor_id=proposal_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )

    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.TERMINAL,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    assert lifecycle.state is not None
    records = tuple(
        record
        for record in lifecycle.state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.REDEPLOY
    )
    assert len(records) == 1
    resolution = cast(dict[str, JsonValue], records[0].payload)
    removal_batch = cast(dict[str, JsonValue], resolution["removal_batch"])
    placement_batch = cast(dict[str, JsonValue], resolution["placement_batch"])
    assert len(cast(list[JsonValue], removal_batch["removals"])) == 5
    assert len(cast(list[JsonValue], placement_batch["placements"])) == 5
    assert cast(list[JsonValue], placement_batch["displacements"]) == []
    assert _event_types(lifecycle).count("prebattle_redeploy_completed") == 1
    payload_blob = json.dumps(records[0].to_payload(), sort_keys=True)
    assert "<" not in payload_blob
    assert "object at 0x" not in payload_blob


def test_phase16b_scout_move_rejects_endpoint_only_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    before_request_id = request.request_id
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()
    before_record_count = len(lifecycle.decision_controller.records)

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-endpoint-only-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0, endpoint_only=True),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.ENDPOINT_ONLY_PATH.value in _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == before_request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_valid_scout_move_records_displacements_without_movement_phase_state() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None

    follow_up = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-valid-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
    )

    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.TERMINAL,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    records = tuple(
        record
        for record in lifecycle.state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.SCOUT_MOVE
    )
    assert len(records) == 1
    resolution = cast(dict[str, JsonValue], records[0].payload)
    transition_batch = cast(dict[str, JsonValue], resolution["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    assert len(displacements) == 5
    assert {cast(str, record["displacement_kind"]) for record in displacements} == {
        ModelDisplacementKind.SCOUT_MOVE.value
    }
    assert lifecycle.state.movement_phase_state is not None
    scout_unit_id = "army-beta:intercessor-unit-2"
    assert scout_unit_id not in lifecycle.state.movement_phase_state.moved_unit_ids
    assert scout_unit_id not in lifecycle.state.movement_phase_state.selected_unit_ids
    assert lifecycle.state.advanced_unit_states == []
    assert lifecycle.state.fell_back_unit_states == []


def test_phase16b_malformed_scout_submission_rejects_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    before_record_count = len(lifecycle.decision_controller.records)
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout Move test request requires scout_distance_inches.")
    proposal = ScoutMoveProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
        game_id=request_context.game_id,
        ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id=request_context.source_rule_id,
        scout_distance_inches=request_context.scout_distance_inches,
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
        context=request_context.context,
    )
    payload = validate_json_value(proposal.to_payload())
    if not isinstance(payload, dict):
        raise GameLifecycleError("Scout Move proposal test payload must be an object.")
    payload.pop("witness")

    invalid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase16b-malformed-scout",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "malformed_prebattle_proposal"
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16b_scout_move_requires_more_than_eight_from_enemy() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    _move_unit_placement(
        lifecycle.state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        dx=47.0,
        dy=-21.0,
    )
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()

    invalid_status = _submit_scout_move(
        lifecycle,
        request=request,
        result_id="phase16b-too-close-scout",
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_proposal_invalid"
    assert PreBattleViolationCode.SCOUT_ENEMY_DISTANCE.value in _violation_codes(invalid_status)
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload


def test_phase16b_completion_options_record_prebattle_action_records() -> None:
    redeploy_catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "REDEPLOY")}
    )
    redeploy_lifecycle, redeploy_status = _advance_after_deployments(
        _config(
            catalog=redeploy_catalog,
            player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),),
        )
    )
    redeploy_request = _decision_request(redeploy_status)
    assert redeploy_request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    _submit_option(
        redeploy_lifecycle,
        request=redeploy_request,
        option_id="complete_redeploys",
        result_id="phase16b-complete-redeploys",
    )
    assert redeploy_lifecycle.state is not None
    assert any(
        record.action_kind is PreBattleActionKind.COMPLETE_REDEPLOYS
        for record in redeploy_lifecycle.state.prebattle_action_records
    )

    prebattle_lifecycle, prebattle_status = _advance_after_deployments(_scouts_config())
    prebattle_request = _decision_request(prebattle_status)
    assert prebattle_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    _submit_option(
        prebattle_lifecycle,
        request=prebattle_request,
        option_id="complete_prebattle_actions",
        result_id="phase16b-complete-prebattle",
    )
    assert prebattle_lifecycle.state is not None
    assert any(
        record.action_kind is PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS
        for record in prebattle_lifecycle.state.prebattle_action_records
    )


def test_phase16b_scout_reserve_setup_uses_structured_proposal_and_validation() -> None:
    state = _manual_prebattle_state(
        catalog=_catalog_with_datasheet_keywords(
            {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
        )
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )
    request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id="player-b",
    )
    option = _option_for_prefix(request, "scout_reserve_setup:")
    selection_result = DecisionResult.for_request(
        result_id="phase16b-scout-reserve-select",
        request=request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        selection_request=request,
        result=selection_result,
    )
    proposal = PreBattlePlacementProposal.from_payload(
        cast(
            PreBattlePlacementProposalPayload,
            _prebattle_placement_payload(
                state=state,
                request_context=proposal_request,
                pose_factory=lambda index: Pose.at(
                    57.0 - ((index // 3) * 1.8),
                    32.0 + ((index % 3) * 1.8),
                    0.0,
                    facing_degrees=180.0,
                ),
            ),
        )
    )

    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=proposal_request,
        proposal=proposal,
    )
    assert resolution.is_valid
    assert resolution.transition_batch is not None
    assert len(resolution.transition_batch.placements) == 5

    invalid_proposal = replace(
        proposal,
        model_placements=tuple(
            placement.with_pose(Pose.at(28.0, placement.pose.position.y, 0.0))
            for placement in proposal.model_placements
        ),
    )
    invalid_resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=proposal_request,
        proposal=invalid_proposal,
    )
    assert not invalid_resolution.is_valid
    assert PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION in {
        violation.violation_code for violation in invalid_resolution.violations
    }


def test_phase16b_scout_reserve_setup_apply_records_arrival_action_and_event() -> None:
    state = _manual_prebattle_state(
        catalog=_catalog_with_datasheet_keywords(
            {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
        )
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )
    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id="player-b",
    )
    option = _option_for_prefix(selection_request, "scout_reserve_setup:")
    selection_result = DecisionResult.for_request(
        result_id="phase16b-apply-scout-reserve-select",
        request=selection_request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        selection_request=selection_request,
        result=selection_result,
    )
    request = proposal_request.to_decision_request()
    result = DecisionResult(
        result_id="phase16b-apply-scout-reserve-place",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=_prebattle_placement_payload(
            state=state,
            request_context=proposal_request,
            pose_factory=lambda index: Pose.at(
                57.0 - ((index // 3) * 1.8),
                32.0 + ((index % 3) * 1.8),
                0.0,
                facing_degrees=180.0,
            ),
        ),
    )
    decisions = DecisionController()

    resolution = apply_scout_reserve_setup(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
    )

    assert resolution.is_valid
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    reserve_state = state.reserve_state_for_unit("army-beta:intercessor-unit-2")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.ARRIVED
    assert reserve_state.arrived_phase == SetupStep.RESOLVE_PREBATTLE_ACTIONS.value
    records = tuple(
        record
        for record in state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.SCOUT_RESERVE_SETUP
    )
    assert len(records) == 1
    assert (
        records[0].to_payload()
        == PreBattleActionRecord.from_payload(records[0].to_payload()).to_payload()
    )
    assert "prebattle_scout_reserve_setup_completed" in (
        event.event_type for event in decisions.event_log.records
    )


def test_phase16b_prebattle_timing_and_proposal_payloads_are_replay_safe() -> None:
    state = _manual_prebattle_state(
        catalog=_catalog_with_datasheet_keywords(
            {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
        )
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )

    timing = prebattle_timing_state_for_state(state)
    assert timing.next_player_id == "player-b"
    assert timing.to_payload()["available_action_count_by_player"] == {
        "player-a": 0,
        "player-b": 1,
    }
    with pytest.raises(GameLifecycleError, match="requires a pre-battle step"):
        PreBattleTimingWindowState(
            setup_step=SetupStep.DEPLOY_ARMIES,
            next_player_id=None,
            available_action_count_by_player={},
            completed_player_ids=(),
        )

    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id="player-b",
    )
    selection_result = DecisionResult.for_request(
        result_id="phase16b-payload-scout-reserve-select",
        request=selection_request,
        selected_option_id=_option_for_prefix(
            selection_request,
            "scout_reserve_setup:",
        ).option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        selection_request=selection_request,
        result=selection_result,
    )
    payload = proposal_request.to_payload()
    assert PreBattleProposalRequest.from_payload(payload) == proposal_request
    request = proposal_request.to_decision_request()
    assert (
        PreBattleProposalRequest.from_decision_request_payload(request.payload) == proposal_request
    )
    request_payload_json = json.dumps(request.payload, sort_keys=True)
    assert "<" not in request_payload_json
    assert "object at 0x" not in request_payload_json

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        PreBattleProposalRequest.from_decision_request_payload(())
    with pytest.raises(GameLifecycleError, match="payload missing request"):
        PreBattleProposalRequest.from_decision_request_payload({})
    bad_payload = dict(payload)
    bad_payload["legal_deployment_zones"] = []
    with pytest.raises(GameLifecycleError, match="requires deployment zones"):
        PreBattleProposalRequest.from_payload(cast(PreBattleProposalRequestPayload, bad_payload))


def test_phase16b_scout_move_request_drift_rejects_before_queue_pop() -> None:
    lifecycle, status = _advance_after_deployments(_scouts_config())
    request = _select_scout_move(lifecycle, _decision_request(status))
    assert lifecycle.state is not None
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout Move test request requires scout_distance_inches.")
    proposal = ScoutMoveProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=request_context.proposal_kind,
        game_id="phase16b-drifted-game",
        ruleset_descriptor_hash="phase16b-drifted-ruleset",
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id="phase16b-drifted-source",
        scout_distance_inches=request_context.scout_distance_inches + 1.0,
        witness=_scout_move_witness(lifecycle.state, request=request, dx=-3.0),
        context=request_context.context,
    )
    result = DecisionResult(
        result_id="phase16b-drifted-scout",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(proposal.to_payload()),
    )

    invalid_status = invalid_prebattle_proposal_status(
        state=lifecycle.state,
        request=request,
        result=result,
        ruleset_descriptor=_ruleset(),
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(invalid_status) == "prebattle_request_drift"
    assert {
        PreBattleViolationCode.GAME_ID_DRIFT.value,
        PreBattleViolationCode.RULESET_HASH_DRIFT.value,
        PreBattleViolationCode.SOURCE_RULE_DRIFT.value,
    } <= _violation_codes(invalid_status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_phase16b_prebattle_action_record_round_trips_and_rejects_invalid_tokens() -> None:
    record = PreBattleActionRecord(
        action_id="prebattle-action-000001",
        game_id="phase16b-game",
        player_id="player-a",
        setup_step=SetupStep.REDEPLOY_UNITS,
        action_kind=PreBattleActionKind.REDEPLOY,
        unit_instance_id="army-alpha:intercessor-unit-1",
        source_rule_id="core_rules:redeploy",
        request_id="decision-request-000001",
        result_id="decision-result-000001",
        payload={"is_valid": True},
    )

    assert PreBattleActionRecord.from_payload(record.to_payload()) == record
    assert (
        prebattle_action_kind_from_token(PreBattleActionKind.REDEPLOY)
        is PreBattleActionKind.REDEPLOY
    )
    assert (
        prebattle_violation_code_from_token(PreBattleViolationCode.UNIT_NOT_ELIGIBLE)
        is PreBattleViolationCode.UNIT_NOT_ELIGIBLE
    )
    scout_instance = ScoutAbilityInstance.from_payload(
        {
            "model_instance_id": "army-alpha:intercessor-unit-1:model-1",
            "distance_inches": 6,
            "source_id": "core_rules:scouts",
        }
    )
    assert scout_instance.to_payload()["distance_inches"] == 6.0

    with pytest.raises(GameLifecycleError, match="token must be a string"):
        prebattle_action_kind_from_token(3)
    with pytest.raises(GameLifecycleError, match="Unsupported PreBattleActionKind"):
        prebattle_action_kind_from_token("unsupported-action")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        prebattle_violation_code_from_token(None)
    with pytest.raises(GameLifecycleError, match="Unsupported PreBattleViolationCode"):
        prebattle_violation_code_from_token("unsupported-violation")

    bad_step_payload = record.to_payload()
    bad_step_payload["setup_step"] = cast(str, 3)
    with pytest.raises(GameLifecycleError, match="setup_step token must be a string"):
        PreBattleActionRecord.from_payload(bad_step_payload)

    bad_step_payload = record.to_payload()
    bad_step_payload["setup_step"] = "unsupported-step"
    with pytest.raises(GameLifecycleError, match="Unsupported setup step token"):
        PreBattleActionRecord.from_payload(bad_step_payload)

    with pytest.raises(GameLifecycleError, match="action_id must be a string"):
        PreBattleActionRecord(
            action_id=cast(str, 3),
            game_id="phase16b-game",
            player_id="player-a",
            setup_step=SetupStep.REDEPLOY_UNITS,
            action_kind=PreBattleActionKind.REDEPLOY,
            source_rule_id="core_rules:redeploy",
            request_id="decision-request-000001",
            result_id="decision-result-000001",
        )
    with pytest.raises(GameLifecycleError, match="action_id must not be empty"):
        PreBattleActionRecord(
            action_id=" ",
            game_id="phase16b-game",
            player_id="player-a",
            setup_step=SetupStep.REDEPLOY_UNITS,
            action_kind=PreBattleActionKind.REDEPLOY,
            source_rule_id="core_rules:redeploy",
            request_id="decision-request-000001",
            result_id="decision-result-000001",
        )
    with pytest.raises(GameLifecycleError, match="must be a positive finite number"):
        ScoutAbilityInstance(
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            distance_inches=0,
            source_id="core_rules:scouts",
        )


def test_phase16b_dedicated_transport_with_non_scout_cargo_is_ineligible() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {"core-transport": ("Transport", "Vehicle", "DEDICATED_TRANSPORT")}
    )
    state = _manual_prebattle_state(
        catalog=catalog,
        player_b_unit_selections=(
            _unit_selection(unit_selection_id="intercessor-unit-2"),
            _unit_selection(
                unit_selection_id="transport-unit-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id="army-beta:transport-unit-1",
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("Infantry",),
            ),
            embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            disembarked_this_phase_unit_instance_ids=(),
        )
    )
    _place_unit(
        state,
        unit_instance_id="army-beta:transport-unit-1",
        pose_factory=lambda _index: Pose.at(55.0, 20.0, 0.0, facing_degrees=180.0),
    )

    assert (
        dedicated_transport_scout_move_candidates_for_player(
            state=state,
            player_id="player-b",
        )
        == ()
    )


def test_phase16b_dedicated_transport_scout_move_uses_cargo_scouts_and_records_action() -> None:
    catalog = _catalog_with_datasheet_keywords(
        {
            "core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS"),
            "core-transport": ("Transport", "Vehicle", "DEDICATED_TRANSPORT"),
        }
    )
    state = _manual_prebattle_state(
        catalog=catalog,
        player_b_unit_selections=(
            _unit_selection(unit_selection_id="intercessor-unit-2"),
            _unit_selection(
                unit_selection_id="transport-unit-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id="army-beta:transport-unit-1",
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("Infantry",),
            ),
            embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=("army-beta:intercessor-unit-2",),
            disembarked_this_phase_unit_instance_ids=(),
        )
    )
    _place_unit(
        state,
        unit_instance_id="army-beta:transport-unit-1",
        pose_factory=lambda _index: Pose.at(55.0, 20.0, 0.0, facing_degrees=180.0),
    )
    selection_request = prebattle_action_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id="player-b",
    )
    option = _option_for_prefix(selection_request, "dedicated_transport_scout_move:")
    selection_result = DecisionResult.for_request(
        result_id="phase16b-dedicated-transport-select",
        request=selection_request,
        selected_option_id=option.option_id,
    )
    proposal_request = _proposal_request_from_selection_payload(
        state=state,
        selection_request=selection_request,
        result=selection_result,
    )
    assert proposal_request.action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE
    assert proposal_request.scout_distance_inches == 6.0
    if proposal_request.scout_distance_inches is None:
        raise GameLifecycleError("Dedicated Transport Scout Move requires scout_distance_inches.")
    request = proposal_request.to_decision_request()
    result = DecisionResult(
        result_id="phase16b-dedicated-transport-scout",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            ScoutMoveProposal(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                game_id=proposal_request.game_id,
                ruleset_descriptor_hash=proposal_request.ruleset_descriptor_hash,
                setup_step=proposal_request.setup_step,
                player_id=proposal_request.player_id,
                unit_instance_id=proposal_request.unit_instance_id,
                action_kind=proposal_request.action_kind,
                source_rule_id=proposal_request.source_rule_id,
                scout_distance_inches=proposal_request.scout_distance_inches,
                witness=_scout_move_witness(state, request=request),
                context=proposal_request.context,
            ).to_payload()
        ),
    )
    decisions = DecisionController()

    resolution = apply_scout_move(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
    )

    assert resolution.is_valid
    records = tuple(
        record
        for record in state.prebattle_action_records
        if record.action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE
    )
    assert len(records) == 1
    assert records[0].unit_instance_id == "army-beta:transport-unit-1"
    assert "prebattle_scout_move_completed" in (
        event.event_type for event in decisions.event_log.records
    )


def _advance_after_deployments(config: GameConfig) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16b-deploy",
    )
    return lifecycle, status


def _advance_to_first_deployment_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_option(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16b-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_option(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16b-secondary-player-b",
    )
    assert _decision_request(deployment_status).decision_type == (
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    )
    return lifecycle, deployment_status


def _select_scout_move(
    lifecycle: GameLifecycle,
    selection_request: DecisionRequest,
) -> DecisionRequest:
    assert selection_request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
    option = _option_for_prefix(selection_request, "scout_move:")
    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=option.option_id,
        result_id="phase16b-scout-select",
    )
    proposal_request = _decision_request(status)
    assert proposal_request.decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE
    return proposal_request


def _submit_scout_move(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    witness: PathWitness,
) -> LifecycleStatus:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout Move test request requires scout_distance_inches.")
    proposal = ScoutMoveProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
        game_id=request_context.game_id,
        ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id=request_context.source_rule_id,
        scout_distance_inches=request_context.scout_distance_inches,
        witness=witness,
        context=request_context.context,
    )
    payload = validate_json_value(proposal.to_payload())
    if not isinstance(payload, dict):
        raise GameLifecycleError("Scout Move proposal test payload must be an object.")
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )


def _scout_move_witness(
    state: GameState,
    *,
    request: DecisionRequest,
    dx: float = 0.0,
    dy: float = 0.0,
    endpoint_only: bool = False,
) -> PathWitness:
    if state.battlefield_state is None:
        raise GameLifecycleError("Scout Move witness test helper requires battlefield_state.")
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    unit_placement = state.battlefield_state.unit_placement_by_id(request_context.unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        poses: tuple[Pose, ...]
        if endpoint_only:
            poses = (start, end)
        else:
            poses = (
                start,
                Pose.at(
                    start.position.x + (dx / 2.0),
                    start.position.y + (dy / 2.0),
                    start.position.z,
                    facing_degrees=start.facing.degrees,
                ),
                end,
            )
        model_paths.append((placement.model_instance_id, poses))
    return PathWitness.for_paths(tuple(model_paths))


def _prebattle_placement_payload_for_request(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    pose_factory: _PoseFactory,
) -> dict[str, JsonValue]:
    if lifecycle.state is None:
        raise GameLifecycleError("Pre-battle placement helper requires GameState.")
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    return _prebattle_placement_payload(
        state=lifecycle.state,
        request_context=request_context,
        pose_factory=pose_factory,
    )


type _PoseFactory = Callable[[int], Pose]


def _prebattle_placement_payload(
    *,
    state: GameState,
    request_context: PreBattleProposalRequest,
    pose_factory: _PoseFactory,
) -> dict[str, JsonValue]:
    placements: list[ModelPlacement] = []
    for index, model_instance_id in enumerate(request_context.model_instance_ids):
        army_id, player_id, unit_instance_id = _model_source_for_id(
            state=state,
            model_instance_id=model_instance_id,
        )
        placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                model_instance_id=model_instance_id,
                pose=pose_factory(index),
            )
        )
    if request_context.placement_kind is None:
        raise GameLifecycleError("Pre-battle placement request requires placement_kind.")
    proposal = PreBattlePlacementProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=request_context.proposal_kind,
        game_id=request_context.game_id,
        ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
        setup_step=request_context.setup_step,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        action_kind=request_context.action_kind,
        source_rule_id=request_context.source_rule_id,
        placement_kind=request_context.placement_kind,
        model_placements=tuple(placements),
        context=request_context.context,
    )
    payload = validate_json_value(proposal.to_payload())
    if not isinstance(payload, dict):
        raise GameLifecycleError("Pre-battle placement proposal test payload must be an object.")
    return payload


def _proposal_request_from_selection_payload(
    *,
    state: GameState,
    selection_request: DecisionRequest,
    result: DecisionResult,
) -> PreBattleProposalRequest:
    from warhammer40k_core.engine.prebattle import prebattle_proposal_request_from_selection

    return prebattle_proposal_request_from_selection(
        state=state,
        ruleset_descriptor=_ruleset(),
        selection_request=selection_request,
        result=result,
    )


def _manual_prebattle_state(
    *,
    catalog: ArmyCatalog,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
) -> GameState:
    config = _config(
        catalog=catalog,
        player_b_unit_selections=player_b_unit_selections,
    )
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=catalog, request=request))
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    while state.current_setup_step is not SetupStep.RESOLVE_PREBATTLE_ACTIONS:
        state.complete_current_setup_step()
    return state


def _place_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    pose_factory: _PoseFactory,
) -> None:
    if state.battlefield_state is None:
        raise GameLifecycleError("Placement helper requires battlefield_state.")
    placements: list[ModelPlacement] = []
    army, unit = _unit_source_for_id(state=state, unit_instance_id=unit_instance_id)
    for index, model in enumerate(unit.own_models):
        placements.append(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose_factory(index),
            )
        )
    placement = UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit_instance_id,
        model_placements=tuple(placements),
    )
    state.replace_battlefield_state(state.battlefield_state.with_added_unit_placement(placement))


def _move_unit_placement(
    state: GameState,
    *,
    unit_instance_id: str,
    dx: float,
    dy: float = 0.0,
) -> None:
    if state.battlefield_state is None:
        raise GameLifecycleError("Move placement helper requires battlefield_state.")
    current = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    moved = tuple(
        placement.with_pose(
            Pose.at(
                placement.pose.position.x + dx,
                placement.pose.position.y + dy,
                placement.pose.position.z,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
        for placement in current.model_placements
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(current.with_model_placements(moved))
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _invalid_reason(status: LifecycleStatus) -> str:
    assert isinstance(status.payload, dict)
    value = status.payload["invalid_reason"]
    assert type(value) is str
    return value


def _violation_codes(status: LifecycleStatus) -> set[str]:
    assert isinstance(status.payload, dict)
    violations = status.payload["violations"]
    assert isinstance(violations, list)
    codes: set[str] = set()
    for violation in violations:
        assert isinstance(violation, dict)
        code = violation["violation_code"]
        assert type(code) is str
        codes.add(code)
    return codes


def _option_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(option.option_id for option in request.options)


def _option_for_prefix(request: DecisionRequest, prefix: str) -> DecisionOption:
    for option in request.options:
        if option.option_id.startswith(prefix):
            return option
    raise GameLifecycleError("Expected pre-battle option was not available.")


def _event_types(lifecycle: GameLifecycle) -> list[str]:
    return [event.event_type for event in lifecycle.decision_controller.event_log.records]


def _scouts_config() -> GameConfig:
    return _config(
        catalog=_catalog_with_datasheet_keywords(
            {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
        ),
        player_a_unit_selections=(_vehicle_unit_selection(unit_selection_id="intercessor-unit-1"),),
    )


def _config(
    *,
    catalog: ArmyCatalog | None = None,
    player_a_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id="phase16b-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=resolved_catalog,
        army_muster_requests=_army_muster_requests(
            resolved_catalog,
            player_a_unit_selections=player_a_unit_selections,
            player_b_unit_selections=player_b_unit_selections,
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16b-test")


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_requests(
    catalog: ArmyCatalog,
    *,
    player_a_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
) -> tuple[ArmyMusterRequest, ...]:
    return (
        _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                (_unit_selection(unit_selection_id="intercessor-unit-1"),)
                if player_a_unit_selections is None
                else player_a_unit_selections
            ),
        ),
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                (_unit_selection(unit_selection_id="intercessor-unit-2"),)
                if player_b_unit_selections is None
                else player_b_unit_selections
            ),
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
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _vehicle_unit_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-vehicle-monster",
        model_profile_id="core-vehicle-monster",
        model_count=1,
    )


def _catalog_with_datasheet_keywords(mapping: dict[str, tuple[str, ...]]) -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets: list[DatasheetDefinition] = []
    for datasheet in base.datasheets:
        keywords = mapping.get(datasheet.datasheet_id)
        datasheets.append(
            replace(
                datasheet,
                keywords=DatasheetKeywordSet(
                    keywords=datasheet.keywords.keywords if keywords is None else keywords,
                    faction_keywords=datasheet.keywords.faction_keywords,
                ),
            )
        )
    return replace(base, datasheets=tuple(datasheets))


def _model_source_for_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[str, str, str]:
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == model_instance_id:
                    return army.army_id, army.player_id, unit.unit_instance_id
    raise GameLifecycleError("Pre-battle proposal model_instance_id is not mustered.")


def _unit_source_for_id(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[ArmyDefinition, UnitInstance]:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return army, unit
    raise GameLifecycleError("Unit was not mustered.")
