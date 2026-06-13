from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_MOVE_PENDING_STATUS,
    CHARGE_NO_MOVE_POSSIBLE_STATUS,
    CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,
    ChargeDistanceState,
    ChargeRollRequest,
    ChargeRollResult,
    ChargeRollResultPayload,
    ChargeTargetCandidate,
    ChargeTargetCandidatePayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargeEndpointWitness,
    ChargeMoveProposal,
    ChargeMoveResolution,
    ChargePhaseState,
    ChargingUnitSelection,
    resolve_charge_move,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.unit_coherency import MovementRollbackRecord, UnitCoherencyResult
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_charging_unit_selection_rolls_immediately_and_uses_lifecycle_records() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-records",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert selection_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert selection_request.actor_id == "player-a"
    assert {
        units["intercessor-1"].unit_instance_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    } == {option.option_id for option in selection_request.options}

    unit_option = selection_request.option_by_id(units["intercessor-1"].unit_instance_id)
    unit_payload = cast(dict[str, object], unit_option.payload)
    eligibility_context = cast(dict[str, object], unit_payload["eligibility_context"])
    target_candidates = cast(list[dict[str, object]], eligibility_context["target_candidates"])
    assert target_candidates[0]["target_unit_instance_id"] == units["enemy"].unit_instance_id
    assert target_candidates[0]["is_legal"] is True

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-select-charger",
    )
    event_types = [event.event_type for event in lifecycle.decision_controller.event_log.records]
    roll_result = _roll_result_from_event(lifecycle, "charge_roll_resolved")
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.phase == BattlePhase.CHARGE.value
    assert proposal.movement_phase_action == "charge_move"
    assert proposal.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert cast(dict[str, object], proposal.context)["movement_mode"] == "charge"
    assert [record.request.decision_type for record in lifecycle.decision_controller.records] == [
        SELECT_CHARGING_UNIT_DECISION_TYPE,
    ]
    assert "charging_unit_selected" in event_types
    assert "charge_declaration_accepted" not in event_types
    assert "charge_roll_resolved" in event_types
    assert "charge_move_required" in event_types
    assert "charge_move_proposal_requested" in event_types
    assert roll_result.request.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert roll_result.move_available is True
    assert units["enemy"].unit_instance_id in roll_result.reachable_target_distances_inches
    assert 2 <= roll_result.value <= 12
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload


def test_successful_charge_roll_creates_phase15b_movement_boundary() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-success-submit",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_move_required")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None
    assert after_state.charge_phase_state is not None
    pending_distance_state = after_state.charge_phase_state.move_pending_distance_state()
    repeated_status = lifecycle.advance_until_decision_or_terminal()
    status_payload = cast(dict[str, object], status.payload)
    repeated_payload = cast(dict[str, object], repeated_status.payload)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert status_payload["phase_body_status"] == "charge_move_proposal_required"
    assert status_payload["reachable_target_unit_instance_ids"] == [units["enemy"].unit_instance_id]
    assert repeated_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert repeated_status.decision_request == status.decision_request
    assert repeated_payload["pending_request_id"] == status.decision_request.request_id
    assert roll_result.move_available is True
    assert roll_result.status == CHARGE_MOVE_PENDING_STATUS
    assert pending_distance_state is not None
    assert pending_distance_state.roll_result == roll_result
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert _event_payloads(lifecycle, "charge_no_move_possible") == ()
    assert all(
        not _payload_has_displacements(cast(dict[str, object], event.payload))
        for event in lifecycle.decision_controller.event_log.records
    )


def test_charge_roll_with_no_reachable_targets_resolves_without_model_movement() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(27.0, 20.0), model_count=5),
        game_id="phase15a-no-move-charge",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-no-move-submit",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_no_move_possible")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert after_state.current_battle_phase is BattlePhase.MOVEMENT
    assert after_state.charge_phase_state is None
    assert roll_result.move_available is False
    assert roll_result.status == CHARGE_NO_MOVE_POSSIBLE_STATUS
    assert roll_result.reachable_target_distances_inches == {}
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert _event_payloads(lifecycle, "charge_move_required") == ()
    assert all(
        not _payload_has_displacements(cast(dict[str, object], event.payload))
        for event in lifecycle.decision_controller.event_log.records
    )


