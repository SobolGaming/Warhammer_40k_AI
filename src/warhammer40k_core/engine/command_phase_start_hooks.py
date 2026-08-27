from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
    from warhammer40k_core.engine.battle_shock_historical_authority import (
        HistoricalBattleShockAuthorityContext,
    )
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.faction_rule_states import FactionRuleState
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE = (
    "select_faction_rule_command_phase_start_option"
)
COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND = "command_phase_start_battle_shock"


type CommandPhaseStartHandler = Callable[["CommandPhaseStartContext"], None]
type CommandPhaseStartEffectHandler = Callable[
    ["CommandPhaseStartEffectContext"],
    "LifecycleStatus | None",
]
type CommandPhaseStartRequestHandler = Callable[
    ["CommandPhaseStartRequestContext"],
    DecisionRequest | None,
]
type CommandPhaseStartResultHandler = Callable[
    ["CommandPhaseStartResultContext"],
    bool,
]
type CommandPhaseStartNestedResultHandler = Callable[
    ["CommandPhaseStartNestedResultContext"],
    bool,
]
type CommandPhaseStartNestedPendingAuthorityValidator = Callable[
    ["CommandPhaseStartNestedPendingAuthorityContext"],
    bool,
]
type CommandPhaseStartCompletedBattleShockAuthorityValidator = Callable[
    ["CommandPhaseStartCompletedBattleShockAuthorityContext"],
    None,
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
class CommandPhaseStartEffectContext:
    state: GameState
    decisions: DecisionController
    active_player_id: str
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("CommandPhaseStartEffectContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "CommandPhaseStartEffectContext decisions must be DecisionController."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "CommandPhaseStartEffectContext runtime_modifier_registry must be a registry."
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
class CommandPhaseStartNestedResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    active_player_id: str
    battle_shock_hooks: BattleShockHookRegistry
    runtime_modifier_registry: RuntimeModifierRegistry
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]

    def __post_init__(self) -> None:
        _validate_nested_context_common(
            state=self.state,
            decisions=self.decisions,
            request=self.request,
            active_player_id=self.active_player_id,
            battle_shock_hooks=self.battle_shock_hooks,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError(
                "CommandPhaseStartNestedResultContext result must be DecisionResult."
            )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )


@dataclass(frozen=True, slots=True)
class CommandPhaseStartNestedPendingAuthorityContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    active_player_id: str
    battle_shock_hooks: BattleShockHookRegistry
    runtime_modifier_registry: RuntimeModifierRegistry
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]

    def __post_init__(self) -> None:
        _validate_nested_context_common(
            state=self.state,
            decisions=self.decisions,
            request=self.request,
            active_player_id=self.active_player_id,
            battle_shock_hooks=self.battle_shock_hooks,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )


@dataclass(frozen=True, slots=True)
class CommandPhaseStartCompletedBattleShockAuthorityContext:
    state: GameState
    historical: HistoricalBattleShockAuthorityContext
    source_state: FactionRuleState
    source_decision_record: DecisionRecord
    request: BattleShockTestRequest

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
        from warhammer40k_core.engine.battle_shock_historical_authority import (
            HistoricalBattleShockAuthorityContext,
        )
        from warhammer40k_core.engine.decision_record import DecisionRecord
        from warhammer40k_core.engine.faction_rule_states import FactionRuleState
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority state must be GameState."
            )
        if type(self.historical) is not HistoricalBattleShockAuthorityContext:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority history is invalid."
            )
        if type(self.source_state) is not FactionRuleState:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority source state is invalid."
            )
        if type(self.source_decision_record) is not DecisionRecord:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority decision record is invalid."
            )
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority request is invalid."
            )
        if self.historical.request != self.request:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority request history drifted."
            )


