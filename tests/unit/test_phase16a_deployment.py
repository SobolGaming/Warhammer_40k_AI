from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    DeploymentPoseFactory,
    deployment_proposal_for_state,
    submit_all_deployments_if_pending,
    submit_deployment_placement,
    submit_deployment_unit_selection,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import CatalogAbilitySupport, DatasheetAbilityDescriptor
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, PlacementError
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    DeploymentOrderPolicy,
    DeploymentOrderPolicyKind,
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
    DeploymentPlacementResolution,
    DeploymentPlacementViolation,
    DeploymentPlacementViolationCode,
    DeploymentSetupState,
    create_empty_deployment_battlefield_state,
    deployment_order_policy_kind_from_token,
    deployment_placement_request_from_selection,
    deployment_placement_violation_code_from_token,
    deployment_unit_selection_request,
    deployment_unit_views_for_player,
    resolve_deployment_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
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
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_phase16a_deploy_armies_uses_lifecycle_decisions_not_deterministic_bridge() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    request = _decision_request(deployment_status)

    assert request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert _option_ids(request) == ("deploy:army-beta:intercessor-unit-2",)
    option_payload = request.options[0].payload
    assert isinstance(option_payload, dict)
    assert option_payload["submission_kind"] == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE

    battle_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16a-deploy",
    )

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.battlefield_id == (
        "phase16a-game:take-and-hold-vs-purge-the-foe-layout-3-deployment:battlefield"
    )
    assert len(lifecycle.state.battlefield_state.placed_model_ids()) == 10
    assert battle_status.decision_request is None or (
        battle_status.decision_request.decision_type
        not in {
            SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
            SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        }
    )

    decision_types = tuple(
        record.request.decision_type for record in lifecycle.decision_controller.records
    )
    assert decision_types.count(SELECT_DEPLOYMENT_UNIT_DECISION_TYPE) == 2
    assert decision_types.count(SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE) == 2
    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert event_types.count("battlefield_created") == 1
    assert event_types.count("deployment_unit_selected") == 2
    assert event_types.count("deployment_unit_placed") == 2
    assert event_types.count("battlefield_models_placed") == 2
    assert _deployment_transition_source_event_ids(lifecycle) == {
        "phase16a-deploy-000002",
        "phase16a-deploy-000004",
    }

    payload_blob = json.dumps(lifecycle.to_payload(), sort_keys=True)
    assert "phase10a_deterministic_bridge" not in payload_blob
    assert "phase10a" not in lifecycle.state.battlefield_state.battlefield_id
    assert "<" not in payload_blob
    assert "object at 0x" not in payload_blob


def test_phase17j_deployment_queue_drains_opponent_remaining_units() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = _config(
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
                unit_selections=(
                    _unit_selection(unit_selection_id="intercessor-unit-2"),
                    _unit_selection(unit_selection_id="intercessor-unit-3"),
                ),
            ),
        )
    )
    lifecycle, first_status = _advance_to_first_deployment_selection(config)
    first_request = _decision_request(first_status)

    assert first_request.actor_id == "player-b"
    assert _option_ids(first_request) == (
        "deploy:army-beta:intercessor-unit-2",
        "deploy:army-beta:intercessor-unit-3",
    )

    first_placement = submit_deployment_unit_selection(
        lifecycle,
        request=first_request,
        result_id="phase17j-drain-select-b1",
        option_id="deploy:army-beta:intercessor-unit-2",
    )
    second_selection = submit_deployment_placement(
        lifecycle,
        request=_decision_request(first_placement),
        result_id="phase17j-drain-place-b1",
    )
    second_request = _decision_request(second_selection)
    assert second_request.actor_id == "player-a"
    assert _option_ids(second_request) == ("deploy:army-alpha:intercessor-unit-1",)

    second_placement = submit_deployment_unit_selection(
        lifecycle,
        request=second_request,
        result_id="phase17j-drain-select-a1",
    )
    drain_selection = submit_deployment_placement(
        lifecycle,
        request=_decision_request(second_placement),
        result_id="phase17j-drain-place-a1",
    )
    drain_request = _decision_request(drain_selection)

    assert drain_request.actor_id == "player-b"
    assert _option_ids(drain_request) == ("deploy:army-beta:intercessor-unit-3",)