def test_phase15b_charge_move_proposal_applies_witness_records_displacements_and_fights_first() -> (
    None
):
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    target_unit_id = units["enemy"].unit_instance_id
    witness = _charge_path_witness_for_unit(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        dx=3.0,
    )

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-success",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(target_unit_id,),
            witness=witness,
        ),
    )
    completed = _last_event_payload(lifecycle, "charge_move_completed")
    transition_batch = cast(dict[str, object], completed["transition_batch"])
    displacements = cast(list[dict[str, object]], transition_batch["displacements"])
    endpoint_witness = cast(dict[str, object], completed["endpoint_witness"])
    persisting_effect = cast(dict[str, object], completed["persisting_effect"])
    effect_payload = cast(dict[str, object], persisting_effect["effect_payload"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    fight_movement_request = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert fight_movement_request.proposal_kind is ProposalKind.PILE_IN
    assert after_state.current_battle_phase is BattlePhase.FIGHT
    assert after_state.charge_phase_state is None
    assert after_state.battlefield_state.to_payload() != before_battlefield
    assert len(displacements) == len(units["intercessor-1"].own_models)
    assert {record["displacement_kind"] for record in displacements} == {"charge_move"}
    assert {record["source_phase"] for record in displacements} == {"charge"}
    assert {record["source_step"] for record in displacements} == {"charge_move"}
    assert all(record["path_witness"] is not None for record in displacements)
    assert endpoint_witness["engaged_target_unit_instance_ids"] == [target_unit_id]
    assert endpoint_witness["preferred_distance_target_unit_instance_ids"] == [target_unit_id]
    assert endpoint_witness["non_target_engaged_unit_instance_ids"] == []
    assert persisting_effect["started_phase"] == "charge"
    assert cast(dict[str, object], persisting_effect["expiration"])["expiration_kind"] == "end_turn"
    assert effect_payload["effect_kind"] == "charge_grants_fights_first"
    assert after_state.persisting_effects_for_unit(units["intercessor-1"].unit_instance_id)
    assert [record.request.decision_type for record in lifecycle.decision_controller.records] == [
        SELECT_CHARGING_UNIT_DECISION_TYPE,
        MOVEMENT_PROPOSAL_DECISION_TYPE,
    ]
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15b_charge_move_no_move_choice_records_decline_without_mutation() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-no-move",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-no-move",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(),
            witness=None,
        ),
    )
    declined = _last_event_payload(lifecycle, "charge_move_declined")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert after_state.current_battle_phase is BattlePhase.MOVEMENT
    assert after_state.charge_phase_state is None
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert after_state.persisting_effects_for_unit(units["intercessor-1"].unit_instance_id) == ()
    assert declined["phase_body_status"] == "charge_move_declined"
    assert _event_payloads(lifecycle, "charge_move_completed") == ()
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15f_charge_completion_gate_runs_for_both_players() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15f-charge-both-players",
    )

    player_a_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_a_status = _submit_option(
        lifecycle,
        request=player_a_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15f-player-a-complete-charge",
    )
    state = _state(lifecycle)
    player_a_movement_request = _decision_request(player_a_status)
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.active_player_id == "player-b"
    assert state.charge_phase_state is None
    assert player_a_movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    lifecycle.decision_controller.queue.remove_by_id(player_a_movement_request.request_id)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.active_player_id = "player-b"

    player_b_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_b_status = _submit_option(
        lifecycle,
        request=player_b_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15f-player-b-complete-charge",
    )
    player_b_completed = _last_event_payload(lifecycle, "charge_phase_completed")

    assert player_b_request.actor_id == "player-b"
    assert units["enemy"].unit_instance_id in {
        option.option_id for option in player_b_request.options
    }
    assert _decision_request(player_b_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert player_b_completed["active_player_id"] == "player-b"
    assert len(_event_payloads(lifecycle, "charge_phase_completed")) == 2
    assert [record.request.decision_type for record in lifecycle.decision_controller.records].count(
        SELECT_CHARGING_UNIT_DECISION_TYPE
    ) == 2


def test_phase15b_charge_target_without_witness_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-missing-witness",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-missing-witness",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
            witness=None,
        ),
    )
    invalid = _last_event_payload(lifecycle, "charge_move_proposal_invalid")
    proposal_validation = cast(dict[str, object], invalid["proposal_validation"])
    violations = cast(list[dict[str, object]], proposal_validation["violations"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (proposal_request,)
    assert len(lifecycle.decision_controller.records) == 1
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert violations[0]["violation_code"] == "charge_move_witness_required"
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15b_endpoint_only_charge_witness_records_rejected_attempt_and_retries() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-endpoint-only",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=units["intercessor-1"].unit_instance_id,
                dx=3.0,
                endpoint_only=True,
            ),
        ),
    )
    invalid = _last_event_payload(lifecycle, "charge_move_invalid")
    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["violation_code"] == "endpoint_only_path"
    assert invalid["violation_code"] == "endpoint_only_path"
    assert retry_request.request_id != proposal_request.request_id
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert len(lifecycle.decision_controller.records) == 2
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert len(_event_payloads(lifecycle, "charge_move_proposal_requested")) == 2


