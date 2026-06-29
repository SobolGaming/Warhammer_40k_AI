from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
    CharacteristicValuePayload,
    characteristic_from_token,
)
from warhammer40k_core.core.content_scope import (
    CatalogContentScope,
    CatalogContentScopeError,
    catalog_content_scope_from_token,
)


class DatasheetCatalogError(ValueError):
    """Raised when datasheet catalog data violates CORE V2 invariants."""


class BaseSizeKind(StrEnum):
    CIRCULAR = "circular"
    OVAL = "oval"
    RECTANGULAR = "rectangular"


class CatalogAbilitySupport(StrEnum):
    DESCRIPTOR_ONLY = "descriptor_only"
    GENERIC_RULE_IR = "generic_rule_ir"
    UNSUPPORTED = "unsupported"


class CatalogAbilitySourceKind(StrEnum):
    CORE = "core"
    FACTION = "faction"
    DATASHEET = "datasheet"
    WARGEAR = "wargear"


class DamagedEffectKind(StrEnum):
    HIT_ROLL_MODIFIER = "hit_roll_modifier"
    OBJECTIVE_CONTROL_MODIFIER = "objective_control_modifier"
    WEAPON_ATTACKS_MODIFIER = "weapon_attacks_modifier"
    WEAPON_ATTACKS_HALVE = "weapon_attacks_halve"
    SHOOTING_WEAPON_SELECTION_LIMIT = "shooting_weapon_selection_limit"
    ABILITY_SELECTION_LIMIT = "ability_selection_limit"


class DamagedWeaponScope(StrEnum):
    ALL = "all"
    MELEE = "melee"
    NAMED = "named"


class WargearOptionConditionKind(StrEnum):
    MODEL_NOT_EQUIPPED_WITH = "model_not_equipped_with"


class WargearOptionEffectKind(StrEnum):
    ADD_WARGEAR = "add_wargear"


class AttachmentRole(StrEnum):
    LEADER = "leader"
    SUPPORT = "support"


CatalogParameterValue = int | float | str | bool
type CatalogJsonValue = None | bool | int | float | str | list[CatalogJsonValue] | CatalogJsonObject
type CatalogJsonObject = dict[str, CatalogJsonValue]

REQUIRED_MODEL_CHARACTERISTICS = frozenset(
    {
        Characteristic.MOVEMENT,
        Characteristic.TOUGHNESS,
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
        Characteristic.WOUNDS,
        Characteristic.LEADERSHIP,
        Characteristic.OBJECTIVE_CONTROL,
        Characteristic.WEAPON_SKILL,
        Characteristic.BALLISTIC_SKILL,
    }
)
MUSTERING_WARLORD_RULE_KEY = "mustering_warlord"
MUSTERING_WARLORD_REQUIRED = "required"
MUSTERING_WARLORD_FORBIDDEN = "forbidden"


class BaseSizeDefinitionPayload(TypedDict):
    kind: str
    diameter_mm: float | None
    length_mm: float | None
    width_mm: float | None


class ModelProfileDefinitionPayload(TypedDict):
    model_profile_id: str
    name: str
    characteristics: list[CharacteristicValuePayload]
    base_size: BaseSizeDefinitionPayload
    source_ids: list[str]


class UnitCompositionDefinitionPayload(TypedDict):
    model_profile_id: str
    min_models: int
    max_models: int


class DatasheetKeywordSetPayload(TypedDict):
    keywords: list[str]
    faction_keywords: list[str]


class DatasheetWargearOptionConditionPayload(TypedDict):
    kind: str
    wargear_ids: list[str]


class DatasheetWargearOptionEffectPayload(TypedDict):
    kind: str
    wargear_id: str
    model_count: int
    wargear_count: int


class DatasheetWargearOptionPayload(TypedDict):
    option_id: str
    model_profile_id: str
    default_wargear_ids: list[str]
    allowed_wargear_ids: list[str]
    min_selections: int
    max_selections: int
    source_ids: list[str]
    conditions: NotRequired[list[DatasheetWargearOptionConditionPayload]]
    effects: NotRequired[list[DatasheetWargearOptionEffectPayload]]


class DatasheetAbilityDescriptorPayload(TypedDict):
    ability_id: str
    name: str
    source_id: str
    support: str
    source_kind: str
    effect_description: str
    source_wargear_id: str | None
    rule_ir_payload: CatalogJsonObject | None
    rule_ir_diagnostics: list[CatalogJsonObject]
    timing_tags: list[str]
    parameter_tokens: list[str]


class DamagedEffectDefinitionPayload(TypedDict):
    damaged_effect_id: str
    model_profile_id: str | None
    wounds_min: int
    wounds_max: int
    effect_kind: str
    modifier: int | None
    weapon_scope: str | None
    weapon_names: list[str]
    max_selections: int | None
    baseline_max_selections: int | None
    selection_group: str | None
    source_id: str


class AttachmentEligibilityPayload(TypedDict):
    role: str
    allowed_bodyguard_datasheet_ids: list[str]
    source_id: str


