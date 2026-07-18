from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError


class UnitStartingResourceAllocationPayload(TypedDict):
    resource_kind: str
    amount: int


class UnitResourceTransactionPayload(TypedDict):
    transaction_id: str
    player_id: str
    unit_instance_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: str
    amount: int
    source_rule_id: str
    decision_request_id: str | None
    decision_result_id: str | None


class UnitResourceLedgerPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    starting_resources: dict[str, int]
    resources: dict[str, int]
    transactions: list[UnitResourceTransactionPayload]


class UnitResourceResultPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: str
    requested_amount: int
    applied_amount: int
    status: str
    source_rule_id: str
    decision_request_id: str | None
    decision_result_id: str | None
    transaction: UnitResourceTransactionPayload | None
    insufficient_reason: str | None


class UnitResourceTransactionKind(StrEnum):
    INITIALIZE = "initialize"
    SPEND = "spend"


class UnitResourceStatus(StrEnum):
    APPLIED = "applied"
    INSUFFICIENT = "insufficient"


def _empty_resource_totals() -> dict[str, int]:
    return {}


@dataclass(frozen=True, slots=True)
class UnitStartingResourceAllocation:
    resource_kind: str
    amount: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier(
                "UnitStartingResourceAllocation resource_kind",
                self.resource_kind,
            ),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_positive_int("UnitStartingResourceAllocation amount", self.amount),
        )

    def to_payload(self) -> UnitStartingResourceAllocationPayload:
        return {"resource_kind": self.resource_kind, "amount": self.amount}

    @classmethod
    def from_payload(cls, payload: UnitStartingResourceAllocationPayload) -> Self:
        return cls(resource_kind=payload["resource_kind"], amount=payload["amount"])


