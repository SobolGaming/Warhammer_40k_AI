from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.content_scope import (
    CatalogContentScope,
    CatalogContentScopeError,
    catalog_content_scope_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token


class FactionCatalogError(ValueError):
    """Raised when faction catalog data violates CORE V2 invariants."""


class ArmyRuleDefinitionPayload(TypedDict):
    rule_id: str
    name: str
    source_id: str
    content_scope: str
    ability_descriptor_ids: list[str]


class FactionDefinitionPayload(TypedDict):
    faction_id: str
    name: str
    content_scope: str
    faction_keywords: list[str]
    army_rule_ids: list[str]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class ArmyRuleDefinition:
    rule_id: str
    name: str
    source_id: str
    content_scope: CatalogContentScope = CatalogContentScope.MATCHED_PLAY
    ability_descriptor_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_unprefixed_identifier(
                "ArmyRuleDefinition rule_id",
                self.rule_id,
                "army-rule:",
            ),
        )
        object.__setattr__(self, "name", _validate_identifier("ArmyRuleDefinition name", self.name))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ArmyRuleDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "ArmyRuleDefinition content_scope",
                self.content_scope,
            ),
        )
        object.__setattr__(
            self,
            "ability_descriptor_ids",
            _validate_identifier_tuple(
                "ArmyRuleDefinition ability_descriptor_ids",
                self.ability_descriptor_ids,
            ),
        )

    def stable_identity(self) -> str:
        return f"army-rule:{self.rule_id}"

    def to_payload(self) -> ArmyRuleDefinitionPayload:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "source_id": self.source_id,
            "content_scope": self.content_scope.value,
            "ability_descriptor_ids": list(self.ability_descriptor_ids),
        }

    @classmethod
    def from_payload(cls, payload: ArmyRuleDefinitionPayload) -> Self:
        return cls(
            rule_id=payload["rule_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            ability_descriptor_ids=tuple(payload["ability_descriptor_ids"]),
        )


@dataclass(frozen=True, slots=True)
class FactionDefinition:
    faction_id: str
    name: str
    faction_keywords: tuple[str, ...]
    content_scope: CatalogContentScope = CatalogContentScope.MATCHED_PLAY
    army_rule_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_id",
            _validate_unprefixed_identifier(
                "FactionDefinition faction_id",
                self.faction_id,
                "faction:",
            ),
        )
        object.__setattr__(self, "name", _validate_identifier("FactionDefinition name", self.name))
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "FactionDefinition content_scope",
                self.content_scope,
            ),
        )
        faction_keywords = _validate_identifier_tuple(
            "FactionDefinition faction_keywords",
            self.faction_keywords,
            canonicalize_keywords=True,
        )
        if not faction_keywords:
            raise FactionCatalogError("FactionDefinition faction_keywords must not be empty.")
        object.__setattr__(self, "faction_keywords", faction_keywords)
        object.__setattr__(
            self,
            "army_rule_ids",
            _validate_identifier_tuple("FactionDefinition army_rule_ids", self.army_rule_ids),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("FactionDefinition source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"faction:{self.faction_id}"

    def to_payload(self) -> FactionDefinitionPayload:
        return {
            "faction_id": self.faction_id,
            "name": self.name,
            "content_scope": self.content_scope.value,
            "faction_keywords": list(self.faction_keywords),
            "army_rule_ids": list(self.army_rule_ids),
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: FactionDefinitionPayload) -> Self:
        return cls(
            faction_id=payload["faction_id"],
            name=payload["name"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            faction_keywords=tuple(payload["faction_keywords"]),
            army_rule_ids=tuple(payload["army_rule_ids"]),
            source_ids=tuple(payload["source_ids"]),
        )


def _catalog_content_scope_from_token(field_name: str, token: object) -> CatalogContentScope:
    try:
        return catalog_content_scope_from_token(token)
    except CatalogContentScopeError as exc:
        raise FactionCatalogError(f"{field_name} is invalid.") from exc


_validate_identifier = IdentifierValidator(FactionCatalogError)


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise FactionCatalogError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    canonicalize_keywords: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise FactionCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if canonicalize_keywords:
            identifier = canonical_keyword_token(identifier)
        if identifier in seen:
            raise FactionCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))
