from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptorError,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)

CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID = "core:movement-keyword-gate"
CORE_HAZARDOUS_HANDLER_ID = "core:hazardous"
GENERIC_RULE_IR_ABILITY_HANDLER_ID = "generic:rule-ir"
MOVEMENT_CAPABILITY_FLAGS_PAYLOAD_KEY = "movement_capability_flags"


class AbilitySourceKind(StrEnum):
    CORE = "core"
    KEYWORD = "keyword"
    FACTION = "faction"
    DETACHMENT = "detachment"
    DATASHEET = "datasheet"
    ENHANCEMENT = "enhancement"
    WARGEAR = "wargear"
    WEAPON = "weapon"


class AbilityResolutionStatus(StrEnum):
    APPLIED = "applied"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class KeywordGatePayload(TypedDict):
    required_keywords: list[str]
    forbidden_keywords: list[str]


class AbilityTimingDescriptorPayload(TypedDict):
    trigger_kind: str
    phase: str | None
    timing_window_id: str | None


class AbilityDefinitionPayload(TypedDict):
    ability_id: str
    name: str
    source_id: str
    when_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: AbilityTimingDescriptorPayload
    keyword_gate: KeywordGatePayload
    handler_id: str
    required_input_keys: list[str]
    replay_payload: JsonValue


class AbilityCatalogRecordPayload(TypedDict):
    record_id: str
    definition: AbilityDefinitionPayload
    source_kind: str
    faction_id: str | None
    detachment_id: str | None
    datasheet_id: str | None
    wargear_id: str | None
    weapon_profile_id: str | None
    disabled: bool


class AbilityExecutionContextPayload(TypedDict):
    game_id: str
    player_id: str
    battle_round: int
    phase: str | None
    active_player_id: str | None
    trigger_kind: str
    timing_window_id: str | None
    source_unit_instance_id: str | None
    source_model_instance_id: str | None
    target_unit_instance_id: str | None
    source_keywords: list[str]
    trigger_payload: JsonValue


class AbilityResolutionResultPayload(TypedDict):
    record_id: str
    ability_id: str
    handler_id: str
    source_id: str
    status: str
    reason: str | None
    replay_payload: JsonValue


@dataclass(frozen=True, slots=True)
class KeywordGate:
    required_keywords: tuple[str, ...] = ()
    forbidden_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required_keywords = _validate_keyword_tuple(
            "KeywordGate required_keywords",
            self.required_keywords,
        )
        forbidden_keywords = _validate_keyword_tuple(
            "KeywordGate forbidden_keywords",
            self.forbidden_keywords,
        )
        overlap = set(required_keywords) & set(forbidden_keywords)
        if overlap:
            raise GameLifecycleError("KeywordGate keywords cannot be both required and forbidden.")
        object.__setattr__(self, "required_keywords", required_keywords)
        object.__setattr__(self, "forbidden_keywords", forbidden_keywords)

    @property
    def is_empty(self) -> bool:
        return not self.required_keywords and not self.forbidden_keywords

    def matches(self, keywords: tuple[str, ...]) -> bool:
        keyword_set = set(_validate_keyword_tuple("KeywordGate source keywords", keywords))
        return set(self.required_keywords).issubset(keyword_set) and not (
            set(self.forbidden_keywords) & keyword_set
        )

    def to_payload(self) -> KeywordGatePayload:
        return {
            "required_keywords": list(self.required_keywords),
            "forbidden_keywords": list(self.forbidden_keywords),
        }

    @classmethod
    def from_payload(cls, payload: KeywordGatePayload) -> Self:
        return cls(
            required_keywords=tuple(payload["required_keywords"]),
            forbidden_keywords=tuple(payload["forbidden_keywords"]),
        )


