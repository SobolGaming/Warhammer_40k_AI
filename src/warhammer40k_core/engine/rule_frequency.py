from __future__ import annotations

import hashlib
import json

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
    condition = optional_ability_frequency_condition(clause)
    if condition is None:
        return None
    if event_log is None:
        return "missing_input:event_log"
    usage_key = optional_ability_frequency_usage_key(
        rule_ir=rule_ir,
        clause=clause,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    used_count = sum(
        1 for record in event_log.records if _frequency_event_usage_key(record) == usage_key
    )
    max_uses = _frequency_max_uses(condition)
    if used_count >= max_uses:
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
    condition = optional_ability_frequency_condition(clause)
    if condition is None:
        return ()
    unavailable = optional_ability_frequency_unavailable_reason(
        rule_ir=rule_ir,
        clause=clause,
        event_log=event_log,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    if unavailable is not None:
        raise GameLifecycleError(f"Cannot consume RuleIR frequency limit: {unavailable}.")
    if event_log is None:
        raise GameLifecycleError("RuleIR frequency consumption requires EventLog.")
    parameters = _validated_frequency_parameters(condition)
    usage_key = optional_ability_frequency_usage_key(
        rule_ir=rule_ir,
        clause=clause,
        player_id=player_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    return (
        event_log.append(
            RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
            {
                "usage_key": usage_key,
                "rule_id": rule_ir.rule_id,
                "source_id": rule_ir.source_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "clause_id": clause.clause_id,
                "player_id": player_id,
                "source_unit_instance_id": source_unit_instance_id,
                "source_model_instance_id": source_model_instance_id,
                "activation_kind": parameters["activation_kind"],
                "usage_subject": parameters["usage_subject"],
                "scope": parameters["scope"],
                "max_uses": parameters["max_uses"],
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
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Rule frequency key requires RuleIR.")
    condition = optional_ability_frequency_condition(clause)
    if condition is None:
        raise GameLifecycleError("Rule frequency key requires optional ability frequency limit.")
    parameters = _validated_frequency_parameters(condition)
    player = _validate_identifier("player_id", player_id)
    usage_subject = parameters["usage_subject"]
    if usage_subject in {"this_model", "bearer"}:
        subject_id = _validate_identifier("source_model_instance_id", source_model_instance_id)
    else:
        subject_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    canonical = json.dumps(
        {
            "clause_id": clause.clause_id,
            "player_id": player,
            "rule_ir_hash": rule_ir.ir_hash(),
            "scope": parameters["scope"],
            "subject_id": subject_id,
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


def _frequency_max_uses(condition: RuleCondition) -> int:
    max_uses = _validated_frequency_parameters(condition)["max_uses"]
    if type(max_uses) is not int:
        raise GameLifecycleError("Optional ability frequency max_uses must be an int.")
    return max_uses


def _frequency_event_usage_key(record: EventRecord) -> str | None:
    if record.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT:
        return None
    if not isinstance(record.payload, dict):
        raise GameLifecycleError("Rule frequency event payload must be an object.")
    usage_key = record.payload.get("usage_key")
    if type(usage_key) is not str:
        raise GameLifecycleError("Rule frequency event payload requires usage_key.")
    return _validate_identifier("usage_key", usage_key)


_validate_identifier = IdentifierValidator(GameLifecycleError)
