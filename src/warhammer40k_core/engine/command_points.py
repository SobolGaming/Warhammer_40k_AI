from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.phase import GameLifecycleError


class CommandPhaseStep(StrEnum):
    COMMAND = "command"
    BATTLE_SHOCK = "battle_shock"


class CommandPointSourceKind(StrEnum):
    COMMAND_PHASE_START = "command_phase_start"
    OTHER = "other"
    STRATAGEM_SPEND = "stratagem_spend"
    STRATAGEM_REFUND = "stratagem_refund"


class CommandPointGainStatus(StrEnum):
    APPLIED = "applied"
    CAPPED = "capped"


class CommandPointSpendStatus(StrEnum):
    APPLIED = "applied"
    INSUFFICIENT = "insufficient"


class CommandPointRefundStatus(StrEnum):
    APPLIED = "applied"
    CAPPED = "capped"


class CommandStepStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    current_step: str
    command_points_granted: bool
    scoring_hooks_resolved: bool
    tactical_secondary_resolved: bool
    tactical_secondary_replacement_resolved: bool
    battle_shock_step_resolved: bool


class CommandPointTransactionPayload(TypedDict):
    transaction_id: str
    player_id: str
    battle_round: int
    amount: int
    source_id: str
    source_kind: str
    cap_exempt: bool


class CommandPointLedgerPayload(TypedDict):
    player_id: str
    command_points: int
    transactions: list[CommandPointTransactionPayload]


class CommandPointGainResultPayload(TypedDict):
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: str
    source_id: str
    source_kind: str
    transaction: CommandPointTransactionPayload | None
    capped_reason: str | None


class CommandPointSpendResultPayload(TypedDict):
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: str
    source_id: str
    source_kind: str
    transaction: CommandPointTransactionPayload | None
    insufficient_reason: str | None


class CommandPointRefundResultPayload(TypedDict):
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: str
    source_id: str
    source_kind: str
    transaction: CommandPointTransactionPayload | None
    capped_reason: str | None


