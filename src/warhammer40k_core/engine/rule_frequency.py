from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleIR,
    RuleParameterValue,
    parameter_payload,
)

OPTIONAL_ABILITY_USE_ACTIVATION_KIND = "optional_ability_use"
RULE_FREQUENCY_LIMIT_CONSUMED_EVENT = "rule_frequency_limit_consumed"


class OptionalAbilityFrequencyUsagePayload(TypedDict):
    usage_key: str
    rule_id: str
    source_id: str
    rule_ir_hash: str
    clause_id: str
    player_id: str
    source_unit_instance_id: str | None
    source_model_instance_id: str | None
    activation_kind: str
    usage_subject: str
    scope: str
    max_uses: int


class OptionalAbilityFrequencyEventPayload(OptionalAbilityFrequencyUsagePayload):
    battle_round: int
    phase: str | None
    active_player_id: str | None
    timing_window_id: str | None


_OPTIONAL_ABILITY_FREQUENCY_USAGE_PAYLOAD_KEYS = frozenset(
    OptionalAbilityFrequencyUsagePayload.__required_keys__
)
_OPTIONAL_ABILITY_FREQUENCY_EVENT_PAYLOAD_KEYS = frozenset(
    OptionalAbilityFrequencyEventPayload.__required_keys__
)


