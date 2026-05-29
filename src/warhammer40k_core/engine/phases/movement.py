from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecPayload,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.core.ruleset_descriptor import (
    MissionDeploymentZoneSource,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.aircraft import (
    AircraftMinimumMoveResult,
    AircraftMovementPolicy,
    AircraftMovementPolicyPayload,
    AircraftMovementViolation,
    AircraftReserveTransitionReason,
    HoverModeState,
    aircraft_model_ids_for_scenario,
    apply_aircraft_reserve_transition_to_battlefield,
    resolve_aircraft_reserve_transition,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    battlefield_placement_kind_from_token,
    geometry_model_for_placement,
    model_displacement_kind_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    LargeModelReservePlacementExceptionPayload,
    ReinforcementPlacement,
    ReserveKind,
    ReserveState,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkResolution,
    DisembarkSelection,
    EmbarkResolution,
    EmbarkSelection,
    EmbarkSelectionPayload,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportRestrictionOverride,
    TransportRestrictionOverridePayload,
    apply_disembark_to_battlefield,
    apply_embark_to_battlefield,
    resolve_disembark,
    resolve_embark,
    transport_movement_status_from_token,
)
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    MovementRollbackRecordPayload,
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    resolve_unit_movement_endpoint_coherency,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathConstraintViolation,
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
    model_is_within_battlefield_footprint,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup


SELECT_MOVEMENT_UNIT_DECISION_TYPE = "select_movement_unit"
SELECT_MOVEMENT_ACTION_DECISION_TYPE = "select_movement_action"
SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE = "select_desperate_escape_model"
SELECT_REINFORCEMENT_UNIT_DECISION_TYPE = "select_reinforcement_unit"
PLACE_REINFORCEMENT_UNIT_DECISION_TYPE = "place_reinforcement_unit"
SELECT_DISEMBARK_UNIT_DECISION_TYPE = "select_disembark_unit"
PLACE_DISEMBARK_UNIT_DECISION_TYPE = "place_disembark_unit"
SELECT_EMBARK_TRANSPORT_DECISION_TYPE = "select_embark_transport"
COMPLETE_REINFORCEMENTS_OPTION_ID = "complete_reinforcements"
COMPLETE_DISEMBARKS_OPTION_ID = "complete_disembarks"
DECLINE_EMBARK_OPTION_ID = "decline_embark"


class MovementPhaseStepKind(StrEnum):
    MOVE_UNITS = "move_units"
    REINFORCEMENTS = "reinforcements"


class MovementPhaseActionKind(StrEnum):
    REMAIN_STATIONARY = "remain_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"


class DesperateEscapeRequirementReason(StrEnum):
    ENEMY_MODEL_OVERFLIGHT = "enemy_model_overflight"
    BATTLE_SHOCKED = "battle_shocked"


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
_ADVANCE_REROLL_KEYWORD = "ADVANCE_REROLL"
_ADVANCED_UNIT_CLEANUP_POINT = "end_of_turn"
_FELL_BACK_UNIT_CLEANUP_POINT = "end_of_turn"
_DESPERATE_ESCAPE_ROLL_TYPE = "desperate_escape_roll"


class MovementUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class MovementPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    step: str
    reinforcements_completed: bool
    declined_disembark_unit_ids: list[str]
    declined_post_normal_move_disembark_unit_ids: list[str]
    selected_unit_ids: list[str]
    moved_unit_ids: list[str]
    active_selection: MovementUnitSelectionPayload | None


class MovementActionAvailabilityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: list[str]
    enemy_aircraft_engagement_model_ids: NotRequired[list[str]]
    aircraft_movement_policy: NotRequired[AircraftMovementPolicyPayload]


class MovementActionAvailabilityResultPayload(TypedDict):
    context: MovementActionAvailabilityContextPayload
    available_actions: list[str]
    unavailable_actions: list[str]


class AdvanceRollRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpecPayload
    reroll_permission: RerollPermissionPayload | None


class AdvanceRollResultPayload(TypedDict):
    request: AdvanceRollRequestPayload
    roll_state: DiceRollStatePayload
    value: int


class MovementDiceRecordPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: str
    advance_roll: AdvanceRollResultPayload


class AdvancedUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_dice_record: MovementDiceRecordPayload
    can_shoot: bool
    can_declare_charge: bool
    cleanup_point: str


class DesperateEscapeRequirementPayload(TypedDict):
    requirement_id: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    model_instance_id: str
    reasons: list[str]
    enemy_model_ids: list[str]


class DesperateEscapeRollPayload(TypedDict):
    requirement: DesperateEscapeRequirementPayload
    roll_state: DiceRollStatePayload
    value: int


class FellBackUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    desperate_escape_rolls: list[DesperateEscapeRollPayload]
    can_shoot: bool
    can_declare_charge: bool
    cleanup_point: str


class FallBackActionResultPayload(TypedDict):
    unit_instance_id: str
    attempted_placement: UnitPlacementPayload
    witness: PathWitnessPayload
    desperate_escape_requirements: list[DesperateEscapeRequirementPayload]
    desperate_escape_rolls: list[DesperateEscapeRollPayload]
    path_validation_results: list[PathValidationResultPayload]
    terrain_path_legality_results: list[TerrainPathLegalityResultPayload]
    coherency_result: UnitCoherencyResultPayload
    rollback_record: MovementRollbackRecordPayload | None
    movement_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class MovementActionAvailabilityContext:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: tuple[str, ...] = ()
    enemy_aircraft_engagement_model_ids: tuple[str, ...] = ()
    aircraft_movement_policy: AircraftMovementPolicy | None = None

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
        object.__setattr__(
            self,
            "enemy_aircraft_engagement_model_ids",
            _validate_identifier_tuple(
                "MovementActionAvailabilityContext enemy_aircraft_engagement_model_ids",
                self.enemy_aircraft_engagement_model_ids,
            ),
        )
        if self.aircraft_movement_policy is not None:
            if type(self.aircraft_movement_policy) is not AircraftMovementPolicy:
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy must be "
                    "AircraftMovementPolicy."
                )
            if self.aircraft_movement_policy.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy unit drift."
                )
            if (
                self.aircraft_movement_policy.ruleset_descriptor_hash
                != self.ruleset_descriptor_hash
            ):
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy descriptor drift."
                )

    @property
    def is_within_enemy_engagement_range(self) -> bool:
        return bool(self.enemy_engagement_model_ids)

    def evaluate(self) -> MovementActionAvailabilityResult:
        available_actions: tuple[MovementPhaseActionKind, ...]
        if (
            self.aircraft_movement_policy is not None
            and self.aircraft_movement_policy.uses_aircraft_rules
        ):
            available_actions = (MovementPhaseActionKind.NORMAL_MOVE,)
        elif self.is_within_enemy_engagement_range:
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
        payload: MovementActionAvailabilityContextPayload = {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "player_id": self.player_id,
            "enemy_engagement_model_ids": list(self.enemy_engagement_model_ids),
        }
        if self.enemy_aircraft_engagement_model_ids:
            payload["enemy_aircraft_engagement_model_ids"] = list(
                self.enemy_aircraft_engagement_model_ids
            )
        if self.aircraft_movement_policy is not None:
            payload["aircraft_movement_policy"] = self.aircraft_movement_policy.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: MovementActionAvailabilityContextPayload) -> Self:
        aircraft_policy_payload = payload.get("aircraft_movement_policy")
        aircraft_engagement_payload = payload.get("enemy_aircraft_engagement_model_ids")
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            player_id=payload["player_id"],
            enemy_engagement_model_ids=tuple(payload["enemy_engagement_model_ids"]),
            enemy_aircraft_engagement_model_ids=()
            if aircraft_engagement_payload is None
            else tuple(aircraft_engagement_payload),
            aircraft_movement_policy=None
            if aircraft_policy_payload is None
            else AircraftMovementPolicy.from_payload(aircraft_policy_payload),
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
class AdvanceRollRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpec
    reroll_permission: RerollPermission | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("AdvanceRollRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("AdvanceRollRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("AdvanceRollRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AdvanceRollRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvanceRollRequest unit_instance_id", self.unit_instance_id),
        )
        if type(self.spec) is not DiceRollSpec:
            raise GameLifecycleError("AdvanceRollRequest spec must be a DiceRollSpec.")
        _validate_advance_roll_spec(self.spec, unit_instance_id=self.unit_instance_id)
        if self.reroll_permission is not None:
            if type(self.reroll_permission) is not RerollPermission:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must be a RerollPermission."
                )
            if self.reroll_permission.owning_player_id != self.player_id:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission owner must match player_id."
                )
            if self.reroll_permission.eligible_roll_type != self.spec.roll_type:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must target advance_roll."
                )

    @classmethod
    def for_unit(
        cls,
        *,
        request_id: str,
        game_id: str,
        battle_round: int,
        player_id: str,
        unit_instance_id: str,
        reroll_permission: RerollPermission | None = None,
    ) -> Self:
        return cls(
            request_id=request_id,
            game_id=game_id,
            battle_round=battle_round,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            spec=DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Advance roll for {unit_instance_id}",
                roll_type="advance_roll",
                actor_id=unit_instance_id,
            ),
            reroll_permission=reroll_permission,
        )

    def to_payload(self) -> AdvanceRollRequestPayload:
        return {
            "request_id": self.request_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "spec": self.spec.to_payload(),
            "reroll_permission": (
                None if self.reroll_permission is None else self.reroll_permission.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollRequestPayload) -> Self:
        reroll_permission_payload = payload["reroll_permission"]
        return cls(
            request_id=payload["request_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            spec=DiceRollSpec.from_payload(payload["spec"]),
            reroll_permission=(
                None
                if reroll_permission_payload is None
                else RerollPermission.from_payload(reroll_permission_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollResult:
    request: AdvanceRollRequest
    roll_state: DiceRollState
    value: int

    def __post_init__(self) -> None:
        if type(self.request) is not AdvanceRollRequest:
            raise GameLifecycleError("AdvanceRollResult request must be an AdvanceRollRequest.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("AdvanceRollResult roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.request.spec:
            raise GameLifecycleError("AdvanceRollResult roll_state spec must match request.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("AdvanceRollResult value must match roll_state total.")
        if self.value < 1 or self.value > 6:
            raise GameLifecycleError("AdvanceRollResult value must be between 1 and 6.")

    @classmethod
    def from_roll_state(cls, *, request: AdvanceRollRequest, roll_state: DiceRollState) -> Self:
        return cls(request=request, roll_state=roll_state, value=roll_state.current_total)

    def to_payload(self) -> AdvanceRollResultPayload:
        return {
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollResultPayload) -> Self:
        return cls(
            request=AdvanceRollRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class MovementDiceRecord:
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: MovementPhaseActionKind
    advance_roll: AdvanceRollResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementDiceRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementDiceRecord battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementDiceRecord unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            movement_phase_action_kind_from_token(self.movement_phase_action),
        )
        if self.movement_phase_action is not MovementPhaseActionKind.ADVANCE:
            raise GameLifecycleError("MovementDiceRecord currently supports only Advance dice.")
        if type(self.advance_roll) is not AdvanceRollResult:
            raise GameLifecycleError("MovementDiceRecord advance_roll must be AdvanceRollResult.")
        if self.advance_roll.request.player_id != self.player_id:
            raise GameLifecycleError("MovementDiceRecord advance_roll player_id drift.")
        if self.advance_roll.request.battle_round != self.battle_round:
            raise GameLifecycleError("MovementDiceRecord advance_roll battle_round drift.")
        if self.advance_roll.request.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("MovementDiceRecord advance_roll unit_instance_id drift.")

    def to_payload(self) -> MovementDiceRecordPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action.value,
            "advance_roll": self.advance_roll.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementDiceRecordPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=movement_phase_action_kind_from_token(
                payload["movement_phase_action"]
            ),
            advance_roll=AdvanceRollResult.from_payload(payload["advance_roll"]),
        )


@dataclass(frozen=True, slots=True)
class AdvancedUnitState:
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_dice_record: MovementDiceRecord
    can_shoot: bool = False
    can_declare_charge: bool = False
    cleanup_point: str = _ADVANCED_UNIT_CLEANUP_POINT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AdvancedUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("AdvancedUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvancedUnitState unit_instance_id", self.unit_instance_id),
        )
        if type(self.movement_dice_record) is not MovementDiceRecord:
            raise GameLifecycleError(
                "AdvancedUnitState movement_dice_record must be MovementDiceRecord."
            )
        if self.movement_dice_record.player_id != self.player_id:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record player_id drift.")
        if self.movement_dice_record.battle_round != self.battle_round:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record battle_round drift.")
        if self.movement_dice_record.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record unit drift.")
        object.__setattr__(
            self,
            "can_shoot",
            _validate_bool("AdvancedUnitState can_shoot", self.can_shoot),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("AdvancedUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "cleanup_point",
            _validate_identifier("AdvancedUnitState cleanup_point", self.cleanup_point),
        )
        if self.cleanup_point != _ADVANCED_UNIT_CLEANUP_POINT:
            raise GameLifecycleError("AdvancedUnitState cleanup_point must be end_of_turn.")

    def to_payload(self) -> AdvancedUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "movement_dice_record": self.movement_dice_record.to_payload(),
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "cleanup_point": self.cleanup_point,
        }

    @classmethod
    def from_payload(cls, payload: AdvancedUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            movement_dice_record=MovementDiceRecord.from_payload(payload["movement_dice_record"]),
            can_shoot=payload["can_shoot"],
            can_declare_charge=payload["can_declare_charge"],
            cleanup_point=payload["cleanup_point"],
        )


@dataclass(frozen=True, slots=True)
class DesperateEscapeRequirement:
    requirement_id: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    model_instance_id: str
    reasons: tuple[DesperateEscapeRequirementReason, ...]
    enemy_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _validate_identifier(
                "DesperateEscapeRequirement requirement_id",
                self.requirement_id,
            ),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DesperateEscapeRequirement player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DesperateEscapeRequirement battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DesperateEscapeRequirement unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "DesperateEscapeRequirement model_instance_id",
                self.model_instance_id,
            ),
        )
        if not self.model_instance_id.startswith(f"{self.unit_instance_id}:"):
            raise GameLifecycleError(
                "DesperateEscapeRequirement model_instance_id must belong to unit_instance_id."
            )
        object.__setattr__(
            self,
            "reasons",
            _validate_desperate_escape_reason_tuple(
                "DesperateEscapeRequirement reasons",
                self.reasons,
            ),
        )
        object.__setattr__(
            self,
            "enemy_model_ids",
            _validate_identifier_tuple(
                "DesperateEscapeRequirement enemy_model_ids",
                self.enemy_model_ids,
            ),
        )
        if (
            DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT in self.reasons
            and not self.enemy_model_ids
        ):
            raise GameLifecycleError(
                "DesperateEscapeRequirement enemy overflight requires enemy_model_ids."
            )

    def roll_spec(self) -> DiceRollSpec:
        return DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Desperate Escape roll for {self.model_instance_id}",
            roll_type=_DESPERATE_ESCAPE_ROLL_TYPE,
            actor_id=self.model_instance_id,
        )

    def to_payload(self) -> DesperateEscapeRequirementPayload:
        return {
            "requirement_id": self.requirement_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "reasons": [reason.value for reason in self.reasons],
            "enemy_model_ids": list(self.enemy_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: DesperateEscapeRequirementPayload) -> Self:
        return cls(
            requirement_id=payload["requirement_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            reasons=tuple(
                desperate_escape_requirement_reason_from_token(reason)
                for reason in payload["reasons"]
            ),
            enemy_model_ids=tuple(payload["enemy_model_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DesperateEscapeRoll:
    requirement: DesperateEscapeRequirement
    roll_state: DiceRollState
    value: int

    def __post_init__(self) -> None:
        if type(self.requirement) is not DesperateEscapeRequirement:
            raise GameLifecycleError(
                "DesperateEscapeRoll requirement must be a DesperateEscapeRequirement."
            )
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("DesperateEscapeRoll roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.requirement.roll_spec():
            raise GameLifecycleError("DesperateEscapeRoll roll_state spec must match requirement.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("DesperateEscapeRoll value must match roll_state total.")
        if self.value < 1 or self.value > 6:
            raise GameLifecycleError("DesperateEscapeRoll value must be between 1 and 6.")

    @classmethod
    def from_roll_state(
        cls,
        *,
        requirement: DesperateEscapeRequirement,
        roll_state: DiceRollState,
    ) -> Self:
        return cls(
            requirement=requirement,
            roll_state=roll_state,
            value=roll_state.current_total,
        )

    @property
    def is_failed(self) -> bool:
        return self.value <= 2

    def to_payload(self) -> DesperateEscapeRollPayload:
        return {
            "requirement": self.requirement.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: DesperateEscapeRollPayload) -> Self:
        return cls(
            requirement=DesperateEscapeRequirement.from_payload(payload["requirement"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class FellBackUnitState:
    player_id: str
    battle_round: int
    unit_instance_id: str
    desperate_escape_rolls: tuple[DesperateEscapeRoll, ...] = ()
    can_shoot: bool = False
    can_declare_charge: bool = False
    cleanup_point: str = _FELL_BACK_UNIT_CLEANUP_POINT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FellBackUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FellBackUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FellBackUnitState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "desperate_escape_rolls",
            _validate_desperate_escape_roll_tuple(
                "FellBackUnitState desperate_escape_rolls",
                self.desperate_escape_rolls,
            ),
        )
        for roll in self.desperate_escape_rolls:
            requirement = roll.requirement
            if requirement.player_id != self.player_id:
                raise GameLifecycleError("FellBackUnitState roll player_id drift.")
            if requirement.battle_round != self.battle_round:
                raise GameLifecycleError("FellBackUnitState roll battle_round drift.")
            if requirement.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError("FellBackUnitState roll unit drift.")
        object.__setattr__(
            self,
            "can_shoot",
            _validate_bool("FellBackUnitState can_shoot", self.can_shoot),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("FellBackUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "cleanup_point",
            _validate_identifier("FellBackUnitState cleanup_point", self.cleanup_point),
        )
        if self.cleanup_point != _FELL_BACK_UNIT_CLEANUP_POINT:
            raise GameLifecycleError("FellBackUnitState cleanup_point must be end_of_turn.")

    def to_payload(self) -> FellBackUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "desperate_escape_rolls": [roll.to_payload() for roll in self.desperate_escape_rolls],
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "cleanup_point": self.cleanup_point,
        }

    @classmethod
    def from_payload(cls, payload: FellBackUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            desperate_escape_rolls=tuple(
                DesperateEscapeRoll.from_payload(roll) for roll in payload["desperate_escape_rolls"]
            ),
            can_shoot=payload["can_shoot"],
            can_declare_charge=payload["can_declare_charge"],
            cleanup_point=payload["cleanup_point"],
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
    step: MovementPhaseStepKind = MovementPhaseStepKind.MOVE_UNITS
    reinforcements_completed: bool = False
    declined_disembark_unit_ids: tuple[str, ...] = ()
    declined_post_normal_move_disembark_unit_ids: tuple[str, ...] = ()
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
        object.__setattr__(self, "step", movement_phase_step_kind_from_token(self.step))
        object.__setattr__(
            self,
            "reinforcements_completed",
            _validate_bool(
                "MovementPhaseState reinforcements_completed",
                self.reinforcements_completed,
            ),
        )
        object.__setattr__(
            self,
            "declined_disembark_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState declined_disembark_unit_ids",
                self.declined_disembark_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "declined_post_normal_move_disembark_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState declined_post_normal_move_disembark_unit_ids",
                self.declined_post_normal_move_disembark_unit_ids,
            ),
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
        if self.step is MovementPhaseStepKind.REINFORCEMENTS and self.active_selection is not None:
            raise GameLifecycleError("Reinforcements step must not have active_selection.")
        if self.reinforcements_completed and self.step is not MovementPhaseStepKind.REINFORCEMENTS:
            raise GameLifecycleError(
                "MovementPhaseState reinforcements_completed requires Reinforcements step."
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

    def legal_unit_ids(
        self,
        scenario: BattlefieldScenario,
        *,
        accounted_unplaced_model_ids: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            return ()
        return _remaining_move_units_unit_ids(
            scenario=scenario,
            active_player_id=self.active_player_id,
            selected_unit_ids=self.selected_unit_ids,
            accounted_unplaced_model_ids=accounted_unplaced_model_ids,
        )

    def with_unit_selection(self, selection: MovementUnitSelection) -> Self:
        if type(selection) is not MovementUnitSelection:
            raise GameLifecycleError("Movement selection must be a MovementUnitSelection.")
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Movement selection requires Move Units step.")
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
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            moved_unit_ids=self.moved_unit_ids,
            active_selection=selection,
        )

    def with_disembark_declined(self, unit_instance_ids: tuple[str, ...]) -> Self:
        declined_ids = _validate_identifier_tuple("unit_instance_ids", unit_instance_ids)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Disembark decline requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Disembark decline requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=tuple(
                sorted((*self.declined_disembark_unit_ids, *declined_ids))
            ),
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            active_selection=None,
        )

    def with_post_normal_move_disembark_declined(
        self,
        unit_instance_ids: tuple[str, ...],
    ) -> Self:
        declined_ids = _validate_identifier_tuple("unit_instance_ids", unit_instance_ids)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Post-move Disembark decline requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Post-move Disembark decline requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=tuple(
                sorted((*self.declined_post_normal_move_disembark_unit_ids, *declined_ids))
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            active_selection=None,
        )

    def with_post_normal_move_disembark_counted_as_moved(
        self,
        unit_instance_id: str,
    ) -> Self:
        moved_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError(
                "Post-move Disembark movement record requires Move Units step."
            )
        if self.active_selection is not None:
            raise GameLifecycleError(
                "Post-move Disembark movement record requires no active_selection."
            )
        if moved_unit_id in self.selected_unit_ids or moved_unit_id in self.moved_unit_ids:
            raise GameLifecycleError("Post-move Disembark unit already has movement state.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=(*self.selected_unit_ids, moved_unit_id),
            moved_unit_ids=(*self.moved_unit_ids, moved_unit_id),
            active_selection=None,
        )

    def with_activation_complete(self, unit_instance_id: str) -> Self:
        completed_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Movement activation completion requires Move Units step.")
        if self.active_selection is None:
            raise GameLifecycleError("Movement activation completion requires active_selection.")
        if completed_unit_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Movement activation completion must match active_selection.")
        if completed_unit_id in self.moved_unit_ids:
            raise GameLifecycleError("Movement unit has already completed movement.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=(*self.moved_unit_ids, completed_unit_id),
            active_selection=None,
        )

    def with_step(self, step: MovementPhaseStepKind) -> Self:
        requested_step = movement_phase_step_kind_from_token(step)
        if requested_step is self.step:
            return self
        if self.active_selection is not None:
            raise GameLifecycleError("MovementPhaseState step change requires no active_selection.")
        if requested_step is MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("MovementPhaseState cannot return to Move Units.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=requested_step,
            reinforcements_completed=False,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            active_selection=None,
        )

    def with_reinforcement_arrival(self, unit_instance_id: str) -> Self:
        arrived_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.REINFORCEMENTS:
            raise GameLifecycleError("Reinforcement arrival requires Reinforcements step.")
        if self.reinforcements_completed:
            raise GameLifecycleError("Reinforcement arrival requires incomplete Reinforcements.")
        selected = self.selected_unit_ids
        moved = self.moved_unit_ids
        if arrived_unit_id not in selected:
            selected = (*selected, arrived_unit_id)
        if arrived_unit_id not in moved:
            moved = (*moved, arrived_unit_id)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=selected,
            moved_unit_ids=moved,
            active_selection=None,
        )

    def with_reinforcements_completed(self) -> Self:
        if self.step is not MovementPhaseStepKind.REINFORCEMENTS:
            raise GameLifecycleError("Completing Reinforcements requires Reinforcements step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Completing Reinforcements requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=True,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            active_selection=None,
        )

    def to_payload(self) -> MovementPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "step": self.step.value,
            "reinforcements_completed": self.reinforcements_completed,
            "declined_disembark_unit_ids": list(self.declined_disembark_unit_ids),
            "declined_post_normal_move_disembark_unit_ids": list(
                self.declined_post_normal_move_disembark_unit_ids
            ),
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
            step=movement_phase_step_kind_from_token(payload["step"]),
            reinforcements_completed=payload["reinforcements_completed"],
            declined_disembark_unit_ids=tuple(payload["declined_disembark_unit_ids"]),
            declined_post_normal_move_disembark_unit_ids=tuple(
                payload["declined_post_normal_move_disembark_unit_ids"]
            ),
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
        expected_aircraft_policy = self.movement_payload.get("aircraft_movement_policy")
        if selected_payload.get("aircraft_movement_policy") != expected_aircraft_policy:
            return "normal_move_aircraft_policy_drift"
        expected_model_movements = self.movement_payload["model_movements"]
        expected_aircraft_minimum = _aircraft_minimum_move_payloads(expected_model_movements)
        if expected_aircraft_minimum:
            selected_aircraft_minimum = _aircraft_minimum_move_payloads(
                selected_payload.get("model_movements")
            )
            if selected_aircraft_minimum != expected_aircraft_minimum:
                return "normal_move_aircraft_minimum_move_witness_drift"
        if selected_payload.get("model_movements") != expected_model_movements:
            return "normal_move_model_movement_witness_drift"
        return None


def _aircraft_minimum_move_payloads(
    model_movements: object,
) -> dict[str, JsonValue] | None:
    validated_model_movements = validate_json_value(model_movements)
    if not isinstance(validated_model_movements, list):
        return None
    payloads: dict[str, JsonValue] = {}
    for value in validated_model_movements:
        if not isinstance(value, dict):
            return None
        model_instance_id = value.get("model_instance_id")
        if type(model_instance_id) is not str:
            return None
        minimum_move_payload = value.get("aircraft_minimum_move_result")
        if minimum_move_payload is not None:
            payloads[model_instance_id] = minimum_move_payload
    return payloads


@dataclass(frozen=True, slots=True)
class AdvanceMoveResolution:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    advance_roll: AdvanceRollResult
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvanceMoveResolution unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "AdvanceMoveResolution attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "AdvanceMoveResolution attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("AdvanceMoveResolution witness must be a PathWitness.")
        if type(self.advance_roll) is not AdvanceRollResult:
            raise GameLifecycleError(
                "AdvanceMoveResolution advance_roll must be an AdvanceRollResult."
            )
        if self.advance_roll.request.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("AdvanceMoveResolution advance_roll unit drift.")
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "AdvanceMoveResolution path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "AdvanceMoveResolution terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "AdvanceMoveResolution coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "AdvanceMoveResolution rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "AdvanceMoveResolution movement_payload",
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
            raise GameLifecycleError("Invalid Advance cannot emit displacement records.")
        return _movement_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        )


@dataclass(frozen=True, slots=True)
class FallBackActionResult:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    desperate_escape_requirements: tuple[DesperateEscapeRequirement, ...]
    desperate_escape_rolls: tuple[DesperateEscapeRoll, ...]
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FallBackActionResult unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "FallBackActionResult attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "FallBackActionResult attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("FallBackActionResult witness must be a PathWitness.")
        object.__setattr__(
            self,
            "desperate_escape_requirements",
            _validate_desperate_escape_requirement_tuple(
                "FallBackActionResult desperate_escape_requirements",
                self.desperate_escape_requirements,
            ),
        )
        for requirement in self.desperate_escape_requirements:
            if requirement.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError("FallBackActionResult requirement unit drift.")
        object.__setattr__(
            self,
            "desperate_escape_rolls",
            _validate_desperate_escape_roll_tuple(
                "FallBackActionResult desperate_escape_rolls",
                self.desperate_escape_rolls,
            ),
        )
        requirement_by_id = {
            requirement.requirement_id: requirement
            for requirement in self.desperate_escape_requirements
        }
        for roll in self.desperate_escape_rolls:
            expected_requirement = requirement_by_id.get(roll.requirement.requirement_id)
            if expected_requirement is None:
                raise GameLifecycleError(
                    "FallBackActionResult roll must match a Desperate Escape requirement."
                )
            if roll.requirement != expected_requirement:
                raise GameLifecycleError("FallBackActionResult roll requirement drift.")
        if len(self.desperate_escape_rolls) not in {0, len(self.desperate_escape_requirements)}:
            raise GameLifecycleError(
                "FallBackActionResult must roll either no Desperate Escape tests or every "
                "requirement."
            )
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "FallBackActionResult path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "FallBackActionResult terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "FallBackActionResult coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "FallBackActionResult rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "FallBackActionResult movement_payload",
                self.movement_payload,
            ),
        )

    @classmethod
    def unresolved(
        cls,
        *,
        unit_instance_id: str,
        attempted_placement: UnitPlacement,
        witness: PathWitness,
        desperate_escape_requirements: tuple[DesperateEscapeRequirement, ...],
        path_validation_results: tuple[PathValidationResult, ...],
        terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...],
        coherency_result: UnitCoherencyResult,
        rollback_record: MovementRollbackRecord | None,
        movement_payload: dict[str, JsonValue],
    ) -> Self:
        return cls(
            unit_instance_id=unit_instance_id,
            attempted_placement=attempted_placement,
            witness=witness,
            desperate_escape_requirements=desperate_escape_requirements,
            desperate_escape_rolls=(),
            path_validation_results=path_validation_results,
            terrain_path_legality_results=terrain_path_legality_results,
            coherency_result=coherency_result,
            rollback_record=rollback_record,
            movement_payload=movement_payload,
        )

    @classmethod
    def with_desperate_escape_rolls(
        cls,
        *,
        resolution: FallBackActionResult,
        desperate_escape_rolls: tuple[DesperateEscapeRoll, ...],
    ) -> Self:
        if type(resolution) is not FallBackActionResult:
            raise GameLifecycleError("Fall Back resolution must be a FallBackActionResult.")
        return cls(
            unit_instance_id=resolution.unit_instance_id,
            attempted_placement=resolution.attempted_placement,
            witness=resolution.witness,
            desperate_escape_requirements=resolution.desperate_escape_requirements,
            desperate_escape_rolls=desperate_escape_rolls,
            path_validation_results=resolution.path_validation_results,
            terrain_path_legality_results=resolution.terrain_path_legality_results,
            coherency_result=resolution.coherency_result,
            rollback_record=resolution.rollback_record,
            movement_payload={
                **resolution.movement_payload,
                "desperate_escape_rolls": validate_json_value(
                    [roll.to_payload() for roll in desperate_escape_rolls]
                ),
            },
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    @property
    def failed_desperate_escape_rolls(self) -> tuple[DesperateEscapeRoll, ...]:
        return tuple(roll for roll in self.desperate_escape_rolls if roll.is_failed)

    def transition_batch(
        self,
        *,
        before: UnitPlacement,
        destroyed_model_ids: tuple[str, ...],
    ) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Fall Back cannot emit transition records.")
        if self.desperate_escape_requirements and not self.desperate_escape_rolls:
            raise GameLifecycleError(
                "Fall Back cannot emit transition records before Desperate Escape rolls are "
                "resolved."
            )
        destroyed_ids = _validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids)
        failed_model_ids = tuple(
            roll.requirement.model_instance_id for roll in self.failed_desperate_escape_rolls
        )
        if len(destroyed_ids) != len(failed_model_ids):
            raise GameLifecycleError(
                "Fall Back must select one model for every failed Desperate Escape roll."
            )
        eligible_model_ids = {
            placement.model_instance_id for placement in self.attempted_placement.model_placements
        }
        for destroyed_id in destroyed_ids:
            if destroyed_id not in eligible_model_ids:
                raise GameLifecycleError(
                    "Fall Back destroyed_model_ids must be eligible falling-back models."
                )
        return _fall_back_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
            destroyed_model_ids=destroyed_ids,
        )

    def surviving_attempted_placement(
        self,
        *,
        destroyed_model_ids: tuple[str, ...],
    ) -> UnitPlacement | None:
        destroyed_ids = set(_validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids))
        surviving_placements = tuple(
            placement
            for placement in self.attempted_placement.model_placements
            if placement.model_instance_id not in destroyed_ids
        )
        if not surviving_placements:
            return None
        return self.attempted_placement.with_model_placements(surviving_placements)

    def selected_payload_drift_code(self, payload: dict[str, JsonValue]) -> str | None:
        selected_payload = _validate_json_object("Fall Back selected payload", payload)
        if selected_payload.get("witness") != self.witness.to_payload():
            return "fall_back_witness_drift"
        expected_model_movements = self.movement_payload["model_movements"]
        if selected_payload.get("model_movements") != expected_model_movements:
            return "fall_back_model_movement_witness_drift"
        expected_aircraft_policy = self.movement_payload.get("aircraft_movement_policy")
        if selected_payload.get("aircraft_movement_policy") != expected_aircraft_policy:
            return "fall_back_aircraft_policy_drift"
        return None

    def to_payload(self) -> FallBackActionResultPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "attempted_placement": self.attempted_placement.to_payload(),
            "witness": self.witness.to_payload(),
            "desperate_escape_requirements": [
                requirement.to_payload() for requirement in self.desperate_escape_requirements
            ],
            "desperate_escape_rolls": [roll.to_payload() for roll in self.desperate_escape_rolls],
            "path_validation_results": [
                result.to_payload() for result in self.path_validation_results
            ],
            "terrain_path_legality_results": [
                result.to_payload() for result in self.terrain_path_legality_results
            ],
            "coherency_result": self.coherency_result.to_payload(),
            "rollback_record": (
                None if self.rollback_record is None else self.rollback_record.to_payload()
            ),
            "movement_payload": self.movement_payload,
        }

    @classmethod
    def from_payload(cls, payload: FallBackActionResultPayload) -> Self:
        rollback_payload = payload["rollback_record"]
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            witness=PathWitness.from_payload(payload["witness"]),
            desperate_escape_requirements=tuple(
                DesperateEscapeRequirement.from_payload(requirement)
                for requirement in payload["desperate_escape_requirements"]
            ),
            desperate_escape_rolls=tuple(
                DesperateEscapeRoll.from_payload(roll) for roll in payload["desperate_escape_rolls"]
            ),
            path_validation_results=tuple(
                PathValidationResult.from_payload(result)
                for result in payload["path_validation_results"]
            ),
            terrain_path_legality_results=tuple(
                TerrainPathLegalityResult.from_payload(result)
                for result in payload["terrain_path_legality_results"]
            ),
            coherency_result=UnitCoherencyResult.from_payload(payload["coherency_result"]),
            rollback_record=(
                None
                if rollback_payload is None
                else MovementRollbackRecord.from_payload(rollback_payload)
            ),
            movement_payload=payload["movement_payload"],
        )


@dataclass(frozen=True, slots=True)
class _ResolvedUnitMove:
    attempted_placement: UnitPlacement
    witness: PathWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]


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
        _ensure_transport_cargo_phase_states(state)
        if movement_state.step is MovementPhaseStepKind.REINFORCEMENTS:
            assert_move_units_step_complete_for_reinforcements(
                state=state,
                movement_state=movement_state,
            )
            return _begin_reinforcements_step(state=state, decisions=decisions)
        active_selection = movement_state.active_selection
        if active_selection is not None:
            return _request_movement_action(
                state=state,
                decisions=decisions,
                active_selection=active_selection,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )

        if state.transport_cargo_states:
            disembark_status = _request_pre_move_disembark_if_available(
                state=state,
                decisions=decisions,
                movement_state=movement_state,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
            if disembark_status is not None:
                return disembark_status

        scenario = _battlefield_scenario(state)
        legal_unit_ids = movement_state.legal_unit_ids(
            scenario,
            accounted_unplaced_model_ids=state.unavailable_model_ids(),
        )
        if not legal_unit_ids:
            state.movement_phase_state = movement_state.with_step(
                MovementPhaseStepKind.REINFORCEMENTS
            )
            decisions.event_log.append(
                "movement_phase_step_entered",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                    "phase": BattlePhase.MOVEMENT.value,
                    "step": MovementPhaseStepKind.REINFORCEMENTS.value,
                    "phase_body_status": "reinforcements_step_entered",
                },
            )
            return _begin_reinforcements_step(state=state, decisions=decisions)

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
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            return _apply_advance_roll_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE:
            return _apply_desperate_escape_model_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE:
            return _apply_movement_action_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE:
            return _apply_reinforcement_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == PLACE_REINFORCEMENT_UNIT_DECISION_TYPE:
            return _apply_reinforcement_placement_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE:
            return _apply_disembark_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == PLACE_DISEMBARK_UNIT_DECISION_TYPE:
            return _apply_disembark_placement_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE:
            return _apply_embark_transport_selection_decision(
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
        if unit_instance_id not in movement_state.legal_unit_ids(
            scenario,
            accounted_unplaced_model_ids=state.unavailable_model_ids(),
        ):
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


def _begin_reinforcements_step(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.REINFORCEMENTS:
        raise GameLifecycleError("Reinforcements step requires movement phase state.")
    unarrived_reserve_states = state.unarrived_reserve_states_for_player(active_player_id)
    if _overdue_required_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Required Reinforcements arrival was missed.")
    eligible_reserve_states = _eligible_reinforcement_reserve_states(state=state)
    required_reserve_states = _required_reinforcement_reserve_states(state=state)
    if movement_state.reinforcements_completed or not eligible_reserve_states:
        return _complete_reinforcements_step(
            state=state,
            decisions=decisions,
            unarrived_reserve_count=len(unarrived_reserve_states),
        )

    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
        actor_id=active_player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "active_player_id": active_player_id,
        },
        options=_reinforcement_unit_options(
            eligible_reserve_states,
            completion_allowed=not required_reserve_states,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "phase_body_status": "reinforcements_waiting_for_arrival_choice",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unarrived_reserve_count": len(unarrived_reserve_states),
            "eligible_reserve_count": len(eligible_reserve_states),
            "required_reserve_count": len(required_reserve_states),
        },
    )


def _complete_reinforcements_step(
    *,
    state: GameState,
    decisions: DecisionController,
    unarrived_reserve_count: int,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.REINFORCEMENTS:
        raise GameLifecycleError("Completing Reinforcements requires Reinforcements step.")
    if not movement_state.reinforcements_completed:
        state.movement_phase_state = movement_state.with_reinforcements_completed()
    decisions.event_log.append(
        "reinforcements_step_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "unarrived_reserve_count": unarrived_reserve_count,
            "phase_body_status": "reinforcements_complete",
        },
    )
    return LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "phase_body_status": "reinforcements_complete",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unarrived_reserve_count": unarrived_reserve_count,
        },
    )


