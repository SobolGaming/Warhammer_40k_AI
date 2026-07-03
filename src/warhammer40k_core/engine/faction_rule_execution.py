from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionResult,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)


class FactionRuleExecutionStatus(StrEnum):
    APPLIED = "applied"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class FactionRuleExecutionContextPayload(TypedDict):
    game_id: str
    player_id: str
    battle_round: int
    phase: str | None
    active_player_id: str | None
    source_unit_instance_id: str | None
    target_unit_instance_ids: list[str]
    trigger_payload: JsonValue


class FactionRuleExecutionResultPayload(TypedDict):
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: str
    faction_id: str
    faction_name: str
    detachment_id: str | None
    detachment_name: str | None
    handler_id: str | None
    source_ids: list[str]
    status: str
    reason: str | None
    replay_payload: JsonValue


@dataclass(frozen=True, slots=True)
class FactionRuleExecutionContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind | None
    active_player_id: str | None
    source_unit_instance_id: str | None = None
    target_unit_instance_ids: tuple[str, ...] = ()
    trigger_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", _validate_optional_phase("phase", self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_optional_identifier("source_unit_instance_id", self.source_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "target_unit_instance_ids",
                self.target_unit_instance_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(self, "trigger_payload", validate_json_value(self.trigger_payload))

    def to_payload(self) -> FactionRuleExecutionContextPayload:
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": None if self.phase is None else self.phase.value,
            "active_player_id": self.active_player_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
            "trigger_payload": self.trigger_payload,
        }

    @classmethod
    def from_payload(cls, payload: FactionRuleExecutionContextPayload) -> Self:
        phase = payload["phase"]
        return cls(
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=None if phase is None else battle_phase_kind_from_token(phase),
            active_player_id=payload["active_player_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            target_unit_instance_ids=tuple(payload["target_unit_instance_ids"]),
            trigger_payload=payload["trigger_payload"],
        )


@dataclass(frozen=True, slots=True)
class FactionRuleExecutionResult:
    execution_id: str
    coverage_descriptor_id: str
    coverage_kind: str
    faction_id: str
    faction_name: str
    source_ids: tuple[str, ...]
    status: FactionRuleExecutionStatus
    reason: str | None = None
    detachment_id: str | None = None
    detachment_name: str | None = None
    handler_id: str | None = None
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_id",
            _validate_identifier("execution_id", self.execution_id),
        )
        object.__setattr__(
            self,
            "coverage_descriptor_id",
            _validate_identifier("coverage_descriptor_id", self.coverage_descriptor_id),
        )
        object.__setattr__(
            self,
            "coverage_kind",
            _validate_identifier("coverage_kind", self.coverage_kind),
        )
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(
            self,
            "faction_name",
            _validate_non_empty_text("faction_name", self.faction_name),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )
        object.__setattr__(self, "status", _execution_status_from_token(self.status))
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("reason", self.reason),
        )
        if self.detachment_id is not None:
            object.__setattr__(
                self,
                "detachment_id",
                _validate_identifier("detachment_id", self.detachment_id),
            )
        if self.detachment_name is not None:
            object.__setattr__(
                self,
                "detachment_name",
                _validate_non_empty_text("detachment_name", self.detachment_name),
            )
        if self.handler_id is not None:
            object.__setattr__(
                self,
                "handler_id",
                _validate_identifier("handler_id", self.handler_id),
            )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        if self.status is FactionRuleExecutionStatus.APPLIED and self.reason is not None:
            raise GameLifecycleError("Applied faction-rule execution cannot include reason.")
        if self.status is not FactionRuleExecutionStatus.APPLIED and self.reason is None:
            raise GameLifecycleError("Non-applied faction-rule execution requires reason.")

    @classmethod
    def unsupported(
        cls,
        *,
        record: Phase17FExecutionRecord,
        reason: str,
        context: FactionRuleExecutionContext,
    ) -> Self:
        return cls(
            execution_id=record.execution_id,
            coverage_descriptor_id=record.coverage_descriptor_id,
            coverage_kind=record.coverage_kind.value,
            faction_id=record.faction_id,
            faction_name=record.faction_name,
            detachment_id=record.detachment_id,
            detachment_name=record.detachment_name,
            handler_id=record.handler_id,
            source_ids=record.source_ids,
            status=FactionRuleExecutionStatus.UNSUPPORTED,
            reason=reason,
            replay_payload=_replay_payload(record=record, context=context),
        )

    @classmethod
    def applied(
        cls,
        *,
        record: Phase17FExecutionRecord,
        context: FactionRuleExecutionContext,
        replay_payload: JsonValue = None,
    ) -> Self:
        return cls(
            execution_id=record.execution_id,
            coverage_descriptor_id=record.coverage_descriptor_id,
            coverage_kind=record.coverage_kind.value,
            faction_id=record.faction_id,
            faction_name=record.faction_name,
            detachment_id=record.detachment_id,
            detachment_name=record.detachment_name,
            handler_id=record.handler_id,
            source_ids=record.source_ids,
            status=FactionRuleExecutionStatus.APPLIED,
            replay_payload=(
                _replay_payload(record=record, context=context)
                if replay_payload is None
                else replay_payload
            ),
        )

    @classmethod
    def invalid(
        cls,
        *,
        record: Phase17FExecutionRecord,
        reason: str,
        context: FactionRuleExecutionContext,
        replay_payload: JsonValue = None,
    ) -> Self:
        return cls(
            execution_id=record.execution_id,
            coverage_descriptor_id=record.coverage_descriptor_id,
            coverage_kind=record.coverage_kind.value,
            faction_id=record.faction_id,
            faction_name=record.faction_name,
            detachment_id=record.detachment_id,
            detachment_name=record.detachment_name,
            handler_id=record.handler_id,
            source_ids=record.source_ids,
            status=FactionRuleExecutionStatus.INVALID,
            reason=reason,
            replay_payload=(
                _replay_payload(record=record, context=context)
                if replay_payload is None
                else replay_payload
            ),
        )

    def to_payload(self) -> FactionRuleExecutionResultPayload:
        return {
            "execution_id": self.execution_id,
            "coverage_descriptor_id": self.coverage_descriptor_id,
            "coverage_kind": self.coverage_kind,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "handler_id": self.handler_id,
            "source_ids": list(self.source_ids),
            "status": self.status.value,
            "reason": self.reason,
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: FactionRuleExecutionResultPayload) -> Self:
        return cls(
            execution_id=payload["execution_id"],
            coverage_descriptor_id=payload["coverage_descriptor_id"],
            coverage_kind=payload["coverage_kind"],
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            handler_id=payload["handler_id"],
            source_ids=tuple(payload["source_ids"]),
            status=_execution_status_from_token(payload["status"]),
            reason=payload["reason"],
            replay_payload=payload["replay_payload"],
        )


