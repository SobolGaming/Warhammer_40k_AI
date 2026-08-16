from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
)
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )


def validate_primary_award_semantics(
    *,
    state: GameState,
    award: VictoryPointAward,
) -> None:
    """Require a live Primary award to equal the policy result for frozen evidence."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary VP semantic validation requires GameState.")
    if type(award) is not VictoryPointAward:
        raise GameLifecycleError("Primary VP semantic validation requires an award.")
    if award.source_kind is not VictoryPointSourceKind.PRIMARY:
        raise GameLifecycleError("Primary VP semantic validation requires a Primary award.")
    evidence = _evidence_for_metadata(state=state, metadata=award.metadata)
    expected = _expected_awards(state=state, evidence=evidence)
    if award not in expected:
        raise GameLifecycleError(
            "Primary VP award drifted from authoritative scoring-state semantics."
        )


def validate_primary_transaction_semantics(*, state: GameState) -> None:
    """Re-evaluate every required scoring boundary and its exact Primary rows."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary VP transaction validation requires GameState.")
    transactions = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    transactions_by_evidence_id: dict[str, list[VictoryPointTransaction]] = {}
    for transaction in transactions:
        evidence = _evidence_for_metadata(state=state, metadata=transaction.metadata)
        transactions_by_evidence_id.setdefault(evidence.evidence_id, []).append(transaction)
    if state.mission_setup is None:
        if state.primary_scoring_state_evidence_records or transactions:
            raise GameLifecycleError("Primary VP semantic validation requires MissionSetup.")
        return
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    required_boundary_keys = {
        (record.record_id, boundary_kind)
        for record in state.objective_control_records
        for boundary_kind in required_primary_scoring_boundary_kinds(
            policies=policies,
            record=record,
            turn_order=state.turn_order,
        )
    }
    evidence_boundary_keys = {
        (evidence.objective_control_record_id, evidence.scoring_boundary_kind)
        for evidence in state.primary_scoring_state_evidence_records
    }
    if evidence_boundary_keys != required_boundary_keys:
        raise GameLifecycleError(
            "Primary scoring-state evidence registry is incomplete or unexpected."
        )
    for evidence in state.primary_scoring_state_evidence_records:
        boundary_transactions = transactions_by_evidence_id.get(evidence.evidence_id, [])
        expected = _awards_by_identity(_expected_awards(state=state, evidence=evidence))
        actual = _awards_by_identity(
            tuple(
                _uncapped_award_from_transaction(transaction)
                for transaction in boundary_transactions
            )
        )
        if actual != expected:
            raise GameLifecycleError(
                "Primary VP transactions drifted from authoritative scoring-state semantics."
            )


def validate_primary_boundary_transaction_semantics(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
) -> None:
    """Require one already-resolved Primary boundary to have its exact transaction set."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Primary boundary transaction validation requires GameState.")
    if type(evidence) is not PrimaryScoringStateEvidence:
        raise GameLifecycleError(
            "Primary boundary transaction validation requires typed state evidence."
        )
    boundary_transactions: list[VictoryPointTransaction] = []
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.source_kind is not VictoryPointSourceKind.PRIMARY:
                continue
            transaction_evidence = _evidence_for_metadata(
                state=state,
                metadata=transaction.metadata,
            )
            if transaction_evidence.evidence_id == evidence.evidence_id:
                boundary_transactions.append(transaction)
    expected = _awards_by_identity(_expected_awards(state=state, evidence=evidence))
    actual = _awards_by_identity(
        tuple(
            _uncapped_award_from_transaction(transaction) for transaction in boundary_transactions
        )
    )
    if actual != expected:
        raise GameLifecycleError(
            "Primary boundary transactions drifted from authoritative scoring-state semantics."
        )


def _expected_awards(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
) -> tuple[VictoryPointAward, ...]:
    if state.mission_setup is None:
        raise GameLifecycleError("Primary VP semantic validation requires MissionSetup.")
    boundaries = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == evidence.objective_control_record_id
    )
    if len(boundaries) != 1:
        raise GameLifecycleError(
            "Primary VP semantic validation requires one objective-control boundary."
        )
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    return policies.primary_awards_from_state_evidence(
        record=boundaries[0],
        authoritative_state=state,
        state_evidence=evidence,
    )


def _evidence_for_metadata(
    *,
    state: GameState,
    metadata: JsonValue,
) -> PrimaryScoringStateEvidence:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Primary VP metadata must be an object.")
    raw_id = metadata.get("primary_scoring_state_evidence_id")
    if type(raw_id) is not str or not raw_id:
        raise GameLifecycleError("Primary VP metadata requires scoring-state evidence ID.")
    matches = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.evidence_id == raw_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary VP scoring-state evidence does not identify an authoritative record."
        )
    return matches[0]


def _uncapped_award_from_transaction(
    transaction: VictoryPointTransaction,
) -> VictoryPointAward:
    if not isinstance(transaction.metadata, dict):
        raise GameLifecycleError("Primary VP transaction metadata must be an object.")
    metadata = transaction.metadata
    cap_audit = metadata.get("vp_cap_audit")
    requested_amount = transaction.amount
    if cap_audit is not None:
        if not isinstance(cap_audit, dict):
            raise GameLifecycleError("Primary VP transaction cap audit must be an object.")
        raw_requested_amount = cap_audit.get("requested_amount")
        if type(raw_requested_amount) is not int or raw_requested_amount <= 0:
            raise GameLifecycleError(
                "Primary VP transaction cap audit requires positive requested_amount."
            )
        requested_amount = raw_requested_amount
    return VictoryPointAward(
        player_id=transaction.player_id,
        battle_round=transaction.battle_round,
        phase=transaction.phase,
        amount=requested_amount,
        source_kind=transaction.source_kind,
        source_id=transaction.source_id,
        scoring_timing=transaction.scoring_timing,
        hidden=transaction.hidden,
        metadata={key: value for key, value in metadata.items() if key != "vp_cap_audit"},
    )


def _awards_by_identity(
    awards: tuple[VictoryPointAward, ...],
) -> Mapping[tuple[str, str], VictoryPointAward]:
    indexed: dict[tuple[str, str], VictoryPointAward] = {}
    for award in awards:
        if not isinstance(award.metadata, dict):
            raise GameLifecycleError("Primary VP award metadata must be an object.")
        rule_id = award.metadata.get("scoring_rule_id")
        if type(rule_id) is not str or not rule_id:
            raise GameLifecycleError("Primary VP award metadata requires scoring_rule_id.")
        identity = (award.player_id, rule_id)
        if identity in indexed:
            raise GameLifecycleError("Primary VP semantic award identities must be unique.")
        indexed[identity] = award
    return indexed


__all__ = (
    "validate_primary_award_semantics",
    "validate_primary_boundary_transaction_semantics",
    "validate_primary_transaction_semantics",
)
