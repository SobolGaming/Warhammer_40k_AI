from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phase_start_sequencing import resolve_phase_start_candidates
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


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
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )
    authoritative_request_id: str | None = None

    def issue_request_id(self) -> str:
        return (
            self.state.next_decision_request_id()
            if self.authoritative_request_id is None
            else self.authoritative_request_id
        )

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
    battle_shock_hooks: BattleShockHookRegistry | None = None
    runtime_modifier_registry: RuntimeModifierRegistry | None = None
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=lambda: MappingProxyType({})
    )

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
        from warhammer40k_core.engine.abilities import AbilityCatalogIndex
        from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
        from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

        if (
            self.battle_shock_hooks is not None
            and type(self.battle_shock_hooks) is not BattleShockHookRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext Battle-shock hooks must be a registry."
            )
        if (
            self.runtime_modifier_registry is not None
            and type(self.runtime_modifier_registry) is not RuntimeModifierRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseStartResultContext runtime modifiers must be a registry."
            )
        indexes = dict(self.ability_indexes_by_player_id)
        if any(type(player_id) is not str for player_id in indexes) or any(
            type(index) is not AbilityCatalogIndex for index in indexes.values()
        ):
            raise GameLifecycleError("ShootingPhaseStartResultContext ability indexes are invalid.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(indexes))
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
    candidate_handler: (
        Callable[[ShootingPhaseStartRequestContext], tuple[TimingRuleCandidate, ...]] | None
    ) = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if (
            self.request_handler is None
            and self.result_handler is None
            and self.candidate_handler is None
        ):
            raise GameLifecycleError("ShootingPhaseStartHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "ShootingPhaseStartHookBinding request_handler must be callable."
            )
        if self.candidate_handler is not None and not callable(self.candidate_handler):
            raise GameLifecycleError(
                "ShootingPhaseStartHookBinding candidate_handler must be callable."
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
    ) -> DecisionRequest | LifecycleStatus | None:
        if type(context) is not ShootingPhaseStartRequestContext:
            raise GameLifecycleError("Shooting-phase start request hooks require context.")
        return resolve_phase_start_candidates(
            state=context.state,
            decisions=context.decisions,
            discover=lambda: self.candidates_for(context),
        )

    def candidates_for(
        self, context: ShootingPhaseStartRequestContext
    ) -> tuple[TimingRuleCandidate, ...]:
        candidates: list[TimingRuleCandidate] = []
        for binding in self.bindings:
            if binding.request_handler is None and binding.candidate_handler is None:
                continue
            if binding.candidate_handler is None:
                raise GameLifecycleError(
                    "Shooting-start providers require pure candidate discovery."
                )
            before = (context.state.to_payload(), context.decisions.to_payload())
            discovered = binding.candidate_handler(context)
            if before != (context.state.to_payload(), context.decisions.to_payload()):
                raise GameLifecycleError("Shooting-start discovery mutated engine state.")
            if type(discovered) is not tuple or any(
                type(item) is not TimingRuleCandidate for item in discovered
            ):
                raise GameLifecycleError("Shooting-start discovery requires typed candidates.")
            candidates.extend(discovered)
        return tuple(candidates)

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
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.SHOOTING_PHASE_START,
        binding_type=ShootingPhaseStartHookBinding,
        registry_name="ShootingPhaseStartHookRegistry",
        invalid_binding_message="ShootingPhaseStartHookRegistry requires hook bindings.",
    )


def _validate_shooting_phase_start_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Shooting-phase start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Shooting-phase start hooks require Shooting phase.")
    if state.shooting_phase_state is not None:
        raise GameLifecycleError("Shooting-phase start hooks require unopened ShootingPhaseState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