def test_phase15b_charge_move_rejects_non_target_engagement_without_mutation() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        enemy_unit_ids=("enemy-1", "enemy-2"),
        enemy_origins={
            "enemy-1": Pose.at(20.0, 20.0, facing_degrees=180.0),
            "enemy-2": Pose.at(18.6, 22.1, facing_degrees=180.0),
        },
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-non-target-engagement",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy-1"].unit_instance_id,),
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=units["intercessor-1"].unit_instance_id,
                dx=3.0,
            ),
        ),
    )
    invalid = _last_event_payload(lifecycle, "charge_move_invalid")
    endpoint_witness = cast(dict[str, object], invalid["endpoint_witness"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert invalid["violation_code"] == "charge_non_target_engaged"
    assert endpoint_witness["non_target_engaged_unit_instance_ids"] == [
        units["enemy-2"].unit_instance_id
    ]
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert len(lifecycle.decision_controller.records) == 2
    assert lifecycle.decision_controller.queue.pending_requests[0].request_id != (
        proposal_request.request_id
    )


def test_phase15b_charge_movement_legality_applies_fly_transit_policy() -> None:
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15b-fly-test"
    )
    walking_context = MovementLegalityContext.from_keywords(
        keywords=(),
        ruleset_descriptor=ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
    )
    flying_context = MovementLegalityContext.from_keywords(
        keywords=("FLY",),
        ruleset_descriptor=ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
    )

    moving_model = Model(
        model_id="fly-check-model",
        pose=Pose.at(1.0, 1.0),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )
    witness = PathWitness.for_paths((("fly-check-model", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    walking_path_context = walking_context.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=44.0,
        battlefield_depth_inches=44.0,
    )
    flying_path_context = flying_context.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=44.0,
        battlefield_depth_inches=44.0,
    )

    assert walking_path_context.to_payload()["may_transit_enemy_models"] is False
    assert flying_path_context.to_payload()["may_transit_enemy_models"] is True
    assert flying_path_context.to_payload()["may_transit_enemy_engagement"] is True


def test_phase15b_charge_move_proposal_value_object_rejects_request_drift() -> None:
    request = _charge_move_proposal_request_for_value_tests()
    witness = PathWitness.for_paths((("model-a", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    valid_proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="unit-a",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("target-a",),
        witness=witness,
    )

    round_tripped = ChargeMoveProposal.from_payload(valid_proposal.to_payload())

    assert round_tripped == valid_proposal
    assert valid_proposal.validation_result_for_request(request).is_valid
    assert (
        replace(valid_proposal, proposal_request_id="request-b")
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "stale_proposal_request"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(request, proposal_kind=ProposalKind.NORMAL_MOVE)
        )
        .violations[0]
        .violation_code
        == "proposal_kind_drift"
    )
    assert (
        replace(valid_proposal, unit_instance_id="unit-b")
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "proposal_unit_drift"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(request, movement_phase_action="normal_move")
        )
        .violations[0]
        .violation_code
        == "proposal_action_drift"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(
                request,
                context={
                    **dict(request.context or {}),
                    "movement_mode": "normal",
                },
            )
        )
        .violations[0]
        .violation_code
        == "proposal_movement_mode_drift"
    )
    assert replace(
        valid_proposal,
        charge_target_unit_instance_ids=("target-b",),
    ).validation_result_for_request(request).violations[0].violation_code == (
        "charge_target_not_reachable"
    )
    assert replace(
        valid_proposal,
        charge_target_unit_instance_ids=(),
    ).validation_result_for_request(request).violations[0].violation_code == (
        "no_move_witness_forbidden"
    )
    assert (
        replace(valid_proposal, witness=None)
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "charge_move_witness_required"
    )


def test_phase15b_charge_move_proposal_value_object_rejects_malformed_fields() -> None:
    request = _charge_move_proposal_request_for_value_tests()
    witness = PathWitness.for_paths((("model-a", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    valid_proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="unit-a",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("target-a",),
        witness=witness,
    )

    with pytest.raises(GameLifecycleError, match="proposal_kind must be charge_move"):
        replace(valid_proposal, proposal_kind=ProposalKind.NORMAL_MOVE)
    with pytest.raises(GameLifecycleError, match="movement_mode must be charge"):
        replace(valid_proposal, movement_mode=MovementMode.NORMAL)
    with pytest.raises(GameLifecycleError, match="movement_phase_action must be charge_move"):
        replace(valid_proposal, movement_phase_action="normal_move")
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        replace(valid_proposal, charge_target_unit_instance_ids=("target-a", "target-a"))
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        replace(valid_proposal, witness=cast(PathWitness, object()))
    with pytest.raises(GameLifecycleError, match="Unsupported ProposalKind token"):
        ChargeMoveProposal.from_payload(
            {
                **valid_proposal.to_payload(),
                "proposal_kind": "bad-proposal-kind",
            }
        )


def test_phase15b_charge_endpoint_witness_payload_sorts_and_rejects_malformed_fields() -> None:
    witness = ChargeEndpointWitness(
        selected_target_unit_instance_ids=("target-b", "target-a"),
        target_distances_before_inches={"target-b": 5.0, "target-a": 3.0},
        target_distances_after_inches={"target-b": 2.0, "target-a": 1.0},
        engaged_target_unit_instance_ids=("target-b",),
        preferred_distance_target_unit_instance_ids=("target-a",),
        non_target_engaged_unit_instance_ids=("enemy-c",),
    )

    payload = witness.to_payload()

    assert payload["selected_target_unit_instance_ids"] == ["target-a", "target-b"]
    assert list(payload["target_distances_before_inches"]) == ["target-a", "target-b"]
    assert list(payload["target_distances_after_inches"]) == ["target-a", "target-b"]
    assert payload["engaged_target_unit_instance_ids"] == ["target-b"]
    assert payload["preferred_distance_target_unit_instance_ids"] == ["target-a"]
    assert payload["non_target_engaged_unit_instance_ids"] == ["enemy-c"]
    with pytest.raises(GameLifecycleError, match="distances must be non-negative"):
        replace(witness, target_distances_after_inches={"target-a": -1.0})
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        replace(
            witness,
            engaged_target_unit_instance_ids=cast(tuple[str, ...], ["target-a"]),
        )


def test_phase15b_invalid_charge_move_resolution_cannot_emit_transition_batch() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-invalid-resolution",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-invalid-resolution",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(
        units["intercessor-1"].unit_instance_id
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    proposal_context = cast(dict[str, object], proposal.context)
    maximum_distance = proposal_context["maximum_distance_inches"]
    assert type(maximum_distance) is int

    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15a-test"
        ),
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        maximum_distance_inches=maximum_distance,
        path_witness=_charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=units["intercessor-1"].unit_instance_id,
            dx=3.0,
            endpoint_only=True,
        ),
    )

    assert not resolution.is_valid
    with pytest.raises(GameLifecycleError, match="Invalid Charge Move"):
        resolution.transition_batch(before=unit_placement)


def test_phase15b_charge_move_resolution_value_object_rejects_malformed_fields() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-resolution-value-object",
    )
    resolution, _unit_placement = _resolved_charge_move_for_tests(
        lifecycle,
        units=units,
        unit_key="intercessor-1",
        target_key="enemy",
        dx=3.0,
    )

    with pytest.raises(GameLifecycleError, match="attempted_placement unit drift"):
        replace(resolution, unit_instance_id="unit-b")
    with pytest.raises(GameLifecycleError, match="attempted_placement must be UnitPlacement"):
        replace(resolution, attempted_placement=cast(UnitPlacement, object()))
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        replace(resolution, witness=cast(PathWitness, object()))
    with pytest.raises(GameLifecycleError, match="endpoint_witness must be ChargeEndpointWitness"):
        replace(resolution, endpoint_witness=cast(ChargeEndpointWitness, object()))
    with pytest.raises(GameLifecycleError, match="path_validation_results must be a tuple"):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="path_validation_results must contain PathValidationResult",
    ):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], (object(),)),
        )
    with pytest.raises(
        GameLifecycleError,
        match="terrain_path_legality_results must be a tuple",
    ):
        replace(
            resolution,
            terrain_path_legality_results=cast(tuple[TerrainPathLegalityResult, ...], []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="terrain_path_legality_results must contain TerrainPathLegalityResult",
    ):
        replace(
            resolution,
            terrain_path_legality_results=cast(
                tuple[TerrainPathLegalityResult, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="coherency_result must be UnitCoherencyResult"):
        replace(resolution, coherency_result=cast(UnitCoherencyResult, object()))
    with pytest.raises(GameLifecycleError, match="rollback_record must be MovementRollbackRecord"):
        replace(resolution, rollback_record=cast(MovementRollbackRecord, object()))
    with pytest.raises(GameLifecycleError, match="movement_payload must be a JSON object"):
        replace(resolution, movement_payload=cast(dict[str, JsonValue], []))


def test_phase15b_resolve_charge_move_rejects_malformed_inputs() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-resolve-inputs",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(
        units["intercessor-1"].unit_instance_id
    )
    witness = _charge_path_witness_for_unit(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        dx=3.0,
    )
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15a-test"
    )
    selected_target_unit_instance_ids = (units["enemy"].unit_instance_id,)

    with pytest.raises(GameLifecycleError, match="requires a BattlefieldScenario"):
        resolve_charge_move(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="unit_placement must be a UnitPlacement"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=cast(UnitPlacement, object()),
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a PathWitness"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=cast(PathWitness, object()),
        )
    with pytest.raises(GameLifecycleError, match="maximum distance must be an int"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=cast(int, 6.0),
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="maximum distance must be a 2D6 value"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=1,
            path_witness=witness,
        )
    with pytest.raises(
        GameLifecycleError, match="selected_target_unit_instance_ids must be a tuple"
    ):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=cast(
                tuple[str, ...],
                [units["enemy"].unit_instance_id],
            ),
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="witness must match the selected unit models"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=PathWitness.for_paths(
                (("wrong-model", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),)
            ),
        )