@dataclass(frozen=True, slots=True)
class UnitResourceTransaction:
    transaction_id: str
    player_id: str
    unit_instance_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: UnitResourceTransactionKind
    amount: int
    source_rule_id: str
    decision_request_id: str | None = None
    decision_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _validate_identifier("UnitResourceTransaction transaction_id", self.transaction_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("UnitResourceTransaction player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "UnitResourceTransaction unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_non_negative_int(
                "UnitResourceTransaction battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier("UnitResourceTransaction resource_kind", self.resource_kind),
        )
        object.__setattr__(
            self,
            "transaction_kind",
            unit_resource_transaction_kind_from_token(self.transaction_kind),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_positive_int("UnitResourceTransaction amount", self.amount),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "UnitResourceTransaction source_rule_id",
                self.source_rule_id,
            ),
        )
        request_id = _validate_optional_identifier(
            "UnitResourceTransaction decision_request_id",
            self.decision_request_id,
        )
        result_id = _validate_optional_identifier(
            "UnitResourceTransaction decision_result_id",
            self.decision_result_id,
        )
        if self.transaction_kind is UnitResourceTransactionKind.INITIALIZE:
            if self.battle_round != 0:
                raise GameLifecycleError("Unit resource initialization must use battle round zero.")
            if request_id is not None or result_id is not None:
                raise GameLifecycleError(
                    "Unit resource initialization must not include decision provenance."
                )
        if self.transaction_kind is UnitResourceTransactionKind.SPEND:
            if self.battle_round < 1:
                raise GameLifecycleError("Unit resource spend requires a positive battle round.")
            if request_id is None or result_id is None:
                raise GameLifecycleError("Unit resource spend requires decision provenance.")
        object.__setattr__(self, "decision_request_id", request_id)
        object.__setattr__(self, "decision_result_id", result_id)

    def to_payload(self) -> UnitResourceTransactionPayload:
        return {
            "transaction_id": self.transaction_id,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "battle_round": self.battle_round,
            "resource_kind": self.resource_kind,
            "transaction_kind": self.transaction_kind.value,
            "amount": self.amount,
            "source_rule_id": self.source_rule_id,
            "decision_request_id": self.decision_request_id,
            "decision_result_id": self.decision_result_id,
        }

    @classmethod
    def from_payload(cls, payload: UnitResourceTransactionPayload) -> Self:
        return cls(
            transaction_id=payload["transaction_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            battle_round=payload["battle_round"],
            resource_kind=payload["resource_kind"],
            transaction_kind=unit_resource_transaction_kind_from_token(payload["transaction_kind"]),
            amount=payload["amount"],
            source_rule_id=payload["source_rule_id"],
            decision_request_id=payload["decision_request_id"],
            decision_result_id=payload["decision_result_id"],
        )


@dataclass(frozen=True, slots=True)
class UnitResourceResult:
    player_id: str
    unit_instance_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: UnitResourceTransactionKind
    requested_amount: int
    applied_amount: int
    status: UnitResourceStatus
    source_rule_id: str
    decision_request_id: str
    decision_result_id: str
    transaction: UnitResourceTransaction | None = None
    insufficient_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier("resource_kind", self.resource_kind),
        )
        transaction_kind = unit_resource_transaction_kind_from_token(self.transaction_kind)
        if transaction_kind is not UnitResourceTransactionKind.SPEND:
            raise GameLifecycleError("UnitResourceResult only represents spend attempts.")
        object.__setattr__(self, "transaction_kind", transaction_kind)
        object.__setattr__(
            self,
            "requested_amount",
            _validate_positive_int("requested_amount", self.requested_amount),
        )
        object.__setattr__(
            self,
            "applied_amount",
            _validate_non_negative_int("applied_amount", self.applied_amount),
        )
        object.__setattr__(self, "status", unit_resource_status_from_token(self.status))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "decision_request_id",
            _validate_identifier("decision_request_id", self.decision_request_id),
        )
        object.__setattr__(
            self,
            "decision_result_id",
            _validate_identifier("decision_result_id", self.decision_result_id),
        )
        if self.transaction is not None and type(self.transaction) is not UnitResourceTransaction:
            raise GameLifecycleError("UnitResourceResult transaction must be typed.")
        reason = _validate_optional_identifier("insufficient_reason", self.insufficient_reason)
        object.__setattr__(self, "insufficient_reason", reason)
        if self.status is UnitResourceStatus.APPLIED:
            if self.applied_amount != self.requested_amount or self.transaction is None:
                raise GameLifecycleError("Applied unit resource result drift.")
            if reason is not None:
                raise GameLifecycleError("Applied unit resource result has insufficient reason.")
        if self.status is UnitResourceStatus.INSUFFICIENT:
            if self.applied_amount != 0 or self.transaction is not None:
                raise GameLifecycleError("Insufficient unit resource result drift.")
            if reason is None:
                raise GameLifecycleError("Insufficient unit resource result requires a reason.")

    def to_payload(self) -> UnitResourceResultPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "battle_round": self.battle_round,
            "resource_kind": self.resource_kind,
            "transaction_kind": self.transaction_kind.value,
            "requested_amount": self.requested_amount,
            "applied_amount": self.applied_amount,
            "status": self.status.value,
            "source_rule_id": self.source_rule_id,
            "decision_request_id": self.decision_request_id,
            "decision_result_id": self.decision_result_id,
            "transaction": None if self.transaction is None else self.transaction.to_payload(),
            "insufficient_reason": self.insufficient_reason,
        }


