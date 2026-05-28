from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, Self, TypedDict, cast

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
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    geometry_model_for_placement,
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
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    MovementRollbackRecordPayload,
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_MOVEMENT_UNIT_DECISION_TYPE = "select_movement_unit"
SELECT_MOVEMENT_ACTION_DECISION_TYPE = "select_movement_action"
SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE = "select_desperate_escape_model"


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
    ) -> UnitPlacement:
        destroyed_ids = set(_validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids))
        return self.attempted_placement.with_model_placements(
            tuple(
                placement
                for placement in self.attempted_placement.model_placements
                if placement.model_instance_id not in destroyed_ids
            )
        )

    def selected_payload_drift_code(self, payload: dict[str, JsonValue]) -> str | None:
        selected_payload = _validate_json_object("Fall Back selected payload", payload)
        if selected_payload.get("witness") != self.witness.to_payload():
            return "fall_back_witness_drift"
        expected_model_movements = self.movement_payload["model_movements"]
        if selected_payload.get("model_movements") != expected_model_movements:
            return "fall_back_model_movement_witness_drift"
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
            )
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
            battle_round=state.battle_round,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
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
    _complete_movement_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.ADVANCE,
        witness=resolution.witness,
        movement_payload=resolution.movement_payload,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        transition_batch=transition_batch,
    )
    return None


def _apply_desperate_escape_model_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
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
    )


def _apply_fall_back_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_placement: UnitPlacement,
    fall_back_result: FallBackActionResult,
    destroyed_model_ids: tuple[str, ...],
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
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
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            desperate_escape_rolls=fall_back_result.desperate_escape_rolls,
        )
    )
    _complete_movement_activation(
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
    )
    return None


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
    battle_round: int = 1,
    battle_shocked_unit_ids: tuple[str, ...] = (),
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
        if action is MovementPhaseActionKind.FALL_BACK:
            fall_back_resolution = resolve_fall_back_move(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
                path_witness=None,
                battle_round=battle_round,
                battle_shocked_unit_ids=battle_shocked_unit_ids,
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
    witness = (
        _default_move_witness(
            scenario=scenario,
            unit_placement=unit_placement,
            movement_bonus_inches=movement_bonus_inches,
        )
        if path_witness is None
        else path_witness
    )
    _validate_move_witness_matches_unit(
        witness=witness,
        unit_placement=unit_placement,
        action_label=action_label,
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
        base_movement_inches = _model_movement_inches(model)
        movement_inches = float(base_movement_inches + movement_bonus_inches)
        max_movement_inches = max(max_movement_inches, movement_inches)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=unit.keywords,
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
                    "base_movement_inches": base_movement_inches,
                    "movement_bonus_inches": movement_bonus_inches,
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
            displacement_kind=displacement_kind,
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
    movement_bonus_inches: int,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = _model_movement_inches(model) + movement_bonus_inches
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                _translated_pose(placement.pose, movement_inches=movement_inches),
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


def _payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be an object: {key}.")
    return value


def _payload_path_witness(payload: dict[str, JsonValue], *, key: str) -> PathWitness:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


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
