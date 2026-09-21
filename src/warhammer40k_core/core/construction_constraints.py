"""Source-neutral, closed roster constraint grammar; no faction records live here."""

from __future__ import annotations

from enum import StrEnum
from typing import Self, cast

import msgspec

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import CatalogJsonObject
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token


class ConstructionConstraintError(ValueError):
    """Construction data is malformed or cannot be evaluated faithfully."""


_identifier = IdentifierValidator(ConstructionConstraintError)


def _identifiers(values: tuple[str, ...], *, empty: bool = False, keywords: bool = False) -> None:
    if type(values) is not tuple or (not values and not empty):
        raise ConstructionConstraintError("Selector identifiers require a nonempty tuple.")
    if any(_identifier("selector identifier", value) != value for value in values):
        raise ConstructionConstraintError("Selector identifiers must be canonical.")
    if len(set(values)) != len(values):
        raise ConstructionConstraintError("Selector identifiers must be unique.")
    if keywords and any(canonical_keyword_token(value) != value for value in values):
        raise ConstructionConstraintError("Selector keywords must be canonical catalog tokens.")


class DatasheetUnitSelector(
    msgspec.Struct, frozen=True, tag="datasheet", forbid_unknown_fields=True
):
    datasheet_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifiers(self.datasheet_ids)


class KeywordUnitSelector(msgspec.Struct, frozen=True, tag="keywords", forbid_unknown_fields=True):
    """Conjunctive filters over effective unit and faction keyword membership.

    CHARACTER, EPIC HERO and BATTLELINE use these same canonical membership atoms.
    Empty all/none clauses impose no condition; empty any imposes no alternative.
    """

    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for values in (self.all_of, self.any_of, self.none_of):
            _identifiers(values, empty=True, keywords=True)
        if not (self.all_of or self.any_of or self.none_of):
            raise ConstructionConstraintError("Keyword selector must contain a predicate.")
        if set(self.all_of).intersection(self.none_of):
            raise ConstructionConstraintError("Keyword selector requires an excluded keyword.")