@dataclass(frozen=True, slots=True)
class CommandPhaseStartHookBinding:
    hook_id: str
    source_id: str
    handler: CommandPhaseStartHandler | None = None
    effect_handler: CommandPhaseStartEffectHandler | None = None
    request_handler: CommandPhaseStartRequestHandler | None = None
    result_handler: CommandPhaseStartResultHandler | None = None
    nested_result_handler: CommandPhaseStartNestedResultHandler | None = None
    nested_pending_authority_validator: CommandPhaseStartNestedPendingAuthorityValidator | None = (
        None
    )
    completed_battle_shock_authority_validator: (
        CommandPhaseStartCompletedBattleShockAuthorityValidator | None
    ) = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if (
            self.handler is None
            and self.effect_handler is None
            and self.request_handler is None
            and self.result_handler is None
            and self.nested_result_handler is None
            and self.nested_pending_authority_validator is None
            and self.completed_battle_shock_authority_validator is None
        ):
            raise GameLifecycleError("CommandPhaseStartHookBinding requires a handler.")
        if self.handler is not None and not callable(self.handler):
            raise GameLifecycleError("CommandPhaseStartHookBinding handler must be callable.")
        if self.effect_handler is not None and not callable(self.effect_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding effect_handler must be callable."
            )
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding request_handler must be callable."
            )
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding result_handler must be callable."
            )
        if self.nested_result_handler is not None and not callable(self.nested_result_handler):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding nested_result_handler must be callable."
            )
        if self.nested_pending_authority_validator is not None and not callable(
            self.nested_pending_authority_validator
        ):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding nested pending authority validator must be callable."
            )
        if self.completed_battle_shock_authority_validator is not None and not callable(
            self.completed_battle_shock_authority_validator
        ):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding completed Battle-shock authority validator "
                "must be callable."
            )
        if (
            self.nested_result_handler is not None
            and self.nested_pending_authority_validator is None
        ):
            raise GameLifecycleError(
                "CommandPhaseStartHookBinding nested result handlers require an authority "
                "validator."
            )


