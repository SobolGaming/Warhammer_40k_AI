from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_MOVE_PENDING_STATUS,
    ChargeDistanceState,
    ChargeDistanceStatePayload,
    ChargeEligibilityContext,
    ChargeRollRequest,
    ChargeRollResult,
    ChargeTargetCandidate,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


SELECT_CHARGING_UNIT_DECISION_TYPE = "select_charging_unit"
COMPLETE_CHARGE_PHASE_OPTION_ID = "complete_charge_phase"
_COMPLETE_CHARGE_PHASE_STATUS = "charge_phase_complete"
_CHARGE_MOVE_PENDING_PHASE15B_STATUS = "charge_move_pending_phase15b"


class ChargingUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class ChargePhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    phase_complete: bool
    selected_unit_ids: list[str]
    active_selection: ChargingUnitSelectionPayload | None
    distance_states: list[ChargeDistanceStatePayload]


@dataclass(frozen=True, slots=True)
class ChargingUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargingUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargingUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargingUnitSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ChargingUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ChargingUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> ChargingUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ChargingUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseState:
    battle_round: int
    active_player_id: str
    phase_complete: bool = False
    selected_unit_ids: tuple[str, ...] = ()
    active_selection: ChargingUnitSelection | None = None
    distance_states: tuple[ChargeDistanceState, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargePhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("ChargePhaseState active_player_id", self.active_player_id),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("ChargePhaseState phase_complete must be a bool.")
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "ChargePhaseState selected_unit_ids", self.selected_unit_ids
            ),
        )
        if self.active_selection is not None:
            if type(self.active_selection) is not ChargingUnitSelection:
                raise GameLifecycleError(
                    "ChargePhaseState active_selection must be ChargingUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError("Charge active_selection active player drift.")
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError("Charge active_selection battle round drift.")
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError("Charge active_selection must be selected.")
        object.__setattr__(
            self,
            "distance_states",
            _validate_charge_distance_states(self.distance_states),
        )
        if self.phase_complete and self.active_selection is not None:
            raise GameLifecycleError("Completed Charge phase cannot have active_selection.")
        if self.phase_complete and self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Completed Charge phase cannot have pending charge movement.")

    def with_unit_selection(self, selection: ChargingUnitSelection) -> Self:
        if type(selection) is not ChargingUnitSelection:
            raise GameLifecycleError("Charge selection must be ChargingUnitSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a charging unit after phase completion.")
        if self.active_selection is not None:
            raise GameLifecycleError("Charge unit selection requires no active selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Charge selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Charge selection battle round drift.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Charge unit was already selected.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            active_selection=selection,
            distance_states=self.distance_states,
        )

    def with_charge_roll_result(self, roll_result: ChargeRollResult) -> Self:
        if type(roll_result) is not ChargeRollResult:
            raise GameLifecycleError("Charge roll result must be ChargeRollResult.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot record a charge roll after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Charge roll requires active_selection.")
        if roll_result.request.player_id != self.active_player_id:
            raise GameLifecycleError("Charge roll player drift.")
        if roll_result.request.battle_round != self.battle_round:
            raise GameLifecycleError("Charge roll battle round drift.")
        if roll_result.request.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Charge roll unit drift.")
        distance_state = ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id=roll_result.request.source_decision_request_id,
            source_decision_result_id=roll_result.request.source_decision_result_id,
        )
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            active_selection=self.active_selection if roll_result.move_available else None,
            distance_states=(*self.distance_states, distance_state),
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Charge completion requires no active selection.")
        if self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Charge completion requires no pending charge movement.")
        skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=True,
            selected_unit_ids=tuple(sorted({*self.selected_unit_ids, *skipped_ids})),
            active_selection=None,
            distance_states=self.distance_states,
        )

    def move_pending_distance_state(self) -> ChargeDistanceState | None:
        if self.active_selection is None:
            return None
        for distance_state in reversed(self.distance_states):
            if (
                distance_state.roll_result.request.unit_instance_id
                == self.active_selection.unit_instance_id
                and distance_state.roll_result.status == CHARGE_MOVE_PENDING_STATUS
            ):
                return distance_state
        return None

    def to_payload(self) -> ChargePhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase_complete": self.phase_complete,
            "selected_unit_ids": list(self.selected_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "distance_states": [distance.to_payload() for distance in self.distance_states],
        }

    @classmethod
    def from_payload(cls, payload: ChargePhaseStatePayload) -> Self:
        selection_payload = payload["active_selection"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase_complete=payload["phase_complete"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            active_selection=(
                None
                if selection_payload is None
                else ChargingUnitSelection.from_payload(selection_payload)
            ),
            distance_states=tuple(
                ChargeDistanceState.from_payload(distance)
                for distance in payload["distance_states"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ChargePhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.CHARGE

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        del reaction_queue
        _validate_charge_phase_state(state)
        charge_state = _ensure_charge_phase_state(state=state)
        pending_distance_state = charge_state.move_pending_distance_state()
        if pending_distance_state is not None:
            return _charge_move_pending_status(
                state=state,
                roll_result=pending_distance_state.roll_result,
            )
        if charge_state.active_selection is not None:
            raise GameLifecycleError("Charge active_selection requires pending charge movement.")
        if charge_state.phase_complete:
            decisions.event_log.append(
                "charge_phase_completed",
                _charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )

        legal_unit_ids = _legal_charging_unit_ids(
            state=state,
            charge_state=charge_state,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
        )
        if not legal_unit_ids:
            state.charge_phase_state = charge_state.with_phase_complete()
            decisions.event_log.append(
                "charge_phase_completed",
                _charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_CHARGING_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload=validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.CHARGE.value,
                    "active_player_id": _active_player_id(state),
                }
            ),
            options=_charging_unit_options(
                state=state,
                unit_ids=legal_unit_ids,
                include_complete=True,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            ),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "charging_unit_selection_requested",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                    "phase": BattlePhase.CHARGE.value,
                    "request_id": request.request_id,
                    "legal_unit_count": len(legal_unit_ids),
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "legal_unit_count": len(legal_unit_ids),
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if result.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE:
            return _apply_charging_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        raise GameLifecycleError("Charge phase received unsupported decision type.")


def _apply_charging_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_charge_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Charging unit selection actor must be the active player.")
    charge_state = state.charge_phase_state
    if charge_state is None:
        raise GameLifecycleError("Charging unit selection requires charge_phase_state.")
    if result.selected_option_id == COMPLETE_CHARGE_PHASE_OPTION_ID:
        skipped_unit_ids = _legal_charging_unit_ids(
            state=state,
            charge_state=charge_state,
            ruleset_descriptor=ruleset_descriptor,
        )
        state.charge_phase_state = charge_state.with_phase_complete(
            skipped_unit_ids=skipped_unit_ids,
        )
        decisions.event_log.append(
            "charge_phase_completion_declared",
            _charge_phase_status_payload(
                state=state,
                phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                skipped_unit_ids=skipped_unit_ids,
            ),
        )
        return None

    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    legal_unit_ids = _legal_charging_unit_ids(
        state=state,
        charge_state=charge_state,
        ruleset_descriptor=ruleset_descriptor,
    )
    if unit_instance_id not in legal_unit_ids:
        raise GameLifecycleError("Charging unit selection is not currently legal.")
    selection = ChargingUnitSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.charge_phase_state = charge_state.with_unit_selection(selection)
    decisions.event_log.append(
        "charging_unit_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": active_player_id,
                "unit_instance_id": unit_instance_id,
                "source_decision_request_id": result.request_id,
                "source_decision_result_id": result.result_id,
            }
        ),
    )
    return _resolve_charge_roll(
        state=state,
        selection=selection,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
    )


def _resolve_charge_roll(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    roll_request = ChargeRollRequest(
        request_id=f"charge-roll:{selection.result_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        source_decision_request_id=selection.request_id,
        source_decision_result_id=selection.result_id,
    )
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        roll_request.spec
    )
    reachable_distances = _reachable_charge_target_distances(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        maximum_distance_inches=roll_state.current_total,
        ruleset_descriptor=ruleset_descriptor,
    )
    roll_result = ChargeRollResult.from_roll_state(
        request=roll_request,
        roll_state=roll_state,
        reachable_target_distances_inches=reachable_distances,
    )
    charge_state = state.charge_phase_state
    if charge_state is None:
        raise GameLifecycleError("Charge roll requires charge_phase_state.")
    state.charge_phase_state = charge_state.with_charge_roll_result(roll_result)
    decisions.event_log.append(
        "charge_roll_resolved",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    if not roll_result.move_available:
        decisions.event_log.append(
            "charge_no_move_possible",
            phase15a_charge_roll_payload(roll_result=roll_result),
        )
        return None
    decisions.event_log.append(
        "charge_move_required",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    return _charge_move_pending_status(state=state, roll_result=roll_result)


def _charge_move_pending_status(
    *,
    state: GameState,
    roll_result: ChargeRollResult,
) -> LifecycleStatus:
    payload = phase15a_charge_roll_payload(roll_result=roll_result)
    payload["phase_body_status"] = _CHARGE_MOVE_PENDING_PHASE15B_STATUS
    return LifecycleStatus.unsupported(
        stage=GameLifecycleStage.BATTLE,
        message="Charge movement is deferred to Phase 15B.",
        payload=validate_json_value(payload),
    )


def _legal_charging_unit_ids(
    *,
    state: GameState,
    charge_state: ChargePhaseState,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[str, ...]:
    active_player_id = _active_player_id(state)
    placed_unit_ids = _active_player_placed_unit_ids(state=state, player_id=active_player_id)
    legal_ids: list[str] = []
    for unit_id in placed_unit_ids:
        ineligible_reason = _charge_unit_ineligibility_reason(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_state=charge_state,
            ignore_already_selected=False,
        )
        if ineligible_reason is None:
            legal_ids.append(unit_id)
    return tuple(sorted(legal_ids))


def _charge_unit_ineligibility_reason(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_state: ChargePhaseState,
    ignore_already_selected: bool,
) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if not ignore_already_selected and requested_unit_id in charge_state.selected_unit_ids:
        return "charge_unit_already_selected"
    if requested_unit_id not in _active_player_placed_unit_ids(
        state=state,
        player_id=charge_state.active_player_id,
    ):
        return "charge_unit_off_battlefield"
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=charge_state.active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=requested_unit_id,
    )
    if (
        advanced_state is not None
        and ruleset_descriptor.charge_policy.forbids_advance
        and not advanced_state.can_declare_charge
    ):
        return "charge_unit_advanced"
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=charge_state.active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=requested_unit_id,
    )
    if (
        fell_back_state is not None
        and ruleset_descriptor.charge_policy.forbids_fall_back
        and not fell_back_state.can_declare_charge
    ):
        return "charge_unit_fell_back"
    if ruleset_descriptor.charge_policy.requires_unengaged_unit and _unit_is_engaged(
        state=state,
        unit_instance_id=requested_unit_id,
        player_id=charge_state.active_player_id,
        ruleset_descriptor=ruleset_descriptor,
    ):
        return "charge_unit_engaged"
    candidates = _charge_target_candidates(
        state=state,
        unit_instance_id=requested_unit_id,
        ruleset_descriptor=ruleset_descriptor,
    )
    if not any(candidate.is_legal for candidate in candidates):
        return "charge_unit_no_legal_targets"
    return None


def _charge_target_candidates(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[ChargeTargetCandidate, ...]:
    scenario = _battlefield_scenario(state)
    max_range = ruleset_descriptor.charge_policy.max_declaration_range_inches
    candidates: list[ChargeTargetCandidate] = []
    for target_id in _enemy_placed_unit_ids(state=state, player_id=_active_player_id(state)):
        distance = _closest_unit_distance_inches(
            scenario=scenario,
            source_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_id,
        )
        is_legal = distance <= max_range
        candidates.append(
            ChargeTargetCandidate(
                target_unit_instance_id=target_id,
                closest_distance_inches=distance,
                is_legal=is_legal,
                violation_code=None if is_legal else "target_out_of_declaration_range",
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.target_unit_instance_id))


def _reachable_charge_target_distances(
    *,
    state: GameState,
    unit_instance_id: str,
    maximum_distance_inches: int,
    ruleset_descriptor: RulesetDescriptor,
) -> dict[str, float]:
    distances: dict[str, float] = {}
    for candidate in _charge_target_candidates(
        state=state,
        unit_instance_id=unit_instance_id,
        ruleset_descriptor=ruleset_descriptor,
    ):
        if candidate.is_legal and candidate.closest_distance_inches <= maximum_distance_inches:
            distances[candidate.target_unit_instance_id] = candidate.closest_distance_inches
    return dict(sorted(distances.items()))


def _closest_unit_distance_inches(
    *,
    scenario: BattlefieldScenario,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
) -> float:
    source_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=source_unit_instance_id,
    )
    target_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
    )
    if not source_models or not target_models:
        raise GameLifecycleError("Charge distance requires placed models.")
    return min(
        source_model.range_to(target_model)
        for source_model in source_models
        for target_model in target_models
    )


def _unit_is_engaged(
    *,
    state: GameState,
    unit_instance_id: str,
    player_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    scenario = _battlefield_scenario(state)
    source_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
    enemy_models = tuple(
        model
        for enemy_unit_id in _enemy_placed_unit_ids(state=state, player_id=player_id)
        for model in _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=enemy_unit_id,
        )
    )
    policy = ruleset_descriptor.engagement_policy
    return any(
        source_model.is_within_engagement_range(
            enemy_model,
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        )
        for source_model in source_models
        for enemy_model in enemy_models
    )


def _geometry_models_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    try:
        placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Charge unit placement is unavailable.") from exc
    unit = scenario.unit_instance_for_placement(placement)
    models: list[GeometryModel] = []
    for model_placement in placement.model_placements:
        model_instance = None
        for model in unit.own_models:
            if model.model_instance_id == model_placement.model_instance_id:
                model_instance = model
                break
        if model_instance is None:
            raise GameLifecycleError("Charge model placement is invalid.")
        models.append(geometry_model_for_placement(model=model_instance, placement=model_placement))
    return tuple(models)


def _charging_unit_options(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    include_complete: bool,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        unit = _unit_by_id(state=state, unit_instance_id=unit_id)
        target_candidates = _charge_target_candidates(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
        )
        eligibility_context = ChargeEligibilityContext(
            player_id=_active_player_id(state),
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
            target_candidates=target_candidates,
        )
        options.append(
            DecisionOption(
                option_id=unit_id,
                label=unit.name,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_CHARGING_UNIT_DECISION_TYPE,
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.CHARGE.value,
                        "active_player_id": _active_player_id(state),
                        "unit_instance_id": unit_id,
                        "eligibility_context": eligibility_context.to_payload(),
                    }
                ),
            )
        )
    if include_complete:
        options.append(
            DecisionOption(
                option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
                label="Complete Charge Phase",
                payload=validate_json_value(
                    {
                        "submission_kind": COMPLETE_CHARGE_PHASE_OPTION_ID,
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.CHARGE.value,
                        "active_player_id": state.active_player_id,
                        "phase_body_status": _COMPLETE_CHARGE_PHASE_STATUS,
                        "skipped_unit_ids": list(unit_ids),
                    }
                ),
            )
        )
    return tuple(options)


