from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    fight_rules_unit_movement_endpoint_from_completed_event,
    rules_unit_views_for_completed_move_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload
from warhammer40k_core.geometry.pose import Pose, PosePayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def completed_move_model_placements(
    *, state: GameState, event: EventRecord
) -> tuple[ModelPlacement, ...]:
    """Read physical endpoints from the accepted move, independently of live presence."""
    payload = event.payload
    if not isinstance(payload, dict) or type(payload.get("unit_instance_id")) is not str:
        raise GameLifecycleError("Move endpoint evidence requires its moving unit.")
    views = rules_unit_views_for_completed_move_event(
        state=state,
        event_type=event.event_type,
        unit_instance_id=cast(str, payload["unit_instance_id"]),
    )
    component_ids = tuple(
        sorted({identifier for view in views for identifier in view.component_unit_instance_ids})
    )
    if event.event_type == "fight_movement_completed":
        return fight_rules_unit_movement_endpoint_from_completed_event(
            payload=payload, component_unit_instance_ids=component_ids
        ).model_placements
    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Move endpoint evidence requires its transition batch.")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    poses: dict[str, Pose]
    if event.event_type in {"unit_disembarked", "reinforcement_unit_arrived"}:
        if transition.displacements or transition.removals or not transition.placements:
            raise GameLifecycleError("Set-up endpoint evidence requires placement records.")
        poses = {row.model_instance_id: row.pose for row in transition.placements}
    elif event.event_type == "movement_activation_completed":
        raw_witness = payload.get("witness")
        if not isinstance(raw_witness, dict):
            raise GameLifecycleError("Movement endpoint evidence requires its PathWitness.")
        witness = PathWitness.from_payload(cast(PathWitnessPayload, raw_witness))
        poses = {model_id: path[-1] for model_id, path in witness.model_paths}
    elif event.event_type in {
        "charge_move_completed",
        "triggered_movement_resolved",
        "heroic_intervention_charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    }:
        poses = _model_movement_endpoints(payload)
    else:
        raise GameLifecycleError("Move endpoint evidence has an unsupported source event.")
    for displacement in transition.displacements:
        if poses.get(displacement.model_instance_id) != displacement.end_pose:
            raise GameLifecycleError("Move endpoint differs from its accepted displacement.")
    removed = {row.model_instance_id for row in transition.removals}
    owners = {
        model.model_instance_id: (army, unit)
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    }
    if not set(poses).issubset(owners):
        raise GameLifecycleError("Move endpoint model ownership drift.")
    return tuple(
        ModelPlacement(
            army_id=owners[model_id][0].army_id,
            player_id=owners[model_id][0].player_id,
            unit_instance_id=owners[model_id][1].unit_instance_id,
            model_instance_id=model_id,
            pose=pose,
            split_origin=owners[model_id][1].split_origin,
        )
        for model_id, pose in sorted(poses.items())
        if model_id not in removed
    )


def _model_movement_endpoints(payload: dict[str, JsonValue]) -> dict[str, Pose]:
    rows = payload.get("model_movements")
    if not isinstance(rows, list) or not rows:
        raise GameLifecycleError("Move endpoint evidence requires per-model movements.")
    poses: dict[str, Pose] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or type(row.get("model_instance_id")) is not str
            or not isinstance(row.get("end_pose"), dict)
        ):
            raise GameLifecycleError("Move endpoint evidence has an invalid model movement.")
        model_id = cast(str, row["model_instance_id"])
        if model_id in poses:
            raise GameLifecycleError("Move endpoint model evidence is duplicated.")
        poses[model_id] = Pose.from_payload(cast(PosePayload, row["end_pose"]))
    return poses