@dataclass(frozen=True, slots=True)
class UnitResourceLedger:
    player_id: str
    unit_instance_id: str
    starting_resources: dict[str, int] = field(default_factory=_empty_resource_totals)
    resources: dict[str, int] = field(default_factory=_empty_resource_totals)
    transactions: tuple[UnitResourceTransaction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("UnitResourceLedger player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("UnitResourceLedger unit_instance_id", self.unit_instance_id),
        )
        starting = _validate_resource_totals(
            "UnitResourceLedger starting_resources",
            self.starting_resources,
        )
        current = _validate_resource_totals("UnitResourceLedger resources", self.resources)
        transactions = _validate_transactions(
            self.transactions,
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
        )
        expected_starting, expected_current = _totals_from_transactions(transactions)
        if starting != expected_starting or current != expected_current:
            raise GameLifecycleError("UnitResourceLedger totals drifted from transactions.")
        object.__setattr__(self, "starting_resources", starting)
        object.__setattr__(self, "resources", current)
        object.__setattr__(self, "transactions", transactions)

    @classmethod
    def empty_for_unit(cls, *, player_id: str, unit_instance_id: str) -> Self:
        return cls(player_id=player_id, unit_instance_id=unit_instance_id)

    def starting_total(self, resource_kind: str) -> int:
        return self.starting_resources.get(_validate_identifier("resource_kind", resource_kind), 0)

    def total(self, resource_kind: str) -> int:
        return self.resources.get(_validate_identifier("resource_kind", resource_kind), 0)

    def initialize(
        self,
        *,
        resource_kind: str,
        amount: int,
        source_rule_id: str,
    ) -> Self:
        requested_kind = _validate_identifier("resource_kind", resource_kind)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source = _validate_identifier("source_rule_id", source_rule_id)
        if requested_kind in self.starting_resources:
            raise GameLifecycleError("Unit resource kind is already initialized for this unit.")
        transaction = self._transaction(
            battle_round=0,
            resource_kind=requested_kind,
            transaction_kind=UnitResourceTransactionKind.INITIALIZE,
            amount=requested_amount,
            source_rule_id=requested_source,
        )
        starting = {**self.starting_resources, requested_kind: requested_amount}
        current = {**self.resources, requested_kind: requested_amount}
        return replace(
            self,
            starting_resources=starting,
            resources=current,
            transactions=(*self.transactions, transaction),
        )

    def spend(
        self,
        *,
        battle_round: int,
        resource_kind: str,
        amount: int,
        source_rule_id: str,
        decision_request_id: str,
        decision_result_id: str,
    ) -> tuple[Self, UnitResourceResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_kind = _validate_identifier("resource_kind", resource_kind)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source = _validate_identifier("source_rule_id", source_rule_id)
        request_id = _validate_identifier("decision_request_id", decision_request_id)
        result_id = _validate_identifier("decision_result_id", decision_result_id)
        current_total = self.total(requested_kind)
        if current_total < requested_amount:
            return (
                self,
                UnitResourceResult(
                    player_id=self.player_id,
                    unit_instance_id=self.unit_instance_id,
                    battle_round=requested_round,
                    resource_kind=requested_kind,
                    transaction_kind=UnitResourceTransactionKind.SPEND,
                    requested_amount=requested_amount,
                    applied_amount=0,
                    status=UnitResourceStatus.INSUFFICIENT,
                    source_rule_id=requested_source,
                    decision_request_id=request_id,
                    decision_result_id=result_id,
                    insufficient_reason="insufficient_resource",
                ),
            )
        transaction = self._transaction(
            battle_round=requested_round,
            resource_kind=requested_kind,
            transaction_kind=UnitResourceTransactionKind.SPEND,
            amount=requested_amount,
            source_rule_id=requested_source,
            decision_request_id=request_id,
            decision_result_id=result_id,
        )
        current = {**self.resources, requested_kind: current_total - requested_amount}
        updated = replace(
            self,
            resources=current,
            transactions=(*self.transactions, transaction),
        )
        return (
            updated,
            UnitResourceResult(
                player_id=self.player_id,
                unit_instance_id=self.unit_instance_id,
                battle_round=requested_round,
                resource_kind=requested_kind,
                transaction_kind=UnitResourceTransactionKind.SPEND,
                requested_amount=requested_amount,
                applied_amount=requested_amount,
                status=UnitResourceStatus.APPLIED,
                source_rule_id=requested_source,
                decision_request_id=request_id,
                decision_result_id=result_id,
                transaction=transaction,
            ),
        )

    def to_payload(self) -> UnitResourceLedgerPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "starting_resources": dict(sorted(self.starting_resources.items())),
            "resources": dict(sorted(self.resources.items())),
            "transactions": [transaction.to_payload() for transaction in self.transactions],
        }

    @classmethod
    def from_payload(cls, payload: UnitResourceLedgerPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            starting_resources=dict(payload["starting_resources"]),
            resources=dict(payload["resources"]),
            transactions=tuple(
                UnitResourceTransaction.from_payload(transaction)
                for transaction in payload["transactions"]
            ),
        )

    def _transaction(
        self,
        *,
        battle_round: int,
        resource_kind: str,
        transaction_kind: UnitResourceTransactionKind,
        amount: int,
        source_rule_id: str,
        decision_request_id: str | None = None,
        decision_result_id: str | None = None,
    ) -> UnitResourceTransaction:
        return UnitResourceTransaction(
            transaction_id=(
                f"{self.player_id}:{self.unit_instance_id}:{resource_kind}:"
                f"transaction-{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            battle_round=battle_round,
            resource_kind=resource_kind,
            transaction_kind=transaction_kind,
            amount=amount,
            source_rule_id=source_rule_id,
            decision_request_id=decision_request_id,
            decision_result_id=decision_result_id,
        )


def validate_starting_resource_allocations(
    field_name: str,
    value: object,
) -> tuple[UnitStartingResourceAllocation, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    allocations: list[UnitStartingResourceAllocation] = []
    seen: set[str] = set()
    for allocation in cast(tuple[object, ...], value):
        if type(allocation) is not UnitStartingResourceAllocation:
            raise GameLifecycleError(
                f"{field_name} must contain UnitStartingResourceAllocation values."
            )
        if allocation.resource_kind in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate resource kinds.")
        seen.add(allocation.resource_kind)
        allocations.append(allocation)
    return tuple(sorted(allocations, key=lambda allocation: allocation.resource_kind))


def unit_resource_transaction_kind_from_token(token: object) -> UnitResourceTransactionKind:
    if type(token) is UnitResourceTransactionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("UnitResourceTransactionKind token must be a string.")
    try:
        return UnitResourceTransactionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported UnitResourceTransactionKind: {token}.") from exc


def unit_resource_status_from_token(token: object) -> UnitResourceStatus:
    if type(token) is UnitResourceStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("UnitResourceStatus token must be a string.")
    try:
        return UnitResourceStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported UnitResourceStatus: {token}.") from exc


def _validate_transactions(
    value: object,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[UnitResourceTransaction, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("UnitResourceLedger transactions must be a tuple.")
    transactions: list[UnitResourceTransaction] = []
    initialized_kinds: set[str] = set()
    for index, transaction in enumerate(cast(tuple[object, ...], value), start=1):
        if type(transaction) is not UnitResourceTransaction:
            raise GameLifecycleError("Unit resource transactions must be typed.")
        if transaction.player_id != player_id or transaction.unit_instance_id != unit_instance_id:
            raise GameLifecycleError("Unit resource transaction ownership drift.")
        expected_id = (
            f"{player_id}:{unit_instance_id}:{transaction.resource_kind}:transaction-{index:06d}"
        )
        if transaction.transaction_id != expected_id:
            raise GameLifecycleError("Unit resource transaction ID drift.")
        if transaction.transaction_kind is UnitResourceTransactionKind.INITIALIZE:
            if transaction.resource_kind in initialized_kinds:
                raise GameLifecycleError("Unit resource kind initialized more than once.")
            initialized_kinds.add(transaction.resource_kind)
        elif transaction.resource_kind not in initialized_kinds:
            raise GameLifecycleError("Unit resource spent before initialization.")
        transactions.append(transaction)
    return tuple(transactions)


def _totals_from_transactions(
    transactions: tuple[UnitResourceTransaction, ...],
) -> tuple[dict[str, int], dict[str, int]]:
    starting: dict[str, int] = {}
    current: dict[str, int] = {}
    for transaction in transactions:
        if transaction.transaction_kind is UnitResourceTransactionKind.INITIALIZE:
            starting[transaction.resource_kind] = transaction.amount
            current[transaction.resource_kind] = transaction.amount
            continue
        remaining = current[transaction.resource_kind] - transaction.amount
        if remaining < 0:
            raise GameLifecycleError("Unit resource transactions overspend the ledger.")
        current[transaction.resource_kind] = remaining
    return dict(sorted(starting.items())), dict(sorted(current.items()))


def _validate_resource_totals(field_name: str, value: object) -> dict[str, int]:
    if type(value) is not dict:
        raise GameLifecycleError(f"{field_name} must be a dict.")
    totals: dict[str, int] = {}
    for raw_kind, raw_total in cast(dict[object, object], value).items():
        kind = _validate_identifier(f"{field_name} resource kind", raw_kind)
        if kind in totals:
            raise GameLifecycleError(f"{field_name} must not duplicate resource kinds.")
        totals[kind] = _validate_non_negative_int(f"{field_name} total", raw_total)
    return dict(sorted(totals.items()))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive int.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative int.")
    return value
