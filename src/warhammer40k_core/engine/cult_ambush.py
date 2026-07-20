from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.cult_ambush_resurgence import (
    cult_ambush_resurgence_cost_for_unit as _cult_ambush_resurgence_cost_for_unit,
)
from warhammer40k_core.engine.cult_ambush_resurgence import (
    cult_ambush_return_candidate,
    replacement_unit_for_destroyed_unit,
    resurgence_cost,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import FactionResourceStatus
from warhammer40k_core.engine.list_validation import BattleSize, battle_size_from_token
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
    ProposalValidationResult,
    ProposalViolation,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyStatus,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.measurement import (
    DistanceMeasurementContext,
    millimeters_to_inches,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


GENESTEALER_CULTS_FACTION_ID = "genestealer-cults"
SOURCE_RULE_ID = "warhammer_40000_11th:genestealer_cults:army_rule:cult_ambush"
ATTACHED_CHARACTER_EXCLUSION_SOURCE_ID = (
    "warhammer_40000_11th:event_faq:tacoma_2026:cult_ambush_attached_character_exclusions"
)
BATTLE_FORMATION_HOOK_ID = f"{SOURCE_RULE_ID}:initial_resurgence"
UNIT_DESTROYED_HOOK_ID = f"{SOURCE_RULE_ID}:unit_destroyed"
TURN_END_HOOK_ID = f"{SOURCE_RULE_ID}:marker_ingress"
RESURGENCE_RESOURCE_KIND = "resurgence_points"
SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE = "select_cult_ambush_resurgence"
SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE = "submit_cult_ambush_marker_placement"
CULT_AMBUSH_MARKER_PLACEMENT_KIND = "cult_ambush_marker_placement"
CULT_AMBUSH_MARKER_DIAMETER_INCHES = millimeters_to_inches(32.0)
CULT_AMBUSH_MARKER_RADIUS_INCHES = CULT_AMBUSH_MARKER_DIAMETER_INCHES / 2.0
CULT_AMBUSH_MARKER_ENEMY_DISTANCE_INCHES = 9.0
CULT_AMBUSH_MARKER_REMOVAL_DISTANCE_INCHES = 8.0
CULT_AMBUSH_INGRESS_WHOLLY_WITHIN_INCHES = 3.0

_RESURGENCE_POINTS_BY_BATTLE_SIZE = {
    BattleSize.INCURSION: 6,
    BattleSize.STRIKE_FORCE: 10,
    BattleSize.ONSLAUGHT: 14,
}
_PROCESSED_MARKER_REMOVAL_MOVE_EVENTS = {
    "movement_activation_completed",
    "charge_move_completed",
    "fight_movement_completed",
    "unit_disembarked",
    "reinforcement_unit_arrived",
}


class CultAmbushMarkerPayload(TypedDict):
    marker_id: str
    player_id: str
    replacement_unit_instance_id: str
    source_destroyed_unit_instance_id: str
    created_battle_round: int
    created_phase: str
    created_active_player_id: str
    x_inches: float
    y_inches: float
    marker_diameter_inches: float
    ingress_window_closed: bool


class CultAmbushMarkerPlacementSubmissionPayload(TypedDict):
    submission_kind: str
    request_id: str
    marker_id: str
    player_id: str
    x_inches: NotRequired[float]
    y_inches: NotRequired[float]
    no_marker_reason: NotRequired[str]


@dataclass(frozen=True, slots=True)
class CultAmbushMarker:
    marker_id: str
    player_id: str
    replacement_unit_instance_id: str
    source_destroyed_unit_instance_id: str
    created_battle_round: int
    created_phase: BattlePhase
    created_active_player_id: str
    x_inches: float
    y_inches: float
    marker_diameter_inches: float = CULT_AMBUSH_MARKER_DIAMETER_INCHES
    ingress_window_closed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "marker_id", _validate_identifier("marker_id", self.marker_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "replacement_unit_instance_id",
            _validate_identifier(
                "replacement_unit_instance_id",
                self.replacement_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_destroyed_unit_instance_id",
            _validate_identifier(
                "source_destroyed_unit_instance_id",
                self.source_destroyed_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "created_battle_round",
            _validate_positive_int("created_battle_round", self.created_battle_round),
        )
        object.__setattr__(self, "created_phase", _battle_phase_from_token(self.created_phase))
        object.__setattr__(
            self,
            "created_active_player_id",
            _validate_identifier("created_active_player_id", self.created_active_player_id),
        )
        object.__setattr__(self, "x_inches", _validate_finite_number("x_inches", self.x_inches))
        object.__setattr__(self, "y_inches", _validate_finite_number("y_inches", self.y_inches))
        object.__setattr__(
            self,
            "marker_diameter_inches",
            _validate_positive_number("marker_diameter_inches", self.marker_diameter_inches),
        )
        object.__setattr__(
            self,
            "ingress_window_closed",
            _validate_bool("ingress_window_closed", self.ingress_window_closed),
        )

    @property
    def pose(self) -> Pose:
        return Pose.at(self.x_inches, self.y_inches)

    def with_ingress_window_closed(self) -> Self:
        return replace(self, ingress_window_closed=True)

    def to_payload(self) -> CultAmbushMarkerPayload:
        return {
            "marker_id": self.marker_id,
            "player_id": self.player_id,
            "replacement_unit_instance_id": self.replacement_unit_instance_id,
            "source_destroyed_unit_instance_id": self.source_destroyed_unit_instance_id,
            "created_battle_round": self.created_battle_round,
            "created_phase": self.created_phase.value,
            "created_active_player_id": self.created_active_player_id,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
            "marker_diameter_inches": self.marker_diameter_inches,
            "ingress_window_closed": self.ingress_window_closed,
        }

    @classmethod
    def from_payload(cls, payload: CultAmbushMarkerPayload) -> Self:
        return cls(
            marker_id=payload["marker_id"],
            player_id=payload["player_id"],
            replacement_unit_instance_id=payload["replacement_unit_instance_id"],
            source_destroyed_unit_instance_id=payload["source_destroyed_unit_instance_id"],
            created_battle_round=payload["created_battle_round"],
            created_phase=_battle_phase_from_token(payload["created_phase"]),
            created_active_player_id=payload["created_active_player_id"],
            x_inches=payload["x_inches"],
            y_inches=payload["y_inches"],
            marker_diameter_inches=payload["marker_diameter_inches"],
            ingress_window_closed=payload["ingress_window_closed"],
        )


def starting_resurgence_points_for_battle_size(battle_size: BattleSize) -> int:
    resolved = battle_size_from_token(battle_size)
    return _RESURGENCE_POINTS_BY_BATTLE_SIZE[resolved]


def cult_ambush_resurgence_cost_for_unit(state: GameState, unit: UnitInstance) -> int | None:
    return _cult_ambush_resurgence_cost_for_unit(state, unit)


def grant_initial_resurgence_points(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleFormationRequestContext:
        raise GameLifecycleError("Cult Ambush setup requires BattleFormationRequestContext.")
    for army in context.state.army_definitions:
        if army.detachment_selection.faction_id != GENESTEALER_CULTS_FACTION_ID:
            continue
        source_id = f"{SOURCE_RULE_ID}:initial:{army.battle_size.value}"
        if _faction_resource_source_exists(
            context.state,
            player_id=army.player_id,
            resource_kind=RESURGENCE_RESOURCE_KIND,
            source_id=source_id,
        ):
            continue
        amount = starting_resurgence_points_for_battle_size(army.battle_size)
        gain = context.state.gain_starting_faction_resource(
            player_id=army.player_id,
            resource_kind=RESURGENCE_RESOURCE_KIND,
            amount=amount,
            source_id=source_id,
        )
        context.decisions.event_log.append(
            "genestealer_cults_resurgence_points_granted",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "player_id": army.player_id,
                    "faction_id": GENESTEALER_CULTS_FACTION_ID,
                    "battle_size": army.battle_size.value,
                    "resource_kind": RESURGENCE_RESOURCE_KIND,
                    "amount": amount,
                    "source_rule_id": SOURCE_RULE_ID,
                    "faction_resource_result": gain.to_payload(),
                }
            ),
        )
    return None


def request_cult_ambush_resurgence(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Cult Ambush destruction hook requires UnitDestroyedContext.")
    if context.destroyed_player_id not in _genestealer_cults_player_ids(context.state):
        return
    if _cult_ambush_resurgence_request_exists(
        decisions=context.decisions,
        model_destroyed_event_id=context.model_destroyed_event_id,
        destroyed_unit_instance_id=context.destroyed_unit_instance_id,
    ):
        return
    candidate = cult_ambush_return_candidate(
        context.state,
        destroyed_unit_instance_id=context.destroyed_unit_instance_id,
    )
    if candidate is None:
        return
    unit = candidate.unit
    cost = resurgence_cost(
        unit=unit,
        starting_strength=candidate.starting_strength,
    )
    if cost is None:
        return
    total = context.state.faction_resource_total(
        player_id=context.destroyed_player_id,
        resource_kind=RESURGENCE_RESOURCE_KIND,
    )
    if total < cost:
        return
    payload = validate_json_value(
        {
            "source_rule_id": SOURCE_RULE_ID,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "destroyed_player_id": context.destroyed_player_id,
            "destroying_player_id": context.destroying_player_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "starting_strength": candidate.starting_strength,
            "resurgence_cost": cost,
            "current_resurgence_points": total,
        }
    )
    request = DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
        actor_id=context.destroyed_player_id,
        payload=payload,
        options=(
            DecisionOption(
                option_id=(
                    f"genestealer_cults:cult_ambush:decline:{context.destroyed_unit_instance_id}"
                ),
                label="Decline Cult Ambush",
                payload={
                    "selection": "decline",
                    "source_rule_id": SOURCE_RULE_ID,
                    "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                    "model_destroyed_event_id": context.model_destroyed_event_id,
                },
            ),
            DecisionOption(
                option_id=(
                    f"genestealer_cults:cult_ambush:spend:{context.destroyed_unit_instance_id}"
                ),
                label="Spend Resurgence Points",
                payload={
                    "selection": "spend",
                    "source_rule_id": SOURCE_RULE_ID,
                    "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                    "model_destroyed_event_id": context.model_destroyed_event_id,
                    "resurgence_cost": cost,
                },
            ),
        ),
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "genestealer_cults_cult_ambush_resurgence_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": context.completed_phase.value,
                "player_id": context.destroyed_player_id,
                "request_id": request.request_id,
                "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                "model_destroyed_event_id": context.model_destroyed_event_id,
                "resurgence_cost": cost,
                "current_resurgence_points": total,
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )


def invalid_cult_ambush_resurgence_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid = _invalid_finite_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_cult_ambush_resurgence_result",
    )
    if invalid is not None:
        return invalid
    result_payload = _result_payload_object(result)
    selection = _payload_string(result_payload, "selection")
    if selection == "decline":
        return None
    if selection != "spend":
        return _invalid(
            state,
            "Cult Ambush selection is invalid.",
            "invalid_selection",
            "selection",
        )
    destroyed_unit_id = _payload_string(result_payload, "destroyed_unit_instance_id")
    candidate = cult_ambush_return_candidate(
        state,
        destroyed_unit_instance_id=destroyed_unit_id,
    )
    if candidate is None:
        return _invalid(
            state,
            "Destroyed unit no longer has Cult Ambush.",
            "ability_drift",
            "destroyed_unit_instance_id",
        )
    current_cost = resurgence_cost(
        unit=candidate.unit,
        starting_strength=candidate.starting_strength,
    )
    if current_cost is None:
        return _invalid(
            state,
            "Destroyed unit is not eligible for Cult Ambush Resurgence.",
            "unit_ineligible",
            "destroyed_unit_instance_id",
        )
    if _payload_int(result_payload, "resurgence_cost") != current_cost:
        return _invalid(
            state,
            "Cult Ambush Resurgence cost drifted.",
            "cost_drift",
            "resurgence_cost",
        )
    current_total = state.faction_resource_total(
        player_id=_require_actor_id(request),
        resource_kind=RESURGENCE_RESOURCE_KIND,
    )
    if current_total < current_cost:
        return _invalid(
            state,
            "Insufficient Resurgence points.",
            "insufficient_resurgence_points",
            "resurgence_points",
        )
    return None


def apply_cult_ambush_resurgence_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    payload = _result_payload_object(result)
    selection = _payload_string(payload, "selection")
    destroyed_unit_id = _payload_string(payload, "destroyed_unit_instance_id")
    player_id = _require_actor_id(request)
    if selection == "decline":
        decisions.event_log.append(
            "genestealer_cults_cult_ambush_resurgence_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": _current_phase_token(state),
                    "player_id": player_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "destroyed_unit_instance_id": destroyed_unit_id,
                    "source_rule_id": SOURCE_RULE_ID,
                }
            ),
        )
        return
    if selection != "spend":
        raise GameLifecycleError("Cult Ambush result was not prevalidated.")
    candidate = cult_ambush_return_candidate(
        state,
        destroyed_unit_instance_id=destroyed_unit_id,
    )
    if candidate is None:
        raise GameLifecycleError("Cult Ambush return unit was not prevalidated.")
    cost = _payload_int(payload, "resurgence_cost")
    spend = state.spend_faction_resource(
        player_id=player_id,
        resource_kind=RESURGENCE_RESOURCE_KIND,
        amount=cost,
        source_id=f"{SOURCE_RULE_ID}:resurgence:{result.result_id}",
    )
    if spend.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Cult Ambush spend was not prevalidated.")
    replacement = replacement_unit_for_destroyed_unit(state, candidate.unit)
    starting_strength_record = state.add_unit_to_army(
        player_id=player_id,
        unit=replacement,
        source_id=SOURCE_RULE_ID,
    )
    current_phase = _current_phase(state)
    reserve_state = ReserveState.entered_during_battle(
        player_id=player_id,
        unit_instance_id=replacement.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=state.battle_round,
        phase=current_phase,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            state.runtime_ruleset_descriptor().mission_policy
        ),
        source_rule_ids=(SOURCE_RULE_ID, ATTACHED_CHARACTER_EXCLUSION_SOURCE_ID),
    )
    state.record_reserve_state(reserve_state)
    event_payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "player_id": player_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "destroyed_unit_instance_id": destroyed_unit_id,
            "replacement_unit_instance_id": replacement.unit_instance_id,
            "resurgence_cost": cost,
            "faction_resource_result": spend.to_payload(),
            "reserve_state": reserve_state.to_payload(),
            "starting_strength_record": starting_strength_record.to_payload(),
            "source_rule_id": SOURCE_RULE_ID,
        }
    )
    decisions.event_log.append(
        "genestealer_cults_cult_ambush_resurgence_spent",
        event_payload,
    )
    marker_id = _marker_id(
        state=state,
        player_id=player_id,
        replacement_unit_instance_id=replacement.unit_instance_id,
        source_result_id=result.result_id,
    )
    if not cult_ambush_marker_has_any_legal_position(state, player_id=player_id):
        decisions.event_log.append(
            "genestealer_cults_cult_ambush_marker_not_placed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": current_phase.value,
                    "player_id": player_id,
                    "marker_id": marker_id,
                    "replacement_unit_instance_id": replacement.unit_instance_id,
                    "destroyed_unit_instance_id": destroyed_unit_id,
                    "reason": "no_legal_marker_position",
                    "source_rule_id": SOURCE_RULE_ID,
                }
            ),
        )
        return
    _request_marker_placement(
        state=state,
        decisions=decisions,
        player_id=player_id,
        marker_id=marker_id,
        replacement_unit_instance_id=replacement.unit_instance_id,
        destroyed_unit_instance_id=destroyed_unit_id,
        source_request_id=result.request_id,
        source_result_id=result.result_id,
    )


