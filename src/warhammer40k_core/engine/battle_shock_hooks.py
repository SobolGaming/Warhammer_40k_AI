from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_test_reason_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type BattleShockModifierHandler = Callable[
    ["BattleShockModifierContext"],
    tuple[RollModifier, ...],
]
type BattleShockDiceExpressionHandler = Callable[
    ["BattleShockDiceExpressionContext"],
    DiceExpression | None,
]
type BattleShockOutcomeHandler = Callable[["BattleShockOutcomeContext"], None]
type BattleShockForcedTestHandler = Callable[
    ["BattleShockForcedTestContext"],
    tuple[str, ...],
]


@dataclass(frozen=True, slots=True)
class BattleShockForcedTestContext:
    state: GameState
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockForcedTestContext state must be a GameState.")
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockModifierContext:
    state: GameState
    request: BattleShockTestRequest
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockModifierContext state must be a GameState.")
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError(
                "BattleShockModifierContext request must be a BattleShockTestRequest."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockDiceExpressionContext:
    state: GameState
    player_id: str
    unit_instance_id: str
    reason: BattleShockTestReason
    active_player_id: str
    phase: BattlePhase
    default_expression: DiceExpression
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockDiceExpressionContext state must be a GameState.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "reason",
            battle_shock_test_reason_from_token(self.reason),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.default_expression) is not DiceExpression:
            raise GameLifecycleError(
                "BattleShockDiceExpressionContext default_expression must be a DiceExpression."
            )
        _validate_battle_shock_dice_expression(self.default_expression)
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockOutcomeContext:
    state: GameState
    decisions: DecisionController
    dice_manager: DiceRollManager
    result: BattleShockResult
    active_player_id: str
    phase: BattlePhase
    auto_passed: bool
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockOutcomeContext state must be a GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleShockOutcomeContext decisions must be a DecisionController."
            )
        if type(self.dice_manager) is not DiceRollManager:
            raise GameLifecycleError(
                "BattleShockOutcomeContext dice_manager must be a DiceRollManager."
            )
        if type(self.result) is not BattleShockResult:
            raise GameLifecycleError(
                "BattleShockOutcomeContext result must be a BattleShockResult."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.auto_passed) is not bool:
            raise GameLifecycleError("BattleShockOutcomeContext auto_passed must be a bool.")
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockHookBinding:
    hook_id: str
    source_id: str
    forced_test_handler: BattleShockForcedTestHandler | None = None
    dice_expression_handler: BattleShockDiceExpressionHandler | None = None
    modifier_handler: BattleShockModifierHandler | None = None
    outcome_handler: BattleShockOutcomeHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if (
            self.forced_test_handler is None
            and self.dice_expression_handler is None
            and self.modifier_handler is None
            and self.outcome_handler is None
        ):
            raise GameLifecycleError("BattleShockHookBinding requires at least one handler.")
        if self.forced_test_handler is not None and not callable(self.forced_test_handler):
            raise GameLifecycleError("BattleShockHookBinding forced_test_handler must be callable.")
        if self.dice_expression_handler is not None and not callable(self.dice_expression_handler):
            raise GameLifecycleError(
                "BattleShockHookBinding dice_expression_handler must be callable."
            )
        if self.modifier_handler is not None and not callable(self.modifier_handler):
            raise GameLifecycleError("BattleShockHookBinding modifier_handler must be callable.")
        if self.outcome_handler is not None and not callable(self.outcome_handler):
            raise GameLifecycleError("BattleShockHookBinding outcome_handler must be callable.")


