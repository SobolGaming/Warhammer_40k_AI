"""Admit and prove a bounded native pre-roll Charge flight comparison."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
from sys import float_info
from typing import TYPE_CHECKING, Literal

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
from warhammer40k_core.engine.charge_path_contexts import charge_model_path_contexts
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
from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import CORE_COMMAND_REROLL_HANDLER_ID
from warhammer40k_core.engine.take_to_the_skies import flight_penalty
from warhammer40k_core.geometry.base import CircularBase, OvalBase
from warhammer40k_core.geometry.milli_inch import TICKS_PER_INCH
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import classified_feature_transit_permission
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.charge_movement_source import ChargePlacement
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
    BOUNDS_OVERLAP = "bounds_overlap"


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
    def minimum_roll(self) -> int | None:
        return self.successful_rolls[0] if self.successful_rolls else None


@dataclass(frozen=True, slots=True)
class ProvenChargeFlightChoice:
    offer: ChargeFlightOffer
    witness_sha256: str
    ground: ChargeFlightModeProof
    flight: ChargeFlightModeProof
    action: PolicyAction


@dataclass(frozen=True, slots=True)
class ProvenChargeFlightNoSuccess:
    """Both modes are ruled out for this target; do not declare a charge."""

    offer: ChargeFlightOffer
    ground: ChargeFlightModeProof
    flight: ChargeFlightModeProof
    action: None = None


@dataclass(frozen=True, slots=True)
class ChargeFlightRollBound:
    rolls: tuple[int, ...]
    ordered_outcomes: int


@dataclass(frozen=True, slots=True)
class ProvenChargeFlightAdvantage:
    """Flight is better if no additional Command Points are spent on the Charge."""

    offer: ChargeFlightOffer
    witness_sha256: str
    ground_distance_lower_bound_inches: float
    ground_upper_bound: ChargeFlightRollBound
    flight_lower_bound: ChargeFlightRollBound
    action: PolicyAction
    comparison_scope: Literal["no_additional_cp"] = "no_additional_cp"


def choose_proven_charge_flight_mode(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    unit_id: str,
    target_id: str,
    witness: PathWitness,
) -> (
    ProvenChargeFlightChoice
    | ProvenChargeFlightNoSuccess
    | ProvenChargeFlightAdvantage
    | ChargeFlightUnresolved
):
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
    poses = _visible_poses(context, offer)
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
    scenario = _native_scenario(state, poses)
    abilities = handler.ability_index_for_player(actor)
    if scenario is None or not _plain_charge_supported(
        state,
        handler,
        offer,
        actor,
        abilities,
        no_additional_cp=bool(scenario.battlefield_state.terrain_features),
    ):
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

    placement = charge_movement_placement(scenario=scenario, unit_instance_id=offer.unit_id)
    proof: (
        ProvenChargeFlightChoice
        | ProvenChargeFlightNoSuccess
        | ProvenChargeFlightAdvantage
        | ChargeFlightUnresolved
    )
    if scenario.battlefield_state.terrain_features:
        proof = _prove_wall_advantage(
            context, scenario, ruleset, offer, witness, counts, abilities, placement
        )
    else:
        proof = _prove_open_choice(
            context, scenario, ruleset, offer, witness, counts, abilities, placement
        )
    if (
        lifecycle.pending_decision_request() != request
        or payload_digest(session.view_for_context(viewer=viewer)) != offer.observation_hash
    ):
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.OBSERVATION_DRIFT)
    return proof


def _prove_open_choice(
    context: PlayerDecisionContext,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    offer: ChargeFlightOffer,
    witness: PathWitness,
    counts: Counter[int],
    abilities: AbilityCatalogIndex,
    placement: ChargePlacement,
) -> ProvenChargeFlightChoice | ProvenChargeFlightNoSuccess | ChargeFlightUnresolved:
    ground = _prove_mode(
        scenario, ruleset, offer, witness, counts, abilities, placement, flies=False
    )
    flight = _prove_mode(
        scenario, ruleset, offer, witness, counts, abilities, placement, flies=True
    )
    if ground is None or flight is None:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.MINIMUM_ROLL_UNPROVEN, offer)
    if not ground.successful_rolls and not flight.successful_rolls:
        return ProvenChargeFlightNoSuccess(offer, ground, flight)
    # Use the exact ordered 2D6 outcome counts and prefer ground on a proven nonzero tie.
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


def _visible_poses(
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


def _native_scenario(state: GameState, poses: dict[str, Pose]) -> BattlefieldScenario | None:
    board = state.battlefield_state
    mission = state.mission_setup
    if (
        board is None
        or mission is None
        or mission.terrain_areas
        or board.terrain_features != mission.terrain_features
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
    state: GameState,
    handler: ChargePhaseHandler,
    offer: ChargeFlightOffer,
    actor: str,
    abilities: AbilityCatalogIndex,
    *,
    no_additional_cp: bool = False,
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
        # Only the explicitly conditional wall proof may ignore optional paid
        # choices (including a paid reroll or later terrain transit). Neither
        # holding CP nor another unit's use grants this mover terrain transit.
        or (
            not no_additional_cp
            and state.command_point_ledger_for_player(actor).command_points != 0
        )
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
    abilities: AbilityCatalogIndex,
    placement: ChargePlacement,
    *,
    flies: bool,
) -> ChargeFlightModeProof | None:
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
        if not _witness_accepted(
            scenario, ruleset, offer, witness, abilities, placement, budget=budget, flies=flies
        ):
            return None
        successes.append(raw_roll)
    # An empty set is a proof only if every budget was excluded by the target filter.
    return ChargeFlightModeProof(tuple(successes), sum(counts[roll] for roll in successes))


def _prove_wall_advantage(
    context: PlayerDecisionContext,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    offer: ChargeFlightOffer,
    witness: PathWitness,
    counts: Counter[int],
    abilities: AbilityCatalogIndex,
    placement: ChargePlacement,
) -> ProvenChargeFlightAdvantage | ChargeFlightUnresolved:
    distance = _wall_ground_distance_lower_bound(
        context, scenario, ruleset, offer, witness, abilities
    )
    if distance is None:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT, offer)
    # Removing rolls below a necessary ground distance is safe regardless of
    # which endpoints a real player would consider. Native movement rounds the
    # whole path to milli-inches; retain a full tick at the comparison boundary.
    ground = tuple(
        roll
        for roll in sorted(counts)
        if roll >= offer.target_filter_distance_inches and roll + 1 / TICKS_PER_INCH >= distance
    )
    flight: list[int] = []
    penalty = (("take-to-the-skies", -offer.flight_penalty_inches),)
    for roll in sorted(counts):
        budget, _ = resolve_distance_deltas(float(roll), penalty)
        if budget >= offer.target_filter_distance_inches and _witness_accepted(
            scenario, ruleset, offer, witness, abilities, placement, budget=budget, flies=True
        ):
            flight.append(roll)
    ground_count = sum(counts[roll] for roll in ground)
    flight_count = sum(counts[roll] for roll in flight)
    if flight_count <= ground_count:
        return ChargeFlightUnresolved(ChargeFlightUnresolvedReason.BOUNDS_OVERLAP, offer)
    return ProvenChargeFlightAdvantage(
        offer,
        payload_digest(witness.to_payload()),
        distance,
        ChargeFlightRollBound(ground, ground_count),
        ChargeFlightRollBound(tuple(flight), flight_count),
        context.select_option(offer.flight_option_id),
    )


def _wall_ground_distance_lower_bound(
    context: PlayerDecisionContext,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    offer: ChargeFlightOffer,
    witness: PathWitness,
    abilities: AbilityCatalogIndex,
) -> float | None:
    """Certify a single public axis-aligned Dense wall across the enclosing engagement disk."""
    board = scenario.battlefield_state
    field = context.observation["battlefield_view"]
    if (
        field is None
        or len(board.terrain_features) != 1
        or not ruleset.charge_policy.must_end_engaged_with_every_selected_target
    ):
        return None
    (feature,) = board.terrain_features
    public_features = field["authoritative"]["terrain_features_by_id"]
    public = public_features.get(feature.feature_id)
    if (
        len(public_features) != 1
        or public is None
        or public["classification"] != TerrainAreaClassification.DENSE.value
        or feature.classification is not TerrainAreaClassification.DENSE
        or feature.floors
        or len(feature.walls) != 1
        or len(public["volumes"]) != 1
    ):
        return None
    (wall,) = feature.walls
    (volume,) = public["volumes"]
    if (
        wall.bottom_z_inches != 0
        or wall.rotation_degrees != 0
        or volume["volume_kind"] != "wall"
        or volume["volume_id"] != wall.wall_id
        or volume["bottom_center"]
        != {
            "x_inches": wall.center_x_inches,
            "y_inches": wall.center_y_inches,
            "z_inches": 0.0,
        }
        or volume["width_inches"] != wall.width_inches
        or volume["depth_inches"] != wall.depth_inches
        or volume["height_inches"] != wall.height_inches
        or volume["rotation_degrees"] != 0
    ):
        return None

    (mover,) = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id=offer.unit_id
    )
    (target,) = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id=offer.target_id
    )
    entities = field["authoritative"]["models_by_id"]
    if not (
        isinstance(mover.base, CircularBase | OvalBase)
        and isinstance(target.base, CircularBase | OvalBase)
        and not mover.measures_every_part
        and not target.measures_every_part
    ):
        return None
    for model in (mover, target):
        geometry = entities[model.model_id]["geometry"]
        shape = geometry["support_shape"]
        if geometry["measurement_basis"] != "base":
            return None
        if shape["kind"] == "circle":
            radius = shape["radius_inches"]
        elif (
            shape["kind"] == "ellipse"
            and shape["length_inches"] is not None
            and shape["width_inches"] is not None
        ):
            radius = max(shape["length_inches"], shape["width_inches"]) / 2
        else:
            return None
        if radius != model.base.max_radius():
            return None

    # Endpoints must be engaged. Project that whole engagement disk onto X:
    # even allowing every facing and any elevation, its nearest possible X
    # must be strictly beyond the wall's center plane.
    start = mover.pose.position
    engagement_radius = (
        mover.base.max_radius()
        + target.base.max_radius()
        + ruleset.engagement_policy.horizontal_inches
    )
    padding = 1 / TICKS_PER_INCH
    if not (
        start.x + padding
        < wall.center_x_inches
        < target.pose.position.x - engagement_radius - padding
    ):
        return None

    mover_placement = board.model_placement_by_id(mover.model_id)
    unit = scenario.army_by_id(mover_placement.army_id).unit_by_id(offer.unit_id)
    path, terrain = charge_model_path_contexts(
        unit=unit,
        moving_model=mover,
        witness=witness,
        ruleset=ruleset,
        owner_player_id=mover_placement.player_id,
        current_model_instance_ids=(mover.model_id,),
        take_to_the_skies=False,
        ability_index=abilities,
        effects=(),
        battlefield_width_inches=board.battlefield_width_inches,
        battlefield_depth_inches=board.battlefield_depth_inches,
        friendly_models=(),
        enemy_models=(target,),
        units_by_model_id={
            target.model_id: scenario.army_by_id(
                board.model_placement_by_id(target.model_id).army_id
            ).unit_by_id(offer.target_id)
        },
        retained_model_ids=frozenset(),
        maximum_distance_inches=12,
        terrain=feature.terrain_volumes(),
        terrain_features=(feature,),
    )
    policy = terrain.terrain_movement_policy
    feature_policy = policy.policy_for_feature_kind(feature.feature_kind)
    if (
        path.ignores_vertical_distance
        or terrain.can_transit_all_terrain
        or terrain.horizontal_terrain_feature_transit
        or terrain.nonlevel_terrain_feature_transit
        or wall.height_inches
        <= max(
            policy.freely_traversable_height_threshold_inches,
            feature_policy.freely_moved_over_height_inches or 0,
            terrain.terrain_as_if_absent_height_inches or 0,
            terrain.horizontal_terrain_transit_height_inches or 0,
        )
        or classified_feature_transit_permission(feature, terrain.movement_keywords, (mover.pose,))
        is not False
    ):
        return None

    # When the continuous center path crosses the plane, a native sampled
    # center is no more than half a sampling interval away. Keep that margin
    # INSIDE the wall footprint: every path below the side bound is detected
    # by native terrain sampling, even if its waypoints skip the wall.
    sample_margin = terrain.sample_interval_inches / 2 + padding
    if wall.width_inches / 2 <= sample_margin:
        return None
    side = wall.depth_inches / 2 - abs(start.y - wall.center_y_inches) - sample_margin
    # Alternatively the path must reach the top. Leave slack for the
    # validator's math.isclose terrain-top contact comparison.
    climb = wall.height_inches * (1 - 1e-9) - padding
    distance = min(side, climb)
    return distance if distance > 0 else None


def _witness_accepted(
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    offer: ChargeFlightOffer,
    witness: PathWitness,
    abilities: AbilityCatalogIndex,
    placement: ChargePlacement,
    *,
    budget: float,
    flies: bool,
) -> bool:
    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_placement=placement,
        selected_target_unit_instance_ids=(offer.target_id,),
        maximum_distance_inches=budget,
        take_to_the_skies=flies,
        path_witness=witness,
        ability_index=abilities,
    )
    return (
        charge_move_violation_code(
            resolution=resolution, ruleset_descriptor=ruleset, maximum_distance_inches=budget
        )
        is None
    )