FactionRuleNamedHandler = Callable[
    [Phase17FExecutionRecord, FactionRuleExecutionContext],
    FactionRuleExecutionResult,
]
FactionRuleGenericIrExecutor = Callable[
    [Phase17FExecutionRecord, FactionRuleExecutionContext],
    FactionRuleExecutionResult,
]


@dataclass(frozen=True, slots=True)
class FactionRuleExecutionRegistry:
    _records_by_execution_id: Mapping[str, Phase17FExecutionRecord]
    _named_handlers: Mapping[str, FactionRuleNamedHandler]
    _generic_ir_executor: FactionRuleGenericIrExecutor | None = None

    @classmethod
    def from_records(
        cls,
        records: tuple[Phase17FExecutionRecord, ...],
        *,
        named_handlers: Mapping[str, FactionRuleNamedHandler] | None = None,
        generic_ir_executor: FactionRuleGenericIrExecutor | None = None,
    ) -> Self:
        if type(records) is not tuple:
            raise GameLifecycleError("FactionRuleExecutionRegistry records must be a tuple.")
        mapped: dict[str, Phase17FExecutionRecord] = {}
        for record in records:
            if type(record) is not Phase17FExecutionRecord:
                raise GameLifecycleError(
                    "FactionRuleExecutionRegistry records must contain Phase17FExecutionRecord."
                )
            if record.execution_id in mapped:
                raise GameLifecycleError("FactionRuleExecutionRegistry record IDs must be unique.")
            mapped[record.execution_id] = record
        return cls(
            _records_by_execution_id=MappingProxyType(mapped),
            _named_handlers=_validate_named_handlers(named_handlers),
            _generic_ir_executor=_validate_generic_ir_executor(generic_ir_executor),
        )

    def all_records(self) -> tuple[Phase17FExecutionRecord, ...]:
        return tuple(
            sorted(self._records_by_execution_id.values(), key=lambda row: row.execution_id)
        )

    def record_by_execution_id(self, execution_id: str) -> Phase17FExecutionRecord:
        validated_id = _validate_identifier("execution_id", execution_id)
        record = self._records_by_execution_id.get(validated_id)
        if record is None:
            raise GameLifecycleError("FactionRuleExecutionRegistry missing execution record.")
        return record

    def execute(
        self,
        *,
        execution_id: str,
        context: FactionRuleExecutionContext,
    ) -> FactionRuleExecutionResult:
        if type(context) is not FactionRuleExecutionContext:
            raise GameLifecycleError("Faction rule execution requires a context.")
        record = self.record_by_execution_id(execution_id)
        if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED:
            return FactionRuleExecutionResult.unsupported(
                record=record,
                reason="structured_rule_semantics_required",
                context=context,
            )
        if (
            record.execution_status
            is Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP
        ):
            if record.phase17e_unsupported_reason is None:
                raise GameLifecycleError("Source-gap execution record lacks Phase17E reason.")
            return FactionRuleExecutionResult.unsupported(
                record=record,
                reason=f"approved_phase17e_source_gap:{record.phase17e_unsupported_reason}",
                context=context,
            )
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR:
            if self._generic_ir_executor is None:
                return FactionRuleExecutionResult.unsupported(
                    record=record,
                    reason="generic_ir_executor_not_registered",
                    context=context,
                )
            return _validate_executor_result(
                record=record,
                result=self._generic_ir_executor(record, context),
            )
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER:
            if record.handler_id is None:
                raise GameLifecycleError("Executable named-handler record lacks handler_id.")
            handler = self._named_handlers.get(record.handler_id)
            if handler is None:
                return FactionRuleExecutionResult.unsupported(
                    record=record,
                    reason="named_handler_not_registered",
                    context=context,
                )
            return _validate_executor_result(record=record, result=handler(record, context))
        raise GameLifecycleError("Unsupported Phase17F execution status.")