@dataclass(frozen=True, slots=True)
class BattleShockHookRegistry:
    bindings: tuple[BattleShockHookBinding, ...]

    def __post_init__(self) -> None:
        bindings = _validate_hook_bindings(self.bindings)
        object.__setattr__(self, "bindings", bindings)

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[BattleShockHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[BattleShockHookBinding, ...]:
        return self.bindings

    def modifiers_for(
        self,
        context: BattleShockModifierContext,
    ) -> tuple[RollModifier, ...]:
        if type(context) is not BattleShockModifierContext:
            raise GameLifecycleError("Battle-shock modifier hooks require a context.")
        modifiers: list[RollModifier] = []
        for binding in self.bindings:
            if binding.modifier_handler is None:
                continue
            handler_modifiers = binding.modifier_handler(context)
            modifiers.extend(_validate_roll_modifier_tuple(handler_modifiers))
        _validate_unique_modifier_ids(tuple(modifiers))
        return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))

    def dice_expression_for(
        self,
        context: BattleShockDiceExpressionContext,
    ) -> DiceExpression:
        if type(context) is not BattleShockDiceExpressionContext:
            raise GameLifecycleError("Battle-shock dice-expression hooks require a context.")
        expression = context.default_expression
        override_source_ids: list[str] = []
        for binding in self.bindings:
            if binding.dice_expression_handler is None:
                continue
            candidate = binding.dice_expression_handler(context)
            if candidate is None:
                continue
            if type(candidate) is not DiceExpression:
                raise GameLifecycleError(
                    "Battle-shock dice-expression handlers must return DiceExpression or None."
                )
            _validate_battle_shock_dice_expression(candidate)
            if override_source_ids and candidate != expression:
                raise GameLifecycleError(
                    "Battle-shock dice-expression hooks produced conflicting overrides."
                )
            expression = candidate
            override_source_ids.append(binding.source_id)
        return expression

    def forced_below_starting_strength_unit_ids(
        self,
        context: BattleShockForcedTestContext,
    ) -> tuple[str, ...]:
        if type(context) is not BattleShockForcedTestContext:
            raise GameLifecycleError("Battle-shock forced-test hooks require a context.")
        forced_ids: set[str] = set()
        for binding in self.bindings:
            if binding.forced_test_handler is None:
                continue
            handler_ids = binding.forced_test_handler(context)
            forced_ids.update(
                _validate_identifier_tuple(
                    "forced_below_starting_strength_unit_ids",
                    handler_ids,
                )
            )
        return tuple(sorted(forced_ids))

    def resolve_outcomes(self, context: BattleShockOutcomeContext) -> None:
        if type(context) is not BattleShockOutcomeContext:
            raise GameLifecycleError("Battle-shock outcome hooks require a context.")
        for binding in self.bindings:
            if binding.outcome_handler is None:
                continue
            binding.outcome_handler(context)


def _validate_hook_bindings(value: object) -> tuple[BattleShockHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("BattleShockHookRegistry bindings must be a tuple.")
    bindings: list[BattleShockHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not BattleShockHookBinding:
            raise GameLifecycleError(
                "BattleShockHookRegistry bindings must contain BattleShockHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("BattleShockHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_roll_modifier_tuple(value: object) -> tuple[RollModifier, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Battle-shock modifier handlers must return a tuple.")
    modifiers: list[RollModifier] = []
    for modifier in cast(tuple[object, ...], value):
        if type(modifier) is not RollModifier:
            raise GameLifecycleError(
                "Battle-shock modifier handlers must return RollModifier values."
            )
        modifiers.append(modifier)
    return tuple(modifiers)


def _validate_unique_modifier_ids(modifiers: tuple[RollModifier, ...]) -> None:
    seen: set[str] = set()
    for modifier in modifiers:
        if modifier.modifier_id in seen:
            raise GameLifecycleError("Battle-shock modifier IDs must be unique.")
        seen.add(modifier.modifier_id)


def _validate_battle_shock_dice_expression(expression: DiceExpression) -> None:
    if expression not in {
        DiceExpression(quantity=2, sides=6),
        DiceExpression(quantity=3, sides=6),
    }:
        raise GameLifecycleError("Battle-shock dice expression must be 2D6 or 3D6.")


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Battle-shock hook {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} value", item)
        if identifier in seen:
            raise GameLifecycleError(f"Battle-shock hook {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Battle-shock hook phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Battle-shock hook phase: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Battle-shock hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Battle-shock hook {field_name} must not be empty.")
    return stripped
