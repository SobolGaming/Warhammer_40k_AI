from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import MovementBudgetModifierBinding


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
class MovementBudgetModifierApplication:
    modifier_id: str
    source_id: str | None
    before_inches: float
    after_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("movement modifier application modifier_id", self.modifier_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_optional_identifier(
                "movement modifier application source_id",
                self.source_id,
            ),
        )
        object.__setattr__(
            self,
            "before_inches",
            _validate_non_negative_float("before_inches", self.before_inches),
        )
        object.__setattr__(
            self,
            "after_inches",
            _validate_non_negative_float("after_inches", self.after_inches),
        )


def movement_budget_modifier_trace(
    *,
    context: MovementBudgetModifierContext,
    bindings: tuple[MovementBudgetModifierBinding, ...],
) -> tuple[float, tuple[MovementBudgetModifierApplication, ...]]:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Movement budget modifiers require a context.")
    from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
    from warhammer40k_core.engine.modifier_ignore import ignored_modifier_ids_for_context

    ignored_ids = frozenset(
        ignored_modifier_ids_for_context(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
            model_instance_id=context.model_instance_id,
            kind=ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
        )
    )
    current = context.current_movement_inches
    applications: list[MovementBudgetModifierApplication] = []
    for binding in bindings:
        if binding.modifier_id in ignored_ids:
            continue
        modified = _validate_non_negative_float(
            f"{binding.modifier_id} returned movement",
            binding.handler(replace(context, current_movement_inches=current)),
        )
        if modified != current:
            applications.append(
                MovementBudgetModifierApplication(
                    modifier_id=binding.modifier_id,
                    source_id=binding.source_id,
                    before_inches=current,
                    after_inches=modified,
                )
            )
        current = modified
    current, generic_applications = generic_rule_movement_modifier_trace(
        replace(context, current_movement_inches=current),
        ignored_modifier_ids=ignored_ids,
    )
    return current, (*applications, *generic_applications)


def generic_rule_movement_modifier_trace(
    context: MovementBudgetModifierContext,
    *,
    ignored_modifier_ids: frozenset[str] = frozenset(),
) -> tuple[float, tuple[MovementBudgetModifierApplication, ...]]:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Generic movement hooks require MovementBudgetModifierContext.")
    if type(ignored_modifier_ids) is not frozenset or any(
        type(modifier_id) is not str or not modifier_id for modifier_id in ignored_modifier_ids
    ):
        raise GameLifecycleError("Generic movement ignored modifier IDs must be a frozenset.")
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_matching_unit_effects,
        generic_rule_modifier_source_id,
        generic_rule_unit_characteristic_modifiers,
    )

    current = context.current_movement_inches
    applications: list[MovementBudgetModifierApplication] = []
    for effect_id, delta in generic_rule_unit_characteristic_modifiers(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        characteristic=Characteristic.MOVEMENT,
    ):
        if effect_id in ignored_modifier_ids:
            continue
        modified = max(0.0, current + delta)
        if modified != current:
            applications.append(
                MovementBudgetModifierApplication(
                    modifier_id=effect_id,
                    source_id=effect_id,
                    before_inches=current,
                    after_inches=modified,
                )
            )
        current = modified
    for effect in generic_rule_matching_unit_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        effect_kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
    ):
        modifier_id = effect.persisting_effect.effect_id
        if modifier_id in ignored_modifier_ids:
            continue
        modified = max(
            0.0,
            current + _required_numeric_parameter(effect.parameters, key="delta"),
        )
        if modified != current:
            applications.append(
                MovementBudgetModifierApplication(
                    modifier_id=modifier_id,
                    source_id=generic_rule_modifier_source_id(effect),
                    before_inches=current,
                    after_inches=modified,
                )
            )
        current = modified
    return current, tuple(applications)


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(int | float, value))
    if numeric < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return numeric


def _required_numeric_parameter(parameters: dict[str, JsonValue], *, key: str) -> float:
    value = parameters.get(key)
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be numeric.")
    return float(cast(int | float, value))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    return None if value is None else _validate_identifier(field_name, value)
