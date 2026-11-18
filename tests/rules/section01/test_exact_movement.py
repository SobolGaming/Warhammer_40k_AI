from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest

from warhammer40k_core.engine.exact_movement import (
    ExactBattlefieldState,
    ExactModelPlacement,
    ExactMovementError,
    apply_exact_movement,
)
from warhammer40k_core.geometry.exact_contact import ExactDisk, rational_anchor_contact_centers
from warhammer40k_core.geometry.exact_coordinate import (
    ExactCoordinate,
    ExactCoordinateError,
    UnsupportedExactCoordinateError,
    rational_coordinate,
)
from warhammer40k_core.geometry.exact_path import (
    ExactDiskSweep,
    ExactPathWitness,
    exact_path_travel_ticks,
)
from warhammer40k_core.geometry.exact_pose import ExactPose
from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.pose import GeometryError, Pose, PosePayload


def pose(x: int | str, y: int | str) -> ExactPose:
    return ExactPose(rational_coordinate(Fraction(x)), rational_coordinate(Fraction(y)))


def battlefield(*placements: ExactModelPlacement) -> ExactBattlefieldState:
    return ExactBattlefieldState(
        10_000, 10_000, tuple(sorted(placements, key=lambda placement: placement.model_instance_id))
    )


def witness(state: ExactBattlefieldState, *waypoints: ExactPose) -> ExactPathWitness:
    return ExactPathWitness(state.content_hash, "mover", waypoints)


def test_half_tick_contact_commits_authoritative_pose_and_preserves_replay_input() -> None:
    anchor = ExactModelPlacement("anchor", 1000, pose(2, 2))
    mover = ExactModelPlacement("mover", 1001, pose(4, 2))
    state = battlefield(anchor, mover)
    endpoint = pose("3.0005", 2)
    path = witness(state, mover.pose, endpoint)

    result = apply_exact_movement(
        state,
        model_instance_id="mover",
        witness=path,
        budget_ticks=1000,
        required_contact_ids=("anchor",),
    )
    assert result.travel_ticks == 1000
    assert result.state.placements == (anchor, replace(mover, pose=endpoint))
    assert (
        result.state.placements[1].disk.relation_to(anchor.disk) is CircleRelation.EXTERNAL_CONTACT
    )
    assert result.state.content_hash != state.content_hash
    assert state.placements == (anchor, mover)

    restored_source = ExactBattlefieldState.from_payload(json.loads(json.dumps(state.to_payload())))
    restored_end = ExactBattlefieldState.from_payload(
        json.loads(json.dumps(result.state.to_payload()))
    )
    retained_path = ExactPathWitness.from_payload(
        json.loads(json.dumps(result.witness.to_payload()))
    )
    assert restored_end == result.state
    assert restored_end.content_hash == result.state.content_hash
    assert retained_path == path
    assert (
        apply_exact_movement(
            restored_source,
            model_instance_id="mover",
            witness=retained_path,
            budget_ticks=1000,
            required_contact_ids=("anchor",),
        )
        == result
    )


def test_half_tick_above_inclusive_budget_is_rejected() -> None:
    anchor = ExactModelPlacement("anchor", 1000, pose(2, 2))
    mover = ExactModelPlacement("mover", 1001, pose("4.001", 2))
    state = battlefield(anchor, mover)
    path = witness(state, mover.pose, pose("3.0005", 2))

    with pytest.raises(ExactMovementError, match="exceeds"):
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=path,
            budget_ticks=1000,
            required_contact_ids=("anchor",),
        )
    assert state.placements[1].pose == mover.pose
    assert (
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=path,
            budget_ticks=1001,
            required_contact_ids=("anchor",),
        ).travel_ticks
        == 1001
    )


