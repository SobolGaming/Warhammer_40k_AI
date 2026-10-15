from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest

from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.sequential_translation_helpers import leading_first_translation_paths
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.battlefield_transition_history import (
    AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES,
    authoritative_battlefield_transition_batch_or_none,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    create_empty_deployment_battlefield_state,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
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
    redeploy_timing_state_for_state,
    resolve_prebattle_proposal,
    scout_move_candidates_for_player,
)
from warhammer40k_core.engine.prebattle_integrity import validate_prebattle_alternation_restore
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    PreBattleActionRecord,
    PreBattleAlternationCursor,
    prebattle_action_kind_from_token,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState, ReserveStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.transport_disembark_state import DisembarkModeKind
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


@pytest.fixture
def pending_alternating_scout_after_first_action_payload() -> GameLifecyclePayload:
    catalog = _catalog_with_datasheet_keywords(
        {"core-intercessor-like-infantry": ("Infantry", "Battleline", "SCOUTS")}
    )
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(
                _unit_selection(unit_selection_id="scout-unit-1"),
                _unit_selection(unit_selection_id="scout-unit-2"),
            ),
            player_b_unit_selections=(
                _unit_selection(unit_selection_id="scout-unit-1"),
                _unit_selection(unit_selection_id="scout-unit-2"),
            ),
        )
    )
    selection_request = _decision_request(status)
    proposal_status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id="scout_move:army-alpha:scout-unit-1",
        result_id="phase16b-restore-integrity-scout-select-a-1",
    )
    proposal_request = _decision_request(proposal_status)
    if lifecycle.state is None:
        raise GameLifecycleError("Alternating Scout fixture requires GameState.")
    follow_up = _submit_scout_move(
        lifecycle,
        request=proposal_request,
        result_id="phase16b-restore-integrity-scout-apply-a-1",
        witness=_scout_move_witness(lifecycle.state, request=proposal_request, dx=1.0),
    )
    assert _decision_request(follow_up).actor_id == "player-b"
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
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


def _redeploy_placement_request(
    catalog: ArmyCatalog,
    *,
    player_a_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    player_b_unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    mission_setup: MissionSetup | None = None,
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, status = _advance_after_deployments(
        _config(
            catalog=catalog,
            player_a_unit_selections=(
                (_vehicle_unit_selection(unit_selection_id="enemy-unit-1"),)
                if player_a_unit_selections is None
                else player_a_unit_selections
            ),
            player_b_unit_selections=player_b_unit_selections,
            mission_setup=mission_setup,
        )
    )
    selection_request = _decision_request(status)
    assert selection_request.decision_type == SELECT_REDEPLOY_UNIT_DECISION_TYPE
    option = _option_for_prefix(selection_request, "redeploy:")
    proposal_status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=option.option_id,
        result_id="phase16b-redeploy-select",
    )
    request = _decision_request(proposal_status)
    assert request.decision_type == SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE
    return lifecycle, request


def _redeploy_invalid_pose_factory(case_id: str) -> _PoseFactory:
    if case_id == "illegal-zone":
        return _redeploy_illegal_zone_pose
    if case_id == "overlap":
        return _redeploy_overlap_pose
    if case_id == "broken-coherency":
        return _redeploy_broken_coherency_pose
    raise GameLifecycleError("Unsupported redeploy invalid geometry case.")


def _redeploy_illegal_zone_pose(index: int) -> Pose:
    return Pose.at(12.0, 10.0 + (index * 1.8), 0.0)


def _redeploy_overlap_pose(_index: int) -> Pose:
    return Pose.at(56.0, 34.0, 0.0, facing_degrees=180.0)


def _redeploy_broken_coherency_pose(index: int) -> Pose:
    return Pose.at(56.0, 4.0 + (index * 8.0), 0.0, facing_degrees=180.0)


def _submit_redeploy_placement_payload(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    payload: dict[str, JsonValue],
) -> LifecycleStatus:
    if lifecycle.state is None or lifecycle.state.battlefield_state is None:
        raise GameLifecycleError("Redeploy test requires placed battlefield state.")
    before_battlefield = lifecycle.state.battlefield_state.to_payload()
    before_record_count = len(lifecycle.decision_controller.records)
    invalid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=payload,
        )
    )
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield
    return invalid_status


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
            poses = (start, end, end)
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
    return PathWitness.for_paths(leading_first_translation_paths(tuple(model_paths), dx=dx, dy=dy))


def _witness_with_first_start_drift(witness: PathWitness) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, model_id in enumerate(witness.model_ids()):
        poses = witness.poses_for_model(model_id)
        if index == 0:
            start = poses[0]
            poses = (
                Pose.at(
                    start.position.x + 0.25,
                    start.position.y,
                    start.position.z,
                    facing_degrees=start.facing.degrees,
                ),
                *poses[1:],
            )
        model_paths.append((model_id, poses))
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
    catalog: ArmyCatalog,
    selection_request: DecisionRequest,
    result: DecisionResult,
) -> PreBattleProposalRequest:
    from warhammer40k_core.engine.prebattle import prebattle_proposal_request_from_selection

    return prebattle_proposal_request_from_selection(
        state=state,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
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


def _clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(payload)))


