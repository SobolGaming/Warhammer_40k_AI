from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_boundary_lifecycle_bindings import (
    GENERIC_RULE_IR_EFFECT_INDEX_KEY,
    GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY,
    GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY,
    GENERIC_RULE_IR_HASH_KEY,
    GENERIC_RULE_IR_SOURCE_ID_KEY,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    BattlePhaseKind,
    EventLog,
    GameLifecycle,
    GameLifecyclePayload,
    GameState,
    JsonValue,
    ObjectiveRuleScope,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryScoringBoundaryLifecyclePayload,
    PrimaryScoringStateEvidencePayload,
    RegisteredPhase11FCapProbe,
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleExecutionContext,
    RuleExecutionStatus,
    RuleIR,
    RuleSourceText,
    RuntimeRuleIRAuthorityIndex,
    RuntimeRuleIRSourceKey,
    SecondaryScoringProviderKind,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _uncapped_award_from_transaction,  # pyright: ignore[reportPrivateUsage]
    canonical_payload_sha256,
    cast,
    compile_rule_source_text,
    default_rule_execution_registry,
    execute_rule_ir,
    registered_phase11f_cap_probe,
    replace,
    secondary_scoring_provider_kind_from_metadata,
)
from tests.shared.category_migration.primary_boundary_state_and_geometry import (
    _json_list,
    _json_object,
)


def _ledger_payload(payload: GameLifecyclePayload, *, player_id: str) -> dict[str, object]:
    state = _json_object(payload["state"], label="lifecycle state")
    ledgers = _json_list(state["victory_point_ledgers"], label="victory point ledgers")
    for ledger in ledgers:
        ledger_map = _json_object(ledger, label="victory point ledger")
        if ledger_map["player_id"] == player_id:
            return ledger_map
    raise AssertionError(f"ledger for {player_id} was not found")


def _secondary_transaction_payloads(
    ledger: dict[str, object],
    *,
    source_kind: str,
) -> list[dict[str, object]]:
    transactions = _json_list(ledger["transactions"], label="victory point transactions")
    matches: list[dict[str, object]] = []
    for transaction in transactions:
        transaction_map = _json_object(transaction, label="victory point transaction")
        if transaction_map["source_kind"] == source_kind:
            matches.append(transaction_map)
    return matches


