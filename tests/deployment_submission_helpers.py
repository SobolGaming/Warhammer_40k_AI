from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.adapters.decisions import submit_option, submit_parameterized_payload
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, SetupStep
from warhammer40k_core.geometry.pose import Pose

DeploymentPoseFactory = Callable[[int, str, str], Pose]


def submit_all_deployments_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id_prefix: str,
    pose_factory: DeploymentPoseFactory | None = None,
) -> LifecycleStatus:
    current = status
    result_number = 1
    while current.decision_request is not None and current.decision_request.decision_type in {
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    }:
        request = current.decision_request
        result_id = f"{result_id_prefix}-{result_number:06d}"
        if request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
            current = submit_deployment_unit_selection(
                lifecycle,
                request=request,
                result_id=result_id,
            )
        else:
            current = submit_deployment_placement(
                lifecycle,
                request=request,
                result_id=result_id,
                pose_factory=pose_factory,
            )
        result_number += 1
    return current


def submit_deployment_unit_selection(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    option_id: str | None = None,
) -> LifecycleStatus:
    if request.decision_type != SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
        raise GameLifecycleError("Expected deployment unit selection request.")
    selected_option_id = request.options[0].option_id if option_id is None else option_id
    return submit_option(
        lifecycle=lifecycle,
        request_id=request.request_id,
        option_id=selected_option_id,
        result_id=result_id,
    )


def submit_deployment_placement(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    pose_factory: DeploymentPoseFactory | None = None,
    payload_mutation: Callable[[dict[str, JsonValue]], None] | None = None,
) -> LifecycleStatus:
    payload = deployment_placement_payload_for_request(
        lifecycle,
        request=request,
        pose_factory=pose_factory,
    )
    if payload_mutation is not None:
        payload_mutation(payload)
    return submit_parameterized_payload(
        lifecycle=lifecycle,
        request_id=request.request_id,
        payload=payload,
        result_id=result_id,
    )


def deployment_placement_payload_for_request(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    pose_factory: DeploymentPoseFactory | None = None,
) -> dict[str, JsonValue]:
    proposal_payload = validate_json_value(
        deployment_proposal_for_request(
            lifecycle,
            request=request,
            pose_factory=pose_factory,
        ).to_payload()
    )
    if not isinstance(proposal_payload, dict):
        raise GameLifecycleError("Deployment proposal test helper payload must be an object.")
    return proposal_payload


def deployment_proposal_for_request(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    pose_factory: DeploymentPoseFactory | None = None,
) -> DeploymentPlacementProposal:
    if lifecycle.state is None:
        raise GameLifecycleError("Deployment proposal test helper requires GameState.")
    return deployment_proposal_for_state(
        lifecycle.state,
        request=request,
        pose_factory=pose_factory,
    )


def deployment_proposal_for_state(
    state: GameState,
    *,
    request: DecisionRequest,
    pose_factory: DeploymentPoseFactory | None = None,
) -> DeploymentPlacementProposal:
    if request.decision_type != SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Expected deployment placement proposal request.")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
    placements: list[ModelPlacement] = []
    for index, model_instance_id in enumerate(request_context.model_instance_ids):
        source = _model_source_for_id(state=state, model_instance_id=model_instance_id)
        pose = (
            default_deployment_pose_for_unit(
                index,
                request_context.player_id,
                model_instance_id,
                request_context.unit_instance_id,
            )
            if pose_factory is None
            else pose_factory(index, request_context.player_id, model_instance_id)
        )
        placements.append(
            ModelPlacement(
                army_id=source[0],
                player_id=source[1],
                unit_instance_id=source[2],
                model_instance_id=model_instance_id,
                pose=pose,
            )
        )
    return DeploymentPlacementProposal(
        proposal_request_id=request_context.request_id,
        proposal_kind=request_context.proposal_kind,
        game_id=request_context.game_id,
        ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
        setup_step=SetupStep.DEPLOY_ARMIES,
        player_id=request_context.player_id,
        unit_instance_id=request_context.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
        model_placements=tuple(placements),
        context=request_context.context,
    )


def default_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    return default_deployment_pose_for_unit(index, player_id, model_instance_id, unit_instance_id)


def default_deployment_pose_for_unit(
    index: int,
    player_id: str,
    _model_instance_id: str,
    unit_instance_id: str,
) -> Pose:
    row = index // 3
    column = index % 3
    base_y = _deployment_base_y_for_unit(unit_instance_id)
    if player_id == "player-b":
        return Pose.at(57.0 - (row * 1.8), base_y + (column * 1.8), 0.0, facing_degrees=180.0)
    return Pose.at(3.0 + (row * 1.8), base_y + (column * 1.8), 0.0, facing_degrees=0.0)


def _deployment_base_y_for_unit(unit_instance_id: str) -> float:
    slots = (24.0, 3.0, 13.5, 32.0)
    return slots[_unit_slot(unit_instance_id) % len(slots)]


def _unit_slot(unit_instance_id: str) -> int:
    digits = ""
    for character in reversed(unit_instance_id):
        if character.isdigit():
            digits = f"{character}{digits}"
            continue
        if digits:
            break
    if not digits:
        return 0
    return max(int(digits) - 1, 0)


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
    raise GameLifecycleError("Deployment proposal model_instance_id is not mustered.")