def _reinforcement_unit_options(
    reserve_states: tuple[ReserveState, ...],
    *,
    completion_allowed: bool = True,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    if completion_allowed:
        options.append(
            DecisionOption(
                option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
                label="Complete Reinforcements",
                payload={
                    "reinforcement_decision": COMPLETE_REINFORCEMENTS_OPTION_ID,
                },
            )
        )
    options.extend(
        DecisionOption(
            option_id=reserve_state.unit_instance_id,
            label=f"Arrive {reserve_state.unit_instance_id}",
            payload={
                "reinforcement_decision": "select_arrival",
                "unit_instance_id": reserve_state.unit_instance_id,
                "reserve_kind": reserve_state.reserve_kind.value,
                "reserve_origin": reserve_state.reserve_origin.value,
            },
        )
        for reserve_state in reserve_states
    )
    return tuple(options)


def _eligible_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.arrival_is_eligible_at(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
        )
    )


def _required_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.arrival_is_required_at(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
        )
    )


def _overdue_required_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.has_required_arrival
        and reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
        and reserve_state.required_arrival_battle_round is not None
        and reserve_state.required_arrival_battle_round < state.battle_round
    )


def _apply_reinforcement_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Reinforcement selection actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.REINFORCEMENTS:
        raise GameLifecycleError("Reinforcement selection requires Reinforcements step.")
    if movement_state.reinforcements_completed:
        raise GameLifecycleError("Reinforcement selection requires incomplete Reinforcements.")

    payload = _decision_payload_object(result.payload)
    reinforcement_decision = _payload_string(payload, key="reinforcement_decision")
    if reinforcement_decision == COMPLETE_REINFORCEMENTS_OPTION_ID:
        if _required_reinforcement_reserve_states(state=state):
            raise GameLifecycleError("Required Reinforcements arrival cannot be skipped.")
        state.movement_phase_state = movement_state.with_reinforcements_completed()
        decisions.event_log.append(
            "reinforcements_completion_selected",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "step": MovementPhaseStepKind.REINFORCEMENTS.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "reinforcements_completion_selected",
            },
        )
        return None
    if reinforcement_decision != "select_arrival":
        raise GameLifecycleError("Unsupported Reinforcements selection payload.")

    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Reinforcement selection requires ReserveState.")
    if reserve_state not in _eligible_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Reinforcement selection is not currently legal.")

    decisions.event_log.append(
        "reinforcement_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "unit_instance_id": unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_unit_selected",
        },
    )
    return _request_reinforcement_placement(
        state=state,
        decisions=decisions,
        reserve_state=reserve_state,
        ruleset_descriptor=ruleset_descriptor,
    )