def test_quadratic_simultaneous_contact_survives_subdivision_and_restoration() -> None:
    left = ExactModelPlacement("anchor-left", 1000, pose(2, 2))
    right = ExactModelPlacement("anchor-right", 1000, pose(4, 2))
    mover = ExactModelPlacement("mover", 1001, pose(3, 4))
    state = battlefield(left, right, mover)
    upper, _ = rational_anchor_contact_centers(left.disk, right.disk, mover.diameter_ticks)
    endpoint = ExactPose(*upper.center)
    assert endpoint.y == ExactCoordinate.from_root(Fraction(2), Fraction(1, 2000), Fraction(4001))
    midpoint = ExactPose(
        endpoint.x, (mover.pose.y + endpoint.y) * rational_coordinate(Fraction(1, 2))
    )
    contacts = ("anchor-left", "anchor-right")
    direct = apply_exact_movement(
        state,
        model_instance_id="mover",
        witness=witness(state, mover.pose, endpoint),
        budget_ticks=2000,
        required_contact_ids=contacts,
    )
    split = apply_exact_movement(
        state,
        model_instance_id="mover",
        witness=witness(state, mover.pose, midpoint, endpoint),
        budget_ticks=2000,
        required_contact_ids=contacts,
    )
    assert direct.travel_ticks == split.travel_ticks == 1968
    assert direct.state == split.state
    assert (
        ExactBattlefieldState.from_payload(split.state.to_payload()).placements[-1].pose == endpoint
    )
    assert ExactPathWitness.from_payload(split.witness.to_payload()).waypoints[1] == midpoint


def test_clear_endpoints_cannot_authorize_a_blocked_path() -> None:
    blocker = ExactModelPlacement("blocker", 1000, pose(4, 2))
    mover = ExactModelPlacement("mover", 1000, pose(2, 2))
    state = battlefield(blocker, mover)
    endpoint = pose(6, 2)
    with pytest.raises(ExactMovementError, match="along a segment"):
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=witness(state, mover.pose, endpoint),
            budget_ticks=8000,
        )
    detour = witness(state, mover.pose, pose(2, 4), pose(6, 4), endpoint)
    assert (
        apply_exact_movement(
            state, model_instance_id="mover", witness=detour, budget_ticks=8000
        ).travel_ticks
        == 8000
    )


def test_length_uses_the_complete_path_once_and_counts_backtracking() -> None:
    mover = ExactModelPlacement("mover", 1000, pose(2, 2))
    state = battlefield(mover)
    path = witness(state, mover.pose, pose("2.3335", 2), mover.pose)
    with pytest.raises(ExactMovementError, match="exceeds"):
        apply_exact_movement(state, model_instance_id="mover", witness=path, budget_ticks=666)
    result = apply_exact_movement(state, model_instance_id="mover", witness=path, budget_ticks=667)
    assert result.travel_ticks == 667
    assert result.state == state


def test_board_clearance_uses_all_waypoints_and_radii() -> None:
    mover = ExactModelPlacement("mover", 1001, pose(2, 2))
    state = battlefield(mover)
    endpoint = pose(4, 2)
    path = witness(state, mover.pose, pose("0.5", 2), endpoint)
    with pytest.raises(ExactMovementError, match="footprint leaves"):
        apply_exact_movement(state, model_instance_id="mover", witness=path, budget_ticks=6000)
    tangent = witness(state, mover.pose, pose("0.5005", 2), endpoint)
    assert (
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=tangent,
            budget_ticks=5000,
        ).travel_ticks
        == 4999
    )


def test_rounded_zero_gap_does_not_establish_required_contact() -> None:
    anchor = ExactModelPlacement("anchor", 1000, pose(2, 2))
    mover = ExactModelPlacement("mover", 1001, pose(4, 2))
    state = battlefield(anchor, mover)
    with pytest.raises(ExactMovementError, match="required external contact"):
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=witness(state, mover.pose, pose("3.0006", 2)),
            budget_ticks=1000,
            required_contact_ids=("anchor",),
        )