class CharacteristicComparison(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    EQUAL = "equal"


class ModelQuantifier(StrEnum):
    ANY = "any"
    ALL = "all"


class CharacteristicUnitSelector(
    msgspec.Struct, frozen=True, tag="characteristic", forbid_unknown_fields=True
):
    """Compare the selected models' roster characteristics, never an omitted profile."""

    characteristic: Characteristic
    comparison: CharacteristicComparison
    value: int
    models: ModelQuantifier

    def __post_init__(self) -> None:
        if type(self.characteristic) is not Characteristic or self.characteristic not in {
            Characteristic.MOVEMENT,
            Characteristic.TOUGHNESS,
            Characteristic.SAVE,
            Characteristic.WOUNDS,
            Characteristic.LEADERSHIP,
            Characteristic.OBJECTIVE_CONTROL,
        }:
            raise ConstructionConstraintError("Selector requires a supported model characteristic.")
        if type(self.comparison) is not CharacteristicComparison:
            raise ConstructionConstraintError("Selector comparison must be typed.")
        if type(self.models) is not ModelQuantifier:
            raise ConstructionConstraintError("Selector model quantifier must be explicit.")
        if type(self.value) is not int or self.value < 0:
            raise ConstructionConstraintError("Selector threshold must be a nonnegative integer.")


class AllUnitSelector(msgspec.Struct, frozen=True, tag="all", forbid_unknown_fields=True):
    selectors: tuple[UnitSelector, ...]

    def __post_init__(self) -> None:
        _validate_children(self.selectors)


class AnyUnitSelector(msgspec.Struct, frozen=True, tag="any", forbid_unknown_fields=True):
    selectors: tuple[UnitSelector, ...]

    def __post_init__(self) -> None:
        _validate_children(self.selectors)


class ExcludeUnitSelector(msgspec.Struct, frozen=True, tag="exclude", forbid_unknown_fields=True):
    selector: UnitSelector
    excluded: UnitSelector

    def __post_init__(self) -> None:
        _validate_unit_selector(self.selector)
        _validate_unit_selector(self.excluded)


type UnitSelector = (
    DatasheetUnitSelector
    | KeywordUnitSelector
    | CharacteristicUnitSelector
    | AllUnitSelector
    | AnyUnitSelector
    | ExcludeUnitSelector
)


def _validate_unit_selector(value: object) -> None:
    if type(value) not in (
        DatasheetUnitSelector,
        KeywordUnitSelector,
        CharacteristicUnitSelector,
        AllUnitSelector,
        AnyUnitSelector,
        ExcludeUnitSelector,
    ):
        raise ConstructionConstraintError("Unit constraints require a typed UnitSelector.")


def _validate_children(values: tuple[UnitSelector, ...]) -> None:
    if type(values) is not tuple or not values:
        raise ConstructionConstraintError("Composite selector requires nonempty typed children.")
    for value in values:
        _validate_unit_selector(value)


class DetachmentSelector(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """Closed canonical project-owned identity set with optional exclusions."""

    detachment_ids: tuple[str, ...]
    excluded_detachment_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifiers(self.detachment_ids)
        _identifiers(self.excluded_detachment_ids, empty=True)
        if not set(self.excluded_detachment_ids).issubset(self.detachment_ids):
            raise ConstructionConstraintError(
                "Detachment exclusions must belong to the closed set."
            )
        if not set(self.detachment_ids).difference(self.excluded_detachment_ids):
            raise ConstructionConstraintError("Detachment selector must retain an identity.")


class ConstructionConstraintKind(StrEnum):
    REQUIRED_UNIT = "required_unit"
    PROHIBITED_UNIT = "prohibited_unit"
    REQUIRED_OTHER_DETACHMENT = "required_other_detachment"
    PROHIBITED_OTHER_DETACHMENT = "prohibited_other_detachment"


class ConstructionConstraint(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    constraint_id: str
    source_id: str
    kind: ConstructionConstraintKind
    unit_selector: UnitSelector | None = None
    detachment_selector: DetachmentSelector | None = None

    def __post_init__(self) -> None:
        for field in (self.constraint_id, self.source_id):
            if _identifier("construction identity", field) != field:
                raise ConstructionConstraintError("Construction identities must be canonical.")
        if type(self.kind) is not ConstructionConstraintKind:
            raise ConstructionConstraintError("Construction constraint kind must be typed.")
        if self.kind in {
            ConstructionConstraintKind.REQUIRED_UNIT,
            ConstructionConstraintKind.PROHIBITED_UNIT,
        }:
            _validate_unit_selector(self.unit_selector)
            if self.detachment_selector is not None:
                raise ConstructionConstraintError("Unit constraints cannot select detachments.")
        elif (
            type(self.detachment_selector) is not DetachmentSelector
            or self.unit_selector is not None
        ):
            raise ConstructionConstraintError(
                "Other-detachment constraints require only a DetachmentSelector."
            )

    def to_payload(self) -> CatalogJsonObject:
        return cast(CatalogJsonObject, msgspec.to_builtins(self))

    @classmethod
    def from_payload(cls, payload: CatalogJsonObject) -> Self:
        try:
            return msgspec.convert(payload, type=cls, strict=True)
        except msgspec.ValidationError as exc:
            raise ConstructionConstraintError(
                "Construction constraint payload is invalid."
            ) from exc


def validate_construction_constraints(
    values: tuple[ConstructionConstraint, ...],
) -> tuple[ConstructionConstraint, ...]:
    if type(values) is not tuple or any(
        type(value) is not ConstructionConstraint for value in values
    ):
        raise ConstructionConstraintError("Construction constraints must be a typed tuple.")
    if len({value.constraint_id for value in values}) != len(values):
        raise ConstructionConstraintError(
            "Construction constraint IDs must be unique per detachment."
        )
    return tuple(sorted(values, key=lambda value: value.constraint_id))


def selector_datasheet_ids(selector: UnitSelector) -> frozenset[str]:
    if isinstance(selector, DatasheetUnitSelector):
        return frozenset(selector.datasheet_ids)
    if isinstance(selector, (AllUnitSelector, AnyUnitSelector)):
        return frozenset(
            identity for child in selector.selectors for identity in selector_datasheet_ids(child)
        )
    if isinstance(selector, ExcludeUnitSelector):
        return selector_datasheet_ids(selector.selector) | selector_datasheet_ids(selector.excluded)
    if type(selector) in (KeywordUnitSelector, CharacteristicUnitSelector):
        return frozenset()
    raise ConstructionConstraintError("Unsupported construction unit selector.")