def _request_reinforcement_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    reserve_state: ReserveState,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    scenario = _battlefield_scenario(state)
    unit = scenario.army_by_id(reserve_state.unit_instance_id.split(":", maxsplit=1)[0]).unit_by_id(
        reserve_state.unit_instance_id
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
        actor_id=active_player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "active_player_id": active_player_id,
            "unit_instance_id": reserve_state.unit_instance_id,
        },
        options=_reinforcement_placement_options(
            reserve_state=reserve_state,
            unit=unit,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "phase_body_status": "reinforcement_placement_required",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unit_instance_id": reserve_state.unit_instance_id,
            "legal_placement_count": len(request.options),
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
    )


def _reinforcement_placement_options(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
) -> tuple[DecisionOption, ...]:
    placement_kinds = _reserve_placement_kinds_for_unit(reserve_state=reserve_state, unit=unit)
    return tuple(
        DecisionOption(
            option_id=placement_kind.value,
            label=placement_kind.value.replace("_", " ").title(),
            payload=validate_json_value(
                _reinforcement_placement_payload(
                    reserve_state=reserve_state,
                    unit=unit,
                    placement_kind=placement_kind,
                )
            ),
        )
        for placement_kind in placement_kinds
    )


def _reserve_placement_kinds_for_unit(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
) -> tuple[BattlefieldPlacementKind, ...]:
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        kinds = [BattlefieldPlacementKind.STRATEGIC_RESERVES]
        if _unit_has_deep_strike_keyword(unit):
            kinds.append(BattlefieldPlacementKind.DEEP_STRIKE)
        return tuple(kinds)
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return (BattlefieldPlacementKind.DEEP_STRIKE,)
    return (BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,)


def _reinforcement_placement_payload(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
) -> dict[str, JsonValue]:
    attempted_placement, large_model_exceptions = _deterministic_reinforcement_placement(
        reserve_state=reserve_state,
        unit=unit,
        placement_kind=placement_kind,
    )
    return {
        "reinforcement_decision": "place_reinforcement_unit",
        "unit_instance_id": reserve_state.unit_instance_id,
        "placement_kind": placement_kind.value,
        "attempted_placement": validate_json_value(attempted_placement.to_payload()),
        "large_model_exceptions": [
            validate_json_value(exception.to_payload()) for exception in large_model_exceptions
        ],
    }


def _deterministic_reinforcement_placement(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
) -> tuple[UnitPlacement, tuple[LargeModelReservePlacementException, ...]]:
    model_placements: list[ModelPlacement] = []
    large_model_exceptions: list[LargeModelReservePlacementException] = []
    cursor_x = 12.0
    for model in unit.own_models:
        part = model.geometry.primary_part()
        radius_x = part.radius_x_inches
        radius_y = part.radius_y_inches
        y = radius_y + 0.25
        if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES and radius_y * 2.0 > 6.0:
            y = radius_y
            large_model_exceptions.append(
                LargeModelReservePlacementException(
                    model_instance_id=model.model_instance_id,
                    battlefield_edge=BattlefieldEdge.SOUTH,
                )
            )
        model_placements.append(
            ModelPlacement(
                army_id=reserve_state.unit_instance_id.split(":", maxsplit=1)[0],
                player_id=reserve_state.player_id,
                unit_instance_id=reserve_state.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(
                    x=cursor_x + radius_x,
                    y=y,
                    z=0.0,
                    facing_degrees=0.0,
                ),
            )
        )
        cursor_x += (radius_x * 2.0) + 0.75
    return (
        UnitPlacement(
            army_id=reserve_state.unit_instance_id.split(":", maxsplit=1)[0],
            player_id=reserve_state.player_id,
            unit_instance_id=reserve_state.unit_instance_id,
            model_placements=tuple(model_placements),
        ),
        tuple(large_model_exceptions),
    )