def invalid_cult_ambush_marker_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _invalid(state, "Marker placement request id drift.", "request_id", "request_id")
    if result.decision_type != request.decision_type:
        return _invalid(
            state,
            "Marker placement decision type drift.",
            "decision_type",
            "decision_type",
        )
    if result.actor_id != request.actor_id:
        return _invalid(state, "Marker placement actor drift.", "actor_id", "actor_id")
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(
            state,
            "Marker placement requires parameterized payload.",
            "selected_option_id",
            "selected_option_id",
        )
    request_payload = _request_payload_object(request)
    result_payload = _result_payload_object(result)
    if _payload_string(result_payload, "request_id") != request.request_id:
        return _invalid(
            state,
            "Marker placement payload request id drift.",
            "payload_request_id",
            "request_id",
        )
    if _payload_string(result_payload, "marker_id") != _payload_string(
        request_payload,
        "marker_id",
    ):
        return _invalid(state, "Marker id drift.", "marker_id", "marker_id")
    player_id = _payload_string(result_payload, "player_id")
    if player_id != _require_actor_id(request):
        return _invalid(state, "Marker placement player drift.", "player_id", "player_id")
    kind = _payload_string(result_payload, "submission_kind")
    if kind == "cult_ambush_no_marker":
        if cult_ambush_marker_has_any_legal_position(state, player_id=player_id):
            return _invalid(
                state,
                "Cult Ambush marker has at least one legal position.",
                "legal_marker_position_exists",
                "no_marker_reason",
            )
        return None
    if kind != CULT_AMBUSH_MARKER_PLACEMENT_KIND:
        return _invalid(
            state,
            "Cult Ambush marker placement kind is invalid.",
            "submission_kind",
            "submission_kind",
        )
    x_inches = _payload_number(result_payload, "x_inches")
    y_inches = _payload_number(result_payload, "y_inches")
    violation = cult_ambush_marker_position_violation(
        state,
        player_id=player_id,
        x_inches=x_inches,
        y_inches=y_inches,
    )
    if violation is not None:
        return _invalid(
            state,
            "Cult Ambush marker placement is invalid.",
            violation,
            "position",
        )
    return None