@dataclass(frozen=True, slots=True)
class AbilityTimingDescriptor:
    trigger_kind: TimingTriggerKind
    phase: BattlePhaseKind | None = None
    timing_window_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("AbilityTimingDescriptor phase", self.phase),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "AbilityTimingDescriptor timing_window_id",
                self.timing_window_id,
            ),
        )

    def matches(self, context: AbilityExecutionContext) -> bool:
        if type(context) is not AbilityExecutionContext:
            raise GameLifecycleError("Ability timing requires an AbilityExecutionContext.")
        if self.trigger_kind is not context.trigger_kind:
            return False
        if self.phase is not None and self.phase is not context.phase:
            return False
        return not (
            self.timing_window_id is not None and self.timing_window_id != context.timing_window_id
        )

    def to_payload(self) -> AbilityTimingDescriptorPayload:
        return {
            "trigger_kind": self.trigger_kind.value,
            "phase": None if self.phase is None else self.phase.value,
            "timing_window_id": self.timing_window_id,
        }

    @classmethod
    def from_payload(cls, payload: AbilityTimingDescriptorPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            timing_window_id=payload["timing_window_id"],
        )


@dataclass(frozen=True, slots=True)
class AbilityDefinition:
    ability_id: str
    name: str
    source_id: str
    when_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: AbilityTimingDescriptor
    keyword_gate: KeywordGate = field(default_factory=KeywordGate)
    handler_id: str = "record_only"
    required_input_keys: tuple[str, ...] = ()
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("AbilityDefinition ability_id", self.ability_id),
        )
        object.__setattr__(self, "name", _validate_identifier("AbilityDefinition name", self.name))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AbilityDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "when_descriptor",
            _validate_identifier("AbilityDefinition when_descriptor", self.when_descriptor),
        )
        object.__setattr__(
            self,
            "effect_descriptor",
            _validate_identifier("AbilityDefinition effect_descriptor", self.effect_descriptor),
        )
        object.__setattr__(
            self,
            "restrictions_descriptor",
            _validate_identifier(
                "AbilityDefinition restrictions_descriptor",
                self.restrictions_descriptor,
            ),
        )
        if type(self.timing) is not AbilityTimingDescriptor:
            raise GameLifecycleError("AbilityDefinition timing must be a descriptor.")
        if type(self.keyword_gate) is not KeywordGate:
            raise GameLifecycleError("AbilityDefinition keyword_gate must be a KeywordGate.")
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("AbilityDefinition handler_id", self.handler_id),
        )
        object.__setattr__(
            self,
            "required_input_keys",
            _validate_identifier_tuple(
                "AbilityDefinition required_input_keys",
                self.required_input_keys,
            ),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> AbilityDefinitionPayload:
        return {
            "ability_id": self.ability_id,
            "name": self.name,
            "source_id": self.source_id,
            "when_descriptor": self.when_descriptor,
            "effect_descriptor": self.effect_descriptor,
            "restrictions_descriptor": self.restrictions_descriptor,
            "timing": self.timing.to_payload(),
            "keyword_gate": self.keyword_gate.to_payload(),
            "handler_id": self.handler_id,
            "required_input_keys": list(self.required_input_keys),
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: AbilityDefinitionPayload) -> Self:
        return cls(
            ability_id=payload["ability_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            when_descriptor=payload["when_descriptor"],
            effect_descriptor=payload["effect_descriptor"],
            restrictions_descriptor=payload["restrictions_descriptor"],
            timing=AbilityTimingDescriptor.from_payload(payload["timing"]),
            keyword_gate=KeywordGate.from_payload(payload["keyword_gate"]),
            handler_id=payload["handler_id"],
            required_input_keys=tuple(payload["required_input_keys"]),
            replay_payload=payload["replay_payload"],
        )


@dataclass(frozen=True, slots=True)
class AbilityCatalogRecord:
    record_id: str
    definition: AbilityDefinition
    source_kind: AbilitySourceKind = AbilitySourceKind.CORE
    faction_id: str | None = None
    detachment_id: str | None = None
    datasheet_id: str | None = None
    wargear_id: str | None = None
    weapon_profile_id: str | None = None
    disabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("AbilityCatalogRecord record_id", self.record_id),
        )
        if type(self.definition) is not AbilityDefinition:
            raise GameLifecycleError("AbilityCatalogRecord definition must be a definition.")
        object.__setattr__(
            self,
            "source_kind",
            ability_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "faction_id",
            _validate_optional_identifier("AbilityCatalogRecord faction_id", self.faction_id),
        )
        object.__setattr__(
            self,
            "detachment_id",
            _validate_optional_identifier(
                "AbilityCatalogRecord detachment_id",
                self.detachment_id,
            ),
        )
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_optional_identifier("AbilityCatalogRecord datasheet_id", self.datasheet_id),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_optional_identifier("AbilityCatalogRecord wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_optional_identifier(
                "AbilityCatalogRecord weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "disabled",
            _validate_bool("AbilityCatalogRecord disabled", self.disabled),
        )
        _validate_source_owner_shape(self)

    def to_payload(self) -> AbilityCatalogRecordPayload:
        return {
            "record_id": self.record_id,
            "definition": self.definition.to_payload(),
            "source_kind": self.source_kind.value,
            "faction_id": self.faction_id,
            "detachment_id": self.detachment_id,
            "datasheet_id": self.datasheet_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "disabled": self.disabled,
        }

    @classmethod
    def from_payload(cls, payload: AbilityCatalogRecordPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            definition=AbilityDefinition.from_payload(payload["definition"]),
            source_kind=ability_source_kind_from_token(payload["source_kind"]),
            faction_id=payload["faction_id"],
            detachment_id=payload["detachment_id"],
            datasheet_id=payload["datasheet_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            disabled=payload["disabled"],
        )


@dataclass(frozen=True, slots=True)
class AbilityCatalogIndex:
    _records_by_trigger: Mapping[TimingTriggerKind, tuple[AbilityCatalogRecord, ...]]
    _records: tuple[AbilityCatalogRecord, ...]

    @classmethod
    def from_records(cls, records: tuple[AbilityCatalogRecord, ...]) -> Self:
        validated = _validate_catalog_records(records)
        grouped: dict[TimingTriggerKind, list[AbilityCatalogRecord]] = {}
        for record in validated:
            grouped.setdefault(record.definition.timing.trigger_kind, []).append(record)
        records_by_trigger = {
            trigger_kind: tuple(records_for_trigger)
            for trigger_kind, records_for_trigger in grouped.items()
        }
        return cls(
            _records_by_trigger=MappingProxyType(records_by_trigger),
            _records=validated,
        )

    def records_for(self, trigger_kind: TimingTriggerKind) -> tuple[AbilityCatalogRecord, ...]:
        if type(trigger_kind) is not TimingTriggerKind:
            raise GameLifecycleError("AbilityCatalogIndex lookup requires a TimingTriggerKind.")
        return self._records_by_trigger.get(trigger_kind, ())

    def all_records(self) -> tuple[AbilityCatalogRecord, ...]:
        return self._records


@dataclass(frozen=True, slots=True)
class AbilityExecutionContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind | None
    active_player_id: str | None
    trigger_kind: TimingTriggerKind
    timing_window_id: str | None = None
    source_unit_instance_id: str | None = None
    source_model_instance_id: str | None = None
    target_unit_instance_id: str | None = None
    source_keywords: tuple[str, ...] = ()
    trigger_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("AbilityExecutionContext game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AbilityExecutionContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "AbilityExecutionContext battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("AbilityExecutionContext phase", self.phase),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "AbilityExecutionContext active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "AbilityExecutionContext timing_window_id",
                self.timing_window_id,
            ),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_optional_identifier(
                "AbilityExecutionContext source_unit_instance_id",
                self.source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_model_instance_id",
            _validate_optional_identifier(
                "AbilityExecutionContext source_model_instance_id",
                self.source_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_optional_identifier(
                "AbilityExecutionContext target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_keywords",
            _validate_keyword_tuple(
                "AbilityExecutionContext source_keywords",
                self.source_keywords,
            ),
        )
        object.__setattr__(self, "trigger_payload", validate_json_value(self.trigger_payload))

    @classmethod
    def passive_keyword_gate(cls, *, source_keywords: tuple[str, ...]) -> Self:
        return cls(
            game_id="ability-keyword-gate",
            player_id="engine",
            battle_round=1,
            phase=None,
            active_player_id=None,
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            source_keywords=source_keywords,
        )

    def to_payload(self) -> AbilityExecutionContextPayload:
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": None if self.phase is None else self.phase.value,
            "active_player_id": self.active_player_id,
            "trigger_kind": self.trigger_kind.value,
            "timing_window_id": self.timing_window_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "source_model_instance_id": self.source_model_instance_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "source_keywords": list(self.source_keywords),
            "trigger_payload": self.trigger_payload,
        }

    @classmethod
    def from_payload(cls, payload: AbilityExecutionContextPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            active_player_id=payload["active_player_id"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            timing_window_id=payload["timing_window_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            source_model_instance_id=payload["source_model_instance_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            source_keywords=tuple(payload["source_keywords"]),
            trigger_payload=payload["trigger_payload"],
        )


@dataclass(frozen=True, slots=True)
class AbilityResolutionResult:
    record_id: str
    ability_id: str
    handler_id: str
    source_id: str
    status: AbilityResolutionStatus
    reason: str | None = None
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("AbilityResolutionResult record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("AbilityResolutionResult ability_id", self.ability_id),
        )
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("AbilityResolutionResult handler_id", self.handler_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AbilityResolutionResult source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "status",
            ability_resolution_status_from_token(self.status),
        )
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("AbilityResolutionResult reason", self.reason),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        if self.status is AbilityResolutionStatus.APPLIED and self.reason is not None:
            raise GameLifecycleError("Applied AbilityResolutionResult must not include reason.")
        if self.status is not AbilityResolutionStatus.APPLIED and self.reason is None:
            raise GameLifecycleError("Non-applied AbilityResolutionResult requires reason.")

    @classmethod
    def applied(cls, record: AbilityCatalogRecord, *, replay_payload: JsonValue = None) -> Self:
        _validate_catalog_record(record)
        return cls(
            record_id=record.record_id,
            ability_id=record.definition.ability_id,
            handler_id=record.definition.handler_id,
            source_id=record.definition.source_id,
            status=AbilityResolutionStatus.APPLIED,
            replay_payload=replay_payload,
        )

    @classmethod
    def invalid(cls, record: AbilityCatalogRecord, *, reason: str) -> Self:
        _validate_catalog_record(record)
        return cls(
            record_id=record.record_id,
            ability_id=record.definition.ability_id,
            handler_id=record.definition.handler_id,
            source_id=record.definition.source_id,
            status=AbilityResolutionStatus.INVALID,
            reason=reason,
        )

    @classmethod
    def unsupported(cls, record: AbilityCatalogRecord, *, reason: str) -> Self:
        _validate_catalog_record(record)
        return cls(
            record_id=record.record_id,
            ability_id=record.definition.ability_id,
            handler_id=record.definition.handler_id,
            source_id=record.definition.source_id,
            status=AbilityResolutionStatus.UNSUPPORTED,
            reason=reason,
        )

    def to_payload(self) -> AbilityResolutionResultPayload:
        return {
            "record_id": self.record_id,
            "ability_id": self.ability_id,
            "handler_id": self.handler_id,
            "source_id": self.source_id,
            "status": self.status.value,
            "reason": self.reason,
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: AbilityResolutionResultPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            ability_id=payload["ability_id"],
            handler_id=payload["handler_id"],
            source_id=payload["source_id"],
            status=ability_resolution_status_from_token(payload["status"]),
            reason=payload["reason"],
            replay_payload=payload["replay_payload"],
        )


AbilityHandler = Callable[[AbilityCatalogRecord, AbilityExecutionContext], AbilityResolutionResult]


@dataclass(frozen=True, slots=True)
class AbilityHandlerBinding:
    handler_id: str
    timing: AbilityTimingDescriptor
    required_input_keys: tuple[str, ...]
    handler: AbilityHandler

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("AbilityHandlerBinding handler_id", self.handler_id),
        )
        if self.handler_id.startswith("unsupported:"):
            raise GameLifecycleError("AbilityHandlerBinding cannot register unsupported handlers.")
        if type(self.timing) is not AbilityTimingDescriptor:
            raise GameLifecycleError("AbilityHandlerBinding timing must be a descriptor.")
        object.__setattr__(
            self,
            "required_input_keys",
            _validate_identifier_tuple(
                "AbilityHandlerBinding required_input_keys",
                self.required_input_keys,
            ),
        )
        if not callable(self.handler):
            raise GameLifecycleError("AbilityHandlerBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class AbilityHandlerRegistry:
    _handlers: Mapping[str, AbilityHandlerBinding]

    @classmethod
    def from_bindings(cls, bindings: tuple[AbilityHandlerBinding, ...]) -> Self:
        if type(bindings) is not tuple:
            raise GameLifecycleError("AbilityHandlerRegistry bindings must be a tuple.")
        handlers: dict[str, AbilityHandlerBinding] = {}
        for binding in cast(tuple[object, ...], bindings):
            if type(binding) is not AbilityHandlerBinding:
                raise GameLifecycleError(
                    "AbilityHandlerRegistry bindings must contain AbilityHandlerBinding values."
                )
            if binding.handler_id in handlers:
                raise GameLifecycleError("AbilityHandlerRegistry must not contain duplicate IDs.")
            handlers[binding.handler_id] = binding
        return cls(_handlers=MappingProxyType(handlers))

    @classmethod
    def empty(cls) -> Self:
        return cls.from_bindings(())

    def with_handler(
        self,
        *,
        handler_id: str,
        timing: AbilityTimingDescriptor,
        handler: AbilityHandler,
        required_input_keys: tuple[str, ...] = (),
    ) -> Self:
        binding = AbilityHandlerBinding(
            handler_id=handler_id,
            timing=timing,
            required_input_keys=required_input_keys,
            handler=handler,
        )
        return self.from_bindings((*tuple(self._handlers.values()), binding))

    def all_bindings(self) -> tuple[AbilityHandlerBinding, ...]:
        return tuple(sorted(self._handlers.values(), key=lambda binding: binding.handler_id))

    def execute(
        self,
        *,
        record: AbilityCatalogRecord,
        context: AbilityExecutionContext,
    ) -> AbilityResolutionResult:
        _validate_catalog_record(record)
        if type(context) is not AbilityExecutionContext:
            raise GameLifecycleError("Ability execution requires an AbilityExecutionContext.")
        if record.disabled:
            return AbilityResolutionResult.unsupported(record, reason="ability_disabled")
        if not record.definition.timing.matches(context):
            return AbilityResolutionResult.invalid(record, reason="timing_window_mismatch")
        if not record.definition.keyword_gate.matches(context.source_keywords):
            return AbilityResolutionResult.invalid(record, reason="keyword_gate_closed")
        if record.definition.handler_id.startswith("unsupported:"):
            return AbilityResolutionResult.unsupported(record, reason="unsupported_handler")
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID:
            return _generic_rule_ir_ability_handler(record, context)
        binding = self._handlers.get(record.definition.handler_id)
        if binding is None:
            return AbilityResolutionResult.unsupported(record, reason="missing_handler")
        if not binding.timing.matches(context):
            return AbilityResolutionResult.invalid(record, reason="handler_timing_window_mismatch")
        missing_input_keys = _missing_required_input_keys(
            context=context,
            required_input_keys=(
                *record.definition.required_input_keys,
                *binding.required_input_keys,
            ),
        )
        if missing_input_keys:
            return AbilityResolutionResult.invalid(
                record,
                reason=f"missing_input:{','.join(missing_input_keys)}",
            )
        result = binding.handler(record, context)
        if type(result) is not AbilityResolutionResult:
            raise GameLifecycleError("Ability handler must return AbilityResolutionResult.")
        _validate_result_matches_record(result=result, record=record)
        return result


def default_ability_handler_registry() -> AbilityHandlerRegistry:
    return (
        AbilityHandlerRegistry.empty()
        .with_handler(
            handler_id=CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID,
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler=_movement_keyword_gate_handler,
        )
        .with_handler(
            handler_id=CORE_HAZARDOUS_HANDLER_ID,
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
            handler=_hazardous_keyword_handler,
        )
    )


def ability_records_for_context(
    *,
    records: tuple[AbilityCatalogRecord, ...],
    context: AbilityExecutionContext,
) -> tuple[AbilityCatalogRecord, ...]:
    validated_records = _validate_catalog_records(records)
    return _ability_records_for_context(records=validated_records, context=context)


def ability_records_for_context_from_index(
    *,
    index: AbilityCatalogIndex,
    context: AbilityExecutionContext,
) -> tuple[AbilityCatalogRecord, ...]:
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Ability lookup requires an AbilityCatalogIndex.")
    if type(context) is not AbilityExecutionContext:
        raise GameLifecycleError("Ability lookup requires an AbilityExecutionContext.")
    return _ability_records_for_context(
        records=index.records_for(context.trigger_kind),
        context=context,
    )


def execute_abilities_from_index(
    *,
    registry: AbilityHandlerRegistry,
    index: AbilityCatalogIndex,
    context: AbilityExecutionContext,
) -> tuple[AbilityResolutionResult, ...]:
    if type(registry) is not AbilityHandlerRegistry:
        raise GameLifecycleError("Ability execution requires an AbilityHandlerRegistry.")
    records = ability_records_for_context_from_index(index=index, context=context)
    return tuple(registry.execute(record=record, context=context) for record in records)


def movement_capability_flags_from_index(
    *,
    index: AbilityCatalogIndex,
    keywords: tuple[str, ...],
    registry: AbilityHandlerRegistry | None = None,
) -> tuple[str, ...]:
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Movement capability lookup requires an AbilityCatalogIndex.")
    resolved_registry = default_ability_handler_registry() if registry is None else registry
    if type(resolved_registry) is not AbilityHandlerRegistry:
        raise GameLifecycleError("Movement capability lookup requires an AbilityHandlerRegistry.")
    context = AbilityExecutionContext.passive_keyword_gate(source_keywords=keywords)
    flags: list[str] = []
    seen: set[str] = set()
    for record in ability_records_for_context_from_index(index=index, context=context):
        if record.definition.handler_id != CORE_MOVEMENT_KEYWORD_GATE_HANDLER_ID:
            continue
        result = resolved_registry.execute(record=record, context=context)
        for raw_flag in movement_capability_flags_from_result(result):
            flag = _validate_identifier("movement capability flag", raw_flag)
            if flag not in seen:
                seen.add(flag)
                flags.append(flag)
    return tuple(sorted(flags))


def movement_capability_flags_from_result(
    result: AbilityResolutionResult,
) -> tuple[str, ...]:
    if type(result) is not AbilityResolutionResult:
        raise GameLifecycleError("Movement capability flags require an AbilityResolutionResult.")
    if result.status is not AbilityResolutionStatus.APPLIED:
        return ()
    payload = result.replay_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Movement keyword handler requires a replay payload mapping.")
    raw_effect_payload = payload.get("effect_payload")
    if not isinstance(raw_effect_payload, dict):
        raise GameLifecycleError("Movement keyword handler requires an effect payload mapping.")
    raw_flags = raw_effect_payload.get(MOVEMENT_CAPABILITY_FLAGS_PAYLOAD_KEY)
    if not isinstance(raw_flags, list):
        raise GameLifecycleError("Movement keyword handler requires capability flags.")
    return tuple(
        sorted(_validate_identifier("movement capability flag", flag) for flag in raw_flags)
    )


def ability_source_kind_from_token(token: object) -> AbilitySourceKind:
    if type(token) is AbilitySourceKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AbilitySourceKind token must be a string.")
    try:
        return AbilitySourceKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported AbilitySourceKind token: {token}.") from exc


def ability_resolution_status_from_token(token: object) -> AbilityResolutionStatus:
    if type(token) is AbilityResolutionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AbilityResolutionStatus token must be a string.")
    try:
        return AbilityResolutionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported AbilityResolutionStatus token: {token}.") from exc


def _movement_keyword_gate_handler(
    record: AbilityCatalogRecord,
    context: AbilityExecutionContext,
) -> AbilityResolutionResult:
    return AbilityResolutionResult.applied(
        record,
        replay_payload={
            "source_id": record.definition.source_id,
            "trigger_kind": context.trigger_kind.value,
            "source_keywords": list(context.source_keywords),
            "effect_payload": record.definition.replay_payload,
        },
    )


def _hazardous_keyword_handler(
    record: AbilityCatalogRecord,
    context: AbilityExecutionContext,
) -> AbilityResolutionResult:
    return AbilityResolutionResult.applied(
        record,
        replay_payload={
            "source_id": record.definition.source_id,
            "trigger_kind": context.trigger_kind.value,
            "source_keywords": list(context.source_keywords),
            "effect_payload": {
                "effect_kind": "hazardous_weapon_test",
                "resolved_by": "attack_sequence",
            },
        },
    )


def _generic_rule_ir_ability_handler(
    record: AbilityCatalogRecord,
    context: AbilityExecutionContext,
) -> AbilityResolutionResult:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionContext,
        RuleExecutionStatus,
        execute_rule_ir,
        rule_ir_from_execution_payload,
    )

    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            timing_window_id=context.timing_window_id,
            source_unit_instance_id=context.source_unit_instance_id,
            source_model_instance_id=context.source_model_instance_id,
            target_unit_instance_ids=(
                ()
                if context.target_unit_instance_id is None
                else (context.target_unit_instance_id,)
            ),
            source_keywords=context.source_keywords,
            trigger_payload=context.trigger_payload,
        ),
    )
    if result.status is RuleExecutionStatus.APPLIED:
        return AbilityResolutionResult.applied(
            record,
            replay_payload=validate_json_value({"rule_execution": result.to_payload()}),
        )
    if result.status is RuleExecutionStatus.INVALID:
        if result.reason is None:
            raise GameLifecycleError("Invalid generic ability execution is missing reason.")
        return AbilityResolutionResult.invalid(record, reason=result.reason)
    if result.reason is None:
        raise GameLifecycleError("Unsupported generic ability execution is missing reason.")
    return AbilityResolutionResult.unsupported(record, reason=result.reason)


def _ability_records_for_context(
    *,
    records: tuple[AbilityCatalogRecord, ...],
    context: AbilityExecutionContext,
) -> tuple[AbilityCatalogRecord, ...]:
    if type(context) is not AbilityExecutionContext:
        raise GameLifecycleError("Ability lookup requires an AbilityExecutionContext.")
    return tuple(
        record
        for record in records
        if not record.disabled
        and record.definition.timing.matches(context)
        and record.definition.keyword_gate.matches(context.source_keywords)
    )


def _missing_required_input_keys(
    *,
    context: AbilityExecutionContext,
    required_input_keys: tuple[str, ...],
) -> tuple[str, ...]:
    keys = _validate_identifier_tuple("Ability handler required_input_keys", required_input_keys)
    if not keys:
        return ()
    if not isinstance(context.trigger_payload, dict):
        return keys
    return tuple(key for key in keys if key not in context.trigger_payload)


def _validate_result_matches_record(
    *,
    result: AbilityResolutionResult,
    record: AbilityCatalogRecord,
) -> None:
    if result.record_id != record.record_id:
        raise GameLifecycleError("AbilityResolutionResult record_id drift.")
    if result.ability_id != record.definition.ability_id:
        raise GameLifecycleError("AbilityResolutionResult ability_id drift.")
    if result.handler_id != record.definition.handler_id:
        raise GameLifecycleError("AbilityResolutionResult handler_id drift.")
    if result.source_id != record.definition.source_id:
        raise GameLifecycleError("AbilityResolutionResult source_id drift.")


def _validate_catalog_records(
    records: tuple[AbilityCatalogRecord, ...],
) -> tuple[AbilityCatalogRecord, ...]:
    if type(records) is not tuple:
        raise GameLifecycleError("Ability catalog records must be a tuple.")
    validated: list[AbilityCatalogRecord] = []
    seen: set[str] = set()
    for record in cast(tuple[object, ...], records):
        validated_record = _validate_catalog_record(record)
        if validated_record.record_id in seen:
            raise GameLifecycleError("Ability catalog records must not contain duplicate IDs.")
        seen.add(validated_record.record_id)
        validated.append(validated_record)
    return tuple(sorted(validated, key=lambda value: value.record_id))


def _validate_catalog_record(record: object) -> AbilityCatalogRecord:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError(
            "Ability catalog records must contain AbilityCatalogRecord values."
        )
    return record


def _validate_source_owner_shape(record: AbilityCatalogRecord) -> None:
    source_kind = record.source_kind
    owner_fields = (
        record.faction_id,
        record.detachment_id,
        record.datasheet_id,
        record.wargear_id,
        record.weapon_profile_id,
    )
    if source_kind in {AbilitySourceKind.CORE, AbilitySourceKind.KEYWORD}:
        if any(owner is not None for owner in owner_fields):
            raise GameLifecycleError("Core and keyword AbilityCatalogRecords cannot own IDs.")
        return
    if source_kind is AbilitySourceKind.FACTION and record.faction_id is None:
        raise GameLifecycleError("Faction AbilityCatalogRecord requires faction_id.")
    if source_kind is AbilitySourceKind.DETACHMENT and record.detachment_id is None:
        raise GameLifecycleError("Detachment AbilityCatalogRecord requires detachment_id.")
    if source_kind is AbilitySourceKind.DATASHEET and record.datasheet_id is None:
        raise GameLifecycleError("Datasheet AbilityCatalogRecord requires datasheet_id.")
    if source_kind is AbilitySourceKind.ENHANCEMENT and record.detachment_id is None:
        raise GameLifecycleError("Enhancement AbilityCatalogRecord requires detachment_id.")
    if source_kind is AbilitySourceKind.WARGEAR and record.wargear_id is None:
        raise GameLifecycleError("Wargear AbilityCatalogRecord requires wargear_id.")
    if (
        source_kind is AbilitySourceKind.WEAPON
        and record.weapon_profile_id is None
        and record.definition.keyword_gate.is_empty
    ):
        raise GameLifecycleError(
            "Weapon AbilityCatalogRecord requires weapon_profile_id or keyword gate."
        )


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    if type(value) is BattlePhaseKind:
        return value
    try:
        return battle_phase_kind_from_token(value)
    except RulesetDescriptorError as exc:
        raise GameLifecycleError(f"{field_name} is invalid.") from exc


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_keyword(f"{field_name} keyword", value)
        if keyword in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate keywords.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


def _validate_keyword(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value).upper().replace(" ", "_").replace("-", "_")


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