def test_phase15b_malformed_charge_move_payload_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )

    status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=proposal_request.request_id,
            result_id="phase15b-submit-malformed",
            payload={
                "proposal_request_id": proposal_request.request_id,
                "unit_instance_id": units["intercessor-1"].unit_instance_id,
                "movement_phase_action": "charge_move",
                "movement_mode": "charge",
                "charge_target_unit_instance_ids": [units["enemy"].unit_instance_id],
            },
        ).to_result(proposal_request)
    )
    invalid = _last_event_payload(lifecycle, "charge_move_proposal_invalid")
    proposal_validation = cast(dict[str, object], invalid["proposal_validation"])
    violations = cast(list[dict[str, object]], proposal_validation["violations"])

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (proposal_request,)
    assert len(lifecycle.decision_controller.records) == 1
    assert violations[0]["violation_code"] == "proposal_payload_missing_field"
    assert violations[0]["field"] == "proposal_kind"


def test_charge_phase_completion_option_records_skipped_units_and_advances() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-completion",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15a-complete-charge",
    )
    completion_declared = _last_event_payload(lifecycle, "charge_phase_completion_declared")
    completed = _last_event_payload(lifecycle, "charge_phase_completed")
    state = _state(lifecycle)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.charge_phase_state is None
    assert lifecycle.decision_controller.queue.pending_requests == (status.decision_request,)
    assert completion_declared["phase_body_status"] == "charge_phase_complete"
    assert completion_declared["skipped_unit_ids"] == [units["intercessor-1"].unit_instance_id]
    assert completed["phase_body_status"] == "charge_phase_complete"
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()