@dataclass(frozen=True, slots=True)
class CommandStepState:
    battle_round: int
    active_player_id: str
    current_step: CommandPhaseStep = CommandPhaseStep.COMMAND
    command_points_granted: bool = False
    scoring_hooks_resolved: bool = False
    tactical_secondary_resolved: bool = False
    tactical_secondary_replacement_resolved: bool = False
    battle_shock_step_resolved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CommandStepState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("CommandStepState active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "current_step", command_phase_step_from_token(self.current_step))
        object.__setattr__(
            self,
            "command_points_granted",
            _validate_bool("CommandStepState command_points_granted", self.command_points_granted),
        )
        object.__setattr__(
            self,
            "scoring_hooks_resolved",
            _validate_bool("CommandStepState scoring_hooks_resolved", self.scoring_hooks_resolved),
        )
        object.__setattr__(
            self,
            "tactical_secondary_resolved",
            _validate_bool(
                "CommandStepState tactical_secondary_resolved",
                self.tactical_secondary_resolved,
            ),
        )
        object.__setattr__(
            self,
            "battle_shock_step_resolved",
            _validate_bool(
                "CommandStepState battle_shock_step_resolved",
                self.battle_shock_step_resolved,
            ),
        )
        object.__setattr__(
            self,
            "tactical_secondary_replacement_resolved",
            _validate_bool(
                "CommandStepState tactical_secondary_replacement_resolved",
                self.tactical_secondary_replacement_resolved,
            ),
        )
        if self.current_step is CommandPhaseStep.BATTLE_SHOCK and not self.command_points_granted:
            raise GameLifecycleError(
                "CommandStepState cannot enter Battle-shock before Command step CP gain."
            )
        if (
            self.battle_shock_step_resolved
            and self.current_step is not CommandPhaseStep.BATTLE_SHOCK
        ):
            raise GameLifecycleError(
                "CommandStepState resolved Battle-shock state must be in Battle-shock step."
            )

    @classmethod
    def start(cls, *, battle_round: int, active_player_id: str) -> Self:
        return cls(battle_round=battle_round, active_player_id=active_player_id)

    def with_command_points_granted(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=CommandPhaseStep.COMMAND,
            command_points_granted=True,
            scoring_hooks_resolved=self.scoring_hooks_resolved,
            tactical_secondary_resolved=self.tactical_secondary_resolved,
            tactical_secondary_replacement_resolved=self.tactical_secondary_replacement_resolved,
            battle_shock_step_resolved=self.battle_shock_step_resolved,
        )

    def with_scoring_hooks_resolved(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=CommandPhaseStep.COMMAND,
            command_points_granted=self.command_points_granted,
            scoring_hooks_resolved=True,
            tactical_secondary_resolved=self.tactical_secondary_resolved,
            tactical_secondary_replacement_resolved=self.tactical_secondary_replacement_resolved,
            battle_shock_step_resolved=self.battle_shock_step_resolved,
        )

    def with_tactical_secondary_resolved(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=CommandPhaseStep.COMMAND,
            command_points_granted=self.command_points_granted,
            scoring_hooks_resolved=self.scoring_hooks_resolved,
            tactical_secondary_resolved=True,
            tactical_secondary_replacement_resolved=self.tactical_secondary_replacement_resolved,
            battle_shock_step_resolved=self.battle_shock_step_resolved,
        )

    def with_tactical_secondary_replacement_resolved(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=self.current_step,
            command_points_granted=self.command_points_granted,
            scoring_hooks_resolved=self.scoring_hooks_resolved,
            tactical_secondary_resolved=self.tactical_secondary_resolved,
            tactical_secondary_replacement_resolved=True,
            battle_shock_step_resolved=self.battle_shock_step_resolved,
        )

    def enter_battle_shock_step(self) -> Self:
        if not self.command_points_granted:
            raise GameLifecycleError("Battle-shock step requires Command step CP gain.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=CommandPhaseStep.BATTLE_SHOCK,
            command_points_granted=self.command_points_granted,
            scoring_hooks_resolved=self.scoring_hooks_resolved,
            tactical_secondary_resolved=self.tactical_secondary_resolved,
            tactical_secondary_replacement_resolved=self.tactical_secondary_replacement_resolved,
            battle_shock_step_resolved=self.battle_shock_step_resolved,
        )

    def with_battle_shock_step_resolved(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=CommandPhaseStep.BATTLE_SHOCK,
            command_points_granted=self.command_points_granted,
            scoring_hooks_resolved=self.scoring_hooks_resolved,
            tactical_secondary_resolved=self.tactical_secondary_resolved,
            tactical_secondary_replacement_resolved=self.tactical_secondary_replacement_resolved,
            battle_shock_step_resolved=True,
        )

    def to_payload(self) -> CommandStepStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "current_step": self.current_step.value,
            "command_points_granted": self.command_points_granted,
            "scoring_hooks_resolved": self.scoring_hooks_resolved,
            "tactical_secondary_resolved": self.tactical_secondary_resolved,
            "tactical_secondary_replacement_resolved": (
                self.tactical_secondary_replacement_resolved
            ),
            "battle_shock_step_resolved": self.battle_shock_step_resolved,
        }

    @classmethod
    def from_payload(cls, payload: CommandStepStatePayload) -> Self:
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            current_step=command_phase_step_from_token(payload["current_step"]),
            command_points_granted=payload["command_points_granted"],
            scoring_hooks_resolved=payload["scoring_hooks_resolved"],
            tactical_secondary_resolved=payload["tactical_secondary_resolved"],
            tactical_secondary_replacement_resolved=payload[
                "tactical_secondary_replacement_resolved"
            ],
            battle_shock_step_resolved=payload["battle_shock_step_resolved"],
        )