def default_faction_rule_execution_registry() -> FactionRuleExecutionRegistry:
    return FactionRuleExecutionRegistry.from_records(
        faction_execution_2026_27.execution_records(),
        generic_ir_executor=_generic_rule_ir_executor,
    )


def _generic_rule_ir_executor(
    record: Phase17FExecutionRecord,
    context: FactionRuleExecutionContext,
) -> FactionRuleExecutionResult:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    if record.rule_ir_hash != rule_ir.ir_hash():
        raise GameLifecycleError("Generic faction-rule execution record has stale rule_ir_hash.")
    rule_result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            source_unit_instance_id=context.source_unit_instance_id,
            target_unit_instance_ids=context.target_unit_instance_ids,
            trigger_payload=context.trigger_payload,
        ),
    )
    return _faction_result_from_rule_execution_result(
        record=record,
        context=context,
        rule_result=rule_result,
    )


def _faction_result_from_rule_execution_result(
    *,
    record: Phase17FExecutionRecord,
    context: FactionRuleExecutionContext,
    rule_result: RuleExecutionResult,
) -> FactionRuleExecutionResult:
    replay_payload = _replay_payload_with_rule_execution_result(
        record=record,
        context=context,
        rule_result=rule_result,
    )
    if rule_result.status is RuleExecutionStatus.APPLIED:
        return FactionRuleExecutionResult.applied(
            record=record,
            context=context,
            replay_payload=replay_payload,
        )
    if rule_result.status is RuleExecutionStatus.INVALID:
        if rule_result.reason is None:
            raise GameLifecycleError("Invalid generic rule execution lacks reason.")
        return FactionRuleExecutionResult.invalid(
            record=record,
            reason=rule_result.reason,
            context=context,
            replay_payload=replay_payload,
        )
    if rule_result.status is RuleExecutionStatus.UNSUPPORTED:
        if rule_result.reason is None:
            raise GameLifecycleError("Unsupported generic rule execution lacks reason.")
        return FactionRuleExecutionResult.unsupported(
            record=record,
            reason=rule_result.reason,
            context=context,
        )
    raise GameLifecycleError("Unsupported generic rule execution result status.")


