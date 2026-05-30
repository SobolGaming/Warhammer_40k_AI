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
    primary_vp_per_controlled_objective: int
    primary_max_vp_per_turn: int
    secondary_vp_per_score: int
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
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
            _validate_positive_int("VictoryPointTransaction amount", self.amount),
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

    def award(self, award: VictoryPointAward) -> tuple[Self, VictoryPointTransaction]:
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VictoryPointLedger award must be a VictoryPointAward.")
        if award.player_id != self.player_id:
            raise GameLifecycleError("VictoryPointLedger award player_id drift.")
        transaction = VictoryPointTransaction(
            transaction_id=(
                f"victory-point:{self.player_id}:round-{award.battle_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=award.battle_round,
            phase=award.phase,
            amount=award.amount,
            source_kind=award.source_kind,
            source_id=award.source_id,
            scoring_timing=award.scoring_timing,
            hidden=award.hidden,
            metadata=award.metadata,
        )
        return (
            type(self)(
                player_id=self.player_id,
                victory_points=self.victory_points + award.amount,
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
class MissionScoringPolicy:
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: ObjectiveControlTiming
    primary_vp_per_controlled_objective: int
    primary_max_vp_per_turn: int
    secondary_vp_per_score: int
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
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
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=self.secondary_vp_per_score,
            source_kind=kind,
            source_id=_validate_identifier("secondary_mission_id", secondary_mission_id),
            scoring_timing="secondary_mission_score",
            hidden=hidden,
            metadata={"secondary_mission_id": secondary_mission_id},
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
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=self.mission_action_vp
            if amount is None
            else _validate_positive_int("amount", amount),
            source_kind=VictoryPointSourceKind.MISSION_ACTION,
            source_id=_validate_identifier("source_id", source_id),
            scoring_timing="mission_action_complete",
            hidden=False,
            metadata={"action_id": _validate_identifier("action_id", action_id)},
        )

    def to_payload(self) -> MissionScoringPolicyPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "primary_scoring_phase": self.primary_scoring_phase,
            "primary_scoring_timing": self.primary_scoring_timing.value,
            "primary_vp_per_controlled_objective": self.primary_vp_per_controlled_objective,
            "primary_max_vp_per_turn": self.primary_max_vp_per_turn,
            "secondary_vp_per_score": self.secondary_vp_per_score,
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
            primary_vp_per_controlled_objective=payload["primary_vp_per_controlled_objective"],
            primary_max_vp_per_turn=payload["primary_max_vp_per_turn"],
            secondary_vp_per_score=payload["secondary_vp_per_score"],
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
            source_id=payload["source_id"],
        )


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