def _secondary_transaction_payload(
    payload: GameLifecyclePayload,
    *,
    player_id: str,
    source_id: str,
    source_kind: str,
) -> dict[str, object]:
    matches = tuple(
        transaction
        for transaction in _secondary_transaction_payloads(
            _ledger_payload(payload, player_id=player_id),
            source_kind=source_kind,
        )
        if transaction["source_id"] == source_id
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one {source_kind} {source_id} transaction for {player_id}")
    return matches[0]


def _transaction_record_id(transaction: dict[str, object]) -> str:
    metadata = _json_object(transaction["metadata"], label="secondary metadata")
    record_id = metadata["objective_control_record_id"]
    assert isinstance(record_id, str)
    return record_id


def _secondary_transaction(
    state: GameState,
    *,
    source_kind: VictoryPointSourceKind,
) -> VictoryPointTransaction:
    matches = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is source_kind
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one {source_kind.value} transaction")
    return matches[0]


def _award_from_transaction(transaction: VictoryPointTransaction) -> VictoryPointAward:
    return _uncapped_award_from_transaction(transaction)


def _fabricated_generic_rule_ir_metadata(
    *,
    amount: int,
    source_id: str = "phase17d-generic-vp",
    rule_id: str = "phase17d-generic-vp",
    rule_ir_hash: str = "ab" * 32,
    clause_id: str = "clause-1",
    effect_index: int = 0,
    execution_event_id: str = "event-000001",
    execution_context: object | None = None,
    **overrides: object,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "secondary_scoring_provider_kind": SecondaryScoringProviderKind.GENERIC_RULE_IR.value,
        "rule_id": rule_id,
        GENERIC_RULE_IR_SOURCE_ID_KEY: source_id,
        GENERIC_RULE_IR_HASH_KEY: rule_ir_hash,
        "clause_id": clause_id,
        GENERIC_RULE_IR_EFFECT_INDEX_KEY: effect_index,
        "effect": {
            "kind": "add_victory_points",
            "parameters": [
                {"key": "unit", "value": "target"},
                {"key": "delta", "value": amount},
            ],
        },
        GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY: execution_event_id,
        GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY: (
            {
                "player_id": "player-a",
                "battle_round": 1,
                "phase": "fight",
            }
            if execution_context is None
            else cast(JsonValue, execution_context)
        ),
    }
    for key, value in overrides.items():
        payload[key] = cast(JsonValue, value)
    return payload


def _require_registered_phase11f_cap_probe() -> RegisteredPhase11FCapProbe:
    probe = registered_phase11f_cap_probe(
        source_id="assassination",
        scoring_rule_id="phase11f-secondary-cap",
    )
    assert probe is not None
    return probe


def _registered_phase11f_cap_probe_award() -> VictoryPointAward:
    probe = _require_registered_phase11f_cap_probe()
    return VictoryPointAward(
        player_id=probe.player_id,
        battle_round=probe.battle_round,
        phase=probe.phase,
        amount=probe.amount,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        source_id=probe.source_id,
        scoring_timing=probe.scoring_timing,
        metadata={
            "secondary_scoring_provider_kind": SecondaryScoringProviderKind.LEGACY_PHASE11F.value,
            "scoring_rule_id": probe.scoring_rule_id,
        },
    )


def _compiled_generic_vp_rule_ir() -> RuleIR:
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            objective_scope=ObjectiveRuleScope.CORE_RULES,
            source_id="phase17n:generic-vp-score",
            raw_text="When this unit is destroyed, score 5VP.",
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir


def _generic_vp_clause_and_effect(rule_ir: RuleIR) -> tuple[RuleClause, RuleEffectSpec]:
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is RuleEffectKind.ADD_VICTORY_POINTS:
                return clause, effect
    raise AssertionError("compiled RuleIR does not award victory points")


def _generic_vp_execution_context(
    state: GameState,
    *,
    event_log: EventLog | None,
    player_id: str = "player-a",
) -> RuleExecutionContext:
    phase = state.current_battle_phase
    assert phase is not None
    return RuleExecutionContext(
        game_id=state.game_id,
        player_id=player_id,
        battle_round=state.battle_round,
        phase=BattlePhaseKind(phase.value),
        active_player_id=state.active_player_id,
        timing_window_id="phase17n:generic-vp",
        state=state,
        event_log=event_log,
    )


def _empty_rule_ir_authority_index() -> RuntimeRuleIRAuthorityIndex:
    return RuntimeRuleIRAuthorityIndex(
        _rule_irs_by_key={},
        _player_ids_by_key={},
        _ability_records_by_player_key={},
        _stratagem_records_by_player_key={},
    )


def _rule_ir_authority_index(
    rule_ir: RuleIR,
    *,
    player_id: str | None = None,
    player_ids: tuple[str, ...] | None = None,
    globally_registered: bool = False,
) -> RuntimeRuleIRAuthorityIndex:
    key = RuntimeRuleIRSourceKey(source_id=rule_ir.source_id, rule_ir_hash=rule_ir.ir_hash())
    if player_id is not None and player_ids is not None:
        raise AssertionError("pass player_id or player_ids, not both")
    if player_ids is not None:
        owned = player_ids
    elif player_id is not None:
        owned = (player_id,)
    elif globally_registered:
        owned = ()
    else:
        owned = ("player-a",)
    return RuntimeRuleIRAuthorityIndex(
        _rule_irs_by_key={key: rule_ir},
        _player_ids_by_key={key: tuple(sorted(owned))},
        _ability_records_by_player_key={},
        _stratagem_records_by_player_key={},
        _global_source_keys=frozenset({key}) if globally_registered else frozenset(),
    )


def _execute_generic_vp_on_lifecycle(
    lifecycle: GameLifecycle,
    *,
    player_id: str = "player-a",
) -> RuleIR:
    state = lifecycle.state
    assert state is not None
    rule_ir = _compiled_generic_vp_rule_ir()
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_generic_vp_execution_context(
            state,
            event_log=lifecycle.decision_controller.event_log,
            player_id=player_id,
        ),
        registry=default_rule_execution_registry(),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    return rule_ir


def _generic_rule_ir_transaction(state: GameState) -> VictoryPointTransaction:
    matches = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if secondary_scoring_provider_kind_from_metadata(transaction.metadata)
        is SecondaryScoringProviderKind.GENERIC_RULE_IR
    )
    if len(matches) != 1:
        raise AssertionError("expected one generic RuleIR Secondary transaction")
    return matches[0]


def _replace_player_transaction(state: GameState, transaction: VictoryPointTransaction) -> None:
    ledger = state.victory_point_ledger_for_player(transaction.player_id)
    state.victory_point_ledgers = [
        replace(
            ledger,
            transactions=tuple(
                transaction if stored_tx.transaction_id == transaction.transaction_id else stored_tx
                for stored_tx in ledger.transactions
            ),
        )
        if stored.player_id == ledger.player_id
        else stored
        for stored in state.victory_point_ledgers
    ]


def _append_player_transaction_from_award(state: GameState, award: VictoryPointAward) -> None:
    ledger = state.victory_point_ledger_for_player(award.player_id)
    updated, _transaction = ledger.award(award)
    state.victory_point_ledgers = [
        updated if stored.player_id == ledger.player_id else stored
        for stored in state.victory_point_ledgers
    ]


