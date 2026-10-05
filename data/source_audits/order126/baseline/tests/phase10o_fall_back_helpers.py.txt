from __future__ import annotations

from tests.deployment_submission_helpers import (
    default_deployment_pose,
    submit_all_deployments_if_pending,
)
from tests.movement_submission_helpers import (
    submit_default_movement_proposal_if_pending,
)
from warhammer40k_core.engine.battlefield_state import (
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import (
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import (
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    FallBackModeKind,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

_ONE_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-terrain-display-01-0002"

_TWO_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-five-fixed-0272"

_MULTI_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-terrain-display-02-0001"

_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
)

_DESPERATE_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}"
)


def advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = submit_result(
        lifecycle,
        request=decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10o-result-000001",
    )
    assert decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = submit_result(
        lifecycle,
        request=decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10o-result-000002",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase10o-deploy",
        pose_factory=fall_back_deployment_pose,
    )
    assert decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )
    return submit_default_movement_proposal_if_pending(
        lifecycle,
        status,
        result_id=f"{result_id}-proposal",
    )


def decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None
    return status.decision_request


def fall_back_state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    return lifecycle.state


def fall_back_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id == "army-alpha:intercessor-unit-1":
        return Pose.at(3.0 + (index * 1.8), 24.0, 0.0, facing_degrees=0.0)
    if unit_instance_id == "army-beta:intercessor-unit-2":
        return Pose.at(43.5 + (index * 1.8), 24.0, 0.0, facing_degrees=180.0)
    return default_deployment_pose(index, player_id, model_instance_id)


def move_first_enemy_model_into_side_engagement(lifecycle: GameLifecycle) -> None:
    state = fall_back_state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    friendly = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    first_friendly_pose = friendly.model_placements[0].pose
    target_pose = Pose.at(
        first_friendly_pose.position.x - 2.0,
        first_friendly_pose.position.y,
        first_friendly_pose.position.z,
        facing_degrees=180.0,
    )
    updated_enemy = with_first_model_pose(enemy, target_pose)
    state.battlefield_state = battlefield_state.with_unit_placement(updated_enemy)


def with_first_model_pose(unit_placement: UnitPlacement, pose: Pose) -> UnitPlacement:
    first, *rest = unit_placement.model_placements
    return unit_placement.with_model_placements((first.with_pose(pose), *rest))


def fall_back_witness(
    unit_placement: UnitPlacement,
    *,
    first_model_end_pose: Pose,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, placement in enumerate(unit_placement.model_placements):
        start = placement.pose
        end = (
            first_model_end_pose
            if index == 0
            else Pose.at(
                start.position.x,
                start.position.y + 6.0,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
        )
        midpoint = Pose.at(
            (start.position.x + end.position.x) / 2.0,
            (start.position.y + end.position.y) / 2.0,
            (start.position.z + end.position.z) / 2.0,
            facing_degrees=(start.facing.degrees + end.facing.degrees) / 2.0,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def fall_back_forward_pose(unit_placement: UnitPlacement) -> Pose:
    first_pose = unit_placement.model_placements[0].pose
    return Pose.at(
        first_pose.position.x,
        first_pose.position.y + 6.0,
        first_pose.position.z,
        facing_degrees=first_pose.facing.degrees,
    )
