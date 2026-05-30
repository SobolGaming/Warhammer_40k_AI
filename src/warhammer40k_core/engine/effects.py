from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


class EffectError(ValueError):
    """Raised when a persisting effect cannot be represented safely."""


class EffectExpirationKind(StrEnum):
    START_PHASE = "start_phase"
    END_PHASE = "end_phase"
    START_TURN = "start_turn"
    END_TURN = "end_turn"
    START_BATTLE_ROUND = "start_battle_round"
    END_BATTLE_ROUND = "end_battle_round"
    END_OF_BATTLE = "end_of_battle"


class EffectExpirationPayload(TypedDict):
    expiration_kind: str
    battle_round: int | None
    phase: str | None
    player_id: str | None


class EffectExpirationBoundaryPayload(TypedDict):
    expiration_kind: str
    battle_round: int | None
    phase: str | None
    player_id: str | None


class PersistingEffectPayload(TypedDict):
    effect_id: str
    source_rule_id: str
    owner_player_id: str
    target_unit_instance_ids: list[str]
    started_battle_round: int
    started_phase: str | None
    expiration: EffectExpirationPayload
    effect_payload: JsonValue


@dataclass(frozen=True, slots=True)
class EffectExpiration:
    expiration_kind: EffectExpirationKind
    battle_round: int | None = None
    phase: BattlePhaseKind | None = None
    player_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expiration_kind",
            effect_expiration_kind_from_token(self.expiration_kind),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_optional_positive_int("EffectExpiration battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("EffectExpiration phase", self.phase),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_optional_identifier("EffectExpiration player_id", self.player_id),
        )
        self._validate_required_context()

    @classmethod
    def end_phase(
        cls,
        *,
        battle_round: int,
        phase: BattlePhaseKind,
        player_id: str,
    ) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_PHASE,
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )

    @classmethod
    def start_phase(
        cls,
        *,
        battle_round: int,
        phase: BattlePhaseKind,
        player_id: str,
    ) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_PHASE,
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )

    @classmethod
    def end_turn(cls, *, battle_round: int, player_id: str) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_TURN,
            battle_round=battle_round,
            player_id=player_id,
        )

    @classmethod
    def start_turn(cls, *, battle_round: int, player_id: str) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_TURN,
            battle_round=battle_round,
            player_id=player_id,
        )

    @classmethod
    def end_battle_round(cls, *, battle_round: int) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_BATTLE_ROUND,
            battle_round=battle_round,
        )

    @classmethod
    def start_battle_round(cls, *, battle_round: int) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_BATTLE_ROUND,
            battle_round=battle_round,
        )

    @classmethod
    def end_of_battle(cls) -> Self:
        return cls(expiration_kind=EffectExpirationKind.END_OF_BATTLE)

    def matches_boundary(self, boundary: EffectExpirationBoundary) -> bool:
        if type(boundary) is not EffectExpirationBoundary:
            raise EffectError("EffectExpiration boundary must be an EffectExpirationBoundary.")
        return self.to_payload() == boundary.to_payload()

    def to_payload(self) -> EffectExpirationPayload:
        return {
            "expiration_kind": self.expiration_kind.value,
            "battle_round": self.battle_round,
            "phase": None if self.phase is None else self.phase.value,
            "player_id": self.player_id,
        }

    @classmethod
    def from_payload(cls, payload: EffectExpirationPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            expiration_kind=effect_expiration_kind_from_token(payload["expiration_kind"]),
            battle_round=payload["battle_round"],
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            player_id=payload["player_id"],
        )

    def _validate_required_context(self) -> None:
        if self.expiration_kind in (
            EffectExpirationKind.START_PHASE,
            EffectExpirationKind.END_PHASE,
        ):
            if self.battle_round is None or self.phase is None or self.player_id is None:
                raise EffectError("Phase effect expiration requires round, phase, and player.")
            return
        if self.expiration_kind in (
            EffectExpirationKind.START_TURN,
            EffectExpirationKind.END_TURN,
        ):
            if self.battle_round is None or self.player_id is None:
                raise EffectError("Turn effect expiration requires round and player.")
            if self.phase is not None:
                raise EffectError("Turn effect expiration must not include a phase.")
            return
        if self.expiration_kind in (
            EffectExpirationKind.START_BATTLE_ROUND,
            EffectExpirationKind.END_BATTLE_ROUND,
        ):
            if self.battle_round is None:
                raise EffectError("Battle-round effect expiration requires a round.")
            if self.phase is not None or self.player_id is not None:
                raise EffectError("Battle-round effect expiration must not include phase/player.")
            return
        if self.expiration_kind is EffectExpirationKind.END_OF_BATTLE and (
            self.battle_round is not None or self.phase is not None or self.player_id is not None
        ):
            raise EffectError("End-of-battle effect expiration must not include timing context.")


