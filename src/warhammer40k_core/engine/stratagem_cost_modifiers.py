from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import (
        StratagemDefinition,
        StratagemEligibilityContext,
        StratagemTargetBinding,
    )


type StratagemCostModifierHandler = Callable[["StratagemCostModifierContext"], int]


@dataclass(frozen=True, slots=True)
class StratagemCostModificationResult:
    command_point_cost: int
    modifier_ids: tuple[str, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int("command_point_cost", self.command_point_cost),
        )
        object.__setattr__(
            self,
            "modifier_ids",
            _validate_identifier_tuple("modifier_ids", self.modifier_ids),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )


@dataclass(frozen=True, slots=True)
class StratagemCostModifierContext:
    state: GameState
    definition: StratagemDefinition
    eligibility_context: StratagemEligibilityContext
    target_binding: StratagemTargetBinding | None
    effect_selection: JsonValue
    base_command_point_cost: int
    current_command_point_cost: int
    decisions: DecisionController | None = None
    source_decision_request_id: str | None = None
    source_decision_result_id: str | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.decision_controller import DecisionController
        from warhammer40k_core.engine.game_state import GameState
        from warhammer40k_core.engine.stratagems import (
            StratagemDefinition,
            StratagemEligibilityContext,
            StratagemTargetBinding,
        )

        if type(self.state) is not GameState:
            raise GameLifecycleError("Stratagem cost modifier context requires GameState.")
        if type(self.definition) is not StratagemDefinition:
            raise GameLifecycleError(
                "Stratagem cost modifier context requires StratagemDefinition."
            )
        if type(self.eligibility_context) is not StratagemEligibilityContext:
            raise GameLifecycleError(
                "Stratagem cost modifier context requires eligibility context."
            )
        if self.target_binding is not None and type(self.target_binding) is not (
            StratagemTargetBinding
        ):
            raise GameLifecycleError(
                "Stratagem cost modifier target_binding must be StratagemTargetBinding."
            )
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))
        object.__setattr__(
            self,
            "base_command_point_cost",
            _validate_non_negative_int(
                "base_command_point_cost",
                self.base_command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "current_command_point_cost",
            _validate_non_negative_int(
                "current_command_point_cost",
                self.current_command_point_cost,
            ),
        )
        if self.decisions is not None and type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "Stratagem cost modifier decisions must be DecisionController."
            )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_optional_identifier(
                "source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_optional_identifier(
                "source_decision_result_id",
                self.source_decision_result_id,
            ),
        )


@dataclass(frozen=True, slots=True)
class StratagemCostModifierBinding:
    modifier_id: str
    source_id: str
    handler: StratagemCostModifierHandler

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("modifier_id", self.modifier_id),
        )
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("Stratagem cost modifier handler must be callable.")


@dataclass(frozen=True, slots=True)
class StratagemCostModifierRegistry:
    bindings: tuple[StratagemCostModifierBinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[StratagemCostModifierBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[StratagemCostModifierBinding, ...]:
        return self.bindings

    def modified_command_point_cost(self, context: StratagemCostModifierContext) -> int:
        return self.modified_command_point_cost_with_sources(context).command_point_cost

    def modified_command_point_cost_with_sources(
        self,
        context: StratagemCostModifierContext,
    ) -> StratagemCostModificationResult:
        if type(context) is not StratagemCostModifierContext:
            raise GameLifecycleError("Stratagem cost modifiers require a context.")
        current = context.current_command_point_cost
        modifier_ids: list[str] = []
        source_ids: list[str] = []
        for binding in self.bindings:
            raw_modified = _validate_int(
                f"{binding.modifier_id} returned command point cost",
                binding.handler(replace(context, current_command_point_cost=current)),
            )
            modified = max(0, raw_modified)
            if modified != current:
                modifier_ids.append(binding.modifier_id)
                source_ids.append(binding.source_id)
            current = modified
        return StratagemCostModificationResult(
            command_point_cost=current,
            modifier_ids=tuple(modifier_ids),
            source_ids=tuple(source_ids),
        )


def _validate_bindings(value: object) -> tuple[StratagemCostModifierBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Stratagem cost modifier bindings must be a tuple.")
    bindings: list[StratagemCostModifierBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not StratagemCostModifierBinding:
            raise GameLifecycleError("Stratagem cost modifier registry requires modifier bindings.")
        if binding.modifier_id in seen:
            raise GameLifecycleError("Stratagem cost modifier IDs must be unique.")
        seen.add(binding.modifier_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.modifier_id))


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifiers.append(_validate_identifier(f"{field_name} entry", value))
    return tuple(sorted(dict.fromkeys(identifiers)))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