def _apply_reinforcement_placement_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Reinforcement placement actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.REINFORCEMENTS:
        raise GameLifecycleError("Reinforcement placement requires Reinforcements step.")
    if movement_state.reinforcements_completed:
        raise GameLifecycleError("Reinforcement placement requires incomplete Reinforcements.")

    payload = _decision_payload_object(result.payload)
    if _payload_string(payload, key="reinforcement_decision") != "place_reinforcement_unit":
        raise GameLifecycleError("Unsupported Reinforcements placement payload.")
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Reinforcement placement requires ReserveState.")
    if reserve_state not in _eligible_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Reinforcement placement is not currently legal.")
    placement_kind = battlefield_placement_kind_from_token(
        _payload_string(payload, key="placement_kind")
    )
    attempted_placement = _payload_unit_placement(payload, key="attempted_placement")
    large_model_exceptions = _payload_large_model_exceptions(
        payload,
        key="large_model_exceptions",
    )
    mission_setup = _mission_setup_for_live_reinforcements(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
    )
    placement = resolve_reserve_arrival(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=state.battle_round,
        placement_kind=placement_kind,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
        enemy_deployment_zones=mission_setup.enemy_deployment_zones_for_player(
            reserve_state.player_id,
        ),
        large_model_exceptions=large_model_exceptions,
    )
    if not placement.is_valid:
        invalid_payload = {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "unit_instance_id": unit_instance_id,
            "placement_kind": placement_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_placement_invalid",
            "violations": [violation.to_payload() for violation in placement.violations],
            "coherency_result": placement.coherency_result.to_payload(),
        }
        decisions.event_log.append(
            "reinforcement_placement_invalid",
            validate_json_value(invalid_payload),
        )
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Reinforcement placement is invalid.",
            payload=validate_json_value(invalid_payload),
        )
    _apply_valid_reinforcement_placement(
        state=state,
        decisions=decisions,
        placement=placement,
        result=result,
    )
    return None


def _apply_valid_reinforcement_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    placement: ReinforcementPlacement,
    result: DecisionResult,
) -> None:
    if type(placement) is not ReinforcementPlacement:
        raise GameLifecycleError("Reinforcement placement mutation requires placement result.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Reinforcement placement requires battlefield_state.")
    state.battlefield_state = apply_reinforcement_placement_to_battlefield(
        battlefield_state=battlefield_state,
        placement=placement,
    )
    arrived_state = placement.arrived_reserve_state()
    state.replace_reserve_state(arrived_state)
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Reinforcement placement requires movement phase state.")
    state.movement_phase_state = movement_state.with_reinforcement_arrival(
        arrived_state.unit_instance_id
    )
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": arrived_state.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.REINFORCEMENTS.value,
            "unit_instance_id": arrived_state.unit_instance_id,
            "placement_kind": placement.candidate.placement_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_unit_arrived",
            "transition_batch": validate_json_value(placement.transition_batch.to_payload())
            if placement.transition_batch is not None
            else None,
            "large_model_exception_used": placement.large_model_exception_used,
            "post_arrival_restrictions": [
                restriction.value for restriction in placement.post_arrival_restrictions
            ],
        },
    )


def _request_pre_move_disembark_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    movement_state: MovementPhaseState,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    entries = _pre_move_disembark_entries(
        state=state,
        movement_state=movement_state,
        ruleset_descriptor=ruleset_descriptor,
    )
    if not entries:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_DISEMBARK_UNIT_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": _active_player_id(state),
            "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
        },
        options=_disembark_unit_selection_options(entries),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "disembark_unit_selection_required",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "eligible_disembark_unit_count": len(entries),
        },
    )


def _request_post_normal_move_disembark_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    movement_state: MovementPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    transport_unit_instance_id: str,
) -> LifecycleStatus | None:
    entries = _post_normal_move_disembark_entries(
        state=state,
        movement_state=movement_state,
        ruleset_descriptor=ruleset_descriptor,
        transport_unit_instance_id=transport_unit_instance_id,
    )
    if not entries:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_DISEMBARK_UNIT_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": _active_player_id(state),
            "transport_unit_instance_id": transport_unit_instance_id,
            "transport_movement_status": TransportMovementStatus.NORMAL_MOVE.value,
        },
        options=_disembark_unit_selection_options(entries),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "post_normal_move_disembark_unit_selection_required",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "transport_unit_instance_id": transport_unit_instance_id,
            "eligible_disembark_unit_count": len(entries),
        },
    )


def _pre_move_disembark_entries(
    *,
    state: GameState,
    movement_state: MovementPhaseState,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[DisembarkSelection, ...]:
    scenario = _battlefield_scenario(state)
    declined_unit_ids = set(movement_state.declined_disembark_unit_ids)
    entries: list[DisembarkSelection] = []
    for cargo_state in state.transport_cargo_states:
        if cargo_state.player_id != _active_player_id(state):
            continue
        active_cargo = cargo_state.for_movement_phase(battle_round=state.battle_round)
        transport_placement = scenario.battlefield_state.unit_placement_by_id(
            active_cargo.transport_unit_instance_id
        )
        for unit_instance_id in active_cargo.embarked_unit_instance_ids:
            if unit_instance_id in declined_unit_ids:
                continue
            if not active_cargo.unit_started_phase_embarked(unit_instance_id):
                continue
            if (
                state.disembarked_unit_state_for_unit(
                    player_id=active_cargo.player_id,
                    battle_round=state.battle_round,
                    unit_instance_id=unit_instance_id,
                )
                is not None
            ):
                continue
            unit = _unit_instance_by_id(state=state, unit_instance_id=unit_instance_id)
            selection = DisembarkSelection(
                player_id=active_cargo.player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=active_cargo.transport_unit_instance_id,
                attempted_placement=_deterministic_disembark_placement(
                    unit=unit,
                    transport_placement=transport_placement,
                ),
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            )
            resolution = resolve_disembark(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                cargo_state=active_cargo,
                selection=selection,
                unit=unit,
                transport_placement=transport_placement,
            )
            if resolution.is_valid:
                entries.append(selection)
    return tuple(sorted(entries, key=lambda selection: selection.unit_instance_id))


def _post_normal_move_disembark_entries(
    *,
    state: GameState,
    movement_state: MovementPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    transport_unit_instance_id: str,
) -> tuple[DisembarkSelection, ...]:
    scenario = _battlefield_scenario(state)
    requested_transport_id = _validate_identifier(
        "transport_unit_instance_id",
        transport_unit_instance_id,
    )
    cargo_state = state.transport_cargo_state_for_transport(requested_transport_id)
    if cargo_state is None or cargo_state.player_id != _active_player_id(state):
        return ()
    active_cargo = cargo_state.for_movement_phase(battle_round=state.battle_round)
    declined_unit_ids = set(movement_state.declined_post_normal_move_disembark_unit_ids)
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        active_cargo.transport_unit_instance_id
    )
    entries: list[DisembarkSelection] = []
    for unit_instance_id in active_cargo.embarked_unit_instance_ids:
        if unit_instance_id in declined_unit_ids:
            continue
        if not active_cargo.unit_started_phase_embarked(unit_instance_id):
            continue
        if (
            state.disembarked_unit_state_for_unit(
                player_id=active_cargo.player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_instance_id,
            )
            is not None
        ):
            continue
        unit = _unit_instance_by_id(state=state, unit_instance_id=unit_instance_id)
        selection = DisembarkSelection(
            player_id=active_cargo.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=active_cargo.transport_unit_instance_id,
            attempted_placement=_deterministic_disembark_placement(
                unit=unit,
                transport_placement=transport_placement,
            ),
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        )
        resolution = resolve_disembark(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            cargo_state=active_cargo,
            selection=selection,
            unit=unit,
            transport_placement=transport_placement,
        )
        if resolution.is_valid:
            entries.append(selection)
    return tuple(sorted(entries, key=lambda selection: selection.unit_instance_id))


def _disembark_unit_selection_options(
    selections: tuple[DisembarkSelection, ...],
) -> tuple[DecisionOption, ...]:
    unit_ids = tuple(selection.unit_instance_id for selection in selections)
    options = [
        DecisionOption(
            option_id=COMPLETE_DISEMBARKS_OPTION_ID,
            label="Complete Disembarks",
            payload={
                "transport_decision": COMPLETE_DISEMBARKS_OPTION_ID,
                "declined_unit_instance_ids": list(unit_ids),
            },
        )
    ]
    options.extend(
        DecisionOption(
            option_id=selection.unit_instance_id,
            label=f"Disembark {selection.unit_instance_id}",
            payload={
                "transport_decision": "select_disembark_unit",
                "unit_instance_id": selection.unit_instance_id,
                "transport_unit_instance_id": selection.transport_unit_instance_id,
            },
        )
        for selection in selections
    )
    return tuple(options)


def _apply_disembark_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Disembark selection actor must be the active player.")
    movement_state = state.movement_phase_state
    if (
        movement_state is None
        or movement_state.step is not MovementPhaseStepKind.MOVE_UNITS
        or movement_state.active_selection is not None
    ):
        raise GameLifecycleError("Disembark selection requires inactive Move Units step.")

    request_payload = _request_payload_for_result(decisions=decisions, result=result)
    transport_movement_status = transport_movement_status_from_token(
        _payload_string(request_payload, key="transport_movement_status")
    )
    if transport_movement_status is TransportMovementStatus.NOT_MOVED:
        entries = _pre_move_disembark_entries(
            state=state,
            movement_state=movement_state,
            ruleset_descriptor=ruleset_descriptor,
        )
    elif transport_movement_status is TransportMovementStatus.NORMAL_MOVE:
        entries = _post_normal_move_disembark_entries(
            state=state,
            movement_state=movement_state,
            ruleset_descriptor=ruleset_descriptor,
            transport_unit_instance_id=_payload_string(
                request_payload,
                key="transport_unit_instance_id",
            ),
        )
    else:
        raise GameLifecycleError("Disembark selection request has unsupported timing.")

    payload = _decision_payload_object(result.payload)
    transport_decision = _payload_string(payload, key="transport_decision")
    if transport_decision == COMPLETE_DISEMBARKS_OPTION_ID:
        declined_unit_ids = tuple(
            cast(list[str], _payload_json_array(payload, key="declined_unit_instance_ids"))
        )
        legal_decline_ids = {selection.unit_instance_id for selection in entries}
        if set(declined_unit_ids) != legal_decline_ids:
            raise GameLifecycleError("Disembark decline payload drift.")
        phase_body_status = "disembark_choices_declined"
        if transport_movement_status is TransportMovementStatus.NOT_MOVED:
            state.movement_phase_state = movement_state.with_disembark_declined(declined_unit_ids)
        else:
            state.movement_phase_state = movement_state.with_post_normal_move_disembark_declined(
                declined_unit_ids
            )
            phase_body_status = "post_normal_move_disembark_choices_declined"
        decisions.event_log.append(
            "disembark_choices_declined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "declined_unit_instance_ids": list(declined_unit_ids),
                "transport_movement_status": transport_movement_status.value,
                "phase_body_status": phase_body_status,
            },
        )
        return None
    if transport_decision != "select_disembark_unit":
        raise GameLifecycleError("Unsupported Disembark selection payload.")
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    transport_unit_instance_id = _payload_string(payload, key="transport_unit_instance_id")
    matching = tuple(
        selection
        for selection in entries
        if selection.unit_instance_id == unit_instance_id
        and selection.transport_unit_instance_id == transport_unit_instance_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Disembark selection is not currently legal.")
    decisions.event_log.append(
        "disembark_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "transport_unit_instance_id": transport_unit_instance_id,
            "transport_movement_status": matching[0].transport_movement_status.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "disembark_unit_selected",
        },
    )
    return _request_disembark_placement(
        state=state,
        decisions=decisions,
        selection=matching[0],
        ruleset_descriptor=ruleset_descriptor,
    )


def _request_disembark_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: DisembarkSelection,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACE_DISEMBARK_UNIT_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": selection.unit_instance_id,
            "transport_unit_instance_id": selection.transport_unit_instance_id,
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
        options=(
            DecisionOption(
                option_id=BattlefieldPlacementKind.DISEMBARK.value,
                label="Place Disembarking Unit",
                payload=validate_json_value(
                    {
                        "transport_decision": "place_disembark_unit",
                        "unit_instance_id": selection.unit_instance_id,
                        "transport_unit_instance_id": selection.transport_unit_instance_id,
                        "attempted_placement": selection.attempted_placement.to_payload(),
                        "transport_movement_status": selection.transport_movement_status.value,
                        "restriction_overrides": [
                            override.to_payload() for override in selection.restriction_overrides
                        ],
                    }
                ),
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "disembark_placement_required",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": selection.unit_instance_id,
            "transport_unit_instance_id": selection.transport_unit_instance_id,
        },
    )


def _apply_disembark_placement_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Disembark placement actor must be the active player.")
    payload = _decision_payload_object(result.payload)
    if _payload_string(payload, key="transport_decision") != "place_disembark_unit":
        raise GameLifecycleError("Unsupported Disembark placement payload.")
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    transport_unit_instance_id = _payload_string(payload, key="transport_unit_instance_id")
    attempted_placement = _payload_unit_placement(payload, key="attempted_placement")
    selection = DisembarkSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        transport_unit_instance_id=transport_unit_instance_id,
        attempted_placement=attempted_placement,
        transport_movement_status=transport_movement_status_from_token(
            _payload_string(payload, key="transport_movement_status")
        ),
        restriction_overrides=_payload_transport_overrides(payload, key="restriction_overrides"),
    )
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Disembark placement requires TransportCargoState.")
    scenario = _battlefield_scenario(state)
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport_unit_instance_id
    )
    resolution = resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=_unit_instance_by_id(state=state, unit_instance_id=unit_instance_id),
        transport_placement=transport_placement,
    )
    if not resolution.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_player_id,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            result=result,
            phase_body_status="disembark_placement_invalid",
            violations=resolution.violations,
        )
        decisions.event_log.append("disembark_placement_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Disembark placement is invalid.",
            payload=invalid_payload,
        )
    _apply_valid_disembark(
        state=state,
        decisions=decisions,
        disembark=resolution,
        result=result,
    )
    return None


def _apply_valid_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    disembark: DisembarkResolution,
    result: DecisionResult,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Disembark placement requires battlefield_state.")
    if disembark.updated_cargo_state is None or disembark.disembarked_unit_state is None:
        raise GameLifecycleError("Valid DisembarkResolution requires state records.")
    state.battlefield_state = apply_disembark_to_battlefield(
        battlefield_state=battlefield_state,
        disembark=disembark,
    )
    state.replace_transport_cargo_state(disembark.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.disembarked_unit_state)
    if disembark.selection.transport_movement_status is TransportMovementStatus.NORMAL_MOVE:
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
        state.movement_phase_state = (
            movement_state.with_post_normal_move_disembark_counted_as_moved(
                disembark.selection.unit_instance_id
            )
        )
    decisions.event_log.append(
        "unit_disembarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": disembark.selection.unit_instance_id,
            "transport_unit_instance_id": disembark.selection.transport_unit_instance_id,
            "transport_movement_status": disembark.selection.transport_movement_status.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_disembarked",
            "updated_cargo_state": validate_json_value(disembark.updated_cargo_state.to_payload()),
            "disembarked_unit_state": validate_json_value(
                disembark.disembarked_unit_state.to_payload()
            ),
            "transition_batch": validate_json_value(disembark.transition_batch.to_payload())
            if disembark.transition_batch is not None
            else None,
        },
    )


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
            battle_round=state.battle_round,
            hover_mode_states=tuple(state.hover_mode_states),
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            disembarked_unit_state=state.disembarked_unit_state_for_unit(
                player_id=_active_player_id(state),
                battle_round=state.battle_round,
                unit_instance_id=active_selection.unit_instance_id,
            ),
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


