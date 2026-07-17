from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogError
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetMusteringOption,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    UnitCompositionDefinition,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.scaled_wargear_limits import (
    ScaledWargearSelection,
    validate_scaled_wargear_selections,
)
from warhammer40k_core.engine.structured_wargear_validation import (
    validate_replace_wargear_effect_count,
)
from warhammer40k_core.engine.wargear_bearer_assignment_validation import (
    validate_wargear_bearer_assignments,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    ModelProfileSelectionPayload,
    WargearSelection,
    WargearSelectionPayload,
)


class BattleSize(StrEnum):
    INCURSION = "incursion"
    STRIKE_FORCE = "strike_force"
    ONSLAUGHT = "onslaught"


DAEMONIC_PACT_FACTION_KEYWORD = "LEGIONES DAEMONICA"
DAEMONIC_PACT_BASE_FACTION_KEYWORDS = frozenset({"CHAOS KNIGHTS", "HERETIC ASTARTES"})
CHAOS_KNIGHTS_DREADBLADES_FACTION_KEYWORD = "CHAOS KNIGHTS"
CHAOS_KNIGHTS_DREADBLADES_ALLOWED_KEYWORDS = frozenset({"TITANIC", "WAR DOG"})
CULT_OF_DARK_GODS_REQUIRED_FACTION_KEYWORD = "HERETIC ASTARTES"
CULT_OF_DARK_GODS_ALLOWED_NAMES = frozenset(
    {
        "KHORNEBERZERKERS",
        "NOISEMARINES",
        "PLAGUEMARINES",
        "RUBRICMARINES",
    }
)
DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_FACTION_KEYWORD = "DRUKHARI"
DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_ALLY_KEYWORDS = frozenset({"HARLEQUINS", "ANHRATHE"})
FREEBLADES_REQUIRED_FACTION_KEYWORD = "IMPERIUM"
FREEBLADES_IMPERIAL_KNIGHTS_FACTION_KEYWORD = "IMPERIAL KNIGHTS"
FREEBLADES_ALLOWED_KEYWORDS = frozenset({"ARMIGER", "TITANIC"})
FORBIDDEN_DEFAULT_ARMY_FACTION_RULE_BY_KEYWORD = {
    "BLOOD LEGIONS": "Pact of Blood",
    "LEGIONS OF EXCESS": "Pact of Excess",
    "PLAGUE LEGIONS": "Pact of Decay",
    "SCINTILLATING LEGIONS": "Pact of Sorcery",
}
SHADOW_LEGION_FACTION_KEYWORD = "LEGIONES DAEMONICA"
SHADOW_LEGION_DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_HERETIC_ASTARTES_FACTION_KEYWORD = "HERETIC ASTARTES"
SHADOW_LEGION_DAMNED_KEYWORD = "DAMNED"
SHADOW_LEGION_ALLOWED_HERETIC_ASTARTES_NAMES = frozenset(
    {
        "CHAOSLORD",
        "CHAOSLORDINTERMINATORARMOUR",
        "CHAOSLORDWITHJUMPPACK",
        "CHAOSTERMINATORSQUAD",
        "CHOSEN",
        "DARKAPOSTLE",
        "HAVOCS",
        "LEGIONARIES",
        "MASTEROFPOSSESSION",
        "POSSESSED",
        "RAPTORS",
        "SORCERER",
        "SORCERERINTERMINATORARMOUR",
        "WARPTALONS",
    }
)


class BattleSizeMusteringPolicyPayload(TypedDict):
    battle_size: str
    points_limit: int
    battlefield_width_inches: float
    battlefield_depth_inches: float
    detachment_point_limit: int
    enhancement_limit: int
    unit_limit: int
    battleline_unit_limit: int


class MusteringOptionSelectionPayload(TypedDict):
    option_id: str


class DetachmentSelectionPayload(TypedDict):
    faction_id: str
    detachment_ids: list[str]
    enhancement_ids: list[str]
    stratagem_ids: list[str]


class UnitMusterSelectionPayload(TypedDict):
    unit_selection_id: str
    datasheet_id: str
    model_profile_selections: list[ModelProfileSelectionPayload]
    wargear_selections: list[WargearSelectionPayload]
    mustering_option_selections: list[MusteringOptionSelectionPayload]


class AttachmentDeclarationPayload(TypedDict):
    source_unit_selection_id: str
    bodyguard_unit_selection_id: str


