from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

FACTION_RESOURCE_SPEND_EFFECT_KIND = "faction_resource_spend"


def _empty_resource_totals() -> dict[str, int]:
    return {}


class FactionResourceTransactionKind(StrEnum):
    GAIN = "gain"
    SPEND = "spend"


class FactionResourceStatus(StrEnum):
    APPLIED = "applied"
    INSUFFICIENT = "insufficient"


class FactionResourceTransactionPayload(TypedDict):
    transaction_id: str
    player_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: str
    amount: int
    source_id: str


class FactionResourceLedgerPayload(TypedDict):
    player_id: str
    resources: dict[str, int]
    transactions: list[FactionResourceTransactionPayload]


class FactionResourceResultPayload(TypedDict):
    player_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: str
    requested_amount: int
    applied_amount: int
    status: str
    source_id: str
    transaction: FactionResourceTransactionPayload | None
    insufficient_reason: str | None


class FactionResourceSpendEffectPayload(TypedDict):
    effect_kind: str
    resource_kind: str
    amount: int
    reason: str


@dataclass(frozen=True, slots=True)
class FactionResourceTransaction:
    transaction_id: str
    player_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: FactionResourceTransactionKind
    amount: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _validate_identifier("FactionResourceTransaction transaction_id", self.transaction_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FactionResourceTransaction player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FactionResourceTransaction battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier("FactionResourceTransaction resource_kind", self.resource_kind),
        )
        object.__setattr__(
            self,
            "transaction_kind",
            faction_resource_transaction_kind_from_token(self.transaction_kind),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_positive_int("FactionResourceTransaction amount", self.amount),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("FactionResourceTransaction source_id", self.source_id),
        )

    def to_payload(self) -> FactionResourceTransactionPayload:
        return {
            "transaction_id": self.transaction_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "resource_kind": self.resource_kind,
            "transaction_kind": self.transaction_kind.value,
            "amount": self.amount,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: FactionResourceTransactionPayload) -> Self:
        return cls(
            transaction_id=payload["transaction_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            resource_kind=payload["resource_kind"],
            transaction_kind=faction_resource_transaction_kind_from_token(
                payload["transaction_kind"]
            ),
            amount=payload["amount"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class FactionResourceResult:
    player_id: str
    battle_round: int
    resource_kind: str
    transaction_kind: FactionResourceTransactionKind
    requested_amount: int
    applied_amount: int
    status: FactionResourceStatus
    source_id: str
    transaction: FactionResourceTransaction | None = None
    insufficient_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FactionResourceResult player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FactionResourceResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _validate_identifier("FactionResourceResult resource_kind", self.resource_kind),
        )
        object.__setattr__(
            self,
            "transaction_kind",
            faction_resource_transaction_kind_from_token(self.transaction_kind),
        )
        object.__setattr__(
            self,
            "requested_amount",
            _validate_positive_int("FactionResourceResult requested_amount", self.requested_amount),
        )
        object.__setattr__(
            self,
            "applied_amount",
            _validate_non_negative_int("FactionResourceResult applied_amount", self.applied_amount),
        )
        object.__setattr__(self, "status", faction_resource_status_from_token(self.status))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("FactionResourceResult source_id", self.source_id),
        )
        if (
            self.transaction is not None
            and type(self.transaction) is not FactionResourceTransaction
        ):
            raise GameLifecycleError("FactionResourceResult transaction must be typed.")
        object.__setattr__(
            self,
            "insufficient_reason",
            _validate_optional_identifier(
                "FactionResourceResult insufficient_reason",
                self.insufficient_reason,
            ),
        )
        if self.status is FactionResourceStatus.APPLIED:
            if self.applied_amount != self.requested_amount:
                raise GameLifecycleError("Applied faction resource result amount drift.")
            if self.transaction is None:
                raise GameLifecycleError("Applied faction resource result requires transaction.")
            if self.insufficient_reason is not None:
                raise GameLifecycleError("Applied faction resource result has insufficient reason.")
        if self.status is FactionResourceStatus.INSUFFICIENT:
            if self.applied_amount != 0:
                raise GameLifecycleError("Insufficient faction resource result applied amount.")
            if self.transaction is not None:
                raise GameLifecycleError("Insufficient faction resource result has transaction.")
            if self.insufficient_reason is None:
                raise GameLifecycleError("Insufficient faction resource result requires reason.")

    def to_payload(self) -> FactionResourceResultPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "resource_kind": self.resource_kind,
            "transaction_kind": self.transaction_kind.value,
            "requested_amount": self.requested_amount,
            "applied_amount": self.applied_amount,
            "status": self.status.value,
            "source_id": self.source_id,
            "transaction": None if self.transaction is None else self.transaction.to_payload(),
            "insufficient_reason": self.insufficient_reason,
        }


