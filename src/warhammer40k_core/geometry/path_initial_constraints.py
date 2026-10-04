"""Initial pose and distance constraints shared by physical path validation."""

from warhammer40k_core.geometry.movement_envelope import MovementDistanceWitness
from warhammer40k_core.geometry.path_validation_result import (
    PathConstraintViolation,
    PathValidationResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model


def initial_path_constraint_result(
    *,
    model: Model,
    path: tuple[Pose, ...],
    distance: MovementDistanceWitness,
    pose_is_fixed: bool,
) -> PathValidationResult | None:
    """A fixed pose excludes rotation and intermediate excursions as well as translation."""
    violation: PathConstraintViolation | None = None
    if path[0] != model.pose:
        violation = PathConstraintViolation(
            "starting_pose_mismatch",
            "Path witness must start at the moving model pose.",
            model_id=model.model_id,
        )
    elif pose_is_fixed and any(pose != model.pose for pose in path):
        violation = PathConstraintViolation(
            "model_pose_fixed",
            "The moving model must retain its pose throughout the path.",
            model_id=model.model_id,
        )
    elif not distance.is_within_budget:
        violation = PathConstraintViolation(
            "movement_distance_exceeded",
            "Path witness exceeds the movement distance budget.",
            model_id=model.model_id,
        )
    if violation is None:
        return None
    return PathValidationResult.invalid(
        violation,
        sampled_pose_count=len(path),
        model_collision_check_count=0,
        terrain_collision_check_count=0,
        engagement_check_count=0,
        movement_distance_witness=distance,
    )