def _fixed_secondary_record_ids(state: GameState) -> tuple[str, ...]:
    record_ids: list[str] = []
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.source_kind is not VictoryPointSourceKind.FIXED_SECONDARY:
                continue
            metadata = transaction.metadata
            assert isinstance(metadata, dict)
            record_id = metadata.get("objective_control_record_id")
            assert isinstance(record_id, str)
            record_ids.append(record_id)
    return tuple(record_ids)


def _rehash_evidence_transactions_and_lifecycles(
    payload: GameLifecyclePayload,
    *,
    evidence: PrimaryScoringStateEvidencePayload,
    scoring_commit_checkpoint: PrimaryMissionBoundaryCheckpoint | None = None,
) -> None:
    evidence_map = _json_object(evidence, label="primary scoring evidence")
    old_evidence_id = evidence_map["evidence_id"]
    assert isinstance(old_evidence_id, str)
    content = {
        key: value
        for key, value in evidence_map.items()
        if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    new_evidence_id = f"primary-scoring-state-evidence:{digest}"
    evidence_map["evidence_id"] = new_evidence_id
    evidence_map["evidence_hash"] = digest
    state = payload["state"]
    for ledger in state["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if type(metadata) is not dict:
                continue
            metadata_map = cast(dict[str, object], metadata)
            if metadata_map.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata_map["primary_scoring_state_evidence_id"] = new_evidence_id
            metadata_map["primary_scoring_state_evidence_hash"] = digest
    for row in state["primary_scoring_boundary_lifecycles"]:
        if row["evidence_id"] != old_evidence_id:
            continue
        row["evidence_id"] = new_evidence_id
        if scoring_commit_checkpoint is not None:
            row["scoring_commit_checkpoint_id"] = scoring_commit_checkpoint.checkpoint_id
            row["scoring_commit_checkpoint_hash"] = scoring_commit_checkpoint.checkpoint_hash
        _rehash_lifecycle_row(row)


def _rehash_lifecycle_row(row: PrimaryScoringBoundaryLifecyclePayload) -> None:
    row_map = _json_object(row, label="primary scoring boundary lifecycle")
    content = {
        key: value
        for key, value in row_map.items()
        if key not in {"lifecycle_id", "lifecycle_hash"}
    }
    digest = canonical_payload_sha256(content)
    row_map["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{digest}"
    row_map["lifecycle_hash"] = digest


__all__: list[str] = []
__all__ += ["GENERIC_RULE_IR_EFFECT_INDEX_KEY", "BattlePhaseKind", "EventLog"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY", "GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY"]
__all__ += ["GENERIC_RULE_IR_HASH_KEY", "GENERIC_RULE_IR_SOURCE_ID_KEY", "GameLifecycle"]
__all__ += ["GameLifecyclePayload", "GameState", "JsonValue", "ObjectiveRuleScope"]
__all__ += ["PrimaryMissionBoundaryCheckpoint", "PrimaryScoringBoundaryLifecyclePayload"]
__all__ += ["PrimaryScoringStateEvidencePayload", "RegisteredPhase11FCapProbe", "RuleClause"]
__all__ += ["RuleEffectKind", "RuleEffectSpec", "RuleExecutionContext", "RuleExecutionStatus"]
__all__ += ["RuleIR", "RuleSourceText", "RuntimeRuleIRAuthorityIndex", "RuntimeRuleIRSourceKey"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "SecondaryScoringProviderKind", "VictoryPointAward"]
__all__ += ["VictoryPointSourceKind", "VictoryPointTransaction"]
__all__ += ["_append_player_transaction_from_award", "_award_from_transaction"]
__all__ += ["_compiled_generic_vp_rule_ir", "_empty_rule_ir_authority_index"]
__all__ += ["_execute_generic_vp_on_lifecycle", "_fabricated_generic_rule_ir_metadata"]
__all__ += ["_fixed_secondary_record_ids", "_generic_rule_ir_transaction"]
__all__ += ["_generic_vp_clause_and_effect", "_generic_vp_execution_context", "_json_list"]
__all__ += ["_json_object", "_ledger_payload", "_registered_phase11f_cap_probe_award"]
__all__ += ["_rehash_evidence_transactions_and_lifecycles", "_rehash_lifecycle_row"]
__all__ += ["_replace_player_transaction", "_require_registered_phase11f_cap_probe"]
__all__ += ["_rule_ir_authority_index", "_secondary_transaction"]
__all__ += ["_secondary_transaction_payload", "_secondary_transaction_payloads"]
__all__ += ["_transaction_record_id", "_uncapped_award_from_transaction"]
__all__ += ["canonical_payload_sha256", "cast", "compile_rule_source_text"]
__all__ += ["default_rule_execution_registry", "execute_rule_ir", "registered_phase11f_cap_probe"]
__all__ += ["replace", "secondary_scoring_provider_kind_from_metadata"]
