from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.secondary_scoring_provider import (
    SecondaryScoringProviderKind,
    secondary_scoring_provider_kind_from_metadata,
    validate_generic_rule_ir_secondary_award,
)
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec, RuleIR

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, RuleExecutionResult

_validate_identifier = IdentifierValidator(GameLifecycleError)

RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE = "rule_execution_victory_points_awarded"
GENERIC_RULE_IR_SOURCE_ID_KEY = "source_id"
GENERIC_RULE_IR_HASH_KEY = "rule_ir_hash"
GENERIC_RULE_IR_EFFECT_INDEX_KEY = "effect_index"
GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY = "execution_event_id"
GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY = "execution_context"


def next_generic_rule_ir_victory_point_event_id(
    *,
    event_log: object | None,
    fallback_id: str,
) -> str:
    from warhammer40k_core.engine.event_log import EventLog

    requested_fallback = _validate_identifier(
        "Generic RuleIR Secondary VP execution_event_id",
        fallback_id,
    )
    if event_log is None:
        return requested_fallback
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Generic RuleIR Secondary VP event_log must be an EventLog.")
    return f"event-{len(event_log.records) + 1:06d}"


def generic_rule_ir_secondary_award(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec,
    context: RuleExecutionContext,
    amount: int,
    execution_event_id: str,
) -> VictoryPointAward:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires RuleIR.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires a RuleClause.")
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires a RuleEffectSpec.")
    if context.phase is None:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires a phase.")
    effect_index = _effect_index(clause=clause, effect=effect)
    return VictoryPointAward(
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=context.phase.value,
        amount=amount,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id=rule_ir.source_id,
        scoring_timing="generic_rule_execution",
        metadata=validate_json_value(
            {
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                ),
                "rule_id": rule_ir.rule_id,
                GENERIC_RULE_IR_SOURCE_ID_KEY: rule_ir.source_id,
                GENERIC_RULE_IR_HASH_KEY: rule_ir.ir_hash(),
                "clause_id": clause.clause_id,
                GENERIC_RULE_IR_EFFECT_INDEX_KEY: effect_index,
                "effect": effect.to_payload(),
                GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY: _validate_identifier(
                    "Generic RuleIR Secondary VP execution_event_id",
                    execution_event_id,
                ),
                GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY: context.to_payload(),
            }
        ),
    )


def apply_generic_rule_ir_victory_points(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    from warhammer40k_core.engine.event_log import EventLog, EventRecord
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionResult,
        generic_rule_effect_payload,
    )

    if effect is None:
        raise GameLifecycleError("Rule execution handler requires an effect.")
    if context.state is None:
        raise GameLifecycleError("Rule execution requires GameState.")
    amount = _positive_delta(effect)
    if context.phase is None:
        return RuleExecutionResult.invalid(rule_ir, reason="missing_phase")
    effect_index = _effect_index(clause=clause, effect=effect)
    fallback_id = (
        f"rule-event:{rule_ir.ir_hash()[:12]}:{clause.clause_id.rsplit(':', 1)[-1]}:"
        f"{effect.kind.value}:vp"
    )
    event_id = next_generic_rule_ir_victory_point_event_id(
        event_log=context.event_log,
        fallback_id=fallback_id,
    )
    award = generic_rule_ir_secondary_award(
        rule_ir=rule_ir,
        clause=clause,
        effect=effect,
        context=context,
        amount=amount,
        execution_event_id=event_id,
    )
    transaction = context.state.award_victory_points(award)
    payload = transaction.to_payload()
    event_payload = validate_json_value(payload)
    if context.event_log is not None:
        if type(context.event_log) is not EventLog:
            raise GameLifecycleError("Generic RuleIR Secondary VP event_log must be an EventLog.")
        event = context.event_log.append(
            RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
            event_payload,
        )
    else:
        event = EventRecord(
            event_id=event_id,
            event_type=RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
            payload=event_payload,
        )
    if event.event_id != event_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP execution event identity drifted.")
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=(
            generic_rule_effect_payload(
                rule_ir=rule_ir,
                clause=clause,
                effect=effect,
                context=context,
                effect_index=effect_index,
            ),
        ),
        victory_point_transactions=(payload,),
        event_records=(event,),
    )


def require_generic_rule_ir_loaded_authority(
    *,
    award: VictoryPointAward,
    rule_ir: RuleIR,
) -> None:
    validate_generic_rule_ir_secondary_award(award=award)
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires RuleIR.")
    raw = _metadata_object(award.metadata)
    if award.source_id != rule_ir.source_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP source_id drifted from RuleIR.")
    if raw.get("rule_id") != rule_ir.rule_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP rule_id drifted from RuleIR.")
    if raw.get(GENERIC_RULE_IR_SOURCE_ID_KEY) != rule_ir.source_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP source_id drifted from RuleIR.")
    if raw.get(GENERIC_RULE_IR_HASH_KEY) != rule_ir.ir_hash():
        raise GameLifecycleError("Generic RuleIR Secondary VP rule_ir_hash drifted from RuleIR.")
    clause_id = raw.get("clause_id")
    clauses = tuple(clause for clause in rule_ir.clauses if clause.clause_id == clause_id)
    if len(clauses) != 1:
        raise GameLifecycleError("Generic RuleIR Secondary VP clause is not in the loaded RuleIR.")
    clause = clauses[0]
    effect_index = raw.get(GENERIC_RULE_IR_EFFECT_INDEX_KEY)
    if type(effect_index) is not int or not 0 <= effect_index < len(clause.effects):
        raise GameLifecycleError("Generic RuleIR Secondary VP effect_index is outside its clause.")
    expected_effect = clause.effects[effect_index].to_payload()
    if raw.get("effect") != expected_effect:
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP effect is not in the loaded RuleIR clause."
        )


