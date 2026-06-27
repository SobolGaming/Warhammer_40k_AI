from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionHookRegistry,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE = (
    "select_faction_rule_shooting_phase_start_option"
)

type ShootingPhaseStartRequestHandler = Callable[
    ["ShootingPhaseStartRequestContext"],
    DecisionRequest | None,
]
type ShootingPhaseStartResultHandler = Callable[
    ["ShootingPhaseStartResultContext"],
    bool | LifecycleStatus,
]


@dataclass(frozen=True, slots=True)
class ShootingPhaseStartRequestContext:
    state: GameState
    decisions: DecisionController
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ShootingPhaseStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "ShootingPhaseStartRequestContext decisions must be DecisionController."
            )
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError(
                "ShootingPhaseStartRequestContext ruleset_descriptor must be RulesetDescriptor."
            )
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError(
                "ShootingPhaseStartRequestContext army_catalog must be ArmyCatalog."
            )
        if (
            type(self.shooting_target_restriction_hooks)
            is not ShootingTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseStartRequestContext shooting_target_restriction_hooks must be a "
                "registry."
            )
        _validate_shooting_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class ShootingPhaseStartResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ShootingPhaseStartResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext decisions must be DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext result must be DecisionResult."
            )
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext ruleset_descriptor must be RulesetDescriptor."
            )
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext army_catalog must be ArmyCatalog."
            )
        if (
            type(self.shooting_target_restriction_hooks)
            is not ShootingTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext shooting_target_restriction_hooks must be a "
                "registry."
            )
        if (
            self.request.decision_type
            != SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
        ):
            raise GameLifecycleError("ShootingPhaseStartResultContext request decision_type drift.")
        _validate_shooting_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class ShootingPhaseStartHookBinding:
    hook_id: str
    source_id: str
    request_handler: ShootingPhaseStartRequestHandler | None = None
    result_handler: ShootingPhaseStartResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("ShootingPhaseStartHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "ShootingPhaseStartHookBinding request_handler must be callable."
            )
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError(
                "ShootingPhaseStartHookBinding result_handler must be callable."
            )


@dataclass(frozen=True, slots=True)
class ShootingPhaseStartHookRegistry:
    bindings: tuple[ShootingPhaseStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[ShootingPhaseStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[ShootingPhaseStartHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: ShootingPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not ShootingPhaseStartRequestContext:
            raise GameLifecycleError("Shooting-phase start request hooks require context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Shooting-phase start request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError(
                "Shooting-phase start hooks produced multiple simultaneous requests."
            )
        if not requests:
            return None
        return requests[0]

    def apply_result(self, context: ShootingPhaseStartResultContext) -> bool | LifecycleStatus:
        if type(context) is not ShootingPhaseStartResultContext:
            raise GameLifecycleError("Shooting-phase start result hooks require context.")
        handled_results: list[bool | LifecycleStatus] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool and type(handled) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Shooting-phase start result handlers must return bool or status."
                )
            if handled:
                handled_results.append(handled)
        if len(handled_results) > 1:
            raise GameLifecycleError("Shooting-phase start result was handled by multiple hooks.")
        if not handled_results:
            return False
        return handled_results[0]


def _validate_hook_bindings(value: object) -> tuple[ShootingPhaseStartHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("ShootingPhaseStartHookRegistry bindings must be a tuple.")
    bindings: list[ShootingPhaseStartHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not ShootingPhaseStartHookBinding:
            raise GameLifecycleError("ShootingPhaseStartHookRegistry requires hook bindings.")
        if binding.hook_id in seen:
            raise GameLifecycleError("ShootingPhaseStartHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_shooting_phase_start_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Shooting-phase start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Shooting-phase start hooks require Shooting phase.")
    if state.shooting_phase_state is not None:
        raise GameLifecycleError("Shooting-phase start hooks require unopened ShootingPhaseState.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Shooting-phase start hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Shooting-phase start hook {field_name} must not be empty.")
    return stripped
