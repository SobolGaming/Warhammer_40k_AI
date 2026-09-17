from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.core_ability_family import (
    CoreAbilityFamily,
    normalize_core_ability_family,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
        DatasheetAbilityDescriptorPayload,
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
    core_family: CoreAbilityFamily | None = field(init=False)

    def __post_init__(self) -> None:
        from warhammer40k_core.core.datasheet import (
            CatalogAbilitySourceKind,
            CatalogAbilitySupport,
            DatasheetCatalogError,
            _validate_identifier,
            _validate_identifier_tuple,
            _validate_json_object,
            _validate_json_object_tuple,
            _validate_optional_identifier,
            _validate_unprefixed_identifier,
            catalog_ability_source_kind_from_token,
            catalog_ability_support_from_token,
        )

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
            "core_family",
            normalize_core_ability_family(ability_id=self.ability_id, name=self.name),
        )
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
        from warhammer40k_core.core.datasheet import (
            catalog_ability_source_kind_from_token,
            catalog_ability_support_from_token,
        )

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
