"""Small, actor-view ground movement search for Stage 2 comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import sqrt
from typing import cast

from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyRoute,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeStatePayload
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    FallBackModeKind,
    MovementPhaseActionKind,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

_MAX_MOVING_MODELS = 5
_MAX_VISIBLE_MODELS = 256
_MAX_ACTION_OPTIONS = 8
_DIAGONAL = sqrt(0.5)
_SHALLOW_MAJOR = 8 / sqrt(73)
_SHALLOW_MINOR = 3 / sqrt(73)
_DIRECTIONS = (
    (1.0, 0.0),
    (_SHALLOW_MAJOR, -_SHALLOW_MINOR),
    (_SHALLOW_MAJOR, _SHALLOW_MINOR),
    (0.0, 1.0),
    (_SHALLOW_MINOR, _SHALLOW_MAJOR),
    (-_SHALLOW_MINOR, _SHALLOW_MAJOR),
    (-1.0, 0.0),
    (-_SHALLOW_MAJOR, _SHALLOW_MINOR),
    (-_SHALLOW_MAJOR, -_SHALLOW_MINOR),
    (0.0, -1.0),
    (-_SHALLOW_MINOR, -_SHALLOW_MAJOR),
    (_SHALLOW_MINOR, -_SHALLOW_MAJOR),
    (_DIAGONAL, _DIAGONAL),
    (-_DIAGONAL, _DIAGONAL),
    (-_DIAGONAL, -_DIAGONAL),
    (_DIAGONAL, -_DIAGONAL),
)
_DISTANCE_FRACTIONS = (0.875, 0.75)
_MAX_TRANSLATION_PROPOSALS = len(_DIRECTIONS) * len(_DISTANCE_FRACTIONS)
MAX_RETREAT_PROPOSALS = _MAX_TRANSLATION_PROPOSALS
MAX_NORMAL_MOVE_PROPOSALS = _MAX_TRANSLATION_PROPOSALS


class ScreenMovementGapReason(StrEnum):
    NO_HOLD_RETREAT_OFFER = "no_hold_retreat_offer"
    NO_ORDINARY_FALL_BACK_REQUEST = "no_ordinary_fall_back_request"
    NO_ORDINARY_NORMAL_MOVE_REQUEST = "no_ordinary_normal_move_request"
    UNSUPPORTED_FORMATION = "unsupported_formation"
    CANDIDATE_LIMIT = "candidate_limit"
    NO_TRANSLATION = "no_translation"


class ScreenMovementGap(CandidateExhaustedError):
    def __init__(self, reason: ScreenMovementGapReason) -> None:
        super().__init__(f"Screen movement candidate gap: {reason.value}.")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ScreenMovementOptions:
    hold: PolicyAction
    fall_back: tuple[tuple[FallBackModeKind, PolicyAction], ...]


def generate_screen_movement_options(context: PlayerDecisionContext) -> ScreenMovementOptions:
    """Retain the pending unit's Hold and issued ordinary Fall Back modes."""
    route = PolicyRoute(
        context.route.actor_id,
        SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        "battle",
        None,
        "movement",
        None,
    )
    if context.route != route:
        raise ScreenMovementGap(ScreenMovementGapReason.NO_HOLD_RETREAT_OFFER)
    request = context.request
    payload = request["payload"]
    if not isinstance(payload, dict) or not isinstance(payload.get("unit_instance_id"), str):
        raise ScreenMovementGap(ScreenMovementGapReason.NO_HOLD_RETREAT_OFFER)
    if len(request["options"]) > _MAX_ACTION_OPTIONS:
        raise ScreenMovementGap(ScreenMovementGapReason.CANDIDATE_LIMIT)
    finite = FiniteCandidateSet.from_context(context)
    hold: PolicyAction | None = None
    fall_back: list[tuple[FallBackModeKind, PolicyAction]] = []
    for candidate in finite.candidates:
        option = candidate.option
        choice = option["payload"]
        if (
            not isinstance(choice, dict)
            or choice.get("unit_instance_id") != payload["unit_instance_id"]
        ):
            continue
        action = choice.get("movement_phase_action")
        if action == MovementPhaseActionKind.REMAIN_STATIONARY:
            hold = context.select_option(option["option_id"])
        if (
            action == MovementPhaseActionKind.FALL_BACK
            and choice.get("movement_mode") == MovementMode.FALL_BACK
        ):
            for mode in FallBackModeKind:
                if choice.get("fall_back_mode") == mode:
                    fall_back.append((mode, context.select_option(option["option_id"])))
    if hold is None or not fall_back:
        raise ScreenMovementGap(ScreenMovementGapReason.NO_HOLD_RETREAT_OFFER)
    return ScreenMovementOptions(hold, tuple(fall_back))


def generate_retreat_proposals(context: PlayerDecisionContext) -> tuple[PolicyAction, ...]:
    """Build rigid, planar Fall Back proposals in the issued retreat mode."""
    return _generate_translation_proposals(
        context,
        kind=ProposalKind.FALL_BACK,
        action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        route_gap=ScreenMovementGapReason.NO_ORDINARY_FALL_BACK_REQUEST,
    )