def _ensure_charge_phase_state(*, state: GameState) -> ChargePhaseState:
    current = state.charge_phase_state
    active_player_id = _active_player_id(state)
    if current is not None:
        return current
    state.charge_phase_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    return state.charge_phase_state


def _validate_charge_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Charge phase requires battle stage.")
    if state.current_battle_phase is not BattlePhase.CHARGE:
        raise GameLifecycleError("Charge phase requires CHARGE phase.")
    _active_player_id(state)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    if state.charge_phase_state is None:
        return
    charge_state = state.charge_phase_state
    if charge_state.battle_round != state.battle_round:
        raise GameLifecycleError("charge_phase_state battle round drift.")
    if charge_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("charge_phase_state active player drift.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Charge battlefield scenario is invalid.") from exc
    return scenario


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Charge phase requires active_player_id.")
    return state.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    try:
        placed_army = battlefield_state.placed_army_for_player(player_id)
    except PlacementError:
        return ()
    return tuple(sorted(placement.unit_instance_id for placement in placed_army.unit_placements))


def _enemy_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    unit_ids: list[str] = []
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        unit_ids.extend(placement.unit_instance_id for placement in placed_army.unit_placements)
    return tuple(sorted(unit_ids))


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Charge unit_instance_id is unknown.")


def _charge_phase_status_payload(
    *,
    state: GameState,
    phase_body_status: str,
    skipped_unit_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.CHARGE.value,
        "phase_body_status": phase_body_status,
        "skipped_unit_ids": list(skipped_ids),
    }


def _decision_payload_object(payload: JsonValue) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return cast(dict[str, object], payload)


def _payload_string(payload: dict[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Payload field {key} must be a string.")
    return _validate_identifier(key, value)


def _ruleset_descriptor_for_handler(handler: ChargePhaseHandler) -> RulesetDescriptor:
    if type(handler) is not ChargePhaseHandler:
        raise GameLifecycleError("Charge ruleset descriptor requires a ChargePhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Charge phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _validate_charge_distance_states(values: object) -> tuple[ChargeDistanceState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ChargePhaseState distance_states must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    states: list[ChargeDistanceState] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ChargeDistanceState:
            raise GameLifecycleError(
                "ChargePhaseState distance_states must contain ChargeDistanceState."
            )
        result_id = value.source_decision_result_id
        if result_id in seen:
            raise GameLifecycleError("ChargePhaseState distance_states duplicate result_id.")
        seen.add(result_id)
        states.append(value)
    return tuple(states)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value