@dataclass(frozen=True, slots=True)
class CommandPointTransaction:
    transaction_id: str
    player_id: str
    battle_round: int
    amount: int
    source_id: str
    source_kind: CommandPointSourceKind
    cap_exempt: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _validate_identifier("CommandPointTransaction transaction_id", self.transaction_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CommandPointTransaction player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CommandPointTransaction battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_non_zero_int("CommandPointTransaction amount", self.amount),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("CommandPointTransaction source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            command_point_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "cap_exempt",
            _validate_bool("CommandPointTransaction cap_exempt", self.cap_exempt),
        )

    def to_payload(self) -> CommandPointTransactionPayload:
        return {
            "transaction_id": self.transaction_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "amount": self.amount,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "cap_exempt": self.cap_exempt,
        }

    @classmethod
    def from_payload(cls, payload: CommandPointTransactionPayload) -> Self:
        return cls(
            transaction_id=payload["transaction_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            amount=payload["amount"],
            source_id=payload["source_id"],
            source_kind=command_point_source_kind_from_token(payload["source_kind"]),
            cap_exempt=payload["cap_exempt"],
        )


@dataclass(frozen=True, slots=True)
class CommandPointGainResult:
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: CommandPointGainStatus
    source_id: str
    source_kind: CommandPointSourceKind
    transaction: CommandPointTransaction | None = None
    capped_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CommandPointGainResult player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CommandPointGainResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "requested_amount",
            _validate_positive_int(
                "CommandPointGainResult requested_amount",
                self.requested_amount,
            ),
        )
        object.__setattr__(
            self,
            "applied_amount",
            _validate_non_negative_int(
                "CommandPointGainResult applied_amount",
                self.applied_amount,
            ),
        )
        object.__setattr__(self, "status", command_point_gain_status_from_token(self.status))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("CommandPointGainResult source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            command_point_source_kind_from_token(self.source_kind),
        )
        if self.transaction is not None and type(self.transaction) is not CommandPointTransaction:
            raise GameLifecycleError(
                "CommandPointGainResult transaction must be a CommandPointTransaction."
            )
        object.__setattr__(
            self,
            "capped_reason",
            _validate_optional_identifier(
                "CommandPointGainResult capped_reason",
                self.capped_reason,
            ),
        )
        if self.status is CommandPointGainStatus.APPLIED:
            if self.transaction is None:
                raise GameLifecycleError("Applied CommandPointGainResult requires a transaction.")
            if self.applied_amount != self.requested_amount:
                raise GameLifecycleError("Applied CommandPointGainResult amount drift.")
            if self.capped_reason is not None:
                raise GameLifecycleError(
                    "Applied CommandPointGainResult cannot have capped_reason."
                )
        if self.status is CommandPointGainStatus.CAPPED:
            if self.transaction is not None:
                raise GameLifecycleError("Capped CommandPointGainResult cannot have a transaction.")
            if self.applied_amount != 0:
                raise GameLifecycleError("Capped CommandPointGainResult applies no CP.")
            if self.capped_reason is None:
                raise GameLifecycleError("Capped CommandPointGainResult requires capped_reason.")

    def to_payload(self) -> CommandPointGainResultPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "requested_amount": self.requested_amount,
            "applied_amount": self.applied_amount,
            "status": self.status.value,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "transaction": None if self.transaction is None else self.transaction.to_payload(),
            "capped_reason": self.capped_reason,
        }

    @classmethod
    def from_payload(cls, payload: CommandPointGainResultPayload) -> Self:
        transaction_payload = payload["transaction"]
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            requested_amount=payload["requested_amount"],
            applied_amount=payload["applied_amount"],
            status=command_point_gain_status_from_token(payload["status"]),
            source_id=payload["source_id"],
            source_kind=command_point_source_kind_from_token(payload["source_kind"]),
            transaction=(
                None
                if transaction_payload is None
                else CommandPointTransaction.from_payload(transaction_payload)
            ),
            capped_reason=payload["capped_reason"],
        )