@dataclass(frozen=True, slots=True)
class FactionResourceLedger:
    player_id: str
    resources: dict[str, int] = field(default_factory=_empty_resource_totals)
    transactions: tuple[FactionResourceTransaction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FactionResourceLedger player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "resources",
            _validate_resource_totals(self.resources),
        )
        object.__setattr__(
            self,
            "transactions",
            _validate_transactions(self.transactions, player_id=self.player_id),
        )

    @classmethod
    def empty_for_player(cls, player_id: str) -> Self:
        return cls(player_id=player_id, resources={}, transactions=())

    def total(self, resource_kind: str) -> int:
        requested_kind = _validate_identifier("resource_kind", resource_kind)
        return self.resources.get(requested_kind, 0)

    def gain(
        self,
        *,
        battle_round: int,
        resource_kind: str,
        amount: int,
        source_id: str,
    ) -> tuple[Self, FactionResourceResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_kind = _validate_identifier("resource_kind", resource_kind)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source_id = _validate_identifier("source_id", source_id)
        transaction = self._transaction(
            battle_round=requested_round,
            resource_kind=requested_kind,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            amount=requested_amount,
            source_id=requested_source_id,
        )
        updated_resources = dict(self.resources)
        updated_resources[requested_kind] = self.total(requested_kind) + requested_amount
        return (
            replace(
                self,
                resources=updated_resources,
                transactions=(*self.transactions, transaction),
            ),
            FactionResourceResult(
                player_id=self.player_id,
                battle_round=requested_round,
                resource_kind=requested_kind,
                transaction_kind=FactionResourceTransactionKind.GAIN,
                requested_amount=requested_amount,
                applied_amount=requested_amount,
                status=FactionResourceStatus.APPLIED,
                source_id=requested_source_id,
                transaction=transaction,
            ),
        )

    def spend(
        self,
        *,
        battle_round: int,
        resource_kind: str,
        amount: int,
        source_id: str,
    ) -> tuple[Self, FactionResourceResult]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_kind = _validate_identifier("resource_kind", resource_kind)
        requested_amount = _validate_positive_int("amount", amount)
        requested_source_id = _validate_identifier("source_id", source_id)
        current_total = self.total(requested_kind)
        if current_total < requested_amount:
            return (
                self,
                FactionResourceResult(
                    player_id=self.player_id,
                    battle_round=requested_round,
                    resource_kind=requested_kind,
                    transaction_kind=FactionResourceTransactionKind.SPEND,
                    requested_amount=requested_amount,
                    applied_amount=0,
                    status=FactionResourceStatus.INSUFFICIENT,
                    source_id=requested_source_id,
                    insufficient_reason="insufficient_resource",
                ),
            )
        transaction = self._transaction(
            battle_round=requested_round,
            resource_kind=requested_kind,
            transaction_kind=FactionResourceTransactionKind.SPEND,
            amount=requested_amount,
            source_id=requested_source_id,
        )
        updated_resources = dict(self.resources)
        updated_resources[requested_kind] = current_total - requested_amount
        return (
            replace(
                self,
                resources=updated_resources,
                transactions=(*self.transactions, transaction),
            ),
            FactionResourceResult(
                player_id=self.player_id,
                battle_round=requested_round,
                resource_kind=requested_kind,
                transaction_kind=FactionResourceTransactionKind.SPEND,
                requested_amount=requested_amount,
                applied_amount=requested_amount,
                status=FactionResourceStatus.APPLIED,
                source_id=requested_source_id,
                transaction=transaction,
            ),
        )

    def to_payload(self) -> FactionResourceLedgerPayload:
        return {
            "player_id": self.player_id,
            "resources": dict(sorted(self.resources.items())),
            "transactions": [transaction.to_payload() for transaction in self.transactions],
        }

    @classmethod
    def from_payload(cls, payload: FactionResourceLedgerPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            resources=dict(payload["resources"]),
            transactions=tuple(
                FactionResourceTransaction.from_payload(transaction)
                for transaction in payload["transactions"]
            ),
        )

    def _transaction(
        self,
        *,
        battle_round: int,
        resource_kind: str,
        transaction_kind: FactionResourceTransactionKind,
        amount: int,
        source_id: str,
    ) -> FactionResourceTransaction:
        next_index = len(self.transactions) + 1
        return FactionResourceTransaction(
            transaction_id=f"{self.player_id}:{resource_kind}:transaction-{next_index:06d}",
            player_id=self.player_id,
            battle_round=battle_round,
            resource_kind=resource_kind,
            transaction_kind=transaction_kind,
            amount=amount,
            source_id=source_id,
        )


def initial_faction_resource_ledgers(player_ids: tuple[str, ...]) -> list[FactionResourceLedger]:
    return [FactionResourceLedger.empty_for_player(player_id) for player_id in player_ids]


def faction_resource_transaction_kind_from_token(
    token: object,
) -> FactionResourceTransactionKind:
    if type(token) is FactionResourceTransactionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FactionResourceTransactionKind token must be a string.")
    try:
        return FactionResourceTransactionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported FactionResourceTransactionKind token: {token}."
        ) from exc


