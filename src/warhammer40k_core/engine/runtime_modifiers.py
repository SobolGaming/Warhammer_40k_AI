from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.saves import SaveOption

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type UnitCharacteristicModifierHandler = Callable[
    ["UnitCharacteristicModifierContext"],
    int,
]
type HitRollModifierHandler = Callable[["HitRollModifierContext"], int]
type SaveOptionModifierHandler = Callable[
    ["SaveOptionModifierContext"],
    tuple[SaveOption, ...],
]
type MovementBudgetModifierHandler = Callable[["MovementBudgetModifierContext"], float]
type ObjectiveControlModifierHandler = Callable[["ObjectiveControlModifierContext"], int]


@dataclass(frozen=True, slots=True)
class UnitCharacteristicModifierContext:
    state: GameState
    unit_instance_id: str
    characteristic: Characteristic
    base_value: int
    current_value: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Unit characteristic modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "characteristic",
            _characteristic_from_token(self.characteristic),
        )
        object.__setattr__(
            self,
            "base_value",
            _validate_non_negative_int("base_value", self.base_value),
        )
        object.__setattr__(
            self,
            "current_value",
            _validate_non_negative_int("current_value", self.current_value),
        )


@dataclass(frozen=True, slots=True)
class HitRollModifierContext:
    state: GameState
    attacker_model_instance_id: str
    source_phase: BattlePhase

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Hit roll modifier state must be GameState.")
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier("attacker_model_instance_id", self.attacker_model_instance_id),
        )
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))


@dataclass(frozen=True, slots=True)
class SaveOptionModifierContext:
    state: GameState
    target_unit_instance_id: str
    save_options: tuple[SaveOption, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Save option modifier state must be GameState.")
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "save_options",
            _validate_save_option_tuple("save_options", self.save_options),
        )


@dataclass(frozen=True, slots=True)
class MovementBudgetModifierContext:
    state: GameState
    unit_instance_id: str
    model_instance_id: str
    base_movement_inches: float
    current_movement_inches: float

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Movement budget modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "base_movement_inches",
            _validate_non_negative_float("base_movement_inches", self.base_movement_inches),
        )
        object.__setattr__(
            self,
            "current_movement_inches",
            _validate_non_negative_float("current_movement_inches", self.current_movement_inches),
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlModifierContext:
    state: GameState
    unit_instance_id: str
    model_instance_id: str
    base_objective_control: int
    current_objective_control: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Objective Control modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "base_objective_control",
            _validate_non_negative_int("base_objective_control", self.base_objective_control),
        )
        object.__setattr__(
            self,
            "current_objective_control",
            _validate_non_negative_int(
                "current_objective_control",
                self.current_objective_control,
            ),
        )


