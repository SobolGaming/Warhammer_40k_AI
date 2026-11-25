"""Admit and prove a bounded native pre-roll Charge flight comparison."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
from sys import float_info
from typing import TYPE_CHECKING

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyRoute,
    payload_digest,
)
from warhammer40k_core.core.modifiers import resolve_distance_deltas
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest
from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.charge_required_targets import charge_target_constraints_satisfied
from warhammer40k_core.engine.charge_roll_permissions import charge_reroll_permission_for_unit
from warhammer40k_core.engine.charge_targets import charge_target_candidates
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_budget_modifiers import move_distance_modifiers
from warhammer40k_core.engine.phases.charge import charge_move_violation_code
from warhammer40k_core.engine.phases.charge_modifier_ignore import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    charge_roll_modifiers_for_unit,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import CORE_COMMAND_REROLL_HANDLER_ID
from warhammer40k_core.engine.take_to_the_skies import flight_penalty
from warhammer40k_core.geometry.pose import Pose

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
    from warhammer40k_core.geometry.pathing import PathWitness


class ChargeFlightUnresolvedReason(StrEnum):
    NOT_ORDINARY_CHARGE_OFFER = "not_ordinary_charge_offer"
    UNSUPPORTED_MOVER = "unsupported_mover"
    UNSUPPORTED_MODE_PAIR = "unsupported_mode_pair"
    UNADMITTED_TARGET = "unadmitted_target"
    OBSERVATION_DRIFT = "observation_drift"
    UNSUPPORTED_PROOF_CONTEXT = "unsupported_proof_context"
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


@dataclass(frozen=True, slots=True)
class ChargeFlightModeProof:
    successful_rolls: tuple[int, ...]
    successful_outcomes: int

    @property
    def minimum_roll(self) -> int:
        return self.successful_rolls[0]


@dataclass(frozen=True, slots=True)
class ProvenChargeFlightChoice:
    offer: ChargeFlightOffer
    witness_sha256: str
    ground: ChargeFlightModeProof
    flight: ChargeFlightModeProof
    action: PolicyAction


def choose_proven_charge_flight_mode(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    unit_id: str,
    target_id: str,
    witness: PathWitness,
) -> ProvenChargeFlightChoice | ChargeFlightUnresolved:
    """Choose an issued declaration only with a proof from this live request.

    Trusted, read-only qualification; there are no speculative submissions, forks,
    checkpoint reads or dice observations. The witness is checked, not submitted
    or chosen. Re-run qualification for any other session or request.
    """
    result = inspect_charge_flight_offer(context, unit_id=unit_id, target_id=target_id)
    offer = result.offer
    if offer is None:
        return result

    actor = context.route.actor_id
    lifecycle = session.lifecycle
    state = lifecycle.state
    request = lifecycle.pending_decision_request()
    if (
        state is None
        or request is None
        or request.decision_type != SELECT_CHARGING_UNIT_DECISION_TYPE
        or request.actor_id != actor
        or state.active_player_id != actor
        or not lifecycle.parameterized_movement_proposals
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.OBSERVATION_DRIFT)
    viewer = ViewerContext.for_player(actor)
    if payload_digest(session.view_for_context(viewer=viewer)) != offer.observation_hash:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.OBSERVATION_DRIFT)
    poses = _open_visible_poses(context, offer)
    if poses is None:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)
    if witness.model_ids() != (offer.model_id,):
        return result
    path = witness.poses_for_model(offer.model_id)
    if (
        len(path) != 2
        or path[0] != poses[offer.model_id]
        or path[1].position.z != 0
        or path[1].facing != path[0].facing
    ):
        return result

    # Use the actual active Charge handler, not a reconstructed/default registry.
    handler = lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    scenario = _open_native_scenario(state, poses)
    if scenario is None or not _plain_charge_supported(state, handler, offer, actor):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)
    # The Charge handler supplies route semantics; the live state's ruleset
    # separately owns the movement-budget penalty, just as in native Charge.
    ruleset = handler.ruleset_descriptor
    mover = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    if (
        ruleset is None
        or flight_penalty(unit=mover, ruleset=state.runtime_ruleset_descriptor())
        != offer.flight_penalty_inches
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)
    targets = charge_target_candidates(
        state=state,
        unit_instance_id=unit_id,
        ruleset_descriptor=ruleset,
        charge_target_restriction_hooks=handler.charge_target_restriction_hooks,
    )
    if (
        len(targets) != 1
        or targets[0].target_unit_instance_id != target_id
        or not targets[0].is_legal
        or targets[0].closest_distance_inches != offer.target_filter_distance_inches
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNADMITTED_TARGET)

    spec = ChargeRollRequest(
        request_id=request.request_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=actor,
        unit_instance_id=unit_id,
        source_decision_request_id=request.request_id,
        source_decision_result_id="pre-roll-charge-proof",
    ).spec
    dice = spec.expression
    if (dice.quantity, dice.sides, dice.modifier) != (2, 6, 0):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)
    counts = Counter(
        dice.total(faces) for faces in product(range(1, dice.sides + 1), repeat=dice.quantity)
    )

    ground = _prove_mode(scenario, ruleset, offer, witness, counts, flies=False)
    flight = _prove_mode(scenario, ruleset, offer, witness, counts, flies=True)
    if ground is None or flight is None:
        return result
    if (
        lifecycle.pending_decision_request() != request
        or payload_digest(session.view_for_context(viewer=viewer)) != offer.observation_hash
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.OBSERVATION_DRIFT)
    # Use the exact ordered 2D6 outcome counts and prefer ground on a proven tie.
    option_id = (
        offer.flight_option_id
        if flight.successful_outcomes > ground.successful_outcomes
        else offer.ground_option_id
    )
    return ProvenChargeFlightChoice(
        offer,
        payload_digest(witness.to_payload()),
        ground,
        flight,
        context.select_option(option_id),
    )


def _open_visible_poses(
    context: PlayerDecisionContext, offer: ChargeFlightOffer
) -> dict[str, Pose] | None:
    view = context.observation
    field = view["battlefield_view"]
    if field is None or set(view["unit_display_by_id"]) != {offer.unit_id, offer.target_id}:
        return None
    board = field["authoritative"]
    placements = board["models_by_id"]
    if (
        board["terrain_areas_by_id"]
        or board["terrain_features_by_id"]
        or set(view["model_display_by_id"]) != placements.keys()
        or len(placements) != 2
        or {p["rules_unit_instance_id"] for p in placements.values()}
        != {offer.unit_id, offer.target_id}
    ):
        return None
    poses: dict[str, Pose] = {}
    for model_id, item in placements.items():
        pose = item["pose"]
        if (
            item["state"] != "placed"
            or item["unit_instance_id"] != item["rules_unit_instance_id"]
            or view["model_display_by_id"][model_id]["visible_status"] != "visible"
            or pose is None
            or pose["position"]["z_inches"] != 0
        ):
            return None
        pos = pose["position"]
        poses[model_id] = Pose.at(
            pos["x_inches"], pos["y_inches"], pos["z_inches"], facing_degrees=pose["facing_degrees"]
        )
    return poses


def _open_native_scenario(state: GameState, poses: dict[str, Pose]) -> BattlefieldScenario | None:
    board = state.battlefield_state
    mission = state.mission_setup
    if (
        board is None
        or mission is None
        or mission.terrain_areas
        or board.terrain_features
        or len(state.army_definitions) != 2
        or any(
            len(army.units) != 1 or len(army.units[0].own_models) != 1
            for army in state.army_definitions
        )
        or set(board.placed_model_ids()) != poses.keys()
        or any(
            board.model_placement_by_id(model_id).pose != pose for model_id, pose in poses.items()
        )
    ):
        return None
    scenario = battlefield_scenario_for_state(state=state)
    return None if scenario.present_destroyed_model_ids else scenario


def _plain_charge_supported(
    state: GameState, handler: ChargePhaseHandler, offer: ChargeFlightOffer, actor: str
) -> bool:
    phase = state.charge_phase_state
    registry = handler.runtime_modifier_registry
    if (
        phase is None
        or phase.phase_complete
        or phase.interruption is not None
        or phase.active_selection is not None
        or offer.unit_id in phase.selected_unit_ids
        or handler.charge_declaration_hooks.bindings
        or handler.charge_target_restriction_hooks.bindings
        or registry.charge_roll_modifier_bindings
        or handler.stratagem_cost_modifier_registry.bindings
        or state.command_point_ledger_for_player(actor).command_points != 0
        or state.persisting_effects_for_unit(offer.unit_id)
    ):
        return False
    index = handler.stratagem_index
    if any(
        row.definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID
        and row.definition.command_point_cost == 0
        for row in index.all_records()
    ):
        return False
    abilities = handler.ability_index_for_player(actor)
    mover = rules_unit_view_by_id(state=state, unit_instance_id=offer.unit_id)
    return (
        not charge_roll_modifiers_for_unit(
            state=state,
            ability_index=abilities,
            unit=mover,
            runtime_modifier_registry=registry,
            apply_selection=False,
        )
        and not move_distance_modifiers(state=state, unit_instance_id=offer.unit_id)
        and charge_reroll_permission_for_unit(
            state=state, player_id=actor, unit_instance_id=offer.unit_id, ability_index=abilities
        )
        is None
        and charge_target_constraints_satisfied(
            state=state,
            unit_instance_id=offer.unit_id,
            candidate_target_unit_instance_ids=(offer.target_id,),
        )
    )


def _prove_mode(
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    offer: ChargeFlightOffer,
    witness: PathWitness,
    counts: Counter[int],
    *,
    flies: bool,
) -> ChargeFlightModeProof | None:
    placement = charge_movement_placement(scenario=scenario, unit_instance_id=offer.unit_id)
    penalty = (("take-to-the-skies", -offer.flight_penalty_inches),) if flies else ()
    successes: list[int] = []
    for raw_roll in sorted(counts):
        budget, _ = resolve_distance_deltas(float(raw_roll), penalty)
        # The mandatory native target offer excludes every route below this floor.
        if budget < offer.target_filter_distance_inches:
            continue
        # Above that floor this fixed path must pass for every attainable budget:
        # a rejection is not proof of impossibility, and endpoint rules may vary
        # by budget, so neither an alternative search nor monotonicity is assumed.
        resolution = resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_placement=placement,
            selected_target_unit_instance_ids=(offer.target_id,),
            maximum_distance_inches=budget,
            take_to_the_skies=flies,
            path_witness=witness,
        )
        if (
            charge_move_violation_code(
                resolution=resolution, ruleset_descriptor=ruleset, maximum_distance_inches=budget
            )
            is not None
        ):
            return None
        successes.append(raw_roll)
    if not successes:
        return None
    return ChargeFlightModeProof(tuple(successes), sum(counts[roll] for roll in successes))
