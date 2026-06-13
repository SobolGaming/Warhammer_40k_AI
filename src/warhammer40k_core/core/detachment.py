from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.content_scope import (
    CatalogContentScope,
    CatalogContentScopeError,
    catalog_content_scope_from_token,
)


class DetachmentCatalogError(ValueError):
    """Raised when detachment catalog data violates CORE V2 invariants."""


class EnhancementSubtype(StrEnum):
    UPGRADE = "upgrade"


class EnhancementDefinitionPayload(TypedDict):
    enhancement_id: str
    name: str
    source_id: str
    content_scope: str
    subtypes: list[str]
    points: int | None
    ability_descriptor_ids: list[str]
    target_required_keywords: list[str]
    target_required_faction_keywords: list[str]


class StratagemDefinitionPayload(TypedDict):
    stratagem_id: str
    name: str
    source_id: str
    content_scope: str
    command_point_cost: int
    timing_tags: list[str]
    ability_descriptor_ids: list[str]


class DetachmentDefinitionPayload(TypedDict):
    detachment_id: str
    name: str
    faction_id: str
    content_scope: str
    detachment_point_cost: int | None
    unit_datasheet_ids: list[str]
    force_disposition_ids: list[str]
    rule_source_ids: list[str]
    enhancement_ids: list[str]
    stratagem_ids: list[str]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class EnhancementDefinition:
    enhancement_id: str
    name: str
    source_id: str
    content_scope: CatalogContentScope = CatalogContentScope.MATCHED_PLAY
    subtypes: tuple[EnhancementSubtype, ...] = ()
    points: int | None = None
    ability_descriptor_ids: tuple[str, ...] = ()
    target_required_keywords: tuple[str, ...] = ()
    target_required_faction_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_unprefixed_identifier(
                "EnhancementDefinition enhancement_id",
                self.enhancement_id,
                "enhancement:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("EnhancementDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("EnhancementDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "EnhancementDefinition content_scope",
                self.content_scope,
            ),
        )
        object.__setattr__(
            self,
            "points",
            _validate_optional_non_negative_int("EnhancementDefinition points", self.points),
        )
        object.__setattr__(
            self,
            "subtypes",
            _validate_enhancement_subtype_tuple(
                "EnhancementDefinition subtypes",
                self.subtypes,
            ),
        )
        object.__setattr__(
            self,
            "ability_descriptor_ids",
            _validate_identifier_tuple(
                "EnhancementDefinition ability_descriptor_ids",
                self.ability_descriptor_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_required_keywords",
            _validate_identifier_tuple(
                "EnhancementDefinition target_required_keywords",
                self.target_required_keywords,
            ),
        )
        object.__setattr__(
            self,
            "target_required_faction_keywords",
            _validate_identifier_tuple(
                "EnhancementDefinition target_required_faction_keywords",
                self.target_required_faction_keywords,
            ),
        )

    def stable_identity(self) -> str:
        return f"enhancement:{self.enhancement_id}"

    def to_payload(self) -> EnhancementDefinitionPayload:
        return {
            "enhancement_id": self.enhancement_id,
            "name": self.name,
            "source_id": self.source_id,
            "content_scope": self.content_scope.value,
            "subtypes": [subtype.value for subtype in self.subtypes],
            "points": self.points,
            "ability_descriptor_ids": list(self.ability_descriptor_ids),
            "target_required_keywords": list(self.target_required_keywords),
            "target_required_faction_keywords": list(self.target_required_faction_keywords),
        }

    @classmethod
    def from_payload(cls, payload: EnhancementDefinitionPayload) -> Self:
        return cls(
            enhancement_id=payload["enhancement_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            subtypes=tuple(
                enhancement_subtype_from_token(subtype) for subtype in payload["subtypes"]
            ),
            points=payload["points"],
            ability_descriptor_ids=tuple(payload["ability_descriptor_ids"]),
            target_required_keywords=tuple(payload["target_required_keywords"]),
            target_required_faction_keywords=tuple(payload["target_required_faction_keywords"]),
        )


@dataclass(frozen=True, slots=True)
class StratagemDefinition:
    stratagem_id: str
    name: str
    source_id: str
    command_point_cost: int
    content_scope: CatalogContentScope = CatalogContentScope.MATCHED_PLAY
    timing_tags: tuple[str, ...] = ()
    ability_descriptor_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stratagem_id",
            _validate_unprefixed_identifier(
                "StratagemDefinition stratagem_id",
                self.stratagem_id,
                "stratagem:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("StratagemDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StratagemDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "StratagemDefinition content_scope",
                self.content_scope,
            ),
        )
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int(
                "StratagemDefinition command_point_cost",
                self.command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "timing_tags",
            _validate_identifier_tuple("StratagemDefinition timing_tags", self.timing_tags),
        )
        object.__setattr__(
            self,
            "ability_descriptor_ids",
            _validate_identifier_tuple(
                "StratagemDefinition ability_descriptor_ids",
                self.ability_descriptor_ids,
            ),
        )

    def stable_identity(self) -> str:
        return f"stratagem:{self.stratagem_id}"

    def to_payload(self) -> StratagemDefinitionPayload:
        return {
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "source_id": self.source_id,
            "content_scope": self.content_scope.value,
            "command_point_cost": self.command_point_cost,
            "timing_tags": list(self.timing_tags),
            "ability_descriptor_ids": list(self.ability_descriptor_ids),
        }

    @classmethod
    def from_payload(cls, payload: StratagemDefinitionPayload) -> Self:
        return cls(
            stratagem_id=payload["stratagem_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            command_point_cost=payload["command_point_cost"],
            timing_tags=tuple(payload["timing_tags"]),
            ability_descriptor_ids=tuple(payload["ability_descriptor_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DetachmentDefinition:
    detachment_id: str
    name: str
    faction_id: str
    content_scope: CatalogContentScope = CatalogContentScope.MATCHED_PLAY
    detachment_point_cost: int | None = None
    unit_datasheet_ids: tuple[str, ...] = ()
    force_disposition_ids: tuple[str, ...] = ()
    rule_source_ids: tuple[str, ...] = ()
    enhancement_ids: tuple[str, ...] = ()
    stratagem_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "detachment_id",
            _validate_unprefixed_identifier(
                "DetachmentDefinition detachment_id",
                self.detachment_id,
                "detachment:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("DetachmentDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "faction_id",
            _validate_identifier("DetachmentDefinition faction_id", self.faction_id),
        )
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "DetachmentDefinition content_scope",
                self.content_scope,
            ),
        )
        object.__setattr__(
            self,
            "detachment_point_cost",
            _validate_optional_detachment_point_cost(
                "DetachmentDefinition detachment_point_cost",
                self.detachment_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "unit_datasheet_ids",
            _validate_identifier_tuple(
                "DetachmentDefinition unit_datasheet_ids",
                self.unit_datasheet_ids,
            ),
        )
        object.__setattr__(
            self,
            "force_disposition_ids",
            _validate_identifier_tuple(
                "DetachmentDefinition force_disposition_ids",
                self.force_disposition_ids,
            ),
        )
        object.__setattr__(
            self,
            "rule_source_ids",
            _validate_identifier_tuple(
                "DetachmentDefinition rule_source_ids",
                self.rule_source_ids,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_ids",
            _validate_identifier_tuple(
                "DetachmentDefinition enhancement_ids",
                self.enhancement_ids,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_ids",
            _validate_identifier_tuple("DetachmentDefinition stratagem_ids", self.stratagem_ids),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("DetachmentDefinition source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"detachment:{self.detachment_id}"

    def to_payload(self) -> DetachmentDefinitionPayload:
        return {
            "detachment_id": self.detachment_id,
            "name": self.name,
            "faction_id": self.faction_id,
            "content_scope": self.content_scope.value,
            "detachment_point_cost": self.detachment_point_cost,
            "unit_datasheet_ids": list(self.unit_datasheet_ids),
            "force_disposition_ids": list(self.force_disposition_ids),
            "rule_source_ids": list(self.rule_source_ids),
            "enhancement_ids": list(self.enhancement_ids),
            "stratagem_ids": list(self.stratagem_ids),
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: DetachmentDefinitionPayload) -> Self:
        return cls(
            detachment_id=payload["detachment_id"],
            name=payload["name"],
            faction_id=payload["faction_id"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            detachment_point_cost=payload["detachment_point_cost"],
            unit_datasheet_ids=tuple(payload["unit_datasheet_ids"]),
            force_disposition_ids=tuple(payload["force_disposition_ids"]),
            rule_source_ids=tuple(payload["rule_source_ids"]),
            enhancement_ids=tuple(payload["enhancement_ids"]),
            stratagem_ids=tuple(payload["stratagem_ids"]),
            source_ids=tuple(payload["source_ids"]),
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DetachmentCatalogError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DetachmentCatalogError(f"{field_name} must not be empty.")
    return stripped


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise DetachmentCatalogError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _catalog_content_scope_from_token(field_name: str, token: object) -> CatalogContentScope:
    try:
        return catalog_content_scope_from_token(token)
    except CatalogContentScopeError as exc:
        raise DetachmentCatalogError(f"{field_name} is invalid.") from exc


def enhancement_subtype_from_token(token: object) -> EnhancementSubtype:
    if type(token) is EnhancementSubtype:
        return token
    if type(token) is not str:
        raise DetachmentCatalogError("EnhancementSubtype token must be a string.")
    try:
        return EnhancementSubtype(token)
    except ValueError as exc:
        raise DetachmentCatalogError(f"Unsupported EnhancementSubtype token: {token}.") from exc


def _validate_enhancement_subtype_tuple(
    field_name: str,
    values: tuple[EnhancementSubtype, ...],
) -> tuple[EnhancementSubtype, ...]:
    if type(values) is not tuple:
        raise DetachmentCatalogError(f"{field_name} must be a tuple.")
    seen: set[EnhancementSubtype] = set()
    validated: list[EnhancementSubtype] = []
    for value in values:
        subtype = enhancement_subtype_from_token(value)
        if subtype in seen:
            raise DetachmentCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(subtype)
        validated.append(subtype)
    return tuple(sorted(validated, key=lambda subtype: subtype.value))


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise DetachmentCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise DetachmentCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise DetachmentCatalogError(f"{field_name} must be an integer.")
    if value < 0:
        raise DetachmentCatalogError(f"{field_name} must not be negative.")
    return value


def _validate_optional_detachment_point_cost(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise DetachmentCatalogError(f"{field_name} must be an integer.")
    if value < 1 or value > 3:
        raise DetachmentCatalogError(f"{field_name} must be between 1 and 3.")
    return value


def _validate_optional_non_negative_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int(field_name, value)