def test_phase16a_invalid_deployment_rejects_before_queue_pop_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_request_id = placement_request.request_id

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-invalid-placement",
        expected_codes={DeploymentPlacementViolationCode.DEPLOYMENT_ZONE_VIOLATION.value},
        pose_factory=_midfield_outside_deployment_zone_pose,
    )

    assert lifecycle.decision_controller.queue.peek_next().request_id == before_request_id


def test_phase16a_rejects_out_of_bounds_pose_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-out-of-bounds-placement",
        expected_codes={DeploymentPlacementViolationCode.BATTLEFIELD_EDGE_CROSSED.value},
        pose_factory=_out_of_bounds_pose,
    )


def test_phase16a_rejects_illegal_terrain_endpoint_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-terrain-endpoint-placement",
        expected_codes={DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value},
        pose_factory=_terrain_endpoint_pose,
    )


def test_phase16a_rejects_blocking_objective_marker_endpoint_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement(
        _config_with_blocking_objective_marker()
    )

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-objective-endpoint-placement",
        expected_codes={DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value},
        pose_factory=_blocking_objective_marker_endpoint_pose,
    )


def test_phase16a_rejects_model_overlap_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-model-overlap-placement",
        expected_codes={DeploymentPlacementViolationCode.MODEL_OVERLAP.value},
        pose_factory=_overlapping_models_pose,
    )


def test_phase16a_rejects_broken_coherency_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-broken-coherency-placement",
        expected_codes={DeploymentPlacementViolationCode.UNIT_COHERENCY_BROKEN.value},
        pose_factory=_broken_coherency_pose,
    )


def test_phase16a_rejects_enemy_engagement_range_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_second_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-enemy-engagement-placement",
        expected_codes={DeploymentPlacementViolationCode.ENEMY_ENGAGEMENT_RANGE.value},
        pose_factory=_enemy_engagement_range_pose,
    )


def test_phase16a_stale_drift_and_malformed_proposals_reject_before_queue_pop() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    stale_status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-stale-placement",
        payload_mutation=lambda payload: payload.__setitem__(
            "ruleset_descriptor_hash",
            "stale-ruleset-hash",
        ),
    )

    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(stale_status) == "deployment_request_drift"
    assert DeploymentPlacementViolationCode.RULESET_HASH_DRIFT.value in _violation_codes(
        stale_status
    )
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count

    malformed_status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-malformed-placement",
        payload_mutation=_drop_model_placements,
    )

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(malformed_status) == "malformed_deployment_placement"
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_omitted_models_reject_before_queue_pop() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-omitted-model-placement",
        payload_mutation=_omit_last_model_placement,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert DeploymentPlacementViolationCode.MODEL_SET_DRIFT.value in _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_model_identity_player_and_component_drift_are_typed_violations() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-model-identity-drift-placement",
        payload_mutation=_drift_first_model_and_append_wrong_unit_model,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert {
        DeploymentPlacementViolationCode.MODEL_SET_DRIFT.value,
        DeploymentPlacementViolationCode.PLAYER_DRIFT.value,
        DeploymentPlacementViolationCode.WRONG_UNIT_MODEL.value,
    } <= _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_infiltrators_may_deploy_outside_zone_more_than_eight_from_enemy_zone() -> None:
    state = _deployment_state_with_mustered_armies(player_b_infiltrators=True)
    request = _deployment_placement_request_for_player(state, player_id="player-b")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)

    valid_resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_valid_midfield_pose,
        ),
    )

    assert valid_resolution.is_valid
    assert valid_resolution.transition_batch is not None
    assert len(valid_resolution.transition_batch.placements) == 5

    invalid_resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_too_close_to_enemy_zone_pose,
        ),
    )

    assert not invalid_resolution.is_valid
    assert DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_ZONE_DISTANCE in {
        violation.violation_code for violation in invalid_resolution.violations
    }


def test_phase16a_infiltrators_datasheet_ability_enables_midfield_deployment() -> None:
    state = _deployment_state_with_mustered_armies(player_b_infiltrators_ability=True)
    request = _deployment_placement_request_for_player(state, player_id="player-b")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)

    resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_valid_midfield_pose,
        ),
    )

    assert resolution.is_valid
    assert resolution.transition_batch is not None
    assert len(resolution.transition_batch.placements) == 5


