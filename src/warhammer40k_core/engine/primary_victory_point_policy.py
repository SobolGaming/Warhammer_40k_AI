from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.descriptor_hash import validate_sha256_hex
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.primary_scoring_timing import (
    primary_scoring_timing_applies,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.scoring import (
        MissionScoringPolicy,
        VictoryPointAward,
        VictoryPointLedger,
        VictoryPointTransaction,
    )


class PrimaryVictoryPointCapTreatment(StrEnum):
    ROUND_CAPPED = "round_capped"
    END_OF_BATTLE_EXEMPT = "end_of_battle_exempt"


@dataclass(frozen=True, slots=True)
class PrimaryVictoryPointPolicyBinding:
    scoring_rule_id: str
    objective_control_record_id: str
    cap_treatment: PrimaryVictoryPointCapTreatment

    @property
    def identity(self) -> tuple[str, str]:
        return (self.objective_control_record_id, self.scoring_rule_id)


@dataclass(frozen=True, slots=True)
class VictoryPointLedgerPolicyValidation:
    end_of_battle_transaction_ids: frozenset[str]
    primary_binding_identities: frozenset[tuple[str, str]]


def validate_primary_victory_point_award(
    *,
    policy: MissionScoringPolicy,
    award: VictoryPointAward,
    objective_control_records: Sequence[ObjectiveControlRecord],
    primary_scoring_state_evidence_records: Sequence[PrimaryScoringStateEvidence],
    turn_order: tuple[str, ...],
    expected_boundary_active_player_id: str,
) -> PrimaryVictoryPointPolicyBinding:
    return _validate_primary_victory_point_record(
        policy=policy,
        record=award,
        objective_control_records=objective_control_records,
        primary_scoring_state_evidence_records=primary_scoring_state_evidence_records,
        turn_order=turn_order,
        expected_boundary_active_player_id=expected_boundary_active_player_id,
        allow_cap_audit=False,
    )


def validate_primary_victory_point_transaction(
    *,
    policy: MissionScoringPolicy,
    transaction: VictoryPointTransaction,
    objective_control_records: Sequence[ObjectiveControlRecord],
    primary_scoring_state_evidence_records: Sequence[PrimaryScoringStateEvidence],
    turn_order: tuple[str, ...],
) -> PrimaryVictoryPointPolicyBinding:
    return _validate_primary_victory_point_record(
        policy=policy,
        record=transaction,
        objective_control_records=objective_control_records,
        primary_scoring_state_evidence_records=primary_scoring_state_evidence_records,
        turn_order=turn_order,
        expected_boundary_active_player_id=None,
        allow_cap_audit=True,
    )


def validate_victory_point_ledger_policy(
    *,
    policy: MissionScoringPolicy,
    ledger: VictoryPointLedger,
    objective_control_records: Sequence[ObjectiveControlRecord],
    primary_scoring_state_evidence_records: Sequence[PrimaryScoringStateEvidence],
    turn_order: tuple[str, ...],
) -> VictoryPointLedgerPolicyValidation:
    """Replay ledger chronology and validate source bindings plus Primary cap audits."""

    from warhammer40k_core.engine.scoring import (
        VictoryPointCapBucket,
        VictoryPointLedger,
        VictoryPointSourceKind,
    )
    from warhammer40k_core.engine.secondary_victory_point_policy import (
        require_source_backed_secondary_cap_bucket,
        state_backed_secondary_binding_identity,
        validate_state_backed_secondary_ledger_binding,
    )
    from warhammer40k_core.engine.victory_point_cap_resolution import (
        resolve_victory_point_cap,
    )

    if ledger.player_id != policy.player_id:
        raise GameLifecycleError("VP ledger and policy player_id drift.")
    end_of_battle_transaction_ids: set[str] = set()
    primary_binding_identities: set[tuple[str, str]] = set()
    secondary_binding_identities: set[tuple[str, VictoryPointSourceKind, str, str]] = set()
    tactical_source_identities: set[tuple[str, str]] = set()
    primary_bucket_transactions: list[VictoryPointTransaction] = []
    replayed_ledger = VictoryPointLedger.initial(player_id=ledger.player_id)
    previous_primary_order_key: tuple[int, int, int, int, int, int, str] | None = None
    for transaction_index, transaction in enumerate(ledger.transactions, start=1):
        expected_transaction_id = (
            f"victory-point:{ledger.player_id}:round-{transaction.battle_round:02d}:"
            f"{transaction_index:06d}"
        )
        if transaction.transaction_id != expected_transaction_id:
            raise GameLifecycleError(
                "Victory Point ledger transaction identity or chronology drifted."
            )
        cap_bucket = policy.cap_bucket_for_victory_point_source(
            source_kind=transaction.source_kind,
            source_id=transaction.source_id,
        )
        binding = None
        end_of_battle_exempt = False
        if transaction.source_kind in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            secondary_identity = state_backed_secondary_binding_identity(
                player_id=transaction.player_id,
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
                metadata=transaction.metadata,
            )
            if secondary_identity is not None:
                require_source_backed_secondary_cap_bucket(
                    policy=policy,
                    source_kind=transaction.source_kind,
                    source_id=transaction.source_id,
                )
                secondary_identity = validate_state_backed_secondary_ledger_binding(
                    transaction=transaction,
                    objective_control_records=objective_control_records,
                )
                if secondary_identity in secondary_binding_identities:
                    raise GameLifecycleError(
                        "Secondary VP ledger must not repeat a source at one boundary."
                    )
                secondary_binding_identities.add(secondary_identity)
                if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
                    tactical_key = (transaction.player_id, transaction.source_id)
                    if tactical_key in tactical_source_identities:
                        raise GameLifecycleError(
                            "Tactical Secondary VP ledger must not repeat a source "
                            "across boundaries."
                        )
                    tactical_source_identities.add(tactical_key)
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY:
            binding = validate_primary_victory_point_transaction(
                policy=policy,
                transaction=transaction,
                objective_control_records=objective_control_records,
                primary_scoring_state_evidence_records=(primary_scoring_state_evidence_records),
                turn_order=turn_order,
            )
            if binding.identity in primary_binding_identities:
                raise GameLifecycleError(
                    "Primary VP ledger must not repeat a scoring rule at one boundary."
                )
            primary_binding_identities.add(binding.identity)
            primary_order_key = _primary_transaction_order_key(
                binding=binding,
                objective_control_records=objective_control_records,
                turn_order=turn_order,
                scoring_player_id=policy.player_id,
            )
            if (
                previous_primary_order_key is not None
                and primary_order_key < previous_primary_order_key
            ):
                raise GameLifecycleError(
                    "Primary VP ledger transaction chronology drifted from scoring boundaries."
                )
            previous_primary_order_key = primary_order_key
            end_of_battle_exempt = (
                binding.cap_treatment is PrimaryVictoryPointCapTreatment.END_OF_BATTLE_EXEMPT
            )
        if cap_bucket is VictoryPointCapBucket.PRIMARY:
            if transaction.scoring_timing == "end_of_battle" and binding is None:
                raise GameLifecycleError(
                    "Only a source-backed Primary scoring rule may claim end-of-battle exemption."
                )
            primary_bucket_transactions.append(transaction)
        uncapped_award = _uncapped_award_from_transaction(transaction)
        cap_resolution = resolve_victory_point_cap(
            policy=policy,
            ledger=replayed_ledger,
            award=uncapped_award,
            end_of_battle_transaction_ids=frozenset(end_of_battle_transaction_ids),
            end_of_battle_exempt=end_of_battle_exempt,
        )
        if (
            transaction.amount != cap_resolution.applied_amount
            or transaction.metadata != cap_resolution.metadata
        ):
            if binding is not None:
                raise GameLifecycleError(
                    "Primary VP transaction cap audit drifted from chronological ledger policy."
                )
            raise GameLifecycleError(
                "Victory point transaction cap audit drifted from chronological ledger policy."
            )
        if end_of_battle_exempt:
            end_of_battle_transaction_ids.add(transaction.transaction_id)
        replayed_ledger = VictoryPointLedger(
            player_id=ledger.player_id,
            victory_points=replayed_ledger.victory_points + transaction.amount,
            transactions=(*replayed_ledger.transactions, transaction),
        )

    if policy.primary_max_vp_per_turn is not None:
        round_totals: dict[int, int] = {}
        for transaction in primary_bucket_transactions:
            if transaction.transaction_id in end_of_battle_transaction_ids:
                continue
            round_totals[transaction.battle_round] = (
                round_totals.get(transaction.battle_round, 0) + transaction.amount
            )
        if any(total > policy.primary_max_vp_per_turn for total in round_totals.values()):
            raise GameLifecycleError(
                "Ordinary Primary VP transactions exceed the battle-round cap."
            )
    return VictoryPointLedgerPolicyValidation(
        end_of_battle_transaction_ids=frozenset(end_of_battle_transaction_ids),
        primary_binding_identities=frozenset(primary_binding_identities),
    )


def _uncapped_award_from_transaction(
    transaction: VictoryPointTransaction,
) -> VictoryPointAward:
    from warhammer40k_core.engine.scoring import VictoryPointAward

    metadata = transaction.metadata
    requested_amount = transaction.amount
    if isinstance(metadata, dict) and "vp_cap_audit" in metadata:
        cap_audit = metadata["vp_cap_audit"]
        if not isinstance(cap_audit, dict):
            raise GameLifecycleError("Victory point transaction cap audit must be an object.")
        requested_amount_value = cap_audit.get("requested_amount")
        applied_amount = cap_audit.get("applied_amount")
        if type(requested_amount_value) is not int or requested_amount_value <= 0:
            raise GameLifecycleError(
                "Victory point transaction cap audit requires positive requested_amount."
            )
        if type(applied_amount) is not int or applied_amount != transaction.amount:
            raise GameLifecycleError("Victory point transaction cap audit applied_amount drifted.")
        if applied_amount > requested_amount_value:
            raise GameLifecycleError(
                "Victory point transaction cap audit applied_amount exceeds requested_amount."
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


def _primary_transaction_order_key(
    *,
    binding: PrimaryVictoryPointPolicyBinding,
    objective_control_records: Sequence[ObjectiveControlRecord],
    turn_order: tuple[str, ...],
    scoring_player_id: str,
) -> tuple[int, int, int, int, int, int, str]:
    matches = tuple(
        record
        for record in objective_control_records
        if record.record_id == binding.objective_control_record_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary VP transaction chronology requires one objective-control boundary."
        )
    boundary = matches[0]
    if boundary.active_player_id not in turn_order:
        raise GameLifecycleError(
            "Primary VP transaction chronology boundary player is not in turn order."
        )
    if scoring_player_id not in turn_order:
        raise GameLifecycleError(
            "Primary VP transaction chronology scoring player is not in turn order."
        )
    phase_order = tuple(phase.value for phase in BattlePhase)
    if boundary.phase not in phase_order:
        raise GameLifecycleError("Primary VP transaction chronology boundary phase is unsupported.")
    timing_order = (
        ObjectiveControlTiming.TURN_START,
        ObjectiveControlTiming.PHASE_END,
        ObjectiveControlTiming.TURN_END,
    )
    return (
        boundary.battle_round,
        turn_order.index(boundary.active_player_id),
        phase_order.index(boundary.phase),
        timing_order.index(boundary.timing),
        (1 if binding.cap_treatment is PrimaryVictoryPointCapTreatment.END_OF_BATTLE_EXEMPT else 0),
        turn_order.index(scoring_player_id),
        binding.scoring_rule_id,
    )


def _validate_primary_victory_point_record(
    *,
    policy: MissionScoringPolicy,
    record: VictoryPointAward | VictoryPointTransaction,
    objective_control_records: Sequence[ObjectiveControlRecord],
    primary_scoring_state_evidence_records: Sequence[PrimaryScoringStateEvidence],
    turn_order: tuple[str, ...],
    expected_boundary_active_player_id: str | None,
    allow_cap_audit: bool,
) -> PrimaryVictoryPointPolicyBinding:
    from warhammer40k_core.engine.scoring import VictoryPointSourceKind

    if record.source_kind is not VictoryPointSourceKind.PRIMARY:
        raise GameLifecycleError("Primary VP policy validation requires a Primary source row.")
    if record.player_id != policy.player_id:
        raise GameLifecycleError("Primary VP policy player_id drift.")
    if not policy.primary_scoring_supported:
        raise GameLifecycleError(
            "Primary mission scoring source is known but engine implementation is pending."
        )
    if record.source_id != policy.primary_mission_id:
        raise GameLifecycleError(
            "Primary VP source does not match the player's assigned Primary mission."
        )
    if not isinstance(record.metadata, dict):
        raise GameLifecycleError("Primary VP metadata must be an object.")
    metadata = record.metadata
    state_evidence_id = _required_string(metadata, "primary_scoring_state_evidence_id")
    state_evidence_hash = validate_sha256_hex(
        _required_string(metadata, "primary_scoring_state_evidence_hash"),
        field_name="Primary VP primary_scoring_state_evidence_hash",
        error_type=GameLifecycleError,
    )
    if state_evidence_id != f"primary-scoring-state-evidence:{state_evidence_hash}":
        raise GameLifecycleError("Primary VP scoring-state evidence identity drifted.")
    scoring_rule_id = _required_string(metadata, "scoring_rule_id")
    rule_matches = tuple(
        rule for rule in policy.primary_scoring_rules if rule.rule_id == scoring_rule_id
    )
    if len(rule_matches) != 1:
        raise GameLifecycleError(
            "Primary VP scoring_rule_id does not identify an assigned Primary scoring rule."
        )
    rule = rule_matches[0]
    if _required_string(metadata, "scoring_rule_source_id") != rule.source_id:
        raise GameLifecycleError("Primary VP scoring_rule_source_id drifted from policy.")
    if _required_string(metadata, "scoring_rule_condition") != rule.condition:
        raise GameLifecycleError("Primary VP scoring_rule_condition drifted from policy.")
    score_count = _required_positive_int(metadata, "score_count")
    points_per_count = _required_positive_int(metadata, "victory_points_per_count")
    if points_per_count != rule.victory_points:
        raise GameLifecycleError("Primary VP victory_points_per_count drifted from policy.")
    requested_amount = score_count * points_per_count
    if rule.cap is not None:
        requested_amount = min(requested_amount, rule.cap)
    if _requested_amount(record, metadata=metadata, allow_cap_audit=allow_cap_audit) != (
        requested_amount
    ):
        raise GameLifecycleError("Primary VP amount drifted from scoring-rule arithmetic.")

    objective_control_record_id = _required_string(metadata, "objective_control_record_id")
    boundaries = tuple(
        boundary
        for boundary in objective_control_records
        if boundary.record_id == objective_control_record_id
    )
    if len(boundaries) != 1:
        raise GameLifecycleError(
            "Primary VP objective_control_record_id does not identify an authoritative boundary."
        )
    boundary = boundaries[0]
    if boundary.record_id != (
        "objective-control:"
        f"round-{boundary.battle_round:02d}:"
        f"{boundary.active_player_id}:"
        f"{boundary.phase}:"
        f"{boundary.timing.value}"
    ):
        raise GameLifecycleError("Primary VP objective-control boundary identity drifted.")
    if record.battle_round != boundary.battle_round or record.phase != boundary.phase:
        raise GameLifecycleError("Primary VP row drifted from its objective-control boundary.")
    if (
        expected_boundary_active_player_id is not None
        and boundary.active_player_id != expected_boundary_active_player_id
    ):
        raise GameLifecycleError("Primary VP boundary drifted from the active player.")
    end_of_battle = record.scoring_timing == "end_of_battle"
    expected_boundary_kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    if (rule.timing == "end_of_battle") != end_of_battle:
        raise GameLifecycleError("Primary VP scoring_timing drifted from its source rule.")
    if end_of_battle:
        if (
            boundary.battle_round != policy.game_length_battle_rounds
            or boundary.phase != BattlePhase.FIGHT.value
            or boundary.timing is not ObjectiveControlTiming.TURN_END
        ):
            raise GameLifecycleError(
                "End-of-battle Primary VP requires the final Fight-phase TURN_END boundary."
            )
        if not turn_order or boundary.active_player_id != turn_order[-1]:
            raise GameLifecycleError(
                "End-of-battle Primary VP requires the last player's turn-end boundary."
            )
        cap_treatment = PrimaryVictoryPointCapTreatment.END_OF_BATTLE_EXEMPT
    else:
        if record.scoring_timing != boundary.timing.value:
            raise GameLifecycleError(
                "Primary VP scoring_timing drifted from its objective-control boundary."
            )
        if boundary.active_player_id != policy.player_id:
            raise GameLifecycleError(
                "Ordinary Primary VP scoring requires the assigned player's boundary."
            )
        cap_treatment = PrimaryVictoryPointCapTreatment.ROUND_CAPPED
    if not primary_scoring_timing_applies(
        timing=rule.timing,
        battle_round=boundary.battle_round,
        phase=boundary.phase,
        objective_control_timing=boundary.timing,
        primary_scoring_phase=policy.primary_scoring_phase,
        primary_scoring_timing=policy.primary_scoring_timing,
        game_length_battle_rounds=policy.game_length_battle_rounds,
        end_of_battle=end_of_battle,
    ):
        raise GameLifecycleError(
            "Primary VP scoring rule does not apply at its objective-control boundary."
        )
    if any(
        type(evidence) is not PrimaryScoringStateEvidence
        for evidence in primary_scoring_state_evidence_records
    ):
        raise GameLifecycleError("Primary VP authority registry must contain typed state evidence.")
    state_evidence_matches = tuple(
        evidence
        for evidence in primary_scoring_state_evidence_records
        if evidence.evidence_id == state_evidence_id
    )
    if len(state_evidence_matches) != 1:
        raise GameLifecycleError(
            "Primary VP scoring-state evidence does not identify an authoritative record."
        )
    state_evidence = state_evidence_matches[0]
    if (
        state_evidence.evidence_hash != state_evidence_hash
        or state_evidence.objective_control_record_id != boundary.record_id
        or state_evidence.objective_control_record_hash != objective_control_record_hash(boundary)
        or state_evidence.scoring_boundary_kind is not expected_boundary_kind
    ):
        raise GameLifecycleError(
            "Primary VP scoring-state evidence drifted from its authoritative boundary."
        )
    return PrimaryVictoryPointPolicyBinding(
        scoring_rule_id=scoring_rule_id,
        objective_control_record_id=objective_control_record_id,
        cap_treatment=cap_treatment,
    )


def _requested_amount(
    record: VictoryPointAward | VictoryPointTransaction,
    *,
    metadata: Mapping[str, object],
    allow_cap_audit: bool,
) -> int:
    cap_audit = metadata.get("vp_cap_audit")
    if cap_audit is None:
        return record.amount
    if not allow_cap_audit:
        raise GameLifecycleError("Primary VP awards must not contain a VP cap audit.")
    if not isinstance(cap_audit, dict):
        raise GameLifecycleError("Primary VP transaction cap audit must be an object.")
    cap_audit_payload = cast(dict[str, object], cap_audit)
    requested_amount = cap_audit_payload.get("requested_amount")
    applied_amount = cap_audit_payload.get("applied_amount")
    if type(requested_amount) is not int or requested_amount <= 0:
        raise GameLifecycleError(
            "Primary VP transaction cap audit requires positive requested_amount."
        )
    if type(applied_amount) is not int or applied_amount != record.amount:
        raise GameLifecycleError("Primary VP transaction cap audit applied_amount drifted.")
    if applied_amount > requested_amount:
        raise GameLifecycleError(
            "Primary VP transaction cap audit applied_amount exceeds requested_amount."
        )
    return requested_amount


def _required_string(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Primary VP metadata requires {key}.")
    return value


def _required_positive_int(metadata: Mapping[str, object], key: str) -> int:
    value = metadata.get(key)
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"Primary VP metadata requires positive {key}.")
    return value


__all__ = (
    "PrimaryVictoryPointCapTreatment",
    "PrimaryVictoryPointPolicyBinding",
    "VictoryPointLedgerPolicyValidation",
    "validate_primary_victory_point_award",
    "validate_primary_victory_point_transaction",
    "validate_victory_point_ledger_policy",
)