@dataclass(frozen=True, slots=True)
class CommandPhaseStartProviderDisposition:
    binding: CommandPhaseStartHookBinding
    emitted_events: tuple[EventRecord, ...]
    state_changed: bool

    def __post_init__(self) -> None:
        if type(self.binding) is not CommandPhaseStartHookBinding:
            raise GameLifecycleError("Command-start disposition requires a provider binding.")
        if type(self.emitted_events) is not tuple or any(
            type(event) is not EventRecord for event in self.emitted_events
        ):
            raise GameLifecycleError("Command-start disposition events must be EventRecords.")
        if type(self.state_changed) is not bool:
            raise GameLifecycleError("Command-start disposition state_changed must be a bool.")
        if self.state_changed and not self.emitted_events:
            raise GameLifecycleError(
                "Command-start providers must emit evidence for authoritative state changes."
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
        self.resolve_with_provider_dispositions(context)

    def resolve_with_provider_dispositions(
        self,
        context: CommandPhaseStartContext,
    ) -> tuple[CommandPhaseStartProviderDisposition, ...]:
        if type(context) is not CommandPhaseStartContext:
            raise GameLifecycleError("Command-phase start hooks require context.")
        dispositions: list[CommandPhaseStartProviderDisposition] = []
        for binding in self.bindings:
            if binding.handler is not None:
                before = _provider_snapshot(context)
                binding.handler(context)
                dispositions.append(
                    _provider_disposition(
                        context=context,
                        binding=binding,
                        before=before,
                    )
                )
        return tuple(dispositions)

    def next_request_for(
        self,
        context: CommandPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        emission = self.next_request_with_provider(context)
        return None if emission is None else emission[0]

    def next_request_with_provider(
        self,
        context: CommandPhaseStartRequestContext,
    ) -> tuple[DecisionRequest, CommandPhaseStartHookBinding] | None:
        if type(context) is not CommandPhaseStartRequestContext:
            raise GameLifecycleError("Command-phase start request hooks require context.")
        emissions: list[tuple[DecisionRequest, CommandPhaseStartHookBinding]] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            before = _provider_snapshot(context)
            request = binding.request_handler(context)
            _require_request_provider_side_effects(
                context=context,
                before=before,
                request=request,
            )
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Command-phase start request handlers must return DecisionRequest or None."
                )
            if (
                request.decision_type
                != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
            ):
                raise GameLifecycleError(
                    "Command-phase start request handlers must use the finite decision type."
                )
            if binding.result_handler is None:
                raise GameLifecycleError(
                    "Command-phase start request providers require a result handler."
                )
            emissions.append((request, binding))
        if len(emissions) > 1:
            sequenced_emission = _sequenced_command_phase_start_emission(
                context=context,
                emissions=tuple(emissions),
            )
            if sequenced_emission is None:
                raise GameLifecycleError(
                    "Command-phase start hooks produced multiple simultaneous requests."
                )
            return sequenced_emission
        if not emissions:
            return None
        return emissions[0]

    def resolve_effects(
        self,
        context: CommandPhaseStartEffectContext,
    ) -> LifecycleStatus | None:
        status, _binding, _dispositions = self.resolve_effects_with_provider_dispositions(context)
        return status

    def resolve_effects_with_provider(
        self,
        context: CommandPhaseStartEffectContext,
    ) -> tuple[LifecycleStatus | None, CommandPhaseStartHookBinding | None]:
        status, binding, _dispositions = self.resolve_effects_with_provider_dispositions(context)
        return status, binding

    def resolve_effects_with_provider_dispositions(
        self,
        context: CommandPhaseStartEffectContext,
    ) -> tuple[
        LifecycleStatus | None,
        CommandPhaseStartHookBinding | None,
        tuple[CommandPhaseStartProviderDisposition, ...],
    ]:
        from warhammer40k_core.engine.phase import LifecycleStatus

        if type(context) is not CommandPhaseStartEffectContext:
            raise GameLifecycleError("Command-phase start effect hooks require context.")
        dispositions: list[CommandPhaseStartProviderDisposition] = []
        for binding in self.bindings:
            if binding.effect_handler is None:
                continue
            before = _provider_snapshot(context)
            status = binding.effect_handler(context)
            if status is None:
                dispositions.append(
                    _provider_disposition(
                        context=context,
                        binding=binding,
                        before=before,
                    )
                )
                continue
            if type(status) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Command-phase start effect handlers must return LifecycleStatus or None."
                )
            dispositions.append(
                _provider_disposition(
                    context=context,
                    binding=binding,
                    before=before,
                )
            )
            return status, binding, tuple(dispositions)
        return None, None, tuple(dispositions)

    def apply_result(
        self,
        context: CommandPhaseStartResultContext,
    ) -> bool:
        if type(context) is not CommandPhaseStartResultContext:
            raise GameLifecycleError("Command-phase start result hooks require context.")
        if (
            context.request.decision_type
            != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        ):
            raise GameLifecycleError("Command-phase start result decision type drifted.")
        handled_dispositions: list[CommandPhaseStartProviderDisposition] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            before = _provider_snapshot(context)
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Command-phase start result handlers must return bool.")
            if handled:
                handled_dispositions.append(
                    _provider_disposition(
                        context=context,
                        binding=binding,
                        before=before,
                    )
                )
            else:
                _require_provider_side_effect_free(
                    context=context,
                    before=before,
                    error_message=(
                        "Command-phase start result handlers that decline a result "
                        "must be side-effect free."
                    ),
                )
        if len(handled_dispositions) > 1:
            raise GameLifecycleError("Command-phase start result was handled by multiple hooks.")
        if not handled_dispositions:
            return False
        from warhammer40k_core.engine.command_phase_start_authority import (
            record_command_phase_start_finite_result,
        )

        record_command_phase_start_finite_result(
            context=context,
            registry=self,
            disposition=handled_dispositions[0],
        )
        return True

    def apply_nested_result(
        self,
        context: CommandPhaseStartNestedResultContext,
    ) -> bool:
        if type(context) is not CommandPhaseStartNestedResultContext:
            raise GameLifecycleError("Command-phase start nested result hooks require context.")
        handled_dispositions: list[CommandPhaseStartProviderDisposition] = []
        for binding in self.bindings:
            if binding.nested_result_handler is None:
                continue
            before = _provider_snapshot(context)
            handled = binding.nested_result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError(
                    "Command-phase start nested result handlers must return bool."
                )
            if handled:
                handled_dispositions.append(
                    _provider_disposition(
                        context=context,
                        binding=binding,
                        before=before,
                    )
                )
            else:
                _require_provider_side_effect_free(
                    context=context,
                    before=before,
                    error_message=(
                        "Command-phase start nested result handlers that decline a result "
                        "must be side-effect free."
                    ),
                )
        if len(handled_dispositions) > 1:
            raise GameLifecycleError(
                "Command-phase start nested result was handled by multiple hooks."
            )
        return bool(handled_dispositions)

    def binding_for_nested_pending_authority(
        self,
        context: CommandPhaseStartNestedPendingAuthorityContext,
    ) -> CommandPhaseStartHookBinding:
        if type(context) is not CommandPhaseStartNestedPendingAuthorityContext:
            raise GameLifecycleError("Command-start nested pending authority requires context.")
        claimed_bindings: list[CommandPhaseStartHookBinding] = []
        for binding in self.bindings:
            validator = binding.nested_pending_authority_validator
            if validator is None:
                continue
            before = _provider_snapshot(context)
            claimed = validator(context)
            if type(claimed) is not bool:
                raise GameLifecycleError(
                    "Command-start nested pending authority validators must return bool."
                )
            _require_provider_side_effect_free(
                context=context,
                before=before,
                error_message="Command-start nested pending authority validation mutated state.",
            )
            if claimed:
                claimed_bindings.append(binding)
        if len(claimed_bindings) != 1:
            raise GameLifecycleError(
                "Command-start nested pending request must have exactly one source authority."
            )
        return claimed_bindings[0]

    def validate_completed_battle_shock_authority(
        self,
        *,
        hook_id: str,
        source_id: str,
        context: CommandPhaseStartCompletedBattleShockAuthorityContext,
    ) -> None:
        if type(context) is not CommandPhaseStartCompletedBattleShockAuthorityContext:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority requires context."
            )
        resolved_hook_id = _validate_identifier("hook_id", hook_id)
        resolved_source_id = _validate_identifier("source_id", source_id)
        bindings = tuple(
            binding
            for binding in self.bindings
            if binding.hook_id == resolved_hook_id and binding.source_id == resolved_source_id
        )
        if len(bindings) != 1:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority requires one loaded provider."
            )
        validator = bindings[0].completed_battle_shock_authority_validator
        if validator is None:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock provider lacks historical authority."
            )
        before_state = context.state.to_payload()
        result = validator(context)
        if result is not None:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority validators must return None."
            )
        if context.state.to_payload() != before_state:
            raise GameLifecycleError(
                "Completed Command-start Battle-shock authority validation mutated state."
            )