def test_phase16a_attached_rules_unit_deploys_group_aware_component_models() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = _config(
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _attached_army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        )
    )
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    request = _decision_request(deployment_status)

    assert request.actor_id == "player-b"
    assert _option_ids(request) == ("deploy:attached-unit:army-beta:bodyguard-unit",)
    option_payload = request.options[0].payload
    assert isinstance(option_payload, dict)
    assert option_payload["is_attached_rules_unit"] is True
    assert option_payload["component_unit_instance_ids"] == [
        "army-beta:bodyguard-unit",
        "army-beta:leader-unit",
        "army-beta:support-unit",
    ]

    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=request,
        result_id="phase16a-attached-select",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    follow_up = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-attached-place",
    )

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    for unit_id in (
        "army-beta:bodyguard-unit",
        "army-beta:leader-unit",
        "army-beta:support-unit",
    ):
        assert lifecycle.state.battlefield_state.unit_placement_by_id(unit_id).player_id == (
            "player-b"
        )
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        lifecycle.state.battlefield_state.unit_placement_by_id(
            "attached-unit:army-beta:bodyguard-unit"
        )


def test_phase16a_unavailable_reserve_units_are_excluded_from_deployment_options() -> None:
    state = _deployment_state_with_mustered_armies()
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )

    assert deployment_unit_views_for_player(state=state, player_id="player-b") == ()


def test_phase16a_replay_restore_preserves_pending_deployment_request() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    request = _decision_request(deployment_status)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    restored = GameLifecycle.from_payload(payload)
    restored_status = restored.advance_until_decision_or_terminal()

    assert _decision_request(restored_status).to_payload() == request.to_payload()
    assert GameLifecycle.from_payload(payload).to_payload() == payload


def test_phase16a_deployment_payload_round_trips_and_reports_request_drift() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    assert lifecycle.state is not None
    assert isinstance(placement_request.payload, dict)
    assert "proposal_request" in placement_request.payload
    assert "deployment_request" not in placement_request.payload
    request = DeploymentPlacementRequest.from_decision_request_payload(placement_request.payload)
    proposal = deployment_proposal_for_state(lifecycle.state, request=placement_request)

    assert DeploymentPlacementRequest.from_payload(request.to_payload()) == request
    assert DeploymentPlacementProposal.from_payload(proposal.to_payload()) == proposal
    grouped = proposal.grouped_unit_placements()
    assert len(grouped) == 1
    assert grouped[0].unit_instance_id == request.unit_instance_id

    drifted = replace(
        proposal,
        proposal_request_id="phase16a-stale-request",
        game_id="phase16a-other-game",
        ruleset_descriptor_hash="phase16a-other-ruleset",
        player_id="player-a",
        unit_instance_id="army-alpha:other-unit",
        placement_kind=BattlefieldPlacementKind.REDEPLOY,
    )

    assert {
        violation.violation_code for violation in drifted.request_drift_violations(request)
    } == {
        DeploymentPlacementViolationCode.STALE_PROPOSAL_REQUEST,
        DeploymentPlacementViolationCode.GAME_ID_DRIFT,
        DeploymentPlacementViolationCode.RULESET_HASH_DRIFT,
        DeploymentPlacementViolationCode.PLAYER_DRIFT,
        DeploymentPlacementViolationCode.UNIT_DRIFT,
        DeploymentPlacementViolationCode.PLACEMENT_KIND_DRIFT,
    }


def test_phase16a_deployment_public_guards_are_fail_fast() -> None:
    assert (
        deployment_order_policy_kind_from_token(
            DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
        )
        is DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
    )
    assert (
        deployment_order_policy_kind_from_token("defender_first_alternating")
        is DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
    )
    assert (
        deployment_placement_violation_code_from_token("unit_drift")
        is DeploymentPlacementViolationCode.UNIT_DRIFT
    )
    with pytest.raises(GameLifecycleError, match="DeploymentOrderPolicyKind token"):
        deployment_order_policy_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported DeploymentOrderPolicyKind"):
        deployment_order_policy_kind_from_token("random_policy")
    with pytest.raises(GameLifecycleError, match="DeploymentPlacementViolationCode token"):
        deployment_placement_violation_code_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported DeploymentPlacementViolationCode"):
        deployment_placement_violation_code_from_token("random_violation")
    with pytest.raises(GameLifecycleError, match="DeploymentSetupState requires DEPLOY_ARMIES"):
        DeploymentSetupState(
            setup_step=SetupStep.MUSTER_ARMIES,
            order_policy=DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING,
            next_player_id=None,
            remaining_unit_count_by_player={},
        )
    with pytest.raises(GameLifecycleError, match="Deployment order requires GameState"):
        DeploymentOrderPolicy.core_rules().next_player_id(cast(GameState, object()))