def test_stale_charging_unit_selection_after_advance_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-advanced",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-stale-advanced-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="unit_instance_id",
    )


def test_stale_charging_unit_selection_after_target_drift_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-target",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            units["enemy"],
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(
                origin=Pose.at(80.0, 80.0, facing_degrees=180.0),
                model_count=len(units["enemy"].own_models),
            ),
        )
    )

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-stale-target-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="unit_instance_id",
    )


def test_stale_charge_phase_completion_rejects_skipped_unit_drift_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-complete",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15a-stale-complete-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="skipped_unit_ids",
    )
    assert _event_payloads(lifecycle, "charge_phase_completion_declared") == ()


def test_charge_phase_filters_ineligible_units() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=(
            "intercessor-1",
            "intercessor-2",
            "intercessor-3",
            "intercessor-4",
            "intercessor-5",
        ),
        alpha_origins={
            "intercessor-1": Pose.at(10.0, 10.0),
            "intercessor-2": Pose.at(10.0, 25.0),
            "intercessor-3": Pose.at(10.0, 40.0),
            "intercessor-4": Pose.at(10.0, 55.0),
            "intercessor-5": Pose.at(10.0, 70.0),
        },
        enemy_model_poses=(
            Pose.at(20.0, 10.0, facing_degrees=180.0),
            Pose.at(21.4, 10.0, facing_degrees=180.0),
            Pose.at(22.8, 10.0, facing_degrees=180.0),
            Pose.at(24.2, 10.0, facing_degrees=180.0),
            Pose.at(25.6, 10.0, facing_degrees=180.0),
        ),
        enemy_unit_ids=("enemy-1", "enemy-2", "enemy-3", "enemy-4", "enemy-5"),
        enemy_origins={
            "enemy-1": Pose.at(20.0, 10.0, facing_degrees=180.0),
            "enemy-2": Pose.at(20.0, 25.0, facing_degrees=180.0),
            "enemy-3": Pose.at(11.0, 40.0, facing_degrees=180.0),
            "enemy-4": Pose.at(20.0, 55.0, facing_degrees=180.0),
            "enemy-5": Pose.at(20.0, 70.0, facing_degrees=180.0),
        },
        game_id="phase15a-eligibility",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=units["intercessor-2"].unit_instance_id,
        )
    )
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        units["intercessor-4"].unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=units["intercessor-4"].unit_instance_id,
            reserve_kind=ReserveKind.RESERVES,
        )
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        units["intercessor-5"].unit_instance_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