@dataclass(frozen=True, slots=True)
class BattleSizeMusteringPolicy:
    battle_size: BattleSize
    points_limit: int
    battlefield_width_inches: float
    battlefield_depth_inches: float
    detachment_point_limit: int
    enhancement_limit: int
    unit_limit: int
    battleline_unit_limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "battle_size", battle_size_from_token(self.battle_size))
        object.__setattr__(
            self,
            "points_limit",
            _validate_positive_int("BattleSizeMusteringPolicy points_limit", self.points_limit),
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "BattleSizeMusteringPolicy battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "BattleSizeMusteringPolicy battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "detachment_point_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy detachment_point_limit",
                self.detachment_point_limit,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy enhancement_limit",
                self.enhancement_limit,
            ),
        )
        object.__setattr__(
            self,
            "unit_limit",
            _validate_positive_int("BattleSizeMusteringPolicy unit_limit", self.unit_limit),
        )
        object.__setattr__(
            self,
            "battleline_unit_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy battleline_unit_limit",
                self.battleline_unit_limit,
            ),
        )
        if self.battleline_unit_limit < self.unit_limit:
            raise ListValidationError(
                "BattleSizeMusteringPolicy battleline_unit_limit must be at least unit_limit."
            )

    @classmethod
    def incursion(cls) -> Self:
        return cls(
            battle_size=BattleSize.INCURSION,
            points_limit=1000,
            battlefield_width_inches=44.0,
            battlefield_depth_inches=30.0,
            detachment_point_limit=2,
            enhancement_limit=4,
            unit_limit=3,
            battleline_unit_limit=6,
        )

    @classmethod
    def strike_force(cls) -> Self:
        return cls(
            battle_size=BattleSize.STRIKE_FORCE,
            points_limit=2000,
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            detachment_point_limit=3,
            enhancement_limit=4,
            unit_limit=3,
            battleline_unit_limit=6,
        )

    @classmethod
    def onslaught(cls) -> Self:
        return cls(
            battle_size=BattleSize.ONSLAUGHT,
            points_limit=3000,
            battlefield_width_inches=90.0,
            battlefield_depth_inches=44.0,
            detachment_point_limit=4,
            enhancement_limit=4,
            unit_limit=3,
            battleline_unit_limit=6,
        )

    def to_payload(self) -> BattleSizeMusteringPolicyPayload:
        return {
            "battle_size": self.battle_size.value,
            "points_limit": self.points_limit,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "detachment_point_limit": self.detachment_point_limit,
            "enhancement_limit": self.enhancement_limit,
            "unit_limit": self.unit_limit,
            "battleline_unit_limit": self.battleline_unit_limit,
        }


@dataclass(frozen=True, slots=True)
class MusteringOptionSelection:
    option_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_unprefixed_identifier(
                "MusteringOptionSelection option_id",
                self.option_id,
                "mustering-option:",
            ),
        )

    def to_payload(self) -> MusteringOptionSelectionPayload:
        return {"option_id": self.option_id}

    @classmethod
    def from_payload(cls, payload: MusteringOptionSelectionPayload) -> Self:
        return cls(option_id=payload["option_id"])