type _ProviderContext = (
    CommandPhaseStartContext
    | CommandPhaseStartEffectContext
    | CommandPhaseStartRequestContext
    | CommandPhaseStartResultContext
    | CommandPhaseStartNestedResultContext
    | CommandPhaseStartNestedPendingAuthorityContext
)
type _ProviderSnapshot = tuple[object, tuple[DecisionRequest, ...], int, int]


def _provider_snapshot(context: _ProviderContext) -> _ProviderSnapshot:
    return (
        context.state.to_payload(),
        context.decisions.queue.pending_requests,
        len(context.decisions.records),
        len(context.decisions.event_log.records),
    )


def _provider_disposition(
    *,
    context: _ProviderContext,
    binding: CommandPhaseStartHookBinding,
    before: _ProviderSnapshot,
) -> CommandPhaseStartProviderDisposition:
    state_payload, _pending_requests, decision_record_count, event_count = before
    records = context.decisions.event_log.records
    if len(context.decisions.records) != decision_record_count:
        raise GameLifecycleError("Command-start providers cannot record player decisions.")
    if len(records) < event_count:
        raise GameLifecycleError("Command-start provider removed retained events.")
    emitted_events = records[event_count:]
    _validate_provider_decision_events(
        context=context,
        emitted_events=emitted_events,
        all_events=records,
    )
    return CommandPhaseStartProviderDisposition(
        binding=binding,
        emitted_events=emitted_events,
        state_changed=context.state.to_payload() != state_payload,
    )