@dataclass(frozen=True, slots=True)
class OptionalAbilityFrequencyUsage:
    usage_key: str
    rule_id: str
    source_id: str
    rule_ir_hash: str
    clause_id: str
    player_id: str
    source_unit_instance_id: str | None
    source_model_instance_id: str | None
    activation_kind: str
    usage_subject: str
    scope: str
    max_uses: int

    def __post_init__(self) -> None:
        for field_name in (
            "usage_key",
            "rule_id",
            "source_id",
            "rule_ir_hash",
            "clause_id",
            "player_id",
            "activation_kind",
            "usage_subject",
            "scope",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        for field_name in ("source_unit_instance_id", "source_model_instance_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        if self.activation_kind != OPTIONAL_ABILITY_USE_ACTIVATION_KIND:
            raise GameLifecycleError("Optional ability frequency activation_kind drift.")
        if self.usage_subject not in {"this_model", "this_unit", "bearer"}:
            raise GameLifecycleError("Optional ability frequency usage_subject is unsupported.")
        if self.scope != "battle":
            raise GameLifecycleError("Optional ability frequency scope must be battle.")
        if type(self.max_uses) is not int or self.max_uses != 1:
            raise GameLifecycleError("Optional ability frequency max_uses must be 1.")
        if self.usage_subject in {"this_model", "bearer"}:
            if self.source_model_instance_id is None:
                raise GameLifecycleError(
                    "Model-scoped optional ability frequency requires source_model_instance_id."
                )
        elif self.source_unit_instance_id is None:
            raise GameLifecycleError(
                "Unit-scoped optional ability frequency requires source_unit_instance_id."
            )
        expected_usage_key = _canonical_optional_ability_frequency_usage_key(
            rule_id=self.rule_id,
            source_id=self.source_id,
            rule_ir_hash=self.rule_ir_hash,
            clause_id=self.clause_id,
            player_id=self.player_id,
            source_unit_instance_id=self.source_unit_instance_id,
            source_model_instance_id=self.source_model_instance_id,
            activation_kind=self.activation_kind,
            usage_subject=self.usage_subject,
            scope=self.scope,
            max_uses=self.max_uses,
        )
        if self.usage_key != expected_usage_key:
            raise GameLifecycleError(
                "Optional ability frequency usage_key does not match its canonical metadata."
            )

    def to_payload(self) -> OptionalAbilityFrequencyUsagePayload:
        return {
            "usage_key": self.usage_key,
            "rule_id": self.rule_id,
            "source_id": self.source_id,
            "rule_ir_hash": self.rule_ir_hash,
            "clause_id": self.clause_id,
            "player_id": self.player_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "source_model_instance_id": self.source_model_instance_id,
            "activation_kind": self.activation_kind,
            "usage_subject": self.usage_subject,
            "scope": self.scope,
            "max_uses": self.max_uses,
        }

    @classmethod
    def from_payload(cls, payload: OptionalAbilityFrequencyUsagePayload) -> Self:
        _validate_optional_ability_frequency_usage_payload(payload)
        return cls(
            usage_key=payload["usage_key"],
            rule_id=payload["rule_id"],
            source_id=payload["source_id"],
            rule_ir_hash=payload["rule_ir_hash"],
            clause_id=payload["clause_id"],
            player_id=payload["player_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            source_model_instance_id=payload["source_model_instance_id"],
            activation_kind=payload["activation_kind"],
            usage_subject=payload["usage_subject"],
            scope=payload["scope"],
            max_uses=payload["max_uses"],
        )


def optional_ability_frequency_condition(clause: RuleClause) -> RuleCondition | None:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Rule frequency lookup requires RuleClause.")
    matches = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
        and parameter_payload(condition.parameters).get("activation_kind")
        == OPTIONAL_ABILITY_USE_ACTIVATION_KIND
    )
    if len(matches) > 1:
        raise GameLifecycleError("Rule clause has multiple optional ability frequency limits.")
    if not matches:
        return None
    _validated_frequency_parameters(matches[0])
    return matches[0]


def optional_ability_frequency_unavailable_reason(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    event_log: EventLog | None,
    player_id: str,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
) -> str | None:
    usage = optional_ability_frequency_usage(
        rule_ir=rule_ir,
        clause=clause,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    if usage is None:
        return None
    return optional_ability_frequency_usage_unavailable_reason(
        usage=usage,
        event_log=event_log,
    )


def optional_ability_frequency_usage_unavailable_reason(
    *,
    usage: OptionalAbilityFrequencyUsage,
    event_log: EventLog | None,
) -> str | None:
    if type(usage) is not OptionalAbilityFrequencyUsage:
        raise GameLifecycleError("Rule frequency lookup requires typed usage metadata.")
    if event_log is None:
        return "missing_input:event_log"
    used_count = sum(
        1 for record in event_log.records if _frequency_event_usage_key(record) == usage.usage_key
    )
    if used_count >= usage.max_uses:
        return "frequency_limit_exhausted:battle"
    return None


def consume_optional_ability_frequency(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    event_log: EventLog | None,
    player_id: str,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
    battle_round: int,
    phase: BattlePhaseKind | None,
    active_player_id: str | None,
    timing_window_id: str | None,
) -> tuple[EventRecord, ...]:
    usage = optional_ability_frequency_usage(
        rule_ir=rule_ir,
        clause=clause,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    if usage is None:
        return ()
    return consume_optional_ability_frequency_usage(
        usage=usage,
        event_log=event_log,
        battle_round=battle_round,
        phase=phase,
        active_player_id=active_player_id,
        timing_window_id=timing_window_id,
    )


def consume_optional_ability_frequency_usage(
    *,
    usage: OptionalAbilityFrequencyUsage,
    event_log: EventLog | None,
    battle_round: int,
    phase: BattlePhaseKind | None,
    active_player_id: str | None,
    timing_window_id: str | None,
) -> tuple[EventRecord, ...]:
    if type(usage) is not OptionalAbilityFrequencyUsage:
        raise GameLifecycleError("Rule frequency consumption requires typed usage metadata.")
    unavailable = optional_ability_frequency_usage_unavailable_reason(
        usage=usage,
        event_log=event_log,
    )
    if unavailable is not None:
        raise GameLifecycleError(f"Cannot consume RuleIR frequency limit: {unavailable}.")
    if event_log is None:
        raise GameLifecycleError("RuleIR frequency consumption requires EventLog.")
    return (
        event_log.append(
            RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
            {
                **usage.to_payload(),
                "battle_round": battle_round,
                "phase": None if phase is None else phase.value,
                "active_player_id": active_player_id,
                "timing_window_id": timing_window_id,
            },
        ),
    )


def optional_ability_frequency_usage_key(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    player_id: str,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
) -> str:
    usage = optional_ability_frequency_usage(
        rule_ir=rule_ir,
        clause=clause,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    if usage is None:
        raise GameLifecycleError("Rule frequency key requires optional ability frequency limit.")
    return usage.usage_key


def optional_ability_frequency_usage(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    player_id: str,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
) -> OptionalAbilityFrequencyUsage | None:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Rule frequency key requires RuleIR.")
    condition = optional_ability_frequency_condition(clause)
    if condition is None:
        return None
    parameters = _validated_frequency_parameters(condition)
    player = _validate_identifier("player_id", player_id)
    usage_subject = parameters["usage_subject"]
    validated_source_unit_id = (
        None
        if source_unit_instance_id is None
        else _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    )
    validated_source_model_id = (
        None
        if source_model_instance_id is None
        else _validate_identifier("source_model_instance_id", source_model_instance_id)
    )
    if usage_subject in {"this_model", "bearer"}:
        _validate_identifier("source_model_instance_id", validated_source_model_id)
    elif validated_source_unit_id is None:
        raise GameLifecycleError(
            "Unit-scoped optional ability frequency requires source_unit_instance_id."
        )
    activation_kind = parameters["activation_kind"]
    scope = parameters["scope"]
    max_uses = parameters["max_uses"]
    if type(activation_kind) is not str or type(usage_subject) is not str or type(scope) is not str:
        raise GameLifecycleError("Optional ability frequency string parameters drifted.")
    if type(max_uses) is not int:
        raise GameLifecycleError("Optional ability frequency max_uses must be an int.")
    rule_ir_hash = rule_ir.ir_hash()
    usage_key = _canonical_optional_ability_frequency_usage_key(
        rule_id=rule_ir.rule_id,
        source_id=rule_ir.source_id,
        rule_ir_hash=rule_ir_hash,
        clause_id=clause.clause_id,
        player_id=player,
        source_unit_instance_id=validated_source_unit_id,
        source_model_instance_id=validated_source_model_id,
        activation_kind=activation_kind,
        usage_subject=usage_subject,
        scope=scope,
        max_uses=max_uses,
    )
    return OptionalAbilityFrequencyUsage(
        usage_key=usage_key,
        rule_id=rule_ir.rule_id,
        source_id=rule_ir.source_id,
        rule_ir_hash=rule_ir_hash,
        clause_id=clause.clause_id,
        player_id=player,
        source_unit_instance_id=validated_source_unit_id,
        source_model_instance_id=validated_source_model_id,
        activation_kind=activation_kind,
        usage_subject=usage_subject,
        scope=scope,
        max_uses=max_uses,
    )


def _canonical_optional_ability_frequency_usage_key(
    *,
    rule_id: str,
    source_id: str,
    rule_ir_hash: str,
    clause_id: str,
    player_id: str,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
    activation_kind: str,
    usage_subject: str,
    scope: str,
    max_uses: int,
) -> str:
    canonical = json.dumps(
        {
            "activation_kind": activation_kind,
            "clause_id": clause_id,
            "max_uses": max_uses,
            "player_id": player_id,
            "rule_id": rule_id,
            "rule_ir_hash": rule_ir_hash,
            "scope": scope,
            "source_id": source_id,
            "source_model_instance_id": source_model_instance_id,
            "source_unit_instance_id": source_unit_instance_id,
            "usage_subject": usage_subject,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"rule-frequency:{hashlib.sha256(canonical).hexdigest()}"


def _validated_frequency_parameters(condition: RuleCondition) -> dict[str, RuleParameterValue]:
    parameters = parameter_payload(condition.parameters)
    if parameters.get("activation_kind") != OPTIONAL_ABILITY_USE_ACTIVATION_KIND:
        raise GameLifecycleError("Optional ability frequency activation_kind drift.")
    if parameters.get("scope") != "battle":
        raise GameLifecycleError("Optional ability frequency scope must be battle.")
    if parameters.get("max_uses") != 1:
        raise GameLifecycleError("Optional ability frequency max_uses must be 1.")
    if parameters.get("usage_subject") not in {"this_model", "this_unit", "bearer"}:
        raise GameLifecycleError("Optional ability frequency usage_subject is unsupported.")
    return dict(parameters)


def _frequency_event_usage_key(record: EventRecord) -> str | None:
    if record.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT:
        return None
    if not isinstance(record.payload, dict):
        raise GameLifecycleError("Rule frequency event payload must be an object.")
    if set(record.payload) != set(_OPTIONAL_ABILITY_FREQUENCY_EVENT_PAYLOAD_KEYS):
        raise GameLifecycleError("Rule frequency event payload requires its exact typed metadata.")
    usage_payload = {
        key: record.payload[key] for key in _OPTIONAL_ABILITY_FREQUENCY_USAGE_PAYLOAD_KEYS
    }
    usage = OptionalAbilityFrequencyUsage.from_payload(
        cast(OptionalAbilityFrequencyUsagePayload, usage_payload)
    )
    battle_round = record.payload["battle_round"]
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Rule frequency event battle_round must be at least 1.")
    phase = record.payload["phase"]
    if phase is not None:
        if type(phase) is not str:
            raise GameLifecycleError("Rule frequency event phase must be a string or null.")
        try:
            BattlePhaseKind(phase)
        except ValueError as exc:
            raise GameLifecycleError("Rule frequency event phase is unsupported.") from exc
    for field_name in ("active_player_id", "timing_window_id"):
        value = record.payload[field_name]
        if value is not None:
            _validate_identifier(field_name, value)
    return usage.usage_key


def _validate_optional_ability_frequency_usage_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise GameLifecycleError(
            "Optional ability frequency usage payload requires its exact schema."
        )
    payload_mapping = cast(Mapping[object, object], payload)
    if set(payload_mapping) != set(_OPTIONAL_ABILITY_FREQUENCY_USAGE_PAYLOAD_KEYS):
        raise GameLifecycleError(
            "Optional ability frequency usage payload requires its exact schema."
        )


_validate_identifier = IdentifierValidator(GameLifecycleError)