def test_movement_rejects_missing_wrong_model_stale_and_wrong_start_witnesses() -> None:
    mover = ExactModelPlacement("mover", 1000, pose(2, 2))
    state = battlefield(mover)
    path = witness(state, mover.pose, pose(3, 2))
    with pytest.raises(ExactMovementError, match="full path witness"):
        apply_exact_movement(
            state,
            model_instance_id="mover",
            witness=cast(ExactPathWitness, None),
            budget_ticks=1000,
        )
    with pytest.raises(ExactMovementError, match="different moving model"):
        apply_exact_movement(state, model_instance_id="other", witness=path, budget_ticks=1000)
    changed = replace(state, width_ticks=9000)
    with pytest.raises(ExactMovementError, match="stale"):
        apply_exact_movement(changed, model_instance_id="mover", witness=path, budget_ticks=1000)
    wrong_start = witness(state, pose("2.0001", 2), pose(3, 2))
    with pytest.raises(ExactMovementError, match="authoritative model pose"):
        apply_exact_movement(
            state, model_instance_id="mover", witness=wrong_start, budget_ticks=1000
        )


def test_exact_payloads_reject_mixed_identity_missing_path_and_legacy_pose() -> None:
    mover = ExactModelPlacement("mover", 1000, pose(2, 2))
    state = battlefield(mover)
    payload = witness(state, mover.pose, pose(3, 2)).to_payload()
    with pytest.raises(ExactCoordinateError, match="identity"):
        ExactPathWitness.from_payload(
            payload | {"coordinate_representation_id": "binary-float-pose-v1"}
        )
    with pytest.raises(ExactCoordinateError, match="two exact waypoints"):
        ExactPathWitness.from_payload(payload | {"waypoints": payload["waypoints"][-1:]})
    with pytest.raises(ExactCoordinateError, match="identity"):
        ExactPose.from_payload(Pose.at(2, 2).to_payload())
    with pytest.raises(GeometryError, match="legacy coordinate payload"):
        Pose.from_payload(cast(PosePayload, mover.pose.to_payload()))
    with pytest.raises(ExactMovementError, match="identity"):
        ExactBattlefieldState.from_payload(
            state.to_payload() | {"numerical_policy_id": "legacy-binary-inch-v1"}
        )


def test_unsupported_bent_quadratic_and_vertical_paths_fail_closed() -> None:
    mover = ExactModelPlacement("mover", 1000, pose(2, 2))
    state = battlefield(mover)
    x = ExactCoordinate.from_root(Fraction(2), Fraction(1, 3), Fraction(2))
    y = rational_coordinate(Fraction(2))
    endpoint = pose(4, 3)
    path = witness(state, mover.pose, ExactPose(x, y), endpoint)
    with pytest.raises(UnsupportedExactCoordinateError, match="Bent paths"):
        apply_exact_movement(state, model_instance_id="mover", witness=path, budget_ticks=10_000)
    with pytest.raises(UnsupportedExactCoordinateError, match="fixed elevation"):
        witness(state, mover.pose, replace(endpoint, z=rational_coordinate(Fraction(1))))


def test_exact_travel_rejects_empty_and_disconnected_sweeps() -> None:
    x = ExactCoordinate.from_root(Fraction(2), Fraction(1), Fraction(2))
    y = rational_coordinate(Fraction(2))
    first = ExactDiskSweep(
        ExactDisk((rational_coordinate(Fraction(1)), y), 1000),
        ExactDisk((x, y), 1000),
    )
    second = ExactDiskSweep(
        ExactDisk((rational_coordinate(Fraction(3)), y), 1000),
        ExactDisk((rational_coordinate(Fraction(4)), y), 1000),
    )
    with pytest.raises(ExactCoordinateError, match="nonempty"):
        exact_path_travel_ticks(())
    with pytest.raises(ExactCoordinateError, match="connected"):
        exact_path_travel_ticks((first, second))