def apply_cult_ambush_marker_placement_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    request_payload = _request_payload_object(request)
    result_payload = _result_payload_object(result)
    marker_id = _payload_string(result_payload, "marker_id")
    player_id = _payload_string(result_payload, "player_id")
    if _payload_string(result_payload, "submission_kind") == "cult_ambush_no_marker":
        decisions.event_log.append(
            "genestealer_cults_cult_ambush_marker_not_placed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": _current_phase_token(state),
                    "player_id": player_id,
                    "marker_id": marker_id,
                    "replacement_unit_instance_id": _payload_string(
                        request_payload,
                        "replacement_unit_instance_id",
                    ),
                    "destroyed_unit_instance_id": _payload_string(
                        request_payload,
                        "destroyed_unit_instance_id",
                    ),
                    "reason": _payload_string(result_payload, "no_marker_reason"),
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "source_rule_id": SOURCE_RULE_ID,
                }
            ),
        )
        return
    marker = CultAmbushMarker(
        marker_id=marker_id,
        player_id=player_id,
        replacement_unit_instance_id=_payload_string(
            request_payload,
            "replacement_unit_instance_id",
        ),
        source_destroyed_unit_instance_id=_payload_string(
            request_payload,
            "destroyed_unit_instance_id",
        ),
        created_battle_round=state.battle_round,
        created_phase=_current_phase(state),
        created_active_player_id=_active_player_id(state),
        x_inches=_payload_number(result_payload, "x_inches"),
        y_inches=_payload_number(result_payload, "y_inches"),
    )
    state.record_cult_ambush_marker(marker)
    decisions.event_log.append(
        "genestealer_cults_cult_ambush_marker_placed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": _current_phase_token(state),
                "player_id": player_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "marker": marker.to_payload(),
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )


def cult_ambush_marker_ingress_request(
    context: TurnEndRequestContext,
) -> DecisionRequest | None:
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Cult Ambush ingress requires TurnEndRequestContext.")
    if context.completed_phase is not BattlePhase.MOVEMENT:
        return None
    active_player_id = _active_player_id(context.state)
    markers = tuple(
        marker
        for marker in context.state.cult_ambush_markers
        if marker.player_id != active_player_id
        and not marker.ingress_window_closed
        and not (
            marker.created_battle_round == context.state.battle_round
            and marker.created_phase is BattlePhase.MOVEMENT
            and marker.created_active_player_id == active_player_id
        )
    )
    if not markers:
        return None
    for marker in sorted(markers, key=lambda value: value.marker_id):
        eligible_unit_ids = _cult_ambush_unarrived_unit_ids(
            context.state,
            player_id=marker.player_id,
        )
        if not eligible_unit_ids:
            continue
        payload = validate_json_value(
            {
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": TURN_END_HOOK_ID,
                "selection_kind": "cult_ambush_marker_ingress",
                "marker": marker.to_payload(),
                "eligible_unit_instance_ids": list(eligible_unit_ids),
                "battle_round": context.state.battle_round,
                "phase": context.completed_phase.value,
                "active_player_id": active_player_id,
            }
        )
        options = [
            DecisionOption(
                option_id=f"genestealer_cults:cult_ambush:marker:{marker.marker_id}:decline",
                label="Do Not Use Cult Ambush Marker",
                payload={
                    "selection": "decline",
                    "source_rule_id": SOURCE_RULE_ID,
                    "marker_id": marker.marker_id,
                },
            )
        ]
        for unit_id in eligible_unit_ids:
            options.append(
                DecisionOption(
                    option_id=f"genestealer_cults:cult_ambush:marker:{marker.marker_id}:unit:{unit_id}",
                    label=f"Cult Ambush Ingress: {unit_id}",
                    payload={
                        "selection": "ingress",
                        "source_rule_id": SOURCE_RULE_ID,
                        "marker_id": marker.marker_id,
                        "unit_instance_id": unit_id,
                    },
                )
            )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
            actor_id=marker.player_id,
            payload=payload,
            options=tuple(options),
        )
    return None


def apply_cult_ambush_marker_ingress_selection(
    context: TurnEndResultContext,
) -> bool:
    if type(context) is not TurnEndResultContext:
        raise GameLifecycleError("Cult Ambush ingress requires TurnEndResultContext.")
    request_payload = _request_payload_object(context.request)
    if request_payload.get("source_rule_id") != SOURCE_RULE_ID:
        return False
    if request_payload.get("hook_id") != TURN_END_HOOK_ID:
        return False
    result_payload = _result_payload_object(context.result)
    marker_id = _payload_string(result_payload, "marker_id")
    marker = _marker_by_id(context.state, marker_id)
    selection = _payload_string(result_payload, "selection")
    if selection == "decline":
        context.state.replace_cult_ambush_marker(marker.with_ingress_window_closed())
        context.decisions.event_log.append(
            "genestealer_cults_cult_ambush_marker_ingress_declined",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.state.active_player_id,
                    "phase": _current_phase_token(context.state),
                    "player_id": marker.player_id,
                    "marker_id": marker.marker_id,
                    "request_id": context.result.request_id,
                    "result_id": context.result.result_id,
                    "source_rule_id": SOURCE_RULE_ID,
                }
            ),
        )
        return True
    if selection != "ingress":
        raise GameLifecycleError("Cult Ambush ingress selection was not prevalidated.")
    unit_id = _payload_string(result_payload, "unit_instance_id")
    proposal = MovementProposalRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=marker.player_id,
        game_id=context.state.game_id,
        battle_round=context.state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=unit_id,
        proposal_kind=ProposalKind.CULT_AMBUSH,
        source_decision_request_id=context.result.request_id,
        source_decision_result_id=context.result.result_id,
        placement_kinds=(BattlefieldPlacementKind.CULT_AMBUSH,),
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "source_rule_id": SOURCE_RULE_ID,
                    "marker": marker.to_payload(),
                    "active_player_id": context.state.active_player_id,
                    "placement_scope": "cult_ambush_marker",
                }
            ),
        ),
    )
    request = proposal.to_decision_request()
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "placement_proposal_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "player_id": marker.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": unit_id,
                "proposal_kind": ProposalKind.CULT_AMBUSH.value,
                "placement_kinds": [BattlefieldPlacementKind.CULT_AMBUSH.value],
                "request_id": request.request_id,
                "source_decision_request_id": context.result.request_id,
                "source_decision_result_id": context.result.result_id,
                "marker_id": marker.marker_id,
                "phase_body_status": "cult_ambush_ingress_placement_proposal_required",
            }
        ),
    )
    return True