def test_charge_roll_forbids_command_reroll_request() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-no-command-reroll",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-no-reroll-submit",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_roll_resolved")
    requested_decision_types = {
        cast(dict[str, object], event.payload)["decision_type"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
    }

    assert CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID in (
        roll_result.request.spec.reroll_forbidden_rule_ids
    )
    assert DICE_REROLL_DECISION_TYPE not in requested_decision_types
    assert {
        request.decision_type for request in lifecycle.decision_controller.queue.pending_requests
    } != {DICE_REROLL_DECISION_TYPE}


def test_charge_roll_and_phase_state_value_objects_reject_drift() -> None:
    request = _charge_roll_request(player_id="player-a", unit_instance_id="unit-a")
    roll_state = DiceRollManager("phase15a-value-objects").roll_fixed(request.spec, [3, 4])
    roll_result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )
    assert roll_result.move_available is True

    with pytest.raises(GameLifecycleError, match="is_legal must be a bool"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=3.0,
            is_legal=cast(bool, "true"),
        )
    with pytest.raises(GameLifecycleError, match="must not carry violation_code"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=3.0,
            is_legal=True,
            violation_code="target_out_of_declaration_range",
        )
    with pytest.raises(GameLifecycleError, match="requires violation_code"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=13.0,
            is_legal=False,
        )
    with pytest.raises(GameLifecycleError, match="payload missing target_unit_instance_id"):
        ChargeTargetCandidate.from_payload(cast(ChargeTargetCandidatePayload, {}))

    request_payload = request.to_payload()
    spec_payload = cast(dict[str, object], request_payload["spec"])
    spec_payload["roll_type"] = "wrong-roll-type"
    with pytest.raises(GameLifecycleError, match="spec payload drift"):
        ChargeRollRequest.from_payload(request_payload)
    with pytest.raises(GameLifecycleError, match="value must match"):
        replace(roll_result, value=8)
    with pytest.raises(GameLifecycleError, match="exceeds roll"):
        replace(roll_result, reachable_target_distances_inches={"target-a": 8.0})
    with pytest.raises(GameLifecycleError, match="move_available flag drift"):
        replace(roll_result, move_available=False)
    with pytest.raises(GameLifecycleError, match="status drift"):
        replace(roll_result, status=CHARGE_NO_MOVE_POSSIBLE_STATUS)
    with pytest.raises(GameLifecycleError, match="source request drift"):
        ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id="source-request-b",
            source_decision_result_id=request.source_decision_result_id,
        )
    with pytest.raises(GameLifecycleError, match="source result drift"):
        ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id=request.source_decision_request_id,
            source_decision_result_id="source-result-b",
        )

    selection = ChargingUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        request_id="select-request",
        result_id="select-result",
    )
    phase_state = ChargePhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    selected_state = phase_state.with_unit_selection(selection)
    pending_state = selected_state.with_charge_roll_result(roll_result)

    assert pending_state.move_pending_distance_state() is not None
    with pytest.raises(GameLifecycleError, match="phase_complete must be a bool"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=cast(bool, "false"),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be ChargingUnitSelection"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=cast(ChargingUnitSelection, object()),
        )
    with pytest.raises(GameLifecycleError, match="active player drift"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=replace(selection, player_id="player-b"),
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=replace(selection, battle_round=2),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be selected"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-b",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="selection must be ChargingUnitSelection"):
        phase_state.with_unit_selection(cast(ChargingUnitSelection, object()))
    with pytest.raises(GameLifecycleError, match="Cannot select"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
        ).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="requires no active selection"):
        selected_state.with_unit_selection(replace(selection, unit_instance_id="unit-b"))
    with pytest.raises(GameLifecycleError, match="selection player drift"):
        phase_state.with_unit_selection(replace(selection, player_id="player-b"))
    with pytest.raises(GameLifecycleError, match="selection battle round drift"):
        phase_state.with_unit_selection(replace(selection, battle_round=2))
    with pytest.raises(GameLifecycleError, match="already selected"):
        replace(phase_state, selected_unit_ids=("unit-a",)).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="roll result must be ChargeRollResult"):
        selected_state.with_charge_roll_result(cast(ChargeRollResult, object()))
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        replace(selected_state, phase_complete=True, active_selection=None).with_charge_roll_result(
            roll_result
        )
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        phase_state.with_charge_roll_result(roll_result)
    with pytest.raises(GameLifecycleError, match="roll player drift"):
        selected_state.with_charge_roll_result(
            _charge_roll_result(player_id="player-b", unit_instance_id="unit-a")
        )
    with pytest.raises(GameLifecycleError, match="roll battle round drift"):
        selected_state.with_charge_roll_result(
            replace(roll_result, request=replace(roll_result.request, battle_round=2))
        )
    with pytest.raises(GameLifecycleError, match="roll unit drift"):
        selected_state.with_charge_roll_result(
            _charge_roll_result(player_id="player-a", unit_instance_id="unit-b")
        )
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
        ).with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        phase_state.with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="resolution unit drift"):
        pending_state.with_charge_move_resolved("unit-b")
    with pytest.raises(GameLifecycleError, match="requires pending distance state"):
        selected_state.with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="completion requires no active selection"):
        selected_state.with_phase_complete()
    with pytest.raises(GameLifecycleError, match="cannot have active_selection"):
        replace(pending_state, phase_complete=True)