def generate_normal_move_proposals(context: PlayerDecisionContext) -> tuple[PolicyAction, ...]:
    """Build ordinary Normal Move alternatives from the pending actor request.

    Select between the issued Normal Move and Hold on the preceding finite
    request. These unranked paths are not legality claims: native submission
    owns the effective budget, traversal, engagement and coherency checks.
    """
    return _generate_translation_proposals(
        context,
        kind=ProposalKind.NORMAL_MOVE,
        action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        route_gap=ScreenMovementGapReason.NO_ORDINARY_NORMAL_MOVE_REQUEST,
    )


def _generate_translation_proposals(
    context: PlayerDecisionContext,
    *,
    kind: ProposalKind,
    action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    route_gap: ScreenMovementGapReason,
) -> tuple[PolicyAction, ...]:
    actor = context.route.actor_id
    route = PolicyRoute(
        actor, MOVEMENT_PROPOSAL_DECISION_TYPE, "battle", None, "movement", kind.value
    )
    if context.route != route:
        raise ScreenMovementGap(route_gap)
    view = context.observation
    request = view["pending_decision"]
    assert request is not None
    issued = MovementProposalRequest.from_decision_request_payload(request["payload"])
    details = issued.context
    if (
        issued.actor_id != actor
        or issued.request_id != request["request_id"]
        or issued.proposal_kind is not kind
        or issued.movement_phase_action != action
        or details is None
        or details.get("movement_mode") != movement_mode
    ):
        raise ScreenMovementGap(route_gap)

    fall_back_mode = None
    if kind is ProposalKind.FALL_BACK:
        mode = details.get("fall_back_mode")
        if not isinstance(mode, str) or mode not in tuple(FallBackModeKind):
            raise ScreenMovementGap(route_gap)
        fall_back_mode = mode

    battlefield = view["battlefield_view"]
    if battlefield is None or not isinstance(view["battlefield_state"], dict):
        raise ScreenMovementGap(ScreenMovementGapReason.UNSUPPORTED_FORMATION)
    models = battlefield["authoritative"]["models_by_id"]
    if len(models) > _MAX_VISIBLE_MODELS:
        raise ScreenMovementGap(ScreenMovementGapReason.CANDIDATE_LIMIT)
    movers = tuple(
        model
        for model in models.values()
        if model["rules_unit_instance_id"] == issued.unit_instance_id and model["state"] == "placed"
    )
    if not 1 <= len(movers) <= _MAX_MOVING_MODELS:
        raise ScreenMovementGap(ScreenMovementGapReason.UNSUPPORTED_FORMATION)
    starts: list[tuple[str, Pose]] = []
    distances: list[int] = []
    for mover in movers:
        model_id = mover["model_instance_id"]
        pose = mover["pose"]
        display = view["model_display_by_id"].get(model_id)
        if mover["owner_player_id"] != actor or pose is None or display is None:
            raise ScreenMovementGap(ScreenMovementGapReason.UNSUPPORTED_FORMATION)
        position = pose["position"]
        movement = display["current_characteristics"]["M"]["final"]
        if position["z_inches"] != 0 or movement is None or movement <= 0:
            raise ScreenMovementGap(ScreenMovementGapReason.UNSUPPORTED_FORMATION)
        starts.append(
            (
                model_id,
                Pose.at(position["x_inches"], position["y_inches"], 0, pose["facing_degrees"]),
            )
        )
        distances.append(movement)

    board = cast(BattlefieldRuntimeStatePayload, view["battlefield_state"])
    width, depth = board["battlefield_width_inches"], board["battlefield_depth_inches"]
    actor_hash = context.observation_hash
    proposals: list[PolicyAction] = []
    shortest_move = min(distances)
    for fraction in _DISTANCE_FRACTIONS:
        distance = shortest_move * fraction
        for x, y in _DIRECTIONS:
            endpoints = tuple(
                (
                    model_id,
                    start,
                    Pose.at(
                        start.position.x + x * distance,
                        start.position.y + y * distance,
                        0,
                        start.facing.degrees,
                    ),
                )
                for model_id, start in starts
            )
            if not all(
                0 < end.position.x < width and 0 < end.position.y < depth for _, _, end in endpoints
            ):
                continue
            proposal = MovementProposalPayload(
                issued.request_id,
                kind,
                issued.unit_instance_id,
                action.value,
                PathWitness.for_straight_line_endpoints(endpoints),
                movement_mode=movement_mode.value,
                fall_back_mode=fall_back_mode,
            )
            proposals.append(
                PolicyAction(
                    actor,
                    issued.request_id,
                    actor_hash,
                    None,
                    canonical_json(proposal.to_payload()),
                )
            )
    if not proposals:
        raise ScreenMovementGap(ScreenMovementGapReason.NO_TRANSLATION)
    return tuple(proposals)
