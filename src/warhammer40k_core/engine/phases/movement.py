from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_MOVEMENT_UNIT_DECISION_TYPE = "select_movement_unit"
SELECT_MOVEMENT_ACTION_DECISION_TYPE = "select_movement_action"


class MovementPhaseStepKind(StrEnum):
    MOVE_UNITS = "move_units"
    REINFORCEMENTS = "reinforcements"


class MovementPhaseActionKind(StrEnum):
    REMAIN_STATIONARY = "remain_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"


_SUPPORTED_MOVEMENT_PHASE_ACTIONS = (
    MovementPhaseActionKind.REMAIN_STATIONARY,
    MovementPhaseActionKind.NORMAL_MOVE,
)
_UNSUPPORTED_MOVEMENT_PHASE_ACTIONS = (
    MovementPhaseActionKind.ADVANCE,
    MovementPhaseActionKind.FALL_BACK,
)
_MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT = (
    MovementPhaseActionKind.REMAIN_STATIONARY,
    MovementPhaseActionKind.NORMAL_MOVE,
    MovementPhaseActionKind.ADVANCE,
)
_MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT = (
    MovementPhaseActionKind.REMAIN_STATIONARY,
    MovementPhaseActionKind.FALL_BACK,
)
_DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES = 60.0
_DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES = 44.0


class MovementUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class MovementPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    selected_unit_ids: list[str]
    moved_unit_ids: list[str]
    active_selection: MovementUnitSelectionPayload | None


class MovementActionAvailabilityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: list[str]


class MovementActionAvailabilityResultPayload(TypedDict):
    context: MovementActionAvailabilityContextPayload
    available_actions: list[str]
    unavailable_actions: list[str]


@dataclass(frozen=True, slots=True)
class MovementActionAvailabilityContext:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "MovementActionAvailabilityContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "MovementActionAvailabilityContext unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementActionAvailabilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "enemy_engagement_model_ids",
            _validate_identifier_tuple(
                "MovementActionAvailabilityContext enemy_engagement_model_ids",
                self.enemy_engagement_model_ids,
            ),
        )

    @property
    def is_within_enemy_engagement_range(self) -> bool:
        return bool(self.enemy_engagement_model_ids)

    def evaluate(self) -> MovementActionAvailabilityResult:
        available_actions: tuple[MovementPhaseActionKind, ...]
        if self.is_within_enemy_engagement_range:
            available_actions = _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT
        else:
            available_actions = _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT
        unavailable_actions = tuple(
            action for action in MovementPhaseActionKind if action not in available_actions
        )
        return MovementActionAvailabilityResult(
            context=self,
            available_actions=available_actions,
            unavailable_actions=unavailable_actions,
        )

    def to_payload(self) -> MovementActionAvailabilityContextPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "player_id": self.player_id,
            "enemy_engagement_model_ids": list(self.enemy_engagement_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: MovementActionAvailabilityContextPayload) -> Self:
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            player_id=payload["player_id"],
            enemy_engagement_model_ids=tuple(payload["enemy_engagement_model_ids"]),
        )