@dataclass(frozen=True, slots=True)
class CommandPointSpendResult:
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: CommandPointSpendStatus
    source_id: str
    source_kind: CommandPointSourceKind
    transaction: CommandPointTransaction | None = None
    insufficient_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CommandPointSpendResult player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CommandPointSpendResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "requested_amount",
            _validate_positive_int(
                "CommandPointSpendResult requested_amount",
                self.requested_amount,
            ),
        )
        object.__setattr__(
            self,
            "applied_amount",
            _validate_non_negative_int(
                "CommandPointSpendResult applied_amount",
                self.applied_amount,
            ),
        )
        object.__setattr__(self, "status", command_point_spend_status_from_token(self.status))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("CommandPointSpendResult source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            command_point_source_kind_from_token(self.source_kind),
        )
        if self.source_kind is not CommandPointSourceKind.STRATAGEM_SPEND:
            raise GameLifecycleError("CommandPointSpendResult source_kind must be stratagem_spend.")
        if self.transaction is not None and type(self.transaction) is not CommandPointTransaction:
            raise GameLifecycleError(
                "CommandPointSpendResult transaction must be a CommandPointTransaction."
            )
        object.__setattr__(
            self,
            "insufficient_reason",
            _validate_optional_identifier(
                "CommandPointSpendResult insufficient_reason",
                self.insufficient_reason,
            ),
        )
        if self.status is CommandPointSpendStatus.APPLIED:
            if self.transaction is None:
                raise GameLifecycleError("Applied CommandPointSpendResult requires a transaction.")
            if self.transaction.amount != -self.requested_amount:
                raise GameLifecycleError(
                    "Applied CommandPointSpendResult transaction amount drift."
                )
            if self.applied_amount != self.requested_amount:
                raise GameLifecycleError("Applied CommandPointSpendResult amount drift.")
            if self.insufficient_reason is not None:
                raise GameLifecycleError(
                    "Applied CommandPointSpendResult cannot have insufficient_reason."
                )
        if self.status is CommandPointSpendStatus.INSUFFICIENT:
            if self.transaction is not None:
                raise GameLifecycleError(
                    "Insufficient CommandPointSpendResult cannot have a transaction."
                )
            if self.applied_amount != 0:
                raise GameLifecycleError("Insufficient CommandPointSpendResult applies no CP.")
            if self.insufficient_reason is None:
                raise GameLifecycleError(
                    "Insufficient CommandPointSpendResult requires insufficient_reason."
                )

    def to_payload(self) -> CommandPointSpendResultPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "requested_amount": self.requested_amount,
            "applied_amount": self.applied_amount,
            "status": self.status.value,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "transaction": None if self.transaction is None else self.transaction.to_payload(),
            "insufficient_reason": self.insufficient_reason,
        }

    @classmethod
    def from_payload(cls, payload: CommandPointSpendResultPayload) -> Self:
        transaction_payload = payload["transaction"]
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            requested_amount=payload["requested_amount"],
            applied_amount=payload["applied_amount"],
            status=command_point_spend_status_from_token(payload["status"]),
            source_id=payload["source_id"],
            source_kind=command_point_source_kind_from_token(payload["source_kind"]),
            transaction=(
                None
                if transaction_payload is None
                else CommandPointTransaction.from_payload(transaction_payload)
            ),
            insufficient_reason=payload["insufficient_reason"],
        )


