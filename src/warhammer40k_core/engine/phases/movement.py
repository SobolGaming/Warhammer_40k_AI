from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

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
class MovementPhaseHandler:
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
        scenario = _battlefield_scenario(state)
        unit_placement = scenario.battlefield_state.unit_placement_by_id(
            active_selection.unit_instance_id
        )
        updated_placement, witness, movement_payload = _normal_move_plan(
            scenario=scenario,
            unit_placement=unit_placement,
        )
        transition_batch = _normal_move_transition_batch(
            before=unit_placement,
            after=updated_placement,
            witness=witness,
        )
        battlefield_state = state.battlefield_state
        if battlefield_state is None:
            raise GameLifecycleError("Normal Move requires battlefield_state.")
        state.battlefield_state = battlefield_state.with_unit_placement(updated_placement)
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=movement_payload,
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
        message=f"Movement action is not supported in Phase 10C: {action.value}.",
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
) -> tuple[DecisionOption, ...]:
    _updated_placement, witness, movement_payload = _normal_move_plan(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    return (
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
        ),
        DecisionOption(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            label="Normal Move",
            payload=validate_json_value(
                {
                    "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                    "displacement_kind": ModelDisplacementKind.NORMAL_MOVE.value,
                    "unit_instance_id": unit_placement.unit_instance_id,
                    "witness": witness.to_payload(),
                    **movement_payload,
                }
            ),
        ),
        *(
            DecisionOption(
                option_id=action.value,
                label=action.value.replace("_", " ").title(),
                payload={
                    "movement_phase_action": action.value,
                    "unit_instance_id": unit_placement.unit_instance_id,
                },
            )
            for action in _UNSUPPORTED_MOVEMENT_PHASE_ACTIONS
        ),
    )


def _normal_move_plan(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[UnitPlacement, PathWitness, dict[str, JsonValue]]:
    model_paths: list[tuple[str, Pose, Pose]] = []
    moved_placements: list[ModelPlacement] = []
    model_movements: list[JsonValue] = []
    max_movement_inches = 0
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = _model_movement_inches(model)
        max_movement_inches = max(max_movement_inches, movement_inches)
        end_pose = _translated_pose(placement.pose, movement_inches=movement_inches)
        moved_placements.append(placement.with_pose(end_pose))
        model_paths.append((placement.model_instance_id, placement.pose, end_pose))
        model_movements.append(
            validate_json_value(
                {
                    "model_instance_id": placement.model_instance_id,
                    "movement_inches": movement_inches,
                    "base_size": model.base_size.to_payload(),
                    "start_pose": placement.pose.to_payload(),
                    "end_pose": end_pose.to_payload(),
                }
            )
        )
    witness = PathWitness.for_straight_line_endpoints(tuple(model_paths))
    return (
        unit_placement.with_model_placements(tuple(moved_placements)),
        witness,
        {
            "movement_inches": max_movement_inches,
            "model_movements": model_movements,
        },
    )


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