@dataclass(frozen=True, slots=True)
class MovementActionAvailabilityResult:
    context: MovementActionAvailabilityContext
    available_actions: tuple[MovementPhaseActionKind, ...]
    unavailable_actions: tuple[MovementPhaseActionKind, ...]

    def __post_init__(self) -> None:
        if type(self.context) is not MovementActionAvailabilityContext:
            raise GameLifecycleError("MovementActionAvailabilityResult context must be a context.")
        object.__setattr__(
            self,
            "available_actions",
            _validate_movement_action_tuple(
                "MovementActionAvailabilityResult available_actions",
                self.available_actions,
            ),
        )
        object.__setattr__(
            self,
            "unavailable_actions",
            _validate_movement_action_tuple(
                "MovementActionAvailabilityResult unavailable_actions",
                self.unavailable_actions,
            ),
        )
        if set(self.available_actions) & set(self.unavailable_actions):
            raise GameLifecycleError(
                "MovementActionAvailabilityResult actions must not be both available "
                "and unavailable."
            )
        if set(self.available_actions) | set(self.unavailable_actions) != set(
            MovementPhaseActionKind
        ):
            raise GameLifecycleError(
                "MovementActionAvailabilityResult must classify every movement action."
            )

    def is_available(self, action: object) -> bool:
        return movement_phase_action_kind_from_token(action) in self.available_actions

    def to_payload(self) -> MovementActionAvailabilityResultPayload:
        return {
            "context": self.context.to_payload(),
            "available_actions": [action.value for action in self.available_actions],
            "unavailable_actions": [action.value for action in self.unavailable_actions],
        }

    @classmethod
    def from_payload(cls, payload: MovementActionAvailabilityResultPayload) -> Self:
        return cls(
            context=MovementActionAvailabilityContext.from_payload(payload["context"]),
            available_actions=tuple(
                movement_phase_action_kind_from_token(action)
                for action in payload["available_actions"]
            ),
            unavailable_actions=tuple(
                movement_phase_action_kind_from_token(action)
                for action in payload["unavailable_actions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementUnitSelection unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("MovementUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("MovementUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> MovementUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: MovementUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class MovementPhaseState:
    battle_round: int
    active_player_id: str
    selected_unit_ids: tuple[str, ...] = ()
    moved_unit_ids: tuple[str, ...] = ()
    active_selection: MovementUnitSelection | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("MovementPhaseState active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState selected_unit_ids",
                self.selected_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "moved_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState moved_unit_ids",
                self.moved_unit_ids,
            ),
        )
        for unit_id in self.moved_unit_ids:
            if unit_id not in self.selected_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState moved_unit_ids must be in selected_unit_ids."
                )
        if self.active_selection is not None:
            if type(self.active_selection) is not MovementUnitSelection:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must be a MovementUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must match active_player_id."
                )
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must match battle_round."
                )
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must be in selected_unit_ids."
                )
            if self.active_selection.unit_instance_id in self.moved_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must not already be moved."
                )

    def legal_unit_ids(self, scenario: BattlefieldScenario) -> tuple[str, ...]:
        if type(scenario) is not BattlefieldScenario:
            raise GameLifecycleError("MovementPhaseState scenario must be a BattlefieldScenario.")
        try:
            scenario.assert_all_mustered_models_placed()
            placed_army = scenario.battlefield_state.placed_army_for_player(
                self.active_player_id,
            )
        except PlacementError as exc:
            raise GameLifecycleError("Movement phase requires complete placed armies.") from exc
        selected = set(self.selected_unit_ids)
        return tuple(
            placement.unit_instance_id
            for placement in placed_army.unit_placements
            if placement.unit_instance_id not in selected
        )

    def with_unit_selection(self, selection: MovementUnitSelection) -> Self:
        if type(selection) is not MovementUnitSelection:
            raise GameLifecycleError("Movement selection must be a MovementUnitSelection.")
        if self.active_selection is not None:
            raise GameLifecycleError("Movement selection requires no active movement selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Movement selection player_id must match active player.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Movement selection battle_round must match phase state.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Movement unit has already been selected this phase.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            moved_unit_ids=self.moved_unit_ids,
            active_selection=selection,
        )

    def with_activation_complete(self, unit_instance_id: str) -> Self:
        completed_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.active_selection is None:
            raise GameLifecycleError("Movement activation completion requires active_selection.")
        if completed_unit_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Movement activation completion must match active_selection.")
        if completed_unit_id in self.moved_unit_ids:
            raise GameLifecycleError("Movement unit has already completed movement.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=(*self.moved_unit_ids, completed_unit_id),
            active_selection=None,
        )

    def to_payload(self) -> MovementPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "selected_unit_ids": list(self.selected_unit_ids),
            "moved_unit_ids": list(self.moved_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: MovementPhaseStatePayload) -> Self:
        active_selection_payload = payload["active_selection"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            moved_unit_ids=tuple(payload["moved_unit_ids"]),
            active_selection=(
                None
                if active_selection_payload is None
                else MovementUnitSelection.from_payload(active_selection_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class NormalMoveResolution:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("NormalMoveResolution unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "NormalMoveResolution attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "NormalMoveResolution attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("NormalMoveResolution witness must be a PathWitness.")
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "NormalMoveResolution path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "NormalMoveResolution terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "NormalMoveResolution coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "NormalMoveResolution rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "NormalMoveResolution movement_payload",
                self.movement_payload,
            ),
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    def transition_batch(self, *, before: UnitPlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Normal Move cannot emit displacement records.")
        return _normal_move_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
        )

    def selected_payload_drift_code(self, payload: dict[str, JsonValue]) -> str | None:
        selected_payload = _validate_json_object("Normal Move selected payload", payload)
        if selected_payload.get("witness") != self.witness.to_payload():
            return "normal_move_witness_drift"
        expected_model_movements = self.movement_payload["model_movements"]
        if selected_payload.get("model_movements") != expected_model_movements:
            return "normal_move_model_movement_witness_drift"
        return None


@dataclass(frozen=True, slots=True)
class MovementPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "MovementPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.MOVEMENT

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus:
        _validate_movement_phase_state(state)
        movement_state = _ensure_movement_phase_state(state=state, decisions=decisions)
        active_selection = movement_state.active_selection
        if active_selection is not None:
            return _request_movement_action(
                state=state,
                decisions=decisions,
                active_selection=active_selection,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )

        scenario = _battlefield_scenario(state)
        legal_unit_ids = movement_state.legal_unit_ids(scenario)
        if not legal_unit_ids:
            decisions.event_log.append(
                "movement_phase_unit_selection_completed",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "unit_selection_complete",
                },
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "unit_selection_complete",
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                },
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_MOVEMENT_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": _active_player_id(state),
            },
            options=_movement_unit_options(scenario=scenario, unit_ids=legal_unit_ids),
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
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
        if result.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE:
            return _apply_movement_action_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type != SELECT_MOVEMENT_UNIT_DECISION_TYPE:
            raise GameLifecycleError("MovementPhaseHandler received an unsupported decision_type.")
        _validate_movement_phase_state(state)
        active_player_id = _active_player_id(state)
        if result.actor_id != active_player_id:
            raise GameLifecycleError("Movement unit selection actor must be the active player.")
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Movement unit selection requires movement phase state.")

        payload = _decision_payload_object(result.payload)
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        scenario = _battlefield_scenario(state)
        if unit_instance_id not in movement_state.legal_unit_ids(scenario):
            raise GameLifecycleError("Movement unit selection is not currently legal.")

        selection = MovementUnitSelection(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            request_id=result.request_id,
            result_id=result.result_id,
        )
        state.movement_phase_state = movement_state.with_unit_selection(selection)
        decisions.event_log.append(
            "movement_unit_selected",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "unit_selected",
            },
        )
        return None