class DatasheetDefinitionPayload(TypedDict):
    datasheet_id: str
    name: str
    content_scope: str
    keywords: DatasheetKeywordSetPayload
    model_profiles: list[ModelProfileDefinitionPayload]
    composition: list[UnitCompositionDefinitionPayload]
    wargear_options: list[DatasheetWargearOptionPayload]
    abilities: list[DatasheetAbilityDescriptorPayload]
    damaged_effects: list[DamagedEffectDefinitionPayload]
    attachment_eligibilities: list[AttachmentEligibilityPayload]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class BaseSizeDefinition:
    kind: BaseSizeKind
    diameter_mm: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None

    def __post_init__(self) -> None:
        kind = base_size_kind_from_token(self.kind)
        object.__setattr__(self, "kind", kind)

        if kind is BaseSizeKind.CIRCULAR:
            diameter_mm = _validate_positive_number(
                "BaseSizeDefinition diameter_mm",
                self.diameter_mm,
            )
            if self.length_mm is not None or self.width_mm is not None:
                raise DatasheetCatalogError(
                    "Circular BaseSizeDefinition must include only diameter_mm."
                )
            object.__setattr__(self, "diameter_mm", diameter_mm)
            return

        if self.diameter_mm is not None:
            raise DatasheetCatalogError(
                "Non-circular BaseSizeDefinition must not include diameter_mm."
            )
        length_mm = _validate_positive_number("BaseSizeDefinition length_mm", self.length_mm)
        width_mm = _validate_positive_number("BaseSizeDefinition width_mm", self.width_mm)
        if kind is BaseSizeKind.OVAL and length_mm < width_mm:
            raise DatasheetCatalogError("Oval BaseSizeDefinition length must be at least width.")
        object.__setattr__(self, "length_mm", length_mm)
        object.__setattr__(self, "width_mm", width_mm)

    @classmethod
    def circular(cls, diameter_mm: float) -> Self:
        return cls(kind=BaseSizeKind.CIRCULAR, diameter_mm=diameter_mm)

    @classmethod
    def oval(cls, *, length_mm: float, width_mm: float) -> Self:
        return cls(kind=BaseSizeKind.OVAL, length_mm=length_mm, width_mm=width_mm)

    @classmethod
    def rectangular(cls, *, length_mm: float, width_mm: float) -> Self:
        return cls(kind=BaseSizeKind.RECTANGULAR, length_mm=length_mm, width_mm=width_mm)

    def to_payload(self) -> BaseSizeDefinitionPayload:
        return {
            "kind": self.kind.value,
            "diameter_mm": self.diameter_mm,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
        }

    @classmethod
    def from_payload(cls, payload: BaseSizeDefinitionPayload) -> Self:
        return cls(
            kind=base_size_kind_from_token(payload["kind"]),
            diameter_mm=payload["diameter_mm"],
            length_mm=payload["length_mm"],
            width_mm=payload["width_mm"],
        )


@dataclass(frozen=True, slots=True)
class ModelProfileDefinition:
    model_profile_id: str
    name: str
    characteristics: tuple[CharacteristicValue, ...]
    base_size: BaseSizeDefinition
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_unprefixed_identifier(
                "ModelProfileDefinition model_profile_id",
                self.model_profile_id,
                "model-profile:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ModelProfileDefinition name", self.name),
        )
        characteristics = _canonical_characteristic_values(self.characteristics)
        if not characteristics:
            raise DatasheetCatalogError("ModelProfileDefinition characteristics must not be empty.")
        _validate_required_model_characteristics(characteristics)
        object.__setattr__(self, "characteristics", characteristics)
        if type(self.base_size) is not BaseSizeDefinition:
            raise DatasheetCatalogError(
                "ModelProfileDefinition base_size must be a BaseSizeDefinition."
            )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("ModelProfileDefinition source_ids", self.source_ids),
        )

    def characteristic(self, characteristic: Characteristic) -> CharacteristicValue:
        requested_characteristic = _characteristic_from_token(characteristic)
        for value in self.characteristics:
            if value.characteristic is requested_characteristic:
                return value
        raise DatasheetCatalogError("ModelProfileDefinition characteristic was not found.")

    def to_payload(self) -> ModelProfileDefinitionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "name": self.name,
            "characteristics": [value.to_payload() for value in self.characteristics],
            "base_size": self.base_size.to_payload(),
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModelProfileDefinitionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            name=payload["name"],
            characteristics=tuple(
                _characteristic_value_from_payload(value) for value in payload["characteristics"]
            ),
            base_size=BaseSizeDefinition.from_payload(payload["base_size"]),
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitCompositionDefinition:
    model_profile_id: str
    min_models: int
    max_models: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier(
                "UnitCompositionDefinition model_profile_id", self.model_profile_id
            ),
        )
        min_models = _validate_positive_int("UnitCompositionDefinition min_models", self.min_models)
        max_models = _validate_positive_int("UnitCompositionDefinition max_models", self.max_models)
        if max_models < min_models:
            raise DatasheetCatalogError(
                "UnitCompositionDefinition max_models must be at least min_models."
            )
        object.__setattr__(self, "min_models", min_models)
        object.__setattr__(self, "max_models", max_models)

    def to_payload(self) -> UnitCompositionDefinitionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "min_models": self.min_models,
            "max_models": self.max_models,
        }

    @classmethod
    def from_payload(cls, payload: UnitCompositionDefinitionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            min_models=payload["min_models"],
            max_models=payload["max_models"],
        )


@dataclass(frozen=True, slots=True)
class DatasheetKeywordSet:
    keywords: tuple[str, ...] = ()
    faction_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "keywords",
            _validate_identifier_tuple("DatasheetKeywordSet keywords", self.keywords),
        )
        object.__setattr__(
            self,
            "faction_keywords",
            _validate_identifier_tuple(
                "DatasheetKeywordSet faction_keywords",
                self.faction_keywords,
            ),
        )

    def to_payload(self) -> DatasheetKeywordSetPayload:
        return {
            "keywords": list(self.keywords),
            "faction_keywords": list(self.faction_keywords),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetKeywordSetPayload) -> Self:
        return cls(
            keywords=tuple(payload["keywords"]),
            faction_keywords=tuple(payload["faction_keywords"]),
        )