def _apply_movement_action_decision(  # noqa: RET503
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
    unit = scenario.unit_instance_for_placement(unit_placement)
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    if not availability_result.is_available(action):
        raise GameLifecycleError("Movement action is not currently legal for the selected unit.")
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=active_selection.unit_instance_id,
    )
    if disembarked_state is not None:
        if (
            action is MovementPhaseActionKind.REMAIN_STATIONARY
            and not disembarked_state.can_choose_remain_stationary
        ):
            raise GameLifecycleError("Disembarked unit cannot Remain Stationary.")
        if (
            action is not MovementPhaseActionKind.REMAIN_STATIONARY
            and not disembarked_state.can_move_further
        ):
            raise GameLifecycleError("Disembarked unit cannot move further.")

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
            hover_mode_states=tuple(state.hover_mode_states),
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
        transition_reason = _aircraft_reserve_transition_reason_for_normal_move(
            resolution=resolution,
            scenario=scenario,
            unit_placement=unit_placement,
            battlefield_width_inches=_DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
            battlefield_depth_inches=_DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
        )
        if transition_reason is not None:
            _apply_aircraft_reserve_transition_for_normal_move(
                state=state,
                decisions=decisions,
                result=result,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
                resolution=resolution,
                witness=witness,
                reason=transition_reason,
            )
            return None
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
        return _request_embark_after_move_or_complete_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=resolution.movement_payload,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            transition_batch=transition_batch,
            ruleset_descriptor=ruleset_descriptor,
        )

    if action is MovementPhaseActionKind.ADVANCE:
        advance_roll_request = _advance_roll_request_for_action(
            state=state,
            unit=unit,
            unit_placement=unit_placement,
            action_result=result,
        )
        advance_roll_state = _roll_advance_dice(
            state=state,
            decisions=decisions,
            request=advance_roll_request,
        )
        if advance_roll_request.reroll_permission is not None:
            reroll_request = _advance_roll_reroll_request(
                state=state,
                decisions=decisions,
                dice_roll_state=advance_roll_state,
                advance_roll_request=advance_roll_request,
                action_result=result,
            )
            decisions.request_decision(reroll_request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=reroll_request,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "advance_roll_reroll_pending",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                },
            )
        advance_roll = AdvanceRollResult.from_roll_state(
            request=advance_roll_request,
            roll_state=advance_roll_state,
        )
        return _resolve_and_apply_advance_move(
            state=state,
            decisions=decisions,
            result=result,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            advance_roll=advance_roll,
        )

    if action is MovementPhaseActionKind.FALL_BACK:
        witness = _payload_path_witness(payload, key="witness")
        fall_back_resolution = resolve_fall_back_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            path_witness=witness,
            battle_round=state.battle_round,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            hover_mode_states=tuple(state.hover_mode_states),
        )
        drift_code = fall_back_resolution.selected_payload_drift_code(payload)
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
                    **fall_back_resolution.movement_payload,
                },
            )
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message="Fall Back replay payload drift.",
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
        if not fall_back_resolution.is_valid:
            violation_code = _normal_move_violation_code(fall_back_resolution)
            invalid_payload = _movement_action_invalid_payload(
                state=state,
                active_player_id=active_player_id,
                unit_instance_id=active_selection.unit_instance_id,
                action=action,
                result=result,
                violation_code=violation_code,
                movement_payload=fall_back_resolution.movement_payload,
                rollback_record=fall_back_resolution.rollback_record,
            )
            decisions.event_log.append("movement_action_invalid", invalid_payload)
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message=_normal_move_invalid_message(violation_code).replace(
                    "Normal Move",
                    "Fall Back",
                ),
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
        desperate_escape_rolls = _roll_desperate_escape_dice(
            state=state,
            decisions=decisions,
            resolution=fall_back_resolution,
        )
        fall_back_result = FallBackActionResult.with_desperate_escape_rolls(
            resolution=fall_back_resolution,
            desperate_escape_rolls=desperate_escape_rolls,
        )
        if fall_back_result.failed_desperate_escape_rolls:
            request = _desperate_escape_model_selection_request(
                state=state,
                fall_back_result=fall_back_result,
                action_result=result,
            )
            decisions.request_decision(request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "desperate_escape_model_selection_pending",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                },
            )
        return _apply_fall_back_result(
            state=state,
            decisions=decisions,
            result=result,
            unit_placement=unit_placement,
            fall_back_result=fall_back_result,
            destroyed_model_ids=(),
            ruleset_descriptor=ruleset_descriptor,
        )


def _apply_advance_roll_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Advance reroll actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Advance reroll requires active movement selection.")

    record = decisions.record_for_result(result)
    request_payload = _decision_payload_object(record.request.payload)
    context_payload = _payload_object(request_payload, key="movement_context")
    if _payload_string(context_payload, key="movement_phase_action") != (
        MovementPhaseActionKind.ADVANCE.value
    ):
        raise GameLifecycleError("Advance reroll request context must be for Advance.")
    unit_instance_id = _payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != movement_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Advance reroll unit must match active movement selection.")
    action_request_id = _payload_string(context_payload, key="action_request_id")
    action_result_id = _payload_string(context_payload, key="action_result_id")
    initial_roll_payload = _payload_object(context_payload, key="advance_roll_state")
    advance_request_payload = _payload_object(context_payload, key="advance_roll_request")
    advance_request = AdvanceRollRequest.from_payload(
        cast(AdvanceRollRequestPayload, advance_request_payload)
    )
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    dice_manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    rerolled_state = dice_manager.resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    advance_roll = AdvanceRollResult.from_roll_state(
        request=advance_request,
        roll_state=rerolled_state,
    )
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    action_result = DecisionResult(
        result_id=action_result_id,
        request_id=action_request_id,
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=active_player_id,
        selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        payload={
            "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
            "unit_instance_id": unit_instance_id,
        },
    )
    return _resolve_and_apply_advance_move(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        advance_roll=advance_roll,
    )


def _resolve_and_apply_advance_move(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    advance_roll: AdvanceRollResult,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    _record_advance_roll_resolved_event(
        state=state,
        decisions=decisions,
        advance_roll=advance_roll,
    )
    resolution = resolve_advance_move(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        advance_roll=advance_roll,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    if not resolution.is_valid:
        violation_code = _normal_move_violation_code(resolution)
        invalid_payload: dict[str, JsonValue] = {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_placement.unit_instance_id,
            "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
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
            message=_normal_move_invalid_message(violation_code).replace("Normal Move", "Advance"),
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "phase_body_status": "movement_action_invalid",
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "unit_instance_id": unit_placement.unit_instance_id,
                "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                "violation_code": violation_code,
            },
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Advance requires battlefield_state.")
    state.battlefield_state = battlefield_state.with_unit_placement(resolution.attempted_placement)
    dice_record = MovementDiceRecord(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_placement.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        advance_roll=advance_roll,
    )
    state.record_advanced_unit_state(
        AdvancedUnitState(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            movement_dice_record=dice_record,
        )
    )
    return _request_embark_after_move_or_complete_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.ADVANCE,
        witness=resolution.witness,
        movement_payload=resolution.movement_payload,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        transition_batch=transition_batch,
        ruleset_descriptor=ruleset_descriptor,
    )


def _aircraft_reserve_transition_reason_for_normal_move(
    *,
    resolution: NormalMoveResolution,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> AircraftReserveTransitionReason | None:
    if type(resolution) is not NormalMoveResolution:
        raise GameLifecycleError("Aircraft reserve transition requires NormalMoveResolution.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Aircraft reserve transition requires a BattlefieldScenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Aircraft reserve transition requires a UnitPlacement.")
    policy_payload = resolution.movement_payload.get("aircraft_movement_policy")
    if policy_payload is None:
        return None
    policy = AircraftMovementPolicy.from_payload(
        cast(
            AircraftMovementPolicyPayload,
            _validate_json_object("aircraft policy", policy_payload),
        )
    )
    if not policy.uses_aircraft_rules:
        return None
    violation_codes = {
        violation.violation_code
        for path_result in resolution.path_validation_results
        for violation in path_result.violations
    }
    if "battlefield_edge_crossed" in violation_codes:
        return AircraftReserveTransitionReason.BATTLEFIELD_EDGE_CROSSED
    if "aircraft_minimum_move_required" in violation_codes and any(
        _aircraft_minimum_move_unavailable(
            moving_model=geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            ),
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
            minimum_move_inches=_aircraft_minimum_move_inches(policy),
        )
        for placement in unit_placement.model_placements
    ):
        return AircraftReserveTransitionReason.MINIMUM_MOVE_UNAVAILABLE
    return None


def _apply_aircraft_reserve_transition_for_normal_move(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    resolution: NormalMoveResolution,
    witness: PathWitness,
    reason: AircraftReserveTransitionReason,
) -> None:
    transition = resolve_aircraft_reserve_transition(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        battle_round=state.battle_round,
        reason=reason,
        source_event_id=result.result_id,
        hover_mode_state=state.hover_mode_state_for_unit(unit_placement.unit_instance_id),
    )
    if not transition.is_valid:
        raise GameLifecycleError("Aircraft reserve transition must be valid for lifecycle apply.")
    if transition.reserve_state is None or transition.transition_batch is None:
        raise GameLifecycleError("Aircraft reserve transition requires mutation data.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Aircraft reserve transition requires battlefield_state.")
    state.battlefield_state = apply_aircraft_reserve_transition_to_battlefield(
        battlefield_state=battlefield_state,
        transition=transition,
    )
    if state.reserve_state_for_unit(transition.reserve_state.unit_instance_id) is None:
        state.record_reserve_state(transition.reserve_state)
    else:
        state.replace_reserve_state(transition.reserve_state)
    _complete_movement_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.NORMAL_MOVE,
        witness=witness,
        movement_payload={
            **resolution.movement_payload,
            "aircraft_reserve_transition": validate_json_value(transition.to_payload()),
        },
        displacement_kind=None,
        transition_batch=transition.transition_batch,
    )


def _apply_desperate_escape_model_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Desperate Escape selection actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Desperate Escape selection requires active movement selection.")

    record = decisions.record_for_result(result)
    request_payload = _decision_payload_object(record.request.payload)
    context_payload = _payload_object(request_payload, key="fall_back_context")
    unit_instance_id = _payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != movement_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Desperate Escape selection unit must match active selection.")
    fall_back_result_payload = cast(
        FallBackActionResultPayload,
        _payload_object(context_payload, key="fall_back_result"),
    )
    fall_back_result = FallBackActionResult.from_payload(fall_back_result_payload)
    destroyed_model_ids = tuple(
        cast(
            list[str],
            _payload_json_array(
                _decision_payload_object(result.payload),
                key="destroyed_model_ids",
            ),
        )
    )
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    action_result = DecisionResult(
        result_id=_payload_string(context_payload, key="action_result_id"),
        request_id=_payload_string(context_payload, key="action_request_id"),
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=active_player_id,
        selected_option_id=MovementPhaseActionKind.FALL_BACK.value,
        payload={
            "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
            "unit_instance_id": unit_instance_id,
            "witness": validate_json_value(fall_back_result.witness.to_payload()),
            **fall_back_result.movement_payload,
        },
    )
    return _apply_fall_back_result(
        state=state,
        decisions=decisions,
        result=action_result,
        unit_placement=unit_placement,
        fall_back_result=fall_back_result,
        destroyed_model_ids=destroyed_model_ids,
        ruleset_descriptor=ruleset_descriptor,
    )


def _apply_fall_back_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_placement: UnitPlacement,
    fall_back_result: FallBackActionResult,
    destroyed_model_ids: tuple[str, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    scenario = _battlefield_scenario(state)
    surviving_placement = fall_back_result.surviving_attempted_placement(
        destroyed_model_ids=destroyed_model_ids,
    )
    if surviving_placement is not None:
        survivor_coherency_result = unit_placement_coherency_result(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=surviving_placement,
        )
        if not survivor_coherency_result.is_coherent:
            violation_code = "unit_coherency_broken"
            invalid_payload = _movement_action_invalid_payload(
                state=state,
                active_player_id=active_player_id,
                unit_instance_id=unit_placement.unit_instance_id,
                action=MovementPhaseActionKind.FALL_BACK,
                result=result,
                violation_code=violation_code,
                movement_payload={
                    **fall_back_result.movement_payload,
                    "destroyed_model_ids": list(destroyed_model_ids),
                    "surviving_coherency_result": validate_json_value(
                        survivor_coherency_result.to_payload()
                    ),
                },
                rollback_record=None,
            )
            decisions.event_log.append("movement_action_invalid", invalid_payload)
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message="Fall Back surviving endpoint violates unit coherency.",
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "movement_action_invalid",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": unit_placement.unit_instance_id,
                    "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                    "violation_code": violation_code,
                },
            )
    transition_batch = fall_back_result.transition_batch(
        before=unit_placement,
        destroyed_model_ids=destroyed_model_ids,
    )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fall Back requires battlefield_state.")
    state.battlefield_state = battlefield_state.with_unit_placement(
        fall_back_result.attempted_placement
    ).with_removed_models(destroyed_model_ids)
    if surviving_placement is not None:
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                desperate_escape_rolls=fall_back_result.desperate_escape_rolls,
            )
        )
    return _request_embark_after_move_or_complete_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.FALL_BACK,
        witness=fall_back_result.witness,
        movement_payload={
            **fall_back_result.movement_payload,
            "destroyed_model_ids": list(destroyed_model_ids),
        },
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        transition_batch=transition_batch,
        ruleset_descriptor=ruleset_descriptor,
    )


def _request_embark_after_move_or_complete_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    active_selection = _active_movement_selection(state)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Movement activation completion requires battlefield_state.")
    if active_selection.unit_instance_id not in {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }:
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
        )
        return None
    options = _post_move_embark_options(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
        movement_phase_action=_transport_status_for_movement_action(action),
    )
    if not options:
        return _complete_activation_then_request_post_normal_disembark_if_available(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
            ruleset_descriptor=ruleset_descriptor,
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "movement_context": _movement_completion_context_payload(
                result=result,
                action=action,
                witness=witness,
                movement_payload=movement_payload,
                displacement_kind=displacement_kind,
                transition_batch=transition_batch,
            ),
        },
        options=(
            DecisionOption(
                option_id=DECLINE_EMBARK_OPTION_ID,
                label="Decline Embark",
                payload={
                    "transport_decision": DECLINE_EMBARK_OPTION_ID,
                    "unit_instance_id": active_selection.unit_instance_id,
                },
            ),
            *options,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "embark_choice_required",
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "eligible_transport_count": len(options),
        },
    )


def _complete_activation_then_request_post_normal_disembark_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    active_selection = _active_movement_selection(state)
    transport_unit_instance_id = active_selection.unit_instance_id
    _complete_movement_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )
    if action is not MovementPhaseActionKind.NORMAL_MOVE:
        return None
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
    return _request_post_normal_move_disembark_if_available(
        state=state,
        decisions=decisions,
        movement_state=movement_state,
        ruleset_descriptor=ruleset_descriptor,
        transport_unit_instance_id=transport_unit_instance_id,
    )


def _post_move_embark_options(
    *,
    state: GameState,
    unit_instance_id: str,
    movement_phase_action: TransportMovementStatus,
) -> tuple[DecisionOption, ...]:
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    options: list[DecisionOption] = []
    for cargo_state in state.transport_cargo_states:
        if cargo_state.player_id != unit_placement.player_id:
            continue
        transport_placement = scenario.battlefield_state.unit_placement_by_id(
            cargo_state.transport_unit_instance_id
        )
        selection = EmbarkSelection(
            player_id=unit_placement.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=cargo_state.transport_unit_instance_id,
            movement_phase_action=movement_phase_action,
        )
        resolution = resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=selection,
            unit_placement=unit_placement,
            transport_placement=transport_placement,
        )
        if not resolution.is_valid:
            continue
        options.append(
            DecisionOption(
                option_id=cargo_state.transport_unit_instance_id,
                label=f"Embark {cargo_state.transport_unit_instance_id}",
                payload=validate_json_value(
                    {
                        "transport_decision": "embark_unit",
                        **selection.to_payload(),
                    }
                ),
            )
        )
    return tuple(sorted(options, key=lambda option: option.option_id))