def _assert_redeploy_replay_rejected_without_mutation(
    lifecycle_payload: dict[str, Any],
    *,
    result_id: str,
) -> None:
    lifecycle = GameLifecycle.from_payload(cast(GameLifecyclePayload, lifecycle_payload))
    request = lifecycle.decision_controller.queue.peek_next()
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    before = _clone_payload(cast(dict[str, Any], lifecycle.to_payload()))
    state = lifecycle.state
    assert state is not None
    before_timing_state = redeploy_timing_state_for_state(state).to_payload()
    before_record_count = len(lifecycle.decision_controller.records)
    before_event_count = len(lifecycle.decision_controller.event_log.records)
    before_resolved_count = _event_types(lifecycle).count("sequencing_order_resolved")

    status = lifecycle.submit_decision(result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == before
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert len(lifecycle.decision_controller.event_log.records) == before_event_count
    assert _event_types(lifecycle).count("sequencing_order_resolved") == before_resolved_count
    assert redeploy_timing_state_for_state(state).to_payload() == before_timing_state
    before_decisions = DecisionController.from_payload(before["decisions"])
    after_decisions = DecisionController.from_payload(lifecycle.decision_controller.to_payload())
    future_roll_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Setup sequencing rejection future RNG audit",
        roll_type="setup_sequencing_rejection_audit",
    )
    before_future_roll = DiceRollManager(
        state.game_id,
        event_log=before_decisions.event_log,
    ).roll(future_roll_spec)
    after_future_roll = DiceRollManager(
        state.game_id,
        event_log=after_decisions.event_log,
    ).roll(future_roll_spec)
    assert after_future_roll == before_future_roll


def _restored_pending_request(
    lifecycle: GameLifecycle,
    expected_request: DecisionRequest,
) -> DecisionRequest:
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    restored_status = restored.advance_until_decision_or_terminal()

    assert GameLifecycle.from_payload(payload).to_payload() == payload
    assert restored.decision_controller.queue.peek_next().request_id == expected_request.request_id
    return _decision_request(restored_status)


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
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id="phase16b-game",
        allow_legacy_non_strict_rosters=True,
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
        mission_setup=_mission_setup() if mission_setup is None else mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16b-test")


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _mission_setup_with_terrain_endpoint_feature() -> MissionSetup:
    return replace(
        _mission_setup(),
        deployment_map_id="phase16b-terrain-endpoint-custom-deployment",
        terrain_layout_id="phase16b-terrain-endpoint-custom-terrain",
        terrain_features=(
            _terrain_endpoint_feature(
                feature_id="phase16b-redeploy-terrain-endpoint-hill",
                center_x_inches=49.0,
                center_y_inches=17.0,
                width_inches=8.0,
                depth_inches=8.0,
            ),
        ),
    )


def _terrain_endpoint_feature(
    *,
    feature_id: str,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=width_inches,
        footprint_depth_inches=depth_inches,
        rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
            display_template_id="phase16b_terrain_endpoint_hill_rules",
        ).footprint_polygon,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
            display_template_id="phase16b_terrain_endpoint_hill",
        ),
        source_id=f"phase16b-test:terrain:{feature_id}",
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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


def _catalog_with_datasheet_keywords(
    mapping: dict[str, tuple[str, ...]],
    *,
    scouts_distances_by_datasheet: dict[str, tuple[float, ...]] | None = None,
    add_default_scouts_abilities: bool = True,
) -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets: list[DatasheetDefinition] = []
    scouts_distances = (
        {} if scouts_distances_by_datasheet is None else scouts_distances_by_datasheet
    )
    for datasheet in base.datasheets:
        keywords = mapping.get(datasheet.datasheet_id)
        resolved_keywords = datasheet.keywords.keywords if keywords is None else keywords
        abilities = tuple(
            ability
            for ability in datasheet.abilities
            if "scouts" not in {tag.lower() for tag in ability.timing_tags}
        )
        requested_scout_distances = scouts_distances.get(datasheet.datasheet_id)
        if (
            requested_scout_distances is None
            and add_default_scouts_abilities
            and "SCOUTS" in {keyword.upper().replace(" ", "_") for keyword in resolved_keywords}
        ):
            requested_scout_distances = (6.0,)
        if requested_scout_distances is not None:
            abilities = (
                *abilities,
                *_scouts_ability_descriptors(
                    datasheet_id=datasheet.datasheet_id,
                    distances=requested_scout_distances,
                ),
            )
        datasheets.append(
            replace(
                datasheet,
                keywords=DatasheetKeywordSet(
                    keywords=resolved_keywords,
                    faction_keywords=datasheet.keywords.faction_keywords,
                ),
                abilities=abilities,
            )
        )
    return replace(base, datasheets=tuple(datasheets))


