"""Admit native pre-roll Charge flight offers without claiming route proof."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from sys import float_info

from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRoute
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phases.charge_modifier_ignore import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
)


class ChargeFlightUnresolvedReason(StrEnum):
    NOT_ORDINARY_CHARGE_OFFER = "not_ordinary_charge_offer"
    UNSUPPORTED_MOVER = "unsupported_mover"
    UNSUPPORTED_MODE_PAIR = "unsupported_mode_pair"
    UNADMITTED_TARGET = "unadmitted_target"
    MINIMUM_ROLL_UNPROVEN = "minimum_roll_unproven"


@dataclass(frozen=True, slots=True)
class ChargeFlightOffer:
    request_id: str
    observation_hash: str
    unit_id: str
    model_id: str
    target_id: str
    ground_option_id: str
    flight_option_id: str
    flight_penalty_inches: float
    # This is the native target filter distance, not a measured path or minimum roll.
    target_filter_distance_inches: float


@dataclass(frozen=True, slots=True)
class ChargeFlightUnresolved:
    reason: ChargeFlightUnresolvedReason
    offer: ChargeFlightOffer | None = None


def inspect_charge_flight_offer(
    context: PlayerDecisionContext, *, unit_id: str, target_id: str
) -> ChargeFlightUnresolved:
    """Read only actor-visible declaration evidence for an already fixed unit and target.

    Even an admitted offer does not certify a minimum roll or a mode preference.
    This boundary cannot submit decisions and has no session, RNG or replay input.
    """
    reason = ChargeFlightUnresolvedReason
    actor = context.route.actor_id
    if context.route != PolicyRoute(
        actor, SELECT_CHARGING_UNIT_DECISION_TYPE, "battle", None, "charge", None
    ):
        return ChargeFlightUnresolved(reason.NOT_ORDINARY_CHARGE_OFFER)

    view = context.observation
    request = context.request
    options = request["options"]
    # The ordinary request always offers completion; interrupted charges do not.
    if not any(
        row["option_id"] == COMPLETE_CHARGE_PHASE_OPTION_ID
        and isinstance(row["payload"], dict)
        and row["payload"].get("submission_kind") == COMPLETE_CHARGE_PHASE_OPTION_ID
        for row in options
    ):
        return ChargeFlightUnresolved(reason.NOT_ORDINARY_CHARGE_OFFER)

    field = view["battlefield_view"]
    unit = view["unit_display_by_id"].get(unit_id)
    if (
        unit is None
        or field is None
        or unit["visible_status"] != "visible"
        or unit["owner_player_id"] != actor
        or len(unit["model_instance_ids"]) != 1
        or {"HOVER", "AIRCRAFT"}.intersection(unit["keywords"])
    ):
        return ChargeFlightUnresolved(reason.UNSUPPORTED_MOVER)
    (model_id,) = unit["model_instance_ids"]
    model = view["model_display_by_id"].get(model_id)
    placements = field["authoritative"]["models_by_id"]
    physical = placements.get(model_id)
    if (
        model is None
        or model["visible_status"] != "visible"
        or model["unit_instance_id"] != unit_id
        or "FLY" not in model["keywords"]
        or physical is None
        or physical["unit_instance_id"] != unit_id
        or physical["rules_unit_instance_id"] != unit_id
        or physical["owner_player_id"] != actor
        or physical["state"] != "placed"
        or physical["pose"] is None
        or any(
            key != model_id and item["rules_unit_instance_id"] == unit_id
            for key, item in placements.items()
        )
    ):
        return ChargeFlightUnresolved(reason.UNSUPPORTED_MOVER)

    modes: dict[bool, tuple[str, float, JsonValue]] = {}
    for row in options:
        payload = row["payload"]
        if not isinstance(payload, dict) or payload.get("unit_instance_id") != unit_id:
            continue
        mode = payload.get("take_to_the_skies")
        penalty = _nonnegative_inches(payload.get("flight_penalty_inches"))
        if (
            payload.get("submission_kind") != SELECT_CHARGING_UNIT_DECISION_TYPE
            or payload.get("flying_model_instance_ids") != [model_id]
            or "modifier_ignore_context" in payload
            or not isinstance(mode, bool)
            or mode in modes
            or penalty is None
            or (penalty > 0) != mode
        ):
            return ChargeFlightUnresolved(reason.UNSUPPORTED_MODE_PAIR)
        modes[mode] = row["option_id"], penalty, payload.get("eligibility_context")
    if modes.keys() != {False, True}:
        return ChargeFlightUnresolved(reason.UNSUPPORTED_MODE_PAIR)
    ground_id, _, eligibility = modes[False]
    flight_id, flight_penalty, flight_eligibility = modes[True]
    if ground_id == flight_id or eligibility != flight_eligibility:
        return ChargeFlightUnresolved(reason.UNSUPPORTED_MODE_PAIR)

    target_distance = _target_filter_distance(eligibility, target_id)
    target = view["unit_display_by_id"].get(target_id)
    if (
        target_distance is None
        or target is None
        or target["visible_status"] != "visible"
        or target["owner_player_id"] not in view["player_ids"]
        or target["owner_player_id"] == actor
        or not any(
            item["rules_unit_instance_id"] == target_id
            and item["owner_player_id"] == target["owner_player_id"]
            and item["state"] == "placed"
            and item["pose"] is not None
            for item in placements.values()
        )
    ):
        return ChargeFlightUnresolved(reason.UNADMITTED_TARGET)
    return ChargeFlightUnresolved(
        reason.MINIMUM_ROLL_UNPROVEN,
        ChargeFlightOffer(
            request["request_id"],
            context.observation_hash,
            unit_id,
            model_id,
            target_id,
            ground_id,
            flight_id,
            flight_penalty,
            target_distance,
        ),
    )


def _nonnegative_inches(value: JsonValue) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= float_info.max
    ):
        return float(value)
    return None


def _target_filter_distance(eligibility: JsonValue, target_id: str) -> float | None:
    if not isinstance(eligibility, dict):
        return None
    candidates = eligibility.get("target_candidates")
    if not isinstance(candidates, list):
        return None
    matched = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("target_unit_instance_id") == target_id
    ]
    if len(matched) != 1 or matched[0].get("is_legal") is not True:
        return None
    return _nonnegative_inches(matched[0].get("closest_distance_inches"))