def is_cult_ambush_placement_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Cult Ambush placement routing requires DecisionRequest.")
    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return proposal_request.proposal_kind is ProposalKind.CULT_AMBUSH


def invalid_cult_ambush_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    result.validate_for_request(request)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, result.payload)
    )
    if submitted.proposal_request_id != proposal_request.request_id:
        return _invalid(
            state,
            "Cult Ambush placement proposal request id drift.",
            "proposal_request_id",
            "proposal_request_id",
        )
    if submitted.proposal_kind is not ProposalKind.CULT_AMBUSH:
        return _invalid(
            state,
            "Cult Ambush placement proposal kind drift.",
            "proposal_kind",
            "proposal_kind",
        )
    if submitted.unit_instance_id != proposal_request.unit_instance_id:
        return _invalid(
            state,
            "Cult Ambush placement unit drift.",
            "unit_instance_id",
            "unit_instance_id",
        )
    if submitted.placement_kind is not BattlefieldPlacementKind.CULT_AMBUSH:
        return _invalid(
            state,
            "Cult Ambush placement kind drift.",
            "placement_kind",
            "placement_kind",
        )
    return None


def apply_cult_ambush_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, result.payload)
    )
    placement = resolve_cult_ambush_ingress_placement(
        state=state,
        proposal_request=proposal_request,
        submitted=submitted,
    )
    if not placement.validation_result.is_valid:
        decisions.event_log.append(
            "genestealer_cults_cult_ambush_ingress_placement_invalid",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "player_id": proposal_request.actor_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "proposal_kind": ProposalKind.CULT_AMBUSH.value,
                    "placement_kind": submitted.placement_kind.value,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "marker_id": placement.marker.marker_id,
                    "phase_body_status": "cult_ambush_ingress_placement_invalid",
                    "validation_result": placement.validation_result.to_payload(),
                    "coherency_result": placement.coherency_result.to_payload(),
                }
            ),
        )
        retry = _request_cult_ambush_placement_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            rejected_result=result,
        )
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Cult Ambush ingress placement is invalid.",
            payload=validate_json_value(
                {
                    "invalid_reason": "cult_ambush_ingress_placement_invalid",
                    "next_request_id": retry.request_id,
                    "validation_result": placement.validation_result.to_payload(),
                }
            ),
        )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush placement requires battlefield_state.")
    if placement.reserve_state is None:
        raise GameLifecycleError("Cult Ambush placement was not prevalidated with a reserve state.")
    state.replace_battlefield_state(
        battlefield_state.with_added_unit_placement(submitted.require_unit_placement())
    )
    arrived_state = placement.reserve_state.mark_arrived(
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        large_model_exception_used=False,
        post_arrival_restrictions=(),
    )
    state.replace_reserve_state(arrived_state)
    state.remove_cult_ambush_marker(placement.marker.marker_id)
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": arrived_state.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "step": "cult_ambush_marker",
                "unit_instance_id": arrived_state.unit_instance_id,
                "placement_kind": BattlefieldPlacementKind.CULT_AMBUSH.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "cult_ambush_unit_arrived",
                "transition_batch": placement.transition_batch.to_payload(),
                "large_model_exception_used": False,
                "post_arrival_restrictions": [],
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )
    decisions.event_log.append(
        "genestealer_cults_cult_ambush_unit_arrived",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": arrived_state.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": arrived_state.unit_instance_id,
                "marker_id": placement.marker.marker_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "transition_batch": placement.transition_batch.to_payload(),
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )
    return None


@dataclass(frozen=True, slots=True)
class CultAmbushIngressPlacement:
    marker: CultAmbushMarker
    reserve_state: ReserveState | None
    validation_result: ProposalValidationResult
    coherency_result: UnitCoherencyResult
    transition_batch: BattlefieldTransitionBatch


def resolve_cult_ambush_ingress_placement(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    submitted: PlacementProposalPayload,
) -> CultAmbushIngressPlacement:
    marker = _marker_from_proposal_request(proposal_request)
    reserve_state = state.reserve_state_for_unit(submitted.unit_instance_id)
    scenario = _battlefield_scenario(state)
    coherency_result = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=submitted.require_unit_placement(),
    )
    violations: list[ProposalViolation] = []
    if reserve_state is None:
        violations.append(_violation("reserve_state_missing", "ReserveState is missing."))
    elif reserve_state.status is not ReserveStatus.IN_RESERVES:
        violations.append(
            _violation("reserve_state_not_unarrived", "ReserveState is not unarrived.")
        )
    if reserve_state is not None and not reserve_state_is_cult_ambush(reserve_state):
        violations.append(
            _violation("reserve_state_not_cult_ambush", "ReserveState is not Cult Ambush.")
        )
    if marker.marker_id not in {stored.marker_id for stored in state.cult_ambush_markers}:
        violations.append(_violation("marker_not_active", "Cult Ambush marker is not active."))
    if submitted.require_unit_placement().unit_instance_id != submitted.unit_instance_id:
        violations.append(_violation("unit_placement_drift", "UnitPlacement unit drift."))
    if submitted.require_unit_placement().player_id != proposal_request.actor_id:
        violations.append(_violation("player_id_drift", "UnitPlacement player drift."))
    _append_cult_ambush_marker_placement_violations(
        state=state,
        marker=marker,
        unit_placement=submitted.require_unit_placement(),
        violations=violations,
    )
    if coherency_result.status is UnitCoherencyStatus.BROKEN:
        violations.append(_violation("unit_coherency_broken", "Unit coherency is broken."))
    status = "valid" if not violations else "invalid"
    transition_batch = _placement_transition_batch(submitted.require_unit_placement())
    return CultAmbushIngressPlacement(
        marker=marker,
        reserve_state=reserve_state,
        validation_result=ProposalValidationResult(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=ProposalKind.CULT_AMBUSH,
            is_valid=not violations,
            status=status,
            violations=tuple(violations),
        ),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
    )