@dataclass(frozen=True, slots=True)
class EffectExpirationBoundary:
    expiration_kind: EffectExpirationKind
    battle_round: int | None = None
    phase: BattlePhaseKind | None = None
    player_id: str | None = None

    def __post_init__(self) -> None:
        expiration = EffectExpiration(
            expiration_kind=self.expiration_kind,
            battle_round=self.battle_round,
            phase=self.phase,
            player_id=self.player_id,
        )
        object.__setattr__(self, "expiration_kind", expiration.expiration_kind)
        object.__setattr__(self, "battle_round", expiration.battle_round)
        object.__setattr__(self, "phase", expiration.phase)
        object.__setattr__(self, "player_id", expiration.player_id)

    @classmethod
    def phase_end(
        cls,
        *,
        battle_round: int,
        phase: BattlePhaseKind,
        player_id: str,
    ) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_PHASE,
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )

    @classmethod
    def phase_start(
        cls,
        *,
        battle_round: int,
        phase: BattlePhaseKind,
        player_id: str,
    ) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_PHASE,
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )

    @classmethod
    def turn_end(cls, *, battle_round: int, player_id: str) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_TURN,
            battle_round=battle_round,
            player_id=player_id,
        )

    @classmethod
    def turn_start(cls, *, battle_round: int, player_id: str) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_TURN,
            battle_round=battle_round,
            player_id=player_id,
        )

    @classmethod
    def battle_round_end(cls, *, battle_round: int) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.END_BATTLE_ROUND,
            battle_round=battle_round,
        )

    @classmethod
    def battle_round_start(cls, *, battle_round: int) -> Self:
        return cls(
            expiration_kind=EffectExpirationKind.START_BATTLE_ROUND,
            battle_round=battle_round,
        )

    @classmethod
    def battle_end(cls) -> Self:
        return cls(expiration_kind=EffectExpirationKind.END_OF_BATTLE)

    def to_payload(self) -> EffectExpirationBoundaryPayload:
        return {
            "expiration_kind": self.expiration_kind.value,
            "battle_round": self.battle_round,
            "phase": None if self.phase is None else self.phase.value,
            "player_id": self.player_id,
        }


@dataclass(frozen=True, slots=True)
class PersistingEffect:
    effect_id: str
    source_rule_id: str
    owner_player_id: str
    target_unit_instance_ids: tuple[str, ...]
    started_battle_round: int
    expiration: EffectExpiration
    effect_payload: JsonValue
    started_phase: BattlePhaseKind | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effect_id",
            _validate_identifier("PersistingEffect effect_id", self.effect_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PersistingEffect source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("PersistingEffect owner_player_id", self.owner_player_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "PersistingEffect target_unit_instance_ids",
                self.target_unit_instance_ids,
                min_length=1,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "started_battle_round",
            _validate_positive_int(
                "PersistingEffect started_battle_round",
                self.started_battle_round,
            ),
        )
        if type(self.expiration) is not EffectExpiration:
            raise EffectError("PersistingEffect expiration must be an EffectExpiration.")
        object.__setattr__(
            self,
            "started_phase",
            _validate_optional_phase("PersistingEffect started_phase", self.started_phase),
        )
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def applies_to_unit(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return requested_unit_id in self.target_unit_instance_ids

    def expires_at(self, boundary: EffectExpirationBoundary) -> bool:
        return self.expiration.matches_boundary(boundary)

    def with_attached_unit_split(
        self,
        *,
        attached_unit_instance_id: str,
        surviving_unit_instance_ids: tuple[str, ...],
    ) -> Self:
        requested_attached_id = _validate_identifier(
            "attached_unit_instance_id",
            attached_unit_instance_id,
        )
        survivor_ids = _validate_identifier_tuple(
            "surviving_unit_instance_ids",
            surviving_unit_instance_ids,
            min_length=1,
            sort_values=True,
        )
        if requested_attached_id not in self.target_unit_instance_ids:
            return self
        replacement_targets = tuple(
            sorted(
                (
                    *(
                        unit_id
                        for unit_id in self.target_unit_instance_ids
                        if unit_id != requested_attached_id
                    ),
                    *survivor_ids,
                )
            )
        )
        return replace(self, target_unit_instance_ids=replacement_targets)

    def to_payload(self) -> PersistingEffectPayload:
        return {
            "effect_id": self.effect_id,
            "source_rule_id": self.source_rule_id,
            "owner_player_id": self.owner_player_id,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
            "started_battle_round": self.started_battle_round,
            "started_phase": None if self.started_phase is None else self.started_phase.value,
            "expiration": self.expiration.to_payload(),
            "effect_payload": self.effect_payload,
        }

    @classmethod
    def from_payload(cls, payload: PersistingEffectPayload) -> Self:
        phase_token = payload["started_phase"]
        return cls(
            effect_id=payload["effect_id"],
            source_rule_id=payload["source_rule_id"],
            owner_player_id=payload["owner_player_id"],
            target_unit_instance_ids=tuple(payload["target_unit_instance_ids"]),
            started_battle_round=payload["started_battle_round"],
            started_phase=(
                None if phase_token is None else battle_phase_kind_from_token(phase_token)
            ),
            expiration=EffectExpiration.from_payload(payload["expiration"]),
            effect_payload=payload["effect_payload"],
        )


def effect_expiration_kind_from_token(token: object) -> EffectExpirationKind:
    if type(token) is EffectExpirationKind:
        return token
    if type(token) is not str:
        raise EffectError("EffectExpirationKind token must be a string.")
    try:
        return EffectExpirationKind(token)
    except ValueError as exc:
        raise EffectError(f"Unsupported EffectExpirationKind token: {token}.") from exc


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    try:
        return battle_phase_kind_from_token(value)
    except ValueError as exc:
        raise EffectError(f"{field_name} must be a supported BattlePhaseKind.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise EffectError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise EffectError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise EffectError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise EffectError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise EffectError(f"{field_name} must contain at least {min_length} value.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise EffectError(f"{field_name} must be an integer.")
    if value < 1:
        raise EffectError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)