def _scouts_ability_descriptors(
    *,
    datasheet_id: str,
    distances: tuple[float, ...],
) -> tuple[DatasheetAbilityDescriptor, ...]:
    return tuple(
        DatasheetAbilityDescriptor(
            ability_id=f"core-scouts-{index + 1}",
            name=f"CORE Scouts {distance:g}",
            source_id=f"datasheet:{datasheet_id}:ability:scouts:{index + 1}",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description=f"CORE Scouts {distance:g} descriptor.",
            timing_tags=("before_battle", "scouts"),
            parameter_tokens=(f"{distance:g}",),
        )
        for index, distance in enumerate(distances)
    )


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


__all__: list[str] = []
__all__ += ["AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES", "Any", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BattlefieldPlacementKind"]
__all__ += ["BattlefieldTransitionBatch", "Callable", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "DatasheetAbilityDescriptor", "DatasheetDefinition"]
__all__ += ["DatasheetKeywordSet", "DecisionController", "DecisionError", "DecisionOption"]
__all__ += ["DecisionRecord", "DecisionRequest", "DecisionResult", "DetachmentSelection"]
__all__ += ["DiceExpression", "DiceRollManager", "DiceRollSpec", "DisembarkModeKind"]
__all__ += ["EventRecord", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecyclePayload", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup", "ModelDisplacementKind"]
__all__ += ["ModelPlacement", "ModelProfileSelection", "MovementPhaseActionKind"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "MovementProposalRequest", "PathWitness"]
__all__ += ["PlacementProposalPayload", "Pose", "PreBattleActionKind", "PreBattleActionRecord"]
__all__ += ["PreBattleAlternationCursor", "PreBattlePlacementProposal"]
__all__ += ["PreBattlePlacementProposalPayload", "PreBattleProposalRequest"]
__all__ += ["PreBattleProposalRequestPayload", "PreBattleTimingWindowState"]
__all__ += ["PreBattleViolationCode", "ReplayArtifact", "ReplayRunner", "ReserveKind"]
__all__ += ["SCOUT_MOVE_PROPOSAL_KIND", "ReserveState", "ReserveStatus", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_DEPLOYMENT_UNIT_DECISION_TYPE"]
__all__ += ["SELECT_PREBATTLE_ACTION_DECISION_TYPE", "SELECT_REDEPLOY_UNIT_DECISION_TYPE"]
__all__ += ["SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE", "SUBMIT_SCOUT_MOVE_DECISION_TYPE"]
__all__ += ["ScoutAbilityInstance", "ScoutMoveProposal", "SetupStep", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "TransportCapacityProfile"]
__all__ += ["TransportCargoState", "TransportMovementStatus", "UnitInstance"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "_PoseFactory", "_advance_after_deployments"]
__all__ += ["_advance_to_first_deployment_selection", "_army_muster_request"]
__all__ += ["_army_muster_requests", "_assert_redeploy_replay_rejected_without_mutation"]
__all__ += ["_catalog_with_datasheet_keywords", "_clone_payload", "_config", "_decision_request"]
__all__ += ["_event_types", "_invalid_reason", "_manual_prebattle_state", "_mission_setup"]
__all__ += ["_mission_setup_with_terrain_endpoint_feature", "_model_source_for_id"]
__all__ += ["_move_unit_placement", "_option_for_prefix", "_option_ids", "_place_unit"]
__all__ += ["_prebattle_placement_payload", "_prebattle_placement_payload_for_request"]
__all__ += ["_proposal_request_from_selection_payload", "_redeploy_broken_coherency_pose"]
__all__ += ["_redeploy_illegal_zone_pose", "_redeploy_invalid_pose_factory"]
__all__ += ["_redeploy_overlap_pose", "_redeploy_placement_request", "_restored_pending_request"]
__all__ += ["_ruleset", "_scout_move_witness", "_scouts_ability_descriptors", "_scouts_config"]
__all__ += ["_select_scout_move", "_submit_option", "_submit_redeploy_placement_payload"]
__all__ += ["_submit_scout_move", "_terrain_endpoint_feature", "_unit_selection"]
__all__ += ["_unit_source_for_id", "_vehicle_unit_selection", "_violation_codes"]
__all__ += ["_witness_with_first_start_drift", "apply_scout_move", "apply_scout_reserve_setup"]
__all__ += ["authoritative_battlefield_transition_batch_or_none", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["dedicated_transport_scout_move_candidates_for_player"]
__all__ += ["invalid_prebattle_proposal_status", "json", "leading_first_translation_paths"]
__all__ += ["muster_army", "pending_alternating_scout_after_first_action_payload"]
__all__ += ["prebattle_action_kind_from_token", "prebattle_action_selection_request"]
__all__ += ["prebattle_timing_state_for_state", "prebattle_violation_code_from_token", "pytest"]
__all__ += ["redeploy_timing_state_for_state", "replace", "resolve_prebattle_proposal"]
__all__ += ["scout_move_candidates_for_player", "submit_all_deployments_if_pending"]
__all__ += ["validate_json_value", "validate_prebattle_alternation_restore"]