def _apply_embark_transport_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_selection = _active_movement_selection(state)
    if result.actor_id != active_selection.player_id:
        raise GameLifecycleError("Embark selection actor must be the active player.")
    request_payload = _request_payload_for_result(decisions=decisions, result=result)
    context_payload = _payload_object(request_payload, key="movement_context")
    action = movement_phase_action_kind_from_token(
        _payload_string(context_payload, key="movement_phase_action")
    )
    witness = _optional_payload_path_witness(context_payload, key="witness")
    movement_payload = _payload_json_object(context_payload, key="movement_payload")
    displacement_kind = _payload_model_displacement_kind(context_payload, key="displacement_kind")
    transition_batch = _payload_transition_batch(context_payload, key="transition_batch")

    payload = _decision_payload_object(result.payload)
    transport_decision = _payload_string(payload, key="transport_decision")
    if transport_decision == DECLINE_EMBARK_OPTION_ID:
        if _payload_string(payload, key="unit_instance_id") != active_selection.unit_instance_id:
            raise GameLifecycleError("Embark decline unit drift.")
        declined_unit_id = active_selection.unit_instance_id
        _complete_movement_activation_with_record_ids(
            state=state,
            decisions=decisions,
            request_id=_payload_string(context_payload, key="action_request_id"),
            result_id=_payload_string(context_payload, key="action_result_id"),
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
        )
        decisions.event_log.append(
            "embark_declined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "embark_declined",
            },
        )
        if action is not MovementPhaseActionKind.NORMAL_MOVE:
            return None
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
        return _request_post_normal_move_disembark_if_available(
            state=state,
            decisions=decisions,
            movement_state=movement_state,
            ruleset_descriptor=ruleset_descriptor,
            transport_unit_instance_id=declined_unit_id,
        )
    if transport_decision != "embark_unit":
        raise GameLifecycleError("Unsupported Embark selection payload.")
    selection = EmbarkSelection.from_payload(
        cast(
            EmbarkSelectionPayload,
            {
                "player_id": _payload_string(payload, key="player_id"),
                "battle_round": _payload_positive_int(payload, key="battle_round"),
                "unit_instance_id": _payload_string(payload, key="unit_instance_id"),
                "transport_unit_instance_id": _payload_string(
                    payload, key="transport_unit_instance_id"
                ),
                "movement_phase_action": _payload_string(payload, key="movement_phase_action"),
                "restriction_overrides": cast(
                    list[TransportRestrictionOverridePayload],
                    _payload_json_array(payload, key="restriction_overrides"),
                ),
            },
        )
    )
    cargo_state = state.transport_cargo_state_for_transport(selection.transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Embark requires TransportCargoState.")
    scenario = _battlefield_scenario(state)
    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=cargo_state,
        selection=selection,
        unit_placement=scenario.battlefield_state.unit_placement_by_id(
            active_selection.unit_instance_id
        ),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            selection.transport_unit_instance_id
        ),
    )
    if not resolution.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_selection.player_id,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            result=result,
            phase_body_status="embark_selection_invalid",
            violations=resolution.violations,
        )
        decisions.event_log.append("embark_selection_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Embark selection is invalid.",
            payload=invalid_payload,
        )
    _apply_valid_embark(
        state=state,
        decisions=decisions,
        embark=resolution,
        result=result,
        context_payload=context_payload,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )
    return None


def _apply_valid_embark(
    *,
    state: GameState,
    decisions: DecisionController,
    embark: EmbarkResolution,
    result: DecisionResult,
    context_payload: dict[str, JsonValue],
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Embark requires battlefield_state.")
    if embark.updated_cargo_state is None:
        raise GameLifecycleError("Valid EmbarkResolution requires updated cargo state.")
    state.battlefield_state = apply_embark_to_battlefield(
        battlefield_state=battlefield_state,
        embark=embark,
    )
    state.replace_transport_cargo_state(embark.updated_cargo_state)
    decisions.event_log.append(
        "unit_embarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": embark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": embark.selection.unit_instance_id,
            "transport_unit_instance_id": embark.selection.transport_unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_embarked",
            "updated_cargo_state": validate_json_value(embark.updated_cargo_state.to_payload()),
            "transition_batch": validate_json_value(embark.transition_batch.to_payload())
            if embark.transition_batch is not None
            else None,
        },
    )
    _complete_movement_activation_with_record_ids(
        state=state,
        decisions=decisions,
        request_id=_payload_string(context_payload, key="action_request_id"),
        result_id=_payload_string(context_payload, key="action_result_id"),
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
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
    _complete_movement_activation_with_record_ids(
        state=state,
        decisions=decisions,
        request_id=result.request_id,
        result_id=result.result_id,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )


def _complete_movement_activation_with_record_ids(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    result_id: str,
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
        "request_id": request_id,
        "result_id": result_id,
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
    battle_round: int = 1,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    battle_shocked_unit_ids: tuple[str, ...] = (),
    disembarked_unit_state: DisembarkedUnitState | None = None,
) -> tuple[DecisionOption, ...]:
    if disembarked_unit_state is not None and type(disembarked_unit_state) is not (
        DisembarkedUnitState
    ):
        raise GameLifecycleError(
            "Movement action options disembarked_unit_state must be DisembarkedUnitState."
        )
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=hover_mode_states,
    )
    options: list[DecisionOption] = []
    for action in availability_result.available_actions:
        if disembarked_unit_state is not None:
            if (
                action is MovementPhaseActionKind.REMAIN_STATIONARY
                and not disembarked_unit_state.can_choose_remain_stationary
            ):
                continue
            if (
                action is not MovementPhaseActionKind.REMAIN_STATIONARY
                and not disembarked_unit_state.can_move_further
            ):
                continue
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
                hover_mode_states=hover_mode_states,
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
        if action is MovementPhaseActionKind.FALL_BACK:
            fall_back_resolution = resolve_fall_back_move(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
                path_witness=None,
                battle_round=battle_round,
                battle_shocked_unit_ids=battle_shocked_unit_ids,
                hover_mode_states=hover_mode_states,
            )
            options.append(
                DecisionOption(
                    option_id=MovementPhaseActionKind.FALL_BACK.value,
                    label="Fall Back",
                    payload=validate_json_value(
                        {
                            "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                            "displacement_kind": ModelDisplacementKind.FALL_BACK.value,
                            "unit_instance_id": unit_placement.unit_instance_id,
                            "witness": fall_back_resolution.witness.to_payload(),
                            **fall_back_resolution.movement_payload,
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


def _advance_roll_request_for_action(
    *,
    state: GameState,
    unit: UnitInstance,
    unit_placement: UnitPlacement,
    action_result: DecisionResult,
) -> AdvanceRollRequest:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Advance roll requires a UnitInstance.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Advance roll requires a UnitPlacement.")
    return AdvanceRollRequest.for_unit(
        request_id=f"{action_result.result_id}:advance-roll",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        reroll_permission=_advance_reroll_permission_for_unit(
            unit_instance_id=unit_placement.unit_instance_id,
            player_id=unit_placement.player_id,
            keywords=unit.keywords,
        ),
    )


def _roll_advance_dice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: AdvanceRollRequest,
) -> DiceRollState:
    decisions.event_log.append(
        "advance_roll_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": request.unit_instance_id,
            "advance_roll_request": validate_json_value(request.to_payload()),
        },
    )
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    return manager.roll(request.spec)


def _record_advance_roll_resolved_event(
    *,
    state: GameState,
    decisions: DecisionController,
    advance_roll: AdvanceRollResult,
) -> None:
    decisions.event_log.append(
        "advance_roll_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": advance_roll.request.unit_instance_id,
            "advance_roll": validate_json_value(advance_roll.to_payload()),
        },
    )


def _advance_roll_reroll_request(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_roll_state: DiceRollState,
    advance_roll_request: AdvanceRollRequest,
    action_result: DecisionResult,
) -> DecisionRequest:
    permission = advance_roll_request.reroll_permission
    if permission is None:
        raise GameLifecycleError("Advance reroll request requires a legal reroll permission.")
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    return manager.build_reroll_request(
        dice_roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=advance_roll_request.player_id,
        permission=permission,
        extra_payload={
            "movement_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                "unit_instance_id": advance_roll_request.unit_instance_id,
                "action_request_id": action_result.request_id,
                "action_result_id": action_result.result_id,
                "advance_roll_request": validate_json_value(advance_roll_request.to_payload()),
                "advance_roll_state": validate_json_value(dice_roll_state.to_payload()),
            }
        },
    )


def _dice_roll_manager_for_state(
    *,
    state: GameState,
    decisions: DecisionController,
) -> DiceRollManager:
    return DiceRollManager(state.game_id, event_log=decisions.event_log)


def _advance_reroll_permission_for_unit(
    *,
    unit_instance_id: str,
    player_id: str,
    keywords: tuple[str, ...],
) -> RerollPermission | None:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    if _ADVANCE_REROLL_KEYWORD not in keyword_set:
        return None
    return RerollPermission(
        source_id=f"{unit_instance_id}:advance-reroll",
        timing_window="after_roll_before_modifiers",
        owning_player_id=player_id,
        eligible_roll_type="advance_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def _roll_desperate_escape_dice(
    *,
    state: GameState,
    decisions: DecisionController,
    resolution: FallBackActionResult,
) -> tuple[DesperateEscapeRoll, ...]:
    rolls: list[DesperateEscapeRoll] = []
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    for requirement in resolution.desperate_escape_requirements:
        decisions.event_log.append(
            "desperate_escape_roll_requested",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": requirement.unit_instance_id,
                "model_instance_id": requirement.model_instance_id,
                "desperate_escape_requirement": validate_json_value(requirement.to_payload()),
            },
        )
        roll = DesperateEscapeRoll.from_roll_state(
            requirement=requirement,
            roll_state=manager.roll(requirement.roll_spec()),
        )
        decisions.event_log.append(
            "desperate_escape_roll_resolved",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": requirement.unit_instance_id,
                "model_instance_id": requirement.model_instance_id,
                "desperate_escape_roll": validate_json_value(roll.to_payload()),
            },
        )
        rolls.append(roll)
    return tuple(rolls)


def _desperate_escape_model_selection_request(
    *,
    state: GameState,
    fall_back_result: FallBackActionResult,
    action_result: DecisionResult,
) -> DecisionRequest:
    failed_model_ids = tuple(
        roll.requirement.model_instance_id
        for roll in fall_back_result.failed_desperate_escape_rolls
    )
    if not failed_model_ids:
        raise GameLifecycleError("Desperate Escape model selection requires failed rolls.")
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "fall_back_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": fall_back_result.unit_instance_id,
                "action_request_id": action_result.request_id,
                "action_result_id": action_result.result_id,
                "fall_back_result": validate_json_value(fall_back_result.to_payload()),
                "failed_model_ids": list(failed_model_ids),
            }
        },
        options=_desperate_escape_model_selection_options(
            fall_back_result=fall_back_result,
        ),
    )


def _desperate_escape_model_selection_options(
    *,
    fall_back_result: FallBackActionResult,
) -> tuple[DecisionOption, ...]:
    failed_model_ids = tuple(
        roll.requirement.model_instance_id
        for roll in fall_back_result.failed_desperate_escape_rolls
    )
    destroyed_count = len(failed_model_ids)
    eligible_model_ids = tuple(
        placement.model_instance_id
        for placement in fall_back_result.attempted_placement.model_placements
    )
    options: list[DecisionOption] = []
    for selected_ids in combinations(eligible_model_ids, destroyed_count):
        option_id = "destroy:" + ",".join(selected_ids)
        options.append(
            DecisionOption(
                option_id=option_id,
                label="Destroy " + ", ".join(selected_ids),
                payload={
                    "unit_instance_id": fall_back_result.unit_instance_id,
                    "destroyed_model_ids": list(selected_ids),
                    "failed_model_ids": list(failed_model_ids),
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
    hover_mode_states: tuple[HoverModeState, ...] = (),
    battlefield_width_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> NormalMoveResolution:
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        path_witness=path_witness,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain=terrain,
        terrain_features=terrain_features,
        movement_bonus_inches=0,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        action_label="Normal Move",
        rollback_on_endpoint_coherency=True,
        hover_mode_states=hover_mode_states,
    )
    return NormalMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=resolved.movement_payload,
    )


def resolve_advance_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    advance_roll: AdvanceRollResult,
    path_witness: PathWitness | None = None,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    battlefield_width_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> AdvanceMoveResolution:
    if type(advance_roll) is not AdvanceRollResult:
        raise GameLifecycleError("Advance requires an AdvanceRollResult.")
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        path_witness=path_witness,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain=terrain,
        terrain_features=terrain_features,
        movement_bonus_inches=advance_roll.value,
        movement_mode=MovementMode.ADVANCE,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        action_label="Advance",
        rollback_on_endpoint_coherency=True,
        hover_mode_states=hover_mode_states,
    )
    movement_payload = {
        **resolved.movement_payload,
        "advance_roll": validate_json_value(advance_roll.to_payload()),
    }
    return AdvanceMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        advance_roll=advance_roll,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=movement_payload,
    )


def resolve_fall_back_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    path_witness: PathWitness | None = None,
    battle_round: int = 1,
    battle_shocked_unit_ids: tuple[str, ...] = (),
    hover_mode_states: tuple[HoverModeState, ...] = (),
    battlefield_width_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> FallBackActionResult:
    fall_back_witness = (
        _default_fall_back_witness(scenario=scenario, unit_placement=unit_placement)
        if path_witness is None
        else path_witness
    )
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        path_witness=fall_back_witness,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain=terrain,
        terrain_features=terrain_features,
        movement_bonus_inches=0,
        movement_mode=MovementMode.FALL_BACK,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        action_label="Fall Back",
        rollback_on_endpoint_coherency=False,
        hover_mode_states=hover_mode_states,
    )
    desperate_escape_requirements = _desperate_escape_requirements_for_fall_back(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        witness=resolved.witness,
        battle_round=battle_round,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
    )
    movement_payload = {
        **resolved.movement_payload,
        "desperate_escape_requirements": validate_json_value(
            [requirement.to_payload() for requirement in desperate_escape_requirements]
        ),
        "desperate_escape_rolls": [],
    }
    return FallBackActionResult.unresolved(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        desperate_escape_requirements=desperate_escape_requirements,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=movement_payload,
    )


