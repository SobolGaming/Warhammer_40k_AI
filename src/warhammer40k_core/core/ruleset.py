from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict


class RulesetError(ValueError):
    """Raised when ruleset identity data violates CORE V2 invariants."""


class RulesetEdition(StrEnum):
    ELEVENTH = "11e"


class RulesetIdPayload(TypedDict):
    game: str
    edition: str
    version: str


@dataclass(frozen=True, slots=True)
class RulesetId:
    game: str
    edition: RulesetEdition
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "game", _validate_identifier("RulesetId game", self.game))
        object.__setattr__(self, "edition", ruleset_edition_from_token(self.edition))
        object.__setattr__(
            self,
            "version",
            _validate_identifier("RulesetId version", self.version),
        )

    @classmethod
    def warhammer_40000_eleventh(cls, version: str = "core-v2-phase14a") -> Self:
        return cls(game="warhammer_40000", edition=RulesetEdition.ELEVENTH, version=version)

    def to_payload(self) -> RulesetIdPayload:
        return {
            "game": self.game,
            "edition": self.edition.value,
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: RulesetIdPayload) -> Self:
        return cls(
            game=payload["game"],
            edition=ruleset_edition_from_token(payload["edition"]),
            version=payload["version"],
        )


def ruleset_edition_from_token(token: object) -> RulesetEdition:
    if type(token) is RulesetEdition:
        return token
    if type(token) is not str:
        raise RulesetError("RulesetEdition token must be a string.")
    try:
        return RulesetEdition(token)
    except ValueError as exc:
        raise RulesetError(f"Unsupported RulesetEdition token: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise RulesetError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise RulesetError(f"{field_name} must not be empty.")
    return stripped