def _validate_provider_decision_events(
    *,
    context: _ProviderContext,
    emitted_events: tuple[EventRecord, ...],
    all_events: tuple[EventRecord, ...],
) -> None:
    if any(event.event_type == "decision_recorded" for event in emitted_events):
        raise GameLifecycleError("Command-start providers cannot emit decision records.")
    for event in emitted_events:
        if event.event_type != "decision_requested":
            continue
        live_matches = sum(
            request.to_payload() == event.payload
            for request in context.decisions.queue.pending_requests
        ) + sum(
            record.request.to_payload() == event.payload for record in context.decisions.records
        )
        retained_event_count = sum(
            retained.event_type == "decision_requested" and retained.payload == event.payload
            for retained in all_events
        )
        if live_matches != 1 or retained_event_count != 1:
            raise GameLifecycleError("Command-start provider emitted an orphaned decision request.")


def _require_provider_side_effect_free(
    *,
    context: _ProviderContext,
    before: _ProviderSnapshot,
    error_message: str,
) -> None:
    state_payload, pending_requests, decision_record_count, event_count = before
    if (
        context.state.to_payload() != state_payload
        or context.decisions.queue.pending_requests != pending_requests
        or len(context.decisions.records) != decision_record_count
        or len(context.decisions.event_log.records) != event_count
    ):
        raise GameLifecycleError(error_message)


def _require_request_provider_side_effects(
    *,
    context: CommandPhaseStartRequestContext,
    before: _ProviderSnapshot,
    request: object,
) -> None:
    state_payload, pending_requests, decision_record_count, event_count = before
    if not isinstance(state_payload, dict):
        raise GameLifecycleError("Command-phase start request state snapshot is invalid.")
    current_payload = context.state.to_payload()
    retained_payload = dict(cast(dict[str, object], state_payload))
    retained_count = retained_payload.pop("decision_request_count", None)
    current_without_count: dict[str, object] = dict(current_payload)
    current_count = current_without_count.pop("decision_request_count", None)
    allowed_count_change = (
        type(retained_count) is int
        and type(current_count) is int
        and (
            current_count == retained_count
            or (
                type(request) is DecisionRequest
                and current_count == retained_count + 1
                and request.request_id == f"decision-request-{current_count:06d}"
            )
        )
    )
    if (
        retained_payload != current_without_count
        or not allowed_count_change
        or context.decisions.queue.pending_requests != pending_requests
        or len(context.decisions.records) != decision_record_count
        or len(context.decisions.event_log.records) != event_count
    ):
        raise GameLifecycleError(
            "Command-phase start request handlers may only allocate their request ID."
        )


def _validate_bindings(value: object) -> tuple[CommandPhaseStartHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.COMMAND_PHASE_START,
        binding_type=CommandPhaseStartHookBinding,
        registry_name="CommandPhaseStartHookRegistry",
        invalid_binding_message=(
            "CommandPhaseStartHookRegistry bindings must contain hook bindings."
        ),
    )


def _sequenced_command_phase_start_emission(
    *,
    context: CommandPhaseStartRequestContext,
    emissions: tuple[tuple[DecisionRequest, CommandPhaseStartHookBinding], ...],
) -> tuple[DecisionRequest, CommandPhaseStartHookBinding] | None:
    active_actor_requests = tuple(
        emission for emission in emissions if emission[0].actor_id == context.active_player_id
    )
    non_active_actor_requests = tuple(
        emission for emission in emissions if emission[0].actor_id != context.active_player_id
    )
    if len(active_actor_requests) > 1:
        return None
    for request, _binding in non_active_actor_requests:
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


_validate_identifier = IdentifierValidator(GameLifecycleError)


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


def _validate_nested_context_common(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    active_player_id: str,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Command-start nested context state must be GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Command-start nested context decisions must be DecisionController."
        )
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Command-start nested context request must be DecisionRequest.")
    _validate_identifier("active_player_id", active_player_id)
    if type(battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError(
            "Command-start nested context battle_shock_hooks must be a registry."
        )
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Command-start nested context runtime_modifier_registry must be a registry."
        )
    _validate_command_phase_start_state(state, active_player_id=active_player_id)