def _resolve_unit_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    path_witness: PathWitness | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain: tuple[TerrainVolume, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    movement_bonus_inches: int,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    displacement_kind: ModelDisplacementKind,
    action_label: str,
    rollback_on_endpoint_coherency: bool,
    hover_mode_states: tuple[HoverModeState, ...],
) -> _ResolvedUnitMove:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError(f"{action_label} requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError(f"{action_label} requires a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError(f"{action_label} unit_placement must be a UnitPlacement.")
    if type(movement_bonus_inches) is not int:
        raise GameLifecycleError(f"{action_label} movement_bonus_inches must be an integer.")
    if movement_bonus_inches < 0:
        raise GameLifecycleError(f"{action_label} movement_bonus_inches must not be negative.")
    unit = scenario.unit_instance_for_placement(unit_placement)
    hover_mode_state = _hover_mode_state_for_unit(
        hover_mode_states=hover_mode_states,
        unit_instance_id=unit_placement.unit_instance_id,
    )
    aircraft_policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=hover_mode_state,
    )
    witness = (
        _default_move_witness(
            scenario=scenario,
            unit_placement=unit_placement,
            aircraft_policy=aircraft_policy,
            movement_bonus_inches=movement_bonus_inches,
            movement_phase_action=movement_phase_action,
        )
        if path_witness is None
        else path_witness
    )
    _validate_move_witness_matches_unit(
        witness=witness,
        unit_placement=unit_placement,
        action_label=action_label,
    )
    aircraft_model_ids = aircraft_model_ids_for_scenario(
        scenario,
        hover_mode_states=hover_mode_states,
    )
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
        base_movement_inches = _model_base_movement_inches(
            model=model,
            aircraft_policy=aircraft_policy,
        )
        movement_inches = _model_default_movement_distance_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            movement_bonus_inches=movement_bonus_inches,
            movement_phase_action=movement_phase_action,
        )
        movement_distance_budget_inches = _model_movement_budget_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            movement_bonus_inches=movement_bonus_inches,
            movement_phase_action=movement_phase_action,
        )
        max_movement_inches = max(max_movement_inches, movement_inches)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=aircraft_policy.effective_keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            displacement_kind=displacement_kind,
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
            aircraft_model_ids=tuple(
                model_id
                for model_id in aircraft_model_ids
                if model_id != placement.model_instance_id
            ),
            movement_distance_budget_inches=movement_distance_budget_inches,
        ).validate()
        aircraft_violations: tuple[AircraftMovementViolation, ...] = ()
        aircraft_minimum_move_result: AircraftMinimumMoveResult | None = None
        if (
            aircraft_policy.uses_aircraft_rules
            and movement_phase_action is MovementPhaseActionKind.NORMAL_MOVE
        ):
            (
                aircraft_violations,
                aircraft_minimum_move_result,
            ) = aircraft_policy.validate_normal_move_witness_with_minimum_result(
                moving_model=moving_model,
                witness=model_witness,
            )
            path_result = _path_result_with_aircraft_violations(
                path_result=path_result,
                aircraft_violations=aircraft_violations,
            )
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain,
            terrain_features=terrain_features,
        ).validate()
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movement_payload: dict[str, object] = {
            "model_instance_id": placement.model_instance_id,
            "movement_inches": movement_inches,
            "base_movement_inches": base_movement_inches,
            "movement_bonus_inches": movement_bonus_inches,
            "base_size": model.base_size.to_payload(),
            "start_pose": placement.pose.to_payload(),
            "end_pose": witness.final_pose_for_model(placement.model_instance_id).to_payload(),
            "movement_distance_witness": (
                None
                if path_result.movement_distance_witness is None
                else path_result.movement_distance_witness.to_payload()
            ),
            "path_validation_result": path_result.to_payload(),
            "terrain_path_legality_result": terrain_result.to_payload(),
        }
        if aircraft_minimum_move_result is not None:
            model_movement_payload["aircraft_minimum_move_result"] = (
                aircraft_minimum_move_result.to_payload()
            )
        if aircraft_violations:
            model_movement_payload["aircraft_movement_violations"] = [
                violation.to_payload() for violation in aircraft_violations
            ]
        model_movements.append(validate_json_value(model_movement_payload))
    if rollback_on_endpoint_coherency:
        _, coherency_result, rollback_record = resolve_unit_movement_endpoint_coherency(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            before=unit_placement,
            attempted=attempted_placement,
            displacement_kind=displacement_kind,
        )
    else:
        coherency_result = unit_placement_coherency_result(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=attempted_placement,
        )
        rollback_record = None
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
    if aircraft_policy.has_aircraft_keyword:
        movement_payload["aircraft_movement_policy"] = validate_json_value(
            aircraft_policy.to_payload()
        )
    return _ResolvedUnitMove(
        attempted_placement=attempted_placement,
        witness=witness,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
    )


