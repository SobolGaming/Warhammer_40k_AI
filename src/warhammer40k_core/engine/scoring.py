from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class VictoryPointSourceKind(StrEnum):
    PRIMARY = "primary"
    FIXED_SECONDARY = "fixed_secondary"
    TACTICAL_SECONDARY = "tactical_secondary"
    MISSION_ACTION = "mission_action"
    BATTLE_READY = "battle_ready"


class VictoryPointCapBucket(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    BATTLE_READY = "battle_ready"


class ScoringWindowKind(StrEnum):
    END_OF_ROUND = "end_of_round"
    END_OF_GAME = "end_of_game"


class SecondaryMissionCardStatus(StrEnum):
    ACTIVE = "active"
    SCORED = "scored"
    DISCARDED = "discarded"


class SecondaryMissionCardMode(StrEnum):
    FIXED = "fixed"
    TACTICAL = "tactical"


class VictoryPointTransactionPayload(TypedDict):
    transaction_id: str
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: str
    source_id: str
    scoring_timing: str
    hidden: bool
    metadata: JsonValue


class VictoryPointLedgerPayload(TypedDict):
    player_id: str
    victory_points: int
    transactions: list[VictoryPointTransactionPayload]


class VictoryPointAwardPayload(TypedDict):
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: str
    source_id: str
    scoring_timing: str
    hidden: bool
    metadata: JsonValue


class MissionScoringPolicyPayload(TypedDict):
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: str
    primary_scoring_rule_id: str
    primary_scoring_rule_condition: str
    primary_scoring_rule_source_id: str
    primary_vp_per_controlled_objective: int
    primary_max_vp_per_turn: int
    secondary_vp_per_score: int
    secondary_scoring_rules: list[SecondaryMissionScoringRulePayload]
    mission_action_scoring_rules: list[MissionActionScoringRulePayload]
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    end_of_round_scoring_windows: list[str]
    end_of_game_scoring_windows: list[str]
    source_id: str


class SecondaryMissionScoringRulePayload(TypedDict):
    secondary_mission_id: str
    source_kind: str
    victory_points: int
    condition: str
    rule_id: str
    source_id: str


class MissionActionScoringRulePayload(TypedDict):
    mission_action_id: str
    mission_id: str
    mission_kind: str
    scoring_source_id: str
    victory_points: int
    cap_bucket: str
    source_id: str


class SecondaryMissionCardStatePayload(TypedDict):
    player_id: str
    secondary_mission_id: str
    mode: str
    battle_round: int
    status: str
    source_result_id: str | None
    scored_transaction_id: str | None
    discarded_result_id: str | None


class ScoringWindowStatePayload(TypedDict):
    window_id: str
    game_id: str
    battle_round: int
    window_kind: str
    window: str
    source_id: str


class FinalScorePayload(TypedDict):
    player_id: str
    victory_points: int


class FinalScoreLinePayload(TypedDict):
    player_id: str
    victory_points: int
    raw_victory_points: int
    raw_primary_vp: int
    raw_secondary_vp: int
    raw_battle_ready_vp: int
    raw_other_vp: int
    capped_primary_vp: int
    capped_secondary_vp: int
    capped_battle_ready_vp: int
    capped_other_vp: int
    cap_adjustment: int


class FinalScoringAuditPayload(TypedDict):
    policy_source_id: str
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp_cap: int
    total_vp_cap: int
    scoring_windows: list[ScoringWindowStatePayload]
    player_scores: list[FinalScoreLinePayload]


class FinalScoringResultPayload(TypedDict):
    result_id: str
    game_id: str
    battle_round: int
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    final_scores: list[FinalScorePayload]
    winner_player_ids: list[str]
    is_draw: bool
    scoring_audit: FinalScoringAuditPayload


@dataclass(frozen=True, slots=True)
class VictoryPointTransaction:
    transaction_id: str
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: VictoryPointSourceKind
    source_id: str
    scoring_timing: str
    hidden: bool = False
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _validate_identifier("VictoryPointTransaction transaction_id", self.transaction_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointTransaction player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("VictoryPointTransaction battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("VictoryPointTransaction phase", self.phase),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_non_negative_int("VictoryPointTransaction amount", self.amount),
        )
        object.__setattr__(
            self,
            "source_kind",
            victory_point_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("VictoryPointTransaction source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "scoring_timing",
            _validate_identifier(
                "VictoryPointTransaction scoring_timing",
                self.scoring_timing,
            ),
        )
        object.__setattr__(
            self,
            "hidden",
            _validate_bool("VictoryPointTransaction hidden", self.hidden),
        )
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))

    def to_payload(self) -> VictoryPointTransactionPayload:
        return {
            "transaction_id": self.transaction_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "amount": self.amount,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "scoring_timing": self.scoring_timing,
            "hidden": self.hidden,
            "metadata": self.metadata,
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        choices_revealed = _validate_bool(
            "secondary_mission_choices_revealed",
            secondary_mission_choices_revealed,
        )
        if (
            self.hidden
            and viewer != self.player_id
            and not (
                choices_revealed
                and self.source_kind
                in {
                    VictoryPointSourceKind.FIXED_SECONDARY,
                    VictoryPointSourceKind.TACTICAL_SECONDARY,
                }
            )
        ):
            return {
                "transaction_id": self.transaction_id,
                "player_id": self.player_id,
                "battle_round": self.battle_round,
                "phase": self.phase,
                "amount": self.amount,
                "hidden": True,
            }
        payload = cast(dict[str, JsonValue], self.to_payload())
        if self.hidden and viewer != self.player_id:
            payload["hidden"] = False
        return payload

    @classmethod
    def from_payload(cls, payload: VictoryPointTransactionPayload) -> Self:
        return cls(
            transaction_id=payload["transaction_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            amount=payload["amount"],
            source_kind=victory_point_source_kind_from_token(payload["source_kind"]),
            source_id=payload["source_id"],
            scoring_timing=payload["scoring_timing"],
            hidden=payload["hidden"],
            metadata=payload["metadata"],
        )


@dataclass(frozen=True, slots=True)
class VictoryPointAward:
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: VictoryPointSourceKind
    source_id: str
    scoring_timing: str
    hidden: bool = False
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointAward player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("VictoryPointAward battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("VictoryPointAward phase", self.phase),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_positive_int("VictoryPointAward amount", self.amount),
        )
        object.__setattr__(
            self, "source_kind", victory_point_source_kind_from_token(self.source_kind)
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("VictoryPointAward source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "scoring_timing",
            _validate_identifier("VictoryPointAward scoring_timing", self.scoring_timing),
        )
        object.__setattr__(self, "hidden", _validate_bool("VictoryPointAward hidden", self.hidden))
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))

    def to_payload(self) -> VictoryPointAwardPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "amount": self.amount,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "scoring_timing": self.scoring_timing,
            "hidden": self.hidden,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class VictoryPointLedger:
    player_id: str
    victory_points: int = 0
    transactions: tuple[VictoryPointTransaction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointLedger player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int("VictoryPointLedger victory_points", self.victory_points),
        )
        transactions = _validate_victory_point_transaction_tuple(
            "VictoryPointLedger transactions",
            self.transactions,
            player_id=self.player_id,
        )
        total = sum(transaction.amount for transaction in transactions)
        if total != self.victory_points:
            raise GameLifecycleError("VictoryPointLedger points must match transactions.")
        object.__setattr__(self, "transactions", transactions)

    @classmethod
    def initial(cls, *, player_id: str) -> Self:
        return cls(player_id=player_id)

    def award(
        self,
        award: VictoryPointAward,
        *,
        applied_amount: int | None = None,
        metadata: JsonValue | None = None,
    ) -> tuple[Self, VictoryPointTransaction]:
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VictoryPointLedger award must be a VictoryPointAward.")
        if award.player_id != self.player_id:
            raise GameLifecycleError("VictoryPointLedger award player_id drift.")
        transaction_amount = (
            award.amount
            if applied_amount is None
            else _validate_non_negative_int("VictoryPointLedger applied_amount", applied_amount)
        )
        if transaction_amount > award.amount:
            raise GameLifecycleError("VictoryPointLedger applied_amount exceeds award amount.")
        transaction_metadata = award.metadata if metadata is None else validate_json_value(metadata)
        transaction = VictoryPointTransaction(
            transaction_id=(
                f"victory-point:{self.player_id}:round-{award.battle_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=award.battle_round,
            phase=award.phase,
            amount=transaction_amount,
            source_kind=award.source_kind,
            source_id=award.source_id,
            scoring_timing=award.scoring_timing,
            hidden=award.hidden,
            metadata=transaction_metadata,
        )
        return (
            type(self)(
                player_id=self.player_id,
                victory_points=self.victory_points + transaction_amount,
                transactions=(*self.transactions, transaction),
            ),
            transaction,
        )

    def points_from_source_kind(self, source_kind: VictoryPointSourceKind) -> int:
        requested_kind = victory_point_source_kind_from_token(source_kind)
        return sum(
            transaction.amount
            for transaction in self.transactions
            if transaction.source_kind is requested_kind
        )

    def to_payload(self) -> VictoryPointLedgerPayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "transactions": [transaction.to_payload() for transaction in self.transactions],
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "transactions": [
                transaction.to_public_payload(
                    viewer_player_id=viewer_player_id,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
                for transaction in self.transactions
            ],
        }

    @classmethod
    def from_payload(cls, payload: VictoryPointLedgerPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            victory_points=payload["victory_points"],
            transactions=tuple(
                VictoryPointTransaction.from_payload(transaction)
                for transaction in payload["transactions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class SecondaryMissionScoringRule:
    secondary_mission_id: str
    source_kind: VictoryPointSourceKind
    victory_points: int
    condition: str
    rule_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier(
                "SecondaryMissionScoringRule secondary_mission_id",
                self.secondary_mission_id,
            ),
        )
        source_kind = victory_point_source_kind_from_token(self.source_kind)
        if source_kind not in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            raise GameLifecycleError(
                "SecondaryMissionScoringRule source_kind must be a secondary source kind."
            )
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int(
                "SecondaryMissionScoringRule victory_points",
                self.victory_points,
            ),
        )
        object.__setattr__(
            self,
            "condition",
            _validate_identifier("SecondaryMissionScoringRule condition", self.condition),
        )
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("SecondaryMissionScoringRule rule_id", self.rule_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryMissionScoringRule source_id", self.source_id),
        )
        expected_condition = (
            "fixed_secondary_condition"
            if source_kind is VictoryPointSourceKind.FIXED_SECONDARY
            else "tactical_secondary_condition"
        )
        if self.condition != expected_condition:
            raise GameLifecycleError(
                "Unsupported secondary scoring rule condition for source kind."
            )

    def to_payload(self) -> SecondaryMissionScoringRulePayload:
        return {
            "secondary_mission_id": self.secondary_mission_id,
            "source_kind": self.source_kind.value,
            "victory_points": self.victory_points,
            "condition": self.condition,
            "rule_id": self.rule_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryMissionScoringRulePayload) -> Self:
        return cls(
            secondary_mission_id=payload["secondary_mission_id"],
            source_kind=victory_point_source_kind_from_token(payload["source_kind"]),
            victory_points=payload["victory_points"],
            condition=payload["condition"],
            rule_id=payload["rule_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionActionScoringRule:
    mission_action_id: str
    mission_id: str
    mission_kind: str
    scoring_source_id: str
    victory_points: int
    cap_bucket: VictoryPointCapBucket
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_action_id",
            _validate_identifier(
                "MissionActionScoringRule mission_action_id",
                self.mission_action_id,
            ),
        )
        object.__setattr__(
            self,
            "mission_id",
            _validate_identifier("MissionActionScoringRule mission_id", self.mission_id),
        )
        mission_kind = _validate_identifier(
            "MissionActionScoringRule mission_kind",
            self.mission_kind,
        )
        if mission_kind not in {"primary", "secondary"}:
            raise GameLifecycleError("MissionActionScoringRule mission_kind is unsupported.")
        object.__setattr__(self, "mission_kind", mission_kind)
        object.__setattr__(
            self,
            "scoring_source_id",
            _validate_identifier(
                "MissionActionScoringRule scoring_source_id",
                self.scoring_source_id,
            ),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int(
                "MissionActionScoringRule victory_points",
                self.victory_points,
            ),
        )
        cap_bucket = victory_point_cap_bucket_from_token(self.cap_bucket)
        expected_bucket = (
            VictoryPointCapBucket.PRIMARY
            if mission_kind == "primary"
            else VictoryPointCapBucket.SECONDARY
        )
        if cap_bucket is not expected_bucket:
            raise GameLifecycleError("MissionActionScoringRule cap_bucket does not match kind.")
        object.__setattr__(self, "cap_bucket", cap_bucket)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionActionScoringRule source_id", self.source_id),
        )

    def to_payload(self) -> MissionActionScoringRulePayload:
        return {
            "mission_action_id": self.mission_action_id,
            "mission_id": self.mission_id,
            "mission_kind": self.mission_kind,
            "scoring_source_id": self.scoring_source_id,
            "victory_points": self.victory_points,
            "cap_bucket": self.cap_bucket.value,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionActionScoringRulePayload) -> Self:
        return cls(
            mission_action_id=payload["mission_action_id"],
            mission_id=payload["mission_id"],
            mission_kind=payload["mission_kind"],
            scoring_source_id=payload["scoring_source_id"],
            victory_points=payload["victory_points"],
            cap_bucket=victory_point_cap_bucket_from_token(payload["cap_bucket"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ScoringWindowState:
    window_id: str
    game_id: str
    battle_round: int
    window_kind: ScoringWindowKind
    window: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _validate_identifier("ScoringWindowState window_id", self.window_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ScoringWindowState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ScoringWindowState battle_round", self.battle_round),
        )
        object.__setattr__(self, "window_kind", scoring_window_kind_from_token(self.window_kind))
        object.__setattr__(
            self,
            "window",
            _validate_identifier("ScoringWindowState window", self.window),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ScoringWindowState source_id", self.source_id),
        )

    def to_payload(self) -> ScoringWindowStatePayload:
        return {
            "window_id": self.window_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "window_kind": self.window_kind.value,
            "window": self.window,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ScoringWindowStatePayload) -> Self:
        return cls(
            window_id=payload["window_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            window_kind=scoring_window_kind_from_token(payload["window_kind"]),
            window=payload["window"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class FinalScoreLine:
    player_id: str
    victory_points: int
    raw_victory_points: int
    raw_primary_vp: int
    raw_secondary_vp: int
    raw_battle_ready_vp: int
    raw_other_vp: int
    capped_primary_vp: int
    capped_secondary_vp: int
    capped_battle_ready_vp: int
    capped_other_vp: int
    cap_adjustment: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FinalScoreLine player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int("FinalScoreLine victory_points", self.victory_points),
        )
        object.__setattr__(
            self,
            "raw_victory_points",
            _validate_non_negative_int(
                "FinalScoreLine raw_victory_points", self.raw_victory_points
            ),
        )
        object.__setattr__(
            self,
            "raw_primary_vp",
            _validate_non_negative_int("FinalScoreLine raw_primary_vp", self.raw_primary_vp),
        )
        object.__setattr__(
            self,
            "raw_secondary_vp",
            _validate_non_negative_int("FinalScoreLine raw_secondary_vp", self.raw_secondary_vp),
        )
        object.__setattr__(
            self,
            "raw_battle_ready_vp",
            _validate_non_negative_int(
                "FinalScoreLine raw_battle_ready_vp", self.raw_battle_ready_vp
            ),
        )
        object.__setattr__(
            self,
            "raw_other_vp",
            _validate_non_negative_int("FinalScoreLine raw_other_vp", self.raw_other_vp),
        )
        object.__setattr__(
            self,
            "capped_primary_vp",
            _validate_non_negative_int("FinalScoreLine capped_primary_vp", self.capped_primary_vp),
        )
        object.__setattr__(
            self,
            "capped_secondary_vp",
            _validate_non_negative_int(
                "FinalScoreLine capped_secondary_vp", self.capped_secondary_vp
            ),
        )
        object.__setattr__(
            self,
            "capped_battle_ready_vp",
            _validate_non_negative_int(
                "FinalScoreLine capped_battle_ready_vp", self.capped_battle_ready_vp
            ),
        )
        object.__setattr__(
            self,
            "capped_other_vp",
            _validate_non_negative_int("FinalScoreLine capped_other_vp", self.capped_other_vp),
        )
        object.__setattr__(
            self,
            "cap_adjustment",
            _validate_non_negative_int("FinalScoreLine cap_adjustment", self.cap_adjustment),
        )
        capped_total = (
            self.capped_primary_vp
            + self.capped_secondary_vp
            + self.capped_battle_ready_vp
            + self.capped_other_vp
        )
        if capped_total != self.victory_points:
            raise GameLifecycleError("FinalScoreLine victory_points must match capped totals.")
        if self.raw_victory_points < self.victory_points:
            raise GameLifecycleError("FinalScoreLine raw_victory_points cannot be capped upward.")
        if self.raw_victory_points - self.victory_points != self.cap_adjustment:
            raise GameLifecycleError("FinalScoreLine cap_adjustment drift.")

    @classmethod
    def from_ledger(cls, *, ledger: VictoryPointLedger, policy: MissionScoringPolicy) -> Self:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("FinalScoreLine requires a VictoryPointLedger.")
        if type(policy) is not MissionScoringPolicy:
            raise GameLifecycleError("FinalScoreLine requires a MissionScoringPolicy.")
        raw_primary = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.PRIMARY,
        )
        raw_secondary = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.SECONDARY,
        )
        raw_battle_ready = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.BATTLE_READY,
        )
        raw_other = ledger.victory_points - raw_primary - raw_secondary - raw_battle_ready
        if raw_other < 0:
            raise GameLifecycleError("FinalScoreLine source totals exceed raw ledger total.")
        capped_primary = min(raw_primary, policy.primary_vp_cap)
        capped_secondary = min(raw_secondary, policy.secondary_vp_cap)
        capped_battle_ready = min(raw_battle_ready, policy.battle_ready_vp)
        capped_pre_total = capped_primary + capped_secondary + capped_battle_ready + raw_other
        capped_total = min(capped_pre_total, policy.total_vp_cap)
        capped_other = capped_total - capped_primary - capped_secondary - capped_battle_ready
        if capped_other < 0:
            raise GameLifecycleError("FinalScoreLine total cap is below source-capped score.")
        return cls(
            player_id=ledger.player_id,
            victory_points=capped_total,
            raw_victory_points=ledger.victory_points,
            raw_primary_vp=raw_primary,
            raw_secondary_vp=raw_secondary,
            raw_battle_ready_vp=raw_battle_ready,
            raw_other_vp=raw_other,
            capped_primary_vp=capped_primary,
            capped_secondary_vp=capped_secondary,
            capped_battle_ready_vp=capped_battle_ready,
            capped_other_vp=capped_other,
            cap_adjustment=ledger.victory_points - capped_total,
        )

    def to_public_score_payload(self) -> FinalScorePayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
        }

    def to_payload(self) -> FinalScoreLinePayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "raw_victory_points": self.raw_victory_points,
            "raw_primary_vp": self.raw_primary_vp,
            "raw_secondary_vp": self.raw_secondary_vp,
            "raw_battle_ready_vp": self.raw_battle_ready_vp,
            "raw_other_vp": self.raw_other_vp,
            "capped_primary_vp": self.capped_primary_vp,
            "capped_secondary_vp": self.capped_secondary_vp,
            "capped_battle_ready_vp": self.capped_battle_ready_vp,
            "capped_other_vp": self.capped_other_vp,
            "cap_adjustment": self.cap_adjustment,
        }

    @classmethod
    def from_payload(cls, payload: FinalScoreLinePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            victory_points=payload["victory_points"],
            raw_victory_points=payload["raw_victory_points"],
            raw_primary_vp=payload["raw_primary_vp"],
            raw_secondary_vp=payload["raw_secondary_vp"],
            raw_battle_ready_vp=payload["raw_battle_ready_vp"],
            raw_other_vp=payload["raw_other_vp"],
            capped_primary_vp=payload["capped_primary_vp"],
            capped_secondary_vp=payload["capped_secondary_vp"],
            capped_battle_ready_vp=payload["capped_battle_ready_vp"],
            capped_other_vp=payload["capped_other_vp"],
            cap_adjustment=payload["cap_adjustment"],
        )


@dataclass(frozen=True, slots=True)
class FinalScoringResult:
    result_id: str
    game_id: str
    battle_round: int
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    final_scores: tuple[FinalScoreLine, ...]
    winner_player_ids: tuple[str, ...]
    is_draw: bool
    policy_source_id: str
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp_cap: int
    total_vp_cap: int
    scoring_windows: tuple[ScoringWindowState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("FinalScoringResult result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("FinalScoringResult game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FinalScoringResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier("FinalScoringResult mission_pack_id", self.mission_pack_id),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier("FinalScoringResult primary_mission_id", self.primary_mission_id),
        )
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "FinalScoringResult game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(
            self,
            "final_scores",
            _validate_final_score_tuple(self.final_scores),
        )
        object.__setattr__(
            self,
            "winner_player_ids",
            _validate_identifier_tuple_ordered(
                "FinalScoringResult winner_player_ids",
                self.winner_player_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "is_draw",
            _validate_bool("FinalScoringResult is_draw", self.is_draw),
        )
        object.__setattr__(
            self,
            "policy_source_id",
            _validate_identifier("FinalScoringResult policy_source_id", self.policy_source_id),
        )
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int("FinalScoringResult primary_vp_cap", self.primary_vp_cap),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int("FinalScoringResult secondary_vp_cap", self.secondary_vp_cap),
        )
        object.__setattr__(
            self,
            "battle_ready_vp_cap",
            _validate_non_negative_int(
                "FinalScoringResult battle_ready_vp_cap", self.battle_ready_vp_cap
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int("FinalScoringResult total_vp_cap", self.total_vp_cap),
        )
        object.__setattr__(
            self,
            "scoring_windows",
            _validate_scoring_window_tuple(self.scoring_windows, game_id=self.game_id),
        )
        expected_winners = _winner_player_ids_from_scores(self.final_scores)
        if self.winner_player_ids != expected_winners:
            raise GameLifecycleError("FinalScoringResult winner_player_ids drift.")
        if self.is_draw != (len(expected_winners) != 1):
            raise GameLifecycleError("FinalScoringResult is_draw drift.")
        if self.battle_round != self.game_length_battle_rounds:
            raise GameLifecycleError("FinalScoringResult battle_round must match game length.")

    @classmethod
    def from_ledgers(
        cls,
        *,
        game_id: str,
        battle_round: int,
        policy: MissionScoringPolicy,
        ledgers: tuple[VictoryPointLedger, ...],
        scoring_windows: tuple[ScoringWindowState, ...],
    ) -> Self:
        if type(policy) is not MissionScoringPolicy:
            raise GameLifecycleError("Final scoring requires a MissionScoringPolicy.")
        requested_game_id = _validate_identifier("game_id", game_id)
        requested_round = _validate_positive_int("battle_round", battle_round)
        validated_windows = _validate_required_final_scoring_windows(
            scoring_windows=scoring_windows,
            policy=policy,
            game_id=requested_game_id,
            battle_round=requested_round,
        )
        final_scores = tuple(
            sorted(
                (FinalScoreLine.from_ledger(ledger=ledger, policy=policy) for ledger in ledgers),
                key=lambda score: score.player_id,
            )
        )
        if not final_scores:
            raise GameLifecycleError("Final scoring requires at least one player score.")
        winner_ids = _winner_player_ids_from_scores(final_scores)
        return cls(
            result_id=f"final-scoring:{requested_game_id}:round-{requested_round:02d}",
            game_id=requested_game_id,
            battle_round=requested_round,
            mission_pack_id=policy.mission_pack_id,
            primary_mission_id=policy.primary_mission_id,
            game_length_battle_rounds=policy.game_length_battle_rounds,
            final_scores=final_scores,
            winner_player_ids=winner_ids,
            is_draw=len(winner_ids) != 1,
            policy_source_id=policy.source_id,
            primary_vp_cap=policy.primary_vp_cap,
            secondary_vp_cap=policy.secondary_vp_cap,
            battle_ready_vp_cap=policy.battle_ready_vp,
            total_vp_cap=policy.total_vp_cap,
            scoring_windows=validated_windows,
        )

    def to_payload(self) -> FinalScoringResultPayload:
        return {
            "result_id": self.result_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "final_scores": [score.to_public_score_payload() for score in self.final_scores],
            "winner_player_ids": list(self.winner_player_ids),
            "is_draw": self.is_draw,
            "scoring_audit": {
                "policy_source_id": self.policy_source_id,
                "primary_vp_cap": self.primary_vp_cap,
                "secondary_vp_cap": self.secondary_vp_cap,
                "battle_ready_vp_cap": self.battle_ready_vp_cap,
                "total_vp_cap": self.total_vp_cap,
                "scoring_windows": [window.to_payload() for window in self.scoring_windows],
                "player_scores": [score.to_payload() for score in self.final_scores],
            },
        }

    @classmethod
    def from_payload(cls, payload: FinalScoringResultPayload) -> Self:
        audit = payload["scoring_audit"]
        result = cls(
            result_id=payload["result_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_id=payload["primary_mission_id"],
            game_length_battle_rounds=payload["game_length_battle_rounds"],
            final_scores=tuple(
                FinalScoreLine.from_payload(score) for score in audit["player_scores"]
            ),
            winner_player_ids=tuple(payload["winner_player_ids"]),
            is_draw=payload["is_draw"],
            policy_source_id=audit["policy_source_id"],
            primary_vp_cap=audit["primary_vp_cap"],
            secondary_vp_cap=audit["secondary_vp_cap"],
            battle_ready_vp_cap=audit["battle_ready_vp_cap"],
            total_vp_cap=audit["total_vp_cap"],
            scoring_windows=tuple(
                ScoringWindowState.from_payload(window) for window in audit["scoring_windows"]
            ),
        )
        if [score.to_public_score_payload() for score in result.final_scores] != payload[
            "final_scores"
        ]:
            raise GameLifecycleError("FinalScoringResult final_scores drift from scoring audit.")
        return result


@dataclass(frozen=True, slots=True)
class MissionScoringPolicy:
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: ObjectiveControlTiming
    primary_scoring_rule_id: str
    primary_scoring_rule_condition: str
    primary_scoring_rule_source_id: str
    primary_vp_per_controlled_objective: int
    primary_max_vp_per_turn: int
    secondary_vp_per_score: int
    secondary_scoring_rules: tuple[SecondaryMissionScoringRule, ...]
    mission_action_scoring_rules: tuple[MissionActionScoringRule, ...]
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    end_of_round_scoring_windows: tuple[str, ...]
    end_of_game_scoring_windows: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier("MissionScoringPolicy mission_pack_id", self.mission_pack_id),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier(
                "MissionScoringPolicy primary_mission_id",
                self.primary_mission_id,
            ),
        )
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "MissionScoringPolicy game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_phase",
            _validate_identifier(
                "MissionScoringPolicy primary_scoring_phase",
                self.primary_scoring_phase,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_timing",
            objective_control_timing_from_token(self.primary_scoring_timing),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_id",
            _validate_identifier(
                "MissionScoringPolicy primary_scoring_rule_id",
                self.primary_scoring_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_condition",
            _validate_identifier(
                "MissionScoringPolicy primary_scoring_rule_condition",
                self.primary_scoring_rule_condition,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_source_id",
            _validate_identifier(
                "MissionScoringPolicy primary_scoring_rule_source_id",
                self.primary_scoring_rule_source_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_vp_per_controlled_objective",
            _validate_positive_int(
                "MissionScoringPolicy primary_vp_per_controlled_objective",
                self.primary_vp_per_controlled_objective,
            ),
        )
        object.__setattr__(
            self,
            "primary_max_vp_per_turn",
            _validate_positive_int(
                "MissionScoringPolicy primary_max_vp_per_turn",
                self.primary_max_vp_per_turn,
            ),
        )
        object.__setattr__(
            self,
            "secondary_vp_per_score",
            _validate_positive_int(
                "MissionScoringPolicy secondary_vp_per_score",
                self.secondary_vp_per_score,
            ),
        )
        object.__setattr__(
            self,
            "secondary_scoring_rules",
            _validate_secondary_scoring_rule_tuple(self.secondary_scoring_rules),
        )
        object.__setattr__(
            self,
            "mission_action_scoring_rules",
            _validate_mission_action_scoring_rule_tuple(self.mission_action_scoring_rules),
        )
        object.__setattr__(
            self,
            "mission_action_vp",
            _validate_positive_int(
                "MissionScoringPolicy mission_action_vp", self.mission_action_vp
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_timing",
            _validate_identifier(
                "MissionScoringPolicy reserve_destruction_timing",
                self.reserve_destruction_timing,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_battle_round",
            _validate_optional_positive_int(
                "MissionScoringPolicy reserve_destruction_battle_round",
                self.reserve_destruction_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_excludes_during_battle_strategic_reserves",
            _validate_bool(
                "MissionScoringPolicy "
                "reserve_destruction_excludes_during_battle_strategic_reserves",
                self.reserve_destruction_excludes_during_battle_strategic_reserves,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_only_declare_battle_formations",
            _validate_bool(
                "MissionScoringPolicy reserve_destruction_only_declare_battle_formations",
                self.reserve_destruction_only_declare_battle_formations,
            ),
        )
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int("MissionScoringPolicy primary_vp_cap", self.primary_vp_cap),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int(
                "MissionScoringPolicy secondary_vp_cap",
                self.secondary_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "battle_ready_vp",
            _validate_non_negative_int(
                "MissionScoringPolicy battle_ready_vp",
                self.battle_ready_vp,
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int("MissionScoringPolicy total_vp_cap", self.total_vp_cap),
        )
        object.__setattr__(
            self,
            "end_of_round_scoring_windows",
            _validate_identifier_tuple_ordered(
                "MissionScoringPolicy end_of_round_scoring_windows",
                self.end_of_round_scoring_windows,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "end_of_game_scoring_windows",
            _validate_identifier_tuple_ordered(
                "MissionScoringPolicy end_of_game_scoring_windows",
                self.end_of_game_scoring_windows,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionScoringPolicy source_id", self.source_id),
        )

    def primary_award_from_objective_control(
        self,
        record: ObjectiveControlRecord,
    ) -> VictoryPointAward | None:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if record.phase != self.primary_scoring_phase:
            return None
        if record.timing is not self.primary_scoring_timing:
            return None
        if self.primary_scoring_rule_condition == (
            "each_controlled_objective_from_battle_round_two"
        ):
            if record.battle_round < 2:
                return None
        elif self.primary_scoring_rule_condition != "each_controlled_objective":
            raise GameLifecycleError("Unsupported primary scoring rule condition.")
        controlled_objective_ids = tuple(
            result.objective_id
            for result in record.results
            if result.status is ObjectiveControlStatus.CONTROLLED
            and result.controlled_by_player_id == record.active_player_id
        )
        if not controlled_objective_ids:
            return None
        amount = min(
            len(controlled_objective_ids) * self.primary_vp_per_controlled_objective,
            self.primary_max_vp_per_turn,
        )
        return VictoryPointAward(
            player_id=record.active_player_id,
            battle_round=record.battle_round,
            phase=record.phase,
            amount=amount,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=self.primary_mission_id,
            scoring_timing=record.timing.value,
            hidden=False,
            metadata={
                "objective_control_record_id": record.record_id,
                "controlled_objective_ids": list(controlled_objective_ids),
                "scoring_rule_id": self.primary_scoring_rule_id,
                "scoring_rule_condition": self.primary_scoring_rule_condition,
            },
        )

    def secondary_award(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        secondary_mission_id: str,
        source_kind: VictoryPointSourceKind,
        hidden: bool,
    ) -> VictoryPointAward:
        kind = victory_point_source_kind_from_token(source_kind)
        if kind not in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            raise GameLifecycleError("Secondary scoring requires a secondary source kind.")
        requested_secondary_id = _validate_identifier("secondary_mission_id", secondary_mission_id)
        rule = self._secondary_scoring_rule(
            secondary_mission_id=requested_secondary_id,
            source_kind=kind,
        )
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=rule.victory_points,
            source_kind=kind,
            source_id=requested_secondary_id,
            scoring_timing="secondary_mission_score",
            hidden=hidden,
            metadata={
                "secondary_mission_id": requested_secondary_id,
                "scoring_rule_id": rule.rule_id,
                "scoring_rule_condition": rule.condition,
            },
        )

    def mission_action_award(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        action_id: str,
        source_id: str,
        amount: int | None = None,
    ) -> VictoryPointAward:
        source_rule = self._mission_action_scoring_rule_for_source_id(source_id)
        requested_amount = (
            source_rule.victory_points
            if amount is None
            else _validate_positive_int("amount", amount)
        )
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=requested_amount,
            source_kind=VictoryPointSourceKind.MISSION_ACTION,
            source_id=source_rule.scoring_source_id,
            scoring_timing="mission_action_complete",
            hidden=False,
            metadata={"action_id": _validate_identifier("action_id", action_id)},
        )

    def capped_award_for_ledger(
        self,
        *,
        ledger: VictoryPointLedger,
        award: VictoryPointAward,
    ) -> tuple[int, JsonValue]:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointLedger.")
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointAward.")
        if ledger.player_id != award.player_id:
            raise GameLifecycleError("VP cap resolution player_id drift.")

        cap_bucket = self.cap_bucket_for_victory_point_source(
            source_kind=award.source_kind,
            source_id=award.source_id,
        )
        source_points_before = self.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=cap_bucket,
        )
        source_cap = self._source_cap_for_bucket(cap_bucket)
        source_remaining = max(source_cap - source_points_before, 0)
        total_remaining = max(self.total_vp_cap - ledger.victory_points, 0)
        applied_amount = min(award.amount, source_remaining, total_remaining)
        if applied_amount == award.amount:
            return applied_amount, award.metadata

        capped_reasons: list[str] = []
        if source_remaining < award.amount:
            capped_reasons.append(self._source_cap_reason(cap_bucket))
        if total_remaining < award.amount:
            capped_reasons.append("total_vp_cap")
        return (
            applied_amount,
            _metadata_with_vp_cap_audit(
                award.metadata,
                requested_amount=award.amount,
                applied_amount=applied_amount,
                source_cap=source_cap,
                source_points_before=source_points_before,
                source_points_after=source_points_before + applied_amount,
                total_cap=self.total_vp_cap,
                total_points_before=ledger.victory_points,
                total_points_after=ledger.victory_points + applied_amount,
                capped_reasons=tuple(capped_reasons),
            ),
        )

    def to_payload(self) -> MissionScoringPolicyPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "primary_scoring_phase": self.primary_scoring_phase,
            "primary_scoring_timing": self.primary_scoring_timing.value,
            "primary_scoring_rule_id": self.primary_scoring_rule_id,
            "primary_scoring_rule_condition": self.primary_scoring_rule_condition,
            "primary_scoring_rule_source_id": self.primary_scoring_rule_source_id,
            "primary_vp_per_controlled_objective": self.primary_vp_per_controlled_objective,
            "primary_max_vp_per_turn": self.primary_max_vp_per_turn,
            "secondary_vp_per_score": self.secondary_vp_per_score,
            "secondary_scoring_rules": [rule.to_payload() for rule in self.secondary_scoring_rules],
            "mission_action_scoring_rules": [
                rule.to_payload() for rule in self.mission_action_scoring_rules
            ],
            "mission_action_vp": self.mission_action_vp,
            "reserve_destruction_timing": self.reserve_destruction_timing,
            "reserve_destruction_battle_round": self.reserve_destruction_battle_round,
            "reserve_destruction_excludes_during_battle_strategic_reserves": (
                self.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            "reserve_destruction_only_declare_battle_formations": (
                self.reserve_destruction_only_declare_battle_formations
            ),
            "primary_vp_cap": self.primary_vp_cap,
            "secondary_vp_cap": self.secondary_vp_cap,
            "battle_ready_vp": self.battle_ready_vp,
            "total_vp_cap": self.total_vp_cap,
            "end_of_round_scoring_windows": list(self.end_of_round_scoring_windows),
            "end_of_game_scoring_windows": list(self.end_of_game_scoring_windows),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionScoringPolicyPayload) -> Self:
        return cls(
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_id=payload["primary_mission_id"],
            game_length_battle_rounds=payload["game_length_battle_rounds"],
            primary_scoring_phase=payload["primary_scoring_phase"],
            primary_scoring_timing=objective_control_timing_from_token(
                payload["primary_scoring_timing"]
            ),
            primary_scoring_rule_id=payload["primary_scoring_rule_id"],
            primary_scoring_rule_condition=payload["primary_scoring_rule_condition"],
            primary_scoring_rule_source_id=payload["primary_scoring_rule_source_id"],
            primary_vp_per_controlled_objective=payload["primary_vp_per_controlled_objective"],
            primary_max_vp_per_turn=payload["primary_max_vp_per_turn"],
            secondary_vp_per_score=payload["secondary_vp_per_score"],
            secondary_scoring_rules=tuple(
                SecondaryMissionScoringRule.from_payload(rule)
                for rule in payload["secondary_scoring_rules"]
            ),
            mission_action_scoring_rules=tuple(
                MissionActionScoringRule.from_payload(rule)
                for rule in payload["mission_action_scoring_rules"]
            ),
            mission_action_vp=payload["mission_action_vp"],
            reserve_destruction_timing=payload["reserve_destruction_timing"],
            reserve_destruction_battle_round=payload["reserve_destruction_battle_round"],
            reserve_destruction_excludes_during_battle_strategic_reserves=payload[
                "reserve_destruction_excludes_during_battle_strategic_reserves"
            ],
            reserve_destruction_only_declare_battle_formations=payload[
                "reserve_destruction_only_declare_battle_formations"
            ],
            primary_vp_cap=payload["primary_vp_cap"],
            secondary_vp_cap=payload["secondary_vp_cap"],
            battle_ready_vp=payload["battle_ready_vp"],
            total_vp_cap=payload["total_vp_cap"],
            end_of_round_scoring_windows=tuple(payload["end_of_round_scoring_windows"]),
            end_of_game_scoring_windows=tuple(payload["end_of_game_scoring_windows"]),
            source_id=payload["source_id"],
        )

    def cap_bucket_for_victory_point_source(
        self,
        *,
        source_kind: VictoryPointSourceKind,
        source_id: str,
    ) -> VictoryPointCapBucket:
        kind = victory_point_source_kind_from_token(source_kind)
        if kind is VictoryPointSourceKind.PRIMARY:
            return VictoryPointCapBucket.PRIMARY
        if kind in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            return VictoryPointCapBucket.SECONDARY
        if kind is VictoryPointSourceKind.MISSION_ACTION:
            return self._mission_action_scoring_rule_for_source_id(source_id).cap_bucket
        if kind is VictoryPointSourceKind.BATTLE_READY:
            return VictoryPointCapBucket.BATTLE_READY
        raise GameLifecycleError("Unsupported VictoryPointSourceKind for cap policy.")

    def ledger_points_from_cap_bucket(
        self,
        *,
        ledger: VictoryPointLedger,
        cap_bucket: VictoryPointCapBucket,
    ) -> int:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("VP cap bucket accounting requires a VictoryPointLedger.")
        requested_bucket = victory_point_cap_bucket_from_token(cap_bucket)
        return sum(
            transaction.amount
            for transaction in ledger.transactions
            if self.cap_bucket_for_victory_point_source(
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
            )
            is requested_bucket
        )

    def _source_cap_for_bucket(self, cap_bucket: VictoryPointCapBucket) -> int:
        bucket = victory_point_cap_bucket_from_token(cap_bucket)
        if bucket is VictoryPointCapBucket.PRIMARY:
            return self.primary_vp_cap
        if bucket is VictoryPointCapBucket.SECONDARY:
            return self.secondary_vp_cap
        if bucket is VictoryPointCapBucket.BATTLE_READY:
            return self.battle_ready_vp
        raise GameLifecycleError("Unsupported VictoryPointCapBucket for cap policy.")

    def _source_cap_reason(self, cap_bucket: VictoryPointCapBucket) -> str:
        bucket = victory_point_cap_bucket_from_token(cap_bucket)
        if bucket is VictoryPointCapBucket.PRIMARY:
            return "primary_vp_cap"
        if bucket is VictoryPointCapBucket.SECONDARY:
            return "secondary_vp_cap"
        if bucket is VictoryPointCapBucket.BATTLE_READY:
            return "battle_ready_vp_cap"
        raise GameLifecycleError("Unsupported VictoryPointCapBucket for cap policy.")

    def _mission_action_scoring_rule_for_source_id(
        self,
        source_id: str,
    ) -> MissionActionScoringRule:
        requested_source_id = _validate_identifier("source_id", source_id)
        match: MissionActionScoringRule | None = None
        for rule in self.mission_action_scoring_rules:
            if rule.scoring_source_id != requested_source_id:
                continue
            if match is not None:
                raise GameLifecycleError("Multiple Mission Action scoring rules matched.")
            match = rule
        if match is None:
            raise GameLifecycleError("Mission Action scoring source is not source-backed.")
        if (
            match.cap_bucket is VictoryPointCapBucket.PRIMARY
            and match.mission_id != self.primary_mission_id
        ):
            raise GameLifecycleError(
                "Primary Mission Action scoring source does not match active primary mission."
            )
        return match

    def _secondary_scoring_rule(
        self,
        *,
        secondary_mission_id: str,
        source_kind: VictoryPointSourceKind,
    ) -> SecondaryMissionScoringRule:
        match: SecondaryMissionScoringRule | None = None
        for rule in self.secondary_scoring_rules:
            if rule.secondary_mission_id != secondary_mission_id or rule.source_kind is not (
                source_kind
            ):
                continue
            if match is not None:
                raise GameLifecycleError("Multiple secondary scoring rules matched.")
            match = rule
        if match is None:
            raise GameLifecycleError("Secondary scoring rule is not source-backed.")
        return match


@dataclass(frozen=True, slots=True)
class SecondaryMissionCardState:
    player_id: str
    secondary_mission_id: str
    mode: SecondaryMissionCardMode
    battle_round: int
    status: SecondaryMissionCardStatus = SecondaryMissionCardStatus.ACTIVE
    source_result_id: str | None = None
    scored_transaction_id: str | None = None
    discarded_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryMissionCardState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier(
                "SecondaryMissionCardState secondary_mission_id",
                self.secondary_mission_id,
            ),
        )
        object.__setattr__(self, "mode", secondary_mission_card_mode_from_token(self.mode))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("SecondaryMissionCardState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "status",
            secondary_mission_card_status_from_token(self.status),
        )
        object.__setattr__(
            self,
            "source_result_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState source_result_id",
                self.source_result_id,
            ),
        )
        object.__setattr__(
            self,
            "scored_transaction_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState scored_transaction_id",
                self.scored_transaction_id,
            ),
        )
        object.__setattr__(
            self,
            "discarded_result_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState discarded_result_id",
                self.discarded_result_id,
            ),
        )
        if self.status is SecondaryMissionCardStatus.SCORED and self.scored_transaction_id is None:
            raise GameLifecycleError("Scored secondary card requires scored_transaction_id.")
        if self.status is SecondaryMissionCardStatus.DISCARDED and self.discarded_result_id is None:
            raise GameLifecycleError("Discarded secondary card requires discarded_result_id.")
        if self.status is SecondaryMissionCardStatus.ACTIVE and (
            self.scored_transaction_id is not None or self.discarded_result_id is not None
        ):
            raise GameLifecycleError("Active secondary card must not have terminal IDs.")

    @classmethod
    def active_fixed(cls, *, player_id: str, secondary_mission_id: str) -> Self:
        return cls(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.FIXED,
            battle_round=1,
        )

    @classmethod
    def active_tactical(
        cls,
        *,
        player_id: str,
        secondary_mission_id: str,
        battle_round: int,
        source_result_id: str,
    ) -> Self:
        return cls(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=battle_round,
            source_result_id=source_result_id,
        )

    def score(self, *, transaction_id: str) -> Self:
        if self.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError("Only active secondary cards can be scored.")
        return type(self)(
            player_id=self.player_id,
            secondary_mission_id=self.secondary_mission_id,
            mode=self.mode,
            battle_round=self.battle_round,
            status=SecondaryMissionCardStatus.SCORED,
            source_result_id=self.source_result_id,
            scored_transaction_id=transaction_id,
            discarded_result_id=None,
        )

    def discard(self, *, result_id: str) -> Self:
        if self.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError("Only active secondary cards can be discarded.")
        if self.mode is not SecondaryMissionCardMode.TACTICAL:
            raise GameLifecycleError("Only tactical secondary cards can be discarded.")
        return type(self)(
            player_id=self.player_id,
            secondary_mission_id=self.secondary_mission_id,
            mode=self.mode,
            battle_round=self.battle_round,
            status=SecondaryMissionCardStatus.DISCARDED,
            source_result_id=self.source_result_id,
            scored_transaction_id=None,
            discarded_result_id=result_id,
        )

    def to_payload(self) -> SecondaryMissionCardStatePayload:
        return {
            "player_id": self.player_id,
            "secondary_mission_id": self.secondary_mission_id,
            "mode": self.mode.value,
            "battle_round": self.battle_round,
            "status": self.status.value,
            "source_result_id": self.source_result_id,
            "scored_transaction_id": self.scored_transaction_id,
            "discarded_result_id": self.discarded_result_id,
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        choices_revealed = _validate_bool(
            "secondary_mission_choices_revealed",
            secondary_mission_choices_revealed,
        )
        if viewer != self.player_id and not choices_revealed:
            return {
                "player_id": self.player_id,
                "hidden": True,
            }
        payload = cast(dict[str, JsonValue], self.to_payload())
        payload["hidden"] = False
        return payload

    @classmethod
    def from_payload(cls, payload: SecondaryMissionCardStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            secondary_mission_id=payload["secondary_mission_id"],
            mode=secondary_mission_card_mode_from_token(payload["mode"]),
            battle_round=payload["battle_round"],
            status=secondary_mission_card_status_from_token(payload["status"]),
            source_result_id=payload["source_result_id"],
            scored_transaction_id=payload["scored_transaction_id"],
            discarded_result_id=payload["discarded_result_id"],
        )


def initial_victory_point_ledgers(player_ids: tuple[str, ...]) -> list[VictoryPointLedger]:
    return [VictoryPointLedger.initial(player_id=player_id) for player_id in player_ids]


def victory_point_source_kind_from_token(token: object) -> VictoryPointSourceKind:
    if type(token) is VictoryPointSourceKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("VictoryPointSourceKind token must be a string.")
    try:
        return VictoryPointSourceKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported VictoryPointSourceKind token: {token}.") from exc


def victory_point_cap_bucket_from_token(token: object) -> VictoryPointCapBucket:
    if type(token) is VictoryPointCapBucket:
        return token
    if type(token) is not str:
        raise GameLifecycleError("VictoryPointCapBucket token must be a string.")
    try:
        return VictoryPointCapBucket(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported VictoryPointCapBucket token: {token}.") from exc


def secondary_mission_card_status_from_token(token: object) -> SecondaryMissionCardStatus:
    if type(token) is SecondaryMissionCardStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionCardStatus token must be a string.")
    try:
        return SecondaryMissionCardStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionCardStatus token: {token}.") from exc


def secondary_mission_card_mode_from_token(token: object) -> SecondaryMissionCardMode:
    if type(token) is SecondaryMissionCardMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionCardMode token must be a string.")
    try:
        return SecondaryMissionCardMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionCardMode token: {token}.") from exc


def scoring_window_kind_from_token(token: object) -> ScoringWindowKind:
    if type(token) is ScoringWindowKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ScoringWindowKind token must be a string.")
    try:
        return ScoringWindowKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ScoringWindowKind token: {token}.") from exc


def objective_control_timing_from_token(token: object) -> ObjectiveControlTiming:
    if type(token) is ObjectiveControlTiming:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ObjectiveControlTiming token must be a string.")
    try:
        return ObjectiveControlTiming(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ObjectiveControlTiming token: {token}.") from exc


def _validate_victory_point_transaction_tuple(
    field_name: str,
    values: object,
    *,
    player_id: str,
) -> tuple[VictoryPointTransaction, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[VictoryPointTransaction] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not VictoryPointTransaction:
            raise GameLifecycleError(f"{field_name} must contain transactions.")
        if value.player_id != player_id:
            raise GameLifecycleError(f"{field_name} player_id drift.")
        if value.transaction_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.transaction_id)
        validated.append(value)
    return tuple(validated)


def _validate_secondary_scoring_rule_tuple(
    values: object,
) -> tuple[SecondaryMissionScoringRule, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MissionScoringPolicy secondary_scoring_rules must be a tuple.")
    validated: list[SecondaryMissionScoringRule] = []
    seen: set[tuple[str, VictoryPointSourceKind]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryMissionScoringRule:
            raise GameLifecycleError(
                "MissionScoringPolicy secondary_scoring_rules must contain scoring rules."
            )
        key = (value.secondary_mission_id, value.source_kind)
        if key in seen:
            raise GameLifecycleError(
                "MissionScoringPolicy secondary_scoring_rules must not contain duplicates."
            )
        seen.add(key)
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda rule: (rule.secondary_mission_id, rule.source_kind.value),
        )
    )


def _validate_mission_action_scoring_rule_tuple(
    values: object,
) -> tuple[MissionActionScoringRule, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "MissionScoringPolicy mission_action_scoring_rules must be a tuple."
        )
    validated: list[MissionActionScoringRule] = []
    seen_action_ids: set[str] = set()
    seen_scoring_source_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MissionActionScoringRule:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must contain scoring rules."
            )
        if value.mission_action_id in seen_action_ids:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must not duplicate action IDs."
            )
        if value.scoring_source_id in seen_scoring_source_ids:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must not duplicate scoring "
                "source IDs."
            )
        seen_action_ids.add(value.mission_action_id)
        seen_scoring_source_ids.add(value.scoring_source_id)
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda rule: rule.mission_action_id,
        )
    )


def _validate_scoring_window_tuple(
    values: object,
    *,
    game_id: str,
) -> tuple[ScoringWindowState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FinalScoringResult scoring_windows must be a tuple.")
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[ScoringWindowState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ScoringWindowState:
            raise GameLifecycleError("FinalScoringResult scoring_windows must contain states.")
        if value.game_id != requested_game_id:
            raise GameLifecycleError("ScoringWindowState game_id drift.")
        if value.window_id in seen:
            raise GameLifecycleError("FinalScoringResult scoring_windows must not duplicate IDs.")
        seen.add(value.window_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda window: window.window_id))


def _validate_final_score_tuple(values: object) -> tuple[FinalScoreLine, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FinalScoringResult final_scores must be a tuple.")
    validated: list[FinalScoreLine] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not FinalScoreLine:
            raise GameLifecycleError("FinalScoringResult final_scores must contain score lines.")
        if value.player_id in seen:
            raise GameLifecycleError("FinalScoringResult final_scores must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    if not validated:
        raise GameLifecycleError("FinalScoringResult final_scores must not be empty.")
    return tuple(sorted(validated, key=lambda score: score.player_id))


def _winner_player_ids_from_scores(scores: tuple[FinalScoreLine, ...]) -> tuple[str, ...]:
    final_scores = _validate_final_score_tuple(scores)
    max_score = max(score.victory_points for score in final_scores)
    return tuple(score.player_id for score in final_scores if score.victory_points == max_score)


def _validate_required_final_scoring_windows(
    *,
    scoring_windows: tuple[ScoringWindowState, ...],
    policy: MissionScoringPolicy,
    game_id: str,
    battle_round: int,
) -> tuple[ScoringWindowState, ...]:
    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("Final scoring window validation requires MissionScoringPolicy.")
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    validated_windows = _validate_scoring_window_tuple(
        scoring_windows,
        game_id=requested_game_id,
    )
    recorded = {
        (window.window_kind, window.window, window.battle_round) for window in validated_windows
    }
    required = {
        (ScoringWindowKind.END_OF_ROUND, window, requested_round)
        for window in policy.end_of_round_scoring_windows
    } | {
        (ScoringWindowKind.END_OF_GAME, window, requested_round)
        for window in policy.end_of_game_scoring_windows
    }
    missing = tuple(sorted(required - recorded, key=lambda item: (item[0].value, item[1], item[2])))
    if missing:
        missing_text = ", ".join(
            f"{kind.value}:{window}:round-{round_number:02d}"
            for kind, window, round_number in missing
        )
        raise GameLifecycleError(f"Final scoring requires recorded policy windows: {missing_text}.")
    return validated_windows


def _metadata_with_vp_cap_audit(
    metadata: JsonValue,
    *,
    requested_amount: int,
    applied_amount: int,
    source_cap: int,
    source_points_before: int,
    source_points_after: int,
    total_cap: int,
    total_points_before: int,
    total_points_after: int,
    capped_reasons: tuple[str, ...],
) -> JsonValue:
    audit = {
        "requested_amount": _validate_positive_int("requested_amount", requested_amount),
        "applied_amount": _validate_non_negative_int("applied_amount", applied_amount),
        "source_cap": _validate_non_negative_int("source_cap", source_cap),
        "source_points_before": _validate_non_negative_int(
            "source_points_before", source_points_before
        ),
        "source_points_after": _validate_non_negative_int(
            "source_points_after", source_points_after
        ),
        "total_cap": _validate_positive_int("total_cap", total_cap),
        "total_points_before": _validate_non_negative_int(
            "total_points_before", total_points_before
        ),
        "total_points_after": _validate_non_negative_int("total_points_after", total_points_after),
        "capped_reasons": list(
            _validate_identifier_tuple_ordered(
                "capped_reasons",
                capped_reasons,
                min_length=1,
            )
        ),
    }
    validated_metadata = validate_json_value(metadata)
    if validated_metadata is None:
        return {"vp_cap_audit": validate_json_value(audit)}
    if isinstance(validated_metadata, dict):
        if "vp_cap_audit" in validated_metadata:
            raise GameLifecycleError("Victory point metadata already contains vp_cap_audit.")
        updated = dict(validated_metadata)
        updated["vp_cap_audit"] = validate_json_value(audit)
        return updated
    return {
        "original_metadata": validated_metadata,
        "vp_cap_audit": validate_json_value(audit),
    }


def _validate_identifier_tuple_ordered(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(identifiers)


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


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