def _request_movement_action(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: MovementUnitSelection,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        active_selection.unit_instance_id
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": active_selection.unit_instance_id,
        },
        options=_movement_action_options(
            scenario=scenario,
            unit_placement=unit_placement,
            ruleset_descriptor=ruleset_descriptor,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": active_selection.unit_instance_id,
            "legal_action_count": len(request.options),
        },
    )


def _apply_movement_action_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Movement action actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement action requires active movement selection.")

    active_selection = movement_state.active_selection
    payload = _decision_payload_object(result.payload)
    action = movement_phase_action_kind_from_token(
        _payload_string(payload, key="movement_phase_action")
    )
    if _payload_string(payload, key="unit_instance_id") != active_selection.unit_instance_id:
        raise GameLifecycleError("Movement action unit_instance_id must match active_selection.")

    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        active_selection.unit_instance_id
    )
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    if not availability_result.is_available(action):
        raise GameLifecycleError("Movement action is not currently legal for the selected unit.")

    if action is MovementPhaseActionKind.REMAIN_STATIONARY:
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=None,
            movement_payload={
                "movement_inches": 0,
                "model_movements": [],
            },
        )
        return None
    if action is MovementPhaseActionKind.NORMAL_MOVE:
        witness = _payload_path_witness(payload, key="witness")
        resolution = resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            path_witness=witness,
        )
        drift_code = resolution.selected_payload_drift_code(payload)
        if drift_code is not None:
            decisions.event_log.append(
                "movement_action_invalid",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "unit_instance_id": active_selection.unit_instance_id,
                    "movement_phase_action": action.value,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "phase_body_status": "movement_action_invalid",
                    "violation_code": drift_code,
                    **resolution.movement_payload,
                },
            )
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message="Normal Move replay payload drift.",
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "movement_action_invalid",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                    "movement_phase_action": action.value,
                    "violation_code": drift_code,
                },
            )
        if not resolution.is_valid:
            violation_code = _normal_move_violation_code(resolution)
            invalid_payload: dict[str, JsonValue] = {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "movement_phase_action": action.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "movement_action_invalid",
                "violation_code": violation_code,
                **resolution.movement_payload,
            }
            if resolution.rollback_record is not None:
                invalid_payload["rollback_record"] = validate_json_value(
                    resolution.rollback_record.to_payload()
                )
            decisions.event_log.append("movement_action_invalid", invalid_payload)
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message=_normal_move_invalid_message(violation_code),
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "movement_action_invalid",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                    "movement_phase_action": action.value,
                    "violation_code": violation_code,
                },
            )
        transition_batch = resolution.transition_batch(before=unit_placement)
        battlefield_state = state.battlefield_state
        if battlefield_state is None:
            raise GameLifecycleError("Normal Move requires battlefield_state.")
        state.battlefield_state = battlefield_state.with_unit_placement(
            resolution.attempted_placement
        )
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=resolution.movement_payload,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            transition_batch=transition_batch,
        )
        return None

    decisions.event_log.append(
        "movement_action_unsupported",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": active_selection.unit_instance_id,
            "movement_phase_action": action.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "movement_action_unsupported",
        },
    )
    return LifecycleStatus.unsupported(
        stage=GameLifecycleStage.BATTLE,
        message=(
            f"Movement action is not supported by the current implementation slice: {action.value}."
        ),
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "movement_action_unsupported",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "movement_phase_action": action.value,
        },
    )


