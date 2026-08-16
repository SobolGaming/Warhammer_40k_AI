from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring_cap_audit import metadata_with_vp_cap_audit

if TYPE_CHECKING:
    from warhammer40k_core.engine.scoring import (
        MissionScoringPolicy,
        VictoryPointAward,
        VictoryPointLedger,
    )


@dataclass(frozen=True, slots=True)
class VictoryPointCapResolution:
    applied_amount: int
    metadata: JsonValue


def resolve_victory_point_cap(
    *,
    policy: MissionScoringPolicy,
    ledger: VictoryPointLedger,
    award: VictoryPointAward,
    end_of_battle_transaction_ids: frozenset[str],
    end_of_battle_exempt: bool,
) -> VictoryPointCapResolution:
    """Purely resolve one award against an already-authenticated ledger prefix."""
    from warhammer40k_core.engine.scoring import (
        FIXED_SECONDARY_MISSION_VP_CAP,
        MissionScoringPolicy,
        VictoryPointAward,
        VictoryPointCapBucket,
        VictoryPointLedger,
        VictoryPointSourceKind,
    )

    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("VP cap resolution requires a MissionScoringPolicy.")
    if type(ledger) is not VictoryPointLedger:
        raise GameLifecycleError("VP cap resolution requires a VictoryPointLedger.")
    if type(award) is not VictoryPointAward:
        raise GameLifecycleError("VP cap resolution requires a VictoryPointAward.")
    if type(end_of_battle_transaction_ids) is not frozenset or any(
        type(transaction_id) is not str for transaction_id in end_of_battle_transaction_ids
    ):
        raise GameLifecycleError("VP cap resolution requires end-of-battle transaction IDs.")
    if type(end_of_battle_exempt) is not bool:
        raise GameLifecycleError("VP cap resolution end-of-battle exemption must be a bool.")
    if isinstance(award.metadata, dict) and "vp_cap_audit" in award.metadata:
        raise GameLifecycleError("Victory point awards must not contain a VP cap audit.")

    cap_bucket = policy.cap_bucket_for_victory_point_source(
        source_kind=award.source_kind,
        source_id=award.source_id,
    )
    source_points_before = policy.ledger_points_from_cap_bucket(
        ledger=ledger,
        cap_bucket=cap_bucket,
    )
    source_cap, source_cap_reason = _source_cap_and_reason(
        policy=policy,
        cap_bucket=cap_bucket,
    )
    source_remaining = max(source_cap - source_points_before, 0)

    fixed_secondary_points_before = 0
    fixed_secondary_remaining = award.amount
    fixed_secondary_cap = None
    if award.source_kind is VictoryPointSourceKind.FIXED_SECONDARY:
        fixed_secondary_cap = FIXED_SECONDARY_MISSION_VP_CAP
        fixed_secondary_points_before = sum(
            transaction.amount
            for transaction in ledger.transactions
            if transaction.source_kind is award.source_kind
            and transaction.source_id == award.source_id
        )
        fixed_secondary_remaining = max(
            fixed_secondary_cap - fixed_secondary_points_before,
            0,
        )

    primary_battle_round_cap: int | None = None
    primary_battle_round_points_before = 0
    primary_battle_round_remaining = award.amount
    if (
        cap_bucket is VictoryPointCapBucket.PRIMARY
        and policy.primary_max_vp_per_turn is not None
        and not end_of_battle_exempt
    ):
        primary_battle_round_cap = policy.primary_max_vp_per_turn
        primary_battle_round_points_before = sum(
            transaction.amount
            for transaction in ledger.transactions
            if transaction.battle_round == award.battle_round
            and transaction.transaction_id not in end_of_battle_transaction_ids
            and policy.cap_bucket_for_victory_point_source(
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
            )
            is VictoryPointCapBucket.PRIMARY
        )
        primary_battle_round_remaining = max(
            primary_battle_round_cap - primary_battle_round_points_before,
            0,
        )

    total_remaining = max(policy.total_vp_cap - ledger.victory_points, 0)
    applied_amount = min(
        award.amount,
        source_remaining,
        fixed_secondary_remaining,
        primary_battle_round_remaining,
        total_remaining,
    )
    if applied_amount == award.amount:
        return VictoryPointCapResolution(
            applied_amount=applied_amount,
            metadata=award.metadata,
        )

    capped_reasons: list[str] = []
    if source_remaining < award.amount:
        capped_reasons.append(source_cap_reason)
    if fixed_secondary_remaining < award.amount:
        capped_reasons.append("fixed_secondary_mission_vp_cap")
    if primary_battle_round_remaining < award.amount:
        capped_reasons.append("primary_battle_round_vp_cap")
    if total_remaining < award.amount:
        capped_reasons.append("total_vp_cap")
    return VictoryPointCapResolution(
        applied_amount=applied_amount,
        metadata=metadata_with_vp_cap_audit(
            award.metadata,
            requested_amount=award.amount,
            applied_amount=applied_amount,
            source_cap=source_cap,
            source_points_before=source_points_before,
            source_points_after=source_points_before + applied_amount,
            total_cap=policy.total_vp_cap,
            total_points_before=ledger.victory_points,
            total_points_after=ledger.victory_points + applied_amount,
            capped_reasons=tuple(capped_reasons),
            fixed_secondary_mission_cap=fixed_secondary_cap,
            fixed_secondary_mission_points_before=fixed_secondary_points_before,
            fixed_secondary_mission_points_after=(fixed_secondary_points_before + applied_amount),
            primary_battle_round_cap=primary_battle_round_cap,
            primary_battle_round_points_before=primary_battle_round_points_before,
            primary_battle_round_points_after=(primary_battle_round_points_before + applied_amount),
        ),
    )


def _source_cap_and_reason(
    *,
    policy: MissionScoringPolicy,
    cap_bucket: object,
) -> tuple[int, str]:
    from warhammer40k_core.engine.scoring import VictoryPointCapBucket

    if cap_bucket is VictoryPointCapBucket.PRIMARY:
        return policy.primary_vp_cap, "primary_vp_cap"
    if cap_bucket is VictoryPointCapBucket.SECONDARY:
        return policy.secondary_vp_cap, "secondary_vp_cap"
    if cap_bucket is VictoryPointCapBucket.BATTLE_READY:
        return policy.battle_ready_vp, "battle_ready_vp_cap"
    raise GameLifecycleError("Unsupported VictoryPointCapBucket for cap resolution.")


__all__ = (
    "VictoryPointCapResolution",
    "resolve_victory_point_cap",
)
