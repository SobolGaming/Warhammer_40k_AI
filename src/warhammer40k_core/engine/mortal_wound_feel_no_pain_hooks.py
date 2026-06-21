from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type MortalWoundFeelNoPainContinuationHandler = Callable[
    ["MortalWoundFeelNoPainContinuationContext"],
    LifecycleStatus | None,
]


@dataclass(frozen=True, slots=True)
class MortalWoundFeelNoPainContinuationContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    source_context: JsonValue
    dice_manager: DiceRollManager
    runtime_modifier_registry: RuntimeModifierRegistry

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Mortal wound FNP continuation requires GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("Mortal wound FNP continuation requires DecisionController.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("Mortal wound FNP continuation requires request.")
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("Mortal wound FNP continuation requires result.")
        object.__setattr__(
            self,
            "source_context",
            _validate_source_context(self.source_context),
        )
        if type(self.dice_manager) is not DiceRollManager:
            raise GameLifecycleError("Mortal wound FNP continuation requires dice manager.")
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "Mortal wound FNP continuation requires runtime modifier registry."
            )


@dataclass(frozen=True, slots=True)
class MortalWoundFeelNoPainContinuationHookBinding:
    hook_id: str
    source_id: str
    source_kind: str
    handler: MortalWoundFeelNoPainContinuationHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "source_kind",
            _validate_identifier("source_kind", self.source_kind),
        )
        if not callable(self.handler):
            raise GameLifecycleError("Mortal wound FNP continuation handler is not callable.")


@dataclass(frozen=True, slots=True)
class MortalWoundFeelNoPainContinuationHookRegistry:
    bindings: tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[MortalWoundFeelNoPainContinuationHookBinding, ...],
    ) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
        return self.bindings

    def handles_source_context(self, source_context: JsonValue) -> bool:
        source_kind = _source_kind_from_context(source_context)
        return any(binding.source_kind == source_kind for binding in self.bindings)

    def apply_decision(
        self,
        context: MortalWoundFeelNoPainContinuationContext,
    ) -> LifecycleStatus | None:
        if type(context) is not MortalWoundFeelNoPainContinuationContext:
            raise GameLifecycleError("Mortal wound FNP continuation requires context.")
        source_kind = _source_kind_from_context(context.source_context)
        for binding in self.bindings:
            if binding.source_kind != source_kind:
                continue
            status = binding.handler(context)
            if status is not None and type(status) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Mortal wound FNP continuation handlers must return status or None."
                )
            return status
        raise GameLifecycleError("Mortal wound FNP continuation source kind is not registered.")


def _validate_hook_bindings(
    value: object,
) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "MortalWoundFeelNoPainContinuationHookRegistry bindings must be a tuple."
        )
    bindings: list[MortalWoundFeelNoPainContinuationHookBinding] = []
    seen_hook_ids: set[str] = set()
    seen_source_kinds: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not MortalWoundFeelNoPainContinuationHookBinding:
            raise GameLifecycleError(
                "MortalWoundFeelNoPainContinuationHookRegistry bindings must contain "
                "MortalWoundFeelNoPainContinuationHookBinding values."
            )
        if binding.hook_id in seen_hook_ids:
            raise GameLifecycleError(
                "MortalWoundFeelNoPainContinuationHookRegistry hook IDs must be unique."
            )
        if binding.source_kind in seen_source_kinds:
            raise GameLifecycleError(
                "MortalWoundFeelNoPainContinuationHookRegistry source kinds must be unique."
            )
        seen_hook_ids.add(binding.hook_id)
        seen_source_kinds.add(binding.source_kind)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_source_context(value: JsonValue) -> JsonValue:
    context = validate_json_value(value)
    _source_kind_from_context(context)
    return context


def _source_kind_from_context(value: JsonValue) -> str:
    if not isinstance(value, dict):
        raise GameLifecycleError("Mortal wound FNP source context must be an object.")
    source_kind = value.get("source_kind")
    if type(source_kind) is not str or not source_kind.strip():
        raise GameLifecycleError("Mortal wound FNP source context is missing source_kind.")
    return source_kind.strip()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Mortal wound FNP hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Mortal wound FNP hook {field_name} must not be empty.")
    return stripped