def resolve_cult_ambush_marker_removal_for_completed_moves(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
) -> None:
    if not state.cult_ambush_markers:
        return
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    for record in tuple(decisions.event_log.records):
        if record.event_type not in _PROCESSED_MARKER_REMOVAL_MOVE_EVENTS:
            continue
        if _marker_removal_already_processed(decisions, trigger_event_id=record.event_id):
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Move completion event payload must be an object.")
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("active_player_id") != state.active_player_id:
            continue
        if payload.get("phase") != completed_phase.value:
            continue
        unit_id = _event_unit_instance_id(payload)
        if unit_id is None:
            continue
        owner_id = _unit_owner(state, unit_id)
        if _unit_has_aircraft_keyword(_unit_by_id(state, unit_id)):
            continue
        for marker in tuple(state.cult_ambush_markers):
            if marker.player_id == owner_id:
                continue
            if _unit_is_within_marker_removal_distance(
                state,
                marker=marker,
                unit_instance_id=unit_id,
            ):
                state.remove_cult_ambush_marker(marker.marker_id)
                decisions.event_log.append(
                    "genestealer_cults_cult_ambush_marker_removed",
                    validate_json_value(
                        {
                            "game_id": state.game_id,
                            "battle_round": state.battle_round,
                            "active_player_id": state.active_player_id,
                            "phase": completed_phase.value,
                            "player_id": marker.player_id,
                            "marker": marker.to_payload(),
                            "trigger_event_id": record.event_id,
                            "trigger_event_type": record.event_type,
                            "enemy_unit_instance_id": unit_id,
                            "source_rule_id": SOURCE_RULE_ID,
                        }
                    ),
                )


def reserve_state_is_cult_ambush(reserve_state: ReserveState) -> bool:
    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("Cult Ambush reserve lookup requires ReserveState.")
    return SOURCE_RULE_ID in reserve_state.source_rule_ids


def cult_ambush_marker_position_violation(
    state: GameState,
    *,
    player_id: str,
    x_inches: float,
    y_inches: float,
) -> str | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    x_value = _validate_finite_number("x_inches", x_inches)
    y_value = _validate_finite_number("y_inches", y_inches)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush marker placement requires battlefield_state.")
    if x_value < 0.0 or x_value > battlefield_state.battlefield_width_inches:
        return "marker_x_out_of_bounds"
    if y_value < 0.0 or y_value > battlefield_state.battlefield_depth_inches:
        return "marker_y_out_of_bounds"
    marker_pose = Pose.at(x_value, y_value)
    for enemy_model in _enemy_geometry_models(state, player_id=requested_player_id):
        context = DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id="cult-ambush-marker-candidate",
            marker_pose=marker_pose,
            model=enemy_model,
            marker_diameter_inches=CULT_AMBUSH_MARKER_DIAMETER_INCHES,
        )
        if context.horizontal_distance_inches() <= CULT_AMBUSH_MARKER_ENEMY_DISTANCE_INCHES:
            return "marker_enemy_distance"
    return None


def cult_ambush_marker_has_any_legal_position(state: GameState, *, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush marker placement requires battlefield_state.")
    return shapely_backend.bounds_have_point_clear_of_model_footprints(
        bounds=(
            0.0,
            0.0,
            battlefield_state.battlefield_width_inches,
            battlefield_state.battlefield_depth_inches,
        ),
        blocked_models=_enemy_geometry_models(state, player_id=requested_player_id),
        clear_distance_inches=CULT_AMBUSH_MARKER_ENEMY_DISTANCE_INCHES,
        marker_radius_inches=CULT_AMBUSH_MARKER_RADIUS_INCHES,
    )


def _request_marker_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    marker_id: str,
    replacement_unit_instance_id: str,
    destroyed_unit_instance_id: str,
    source_request_id: str,
    source_result_id: str,
) -> DecisionRequest:
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SUBMIT_CULT_AMBUSH_MARKER_PLACEMENT_DECISION_TYPE,
        actor_id=player_id,
        payload=validate_json_value(
            {
                "submission_kind": CULT_AMBUSH_MARKER_PLACEMENT_KIND,
                "source_rule_id": SOURCE_RULE_ID,
                "marker_id": marker_id,
                "player_id": player_id,
                "replacement_unit_instance_id": replacement_unit_instance_id,
                "destroyed_unit_instance_id": destroyed_unit_instance_id,
                "marker_diameter_inches": CULT_AMBUSH_MARKER_DIAMETER_INCHES,
                "required_enemy_horizontal_distance_inches": (
                    CULT_AMBUSH_MARKER_ENEMY_DISTANCE_INCHES
                ),
                "source_decision_request_id": source_request_id,
                "source_decision_result_id": source_result_id,
            }
        ),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "genestealer_cults_cult_ambush_marker_placement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": _current_phase_token(state),
                "player_id": player_id,
                "request_id": request.request_id,
                "marker_id": marker_id,
                "replacement_unit_instance_id": replacement_unit_instance_id,
                "destroyed_unit_instance_id": destroyed_unit_instance_id,
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )
    return request


def _request_cult_ambush_placement_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        placement_kinds=proposal_request.placement_kinds,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": retry_proposal.actor_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": retry_proposal.unit_instance_id,
                "proposal_kind": retry_proposal.proposal_kind.value,
                "placement_kinds": [kind.value for kind in retry_proposal.placement_kinds],
                "request_id": request.request_id,
                "source_decision_request_id": retry_proposal.source_decision_request_id,
                "source_decision_result_id": retry_proposal.source_decision_result_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "phase_body_status": "cult_ambush_ingress_placement_proposal_required",
            }
        ),
    )
    return request