def test_phase16a_deployment_request_and_resolution_guards_reject_invalid_shapes() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    assert lifecycle.state is not None
    request = DeploymentPlacementRequest.from_decision_request_payload(placement_request.payload)
    proposal = deployment_proposal_for_state(lifecycle.state, request=placement_request)
    resolution = resolve_deployment_placement(
        state=lifecycle.state,
        ruleset_descriptor=_ruleset(),
        request=request,
        proposal=proposal,
    )
    assert resolution.is_valid
    assert resolution.transition_batch is not None

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        DeploymentPlacementRequest.from_decision_request_payload("not-an-object")
    with pytest.raises(GameLifecycleError, match="payload missing request"):
        DeploymentPlacementRequest.from_decision_request_payload({})
    with pytest.raises(GameLifecycleError, match="actor_id must match player_id"):
        replace(request, actor_id="player-a" if request.player_id == "player-b" else "player-b")
    with pytest.raises(GameLifecycleError, match="requires deployment placement"):
        replace(request, placement_kind=BattlefieldPlacementKind.REDEPLOY)

    violation = DeploymentPlacementViolation(
        violation_code=DeploymentPlacementViolationCode.UNIT_DRIFT,
        message="Deployment proposal unit does not match the pending request.",
        field="unit_instance_id",
    )
    with pytest.raises(GameLifecycleError, match="Invalid deployment placement"):
        DeploymentPlacementResolution(
            proposal=proposal,
            violations=(violation,),
            coherency_result=resolution.coherency_result,
            transition_batch=resolution.transition_batch,
        )
    with pytest.raises(GameLifecycleError, match="Valid deployment placement requires transitions"):
        DeploymentPlacementResolution(
            proposal=proposal,
            violations=(),
            coherency_result=resolution.coherency_result,
            transition_batch=None,
        )


def _advance_to_first_deployment_selection(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16a-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16a-secondary-player-b",
    )
    assert _decision_request(deployment_status).decision_type == (
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    )
    return lifecycle, deployment_status


def _advance_to_first_deployment_placement(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=_decision_request(deployment_status),
        result_id="phase16a-first-deployment-selection",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    return lifecycle, placement_request


def _advance_to_second_deployment_placement() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, first_request = _advance_to_first_deployment_placement()
    next_selection_status = submit_deployment_placement(
        lifecycle,
        request=first_request,
        result_id="phase16a-first-valid-placement",
    )
    next_selection_request = _decision_request(next_selection_status)
    assert next_selection_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=next_selection_request,
        result_id="phase16a-second-deployment-selection",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    return lifecycle, placement_request


def _deployment_state_with_mustered_armies(
    *,
    player_b_infiltrators: bool = False,
    player_b_infiltrators_ability: bool = False,
) -> GameState:
    config = _config()
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        army = muster_army(catalog=config.army_catalog, request=request)
        if army.player_id == "player-b" and (
            player_b_infiltrators or player_b_infiltrators_ability
        ):
            unit = army.units[0]
            keywords = unit.keywords
            abilities = unit.datasheet_abilities
            if player_b_infiltrators:
                keywords = (*keywords, "INFILTRATORS")
            if player_b_infiltrators_ability:
                abilities = (
                    *abilities,
                    DatasheetAbilityDescriptor(
                        ability_id="core-infiltrators",
                        name="Core Infiltrators",
                        source_id="datasheet:core-intercessor-like-infantry:ability:infiltrators",
                        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                        timing_tags=("deployment",),
                    ),
                )
            army = replace(
                army,
                units=(replace(unit, keywords=keywords, datasheet_abilities=abilities),),
            )
        state.record_army_definition(army)
    while state.current_setup_step is not SetupStep.DEPLOY_ARMIES:
        if state.current_setup_step is SetupStep.CREATE_BATTLEFIELD:
            state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
        state.complete_current_setup_step()
    return state


def _deployment_placement_request_for_player(
    state: GameState,
    *,
    player_id: str,
) -> DecisionRequest:
    selection_request = deployment_unit_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id=player_id,
    )
    selection_result = DecisionResult.for_request(
        result_id=f"phase16a-{player_id}-selection",
        request=selection_request,
        selected_option_id=selection_request.options[0].option_id,
    )
    return deployment_placement_request_from_selection(
        state=state,
        ruleset_descriptor=_ruleset(),
        selection_request=selection_request,
        result=selection_result,
    ).to_decision_request()