@dataclass(frozen=True, slots=True)
class CommandPointRefundResult:
    player_id: str
    battle_round: int
    requested_amount: int
    applied_amount: int
    status: CommandPointRefundStatus
    source_id: str
    source_kind: CommandPointSourceKind
    transaction: CommandPointTransaction | None = None
    capped_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CommandPointRefundResult player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CommandPointRefundResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "requested_amount",
            _validate_positive_int(
                "CommandPointRefundResult requested_amount",
                self.requested_amount,
            ),
        )
        object.__setattr__(
            self,
            "applied_amount",
            _validate_non_negative_int(
                "CommandPointRefundResult applied_amount",
                self.applied_amount,
            ),
        )
        object.__setattr__(self, "status", command_point_refund_status_from_token(self.status))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("CommandPointRefundResult source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            command_point_source_kind_from_token(self.source_kind),
        )
        if self.source_kind is not CommandPointSourceKind.STRATAGEM_REFUND:
            raise GameLifecycleError(
                "CommandPointRefundResult source_kind must be stratagem_refund."
            )
        if self.transaction is not None and type(self.transaction) is not CommandPointTransaction:
            raise GameLifecycleError(
                "CommandPointRefundResult transaction must be a CommandPointTransaction."
            )
        object.__setattr__(
            self,
            "capped_reason",
            _validate_optional_identifier(
                "CommandPointRefundResult capped_reason",
                self.capped_reason,
            ),
        )
        if self.status is CommandPointRefundStatus.APPLIED:
            if self.transaction is None:
                raise GameLifecycleError("Applied CommandPointRefundResult requires a transaction.")
            if self.transaction.amount != self.requested_amount:
                raise GameLifecycleError(
                    "Applied CommandPointRefundResult transaction amount drift."
                )
            if self.applied_amount != self.requested_amount:
                raise GameLifecycleError("Applied CommandPointRefundResult amount drift.")
            if self.capped_reason is not None:
                raise GameLifecycleError(
                    "Applied CommandPointRefundResult cannot have capped_reason."
                )
        if self.status is CommandPointRefundStatus.CAPPED:
            if self.transaction is not None:
                raise GameLifecycleError(
                    "Capped CommandPointRefundResult cannot have a transaction."
                )
            if self.applied_amount != 0:
                raise GameLifecycleError("Capped CommandPointRefundResult applies no CP.")
            if self.capped_reason is None:
                raise GameLifecycleError("Capped CommandPointRefundResult requires capped_reason.")

    def to_payload(self) -> CommandPointRefundResultPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "requested_amount": self.requested_amount,
            "applied_amount": self.applied_amount,
            "status": self.status.value,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "transaction": None if self.transaction is None else self.transaction.to_payload(),
            "capped_reason": self.capped_reason,
        }

    @classmethod
    def from_payload(cls, payload: CommandPointRefundResultPayload) -> Self:
        transaction_payload = payload["transaction"]
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            requested_amount=payload["requested_amount"],
            applied_amount=payload["applied_amount"],
            status=command_point_refund_status_from_token(payload["status"]),
            source_id=payload["source_id"],
            source_kind=command_point_source_kind_from_token(payload["source_kind"]),
            transaction=(
                None
                if transaction_payload is None
                else CommandPointTransaction.from_payload(transaction_payload)
            ),
            capped_reason=payload["capped_reason"],
        )


