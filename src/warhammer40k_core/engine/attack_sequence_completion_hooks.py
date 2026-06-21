from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type AttackSequenceCompletedHandler = Callable[
    ["AttackSequenceCompletedContext"],
    LifecycleStatus | None,
]


@dataclass(frozen=True, slots=True)
class AttackSequenceCompletedContext:
    state: GameState
    decisions: DecisionController
    dice_manager: DiceRollManager
    runtime_modifier_registry: RuntimeModifierRegistry
    source_phase: BattlePhase
    attack_sequence: AttackSequence
    attack_sequence_completed_event_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Attack sequence completion context requires GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "Attack sequence completion context requires DecisionController."
            )
        if type(self.dice_manager) is not DiceRollManager:
            raise GameLifecycleError("Attack sequence completion context requires dice manager.")
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "Attack sequence completion context requires runtime modifier registry."
            )
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        if type(self.attack_sequence) is not AttackSequence:
            raise GameLifecycleError("Attack sequence completion context requires sequence.")
        object.__setattr__(
            self,
            "attack_sequence_completed_event_id",
            _validate_identifier(
                "attack_sequence_completed_event_id",
                self.attack_sequence_completed_event_id,
            ),
        )


@dataclass(frozen=True, slots=True)
class AttackSequenceCompletedHookBinding:
    hook_id: str
    source_id: str
    handler: AttackSequenceCompletedHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("Attack sequence completion hook handler is not callable.")


@dataclass(frozen=True, slots=True)
class AttackSequenceCompletedHookRegistry:
    bindings: tuple[AttackSequenceCompletedHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[AttackSequenceCompletedHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[AttackSequenceCompletedHookBinding, ...]:
        return self.bindings

    def resolve_completed_sequence(
        self,
        context: AttackSequenceCompletedContext,
    ) -> LifecycleStatus | None:
        if type(context) is not AttackSequenceCompletedContext:
            raise GameLifecycleError("Attack sequence completion hooks require context.")
        for binding in self.bindings:
            status = binding.handler(context)
            if status is None:
                continue
            if type(status) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Attack sequence completion handlers must return status or None."
                )
            return status
        return None


def attack_sequence_completed_event_id(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> str:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Attack sequence completion lookup requires decisions.")
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attack sequence completion lookup requires sequence.")
    for event in reversed(decisions.event_log.records):
        if event.event_type != "attack_sequence_completed":
            continue
        payload = cast(dict[str, JsonValue], event.payload)
        if payload.get("sequence_id") == attack_sequence.sequence_id:
            return event.event_id
    raise GameLifecycleError("Completed attack sequence event is missing.")


def _validate_hook_bindings(
    value: object,
) -> tuple[AttackSequenceCompletedHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("AttackSequenceCompletedHookRegistry bindings must be a tuple.")
    bindings: list[AttackSequenceCompletedHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not AttackSequenceCompletedHookBinding:
            raise GameLifecycleError(
                "AttackSequenceCompletedHookRegistry bindings must contain "
                "AttackSequenceCompletedHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("AttackSequenceCompletedHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Attack sequence completion hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Attack sequence completion hook {field_name} must not be empty.")
    return stripped


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Attack sequence completion hook phase is invalid.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported attack sequence completion phase: {token}.") from exc