def test_charge_roll_value_objects_reject_malformed_scalars_and_mappings() -> None:
    request = _charge_roll_request(player_id="player-a", unit_instance_id="unit-a")
    roll_state = DiceRollManager("phase15a-malformed-value-objects").roll_fixed(
        request.spec,
        [2, 3],
    )
    roll_result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )

    with pytest.raises(GameLifecycleError, match="payload missing candidate"):
        ChargeTargetCandidate.from_payload(cast(ChargeTargetCandidatePayload, "bad-candidate"))
    with pytest.raises(GameLifecycleError, match="request_id must be a string"):
        replace(request, request_id=cast(str, 1))
    with pytest.raises(GameLifecycleError, match="battle_round must be greater than zero"):
        replace(request, battle_round=0)
    with pytest.raises(GameLifecycleError, match="reachable target distances must be a dict"):
        replace(roll_result, reachable_target_distances_inches=cast(dict[str, float], []))
    with pytest.raises(GameLifecycleError, match="reachable target key must be a string"):
        replace(
            roll_result,
            reachable_target_distances_inches={cast(str, 1): 3.0},
        )
    with pytest.raises(GameLifecycleError, match="must be finite"):
        replace(roll_result, reachable_target_distances_inches={"target-a": float("inf")})
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        replace(roll_result, reachable_target_distances_inches={"target-a": -1.0})
    with pytest.raises(GameLifecycleError, match="move_available must be a bool"):
        replace(roll_result, move_available=cast(bool, "true"))


def _charge_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_model_poses: tuple[Pose, ...],
    game_id: str,
    alpha_origins: dict[str, Pose] | None = None,
    enemy_unit_ids: tuple[str, ...] = ("enemy",),
    enemy_origins: dict[str, Pose] | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
    )
    armies = _mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15a-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    origins = {} if alpha_origins is None else alpha_origins
    resolved_enemy_origins = {} if enemy_origins is None else enemy_origins
    battlefield = scenario.battlefield_state
    alpha_index = 0
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-alpha":
            origin = origins.get(key, Pose.at(10.0, 20.0 + (alpha_index * 15.0)))
            poses = _compact_test_unit_poses(origin=origin, model_count=len(unit.own_models))
            alpha_index += 1
        else:
            enemy_origin = resolved_enemy_origins.get(key)
            poses = (
                enemy_model_poses
                if enemy_origin is None
                else _compact_test_unit_poses(
                    origin=enemy_origin,
                    model_count=len(unit.own_models),
                )
            )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = "player-a"
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _charge_roll_request(*, player_id: str, unit_instance_id: str) -> ChargeRollRequest:
    return ChargeRollRequest(
        request_id=f"charge-roll-{player_id}-{unit_instance_id}",
        game_id="phase15a-value-objects",
        battle_round=1,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        source_decision_request_id="source-request-a",
        source_decision_result_id="source-result-a",
    )