def _complete_movement_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind | None = None,
    transition_batch: BattlefieldTransitionBatch | None = None,
) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement activation completion requires active selection.")
    active_selection = movement_state.active_selection
    state.movement_phase_state = movement_state.with_activation_complete(
        active_selection.unit_instance_id
    )
    event_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_selection.player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": active_selection.unit_instance_id,
        "movement_phase_action": action.value,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "phase_body_status": "activation_complete",
        "witness": None if witness is None else validate_json_value(witness.to_payload()),
    }
    if displacement_kind is not None:
        event_payload["displacement_kind"] = displacement_kind.value
    if transition_batch is not None:
        event_payload["transition_batch"] = validate_json_value(transition_batch.to_payload())
    event_payload.update(movement_payload)
    decisions.event_log.append("movement_activation_completed", event_payload)


def _movement_action_options(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[DecisionOption, ...]:
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    options: list[DecisionOption] = []
    for action in availability_result.available_actions:
        if action is MovementPhaseActionKind.REMAIN_STATIONARY:
            options.append(
                DecisionOption(
                    option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
                    label="Remain Stationary",
                    payload={
                        "movement_phase_action": MovementPhaseActionKind.REMAIN_STATIONARY.value,
                        "unit_instance_id": unit_placement.unit_instance_id,
                        "movement_inches": 0,
                        "model_movements": [],
                        "witness": None,
                    },
                )
            )
            continue
        if action is MovementPhaseActionKind.NORMAL_MOVE:
            resolution = resolve_normal_move(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
                path_witness=None,
            )
            options.append(
                DecisionOption(
                    option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
                    label="Normal Move",
                    payload=validate_json_value(
                        {
                            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                            "displacement_kind": ModelDisplacementKind.NORMAL_MOVE.value,
                            "unit_instance_id": unit_placement.unit_instance_id,
                            "witness": resolution.witness.to_payload(),
                            **resolution.movement_payload,
                        }
                    ),
                )
            )
            continue
        options.append(
            DecisionOption(
                option_id=action.value,
                label=action.value.replace("_", " ").title(),
                payload={
                    "movement_phase_action": action.value,
                    "unit_instance_id": unit_placement.unit_instance_id,
                },
            )
        )
    return tuple(options)


def resolve_normal_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    path_witness: PathWitness | None = None,
    battlefield_width_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> NormalMoveResolution:
    return _resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        path_witness=path_witness,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain=terrain,
        terrain_features=terrain_features,
    )