def _marker_id(
    *,
    state: GameState,
    player_id: str,
    replacement_unit_instance_id: str,
    source_result_id: str,
) -> str:
    return (
        f"cult-ambush-marker:{state.game_id}:round-{state.battle_round:02d}:"
        f"{player_id}:{replacement_unit_instance_id}:{source_result_id}"
    )


def _genestealer_cults_player_ids(state: GameState) -> set[str]:
    return {
        army.player_id
        for army in state.army_definitions
        if army.detachment_selection.faction_id == GENESTEALER_CULTS_FACTION_ID
    }


def _faction_resource_source_exists(
    state: GameState,
    *,
    player_id: str,
    resource_kind: str,
    source_id: str,
) -> bool:
    ledger = state.faction_resource_ledger_for_player(player_id)
    return any(
        transaction.resource_kind == resource_kind and transaction.source_id == source_id
        for transaction in ledger.transactions
    )


def _cult_ambush_resurgence_request_exists(
    *,
    decisions: DecisionController,
    model_destroyed_event_id: str,
    destroyed_unit_instance_id: str,
) -> bool:
    for request in decisions.queue.pending_requests:
        if request.decision_type != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE:
            continue
        payload = request.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Cult Ambush request payload must be an object.")
        if (
            payload.get("model_destroyed_event_id") == model_destroyed_event_id
            and payload.get("destroyed_unit_instance_id") == destroyed_unit_instance_id
        ):
            return True
    for record in decisions.records:
        request = record.request
        if request.decision_type != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE:
            continue
        payload = request.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Cult Ambush record payload must be an object.")
        if (
            payload.get("model_destroyed_event_id") == model_destroyed_event_id
            and payload.get("destroyed_unit_instance_id") == destroyed_unit_instance_id
        ):
            return True
    return False


def _cult_ambush_unarrived_unit_ids(state: GameState, *, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            reserve_state.unit_instance_id
            for reserve_state in state.unarrived_reserve_states_for_player(player_id)
            if reserve_state.status is ReserveStatus.IN_RESERVES
            and reserve_state_is_cult_ambush(reserve_state)
        )
    )


def _append_cult_ambush_marker_placement_violations(
    *,
    state: GameState,
    marker: CultAmbushMarker,
    unit_placement: UnitPlacement,
    violations: list[ProposalViolation],
) -> None:
    battlefield_state = state.battlefield_state
    mission_setup = state.mission_setup
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush placement requires battlefield_state.")
    placed_model_ids = set(battlefield_state.placed_model_ids())
    for model_placement in unit_placement.model_placements:
        if model_placement.model_instance_id in placed_model_ids:
            violations.append(_violation("model_overlap", "Model is already placed."))
        model = _model_for_placement(
            state,
            unit_placement.unit_instance_id,
            model_placement.model_instance_id,
        )
        geometry_model = geometry_model_for_placement(model=model, placement=model_placement)
        if not shapely_backend.base_footprint_within_bounds(
            geometry_model.base,
            geometry_model.pose,
            (
                0.0,
                0.0,
                battlefield_state.battlefield_width_inches,
                battlefield_state.battlefield_depth_inches,
            ),
        ):
            violations.append(_violation("battlefield_bounds", "Model is outside battlefield."))
        for placed in _placed_geometry_models(state):
            if shapely_backend.base_footprints_intersect(
                geometry_model.base,
                geometry_model.pose,
                placed.base,
                placed.pose,
            ):
                violations.append(_violation("model_overlap", "Model overlaps another model."))
                break
        if mission_setup is not None:
            for marker_definition in mission_setup.objective_markers:
                objective_marker = marker_definition.to_objective_marker()
                if not DistanceMeasurementContext.from_objective_marker_to_model(
                    marker_id=objective_marker.objective_marker_id,
                    marker_pose=Pose.at(
                        objective_marker.x_inches,
                        objective_marker.y_inches,
                        objective_marker.z_inches,
                    ),
                    model=geometry_model,
                    marker_diameter_inches=objective_marker.marker_diameter_inches,
                ).contact_plane_footprints_overlap():
                    continue
                violations.append(
                    _violation(
                        "objective_marker_endpoint_overlap",
                        "Model overlaps an objective marker.",
                    )
                )
                break
        marker_context = DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id=marker.marker_id,
            marker_pose=marker.pose,
            model=geometry_model,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        if not (
            marker_context.contact_plane_footprints_overlap()
            or marker_context.target_wholly_within_distance(
                CULT_AMBUSH_INGRESS_WHOLLY_WITHIN_INCHES,
                horizontal_only=True,
            )
        ):
            violations.append(
                _violation(
                    "cult_ambush_marker_distance",
                    "Each model must be in base contact with or wholly within 3 inches "
                    "of the marker.",
                )
            )
    if not _placement_has_model_in_base_contact_with_marker(
        state=state,
        marker=marker,
        unit_placement=unit_placement,
    ):
        violations.append(
            _violation(
                "cult_ambush_marker_base_contact",
                "At least one model must be in base contact with the marker.",
            )
        )


def _placement_has_model_in_base_contact_with_marker(
    *,
    state: GameState,
    marker: CultAmbushMarker,
    unit_placement: UnitPlacement,
) -> bool:
    for model_placement in unit_placement.model_placements:
        model = _model_for_placement(
            state,
            unit_placement.unit_instance_id,
            model_placement.model_instance_id,
        )
        geometry_model = geometry_model_for_placement(model=model, placement=model_placement)
        if DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id=marker.marker_id,
            marker_pose=marker.pose,
            model=geometry_model,
            marker_diameter_inches=marker.marker_diameter_inches,
        ).contact_plane_footprints_overlap():
            return True
    return False


