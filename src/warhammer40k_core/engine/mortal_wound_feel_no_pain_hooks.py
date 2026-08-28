from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
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
    battle_shock_hooks: BattleShockHookRegistry | None = None
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None

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
        if self.battle_shock_hooks is not None:
            from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry

            if type(self.battle_shock_hooks) is not BattleShockHookRegistry:
                raise GameLifecycleError(
                    "Mortal wound FNP continuation battle_shock_hooks are invalid."
                )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_indexes(self.ability_indexes_by_player_id),
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
        return self.binding_for_source_context(source_context) is not None

    def binding_for_source_context(
        self,
        source_context: JsonValue,
    ) -> MortalWoundFeelNoPainContinuationHookBinding | None:
        source_kind = _source_kind_from_context(source_context)
        return next(
            (binding for binding in self.bindings if binding.source_kind == source_kind),
            None,
        )

    def binding_for_request(
        self,
        request: DecisionRequest,
        *,
        required_source_ids: frozenset[str],
    ) -> MortalWoundFeelNoPainContinuationHookBinding | None:
        if not is_mortal_wound_feel_no_pain_request(request):
            return None
        source_context = mortal_wound_feel_no_pain_source_context(request)
        binding = self.binding_for_source_context(source_context)
        if binding is None:
            return None
        if binding.source_id in required_source_ids:
            request_payload = cast(dict[str, JsonValue], request.payload)
            progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
                request_payload["lost_wound_context"]
            )
            if progress.source_rule_id != binding.source_id:
                raise GameLifecycleError(
                    "Mortal wound FNP continuation source rule identity drifted."
                )
        return binding

    def apply_decision(
        self,
        context: MortalWoundFeelNoPainContinuationContext,
    ) -> LifecycleStatus | None:
        if type(context) is not MortalWoundFeelNoPainContinuationContext:
            raise GameLifecycleError("Mortal wound FNP continuation requires context.")
        binding = self.binding_for_source_context(context.source_context)
        if binding is None:
            raise GameLifecycleError("Mortal wound FNP continuation source kind is not registered.")
        required_source_ids: frozenset[str]
        if context.battle_shock_hooks is None:
            required_source_ids = frozenset()
        else:
            required_source_ids = context.battle_shock_hooks.pending_outcome_authority_source_ids()
        if binding.source_id in required_source_ids:
            request_source_context = mortal_wound_feel_no_pain_source_context(context.request)
            if context.source_context != request_source_context:
                raise GameLifecycleError("Mortal wound FNP continuation source context drifted.")
            if (
                self.binding_for_request(
                    context.request,
                    required_source_ids=required_source_ids,
                )
                != binding
            ):
                raise GameLifecycleError("Mortal wound FNP continuation request binding drifted.")
        status = binding.handler(context)
        if status is not None and type(status) is not LifecycleStatus:
            raise GameLifecycleError(
                "Mortal wound FNP continuation handlers must return status or None."
            )
        return status


def _validate_ability_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Mortal wound FNP continuation ability indexes must be a mapping.")
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex

    untyped_indexes = cast(Mapping[object, object], value)
    for player_id, index in untyped_indexes.items():
        _validate_identifier("ability_indexes_by_player_id key", player_id)
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "Mortal wound FNP continuation ability indexes must contain "
                "AbilityCatalogIndex values."
            )
    return cast(Mapping[str, AbilityCatalogIndex], value)


def _validate_hook_bindings(
    value: object,
) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
    bindings = validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION,
        binding_type=MortalWoundFeelNoPainContinuationHookBinding,
        registry_name="MortalWoundFeelNoPainContinuationHookRegistry",
        invalid_binding_message=(
            "MortalWoundFeelNoPainContinuationHookRegistry bindings must contain "
            "MortalWoundFeelNoPainContinuationHookBinding values."
        ),
    )
    seen_source_kinds: set[str] = set()
    for binding in bindings:
        if binding.source_kind in seen_source_kinds:
            raise GameLifecycleError(
                "MortalWoundFeelNoPainContinuationHookRegistry source kinds must be unique."
            )
        seen_source_kinds.add(binding.source_kind)
    return bindings


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


_validate_identifier = IdentifierValidator(
    GameLifecycleError,
    message_prefix="Mortal wound FNP hook",
)