def _resolve_normal_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    path_witness: PathWitness | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain: tuple[TerrainVolume, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> NormalMoveResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Normal Move requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Normal Move requires a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Normal Move unit_placement must be a UnitPlacement.")
    witness = (
        _default_normal_move_witness(scenario=scenario, unit_placement=unit_placement)
        if path_witness is None
        else path_witness
    )
    _validate_normal_move_witness_matches_unit(
        witness=witness,
        unit_placement=unit_placement,
    )
    unit = scenario.unit_instance_for_placement(unit_placement)
    moved_placements: list[ModelPlacement] = []
    for placement in unit_placement.model_placements:
        moved_placements.append(
            placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
        )
    attempted_placement = unit_placement.with_model_placements(tuple(moved_placements))
    path_validation_results: list[PathValidationResult] = []
    terrain_path_legality_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    max_movement_inches = 0.0
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = float(_model_movement_inches(model))
        max_movement_inches = max(max_movement_inches, movement_inches)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=unit.keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=MovementMode.NORMAL,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        )
        path_result = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=unit_placement,
                attempted_placement=attempted_placement,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            terrain=(),
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=unit_placement.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            movement_distance_budget_inches=movement_inches,
        ).validate()
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain,
            terrain_features=terrain_features,
        ).validate()
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movements.append(
            validate_json_value(
                {
                    "model_instance_id": placement.model_instance_id,
                    "movement_inches": movement_inches,
                    "base_size": model.base_size.to_payload(),
                    "start_pose": placement.pose.to_payload(),
                    "end_pose": witness.final_pose_for_model(
                        placement.model_instance_id
                    ).to_payload(),
                    "movement_distance_witness": (
                        None
                        if path_result.movement_distance_witness is None
                        else path_result.movement_distance_witness.to_payload()
                    ),
                    "path_validation_result": path_result.to_payload(),
                    "terrain_path_legality_result": terrain_result.to_payload(),
                }
            )
        )
    _resolved_placement, coherency_result, rollback_record = (
        resolve_unit_movement_endpoint_coherency(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            before=unit_placement,
            attempted=attempted_placement,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        )
    )
    movement_payload: dict[str, JsonValue] = {
        "movement_inches": max_movement_inches,
        "model_movements": model_movements,
        "path_validation_results": validate_json_value(
            [result.to_payload() for result in path_validation_results]
        ),
        "terrain_path_legality_results": validate_json_value(
            [result.to_payload() for result in terrain_path_legality_results]
        ),
        "coherency_result": validate_json_value(coherency_result.to_payload()),
    }
    return NormalMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=attempted_placement,
        witness=witness,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
    )