@dataclass(frozen=True, slots=True)
class UnitCharacteristicModifierBinding:
    modifier_id: str
    source_id: str
    handler: UnitCharacteristicModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="unit characteristic modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class HitRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: HitRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Hit roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class SaveOptionModifierBinding:
    modifier_id: str
    source_id: str
    handler: SaveOptionModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="save option modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class MovementBudgetModifierBinding:
    modifier_id: str
    source_id: str
    handler: MovementBudgetModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="movement budget modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlModifierBinding:
    modifier_id: str
    source_id: str
    handler: ObjectiveControlModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Objective Control modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class RuntimeModifierRegistry:
    unit_characteristic_modifier_bindings: tuple[UnitCharacteristicModifierBinding, ...] = ()
    hit_roll_modifier_bindings: tuple[HitRollModifierBinding, ...] = ()
    save_option_modifier_bindings: tuple[SaveOptionModifierBinding, ...] = ()
    movement_budget_modifier_bindings: tuple[MovementBudgetModifierBinding, ...] = ()
    objective_control_modifier_bindings: tuple[ObjectiveControlModifierBinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_characteristic_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry unit_characteristic_modifier_bindings",
                self.unit_characteristic_modifier_bindings,
                UnitCharacteristicModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "hit_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry hit_roll_modifier_bindings",
                self.hit_roll_modifier_bindings,
                HitRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "save_option_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry save_option_modifier_bindings",
                self.save_option_modifier_bindings,
                SaveOptionModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "movement_budget_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry movement_budget_modifier_bindings",
                self.movement_budget_modifier_bindings,
                MovementBudgetModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry objective_control_modifier_bindings",
                self.objective_control_modifier_bindings,
                ObjectiveControlModifierBinding,
            ),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @classmethod
    def from_bindings(
        cls,
        *,
        unit_characteristic_modifier_bindings: tuple[
            UnitCharacteristicModifierBinding,
            ...,
        ] = (),
        hit_roll_modifier_bindings: tuple[HitRollModifierBinding, ...] = (),
        save_option_modifier_bindings: tuple[SaveOptionModifierBinding, ...] = (),
        movement_budget_modifier_bindings: tuple[MovementBudgetModifierBinding, ...] = (),
        objective_control_modifier_bindings: tuple[ObjectiveControlModifierBinding, ...] = (),
    ) -> Self:
        return cls(
            unit_characteristic_modifier_bindings=unit_characteristic_modifier_bindings,
            hit_roll_modifier_bindings=hit_roll_modifier_bindings,
            save_option_modifier_bindings=save_option_modifier_bindings,
            movement_budget_modifier_bindings=movement_budget_modifier_bindings,
            objective_control_modifier_bindings=objective_control_modifier_bindings,
        )

    def all_unit_characteristic_bindings(self) -> tuple[UnitCharacteristicModifierBinding, ...]:
        return self.unit_characteristic_modifier_bindings

    def all_hit_roll_bindings(self) -> tuple[HitRollModifierBinding, ...]:
        return self.hit_roll_modifier_bindings

    def all_save_option_bindings(self) -> tuple[SaveOptionModifierBinding, ...]:
        return self.save_option_modifier_bindings

    def all_movement_budget_bindings(self) -> tuple[MovementBudgetModifierBinding, ...]:
        return self.movement_budget_modifier_bindings

    def all_objective_control_bindings(self) -> tuple[ObjectiveControlModifierBinding, ...]:
        return self.objective_control_modifier_bindings

    def modified_unit_characteristic(self, context: UnitCharacteristicModifierContext) -> int:
        if type(context) is not UnitCharacteristicModifierContext:
            raise GameLifecycleError("Unit characteristic modifiers require a context.")
        current = context.current_value
        for binding in self.unit_characteristic_modifier_bindings:
            current = _validate_non_negative_int(
                f"{binding.modifier_id} returned value",
                binding.handler(replace(context, current_value=current)),
            )
        return current

    def hit_roll_modifier(self, context: HitRollModifierContext) -> int:
        if type(context) is not HitRollModifierContext:
            raise GameLifecycleError("Hit roll modifiers require a context.")
        total = 0
        for binding in self.hit_roll_modifier_bindings:
            total += _validate_int(
                f"{binding.modifier_id} returned modifier",
                binding.handler(context),
            )
        return total

    def modified_save_options(
        self,
        context: SaveOptionModifierContext,
    ) -> tuple[SaveOption, ...]:
        if type(context) is not SaveOptionModifierContext:
            raise GameLifecycleError("Save option modifiers require a context.")
        current = context.save_options
        for binding in self.save_option_modifier_bindings:
            current = _validate_save_option_tuple(
                f"{binding.modifier_id} returned save_options",
                binding.handler(replace(context, save_options=current)),
            )
        return current

    def modified_movement_inches(self, context: MovementBudgetModifierContext) -> float:
        if type(context) is not MovementBudgetModifierContext:
            raise GameLifecycleError("Movement budget modifiers require a context.")
        current = context.current_movement_inches
        for binding in self.movement_budget_modifier_bindings:
            current = _validate_non_negative_float(
                f"{binding.modifier_id} returned movement",
                binding.handler(replace(context, current_movement_inches=current)),
            )
        return current

    def modified_objective_control(self, context: ObjectiveControlModifierContext) -> int:
        if type(context) is not ObjectiveControlModifierContext:
            raise GameLifecycleError("Objective Control modifiers require a context.")
        current = context.current_objective_control
        for binding in self.objective_control_modifier_bindings:
            current = _validate_non_negative_int(
                f"{binding.modifier_id} returned Objective Control",
                binding.handler(replace(context, current_objective_control=current)),
            )
        return current


def _validate_bindings[T](
    field_name: str,
    value: object,
    binding_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    bindings: list[T] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not binding_type:
            raise GameLifecycleError(f"{field_name} must contain {binding_type.__name__}.")
        modifier_id = cast(
            UnitCharacteristicModifierBinding
            | HitRollModifierBinding
            | SaveOptionModifierBinding
            | MovementBudgetModifierBinding
            | ObjectiveControlModifierBinding,
            binding,
        ).modifier_id
        if modifier_id in seen:
            raise GameLifecycleError(f"{field_name} modifier IDs must be unique.")
        seen.add(modifier_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=_modifier_id_for_binding))


def _modifier_id_for_binding(binding: object) -> str:
    if type(binding) in {
        UnitCharacteristicModifierBinding,
        HitRollModifierBinding,
        SaveOptionModifierBinding,
        MovementBudgetModifierBinding,
        ObjectiveControlModifierBinding,
    }:
        return cast(
            UnitCharacteristicModifierBinding
            | HitRollModifierBinding
            | SaveOptionModifierBinding
            | MovementBudgetModifierBinding
            | ObjectiveControlModifierBinding,
            binding,
        ).modifier_id
    raise GameLifecycleError("Runtime modifier binding has an unsupported type.")


def _validate_modifier_binding(
    *,
    field_prefix: str,
    modifier_id: object,
    source_id: object,
    handler: object,
) -> None:
    _validate_identifier(f"{field_prefix} modifier_id", modifier_id)
    _validate_identifier(f"{field_prefix} source_id", source_id)
    if not callable(handler):
        raise GameLifecycleError(f"{field_prefix} handler must be callable.")


def _validate_save_option_tuple(field_name: str, value: object) -> tuple[SaveOption, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    options: list[SaveOption] = []
    for option in cast(tuple[object, ...], value):
        if type(option) is not SaveOption:
            raise GameLifecycleError(f"{field_name} must contain SaveOption values.")
        options.append(option)
    return tuple(options)


def _characteristic_from_token(token: object) -> Characteristic:
    if type(token) is Characteristic:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Runtime modifier characteristic must be a Characteristic.")
    try:
        return Characteristic(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported runtime modifier characteristic: {token}.") from exc


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Runtime modifier BattlePhase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported runtime modifier BattlePhase: {token}.") from exc


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(int | float, value))
    if numeric < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return numeric


def _validate_non_negative_int(field_name: str, value: object) -> int:
    integer = _validate_int(field_name, value)
    if integer < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return integer


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