def _model_for_placement(
    state: GameState,
    unit_instance_id: str,
    model_instance_id: str,
) -> ModelInstance:
    unit = _unit_by_id(state, unit_instance_id)
    for model in unit.own_models:
        if model.model_instance_id == model_instance_id:
            return model
    raise GameLifecycleError("Cult Ambush placement references an unknown model.")


def _placed_geometry_models(state: GameState) -> tuple[GeometryModel, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush placement requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )
    return tuple(scenario.placed_geometry_models())


def _enemy_geometry_models(state: GameState, *, player_id: str) -> tuple[GeometryModel, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush marker placement requires battlefield_state.")
    models: list[GeometryModel] = []
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                model = _model_for_placement(
                    state,
                    unit_placement.unit_instance_id,
                    model_placement.model_instance_id,
                )
                models.append(geometry_model_for_placement(model=model, placement=model_placement))
    return tuple(models)


def _unit_is_within_marker_removal_distance(
    state: GameState,
    *,
    marker: CultAmbushMarker,
    unit_instance_id: str,
) -> bool:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return False
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    for model_placement in unit_placement.model_placements:
        model = _model_for_placement(state, unit_instance_id, model_placement.model_instance_id)
        geometry_model = geometry_model_for_placement(model=model, placement=model_placement)
        context = DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id=marker.marker_id,
            marker_pose=marker.pose,
            model=geometry_model,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        if context.horizontal_distance_inches() <= CULT_AMBUSH_MARKER_REMOVAL_DISTANCE_INCHES:
            return True
    return False


def _marker_removal_already_processed(
    decisions: DecisionController,
    *,
    trigger_event_id: str,
) -> bool:
    for record in decisions.event_log.records:
        if record.event_type != "genestealer_cults_cult_ambush_marker_removed":
            continue
        payload = record.payload
        if isinstance(payload, dict) and payload.get("trigger_event_id") == trigger_event_id:
            return True
    return False


def _event_unit_instance_id(payload: dict[str, JsonValue]) -> str | None:
    for key in ("unit_instance_id", "target_unit_instance_id"):
        value = payload.get(key)
        if type(value) is str:
            return _validate_identifier(key, value)
    return None


def _placement_transition_batch(unit_placement: UnitPlacement) -> BattlefieldTransitionBatch:
    return BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=model_placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.CULT_AMBUSH,
                pose=model_placement.pose,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="cult_ambush_marker",
                source_rule_id=SOURCE_RULE_ID,
                source_event_id=None,
            )
            for model_placement in unit_placement.model_placements
        )
    )


def _marker_from_proposal_request(proposal_request: MovementProposalRequest) -> CultAmbushMarker:
    context = proposal_request.context
    if context is None:
        raise GameLifecycleError("Cult Ambush placement request requires context.")
    marker_payload = context.get("marker")
    if not isinstance(marker_payload, dict):
        raise GameLifecycleError("Cult Ambush placement request requires marker payload.")
    return CultAmbushMarker.from_payload(cast(CultAmbushMarkerPayload, marker_payload))


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Cult Ambush placement requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )


def _marker_by_id(state: GameState, marker_id: str) -> CultAmbushMarker:
    marker = state.cult_ambush_marker_by_id(marker_id)
    if marker is None:
        raise GameLifecycleError("Cult Ambush marker is unknown.")
    return marker


def _unit_owner(state: GameState, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Cult Ambush unit owner lookup failed.")


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Cult Ambush unit lookup failed.")


def _unit_has_aircraft_keyword(unit: UnitInstance) -> bool:
    return any(
        keyword.upper() == "AIRCRAFT" for keyword in (*unit.keywords, *unit.faction_keywords)
    )


def _current_phase(state: GameState) -> BattlePhase:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Cult Ambush requires a current battle phase.")
    return phase


def _current_phase_token(state: GameState) -> str:
    return _current_phase(state).value


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Cult Ambush requires an active player.")
    return state.active_player_id


def _require_actor_id(request: DecisionRequest) -> str:
    if request.actor_id is None:
        raise GameLifecycleError("Cult Ambush request requires actor_id.")
    return request.actor_id


def _request_payload_object(request: DecisionRequest) -> dict[str, JsonValue]:
    payload = validate_json_value(request.payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Cult Ambush request payload must be an object.")
    return payload


def _result_payload_object(result: DecisionResult) -> dict[str, JsonValue]:
    payload = validate_json_value(result.payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Cult Ambush result payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Cult Ambush payload missing string field: {key}.")
    return _validate_identifier(key, value)


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Cult Ambush payload missing int field: {key}.")
    return value


def _payload_number(payload: dict[str, JsonValue], key: str) -> float:
    value = payload.get(key)
    return _validate_finite_number(key, value)


def _invalid_finite_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _invalid(state, "Decision result request id drift.", invalid_reason, "request_id")
    if result.decision_type != request.decision_type:
        return _invalid(
            state,
            "Decision result type drift.",
            invalid_reason,
            "decision_type",
        )
    if result.actor_id != request.actor_id:
        return _invalid(state, "Decision result actor drift.", invalid_reason, "actor_id")
    option_payloads = {option.option_id: option.payload for option in request.options}
    if result.selected_option_id not in option_payloads:
        return _invalid(
            state,
            "Decision result selected option is not pending.",
            invalid_reason,
            "selected_option_id",
        )
    if result.payload != option_payloads[result.selected_option_id]:
        return _invalid(state, "Decision result payload drift.", invalid_reason, "payload")
    return None


def _invalid(
    state: GameState,
    message: str,
    invalid_reason: str,
    field: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={"invalid_reason": invalid_reason, "field": field},
    )


def _violation(code: str, message: str) -> ProposalViolation:
    return ProposalViolation(violation_code=code, message=message)


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Cult Ambush battle phase must be a string.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Cult Ambush battle phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Cult Ambush {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"Cult Ambush {field_name} must be positive.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GameLifecycleError(f"Cult Ambush {field_name} must be positive.")
    return number


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"Cult Ambush {field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"Cult Ambush {field_name} must be finite.")
    return number


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"Cult Ambush {field_name} must be a bool.")
    return value