def _default_normal_move_witness(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = _model_movement_inches(model)
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                _translated_pose(placement.pose, movement_inches=movement_inches),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _normal_move_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    displacement_records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Normal Move transition references an unknown model.")
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.MOVEMENT.value,
                source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(displacements=tuple(displacement_records))


def _movement_action_availability_result(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> MovementActionAvailabilityResult:
    return _movement_action_availability_context(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
    ).evaluate()


def _movement_action_availability_context(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> MovementActionAvailabilityContext:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Movement action availability requires a scenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Movement action availability requires a UnitPlacement.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Movement action availability requires a RulesetDescriptor.")
    return MovementActionAvailabilityContext(
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        unit_instance_id=unit_placement.unit_instance_id,
        player_id=unit_placement.player_id,
        enemy_engagement_model_ids=_enemy_engagement_model_ids_for_unit(
            scenario=scenario,
            unit_placement=unit_placement,
            ruleset_descriptor=ruleset_descriptor,
        ),
    )


def _enemy_engagement_model_ids_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[str, ...]:
    friendly_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    enemy_model_ids: set[str] = set()
    for friendly_model in friendly_models:
        for enemy_model in enemy_models:
            if friendly_model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                enemy_model_ids.add(enemy_model.model_id)
    return tuple(sorted(enemy_model_ids))


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            placements = (
                attempted_placement.model_placements
                if current_unit_placement.unit_instance_id == unit_placement.unit_instance_id
                else current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[Model, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(enemy_models)


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _unit_has_vehicle_or_monster_keyword(keywords: tuple[str, ...]) -> bool:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    return "VEHICLE" in keyword_set or "MONSTER" in keyword_set


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _validate_normal_move_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: UnitPlacement,
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Normal Move requires a PathWitness.")
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError("Normal Move witness must match the selected unit models.")


def _normal_move_violation_code(resolution: NormalMoveResolution) -> str:
    for path_result in resolution.path_validation_results:
        if path_result.is_valid:
            continue
        return path_result.violations[0].violation_code
    for terrain_result in resolution.terrain_path_legality_results:
        if terrain_result.is_valid:
            continue
        return terrain_result.violations[0].violation_code
    if resolution.rollback_record is not None:
        return "unit_coherency_broken"
    return "normal_move_invalid"


def _normal_move_invalid_message(violation_code: str) -> str:
    code = _validate_identifier("Normal Move violation_code", violation_code)
    if code == "unit_coherency_broken":
        return "Normal Move endpoint violates unit coherency."
    if code.startswith("terrain") or code in {
        "end_on_forbidden_terrain",
        "upper_floor_keyword_forbidden",
        "base_overhangs_support_surface",
        "model_cannot_be_placed_at_endpoint",
        "ends_mid_climb",
        "manual_geometry_required",
    }:
        return "Normal Move terrain path is invalid."
    return "Normal Move path is invalid."


def _ensure_movement_phase_state(
    *,
    state: GameState,
    decisions: DecisionController,
) -> MovementPhaseState:
    active_player_id = _active_player_id(state)
    current = state.movement_phase_state
    if (
        current is not None
        and current.battle_round == state.battle_round
        and current.active_player_id == active_player_id
    ):
        return current

    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    decisions.event_log.append(
        "movement_phase_entered",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
        },
    )
    return state.movement_phase_state


def _validate_movement_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("MovementPhaseHandler can run only during battle.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("MovementPhaseHandler can run only in the MOVEMENT phase.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Movement phase requires placed battlefield state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )


def _movement_unit_options(
    *,
    scenario: BattlefieldScenario,
    unit_ids: tuple[str, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_id)
        unit = scenario.unit_instance_for_placement(unit_placement)
        options.append(
            DecisionOption(
                option_id=unit.unit_instance_id,
                label=unit.name,
                payload={
                    "unit_instance_id": unit.unit_instance_id,
                    "model_instance_ids": [
                        placement.model_instance_id for placement in unit_placement.model_placements
                    ],
                },
            )
        )
    return tuple(options)


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle state requires an active player.")
    return state.active_player_id


def movement_phase_action_kind_from_token(token: object) -> MovementPhaseActionKind:
    if type(token) is MovementPhaseActionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("MovementPhaseActionKind token must be a string.")
    try:
        return MovementPhaseActionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported MovementPhaseActionKind token: {token}.") from exc


def movement_mode_for_phase_action(action: object) -> MovementMode | None:
    action_kind = movement_phase_action_kind_from_token(action)
    if action_kind is MovementPhaseActionKind.REMAIN_STATIONARY:
        return None
    if action_kind is MovementPhaseActionKind.NORMAL_MOVE:
        return MovementMode.NORMAL
    if action_kind is MovementPhaseActionKind.ADVANCE:
        return MovementMode.ADVANCE
    if action_kind is MovementPhaseActionKind.FALL_BACK:
        return MovementMode.FALL_BACK
    raise GameLifecycleError(f"Unsupported MovementPhaseActionKind token: {action_kind.value}.")


def _model_movement_inches(model: ModelInstance) -> int:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Movement model must be a ModelInstance.")
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.MOVEMENT:
            return characteristic.final
    raise GameLifecycleError("Normal Move requires a Movement characteristic.")


def _translated_pose(pose: Pose, *, movement_inches: int) -> Pose:
    if type(movement_inches) is not int:
        raise GameLifecycleError("movement_inches must be an integer.")
    if movement_inches < 1:
        raise GameLifecycleError("movement_inches must be at least 1.")
    return Pose.at(
        x=pose.position.x + movement_inches,
        y=pose.position.y,
        z=pose.position.z,
        facing_degrees=pose.facing.degrees,
    )


def _ruleset_descriptor_for_handler(handler: MovementPhaseHandler) -> RulesetDescriptor:
    if type(handler) is not MovementPhaseHandler:
        raise GameLifecycleError("Movement ruleset descriptor requires a MovementPhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Movement phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


def _payload_path_witness(payload: dict[str, JsonValue], *, key: str) -> PathWitness:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    json_value = validate_json_value(value)
    if not isinstance(json_value, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return json_value


def _validate_movement_action_tuple(
    field_name: str,
    values: object,
) -> tuple[MovementPhaseActionKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    actions = tuple(
        movement_phase_action_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    seen: set[MovementPhaseActionKind] = set()
    for action in actions:
        if action in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(action)
    return actions


def _validate_path_validation_result_tuple(
    field_name: str,
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[PathValidationResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PathValidationResult:
            raise GameLifecycleError(f"{field_name} must contain PathValidationResult values.")
        results.append(value)
    if not results:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(results)


def _validate_terrain_path_legality_result_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[TerrainPathLegalityResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainPathLegalityResult:
            raise GameLifecycleError(f"{field_name} must contain TerrainPathLegalityResult values.")
        results.append(value)
    if not results:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(results)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