def _midfield_outside_deployment_zone_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(24.0, 20.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _out_of_bounds_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(61.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _terrain_endpoint_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(44.5, 5.0 + (index * 1.8), 0.5, facing_degrees=180.0)


def _blocking_objective_marker_endpoint_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    if index == 0:
        return Pose.at(57.0, 20.0, 0.0, facing_degrees=180.0)
    return Pose.at(57.0, 24.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _overlapping_models_pose(
    _index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(57.0, 3.0, 0.0, facing_degrees=180.0)


def _broken_coherency_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    if index == 4:
        return Pose.at(57.0, 40.0, 0.0, facing_degrees=180.0)
    return Pose.at(57.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _enemy_engagement_range_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(54.0, 3.0 + (index * 1.8), 0.0, facing_degrees=0.0)


def _infiltrators_valid_midfield_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(31.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _infiltrators_too_close_to_enemy_zone_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(25.0, 20.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _drop_model_placements(payload: dict[str, JsonValue]) -> None:
    payload.pop("model_placements")


def _omit_last_model_placement(payload: dict[str, JsonValue]) -> None:
    cast(list[JsonValue], payload["model_placements"]).pop()


def _drift_first_model_and_append_wrong_unit_model(payload: dict[str, JsonValue]) -> None:
    placements = cast(list[dict[str, JsonValue]], payload["model_placements"])
    first = placements[0]
    extra = dict(first)
    first["player_id"] = "player-a"
    extra["player_id"] = "player-a"
    extra["army_id"] = "army-alpha"
    extra["unit_instance_id"] = "army-alpha:intercessor-unit-1"
    extra["model_instance_id"] = "army-alpha:intercessor-unit-1:core-intercessor-like:001"
    placements.append(extra)


def _assert_invalid_deployment_without_mutation(
    lifecycle: GameLifecycle,
    *,
    placement_request: DecisionRequest,
    result_id: str,
    expected_codes: set[str],
    pose_factory: DeploymentPoseFactory | None = None,
    payload_mutation: Callable[[dict[str, JsonValue]], None] | None = None,
) -> LifecycleStatus:
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_record_count = len(lifecycle.decision_controller.records)
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id=result_id,
        pose_factory=pose_factory,
        payload_mutation=payload_mutation,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert expected_codes <= _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload
    return status


def _submit_result(
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


def _deployment_transition_source_event_ids(lifecycle: GameLifecycle) -> set[str]:
    source_event_ids: set[str] = set()
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type != "battlefield_models_placed":
            continue
        assert isinstance(event.payload, dict)
        transition_batch = event.payload["transition_batch"]
        assert isinstance(transition_batch, dict)
        placements = transition_batch["placements"]
        assert isinstance(placements, list)
        for placement in placements:
            assert isinstance(placement, dict)
            source_event_id = placement["source_event_id"]
            assert type(source_event_id) is str
            source_event_ids.add(source_event_id)
    return source_event_ids


def _option_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(option.option_id for option in request.options)


def _config(
    *,
    army_muster_requests: tuple[ArmyMusterRequest, ...] | None = None,
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16a-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_requests(catalog) if army_muster_requests is None else army_muster_requests
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


def _config_with_blocking_objective_marker() -> GameConfig:
    base = _config()
    assert base.mission_setup is not None
    blocking_marker = ObjectiveMarkerDefinition(
        objective_marker_id="phase16a-blocking-objective",
        name="Phase 16A Blocking Objective",
        objective_role=ObjectiveMarkerRole.CENTRAL,
        x_inches=57.0,
        y_inches=20.0,
        blocks_placement=True,
        source_id="phase16a-test:objective-marker",
    )
    mission_setup = replace(
        base.mission_setup,
        objective_markers=(*base.mission_setup.objective_markers, blocking_marker),
    )
    return replace(base, mission_setup=mission_setup)


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16a-test")


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_requests(catalog: ArmyCatalog) -> tuple[ArmyMusterRequest, ...]:
    return (
        _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selection_id="intercessor-unit-1",
        ),
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selection_id="intercessor-unit-2",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
    unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
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
        unit_selections=(
            (_unit_selection(unit_selection_id=unit_selection_id),)
            if unit_selections is None
            else unit_selections
        ),
        attachment_declarations=attachment_declarations,
    )


def _attached_army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return _army_muster_request(
        catalog=catalog,
        player_id=player_id,
        army_id=army_id,
        unit_selection_id="bodyguard-unit",
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
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
