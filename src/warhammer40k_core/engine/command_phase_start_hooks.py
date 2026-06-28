from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE = (
    "select_faction_rule_command_phase_start_option"
)


type CommandPhaseStartHandler = Callable[["CommandPhaseStartContext"], None]
type CommandPhaseStartRequestHandler = Callable[
    ["CommandPhaseStartRequestContext"],
    DecisionRequest | None,
]
type CommandPhaseStartResultHandler = Callable[
    ["CommandPhaseStartResultContext"],
    bool,
]


def _empty_ability_indexes() -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class CommandPhaseStartContext:
    state: GameState
    decisions: DecisionController
    active_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("CommandPhaseStartContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "CommandPhaseStartContext decisions must be DecisionController."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        if self.state.current_battle_phase is not BattlePhase.COMMAND:
            raise GameLifecycleError("Command-phase start hooks require Command phase.")
        if self.state.active_player_id != self.active_player_id:
            raise GameLifecycleError("Command-phase start hook active player drift.")


@dataclass(frozen=True, slots=True)
class CommandPhaseStartRequestContext:
    state: GameState
    decisions: DecisionController
    active_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("CommandPhaseStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "CommandPhaseStartRequestContext decisions must be DecisionController."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        _validate_command_phase_start_state(self.state, active_player_id=self.active_player_id)


@dataclass(frozen=True, slots=True)
class CommandPhaseStartResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    active_player_id: str
    battle_shock_hooks: BattleShockHookRegistry = field(
        default_factory=BattleShockHookRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=_empty_ability_indexes
    )

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("CommandPhaseStartResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext decisions must be DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext result must be DecisionResult."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        if type(self.battle_shock_hooks) is not BattleShockHookRegistry:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext battle_shock_hooks must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext runtime_modifier_registry must be a registry."
            )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )
        _validate_command_phase_start_state(self.state, active_player_id=self.active_player_id)


@dataclass(frozen=True, slots=True)
class CommandPhaseStartHookBinding:
    hook_id: str
    source_id: str
    handler: CommandPhaseStartHandler | None = None
    request_handler: CommandPhaseStartRequestHandler | None = None
    result_handler: CommandPhaseStartResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.handler is None and self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("CommandPhaseStartHookBinding requires a handler.")
        if self.handler is not None and not callable(self.handler):
            raise GameLifecycleError("CommandPhaseStartHookBinding handler must be callable.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding request_handler must be callable."
            )
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding result_handler must be callable."
            )


@dataclass(frozen=True, slots=True)
class CommandPhaseStartHookRegistry:
    bindings: tuple[CommandPhaseStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[CommandPhaseStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[CommandPhaseStartHookBinding, ...]:
        return self.bindings

    def resolve(self, context: CommandPhaseStartContext) -> None:
        if type(context) is not CommandPhaseStartContext:
            raise GameLifecycleError("Command-phase start hooks require context.")
        for binding in self.bindings:
            if binding.handler is not None:
                binding.handler(context)

    def next_request_for(
        self,
        context: CommandPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not CommandPhaseStartRequestContext:
            raise GameLifecycleError("Command-phase start request hooks require context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Command-phase start request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            sequenced_request = _sequenced_command_phase_start_request(
                context=context,
                requests=tuple(requests),
            )
            if sequenced_request is None:
                raise GameLifecycleError(
                    "Command-phase start hooks produced multiple simultaneous requests."
                )
            return sequenced_request
        if not requests:
            return None
        return requests[0]

    def apply_result(
        self,
        context: CommandPhaseStartResultContext,
    ) -> bool:
        if type(context) is not CommandPhaseStartResultContext:
            raise GameLifecycleError("Command-phase start result hooks require context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Command-phase start result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Command-phase start result was handled by multiple hooks.")
        return bool(handled_ids)


def _validate_bindings(value: object) -> tuple[CommandPhaseStartHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("CommandPhaseStartHookRegistry bindings must be a tuple.")
    bindings: list[CommandPhaseStartHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not CommandPhaseStartHookBinding:
            raise GameLifecycleError(
                "CommandPhaseStartHookRegistry bindings must contain hook bindings."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("CommandPhaseStartHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda item: item.hook_id))


def _sequenced_command_phase_start_request(
    *,
    context: CommandPhaseStartRequestContext,
    requests: tuple[DecisionRequest, ...],
) -> DecisionRequest | None:
    active_actor_requests = tuple(
        request for request in requests if request.actor_id == context.active_player_id
    )
    non_active_actor_requests = tuple(
        request for request in requests if request.actor_id != context.active_player_id
    )
    if len(active_actor_requests) > 1:
        return None
    for request in non_active_actor_requests:
        if not _request_allows_non_active_actor(request):
            return None
    if active_actor_requests:
        return active_actor_requests[0]
    if non_active_actor_requests:
        return non_active_actor_requests[0]
    return None


def _request_allows_non_active_actor(request: DecisionRequest) -> bool:
    payload = request.payload
    if not isinstance(payload, Mapping):
        return False
    return payload.get("actor_may_be_non_active") is True


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Command-phase start hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Command-phase start hook {field_name} must not be empty.")
    return stripped


def _validate_ability_index_mapping(
    indexes: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError(
            "CommandPhaseStartResultContext ability_indexes_by_player_id must be a mapping."
        )
    validated: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in cast(Mapping[object, object], indexes).items():
        player_id = _validate_identifier("ability_indexes_by_player_id key", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "CommandPhaseStartResultContext ability indexes must be AbilityCatalogIndex."
            )
        validated[player_id] = raw_index
    return MappingProxyType(dict(sorted(validated.items())))


def _validate_command_phase_start_state(state: GameState, *, active_player_id: str) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Command-phase start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Command-phase start hooks require Command phase.")
    if state.active_player_id != active_player_id:
        raise GameLifecycleError("Command-phase start hook active player drift.")
