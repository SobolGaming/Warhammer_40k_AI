from __future__ import annotations

from dataclasses import dataclass
from typing import Self


class FactionAliasError(ValueError):
    """Raised when faction alias data violates CORE V2 invariants."""


@dataclass(frozen=True, slots=True)
class FactionAliasDefinition:
    faction_id: str
    name: str
    aliases: tuple[str, ...]
    faction_keywords: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(self, "name", _validate_identifier("name", self.name))
        object.__setattr__(
            self,
            "aliases",
            _validate_identifier_tuple("aliases", self.aliases),
        )
        object.__setattr__(
            self,
            "faction_keywords",
            _validate_identifier_tuple("faction_keywords", self.faction_keywords),
        )

    @classmethod
    def from_primary_keyword(cls, *, faction_id: str, name: str, keyword: str) -> Self:
        return cls(
            faction_id=faction_id,
            name=name,
            aliases=(keyword,),
            faction_keywords=(keyword,),
        )

    def reference_tokens(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.name, *self.aliases, *self.faction_keywords)))


SPACE_MARINES_FACTION_ID = "space-marines"
CHAOS_SPACE_MARINES_FACTION_ID = "chaos-space-marines"
AELDARI_FACTION_ID = "aeldari"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"

SPACE_MARINES_FACTION_ALIAS = "Adeptus Astartes"
CHAOS_SPACE_MARINES_FACTION_ALIAS = "Heretic Astartes"
AELDARI_FACTION_ALIAS = "Asuryani"
CHAOS_DAEMONS_FACTION_ALIAS = "Legiones Daemonica"


def faction_aliases() -> tuple[FactionAliasDefinition, ...]:
    return _FACTION_ALIASES


def faction_alias_for_id(faction_id: str) -> FactionAliasDefinition | None:
    return _FACTION_ALIASES_BY_ID.get(_validate_identifier("faction_id", faction_id))


def faction_reference_tokens_for_id(faction_id: str) -> tuple[str, ...]:
    definition = faction_alias_for_id(faction_id)
    if definition is None:
        return (_validate_identifier("faction_id", faction_id),)
    return definition.reference_tokens()


def faction_reference_matches(*, faction_id: str, reference: str) -> bool:
    expected = {
        _canonical_reference_token(token) for token in faction_reference_tokens_for_id(faction_id)
    }
    return _canonical_reference_token(reference) in expected


def _canonical_reference_token(value: str) -> str:
    return " ".join(_validate_identifier("reference", value).upper().split())


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise FactionAliasError(f"Faction alias {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise FactionAliasError(f"Faction alias {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise FactionAliasError(f"Faction alias {field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        canonical = _canonical_reference_token(identifier)
        if canonical in seen:
            raise FactionAliasError(f"Faction alias {field_name} must not contain duplicates.")
        seen.add(canonical)
        validated.append(identifier)
    return tuple(validated)


_FACTION_ALIASES: tuple[FactionAliasDefinition, ...] = (
    FactionAliasDefinition.from_primary_keyword(
        faction_id=SPACE_MARINES_FACTION_ID,
        name="Space Marines",
        keyword=SPACE_MARINES_FACTION_ALIAS,
    ),
    FactionAliasDefinition.from_primary_keyword(
        faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
        name="Chaos Space Marines",
        keyword=CHAOS_SPACE_MARINES_FACTION_ALIAS,
    ),
    FactionAliasDefinition.from_primary_keyword(
        faction_id=AELDARI_FACTION_ID,
        name="Aeldari",
        keyword=AELDARI_FACTION_ALIAS,
    ),
    FactionAliasDefinition.from_primary_keyword(
        faction_id=CHAOS_DAEMONS_FACTION_ID,
        name="Chaos Daemons",
        keyword=CHAOS_DAEMONS_FACTION_ALIAS,
    ),
)
_FACTION_ALIASES_BY_ID = {definition.faction_id: definition for definition in _FACTION_ALIASES}