@dataclass(frozen=True, slots=True)
class CommandPointLedger:
    player_id: str
    command_points: int = 0
    transactions: tuple[CommandPointTransaction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CommandPointLedger player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "command_points",
            _validate_non_negative_int("CommandPointLedger command_points", self.command_points),
        )
        transactions = _validate_transaction_tuple(
            "CommandPointLedger transactions",
            self.transactions,
            player_id=self.player_id,
        )
        object.__setattr__(self, "transactions", transactions)
        total = sum(transaction.amount for transaction in transactions)
        if total != self.command_points:
            raise GameLifecycleError("CommandPointLedger command_points must match transactions.")

    @classmethod
    def initial(cls, *, player_id: str) -> Self:
        return cls(player_id=player_id)

    def gain(
        self,
        *,
        battle_round: int,
        amount: int,
        source_id: str,
        source_kind: CommandPointSourceKind,
        cap_exempt: bool = False,
    ) -> tuple[Self, CommandPointGainResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source = _validate_identifier("source_id", source_id)
        requested_kind = command_point_source_kind_from_token(source_kind)
        requested_cap_exempt = _validate_bool("cap_exempt", cap_exempt)
        if requested_kind in (
            CommandPointSourceKind.STRATAGEM_SPEND,
            CommandPointSourceKind.STRATAGEM_REFUND,
        ):
            raise GameLifecycleError(
                "CommandPointLedger.gain cannot use stratagem spend/refund source kinds."
            )

        if (
            _source_kind_counts_toward_non_command_gain_cap(requested_kind)
            and not requested_cap_exempt
            and self.non_command_points_gained_in_round(requested_round) + requested_amount > 1
        ):
            result = CommandPointGainResult(
                player_id=self.player_id,
                battle_round=requested_round,
                requested_amount=requested_amount,
                applied_amount=0,
                status=CommandPointGainStatus.CAPPED,
                source_id=requested_source,
                source_kind=requested_kind,
                capped_reason="non_command_cp_gain_cap_reached",
            )
            return self, result

        transaction = CommandPointTransaction(
            transaction_id=(
                f"command-point:{self.player_id}:round-{requested_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=requested_round,
            amount=requested_amount,
            source_id=requested_source,
            source_kind=requested_kind,
            cap_exempt=requested_cap_exempt,
        )
        updated = type(self)(
            player_id=self.player_id,
            command_points=self.command_points + requested_amount,
            transactions=(*self.transactions, transaction),
        )
        result = CommandPointGainResult(
            player_id=self.player_id,
            battle_round=requested_round,
            requested_amount=requested_amount,
            applied_amount=requested_amount,
            status=CommandPointGainStatus.APPLIED,
            source_id=requested_source,
            source_kind=requested_kind,
            transaction=transaction,
        )
        return updated, result

    def spend(
        self,
        *,
        battle_round: int,
        amount: int,
        source_id: str,
    ) -> tuple[Self, CommandPointSpendResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source = _validate_identifier("source_id", source_id)
        if self.command_points < requested_amount:
            result = CommandPointSpendResult(
                player_id=self.player_id,
                battle_round=requested_round,
                requested_amount=requested_amount,
                applied_amount=0,
                status=CommandPointSpendStatus.INSUFFICIENT,
                source_id=requested_source,
                source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
                insufficient_reason="insufficient_command_points",
            )
            return self, result

        transaction = CommandPointTransaction(
            transaction_id=(
                f"command-point:{self.player_id}:round-{requested_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=requested_round,
            amount=-requested_amount,
            source_id=requested_source,
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
        )
        updated = type(self)(
            player_id=self.player_id,
            command_points=self.command_points - requested_amount,
            transactions=(*self.transactions, transaction),
        )
        result = CommandPointSpendResult(
            player_id=self.player_id,
            battle_round=requested_round,
            requested_amount=requested_amount,
            applied_amount=requested_amount,
            status=CommandPointSpendStatus.APPLIED,
            source_id=requested_source,
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
            transaction=transaction,
        )
        return updated, result

    def refund(
        self,
        *,
        battle_round: int,
        amount: int,
        source_id: str,
        cap_exempt: bool = False,
    ) -> tuple[Self, CommandPointRefundResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source = _validate_identifier("source_id", source_id)
        requested_cap_exempt = _validate_bool("cap_exempt", cap_exempt)
        if (
            not requested_cap_exempt
            and self.non_command_points_gained_in_round(requested_round) + requested_amount > 1
        ):
            result = CommandPointRefundResult(
                player_id=self.player_id,
                battle_round=requested_round,
                requested_amount=requested_amount,
                applied_amount=0,
                status=CommandPointRefundStatus.CAPPED,
                source_id=requested_source,
                source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
                capped_reason="non_command_cp_gain_cap_reached",
            )
            return self, result

        transaction = CommandPointTransaction(
            transaction_id=(
                f"command-point:{self.player_id}:round-{requested_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=requested_round,
            amount=requested_amount,
            source_id=requested_source,
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            cap_exempt=requested_cap_exempt,
        )
        updated = type(self)(
            player_id=self.player_id,
            command_points=self.command_points + requested_amount,
            transactions=(*self.transactions, transaction),
        )
        result = CommandPointRefundResult(
            player_id=self.player_id,
            battle_round=requested_round,
            requested_amount=requested_amount,
            applied_amount=requested_amount,
            status=CommandPointRefundStatus.APPLIED,
            source_id=requested_source,
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            transaction=transaction,
        )
        return updated, result

    def non_command_points_gained_in_round(self, battle_round: int) -> int:
        requested_round = _validate_positive_int("battle_round", battle_round)
        return sum(
            transaction.amount
            for transaction in self.transactions
            if transaction.battle_round == requested_round
            and transaction.amount > 0
            and _source_kind_counts_toward_non_command_gain_cap(transaction.source_kind)
            and not transaction.cap_exempt
        )

    def to_payload(self) -> CommandPointLedgerPayload:
        return {
            "player_id": self.player_id,
            "command_points": self.command_points,
            "transactions": [transaction.to_payload() for transaction in self.transactions],
        }

    @classmethod
    def from_payload(cls, payload: CommandPointLedgerPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            command_points=payload["command_points"],
            transactions=tuple(
                CommandPointTransaction.from_payload(transaction)
                for transaction in payload["transactions"]
            ),
        )


def command_phase_step_from_token(token: object) -> CommandPhaseStep:
    if type(token) is CommandPhaseStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("CommandPhaseStep token must be a string.")
    try:
        return CommandPhaseStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported CommandPhaseStep token: {token}.") from exc


def command_point_source_kind_from_token(token: object) -> CommandPointSourceKind:
    if type(token) is CommandPointSourceKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("CommandPointSourceKind token must be a string.")
    try:
        return CommandPointSourceKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported CommandPointSourceKind token: {token}.") from exc


def command_point_gain_status_from_token(token: object) -> CommandPointGainStatus:
    if type(token) is CommandPointGainStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("CommandPointGainStatus token must be a string.")
    try:
        return CommandPointGainStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported CommandPointGainStatus token: {token}.") from exc


def command_point_spend_status_from_token(token: object) -> CommandPointSpendStatus:
    if type(token) is CommandPointSpendStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("CommandPointSpendStatus token must be a string.")
    try:
        return CommandPointSpendStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported CommandPointSpendStatus token: {token}.") from exc


def command_point_refund_status_from_token(token: object) -> CommandPointRefundStatus:
    if type(token) is CommandPointRefundStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("CommandPointRefundStatus token must be a string.")
    try:
        return CommandPointRefundStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported CommandPointRefundStatus token: {token}.") from exc


def initial_command_point_ledgers(player_ids: tuple[str, ...]) -> list[CommandPointLedger]:
    return [CommandPointLedger.initial(player_id=player_id) for player_id in player_ids]


def _validate_transaction_tuple(
    field_name: str,
    values: object,
    *,
    player_id: str,
) -> tuple[CommandPointTransaction, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[CommandPointTransaction] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not CommandPointTransaction:
            raise GameLifecycleError(f"{field_name} must contain CommandPointTransaction values.")
        if value.player_id != player_id:
            raise GameLifecycleError(f"{field_name} player_id drift.")
        if value.transaction_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate transactions.")
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


def _validate_non_zero_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value == 0:
        raise GameLifecycleError(f"{field_name} must not be zero.")
    return value


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


def _source_kind_counts_toward_non_command_gain_cap(source_kind: CommandPointSourceKind) -> bool:
    return source_kind is not CommandPointSourceKind.COMMAND_PHASE_START