def _replay_payload(
    *,
    record: Phase17FExecutionRecord,
    context: FactionRuleExecutionContext,
) -> JsonValue:
    return validate_json_value(
        {
            "phase": "17F",
            "execution_record": record.to_payload(),
            "context": context.to_payload(),
        }
    )


def _replay_payload_with_rule_execution_result(
    *,
    record: Phase17FExecutionRecord,
    context: FactionRuleExecutionContext,
    rule_result: RuleExecutionResult,
) -> JsonValue:
    payload = _replay_payload(record=record, context=context)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Faction-rule replay payload must be a JSON object.")
    return validate_json_value(
        {
            **payload,
            "generic_rule_execution_result": rule_result.to_payload(),
        }
    )


def _execution_status_from_token(token: object) -> FactionRuleExecutionStatus:
    if type(token) is FactionRuleExecutionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FactionRuleExecutionStatus token must be a string.")
    try:
        return FactionRuleExecutionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported FactionRuleExecutionStatus token: {token}.") from exc


def _validate_named_handlers(
    named_handlers: object | None,
) -> Mapping[str, FactionRuleNamedHandler]:
    if named_handlers is None:
        return MappingProxyType({})
    if not isinstance(named_handlers, Mapping):
        raise GameLifecycleError("FactionRuleExecutionRegistry named_handlers must be a mapping.")
    validated: dict[str, FactionRuleNamedHandler] = {}
    raw_handlers = cast(Mapping[object, object], named_handlers)
    for handler_id, handler in raw_handlers.items():
        validated_id = _validate_identifier("named handler id", handler_id)
        if not callable(handler):
            raise GameLifecycleError(
                "FactionRuleExecutionRegistry named handlers must be callable."
            )
        validated[validated_id] = cast(FactionRuleNamedHandler, handler)
    return MappingProxyType(validated)


def _validate_generic_ir_executor(
    generic_ir_executor: FactionRuleGenericIrExecutor | None,
) -> FactionRuleGenericIrExecutor | None:
    if generic_ir_executor is None:
        return None
    if not callable(generic_ir_executor):
        raise GameLifecycleError(
            "FactionRuleExecutionRegistry generic_ir_executor must be callable."
        )
    return generic_ir_executor


def _validate_executor_result(
    *,
    record: Phase17FExecutionRecord,
    result: FactionRuleExecutionResult,
) -> FactionRuleExecutionResult:
    if type(result) is not FactionRuleExecutionResult:
        raise GameLifecycleError("Faction-rule executor must return FactionRuleExecutionResult.")
    if result.execution_id != record.execution_id:
        raise GameLifecycleError("Faction-rule executor returned mismatched execution_id.")
    if result.coverage_descriptor_id != record.coverage_descriptor_id:
        raise GameLifecycleError(
            "Faction-rule executor returned mismatched coverage_descriptor_id."
        )
    if result.coverage_kind != record.coverage_kind.value:
        raise GameLifecycleError("Faction-rule executor returned mismatched coverage_kind.")
    if result.faction_id != record.faction_id:
        raise GameLifecycleError("Faction-rule executor returned mismatched faction_id.")
    if result.faction_name != record.faction_name:
        raise GameLifecycleError("Faction-rule executor returned mismatched faction_name.")
    if result.detachment_id != record.detachment_id:
        raise GameLifecycleError("Faction-rule executor returned mismatched detachment_id.")
    if result.detachment_name != record.detachment_name:
        raise GameLifecycleError("Faction-rule executor returned mismatched detachment_name.")
    if result.handler_id != record.handler_id:
        raise GameLifecycleError("Faction-rule executor returned mismatched handler_id.")
    if result.source_ids != record.source_ids:
        raise GameLifecycleError("Faction-rule executor returned mismatched source_ids.")
    return result


def _validate_optional_phase(field_name: str, value: object) -> BattlePhaseKind | None:
    if value is None:
        return None
    if type(value) is BattlePhaseKind:
        return value
    if type(value) is str:
        return battle_phase_kind_from_token(value)
    raise GameLifecycleError(f"{field_name} must be a BattlePhaseKind or None.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_non_empty_text(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int = 1,
    sort_values: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    if len(values) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)
