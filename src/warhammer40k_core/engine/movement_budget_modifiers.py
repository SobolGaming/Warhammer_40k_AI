from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    CharacteristicValueKind,
)
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierStack,
    resolve_characteristic_value,
    resolve_distance_deltas,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import MovementBudgetModifierBinding


@dataclass(frozen=True, slots=True)
class MovementBudgetModifierContext:
    state: GameState
    unit_instance_id: str
    model_instance_id: str
    movement: CharacteristicValue

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
        if (
            type(self.movement) is not CharacteristicValue
            or self.movement.characteristic is not Characteristic.MOVEMENT
        ):
            raise GameLifecycleError("Movement modifiers require a typed Movement characteristic.")


def model_movement_characteristic(model: ModelInstance) -> CharacteristicValue:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Movement model must be a ModelInstance.")
    for value in model.characteristics:
        if value.characteristic is Characteristic.MOVEMENT:
            return value
    raise GameLifecycleError("Normal Move requires a Movement characteristic.")


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
            _validate_finite_float("before_inches", self.before_inches),
        )
        object.__setattr__(
            self,
            "after_inches",
            _validate_finite_float("after_inches", self.after_inches),
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
    return _resolve_movement(context, bindings=bindings, ignored_ids=ignored_ids)


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
    return _resolve_movement(context, bindings=(), ignored_ids=ignored_modifier_ids)


def _resolve_movement(
    context: MovementBudgetModifierContext,
    *,
    bindings: tuple[MovementBudgetModifierBinding, ...],
    ignored_ids: frozenset[str],
) -> tuple[float, tuple[MovementBudgetModifierApplication, ...]]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_characteristic_operations,
        generic_rule_matching_unit_effects,
        generic_rule_modifier_source_id,
    )
    from warhammer40k_core.engine.runtime_characteristic_modifiers import bind_characteristic_terms

    modifiers: list[Modifier] = []
    binding_ids: dict[str, str] = {}
    for binding in bindings:
        if binding.modifier_id in ignored_ids:
            continue
        terms = bind_characteristic_terms(
            modifier_id=binding.modifier_id,
            source_id=binding.source_id,
            characteristic=Characteristic.MOVEMENT,
            terms=binding.handler(context),
        )
        modifiers.extend(terms)
        binding_ids.update((term.modifier_id, binding.modifier_id) for term in terms)
    modifiers.extend(
        modifier
        for modifier in generic_rule_characteristic_operations(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
            characteristic=Characteristic.MOVEMENT,
        )
        if modifier.modifier_id not in ignored_ids
    )
    resolved = resolve_characteristic_value(
        replace(context.movement, raw=context.movement.final),
        modifiers,
        target_id=context.model_instance_id,
    )
    applications: list[MovementBudgetModifierApplication] = []
    if (
        context.movement.is_numeric
        and context.movement.value_kind is not CharacteristicValueKind.REPLACEMENT_ZERO
    ):
        stack = ModifierStack(
            characteristic=Characteristic.MOVEMENT,
            raw_value=context.movement.final,
            modifiers=tuple(modifiers),
            target_id=context.model_instance_id,
        )
        if resolved.is_numeric:
            for step in stack.arithmetic_steps():
                if step.before != step.after:
                    applications.append(
                        MovementBudgetModifierApplication(
                            modifier_id=binding_ids.get(
                                step.modifier.modifier_id, step.modifier.modifier_id
                            ),
                            source_id=step.modifier.source_id,
                            before_inches=float(step.before),
                            after_inches=float(step.after),
                        )
                    )
        else:
            replacement = stack.applicable_modifiers()[0]
            applications.append(
                MovementBudgetModifierApplication(
                    modifier_id=binding_ids.get(replacement.modifier_id, replacement.modifier_id),
                    source_id=replacement.source_id,
                    before_inches=float(context.movement.final),
                    after_inches=0.0,
                )
            )
    if not resolved.is_numeric or resolved.value_kind is CharacteristicValueKind.REPLACEMENT_ZERO:
        return float(resolved.final), tuple(applications)
    distance_effects = tuple(
        effect
        for effect in generic_rule_matching_unit_effects(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
            effect_kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
        )
        if effect.persisting_effect.effect_id not in ignored_ids
    )
    sources = {
        effect.persisting_effect.effect_id: generic_rule_modifier_source_id(effect)
        for effect in distance_effects
    }
    final, distance_steps = resolve_distance_deltas(
        float(resolved.final),
        tuple(
            (
                effect.persisting_effect.effect_id,
                _required_numeric_parameter(effect.parameters, key="delta"),
            )
            for effect in distance_effects
        ),
    )
    applications.extend(
        MovementBudgetModifierApplication(
            modifier_id=modifier_id,
            source_id=sources[modifier_id],
            before_inches=before,
            after_inches=after,
        )
        for modifier_id, before, after in distance_steps
    )
    return final, tuple(applications)


def _validate_finite_float(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(int | float, value))
    if not isfinite(numeric):
        raise GameLifecycleError(f"{field_name} must be finite.")
    return numeric


def _required_numeric_parameter(parameters: dict[str, JsonValue], *, key: str) -> float:
    value = parameters.get(key)
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be numeric.")
    return float(cast(int | float, value))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    return None if value is None else _validate_identifier(field_name, value)