def faction_resource_status_from_token(token: object) -> FactionResourceStatus:
    if type(token) is FactionResourceStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FactionResourceStatus token must be a string.")
    try:
        return FactionResourceStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported FactionResourceStatus token: {token}.") from exc


def faction_resource_spend_effect_payload(
    *,
    resource_kind: str,
    amount: int,
    reason: str,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": FACTION_RESOURCE_SPEND_EFFECT_KIND,
            "resource_kind": _validate_identifier("resource_kind", resource_kind),
            "amount": _validate_positive_int("amount", amount),
            "reason": _validate_identifier("reason", reason),
        }
    )


def apply_faction_resource_spend_effect(
    *,
    state: object,
    player_id: str,
    source_id: str,
    effect_payload: JsonValue,
) -> FactionResourceResult | None:
    if not isinstance(effect_payload, dict):
        return None
    if effect_payload.get("effect_kind") != FACTION_RESOURCE_SPEND_EFFECT_KIND:
        return None
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Faction resource spend effect requires GameState.")
    payload = _faction_resource_spend_payload(effect_payload)
    result = state.spend_faction_resource(
        player_id=_validate_identifier("player_id", player_id),
        resource_kind=payload["resource_kind"],
        amount=payload["amount"],
        source_id=_validate_identifier("source_id", source_id),
    )
    if result.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Faction resource spend effect could not be applied.")
    return result


def faction_resource_result_enriched_payload(
    *,
    effect_payload: JsonValue,
    result: FactionResourceResult | None,
) -> JsonValue:
    if result is None:
        return effect_payload
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Faction resource spend effect payload must be an object.")
    return validate_json_value(
        {
            **effect_payload,
            "faction_resource_result": validate_json_value(result.to_payload()),
        }
    )


def _faction_resource_spend_payload(
    payload: dict[str, JsonValue],
) -> FactionResourceSpendEffectPayload:
    if payload.get("effect_kind") != FACTION_RESOURCE_SPEND_EFFECT_KIND:
        raise GameLifecycleError("Faction resource spend payload effect_kind drift.")
    amount = payload.get("amount")
    if type(amount) is not int:
        raise GameLifecycleError("Faction resource spend payload amount must be an int.")
    return {
        "effect_kind": FACTION_RESOURCE_SPEND_EFFECT_KIND,
        "resource_kind": _validate_identifier("resource_kind", payload.get("resource_kind")),
        "amount": _validate_positive_int("amount", amount),
        "reason": _validate_identifier("reason", payload.get("reason")),
    }


def _validate_resource_totals(value: object) -> dict[str, int]:
    if value is None:
        return {}
    if type(value) is not dict:
        raise GameLifecycleError("FactionResourceLedger resources must be a dict.")
    resources: dict[str, int] = {}
    for raw_kind, raw_total in cast(dict[object, object], value).items():
        kind = _validate_identifier("FactionResourceLedger resource kind", raw_kind)
        total = _validate_non_negative_int("FactionResourceLedger resource total", raw_total)
        if kind in resources:
            raise GameLifecycleError("FactionResourceLedger resources must not duplicate kinds.")
        resources[kind] = total
    return dict(sorted(resources.items()))


def _validate_transactions(
    value: object,
    *,
    player_id: str,
) -> tuple[FactionResourceTransaction, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("FactionResourceLedger transactions must be a tuple.")
    transactions: list[FactionResourceTransaction] = []
    seen_ids: set[str] = set()
    for transaction in cast(tuple[object, ...], value):
        if type(transaction) is not FactionResourceTransaction:
            raise GameLifecycleError(
                "FactionResourceLedger transactions must contain typed transactions."
            )
        if transaction.player_id != player_id:
            raise GameLifecycleError("FactionResourceLedger transaction player drift.")
        if transaction.transaction_id in seen_ids:
            raise GameLifecycleError("FactionResourceLedger transaction IDs must be unique.")
        seen_ids.add(transaction.transaction_id)
        transactions.append(transaction)
    return tuple(transactions)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value