def _charge_roll_result(*, player_id: str, unit_instance_id: str) -> ChargeRollResult:
    request = _charge_roll_request(player_id=player_id, unit_instance_id=unit_instance_id)
    roll_state = DiceRollManager(f"phase15a-{player_id}-{unit_instance_id}").roll_fixed(
        request.spec,
        [3, 4],
    )
    return ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )


def _config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15a-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        primary_mission_id="take-and-hold",
        deployment_map_id="phase15a-open-map",
        terrain_layout_id="phase15a-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase15a-remote-objective",
                name="Phase 15A Remote Objective",
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase15a-test",
            ),
        ),
        deployment_zones=(),
        terrain_features=(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
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
        unit_selections=tuple(_unit_selection(unit_id) for unit_id in unit_selection_ids),
    )


def _unit_selection(unit_selection_id: str) -> UnitMusterSelection:
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


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _advanced_unit_state(unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:advance-roll",
        game_id="phase15a-eligibility",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase15a-advanced-state").roll_fixed(request.spec, [3])
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _charge_move_request_after_selection(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    result_id: str,
) -> DecisionRequest:
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=result_id,
    )
    request = _decision_request(status)
    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.unit_instance_id == unit_instance_id
    return request


def _charge_move_proposal_request_for_value_tests() -> MovementProposalRequest:
    return MovementProposalRequest(
        request_id="request-a",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-a",
        game_id="phase15b-value-object",
        battle_round=1,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id="unit-a",
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="source-request-a",
        source_decision_result_id="source-result-a",
        movement_phase_action="charge_move",
        context={
            "movement_mode": "charge",
            "maximum_distance_inches": 6,
            "reachable_target_unit_instance_ids": ["target-a"],
            "reachable_target_distances_inches": {"target-a": 3.0},
        },
    )


def _submit_charge_move_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: ChargeMoveProposal,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(JsonValue, proposal.to_payload()),
        ).to_result(request)
    )


def _charge_path_witness_for_unit(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    dx: float,
    dy: float = 0.0,
    endpoint_only: bool = False,
) -> PathWitness:
    state = _state(lifecycle)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge Move witness helper requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((placement.model_instance_id, (start, end, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _resolved_charge_move_for_tests(
    lifecycle: GameLifecycle,
    *,
    units: dict[str, UnitInstance],
    unit_key: str,
    target_key: str,
    dx: float,
) -> tuple[ChargeMoveResolution, UnitPlacement]:
    state = _state(lifecycle)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge Move resolution helper requires battlefield_state.")
    unit = units[unit_key]
    target = units[target_key]
    unit_placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    return (
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
                descriptor_version="core-v2-phase15a-test"
            ),
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=(target.unit_instance_id,),
            maximum_distance_inches=6,
            path_witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=unit.unit_instance_id,
                dx=dx,
            ),
        ),
        unit_placement,
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _assert_invalid_charge_submission_keeps_pending_clean(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    status: LifecycleStatus,
    expected_field: str,
) -> None:
    payload = cast(dict[str, object], status.payload)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert payload["invalid_reason"] == "invalid_charging_unit_result"
    assert payload["field"] == expected_field
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.decision_controller.records == ()
    assert _event_payloads(lifecycle, "charging_unit_selected") == ()
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()
    assert _event_payloads(lifecycle, "charge_move_required") == ()
    assert _event_payloads(lifecycle, "charge_no_move_possible") == ()


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _roll_result_from_event(lifecycle: GameLifecycle, event_type: str) -> ChargeRollResult:
    payload = _last_event_payload(lifecycle, event_type)
    return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _payload_has_displacements(payload: dict[str, object]) -> bool:
    transition_batch = payload.get("transition_batch")
    if not isinstance(transition_batch, dict):
        return False
    transition_payload = cast(dict[str, object], transition_batch)
    raw_displacements = transition_payload.get("displacements")
    if not isinstance(raw_displacements, list):
        return False
    displacements = cast(list[object], raw_displacements)
    return bool(displacements)
