"""Qualify fixed Normal Move paths on native forks before dispatching a mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRoute,
    payload_digest,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceBudget,
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

FLIGHT_NORMAL_MOVE_POLICY_ID = "flight-normal-move-v2"
_GROUND = MovementMode.NORMAL
_FLIGHT = MovementMode.FLY_TAKE_TO_SKIES
_NORMAL_MOVE = MovementPhaseActionKind.NORMAL_MOVE


class FlightNormalMoveGapReason(StrEnum):
    OFFER = "unsupported_normal_move_offer"
    MOVER = "unsupported_flying_model"
    OBSERVATION = "unadmitted_observation"
    CHECKPOINT = "unadmitted_checkpoint"
    BUDGET = "unsupported_movement_budget"
    WITNESS = "unadmitted_fixed_destination_witness"
    RECEIPT = "unqualified_native_movement_receipt"
    GROUND_UNRESOLVED = "ground_route_unresolved"
    FLIGHT_UNWITNESSED = "flight_route_unwitnessed"


class FlightNormalMoveGap(CandidateExhaustedError):
    def __init__(self, reason: FlightNormalMoveGapReason) -> None:
        super().__init__(f"Flight Normal Move gap: {reason.value}.")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class FlightNormalMoveChoice:
    action: PolicyAction
    mode: MovementMode
    witness: PathWitness


@dataclass(frozen=True, slots=True)
class PreparedFlightNormalMove:
    choice: FlightNormalMoveChoice
    registration: PolicyRegistration


@dataclass(frozen=True, slots=True)
class _FlightOffer:
    unit_id: str
    model_id: str
    start: Pose
    options: dict[MovementMode, str]


@dataclass(frozen=True, slots=True)
class _NativeRoute:
    accepted: bool
    violation: str | None
    measured: MovementDistanceWitness
    budget: MovementDistanceBudget


def _normal_move_offer(context: PlayerDecisionContext) -> _FlightOffer:
    actor = context.route.actor_id
    route = PolicyRoute(
        actor, SELECT_MOVEMENT_ACTION_DECISION_TYPE, "battle", None, "movement", None
    )
    if context.route != route:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)
    request = context.request
    payload = request["payload"]
    unit_id = payload.get("unit_instance_id") if isinstance(payload, dict) else None
    if not isinstance(unit_id, str):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)
    options: dict[MovementMode, str] = {}
    modes = (_GROUND, _FLIGHT)
    for option in request["options"]:
        details = option["payload"]
        if not isinstance(details, dict) or details.get("movement_phase_action") != _NORMAL_MOVE:
            continue
        for mode in modes:
            if details.get("movement_mode") == mode:
                if mode in options or details.get("unit_instance_id") != unit_id:
                    raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)
                options[mode] = option["option_id"]
    if set(options) != set(modes):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)

    view = context.observation
    unit = view["unit_display_by_id"].get(unit_id)
    field = view["battlefield_view"]
    if (
        unit is None
        or field is None
        or (unit["owner_player_id"] != actor or len(unit["model_instance_ids"]) != 1)
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.MOVER)
    (model_id,) = unit["model_instance_ids"]
    model = view["model_display_by_id"].get(model_id)
    placements = field["authoritative"]["models_by_id"]
    physical = placements.get(model_id)
    if (
        model is None
        or model["unit_instance_id"] != unit_id
        or "FLY" not in model["keywords"]
        or "HOVER" in unit["keywords"]
        or "AIRCRAFT" in unit["keywords"]
        or physical is None
        or physical["owner_player_id"] != actor
        or physical["rules_unit_instance_id"] != unit_id
        or physical["state"] != "placed"
        or physical["pose"] is None
        or any(
            other_id != model_id and other["rules_unit_instance_id"] == unit_id
            for other_id, other in placements.items()
        )
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.MOVER)
    position = physical["pose"]["position"]
    start = Pose.at(
        position["x_inches"],
        position["y_inches"],
        position["z_inches"],
        facing_degrees=physical["pose"]["facing_degrees"],
    )

    return _FlightOffer(unit_id, model_id, start, options)


def _probe_normal_move(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    offer: _FlightOffer,
    *,
    checkpoint_hash: str,
    mode: MovementMode,
    path: PathWitness,
) -> _NativeRoute:
    fork = session.fork()
    if payload_digest(fork.to_persistence_payload()) != checkpoint_hash:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.CHECKPOINT)
    viewer = ViewerContext.for_player(context.route.actor_id)
    action = fork.submit_viewer_option(
        viewer=viewer,
        request_id=context.request["request_id"],
        option_id=offer.options[mode],
        result_id="flight-policy:qualify-mode",
    )
    native_request = action.decision_request
    isolated = fork.view_for_context(viewer=viewer)["pending_decision"]
    if (
        action.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION
        or native_request is None
        or isolated is None
        or isolated["decision_type"] != MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)
    proposal = MovementProposalRequest.from_decision_request_payload(isolated["payload"])
    if (
        proposal.proposal_kind is not ProposalKind.NORMAL_MOVE
        or proposal.unit_instance_id != offer.unit_id
        or proposal.movement_phase_action != _NORMAL_MOVE
        or proposal.context is None
        or proposal.context.get("source_selected_option_id") != offer.options[mode]
        or proposal.context.get("movement_mode") != mode
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OFFER)
    histories = fork.lifecycle.decision_controller.event_log
    first_event = len(histories.records)
    result = fork.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=isolated["request_id"],
        result_id="flight-policy:qualify-path",
        payload=validate_json_value(
            MovementProposalPayload(
                isolated["request_id"],
                ProposalKind.NORMAL_MOVE,
                offer.unit_id,
                _NORMAL_MOVE.value,
                path,
                movement_mode=mode.value,
            ).to_payload()
        ),
    )
    accepted = result.status_kind in (
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    )
    event_type = "movement_activation_completed" if accepted else "movement_proposal_invalid"
    receipts = [
        event.payload
        for event in histories.records[first_event:]
        if event.event_type == event_type
        and isinstance(event.payload, dict)
        and event.payload.get("proposal_request_id") == native_request.request_id
    ]
    if len(receipts) != 1 or result.status_kind is LifecycleStatusKind.UNSUPPORTED:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.RECEIPT)
    (receipt,) = receipts
    if (
        receipt.get("active_player_id") != context.route.actor_id
        or receipt.get("unit_instance_id") != offer.unit_id
        or receipt.get("movement_phase_action") != _NORMAL_MOVE
        or receipt.get("movement_mode") != mode
        or (accepted and receipt.get("witness") != path.to_payload())
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.RECEIPT)
    moves = receipt.get("model_movements")
    if not isinstance(moves, list) or len(moves) != 1 or not isinstance(moves[0], dict):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.RECEIPT)
    move = moves[0]
    final = path.final_pose_for_model(offer.model_id)
    distance_payload = move.get("movement_distance_witness")
    if (
        move.get("model_instance_id") != offer.model_id
        or move.get("movement_mode") != mode
        or move.get("start_pose") != offer.start.to_payload()
        or move.get("end_pose") != final.to_payload()
        or not isinstance(distance_payload, dict)
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.RECEIPT)
    measured = MovementDistanceWitness.from_certified_payload(
        cast(MovementDistanceWitnessPayload, distance_payload)
    )
    budget = measured.budget
    if (
        measured.model_id != offer.model_id
        or budget is None
        or (accepted and not budget.is_within_budget)
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.BUDGET)
    violation = receipt.get("violation_code")
    return _NativeRoute(
        accepted, violation if isinstance(violation, str) else None, measured, budget
    )


def _ground_proven_over_budget(
    route: _NativeRoute, ground_path: PathWitness, offer: _FlightOffer, destination: Pose
) -> bool:
    # The normal move validator fixes its vertical-distance mode before measuring a path.
    # An unflattened direct native measurement certifies 3D counting at this checkpoint.
    return (
        route.violation == "movement_distance_exceeded"
        and not route.budget.is_within_budget
        and ground_path.poses_for_model(offer.model_id) == (offer.start, destination)
        and len(route.measured.segments) == 1
        and route.measured.segments[0].start_pose == offer.start
        and route.measured.segments[0].end_pose == destination
        and offer.start.position.z != destination.position.z
        and offer.start.distance_3d_to(destination) > route.budget.max_distance_inches + 0.001
    )


@dataclass(frozen=True, slots=True)
class _FlightNormalMovePolicy:
    action: PolicyAction

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        if (
            context.route.actor_id != self.action.actor_id
            or context.observation_hash != self.action.observation_hash
            or context.request["request_id"] != self.action.request_id
        ):
            raise FlightNormalMoveGap(FlightNormalMoveGapReason.OBSERVATION)
        return self.action


@dataclass(frozen=True, slots=True)
class _BoundFlightRegistration(PolicyRegistration):
    _origin_checkpoint_hash: str = field(kw_only=True, repr=False)

    def __post_init__(self) -> None:
        PolicyRegistration.__post_init__(self)
        if self.required_checkpoint_hash != self._origin_checkpoint_hash:
            raise FlightNormalMoveGap(FlightNormalMoveGapReason.CHECKPOINT)


def prepare_flight_normal_move(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    destination: Pose,
    ground_path: PathWitness | None,
    flight_path: PathWitness | None,
) -> PreparedFlightNormalMove:
    """Qualify two explicit paths on disposable native forks of the live checkpoint."""
    offer = _normal_move_offer(context)
    if (
        payload_digest(session.view(viewer_player_id=context.route.actor_id))
        != context.observation_hash
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.OBSERVATION)
    if ground_path is None:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.GROUND_UNRESOLVED)
    if flight_path is None:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.FLIGHT_UNWITNESSED)
    for path in (ground_path, flight_path):
        if (
            path.model_ids() != (offer.model_id,)
            or path.poses_for_model(offer.model_id)[0] != offer.start
            or path.final_pose_for_model(offer.model_id) != destination
        ):
            raise FlightNormalMoveGap(FlightNormalMoveGapReason.WITNESS)
    checkpoint_hash = payload_digest(session.to_persistence_payload())
    ground = _probe_normal_move(
        session, context, offer, checkpoint_hash=checkpoint_hash, mode=_GROUND, path=ground_path
    )
    if not ground.accepted and not _ground_proven_over_budget(
        ground, ground_path, offer, destination
    ):
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.GROUND_UNRESOLVED)
    flight = _probe_normal_move(
        session, context, offer, checkpoint_hash=checkpoint_hash, mode=_FLIGHT, path=flight_path
    )
    if not flight.accepted:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.FLIGHT_UNWITNESSED)
    ground_budget = ground.budget.max_distance_inches
    flight_budget = flight.budget.max_distance_inches
    if not 0 < flight_budget < ground_budget:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.BUDGET)
    if payload_digest(session.to_persistence_payload()) != checkpoint_hash:
        raise FlightNormalMoveGap(FlightNormalMoveGapReason.CHECKPOINT)
    mode, witness = (_GROUND, ground_path) if ground.accepted else (_FLIGHT, flight_path)
    choice = FlightNormalMoveChoice(context.select_option(offer.options[mode]), mode, witness)
    registration = _BoundFlightRegistration(
        context.route,
        FLIGHT_NORMAL_MOVE_POLICY_ID,
        canonical_json(
            {
                "observation_hash": context.observation_hash,
                "destination": destination.to_payload(),
                "ground_budget_inches": ground_budget,
                "flight_budget_inches": flight_budget,
                "movement_mode": mode.value,
                "witness": witness.to_payload(),
            }
        ),
        _FlightNormalMovePolicy(choice.action),
        required_checkpoint_hash=checkpoint_hash,
        _origin_checkpoint_hash=checkpoint_hash,
    )
    return PreparedFlightNormalMove(choice, registration)