@dataclass(frozen=True, slots=True)
class DetachmentSelection:
    faction_id: str
    detachment_ids: tuple[str, ...]
    enhancement_ids: tuple[str, ...] = ()
    stratagem_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_id",
            _validate_unprefixed_identifier(
                "DetachmentSelection faction_id",
                self.faction_id,
                "faction:",
            ),
        )
        object.__setattr__(
            self,
            "detachment_ids",
            _validate_unprefixed_identifier_tuple(
                "DetachmentSelection detachment_ids",
                self.detachment_ids,
                "detachment:",
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_ids",
            _validate_identifier_tuple(
                "DetachmentSelection enhancement_ids",
                self.enhancement_ids,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_ids",
            _validate_identifier_tuple(
                "DetachmentSelection stratagem_ids",
                self.stratagem_ids,
                min_length=0,
            ),
        )

    def to_payload(self) -> DetachmentSelectionPayload:
        return {
            "faction_id": self.faction_id,
            "detachment_ids": list(self.detachment_ids),
            "enhancement_ids": list(self.enhancement_ids),
            "stratagem_ids": list(self.stratagem_ids),
        }

    @classmethod
    def from_payload(cls, payload: DetachmentSelectionPayload) -> Self:
        return cls(
            faction_id=payload["faction_id"],
            detachment_ids=tuple(payload["detachment_ids"]),
            enhancement_ids=tuple(payload["enhancement_ids"]),
            stratagem_ids=tuple(payload["stratagem_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitMusterSelection:
    unit_selection_id: str
    datasheet_id: str
    model_profile_selections: tuple[ModelProfileSelection, ...]
    wargear_selections: tuple[WargearSelection, ...] = ()
    mustering_option_selections: tuple[MusteringOptionSelection, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_unprefixed_identifier(
                "UnitMusterSelection unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "UnitMusterSelection datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        model_profile_selections = _validate_model_profile_selection_tuple(
            "UnitMusterSelection model_profile_selections",
            self.model_profile_selections,
        )
        _validate_unique_model_profile_selections(model_profile_selections)
        wargear_selections = _validate_wargear_selection_tuple(
            "UnitMusterSelection wargear_selections",
            self.wargear_selections,
        )
        _validate_unique_wargear_selections(wargear_selections)
        mustering_option_selections = _validate_mustering_option_selection_tuple(
            "UnitMusterSelection mustering_option_selections",
            self.mustering_option_selections,
        )
        _validate_unique_mustering_option_selections(mustering_option_selections)
        object.__setattr__(self, "model_profile_selections", model_profile_selections)
        object.__setattr__(self, "wargear_selections", wargear_selections)
        object.__setattr__(
            self,
            "mustering_option_selections",
            mustering_option_selections,
        )

    def to_payload(self) -> UnitMusterSelectionPayload:
        return {
            "unit_selection_id": self.unit_selection_id,
            "datasheet_id": self.datasheet_id,
            "model_profile_selections": [
                selection.to_payload() for selection in self.model_profile_selections
            ],
            "wargear_selections": [selection.to_payload() for selection in self.wargear_selections],
            "mustering_option_selections": [
                selection.to_payload() for selection in self.mustering_option_selections
            ],
        }

    @classmethod
    def from_payload(cls, payload: UnitMusterSelectionPayload) -> Self:
        return cls(
            unit_selection_id=payload["unit_selection_id"],
            datasheet_id=payload["datasheet_id"],
            model_profile_selections=tuple(
                ModelProfileSelection.from_payload(selection)
                for selection in payload["model_profile_selections"]
            ),
            wargear_selections=tuple(
                WargearSelection.from_payload(selection)
                for selection in payload["wargear_selections"]
            ),
            mustering_option_selections=tuple(
                MusteringOptionSelection.from_payload(selection)
                for selection in payload["mustering_option_selections"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AttachmentDeclaration:
    source_unit_selection_id: str
    bodyguard_unit_selection_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_unit_selection_id",
            _validate_unprefixed_identifier(
                "AttachmentDeclaration source_unit_selection_id",
                self.source_unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_selection_id",
            _validate_unprefixed_identifier(
                "AttachmentDeclaration bodyguard_unit_selection_id",
                self.bodyguard_unit_selection_id,
                "unit-selection:",
            ),
        )
        if self.source_unit_selection_id == self.bodyguard_unit_selection_id:
            raise ListValidationError("AttachmentDeclaration cannot attach a unit to itself.")

    def to_payload(self) -> AttachmentDeclarationPayload:
        return {
            "source_unit_selection_id": self.source_unit_selection_id,
            "bodyguard_unit_selection_id": self.bodyguard_unit_selection_id,
        }

    @classmethod
    def from_payload(cls, payload: AttachmentDeclarationPayload) -> Self:
        return cls(
            source_unit_selection_id=payload["source_unit_selection_id"],
            bodyguard_unit_selection_id=payload["bodyguard_unit_selection_id"],
        )


def validate_detachment_selection(
    *,
    catalog: ArmyCatalog,
    selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> tuple[FactionDefinition, tuple[DetachmentDefinition, ...]]:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not DetachmentSelection:
        raise ListValidationError("selection must be a DetachmentSelection.")
    policy = battle_size_mustering_policy(battle_size)
    faction = _catalog_faction_by_id(catalog, selection.faction_id)
    _validate_army_faction_can_be_selected(faction)
    detachments = tuple(
        _catalog_detachment_by_id(catalog, detachment_id)
        for detachment_id in selection.detachment_ids
    )
    detachment_point_costs: list[int] = []
    for detachment in detachments:
        if detachment.faction_id != faction.faction_id:
            raise ListValidationError("DetachmentSelection detachment does not belong to faction.")
        if detachment.detachment_point_cost is None:
            raise ListValidationError(
                "DetachmentSelection detachment point cost is awaiting source."
            )
        detachment_point_costs.append(detachment.detachment_point_cost)
        if not detachment.unit_datasheet_ids:
            raise ListValidationError(
                "DetachmentSelection detachment unit grants are awaiting source."
            )
        if not detachment.force_disposition_ids:
            raise ListValidationError(
                "DetachmentSelection detachment force disposition is awaiting source."
            )
    total_detachment_points = sum(detachment_point_costs)
    if total_detachment_points > policy.detachment_point_limit:
        raise ListValidationError("DetachmentSelection exceeds battle size Detachment Points.")
    allowed_enhancement_ids = tuple(
        enhancement_id
        for detachment in detachments
        for enhancement_id in detachment.enhancement_ids
    )
    allowed_stratagem_ids = tuple(
        stratagem_id for detachment in detachments for stratagem_id in detachment.stratagem_ids
    )
    _validate_selected_ids_are_allowed(
        field_name="DetachmentSelection enhancement_ids",
        selected_ids=selection.enhancement_ids,
        allowed_ids=allowed_enhancement_ids,
    )
    _validate_selected_ids_are_allowed(
        field_name="DetachmentSelection stratagem_ids",
        selected_ids=selection.stratagem_ids,
        allowed_ids=allowed_stratagem_ids,
    )
    _validate_catalog_contains_enhancements(catalog, selection.enhancement_ids)
    _validate_catalog_contains_stratagems(catalog, selection.stratagem_ids)
    return faction, tuple(sorted(detachments, key=lambda detachment: detachment.detachment_id))


def selected_force_disposition_ids(
    *,
    catalog: ArmyCatalog,
    selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> tuple[str, ...]:
    _faction, detachments = validate_detachment_selection(
        catalog=catalog,
        selection=selection,
        battle_size=battle_size,
    )
    force_disposition_ids = {
        force_disposition_id
        for detachment in detachments
        for force_disposition_id in detachment.force_disposition_ids
    }
    return tuple(sorted(force_disposition_ids))


def validate_force_disposition_selection(
    *,
    catalog: ArmyCatalog,
    detachment_selection: DetachmentSelection,
    force_disposition_id: str,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> str:
    selected_id = _validate_unprefixed_identifier(
        "force_disposition_id",
        force_disposition_id,
        "force-disposition:",
    )
    available_ids = selected_force_disposition_ids(
        catalog=catalog,
        selection=detachment_selection,
        battle_size=battle_size,
    )
    if selected_id not in available_ids:
        raise ListValidationError(
            "Selected Force Disposition is not provided by the selected detachments."
        )
    return selected_id


def validate_unit_selection_for_faction(
    *,
    catalog: ArmyCatalog,
    selection: UnitMusterSelection,
    faction: FactionDefinition,
) -> DatasheetDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not UnitMusterSelection:
        raise ListValidationError("selection must be a UnitMusterSelection.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("faction must be a FactionDefinition.")
    datasheet = _catalog_datasheet_by_id(catalog, selection.datasheet_id)
    if not set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords):
        raise ListValidationError("UnitMusterSelection datasheet is not legal for faction.")
    return datasheet


def validate_unit_selection_for_army(
    *,
    catalog: ArmyCatalog,
    selection: UnitMusterSelection,
    faction: FactionDefinition,
    detachment_selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> DatasheetDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not UnitMusterSelection:
        raise ListValidationError("selection must be a UnitMusterSelection.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("faction must be a FactionDefinition.")
    datasheet = _catalog_datasheet_by_id(catalog, selection.datasheet_id)
    shares_selected_faction = bool(
        set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords)
    )
    daemonic_pact_allowed = daemonic_pact_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    )
    dreadblades_allowed = dreadblades_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    )
    cult_of_dark_gods_allowed = cult_of_dark_gods_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    )
    drukhari_corsairs_allowed = (
        drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
            datasheet=datasheet,
            faction=faction,
        )
    )
    freeblades_allowed = freeblades_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    )
    shadow_legion_thralls_allowed = shadow_legion_thralls_datasheet_has_faction_access(
        datasheet=datasheet,
        faction=faction,
        detachment_selection=detachment_selection,
    )
    if (
        not shares_selected_faction
        and not daemonic_pact_allowed
        and not dreadblades_allowed
        and not cult_of_dark_gods_allowed
        and not drukhari_corsairs_allowed
        and not freeblades_allowed
        and not shadow_legion_thralls_allowed
    ):
        raise ListValidationError("UnitMusterSelection datasheet is not legal for faction.")
    _selected_faction, detachments = validate_detachment_selection(
        catalog=catalog,
        selection=detachment_selection,
        battle_size=battle_size,
    )
    allowed_datasheet_ids = {
        datasheet_id for detachment in detachments for datasheet_id in detachment.unit_datasheet_ids
    }
    if (
        datasheet.datasheet_id not in allowed_datasheet_ids
        and not daemonic_pact_allowed
        and not dreadblades_allowed
        and not cult_of_dark_gods_allowed
        and not drukhari_corsairs_allowed
        and not freeblades_allowed
        and not shadow_legion_thralls_allowed
    ):
        raise ListValidationError(
            "UnitMusterSelection datasheet is not provided by selected detachments."
        )
    return datasheet


def daemonic_pact_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Daemonic Pact datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Daemonic Pact faction must be a FactionDefinition.")
    if not _datasheet_has_faction_keyword(datasheet, DAEMONIC_PACT_FACTION_KEYWORD):
        return False
    faction_keywords = {_canonical_keyword(keyword) for keyword in faction.faction_keywords}
    return bool(faction_keywords & DAEMONIC_PACT_BASE_FACTION_KEYWORDS)


def dreadblades_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Dreadblades datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Dreadblades faction must be a FactionDefinition.")
    if _faction_has_keyword(faction, CHAOS_KNIGHTS_DREADBLADES_FACTION_KEYWORD):
        return False
    if not _datasheet_has_faction_keyword(
        datasheet,
        CHAOS_KNIGHTS_DREADBLADES_FACTION_KEYWORD,
    ):
        return False
    return _datasheet_has_any_keyword(datasheet, CHAOS_KNIGHTS_DREADBLADES_ALLOWED_KEYWORDS)


def cult_of_dark_gods_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Cult of the Dark Gods datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Cult of the Dark Gods faction must be a FactionDefinition.")
    if not _faction_has_keyword(faction, CULT_OF_DARK_GODS_REQUIRED_FACTION_KEYWORD):
        return False
    if _datasheet_has_faction_keyword(datasheet, CULT_OF_DARK_GODS_REQUIRED_FACTION_KEYWORD):
        return False
    return _canonical_name(datasheet.name) in CULT_OF_DARK_GODS_ALLOWED_NAMES


def drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError(
            "Corsairs and Travelling Players datasheet must be a DatasheetDefinition."
        )
    if type(faction) is not FactionDefinition:
        raise ListValidationError(
            "Corsairs and Travelling Players faction must be a FactionDefinition."
        )
    if not _faction_has_keyword(
        faction,
        DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_FACTION_KEYWORD,
    ):
        return False
    if _datasheet_has_faction_keyword(
        datasheet,
        DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_FACTION_KEYWORD,
    ):
        return False
    return _datasheet_has_any_keyword(
        datasheet,
        DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_ALLY_KEYWORDS,
    )


def freeblades_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Freeblades datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Freeblades faction must be a FactionDefinition.")
    if not _faction_has_keyword(faction, FREEBLADES_REQUIRED_FACTION_KEYWORD):
        return False
    selected_faction_keywords = {
        _canonical_keyword(keyword) for keyword in faction.faction_keywords
    }
    datasheet_faction_keywords = {
        _canonical_keyword(keyword) for keyword in datasheet.keywords.faction_keywords
    }
    selected_non_imperium_faction_keywords = selected_faction_keywords - {
        _canonical_keyword(FREEBLADES_REQUIRED_FACTION_KEYWORD)
    }
    if selected_non_imperium_faction_keywords & datasheet_faction_keywords:
        return False
    if not _datasheet_has_faction_keyword(
        datasheet,
        FREEBLADES_IMPERIAL_KNIGHTS_FACTION_KEYWORD,
    ):
        return False
    return _datasheet_has_any_keyword(datasheet, FREEBLADES_ALLOWED_KEYWORDS)


def shadow_legion_thralls_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
    detachment_selection: DetachmentSelection,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Shadow Legion datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Shadow Legion faction must be a FactionDefinition.")
    if type(detachment_selection) is not DetachmentSelection:
        raise ListValidationError("Shadow Legion detachment selection is invalid.")
    if not _faction_has_keyword(faction, SHADOW_LEGION_FACTION_KEYWORD):
        return False
    if SHADOW_LEGION_DETACHMENT_ID not in detachment_selection.detachment_ids:
        return False
    if not _datasheet_has_faction_keyword(
        datasheet,
        SHADOW_LEGION_HERETIC_ASTARTES_FACTION_KEYWORD,
    ):
        return False
    return _shadow_legion_heretic_astartes_datasheet_allowed(datasheet)


def shadow_legion_thralls_datasheet_has_faction_access(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
    detachment_selection: DetachmentSelection,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Shadow Legion datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Shadow Legion faction must be a FactionDefinition.")
    if type(detachment_selection) is not DetachmentSelection:
        raise ListValidationError("Shadow Legion detachment selection is invalid.")
    if not _faction_has_keyword(faction, SHADOW_LEGION_FACTION_KEYWORD):
        return False
    if SHADOW_LEGION_DETACHMENT_ID not in detachment_selection.detachment_ids:
        return False
    return _datasheet_has_faction_keyword(
        datasheet,
        SHADOW_LEGION_HERETIC_ASTARTES_FACTION_KEYWORD,
    )


def _shadow_legion_heretic_astartes_datasheet_allowed(
    datasheet: DatasheetDefinition,
) -> bool:
    if _datasheet_has_any_keyword(datasheet, frozenset({SHADOW_LEGION_DAMNED_KEYWORD})):
        return True
    return _canonical_name(datasheet.name) in SHADOW_LEGION_ALLOWED_HERETIC_ASTARTES_NAMES


def resolve_model_profile_selections(
    *,
    datasheet: DatasheetDefinition,
    selections: tuple[ModelProfileSelection, ...],
) -> tuple[ModelProfileSelection, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("datasheet must be a DatasheetDefinition.")
    selections = _validate_model_profile_selection_tuple("model_profile_selections", selections)
    _validate_unique_model_profile_selections(selections)
    composition_by_profile = {part.model_profile_id: part for part in datasheet.composition}
    selection_by_profile = {selection.model_profile_id: selection for selection in selections}
    if not set(selection_by_profile).issubset(composition_by_profile) or any(
        part.min_models > 0 and part.model_profile_id not in selection_by_profile
        for part in datasheet.composition
    ):
        raise ListValidationError(
            "UnitMusterSelection model_profile_selections must match required composition."
        )
    for model_profile_id, selection in selection_by_profile.items():
        composition = composition_by_profile[model_profile_id]
        _validate_model_count_against_composition(selection, composition)
        datasheet.model_profile_by_id(model_profile_id)
    total_models = sum(selection.model_count for selection in selections)
    if total_models < 1:
        raise ListValidationError("UnitMusterSelection must include at least one model.")
    if datasheet.max_unit_models is not None and total_models > datasheet.max_unit_models:
        raise ListValidationError("UnitMusterSelection exceeds the datasheet unit-size maximum.")
    return tuple(sorted(selections, key=lambda selection: selection.model_profile_id))


def resolve_wargear_selections(
    *,
    catalog: ArmyCatalog,
    datasheet: DatasheetDefinition,
    requested_selections: tuple[WargearSelection, ...],
    model_profile_selections: tuple[ModelProfileSelection, ...] | None = None,
) -> tuple[WargearSelection, ...]:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("datasheet must be a DatasheetDefinition.")
    requested_selections = _validate_wargear_selection_tuple(
        "requested_selections",
        requested_selections,
    )
    _validate_unique_wargear_selections(requested_selections)
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    requested_by_id = {selection.option_id: selection for selection in requested_selections}
    unknown_requested = tuple(sorted(set(requested_by_id).difference(options_by_id)))
    if unknown_requested:
        raise ListValidationError("WargearSelection references an unknown datasheet option.")

    resolved: list[WargearSelection] = []
    for option in datasheet.wargear_options:
        selection = requested_by_id.get(option.option_id)
        if selection is None:
            selection = WargearSelection(
                option_id=option.option_id,
                model_profile_id=option.model_profile_id,
                wargear_ids=option.default_wargear_ids,
            )
        _validate_wargear_selection_against_option(selection, option)
        for wargear_id in selection.wargear_ids:
            _catalog_wargear_by_id(catalog, wargear_id)
        resolved.append(selection)
    resolved_tuple = tuple(sorted(resolved, key=lambda selection: selection.option_id))
    _validate_wargear_option_semantics(
        selections=resolved_tuple,
        datasheet=datasheet,
        model_profile_selections=model_profile_selections,
        requested_option_ids=frozenset(requested_by_id),
    )
    return resolved_tuple


def resolve_mustering_option_selections(
    *,
    datasheet: DatasheetDefinition,
    requested_selections: tuple[MusteringOptionSelection, ...],
) -> tuple[DatasheetMusteringOption, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("datasheet must be a DatasheetDefinition.")
    requested_selections = _validate_mustering_option_selection_tuple(
        "requested_selections",
        requested_selections,
    )
    _validate_unique_mustering_option_selections(requested_selections)
    options_by_id = {option.option_id: option for option in datasheet.mustering_options}
    requested_by_id = {selection.option_id: selection for selection in requested_selections}
    unknown_requested = tuple(sorted(set(requested_by_id).difference(options_by_id)))
    if unknown_requested:
        raise ListValidationError(
            "MusteringOptionSelection references an unknown datasheet option."
        )
    selected_options = tuple(
        options_by_id[selection.option_id] for selection in requested_selections
    )
    groups_by_id: dict[str, tuple[DatasheetMusteringOption, ...]] = {}
    for option in datasheet.mustering_options:
        group_options = groups_by_id.get(option.selection_group_id, ())
        groups_by_id[option.selection_group_id] = (*group_options, option)
    selected_by_group: dict[str, tuple[DatasheetMusteringOption, ...]] = {}
    for option in selected_options:
        group_options = selected_by_group.get(option.selection_group_id, ())
        selected_by_group[option.selection_group_id] = (*group_options, option)
    for selection_group_id, group_options in groups_by_id.items():
        selected = selected_by_group.get(selection_group_id, ())
        if len(selected) > 1:
            raise ListValidationError(
                "MusteringOptionSelection includes multiple options from one group."
            )
        if group_options[0].required and not selected:
            raise ListValidationError(
                "MusteringOptionSelection is missing a required option group."
            )
    return tuple(sorted(selected_options, key=lambda option: option.option_id))


def _catalog_datasheet_by_id(catalog: ArmyCatalog, datasheet_id: str) -> DatasheetDefinition:
    try:
        return catalog.datasheet_by_id(datasheet_id)
    except ArmyCatalogError as exc:
        raise ListValidationError("UnitMusterSelection datasheet_id was not found.") from exc


def _datasheet_has_faction_keyword(
    datasheet: DatasheetDefinition,
    keyword: str,
) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored) == canonical for stored in datasheet.keywords.faction_keywords
    )


def _datasheet_has_any_keyword(
    datasheet: DatasheetDefinition,
    keywords: frozenset[str],
) -> bool:
    requested_keywords = {_canonical_keyword(keyword) for keyword in keywords}
    stored_keywords = {
        _canonical_keyword(stored)
        for stored in (
            *datasheet.keywords.keywords,
            *datasheet.keywords.faction_keywords,
        )
    }
    return bool(requested_keywords & stored_keywords)


def _faction_has_keyword(
    faction: FactionDefinition,
    keyword: str,
) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in faction.faction_keywords)


def _validate_army_faction_can_be_selected(faction: FactionDefinition) -> None:
    faction_tokens = (
        faction.faction_id,
        faction.name,
        *faction.faction_keywords,
    )
    for token in faction_tokens:
        canonical = _canonical_keyword(token)
        rule_name = FORBIDDEN_DEFAULT_ARMY_FACTION_RULE_BY_KEYWORD.get(canonical)
        if rule_name is None:
            continue
        raise ListValidationError(
            f"{rule_name} forbids selecting {canonical} as Army Faction "
            "unless specifically stated otherwise."
        )


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _canonical_name(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _catalog_faction_by_id(catalog: ArmyCatalog, faction_id: str) -> FactionDefinition:
    try:
        return catalog.faction_by_id(faction_id)
    except ArmyCatalogError as exc:
        raise ListValidationError("DetachmentSelection faction_id was not found.") from exc


def _catalog_detachment_by_id(
    catalog: ArmyCatalog,
    detachment_id: str,
) -> DetachmentDefinition:
    requested_id = _validate_identifier("detachment_id", detachment_id)
    for detachment in catalog.detachments:
        if detachment.detachment_id == requested_id:
            return detachment
    raise ListValidationError("DetachmentSelection detachment_id was not found.")


def _catalog_wargear_by_id(catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier("wargear_id", wargear_id)
    for item in catalog.wargear:
        if item.wargear_id == requested_id:
            return item
    raise ListValidationError("WargearSelection wargear_id was not found in catalog.")


def _validate_catalog_contains_enhancements(
    catalog: ArmyCatalog,
    enhancement_ids: tuple[str, ...],
) -> None:
    catalog_ids = {enhancement.enhancement_id for enhancement in catalog.enhancements}
    for enhancement_id in enhancement_ids:
        if enhancement_id not in catalog_ids:
            raise ListValidationError("DetachmentSelection enhancement_id was not found.")


def _validate_catalog_contains_stratagems(
    catalog: ArmyCatalog,
    stratagem_ids: tuple[str, ...],
) -> None:
    catalog_ids = {stratagem.stratagem_id for stratagem in catalog.stratagems}
    for stratagem_id in stratagem_ids:
        if stratagem_id not in catalog_ids:
            raise ListValidationError("DetachmentSelection stratagem_id was not found.")


def _validate_selected_ids_are_allowed(
    *,
    field_name: str,
    selected_ids: tuple[str, ...],
    allowed_ids: tuple[str, ...],
) -> None:
    allowed = set(allowed_ids)
    for selected_id in selected_ids:
        if selected_id not in allowed:
            raise ListValidationError(f"{field_name} includes an ID not allowed by detachment.")


def _validate_model_count_against_composition(
    selection: ModelProfileSelection,
    composition: UnitCompositionDefinition,
) -> None:
    if selection.model_count < composition.min_models:
        raise ListValidationError("ModelProfileSelection model_count is below datasheet minimum.")
    if selection.model_count > composition.max_models:
        raise ListValidationError("ModelProfileSelection model_count exceeds datasheet maximum.")


def _validate_wargear_selection_against_option(
    selection: WargearSelection,
    option: DatasheetWargearOption,
) -> None:
    if selection.model_profile_id != option.model_profile_id:
        raise ListValidationError("WargearSelection model_profile_id does not match option.")
    selected_count = len(selection.wargear_ids)
    if selected_count < option.min_selections:
        raise ListValidationError("WargearSelection does not satisfy minimum selections.")
    if selected_count > option.max_selections:
        raise ListValidationError("WargearSelection exceeds maximum selections.")
    if selection.resolved_selection_count > 1 and option.selection_limit is None:
        raise ListValidationError(
            "WargearSelection selection_count exceeds an unscaled option limit."
        )
    allowed = set(option.allowed_wargear_ids)
    for wargear_id in selection.wargear_ids:
        if wargear_id not in allowed:
            raise ListValidationError("WargearSelection includes wargear not allowed by option.")


def _validate_wargear_option_semantics(
    *,
    selections: tuple[WargearSelection, ...],
    datasheet: DatasheetDefinition,
    model_profile_selections: tuple[ModelProfileSelection, ...] | None,
    requested_option_ids: frozenset[str],
) -> None:
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    validate_wargear_bearer_assignments(
        selections=selections,
        options_by_id=options_by_id,
        model_profile_selections=model_profile_selections,
        requested_option_ids=requested_option_ids,
    )
    selected_by_profile: dict[str, set[str]] = {}
    selections_by_profile: dict[str, list[WargearSelection]] = {}
    for selection in selections:
        selected = selected_by_profile.setdefault(selection.model_profile_id, set())
        selected.update(selection.wargear_ids)
        selections_by_profile.setdefault(selection.model_profile_id, []).append(selection)
    for selection in selections:
        if not selection.wargear_ids:
            continue
        option = options_by_id[selection.option_id]
        selected_for_profile = selected_by_profile[selection.model_profile_id]
        other_selected_for_profile = {
            wargear_id
            for other_selection in selections_by_profile[selection.model_profile_id]
            if other_selection.option_id != selection.option_id
            for wargear_id in other_selection.wargear_ids
        }
        for condition in option.conditions:
            if (
                condition.kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
                and (other_selected_for_profile.intersection(condition.wargear_ids))
                and not _not_equipped_condition_can_use_distinct_models(
                    selection=selection,
                    option=option,
                    condition_wargear_ids=condition.wargear_ids,
                    selections_by_profile=selections_by_profile,
                    options_by_id=options_by_id,
                    model_profile_selections=model_profile_selections,
                )
            ):
                raise ListValidationError(
                    "WargearSelection violates a structured wargear option condition."
                )
            if condition.kind is WargearOptionConditionKind.MODEL_EQUIPPED_WITH and not set(
                condition.wargear_ids
            ).issubset(other_selected_for_profile):
                raise ListValidationError(
                    "WargearSelection violates a structured wargear option condition."
                )
        for effect in option.effects:
            if effect.kind is WargearOptionEffectKind.ADD_WARGEAR:
                _validate_add_wargear_effect_count(selection=selection, effect=effect)
            elif effect.kind is WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED:
                _validate_conditional_add_wargear_effect_count(
                    selection=selection,
                    effect=effect,
                )
            elif effect.kind in {
                WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED,
                WargearOptionEffectKind.REPLACE_WARGEAR,
            }:
                validate_replace_wargear_effect_count(
                    selection_wargear_ids=selection.wargear_ids,
                    effect=effect,
                    option_effects=option.effects,
                    selected_for_profile=selected_for_profile,
                    error_type=ListValidationError,
                )
            else:
                raise ListValidationError("Unsupported structured wargear option effect.")
    _validate_scaled_wargear_selection_limits(
        selections=selections,
        options_by_id=options_by_id,
        datasheet=datasheet,
        model_profile_selections=model_profile_selections,
    )


def _not_equipped_condition_can_use_distinct_models(
    *,
    selection: WargearSelection,
    option: DatasheetWargearOption,
    condition_wargear_ids: tuple[str, ...],
    selections_by_profile: dict[str, list[WargearSelection]],
    options_by_id: dict[str, DatasheetWargearOption],
    model_profile_selections: tuple[ModelProfileSelection, ...] | None,
) -> bool:
    if model_profile_selections is None:
        return False
    selected_model_count = next(
        (
            profile_selection.model_count
            for profile_selection in model_profile_selections
            if profile_selection.model_profile_id == selection.model_profile_id
        ),
        0,
    )
    conflicting_selections = tuple(
        other_selection
        for other_selection in selections_by_profile[selection.model_profile_id]
        if other_selection.option_id != selection.option_id
        and set(other_selection.wargear_ids).intersection(condition_wargear_ids)
    )
    if not option.effects or any(
        not options_by_id[other_selection.option_id].effects
        for other_selection in conflicting_selections
    ):
        return False
    required_bearer_count = _structured_selection_bearer_count(
        selection=selection,
        option=option,
    ) + sum(
        _structured_selection_bearer_count(
            selection=other_selection,
            option=options_by_id[other_selection.option_id],
        )
        for other_selection in conflicting_selections
    )
    return required_bearer_count <= selected_model_count


def _structured_selection_bearer_count(
    *,
    selection: WargearSelection,
    option: DatasheetWargearOption,
) -> int:
    effect_model_counts = tuple(
        effect.model_count * selection.resolved_selection_count
        for effect in option.effects
        if effect.wargear_id in selection.wargear_ids
    )
    return max(effect_model_counts, default=selection.resolved_selection_count)


def _validate_scaled_wargear_selection_limits(
    *,
    selections: tuple[WargearSelection, ...],
    options_by_id: dict[str, DatasheetWargearOption],
    datasheet: DatasheetDefinition,
    model_profile_selections: tuple[ModelProfileSelection, ...] | None,
) -> None:
    limited_options = tuple(
        option for option in options_by_id.values() if option.selection_limit is not None
    )
    if not limited_options:
        return
    if model_profile_selections is None:
        raise ListValidationError(
            "Scaled WargearSelection validation requires model profile selections."
        )
    validated_model_selections = resolve_model_profile_selections(
        datasheet=datasheet,
        selections=model_profile_selections,
    )
    selections_by_option_id = {selection.option_id: selection for selection in selections}
    scaled_selections: list[ScaledWargearSelection] = []
    for option in limited_options:
        limit = option.selection_limit
        if limit is None:
            raise ListValidationError("Scaled wargear option selection limit is missing.")
        scaled_selections.append(
            ScaledWargearSelection(
                option_id=option.option_id,
                selection_group_id=limit.selection_group_id,
                models_per_increment=limit.models_per_increment,
                max_group_selections_per_increment=limit.max_group_selections_per_increment,
                max_option_selections_per_increment=limit.max_option_selections_per_increment,
                selected_count=selections_by_option_id[option.option_id].resolved_selection_count,
            )
        )
    validate_scaled_wargear_selections(
        unit_model_count=sum(selection.model_count for selection in validated_model_selections),
        selections=tuple(scaled_selections),
        error_type=ListValidationError,
    )


def _validate_add_wargear_effect_count(
    *,
    selection: WargearSelection,
    effect: DatasheetWargearOptionEffect,
) -> None:
    selected_wargear_count = sum(
        1 for wargear_id in selection.wargear_ids if wargear_id == effect.wargear_id
    )
    if selected_wargear_count != effect.wargear_count:
        raise ListValidationError(
            "WargearSelection does not satisfy a structured wargear option effect count."
        )


def _validate_conditional_add_wargear_effect_count(
    *,
    selection: WargearSelection,
    effect: DatasheetWargearOptionEffect,
) -> None:
    selected_wargear_count = sum(
        1 for wargear_id in selection.wargear_ids if wargear_id == effect.wargear_id
    )
    if selected_wargear_count not in {0, effect.wargear_count}:
        raise ListValidationError(
            "WargearSelection does not satisfy a structured wargear option effect count."
        )


def _validate_model_profile_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[ModelProfileSelection, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    if not values:
        raise ListValidationError(f"{field_name} must not be empty.")
    validated: list[ModelProfileSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not ModelProfileSelection:
            raise ListValidationError(f"{field_name} must contain ModelProfileSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_model_profile_selections(
    selections: tuple[ModelProfileSelection, ...],
) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.model_profile_id in seen:
            raise ListValidationError(
                "UnitMusterSelection model_profile_selections must not contain duplicates."
            )
        seen.add(selection.model_profile_id)


def _validate_wargear_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[WargearSelection, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[WargearSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not WargearSelection:
            raise ListValidationError(f"{field_name} must contain WargearSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_wargear_selections(
    selections: tuple[WargearSelection, ...],
) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.option_id in seen:
            raise ListValidationError("WargearSelection option_ids must be unique.")
        seen.add(selection.option_id)


def _validate_mustering_option_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[MusteringOptionSelection, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[MusteringOptionSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not MusteringOptionSelection:
            raise ListValidationError(f"{field_name} must contain MusteringOptionSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_mustering_option_selections(
    selections: tuple[MusteringOptionSelection, ...],
) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.option_id in seen:
            raise ListValidationError("MusteringOptionSelection option_ids must be unique.")
        seen.add(selection.option_id)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ListValidationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ListValidationError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier_tuple(
    field_name: str,
    values: object,
    prefix: str,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_unprefixed_identifier(f"{field_name} value", value, prefix)
        if identifier in seen:
            raise ListValidationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ListValidationError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ListValidationError(f"{field_name} must not include the stable identity prefix.")
    return identifier


_validate_identifier = IdentifierValidator(ListValidationError)


def battle_size_from_token(token: object) -> BattleSize:
    if type(token) is BattleSize:
        return token
    if type(token) is not str:
        raise ListValidationError("BattleSize token must be a string.")
    try:
        return BattleSize(token)
    except ValueError as exc:
        raise ListValidationError(f"Unsupported BattleSize token: {token}.") from exc


def battle_size_mustering_policy(battle_size: BattleSize) -> BattleSizeMusteringPolicy:
    resolved_battle_size = battle_size_from_token(battle_size)
    if resolved_battle_size is BattleSize.INCURSION:
        return BattleSizeMusteringPolicy.incursion()
    if resolved_battle_size is BattleSize.STRIKE_FORCE:
        return BattleSizeMusteringPolicy.strike_force()
    if resolved_battle_size is BattleSize.ONSLAUGHT:
        return BattleSizeMusteringPolicy.onslaught()
    raise ListValidationError(f"Unsupported BattleSize: {resolved_battle_size.value}.")


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ListValidationError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise ListValidationError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ListValidationError(f"{field_name} must be an integer.")
    if value < 1:
        raise ListValidationError(f"{field_name} must be at least 1.")
    return value