@dataclass(frozen=True, slots=True)
class DatasheetWargearOptionCondition:
    kind: WargearOptionConditionKind
    wargear_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", wargear_option_condition_kind_from_token(self.kind))
        object.__setattr__(
            self,
            "wargear_ids",
            _validate_identifier_tuple(
                "DatasheetWargearOptionCondition wargear_ids",
                self.wargear_ids,
                min_length=1,
            ),
        )

    def to_payload(self) -> DatasheetWargearOptionConditionPayload:
        return {
            "kind": self.kind.value,
            "wargear_ids": list(self.wargear_ids),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetWargearOptionConditionPayload) -> Self:
        return cls(
            kind=wargear_option_condition_kind_from_token(payload["kind"]),
            wargear_ids=tuple(payload["wargear_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DatasheetWargearOptionEffect:
    kind: WargearOptionEffectKind
    wargear_id: str
    model_count: int
    wargear_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", wargear_option_effect_kind_from_token(self.kind))
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("DatasheetWargearOptionEffect wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "model_count",
            _validate_positive_int("DatasheetWargearOptionEffect model_count", self.model_count),
        )
        object.__setattr__(
            self,
            "wargear_count",
            _validate_positive_int(
                "DatasheetWargearOptionEffect wargear_count",
                self.wargear_count,
            ),
        )

    def to_payload(self) -> DatasheetWargearOptionEffectPayload:
        return {
            "kind": self.kind.value,
            "wargear_id": self.wargear_id,
            "model_count": self.model_count,
            "wargear_count": self.wargear_count,
        }

    @classmethod
    def from_payload(cls, payload: DatasheetWargearOptionEffectPayload) -> Self:
        return cls(
            kind=wargear_option_effect_kind_from_token(payload["kind"]),
            wargear_id=payload["wargear_id"],
            model_count=payload["model_count"],
            wargear_count=payload["wargear_count"],
        )


@dataclass(frozen=True, slots=True)
class DatasheetWargearOption:
    option_id: str
    model_profile_id: str
    default_wargear_ids: tuple[str, ...]
    allowed_wargear_ids: tuple[str, ...]
    min_selections: int = 0
    max_selections: int = 1
    source_ids: tuple[str, ...] = ()
    conditions: tuple[DatasheetWargearOptionCondition, ...] = ()
    effects: tuple[DatasheetWargearOptionEffect, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_unprefixed_identifier(
                "DatasheetWargearOption option_id",
                self.option_id,
                "wargear-option:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("DatasheetWargearOption model_profile_id", self.model_profile_id),
        )
        default_wargear_ids = _validate_identifier_tuple(
            "DatasheetWargearOption default_wargear_ids",
            self.default_wargear_ids,
        )
        allowed_wargear_ids = _validate_identifier_tuple(
            "DatasheetWargearOption allowed_wargear_ids",
            self.allowed_wargear_ids,
        )
        if not allowed_wargear_ids:
            raise DatasheetCatalogError(
                "DatasheetWargearOption allowed_wargear_ids must not be empty."
            )
        allowed_set = set(allowed_wargear_ids)
        for wargear_id in default_wargear_ids:
            if wargear_id not in allowed_set:
                raise DatasheetCatalogError(
                    "DatasheetWargearOption default wargear must be allowed."
                )
        min_selections = _validate_non_negative_int(
            "DatasheetWargearOption min_selections",
            self.min_selections,
        )
        max_selections = _validate_positive_int(
            "DatasheetWargearOption max_selections",
            self.max_selections,
        )
        if max_selections < min_selections:
            raise DatasheetCatalogError(
                "DatasheetWargearOption max_selections must be at least min_selections."
            )
        if len(default_wargear_ids) > max_selections:
            raise DatasheetCatalogError(
                "DatasheetWargearOption default_wargear_ids must not exceed max_selections."
            )
        object.__setattr__(self, "default_wargear_ids", default_wargear_ids)
        object.__setattr__(self, "allowed_wargear_ids", allowed_wargear_ids)
        object.__setattr__(self, "min_selections", min_selections)
        object.__setattr__(self, "max_selections", max_selections)
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("DatasheetWargearOption source_ids", self.source_ids),
        )
        conditions = _validate_wargear_option_condition_tuple(
            "DatasheetWargearOption conditions",
            self.conditions,
        )
        effects = _validate_wargear_option_effect_tuple(
            "DatasheetWargearOption effects",
            self.effects,
        )
        for effect in effects:
            if effect.wargear_id not in allowed_set:
                raise DatasheetCatalogError(
                    "DatasheetWargearOption effects must reference allowed wargear."
                )
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "effects", effects)

    def to_payload(self) -> DatasheetWargearOptionPayload:
        return {
            "option_id": self.option_id,
            "model_profile_id": self.model_profile_id,
            "default_wargear_ids": list(self.default_wargear_ids),
            "allowed_wargear_ids": list(self.allowed_wargear_ids),
            "min_selections": self.min_selections,
            "max_selections": self.max_selections,
            "source_ids": list(self.source_ids),
            "conditions": [condition.to_payload() for condition in self.conditions],
            "effects": [effect.to_payload() for effect in self.effects],
        }

    @classmethod
    def from_payload(cls, payload: DatasheetWargearOptionPayload) -> Self:
        return cls(
            option_id=payload["option_id"],
            model_profile_id=payload["model_profile_id"],
            default_wargear_ids=tuple(payload["default_wargear_ids"]),
            allowed_wargear_ids=tuple(payload["allowed_wargear_ids"]),
            min_selections=payload["min_selections"],
            max_selections=payload["max_selections"],
            source_ids=tuple(payload["source_ids"]),
            conditions=tuple(
                DatasheetWargearOptionCondition.from_payload(condition)
                for condition in payload.get("conditions", [])
            ),
            effects=tuple(
                DatasheetWargearOptionEffect.from_payload(effect)
                for effect in payload.get("effects", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class DatasheetAbilityDescriptor:
    ability_id: str
    name: str
    source_id: str
    support: CatalogAbilitySupport
    source_kind: CatalogAbilitySourceKind
    effect_description: str
    timing_tags: tuple[str, ...] = ()
    parameter_tokens: tuple[str, ...] = ()
    source_wargear_id: str | None = None
    rule_ir_payload: CatalogJsonObject | None = None
    rule_ir_diagnostics: tuple[CatalogJsonObject, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_id",
            _validate_unprefixed_identifier(
                "DatasheetAbilityDescriptor ability_id",
                self.ability_id,
                "ability:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("DatasheetAbilityDescriptor name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DatasheetAbilityDescriptor source_id", self.source_id),
        )
        object.__setattr__(self, "support", catalog_ability_support_from_token(self.support))
        source_kind = catalog_ability_source_kind_from_token(self.source_kind)
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(
            self,
            "effect_description",
            _validate_identifier(
                "DatasheetAbilityDescriptor effect_description",
                self.effect_description,
            ),
        )
        source_wargear_id = _validate_optional_identifier(
            "DatasheetAbilityDescriptor source_wargear_id",
            self.source_wargear_id,
        )
        if source_kind is CatalogAbilitySourceKind.WARGEAR and source_wargear_id is None:
            raise DatasheetCatalogError(
                "Wargear DatasheetAbilityDescriptor requires source_wargear_id."
            )
        if source_kind is not CatalogAbilitySourceKind.WARGEAR and source_wargear_id is not None:
            raise DatasheetCatalogError(
                "Non-wargear DatasheetAbilityDescriptor must not include source_wargear_id."
            )
        object.__setattr__(self, "source_wargear_id", source_wargear_id)
        rule_ir_payload = (
            None
            if self.rule_ir_payload is None
            else _validate_json_object(
                "DatasheetAbilityDescriptor rule_ir_payload",
                self.rule_ir_payload,
            )
        )
        if self.support is CatalogAbilitySupport.GENERIC_RULE_IR and rule_ir_payload is None:
            raise DatasheetCatalogError(
                "generic_rule_ir DatasheetAbilityDescriptor requires rule_ir_payload."
            )
        object.__setattr__(self, "rule_ir_payload", rule_ir_payload)
        object.__setattr__(
            self,
            "rule_ir_diagnostics",
            _validate_json_object_tuple(
                "DatasheetAbilityDescriptor rule_ir_diagnostics",
                self.rule_ir_diagnostics,
            ),
        )
        object.__setattr__(
            self,
            "timing_tags",
            _validate_identifier_tuple(
                "DatasheetAbilityDescriptor timing_tags",
                self.timing_tags,
            ),
        )
        object.__setattr__(
            self,
            "parameter_tokens",
            _validate_identifier_tuple(
                "DatasheetAbilityDescriptor parameter_tokens",
                self.parameter_tokens,
            ),
        )

    def to_payload(self) -> DatasheetAbilityDescriptorPayload:
        return {
            "ability_id": self.ability_id,
            "name": self.name,
            "source_id": self.source_id,
            "support": self.support.value,
            "source_kind": self.source_kind.value,
            "effect_description": self.effect_description,
            "source_wargear_id": self.source_wargear_id,
            "rule_ir_payload": self.rule_ir_payload,
            "rule_ir_diagnostics": list(self.rule_ir_diagnostics),
            "timing_tags": list(self.timing_tags),
            "parameter_tokens": list(self.parameter_tokens),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetAbilityDescriptorPayload) -> Self:
        return cls(
            ability_id=payload["ability_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            support=catalog_ability_support_from_token(payload["support"]),
            source_kind=catalog_ability_source_kind_from_token(payload["source_kind"]),
            effect_description=payload["effect_description"],
            timing_tags=tuple(payload["timing_tags"]),
            parameter_tokens=tuple(payload["parameter_tokens"]),
            source_wargear_id=payload["source_wargear_id"],
            rule_ir_payload=payload["rule_ir_payload"],
            rule_ir_diagnostics=tuple(payload["rule_ir_diagnostics"]),
        )


@dataclass(frozen=True, slots=True)
class DamagedEffectDefinition:
    damaged_effect_id: str
    model_profile_id: str | None
    wounds_min: int
    wounds_max: int
    effect_kind: DamagedEffectKind
    source_id: str
    modifier: int | None = None
    weapon_scope: DamagedWeaponScope | None = None
    weapon_names: tuple[str, ...] = ()
    max_selections: int | None = None
    baseline_max_selections: int | None = None
    selection_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "damaged_effect_id",
            _validate_unprefixed_identifier(
                "DamagedEffectDefinition damaged_effect_id",
                self.damaged_effect_id,
                "damaged-effect:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_optional_identifier(
                "DamagedEffectDefinition model_profile_id",
                self.model_profile_id,
            ),
        )
        wounds_min = _validate_positive_int("DamagedEffectDefinition wounds_min", self.wounds_min)
        wounds_max = _validate_positive_int("DamagedEffectDefinition wounds_max", self.wounds_max)
        if wounds_max < wounds_min:
            raise DatasheetCatalogError(
                "DamagedEffectDefinition wounds_max must be at least wounds_min."
            )
        object.__setattr__(self, "wounds_min", wounds_min)
        object.__setattr__(self, "wounds_max", wounds_max)
        effect_kind = damaged_effect_kind_from_token(self.effect_kind)
        object.__setattr__(self, "effect_kind", effect_kind)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DamagedEffectDefinition source_id", self.source_id),
        )
        modifier = _validate_optional_int("DamagedEffectDefinition modifier", self.modifier)
        weapon_scope = (
            None
            if self.weapon_scope is None
            else damaged_weapon_scope_from_token(self.weapon_scope)
        )
        weapon_names = _validate_identifier_tuple(
            "DamagedEffectDefinition weapon_names",
            self.weapon_names,
        )
        max_selections = _validate_optional_positive_int(
            "DamagedEffectDefinition max_selections",
            self.max_selections,
        )
        baseline_max_selections = _validate_optional_positive_int(
            "DamagedEffectDefinition baseline_max_selections",
            self.baseline_max_selections,
        )
        selection_group = _validate_optional_identifier(
            "DamagedEffectDefinition selection_group",
            self.selection_group,
        )
        if effect_kind in {
            DamagedEffectKind.HIT_ROLL_MODIFIER,
            DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER,
        }:
            if modifier is None:
                raise DatasheetCatalogError(
                    "Damaged roll and Objective Control effects require a modifier."
                )
            if weapon_scope is not None or weapon_names:
                raise DatasheetCatalogError(
                    "Damaged roll and Objective Control effects must not include weapon scope."
                )
            if (
                max_selections is not None
                or baseline_max_selections is not None
                or selection_group is not None
            ):
                raise DatasheetCatalogError(
                    "Damaged roll and Objective Control effects must not include selection limits."
                )
        if effect_kind is DamagedEffectKind.WEAPON_ATTACKS_MODIFIER:
            if modifier is None:
                raise DatasheetCatalogError("Damaged weapon Attacks modifiers require a modifier.")
            _validate_damaged_weapon_scope(weapon_scope=weapon_scope, weapon_names=weapon_names)
            _validate_no_damaged_selection_limit(
                max_selections=max_selections,
                baseline_max_selections=baseline_max_selections,
                selection_group=selection_group,
            )
        if effect_kind is DamagedEffectKind.WEAPON_ATTACKS_HALVE:
            if modifier is not None:
                raise DatasheetCatalogError("Damaged weapon Attacks halving must not modify.")
            _validate_damaged_weapon_scope(weapon_scope=weapon_scope, weapon_names=weapon_names)
            _validate_no_damaged_selection_limit(
                max_selections=max_selections,
                baseline_max_selections=baseline_max_selections,
                selection_group=selection_group,
            )
        if effect_kind in {
            DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
            DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        }:
            if modifier is not None or weapon_scope is not None or weapon_names:
                raise DatasheetCatalogError(
                    "Damaged selection limits must not include characteristic modifiers."
                )
            if max_selections is None:
                raise DatasheetCatalogError("Damaged selection limits require max_selections.")
            if baseline_max_selections is None:
                raise DatasheetCatalogError(
                    "Damaged selection limits require baseline_max_selections."
                )
            if baseline_max_selections < max_selections:
                raise DatasheetCatalogError(
                    "Damaged selection limit baseline must be at least max_selections."
                )
            if selection_group is None:
                raise DatasheetCatalogError("Damaged selection limits require selection_group.")
        object.__setattr__(self, "modifier", modifier)
        object.__setattr__(self, "weapon_scope", weapon_scope)
        object.__setattr__(self, "weapon_names", weapon_names)
        object.__setattr__(self, "max_selections", max_selections)
        object.__setattr__(self, "baseline_max_selections", baseline_max_selections)
        object.__setattr__(self, "selection_group", selection_group)

    def applies_to_wounds(self, wounds_remaining: int) -> bool:
        wounds = _validate_non_negative_int("wounds_remaining", wounds_remaining)
        return self.wounds_min <= wounds <= self.wounds_max

    def to_payload(self) -> DamagedEffectDefinitionPayload:
        return {
            "damaged_effect_id": self.damaged_effect_id,
            "model_profile_id": self.model_profile_id,
            "wounds_min": self.wounds_min,
            "wounds_max": self.wounds_max,
            "effect_kind": self.effect_kind.value,
            "modifier": self.modifier,
            "weapon_scope": None if self.weapon_scope is None else self.weapon_scope.value,
            "weapon_names": list(self.weapon_names),
            "max_selections": self.max_selections,
            "baseline_max_selections": self.baseline_max_selections,
            "selection_group": self.selection_group,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DamagedEffectDefinitionPayload) -> Self:
        return cls(
            damaged_effect_id=payload["damaged_effect_id"],
            model_profile_id=payload["model_profile_id"],
            wounds_min=payload["wounds_min"],
            wounds_max=payload["wounds_max"],
            effect_kind=damaged_effect_kind_from_token(payload["effect_kind"]),
            modifier=payload["modifier"],
            weapon_scope=damaged_weapon_scope_from_token(payload["weapon_scope"]),
            weapon_names=tuple(payload["weapon_names"]),
            max_selections=payload["max_selections"],
            baseline_max_selections=payload["baseline_max_selections"],
            selection_group=payload["selection_group"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class AttachmentEligibility:
    role: AttachmentRole
    allowed_bodyguard_datasheet_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", attachment_role_from_token(self.role))
        object.__setattr__(
            self,
            "allowed_bodyguard_datasheet_ids",
            _validate_identifier_tuple(
                "AttachmentEligibility allowed_bodyguard_datasheet_ids",
                self.allowed_bodyguard_datasheet_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AttachmentEligibility source_id", self.source_id),
        )

    def to_payload(self) -> AttachmentEligibilityPayload:
        return {
            "role": self.role.value,
            "allowed_bodyguard_datasheet_ids": list(self.allowed_bodyguard_datasheet_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: AttachmentEligibilityPayload) -> Self:
        return cls(
            role=attachment_role_from_token(payload["role"]),
            allowed_bodyguard_datasheet_ids=tuple(payload["allowed_bodyguard_datasheet_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class DatasheetDefinition:
    datasheet_id: str
    name: str
    content_scope: CatalogContentScope
    keywords: DatasheetKeywordSet
    model_profiles: tuple[ModelProfileDefinition, ...]
    composition: tuple[UnitCompositionDefinition, ...]
    wargear_options: tuple[DatasheetWargearOption, ...] = ()
    abilities: tuple[DatasheetAbilityDescriptor, ...] = ()
    damaged_effects: tuple[DamagedEffectDefinition, ...] = ()
    attachment_eligibilities: tuple[AttachmentEligibility, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "DatasheetDefinition datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("DatasheetDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "content_scope",
            _catalog_content_scope_from_token(
                "DatasheetDefinition content_scope",
                self.content_scope,
            ),
        )
        if type(self.keywords) is not DatasheetKeywordSet:
            raise DatasheetCatalogError("DatasheetDefinition keywords must be a keyword set.")
        model_profiles = _validate_model_profile_tuple(
            "DatasheetDefinition model_profiles",
            self.model_profiles,
        )
        composition = _validate_composition_tuple(
            "DatasheetDefinition composition",
            self.composition,
        )
        model_profile_ids = {profile.model_profile_id for profile in model_profiles}
        for composition_part in composition:
            if composition_part.model_profile_id not in model_profile_ids:
                raise DatasheetCatalogError(
                    "DatasheetDefinition composition references an unknown model profile."
                )
        wargear_options = _validate_wargear_option_tuple(
            "DatasheetDefinition wargear_options",
            self.wargear_options,
        )
        for option in wargear_options:
            if option.model_profile_id not in model_profile_ids:
                raise DatasheetCatalogError(
                    "DatasheetDefinition wargear option references an unknown model profile."
                )
        abilities = _validate_ability_descriptor_tuple(
            "DatasheetDefinition abilities",
            self.abilities,
        )
        damaged_effects = _validate_damaged_effect_tuple(
            "DatasheetDefinition damaged_effects",
            self.damaged_effects,
        )
        for damaged_effect in damaged_effects:
            if (
                damaged_effect.model_profile_id is not None
                and damaged_effect.model_profile_id not in model_profile_ids
            ):
                raise DatasheetCatalogError(
                    "DatasheetDefinition damaged effect references an unknown model profile."
                )
        attachment_eligibilities = _validate_attachment_eligibility_tuple(
            "DatasheetDefinition attachment_eligibilities",
            self.attachment_eligibilities,
        )
        object.__setattr__(
            self,
            "model_profiles",
            tuple(sorted(model_profiles, key=lambda profile: profile.model_profile_id)),
        )
        object.__setattr__(
            self,
            "composition",
            tuple(sorted(composition, key=lambda value: value.model_profile_id)),
        )
        object.__setattr__(
            self,
            "wargear_options",
            tuple(sorted(wargear_options, key=lambda option: option.option_id)),
        )
        object.__setattr__(
            self,
            "abilities",
            tuple(sorted(abilities, key=lambda ability: ability.ability_id)),
        )
        object.__setattr__(
            self,
            "damaged_effects",
            tuple(sorted(damaged_effects, key=lambda effect: effect.damaged_effect_id)),
        )
        object.__setattr__(
            self,
            "attachment_eligibilities",
            tuple(
                sorted(
                    attachment_eligibilities,
                    key=lambda eligibility: eligibility.source_id,
                )
            ),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("DatasheetDefinition source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"datasheet:{self.datasheet_id}"

    def model_profile_by_id(self, model_profile_id: str) -> ModelProfileDefinition:
        requested_id = _validate_identifier("model_profile_id", model_profile_id)
        for model_profile in self.model_profiles:
            if model_profile.model_profile_id == requested_id:
                return model_profile
        raise DatasheetCatalogError("DatasheetDefinition model_profile_id was not found.")

    def to_payload(self) -> DatasheetDefinitionPayload:
        return {
            "datasheet_id": self.datasheet_id,
            "name": self.name,
            "content_scope": self.content_scope.value,
            "keywords": self.keywords.to_payload(),
            "model_profiles": [profile.to_payload() for profile in self.model_profiles],
            "composition": [part.to_payload() for part in self.composition],
            "wargear_options": [option.to_payload() for option in self.wargear_options],
            "abilities": [ability.to_payload() for ability in self.abilities],
            "damaged_effects": [effect.to_payload() for effect in self.damaged_effects],
            "attachment_eligibilities": [
                eligibility.to_payload() for eligibility in self.attachment_eligibilities
            ],
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetDefinitionPayload) -> Self:
        return cls(
            datasheet_id=payload["datasheet_id"],
            name=payload["name"],
            content_scope=catalog_content_scope_from_token(payload["content_scope"]),
            keywords=DatasheetKeywordSet.from_payload(payload["keywords"]),
            model_profiles=tuple(
                ModelProfileDefinition.from_payload(profile)
                for profile in payload["model_profiles"]
            ),
            composition=tuple(
                UnitCompositionDefinition.from_payload(part) for part in payload["composition"]
            ),
            wargear_options=tuple(
                DatasheetWargearOption.from_payload(option) for option in payload["wargear_options"]
            ),
            abilities=tuple(
                DatasheetAbilityDescriptor.from_payload(ability) for ability in payload["abilities"]
            ),
            damaged_effects=tuple(
                DamagedEffectDefinition.from_payload(effect)
                for effect in payload["damaged_effects"]
            ),
            attachment_eligibilities=tuple(
                AttachmentEligibility.from_payload(eligibility)
                for eligibility in payload["attachment_eligibilities"]
            ),
            source_ids=tuple(payload["source_ids"]),
        )


def base_size_kind_from_token(token: object) -> BaseSizeKind:
    if type(token) is BaseSizeKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("BaseSizeKind token must be a string.")
    try:
        return BaseSizeKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported BaseSizeKind token: {token}.") from exc


def catalog_ability_support_from_token(token: object) -> CatalogAbilitySupport:
    if type(token) is CatalogAbilitySupport:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("CatalogAbilitySupport token must be a string.")
    try:
        return CatalogAbilitySupport(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported CatalogAbilitySupport token: {token}.") from exc


def catalog_ability_source_kind_from_token(token: object) -> CatalogAbilitySourceKind:
    if type(token) is CatalogAbilitySourceKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("CatalogAbilitySourceKind token must be a string.")
    try:
        return CatalogAbilitySourceKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(
            f"Unsupported CatalogAbilitySourceKind token: {token}."
        ) from exc


def damaged_effect_kind_from_token(token: object) -> DamagedEffectKind:
    if type(token) is DamagedEffectKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("DamagedEffectKind token must be a string.")
    try:
        return DamagedEffectKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported DamagedEffectKind token: {token}.") from exc


def damaged_weapon_scope_from_token(token: object | None) -> DamagedWeaponScope | None:
    if token is None:
        return None
    if type(token) is DamagedWeaponScope:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("DamagedWeaponScope token must be a string.")
    try:
        return DamagedWeaponScope(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported DamagedWeaponScope token: {token}.") from exc


def wargear_option_condition_kind_from_token(token: object) -> WargearOptionConditionKind:
    if type(token) is WargearOptionConditionKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("WargearOptionConditionKind token must be a string.")
    try:
        return WargearOptionConditionKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(
            f"Unsupported WargearOptionConditionKind token: {token}."
        ) from exc


def wargear_option_effect_kind_from_token(token: object) -> WargearOptionEffectKind:
    if type(token) is WargearOptionEffectKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("WargearOptionEffectKind token must be a string.")
    try:
        return WargearOptionEffectKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported WargearOptionEffectKind token: {token}.") from exc


def attachment_role_from_token(token: object) -> AttachmentRole:
    if type(token) is AttachmentRole:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("AttachmentRole token must be a string.")
    try:
        return AttachmentRole(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported AttachmentRole token: {token}.") from exc


def _catalog_content_scope_from_token(
    field_name: str,
    token: object,
) -> CatalogContentScope:
    try:
        return catalog_content_scope_from_token(token)
    except CatalogContentScopeError as exc:
        raise DatasheetCatalogError(f"{field_name} is invalid.") from exc


def _characteristic_from_token(token: object) -> Characteristic:
    if type(token) is Characteristic:
        return token
    try:
        return characteristic_from_token(token)
    except CharacteristicError as exc:
        raise DatasheetCatalogError("Characteristic token is invalid.") from exc


def _characteristic_value_from_payload(payload: CharacteristicValuePayload) -> CharacteristicValue:
    try:
        return CharacteristicValue.from_payload(payload)
    except CharacteristicError as exc:
        raise DatasheetCatalogError("CharacteristicValue payload is invalid.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DatasheetCatalogError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise DatasheetCatalogError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise DatasheetCatalogError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_json_object(field_name: str, value: object) -> CatalogJsonObject:
    if type(value) is not dict:
        raise DatasheetCatalogError(f"{field_name} must be a JSON object.")
    validated: CatalogJsonObject = {}
    for raw_key, raw_value in cast(dict[object, object], value).items():
        key = _validate_identifier(f"{field_name} key", raw_key)
        if key in validated:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate keys.")
        validated[key] = _validate_json_value(f"{field_name}.{key}", raw_value)
    return validated


def _validate_json_value(field_name: str, value: object) -> CatalogJsonValue:
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is str:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise DatasheetCatalogError(f"{field_name} must be finite.")
        return value
    if type(value) is list:
        return [_validate_json_value(f"{field_name}[]", item) for item in cast(list[object], value)]
    if type(value) is dict:
        return _validate_json_object(field_name, cast(dict[object, object], value))
    raise DatasheetCatalogError(f"{field_name} must be JSON-safe.")


def _validate_json_object_tuple(
    field_name: str,
    values: tuple[CatalogJsonObject, ...],
) -> tuple[CatalogJsonObject, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    return tuple(_validate_json_object(field_name, value) for value in values)


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise DatasheetCatalogError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise DatasheetCatalogError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise DatasheetCatalogError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise DatasheetCatalogError(f"{field_name} must be an integer.")
    if value < 1:
        raise DatasheetCatalogError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise DatasheetCatalogError(f"{field_name} must be an integer.")
    if value < 0:
        raise DatasheetCatalogError(f"{field_name} must not be negative.")
    return value


def _validate_optional_int(field_name: str, value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise DatasheetCatalogError(f"{field_name} must be an integer.")
    return value


def _validate_optional_positive_int(field_name: str, value: object) -> int | None:
    integer = _validate_optional_int(field_name, value)
    if integer is None:
        return None
    if integer < 1:
        raise DatasheetCatalogError(f"{field_name} must be at least 1.")
    return integer


def _validate_damaged_weapon_scope(
    *,
    weapon_scope: DamagedWeaponScope | None,
    weapon_names: tuple[str, ...],
) -> None:
    if weapon_scope is None:
        raise DatasheetCatalogError("Damaged weapon Attacks effects require weapon scope.")
    if weapon_scope is DamagedWeaponScope.NAMED:
        if not weapon_names:
            raise DatasheetCatalogError(
                "Damaged named weapon Attacks effects require weapon_names."
            )
        return
    if weapon_names:
        raise DatasheetCatalogError(
            "Damaged non-named weapon Attacks effects must not include weapon_names."
        )


def _validate_no_damaged_selection_limit(
    *,
    max_selections: int | None,
    baseline_max_selections: int | None,
    selection_group: str | None,
) -> None:
    if (
        max_selections is not None
        or baseline_max_selections is not None
        or selection_group is not None
    ):
        raise DatasheetCatalogError(
            "Damaged weapon Attacks effects must not include selection limits."
        )


def _canonical_characteristic_values(
    values: tuple[CharacteristicValue, ...],
) -> tuple[CharacteristicValue, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError("ModelProfileDefinition characteristics must be a tuple.")
    seen: set[Characteristic] = set()
    validated: list[CharacteristicValue] = []
    for value in values:
        if type(value) is not CharacteristicValue:
            raise DatasheetCatalogError(
                "ModelProfileDefinition characteristics must be CharacteristicValue values."
            )
        if value.characteristic in seen:
            raise DatasheetCatalogError(
                "ModelProfileDefinition characteristics must not contain duplicates."
            )
        seen.add(value.characteristic)
        validated.append(value)
    return tuple(sorted(validated, key=lambda value: value.characteristic.value))


def _validate_required_model_characteristics(
    values: tuple[CharacteristicValue, ...],
) -> None:
    present = {value.characteristic for value in values}
    missing = tuple(
        sorted(
            REQUIRED_MODEL_CHARACTERISTICS.difference(present),
            key=lambda characteristic: characteristic.value,
        )
    )
    if missing:
        missing_tokens = ", ".join(characteristic.value for characteristic in missing)
        raise DatasheetCatalogError(
            f"ModelProfileDefinition missing required characteristics: {missing_tokens}."
        )


def _validate_model_profile_tuple(
    field_name: str,
    values: tuple[ModelProfileDefinition, ...],
) -> tuple[ModelProfileDefinition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[ModelProfileDefinition] = []
    for value in values:
        if type(value) is not ModelProfileDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain model profile definitions.")
        if value.model_profile_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(validated)


def _validate_composition_tuple(
    field_name: str,
    values: tuple[UnitCompositionDefinition, ...],
) -> tuple[UnitCompositionDefinition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[UnitCompositionDefinition] = []
    for value in values:
        if type(value) is not UnitCompositionDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain composition definitions.")
        if value.model_profile_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate model profiles.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(validated)


def _validate_wargear_option_tuple(
    field_name: str,
    values: tuple[DatasheetWargearOption, ...],
) -> tuple[DatasheetWargearOption, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DatasheetWargearOption] = []
    for value in values:
        if type(value) is not DatasheetWargearOption:
            raise DatasheetCatalogError(f"{field_name} must contain wargear option definitions.")
        if value.option_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate option IDs.")
        seen.add(value.option_id)
        validated.append(value)
    return tuple(validated)


def _validate_wargear_option_condition_tuple(
    field_name: str,
    values: tuple[DatasheetWargearOptionCondition, ...],
) -> tuple[DatasheetWargearOptionCondition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    validated: list[DatasheetWargearOptionCondition] = []
    for value in values:
        if type(value) is not DatasheetWargearOptionCondition:
            raise DatasheetCatalogError(f"{field_name} must contain condition values.")
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda condition: (condition.kind.value, condition.wargear_ids),
        )
    )


def _validate_wargear_option_effect_tuple(
    field_name: str,
    values: tuple[DatasheetWargearOptionEffect, ...],
) -> tuple[DatasheetWargearOptionEffect, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    validated: list[DatasheetWargearOptionEffect] = []
    for value in values:
        if type(value) is not DatasheetWargearOptionEffect:
            raise DatasheetCatalogError(f"{field_name} must contain effect values.")
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda effect: (
                effect.kind.value,
                effect.wargear_id,
                effect.model_count,
                effect.wargear_count,
            ),
        )
    )


def _validate_ability_descriptor_tuple(
    field_name: str,
    values: tuple[DatasheetAbilityDescriptor, ...],
) -> tuple[DatasheetAbilityDescriptor, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DatasheetAbilityDescriptor] = []
    for value in values:
        if type(value) is not DatasheetAbilityDescriptor:
            raise DatasheetCatalogError(f"{field_name} must contain ability descriptors.")
        if value.ability_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate ability IDs.")
        seen.add(value.ability_id)
        validated.append(value)
    return tuple(validated)


def _validate_damaged_effect_tuple(
    field_name: str,
    values: tuple[DamagedEffectDefinition, ...],
) -> tuple[DamagedEffectDefinition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DamagedEffectDefinition] = []
    for value in values:
        if type(value) is not DamagedEffectDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain damaged effect definitions.")
        if value.damaged_effect_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.damaged_effect_id)
        validated.append(value)
    return tuple(validated)


def _validate_attachment_eligibility_tuple(
    field_name: str,
    values: tuple[AttachmentEligibility, ...],
) -> tuple[AttachmentEligibility, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen_roles: set[AttachmentRole] = set()
    seen_sources: set[str] = set()
    validated: list[AttachmentEligibility] = []
    for value in values:
        if type(value) is not AttachmentEligibility:
            raise DatasheetCatalogError(f"{field_name} must contain attachment eligibility values.")
        if value.role in seen_roles:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate roles.")
        if value.source_id in seen_sources:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate source IDs.")
        seen_roles.add(value.role)
        seen_sources.add(value.source_id)
        validated.append(value)
    return tuple(validated)