def _default_move_witness(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    aircraft_policy: AircraftMovementPolicy,
    movement_bonus_inches: int,
    movement_phase_action: MovementPhaseActionKind,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = _model_default_movement_distance_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            movement_bonus_inches=movement_bonus_inches,
            movement_phase_action=movement_phase_action,
        )
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                _default_move_end_pose(
                    start_pose=placement.pose,
                    aircraft_policy=aircraft_policy,
                    movement_inches=movement_inches,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _default_fall_back_witness(
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
                Pose.at(
                    x=placement.pose.position.x,
                    y=placement.pose.position.y + movement_inches,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _movement_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    displacement_kind: ModelDisplacementKind,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    displacement_records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Movement transition references an unknown model.")
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=displacement_kind,
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


def _fall_back_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    destroyed_model_ids: tuple[str, ...],
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    destroyed_id_set = set(_validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids))
    displacement_records: list[ModelDisplacementRecord] = []
    removal_records: list[ModelRemovalRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Fall Back transition references an unknown model.")
        if placement.model_instance_id in destroyed_id_set:
            removal_records.append(
                ModelRemovalRecord(
                    model_instance_id=placement.model_instance_id,
                    removal_kind=BattlefieldRemovalKind.DESTROYED,
                    source_phase=BattlePhase.MOVEMENT.value,
                    source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                    source_rule_id="desperate_escape",
                    source_event_id=None,
                    destination_id=None,
                )
            )
            continue
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.FALL_BACK,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.MOVEMENT.value,
                source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(
        removals=tuple(removal_records),
        displacements=tuple(displacement_records),
    )


def _normal_move_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
) -> BattlefieldTransitionBatch:
    return _movement_transition_batch(
        before=before,
        after=after,
        witness=witness,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _movement_action_availability_result(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> MovementActionAvailabilityResult:
    return _movement_action_availability_context(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=hover_mode_states,
    ).evaluate()


def _movement_action_availability_context(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> MovementActionAvailabilityContext:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Movement action availability requires a scenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Movement action availability requires a UnitPlacement.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Movement action availability requires a RulesetDescriptor.")
    unit = scenario.unit_instance_for_placement(unit_placement)
    hover_mode_state = _hover_mode_state_for_unit(
        hover_mode_states=hover_mode_states,
        unit_instance_id=unit_placement.unit_instance_id,
    )
    aircraft_policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=hover_mode_state,
    )
    enemy_engagement_model_ids, enemy_aircraft_engagement_model_ids = (
        _enemy_engagement_model_ids_for_unit(
            scenario=scenario,
            unit_placement=unit_placement,
            ruleset_descriptor=ruleset_descriptor,
            hover_mode_states=hover_mode_states,
        )
    )
    return MovementActionAvailabilityContext(
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        unit_instance_id=unit_placement.unit_instance_id,
        player_id=unit_placement.player_id,
        enemy_engagement_model_ids=enemy_engagement_model_ids,
        enemy_aircraft_engagement_model_ids=enemy_aircraft_engagement_model_ids,
        aircraft_movement_policy=aircraft_policy if aircraft_policy.has_aircraft_keyword else None,
    )


def _enemy_engagement_model_ids_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    friendly_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    aircraft_model_ids = set(
        aircraft_model_ids_for_scenario(
            scenario,
            hover_mode_states=hover_mode_states,
        )
    )
    enemy_model_ids: set[str] = set()
    enemy_aircraft_model_ids: set[str] = set()
    for friendly_model in friendly_models:
        for enemy_model in enemy_models:
            if friendly_model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                if enemy_model.model_id in aircraft_model_ids:
                    enemy_aircraft_model_ids.add(enemy_model.model_id)
                else:
                    enemy_model_ids.add(enemy_model.model_id)
    return tuple(sorted(enemy_model_ids)), tuple(sorted(enemy_aircraft_model_ids))


def _hover_mode_state_for_unit(
    *,
    hover_mode_states: tuple[HoverModeState, ...],
    unit_instance_id: str,
) -> HoverModeState | None:
    if type(hover_mode_states) is not tuple:
        raise GameLifecycleError("hover_mode_states must be a tuple.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    found: HoverModeState | None = None
    for hover_mode_state in cast(tuple[object, ...], hover_mode_states):
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_states must contain HoverModeState values.")
        if hover_mode_state.unit_instance_id != requested_unit_id:
            continue
        if found is not None:
            raise GameLifecycleError("hover_mode_states must be unique by unit.")
        found = hover_mode_state
    return found if found is not None and found.active else None


def _desperate_escape_requirements_for_fall_back(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    witness: PathWitness,
    battle_round: int,
    battle_shocked_unit_ids: tuple[str, ...],
) -> tuple[DesperateEscapeRequirement, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Desperate Escape requirements require a scenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Desperate Escape requirements require a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Desperate Escape requirements require a UnitPlacement.")
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Desperate Escape requirements require a PathWitness.")
    requirement_battle_round = _validate_positive_int(
        "Desperate Escape requirements battle_round",
        battle_round,
    )
    battle_shocked_ids = set(
        _validate_identifier_tuple(
            "battle_shocked_unit_ids",
            battle_shocked_unit_ids,
        )
    )
    unit = scenario.unit_instance_for_placement(unit_placement)
    unit_keyword_set = {_canonical_keyword(keyword) for keyword in unit.keywords}
    overflight_exempt = "FLY" in unit_keyword_set or "TITANIC" in unit_keyword_set
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    requirements: list[DesperateEscapeRequirement] = []
    for index, placement in enumerate(unit_placement.model_placements, start=1):
        reasons: list[DesperateEscapeRequirementReason] = []
        enemy_model_ids: tuple[str, ...] = ()
        if unit_placement.unit_instance_id in battle_shocked_ids:
            reasons.append(DesperateEscapeRequirementReason.BATTLE_SHOCKED)
        if not overflight_exempt:
            moving_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            )
            enemy_model_ids = _enemy_model_ids_crossed_by_witness(
                moving_model=moving_model,
                witness=witness,
                enemy_models=enemy_models,
            )
            if enemy_model_ids:
                reasons.append(DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT)
        if not reasons:
            continue
        requirements.append(
            DesperateEscapeRequirement(
                requirement_id=f"{unit_placement.unit_instance_id}:desperate-escape:{index:03d}",
                player_id=unit_placement.player_id,
                battle_round=requirement_battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                reasons=tuple(reasons),
                enemy_model_ids=enemy_model_ids,
            )
        )
    return tuple(requirements)


def _enemy_model_ids_crossed_by_witness(
    *,
    moving_model: Model,
    witness: PathWitness,
    enemy_models: tuple[Model, ...],
) -> tuple[str, ...]:
    crossed_enemy_ids: set[str] = set()
    for pose in _sampled_witness_transit_poses(
        witness.poses_for_model(moving_model.model_id),
        sample_interval_inches=0.5,
    ):
        sampled_model = _model_at_pose(moving_model, pose)
        for enemy_model in enemy_models:
            if sampled_model.base_overlaps(enemy_model):
                crossed_enemy_ids.add(enemy_model.model_id)
    return tuple(sorted(crossed_enemy_ids))


def _sampled_witness_transit_poses(
    poses: tuple[Pose, ...],
    *,
    sample_interval_inches: float,
) -> tuple[Pose, ...]:
    if type(poses) is not tuple:
        raise GameLifecycleError("Fall Back witness poses must be a tuple.")
    if len(poses) < 2:
        raise GameLifecycleError("Fall Back witness poses must include start and end.")
    interval = float(sample_interval_inches)
    if not math.isfinite(interval) or interval <= 0:
        raise GameLifecycleError("sample_interval_inches must be greater than 0.")
    sampled: list[Pose] = [poses[0]]
    previous = poses[0]
    for pose in poses[1:]:
        distance = previous.distance_3d_to(pose)
        steps = max(1, math.ceil(distance / interval))
        for step in range(1, steps + 1):
            sampled.append(_interpolate_pose(previous, pose, step / steps))
        previous = pose
    return tuple(sampled[1:-1])


def _interpolate_pose(start: Pose, end: Pose, t: float) -> Pose:
    return Pose.at(
        x=start.position.x + ((end.position.x - start.position.x) * t),
        y=start.position.y + ((end.position.y - start.position.y) * t),
        z=start.position.z + ((end.position.z - start.position.z) * t),
        facing_degrees=start.facing.degrees + ((end.facing.degrees - start.facing.degrees) * t),
    )


def _model_at_pose(model: Model, pose: Pose) -> Model:
    if type(model) is not Model:
        raise GameLifecycleError("model must be a geometry Model.")
    if type(pose) is not Pose:
        raise GameLifecycleError("pose must be a Pose.")
    return Model(
        model_id=model.model_id,
        pose=pose,
        base=model.base,
        volume=model.volume,
    )


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


def _unit_has_deep_strike_keyword(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Deep Strike keyword check requires a UnitInstance.")
    return "DEEP_STRIKE" in {_canonical_keyword(keyword) for keyword in unit.keywords}


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _validate_move_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: UnitPlacement,
    action_label: str,
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError(f"{action_label} requires a PathWitness.")
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError(f"{action_label} witness must match the selected unit models.")


def _path_result_with_aircraft_violations(
    *,
    path_result: PathValidationResult,
    aircraft_violations: tuple[AircraftMovementViolation, ...],
) -> PathValidationResult:
    if type(path_result) is not PathValidationResult:
        raise GameLifecycleError("Aircraft path validation requires a PathValidationResult.")
    if type(aircraft_violations) is not tuple:
        raise GameLifecycleError("aircraft_violations must be a tuple.")
    if not aircraft_violations:
        return path_result
    return PathValidationResult(
        violations=(
            *path_result.violations,
            *(
                PathConstraintViolation(
                    violation_code=violation.violation_code.value,
                    message=violation.message,
                    model_id=violation.model_instance_id,
                )
                for violation in aircraft_violations
            ),
        ),
        sampled_pose_count=path_result.sampled_pose_count,
        model_collision_check_count=path_result.model_collision_check_count,
        terrain_collision_check_count=path_result.terrain_collision_check_count,
        engagement_check_count=path_result.engagement_check_count,
        pivot_cost_inches=path_result.pivot_cost_inches,
        pivot_cost_pending=path_result.pivot_cost_pending,
        movement_distance_witness=path_result.movement_distance_witness,
    )


def _normal_move_violation_code(
    resolution: NormalMoveResolution | AdvanceMoveResolution | FallBackActionResult,
) -> str:
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


def _movement_action_invalid_payload(
    *,
    state: GameState,
    active_player_id: str,
    unit_instance_id: str,
    action: MovementPhaseActionKind,
    result: DecisionResult,
    violation_code: str,
    movement_payload: dict[str, JsonValue],
    rollback_record: MovementRollbackRecord | None,
) -> dict[str, JsonValue]:
    invalid_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": unit_instance_id,
        "movement_phase_action": action.value,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "phase_body_status": "movement_action_invalid",
        "violation_code": violation_code,
        **movement_payload,
    }
    if rollback_record is not None:
        invalid_payload["rollback_record"] = validate_json_value(rollback_record.to_payload())
    return invalid_payload


def assert_move_units_step_complete_for_reinforcements(
    *,
    state: GameState,
    movement_state: MovementPhaseState,
    message: str = "Move Units step must be complete before Reinforcements.",
) -> None:
    if type(movement_state) is not MovementPhaseState:
        raise GameLifecycleError("Move Units completion check requires MovementPhaseState.")
    if movement_state.step is not MovementPhaseStepKind.REINFORCEMENTS:
        raise GameLifecycleError("Move Units completion check requires Reinforcements step.")
    if movement_state.active_selection is not None:
        raise GameLifecycleError(message)
    incomplete_selected_unit_ids = tuple(
        unit_id
        for unit_id in movement_state.selected_unit_ids
        if unit_id not in movement_state.moved_unit_ids
    )
    if incomplete_selected_unit_ids:
        raise GameLifecycleError(message)
    remaining_unit_ids = _remaining_move_units_unit_ids(
        scenario=_battlefield_scenario(state),
        active_player_id=movement_state.active_player_id,
        selected_unit_ids=movement_state.selected_unit_ids,
        accounted_unplaced_model_ids=state.unavailable_model_ids(),
    )
    if remaining_unit_ids:
        raise GameLifecycleError(message)


def _remaining_move_units_unit_ids(
    *,
    scenario: BattlefieldScenario,
    active_player_id: str,
    selected_unit_ids: tuple[str, ...],
    accounted_unplaced_model_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("MovementPhaseState scenario must be a BattlefieldScenario.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    selected = set(_validate_identifier_tuple("selected_unit_ids", selected_unit_ids))
    accounted_ids = _validate_identifier_tuple(
        "accounted_unplaced_model_ids",
        accounted_unplaced_model_ids,
    )
    try:
        scenario.assert_all_mustered_models_placed_or_accounted(accounted_ids)
    except PlacementError as exc:
        raise GameLifecycleError("Movement phase requires complete placed armies.") from exc
    try:
        placed_army = scenario.battlefield_state.placed_army_for_player(player_id)
    except PlacementError:
        return ()
    return tuple(
        placement.unit_instance_id
        for placement in placed_army.unit_placements
        if placement.unit_instance_id not in selected
    )


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


def movement_phase_step_kind_from_token(token: object) -> MovementPhaseStepKind:
    if type(token) is MovementPhaseStepKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("MovementPhaseStepKind token must be a string.")
    try:
        return MovementPhaseStepKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported MovementPhaseStepKind token: {token}.") from exc


def desperate_escape_requirement_reason_from_token(
    token: object,
) -> DesperateEscapeRequirementReason:
    if type(token) is DesperateEscapeRequirementReason:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DesperateEscapeRequirementReason token must be a string.")
    try:
        return DesperateEscapeRequirementReason(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported DesperateEscapeRequirementReason token: {token}."
        ) from exc


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


def _model_base_movement_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
) -> float:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Movement model must be a ModelInstance.")
    if type(aircraft_policy) is not AircraftMovementPolicy:
        raise GameLifecycleError("Movement budget requires an AircraftMovementPolicy.")
    if aircraft_policy.hover_mode_active:
        return 20.0
    return _model_movement_inches(model)


def _model_movement_budget_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
    movement_bonus_inches: int,
    movement_phase_action: MovementPhaseActionKind,
) -> float | None:
    if type(movement_phase_action) is not MovementPhaseActionKind:
        raise GameLifecycleError("movement_phase_action must be a MovementPhaseActionKind.")
    if aircraft_policy.uses_aircraft_rules:
        return None
    return _model_base_movement_inches(
        model=model,
        aircraft_policy=aircraft_policy,
    ) + float(movement_bonus_inches)


def _model_default_movement_distance_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
    movement_bonus_inches: int,
    movement_phase_action: MovementPhaseActionKind,
) -> float:
    if aircraft_policy.uses_aircraft_rules:
        return _aircraft_minimum_move_inches(aircraft_policy)
    movement_budget = _model_movement_budget_inches(
        model=model,
        aircraft_policy=aircraft_policy,
        movement_bonus_inches=movement_bonus_inches,
        movement_phase_action=movement_phase_action,
    )
    if movement_budget is None:
        raise GameLifecycleError("Default movement distance requires a finite movement budget.")
    return movement_budget


def _default_move_end_pose(
    *,
    start_pose: Pose,
    aircraft_policy: AircraftMovementPolicy,
    movement_inches: float,
) -> Pose:
    if aircraft_policy.uses_aircraft_rules:
        return _translated_forward_pose(start_pose, movement_inches=movement_inches)
    return Pose.at(
        x=start_pose.position.x + movement_inches,
        y=start_pose.position.y,
        z=start_pose.position.z,
        facing_degrees=start_pose.facing.degrees,
    )


def _aircraft_minimum_move_inches(aircraft_policy: AircraftMovementPolicy) -> float:
    if type(aircraft_policy) is not AircraftMovementPolicy:
        raise GameLifecycleError("Aircraft minimum move requires an AircraftMovementPolicy.")
    minimum_move_inches = aircraft_policy.minimum_move_inches
    if minimum_move_inches is None:
        raise GameLifecycleError("AIRCRAFT movement policy requires minimum_move_inches.")
    return minimum_move_inches


def _aircraft_minimum_move_unavailable(
    *,
    moving_model: Model,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    minimum_move_inches: float,
) -> bool:
    if type(moving_model) is not Model:
        raise GameLifecycleError("Aircraft minimum move requires a geometry Model.")
    endpoint = _translated_forward_pose(moving_model.pose, movement_inches=minimum_move_inches)
    width = _validate_positive_number("battlefield_width_inches", battlefield_width_inches)
    depth = _validate_positive_number("battlefield_depth_inches", battlefield_depth_inches)
    return not model_is_within_battlefield_footprint(
        _model_at_pose(moving_model, endpoint),
        battlefield_width_inches=width,
        battlefield_depth_inches=depth,
    )


def _translated_forward_pose(pose: Pose, *, movement_inches: float) -> Pose:
    if type(movement_inches) not in (int, float):
        raise GameLifecycleError("movement_inches must be a number.")
    distance = float(movement_inches)
    if not math.isfinite(distance):
        raise GameLifecycleError("movement_inches must be finite.")
    if distance < 1.0:
        raise GameLifecycleError("movement_inches must be at least 1.")
    facing_radians = math.radians(pose.facing.degrees)
    return Pose.at(
        x=pose.position.x + (distance * math.cos(facing_radians)),
        y=pose.position.y + (distance * math.sin(facing_radians)),
        z=pose.position.z,
        facing_degrees=pose.facing.degrees,
    )


def _ruleset_descriptor_for_handler(handler: MovementPhaseHandler) -> RulesetDescriptor:
    if type(handler) is not MovementPhaseHandler:
        raise GameLifecycleError("Movement ruleset descriptor requires a MovementPhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Movement phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _mission_setup_for_live_reinforcements(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
) -> MissionSetup:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Live Reinforcements requires a RulesetDescriptor.")
    if (
        ruleset_descriptor.mission_policy.deployment_zone_source
        is not MissionDeploymentZoneSource.MISSION
    ):
        raise GameLifecycleError(
            "Live Reinforcements requires mission-sourced deployment-zone geometry."
        )
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError(
            "Live Reinforcements requires MissionSetup with deployment zones and terrain features."
        )
    return mission_setup


def _active_movement_selection(state: GameState) -> MovementUnitSelection:
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement transport decision requires active_selection.")
    return movement_state.active_selection


def _ensure_transport_cargo_phase_states(state: GameState) -> None:
    for cargo_state in tuple(state.transport_cargo_states):
        active_cargo_state = cargo_state.for_movement_phase(battle_round=state.battle_round)
        if active_cargo_state != cargo_state:
            state.replace_transport_cargo_state(active_cargo_state)


def _unit_instance_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Unknown unit_instance_id.")


def _deterministic_disembark_placement(
    *,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
) -> UnitPlacement:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Disembark placement requires a UnitInstance.")
    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("Disembark placement requires a Transport UnitPlacement.")
    if not transport_placement.model_placements:
        raise GameLifecycleError("Disembark placement requires a placed Transport model.")
    origin = transport_placement.model_placements[0].pose
    offsets = (
        (3.1, -1.5),
        (4.0, -0.2),
        (4.0, 1.2),
        (3.1, 2.5),
        (2.8, 0.5),
    )
    model_placements: list[ModelPlacement] = []
    for index, model in enumerate(unit.own_models):
        offset_x, offset_y = offsets[index % len(offsets)]
        row = index // len(offsets)
        pose = Pose.at(
            x=origin.position.x + offset_x + (row * 1.0),
            y=origin.position.y + offset_y,
            z=origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        model_placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=transport_placement.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
        )
    return UnitPlacement(
        army_id=unit.unit_instance_id.split(":", maxsplit=1)[0],
        player_id=transport_placement.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(model_placements),
    )


def _transport_status_for_movement_action(
    action: MovementPhaseActionKind,
) -> TransportMovementStatus:
    action_kind = movement_phase_action_kind_from_token(action)
    if action_kind is MovementPhaseActionKind.NORMAL_MOVE:
        return TransportMovementStatus.NORMAL_MOVE
    if action_kind is MovementPhaseActionKind.ADVANCE:
        return TransportMovementStatus.ADVANCE
    if action_kind is MovementPhaseActionKind.FALL_BACK:
        return TransportMovementStatus.FALL_BACK
    if action_kind is MovementPhaseActionKind.REMAIN_STATIONARY:
        return TransportMovementStatus.REMAIN_STATIONARY
    raise GameLifecycleError(f"Unsupported transport movement status action: {action_kind.value}.")


def _movement_completion_context_payload(
    *,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
) -> dict[str, JsonValue]:
    return {
        "action_request_id": result.request_id,
        "action_result_id": result.result_id,
        "movement_phase_action": action.value,
        "witness": None if witness is None else validate_json_value(witness.to_payload()),
        "movement_payload": validate_json_value(movement_payload),
        "displacement_kind": displacement_kind.value,
        "transition_batch": validate_json_value(transition_batch.to_payload()),
    }


def _transport_operation_invalid_payload(
    *,
    state: GameState,
    active_player_id: str,
    unit_instance_id: str,
    transport_unit_instance_id: str,
    result: DecisionResult,
    phase_body_status: str,
    violations: tuple[TransportOperationViolation, ...],
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "transport invalid payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "transport_unit_instance_id": transport_unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": phase_body_status,
            "violations": [violation.to_payload() for violation in violations],
        },
    )


def _request_payload_for_result(
    *,
    decisions: DecisionController,
    result: DecisionResult,
) -> dict[str, JsonValue]:
    for request in decisions.queue.pending_requests:
        if request.request_id == result.request_id:
            return _decision_payload_object(request.payload)
    for record in reversed(decisions.records):
        if record.result == result:
            return _decision_payload_object(record.request.payload)
    raise GameLifecycleError("DecisionResult does not match a known Movement request.")


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


def _payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be an object: {key}.")
    return value


def _payload_json_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    return _payload_object(payload, key=key)


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload key must be an integer: {key}.")
    return _validate_positive_int(key, value)


def _payload_unit_placement(payload: dict[str, JsonValue], *, key: str) -> UnitPlacement:
    value = _payload_object(payload, key=key)
    return UnitPlacement.from_payload(cast(UnitPlacementPayload, value))


def _payload_large_model_exceptions(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[LargeModelReservePlacementException, ...]:
    values = _payload_json_array(payload, key=key)
    exceptions: list[LargeModelReservePlacementException] = []
    for value in values:
        if not isinstance(value, dict):
            raise GameLifecycleError("large_model_exceptions must contain objects.")
        exceptions.append(
            LargeModelReservePlacementException.from_payload(
                cast(LargeModelReservePlacementExceptionPayload, value)
            )
        )
    return tuple(exceptions)


def _payload_path_witness(payload: dict[str, JsonValue], *, key: str) -> PathWitness:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


def _optional_payload_path_witness(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> PathWitness | None:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


def _payload_model_displacement_kind(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> ModelDisplacementKind:
    return model_displacement_kind_from_token(_payload_string(payload, key=key))


def _payload_transition_batch(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> BattlefieldTransitionBatch:
    value = _payload_object(payload, key=key)
    return BattlefieldTransitionBatch.from_payload(cast(BattlefieldTransitionBatchPayload, value))


def _payload_transport_overrides(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[TransportRestrictionOverride, ...]:
    values = _payload_json_array(payload, key=key)
    overrides: list[TransportRestrictionOverride] = []
    for value in values:
        if not isinstance(value, dict):
            raise GameLifecycleError("restriction_overrides must contain objects.")
        overrides.append(
            TransportRestrictionOverride.from_payload(
                cast(TransportRestrictionOverridePayload, value)
            )
        )
    return tuple(overrides)


def _payload_json_array(payload: dict[str, JsonValue], *, key: str) -> list[JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be an array: {key}.")
    return value


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


def _validate_desperate_escape_reason_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRequirementReason, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    reasons = tuple(
        desperate_escape_requirement_reason_from_token(value)
        for value in cast(tuple[object, ...], values)
    )
    if not reasons:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    seen: set[DesperateEscapeRequirementReason] = set()
    for reason in reasons:
        if reason in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(reason)
    return tuple(sorted(reasons, key=lambda reason: reason.value))


def _validate_desperate_escape_requirement_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRequirement, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    requirements: list[DesperateEscapeRequirement] = []
    seen_requirement_ids: set[str] = set()
    seen_model_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DesperateEscapeRequirement:
            raise GameLifecycleError(
                f"{field_name} must contain DesperateEscapeRequirement values."
            )
        if value.requirement_id in seen_requirement_ids:
            raise GameLifecycleError(f"{field_name} must not contain duplicate requirement IDs.")
        if value.model_instance_id in seen_model_ids:
            raise GameLifecycleError(f"{field_name} must not test the same model twice.")
        seen_requirement_ids.add(value.requirement_id)
        seen_model_ids.add(value.model_instance_id)
        requirements.append(value)
    return tuple(sorted(requirements, key=lambda requirement: requirement.requirement_id))


def _validate_desperate_escape_roll_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRoll, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    rolls: list[DesperateEscapeRoll] = []
    seen_requirement_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DesperateEscapeRoll:
            raise GameLifecycleError(f"{field_name} must contain DesperateEscapeRoll values.")
        requirement_id = value.requirement.requirement_id
        if requirement_id in seen_requirement_ids:
            raise GameLifecycleError(f"{field_name} must not contain duplicate requirements.")
        seen_requirement_ids.add(requirement_id)
        rolls.append(value)
    return tuple(sorted(rolls, key=lambda roll: roll.requirement.requirement_id))


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


def _validate_advance_roll_spec(spec: DiceRollSpec, *, unit_instance_id: str) -> None:
    if type(spec) is not DiceRollSpec:
        raise GameLifecycleError("Advance roll spec must be a DiceRollSpec.")
    if spec.expression != DiceExpression(quantity=1, sides=6):
        raise GameLifecycleError("Advance roll spec must be an unmodified D6.")
    if spec.roll_type != "advance_roll":
        raise GameLifecycleError("Advance roll spec roll_type must be advance_roll.")
    if spec.actor_id != unit_instance_id:
        raise GameLifecycleError("Advance roll spec actor_id must match unit_instance_id.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_number(field_name: str, value: object) -> float:
    if type(value) is int:
        number = float(value)
    elif type(value) is float:
        number = value
    else:
        raise GameLifecycleError(f"{field_name} must be a number.")
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
