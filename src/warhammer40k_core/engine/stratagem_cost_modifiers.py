from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierError,
    ModifierOperation,
    ModifierTerm,
    resolve_stratagem_cost,
)
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


type StratagemCostModifierHandler = Callable[["StratagemCostModifierContext"], ModifierTerm | None]


@dataclass(frozen=True, slots=True)
class StratagemCostModificationResult:
    command_point_cost: int
    modifier_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    increased_modifier_ids: tuple[str, ...] = ()

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
        object.__setattr__(
            self,
            "increased_modifier_ids",
            _validate_identifier_tuple(
                "increased_modifier_ids",
                self.increased_modifier_ids,
            ),
        )
        if not set(self.increased_modifier_ids) <= set(self.modifier_ids):
            raise GameLifecycleError(
                "Stratagem cost increased_modifier_ids must be applied modifier IDs."
            )


@dataclass(frozen=True, slots=True)
class StratagemCostModifierContext:
    state: GameState
    definition: StratagemDefinition
    eligibility_context: StratagemEligibilityContext
    target_binding: StratagemTargetBinding | None
    effect_selection: JsonValue
    base_command_point_cost: int
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
    non_cumulative_increase: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("modifier_id", self.modifier_id),
        )
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if type(self.non_cumulative_increase) is not bool:
            raise GameLifecycleError("Stratagem non_cumulative_increase must be bool.")
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
        # Evaluate each source once against the same use, without a running price.
        selected: list[tuple[StratagemCostModifierBinding, ModifierTerm]] = []
        for binding in self.bindings:
            term = binding.handler(context)
            if term is None:
                continue
            if type(term) is not ModifierTerm:
                raise GameLifecycleError(
                    "Stratagem cost modifier must return ModifierTerm or None."
                )
            if binding.non_cumulative_increase and (
                term.operation is not ModifierOperation.ADD or term.operand <= 0
            ):
                raise GameLifecycleError(
                    "Non-cumulative cost increase requires a positive addition."
                )
            selected.append((binding, term))
        # Explicit non-cumulative increases compete with the total ordinary increase.
        # All accepted sources remain commitments, including capped/non-stacking ones.
        ordinary_increase = sum(
            term.operand
            for binding, term in selected
            if not binding.non_cumulative_increase
            and term.operation is ModifierOperation.ADD
            and term.operand > 0
        )
        non_cumulative = [
            (binding, term) for binding, term in selected if binding.non_cumulative_increase
        ]
        strongest = max(non_cumulative, key=lambda item: item[1].operand, default=None)
        use_non_cumulative = strongest is not None and strongest[1].operand > ordinary_increase
        numeric: list[Modifier] = []
        for binding, term in selected:
            if binding.non_cumulative_increase:
                if not use_non_cumulative or (binding, term) != strongest:
                    continue
            elif (
                use_non_cumulative and term.operation is ModifierOperation.ADD and term.operand > 0
            ):
                continue
            numeric.append(term.bind(modifier_id=binding.modifier_id, source_id=binding.source_id))
        try:
            final, steps = resolve_stratagem_cost(context.base_command_point_cost, tuple(numeric))
        except ModifierError as exc:
            raise GameLifecycleError("Invalid Stratagem cost operations.") from exc
        return StratagemCostModificationResult(
            command_point_cost=final,
            modifier_ids=tuple(binding.modifier_id for binding, _ in selected),
            source_ids=tuple(binding.source_id for binding, _ in selected),
            increased_modifier_ids=tuple(
                step.modifier.modifier_id for step in steps if step.after > step.before
            ),
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