def validate_secondary_generic_rule_ir_restore_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR Secondary VP restore requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Generic RuleIR Secondary VP restore requires EventRecord values.")
    if rule_ir_authority_index is not None and type(rule_ir_authority_index) is not (
        RuntimeRuleIRAuthorityIndex
    ):
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP restore requires RuntimeRuleIRAuthorityIndex."
        )
    transactions = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind
        in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }
        and secondary_scoring_provider_kind_from_metadata(transaction.metadata)
        is SecondaryScoringProviderKind.GENERIC_RULE_IR
    )
    events = tuple(
        record
        for record in event_records
        if record.event_type == RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE
    )
    events_by_id = {record.event_id: record for record in events}
    if len(events_by_id) != len(events):
        raise GameLifecycleError("Generic RuleIR Secondary VP execution events are not unique.")
    seen_event_ids: set[str] = set()
    if transactions:
        if rule_ir_authority_index is None:
            raise GameLifecycleError(
                "Generic RuleIR Secondary VP requires loaded RuleIR authority."
            )
        loaded_index = rule_ir_authority_index
        for transaction in transactions:
            award = _award_from_transaction(transaction)
            validate_generic_rule_ir_secondary_award(award=award)
            raw = _metadata_object(transaction.metadata)
            event_id = raw.get(GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY)
            if type(event_id) is not str:
                raise GameLifecycleError("Generic RuleIR Secondary VP requires execution_event_id.")
            if event_id in seen_event_ids:
                raise GameLifecycleError(
                    "Generic RuleIR Secondary VP execution event is bound to multiple transactions."
                )
            seen_event_ids.add(event_id)
            event = events_by_id.get(event_id)
            if event is None:
                raise GameLifecycleError(
                    "Generic RuleIR Secondary VP requires rule_execution_victory_points_awarded."
                )
            if event.payload != transaction.to_payload():
                raise GameLifecycleError(
                    "Generic RuleIR Secondary VP execution event drifted from the ledger "
                    "transaction."
                )
            source_id = raw.get(GENERIC_RULE_IR_SOURCE_ID_KEY)
            rule_ir_hash = raw.get(GENERIC_RULE_IR_HASH_KEY)
            if type(source_id) is not str or type(rule_ir_hash) is not str:
                raise GameLifecycleError(
                    "Generic RuleIR Secondary VP requires source_id and rule_ir_hash."
                )
            require_generic_rule_ir_loaded_authority(
                award=award,
                rule_ir=loaded_index.rule_ir_for_scoring_player(
                    source_id=source_id,
                    rule_ir_hash=rule_ir_hash,
                    player_id=transaction.player_id,
                ),
            )
    if seen_event_ids != set(events_by_id):
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP execution events must match ledger transactions."
        )


def _award_from_transaction(transaction: VictoryPointTransaction) -> VictoryPointAward:
    metadata: JsonValue = transaction.metadata
    requested_amount = transaction.amount
    if isinstance(metadata, dict) and "vp_cap_audit" in metadata:
        cap_audit = metadata["vp_cap_audit"]
        if not isinstance(cap_audit, dict):
            raise GameLifecycleError("Secondary VP transaction cap audit must be an object.")
        requested_amount_value = cap_audit.get("requested_amount")
        if type(requested_amount_value) is not int or requested_amount_value <= 0:
            raise GameLifecycleError(
                "Secondary VP transaction cap audit requires positive requested_amount."
            )
        requested_amount = requested_amount_value
        restored_metadata = dict(metadata)
        restored_metadata.pop("vp_cap_audit")
        metadata = restored_metadata
    return VictoryPointAward(
        player_id=transaction.player_id,
        battle_round=transaction.battle_round,
        phase=transaction.phase,
        amount=requested_amount,
        source_kind=transaction.source_kind,
        source_id=transaction.source_id,
        scoring_timing=transaction.scoring_timing,
        hidden=transaction.hidden,
        metadata=metadata,
    )


def _effect_index(*, clause: RuleClause, effect: RuleEffectSpec) -> int:
    identity_matches = tuple(
        index for index, candidate in enumerate(clause.effects) if candidate is effect
    )
    if len(identity_matches) == 1:
        return identity_matches[0]
    semantic_matches = tuple(
        index for index, candidate in enumerate(clause.effects) if candidate == effect
    )
    if len(semantic_matches) != 1:
        raise GameLifecycleError("Generic RuleIR Secondary VP effect does not identify one clause.")
    return semantic_matches[0]


def _positive_delta(effect: RuleEffectSpec) -> int:
    matches = tuple(parameter.value for parameter in effect.parameters if parameter.key == "delta")
    if len(matches) != 1 or type(matches[0]) is not int or matches[0] < 1:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires a positive effect delta.")
    return matches[0]


def _metadata_object(metadata: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    return metadata


__all__ = (
    "GENERIC_RULE_IR_EFFECT_INDEX_KEY",
    "GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY",
    "GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY",
    "GENERIC_RULE_IR_HASH_KEY",
    "GENERIC_RULE_IR_SOURCE_ID_KEY",
    "RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE",
    "apply_generic_rule_ir_victory_points",
    "generic_rule_ir_secondary_award",
    "next_generic_rule_ir_victory_point_event_id",
    "require_generic_rule_ir_loaded_authority",
    "validate_secondary_generic_rule_ir_restore_authority",
)
