from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    AttachmentEligibility,
    AttachmentRole,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
)
from warhammer40k_core.core.detachment import EnhancementDefinition, EnhancementSubtype
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryCatalogRecord
from warhammer40k_core.core.ruleset import RulesetError, RulesetId, RulesetIdPayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    AttachmentDeclarationPayload,
    BattleSize,
    DetachmentSelection,
    DetachmentSelectionPayload,
    ListValidationError,
    UnitMusterSelection,
    UnitMusterSelectionPayload,
    battle_size_from_token,
    battle_size_mustering_policy,
    daemonic_pact_datasheet_allowed_for_faction,
    drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction,
    freeblades_datasheet_allowed_for_faction,
    shadow_legion_thralls_datasheet_allowed_for_faction,
    validate_detachment_selection,
    validate_unit_selection_for_army,
)
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
    UnitInstancePayload,
)


class ArmyMusteringError(ValueError):
    """Raised when army mustering violates CORE V2 invariants."""


DAEMONIC_PACT_SOURCE_ID = "phase17g:chaos-daemons:daemonic-pact"
DAEMONIC_PACT_FACTION_KEYWORD = "LEGIONES DAEMONICA"
DAEMONIC_PACT_BASE_KEYWORDS = frozenset({"CHAOS KNIGHTS", "HERETIC ASTARTES"})
DAEMONIC_PACT_POINTS_CAP_BY_BATTLE_SIZE = {
    BattleSize.INCURSION: 250,
    BattleSize.STRIKE_FORCE: 500,
    BattleSize.ONSLAUGHT: 750,
}
DAEMONIC_PACT_GOD_KEYWORDS = ("KHORNE", "TZEENTCH", "NURGLE", "SLAANESH")
DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID = (
    "phase17g:drukhari:corsairs-and-travelling-players"
)
DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_POINTS_CAP_BY_BATTLE_SIZE = {
    BattleSize.INCURSION: 250,
    BattleSize.STRIKE_FORCE: 500,
    BattleSize.ONSLAUGHT: 750,
}
FREEBLADES_SOURCE_ID = "phase17g:imperial-knights:freeblades"
FREEBLADES_REQUIRED_FACTION_KEYWORD = "IMPERIUM"
FREEBLADES_ARMIGER_KEYWORD = "ARMIGER"
FREEBLADES_TITANIC_KEYWORD = "TITANIC"
AELDARI_FACTION_ID = "aeldari"
CORSAIR_COTERIE_DETACHMENT_ID = "corsair-coterie"
CORSAIR_COTERIE_ENHANCEMENT_IDS = frozenset(
    {"archraider", "infamy", "voidstone", "webway-pathstone"}
)
ANHRATHE_KEYWORD = "ANHRATHE"
CHARACTER_KEYWORD = "CHARACTER"
INFANTRY_KEYWORD = "INFANTRY"
SHADOW_LEGION_SOURCE_ID = "phase17g:chaos-daemons:shadow-legion:thralls-of-the-first-prince"
SHADOW_LEGION_FACTION_ID = "chaos-daemons"
SHADOW_LEGION_DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"
SHADOW_LEGION_UNDIVIDED_KEYWORD = "UNDIVIDED"
SHADOW_LEGION_DEEP_STRIKE_KEYWORD = "DEEP STRIKE"
SHADOW_LEGION_LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
SHADOW_LEGION_HERETIC_ASTARTES_KEYWORD = "HERETIC ASTARTES"
SHADOW_LEGION_DAMNED_KEYWORD = "DAMNED"
SHADOW_LEGION_POINTS_CAP_BY_BATTLE_SIZE = {
    BattleSize.INCURSION: 500,
    BattleSize.STRIKE_FORCE: 1000,
    BattleSize.ONSLAUGHT: 1500,
}
SHADOW_LEGION_FORBIDDEN_DAEMON_PRINCE_NAMES = frozenset(
    {
        "DAEMONPRINCE",
        "DAEMONPRINCEWITHWINGS",
        "DAEMONPRINCEOFCHAOS",
        "DAEMONPRINCEOFCHAOSWITHWINGS",
    }
)
SHADOW_LEGION_BELAKOR_NAME = "BELAKOR"
SPACE_MARINE_CHAPTERS_SOURCE_ID = "phase17g:space-marines:space-marine-chapters"
SPACE_MARINES_FACTION_ID = "space-marines"
ADEPTUS_ASTARTES_KEYWORD = "ADEPTUS ASTARTES"
AGENTS_OF_THE_IMPERIUM_KEYWORD = "AGENTS OF THE IMPERIUM"
BLACK_TEMPLARS_KEYWORD = "BLACK TEMPLARS"
BLOOD_ANGELS_KEYWORD = "BLOOD ANGELS"
DARK_ANGELS_KEYWORD = "DARK ANGELS"
DEATHWATCH_KEYWORD = "DEATHWATCH"
SPACE_WOLVES_KEYWORD = "SPACE WOLVES"
SPACE_MARINE_CHAPTER_KEYWORDS = frozenset(
    {
        BLACK_TEMPLARS_KEYWORD,
        BLOOD_ANGELS_KEYWORD,
        DARK_ANGELS_KEYWORD,
        DEATHWATCH_KEYWORD,
        "IMPERIAL FISTS",
        "IRON HANDS",
        "RAVEN GUARD",
        "SALAMANDERS",
        SPACE_WOLVES_KEYWORD,
        "ULTRAMARINES",
        "WHITE SCARS",
    }
)
BLACK_TEMPLARS_FORBIDDEN_NON_CHAPTER_NAMES = frozenset(
    {
        "GLADIATORLANCER",
        "GLADIATORREAPER",
        "GLADIATORVALIANT",
        "IMPULSOR",
        "REPULSOR",
        "REPULSOREXECUTIONER",
    }
)
SPACE_WOLVES_FORBIDDEN_UNIT_NAMES = frozenset({"APOTHECARY", "DEVASTATORSQUAD", "TACTICALSQUAD"})
DEATHWATCH_ALLOWED_AGENTS_UNIT_NAMES = frozenset({"KILLTEAMCASSIUS"})
DEATHWATCH_FORBIDDEN_UNIT_NAMES = frozenset(
    {
        "ASSAULTSQUAD",
        "ASSAULTSQUADWITHJUMPPACKS",
        "ATTACKBIKESQUAD",
        "DEVASTATORSQUAD",
        "LANDSPEEDERSTORM",
        "RELICTERMINATORSQUAD",
        "SCOUTBIKESQUAD",
        "SCOUTSQUAD",
        "SCOUTSNIPERSQUAD",
        "TACTICALSQUAD",
        "TERMINATORASSAULTSQUAD",
        "TERMINATORSQUAD",
    }
)


class ArmyMusterRequestPayload(TypedDict):
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetIdPayload
    detachment_selection: DetachmentSelectionPayload
    unit_selections: list[UnitMusterSelectionPayload]
    attachment_declarations: list[AttachmentDeclarationPayload]
    unit_points: list[RosterUnitPointValuePayload]
    enhancement_assignments: list[EnhancementAssignmentPayload]
    warlord_selection: WarlordSelectionPayload | None
    dedicated_transport_manifests: list[DedicatedTransportManifestPayload]
    roster_legality_required: bool
    battle_size: str


class AttachedUnitFormationPayload(TypedDict):
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: list[str]
    support_unit_instance_ids: list[str]
    component_unit_instance_ids: list[str]
    source_id: str


class ArmyDefinitionPayload(TypedDict):
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetIdPayload
    detachment_selection: DetachmentSelectionPayload
    units: list[UnitInstancePayload]
    attached_units: list[AttachedUnitFormationPayload]
    unit_points: list[RosterUnitPointValuePayload]
    enhancement_assignments: list[EnhancementAssignmentPayload]
    warlord_selection: WarlordSelectionPayload | None
    dedicated_transport_manifests: list[DedicatedTransportManifestPayload]
    roster_legality_report: RosterLegalityReportPayload
    battle_size: str


class RosterUnitPointValuePayload(TypedDict):
    unit_selection_id: str
    points: int
    source_id: str


class EnhancementAssignmentPayload(TypedDict):
    enhancement_id: str
    target_unit_selection_id: str
    source_id: str


class WarlordSelectionPayload(TypedDict):
    unit_selection_id: str
    source_id: str


class DedicatedTransportManifestPayload(TypedDict):
    transport_unit_selection_id: str
    embarked_unit_selection_ids: list[str]
    capacity_profile: DedicatedTransportCapacityProfilePayload
    source_id: str


class DedicatedTransportCapacityProfilePayload(TypedDict):
    transport_datasheet_id: str
    max_model_count: int
    allowed_keywords: list[str]
    excluded_keywords: list[str]
    source_id: str


class RosterLegalityViolationPayload(TypedDict):
    violation_code: str
    message: str
    unit_selection_id: str | None
    source_id: str | None


class RosterLegalityReportPayload(TypedDict):
    battle_size: str
    is_legal: bool
    violations: list[RosterLegalityViolationPayload]


@dataclass(frozen=True, slots=True)
class RosterUnitPointValue:
    unit_selection_id: str
    points: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_unprefixed_identifier(
                "RosterUnitPointValue unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "points",
            _validate_non_negative_int("RosterUnitPointValue points", self.points),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("RosterUnitPointValue source_id", self.source_id),
        )

    def to_payload(self) -> RosterUnitPointValuePayload:
        return {
            "unit_selection_id": self.unit_selection_id,
            "points": self.points,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: RosterUnitPointValuePayload) -> Self:
        return cls(
            unit_selection_id=payload["unit_selection_id"],
            points=payload["points"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class EnhancementAssignment:
    enhancement_id: str
    target_unit_selection_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_unprefixed_identifier(
                "EnhancementAssignment enhancement_id",
                self.enhancement_id,
                "enhancement:",
            ),
        )
        object.__setattr__(
            self,
            "target_unit_selection_id",
            _validate_unprefixed_identifier(
                "EnhancementAssignment target_unit_selection_id",
                self.target_unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("EnhancementAssignment source_id", self.source_id),
        )

    def to_payload(self) -> EnhancementAssignmentPayload:
        return {
            "enhancement_id": self.enhancement_id,
            "target_unit_selection_id": self.target_unit_selection_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: EnhancementAssignmentPayload) -> Self:
        return cls(
            enhancement_id=payload["enhancement_id"],
            target_unit_selection_id=payload["target_unit_selection_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class WarlordSelection:
    unit_selection_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_unprefixed_identifier(
                "WarlordSelection unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("WarlordSelection source_id", self.source_id),
        )

    def to_payload(self) -> WarlordSelectionPayload:
        return {
            "unit_selection_id": self.unit_selection_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: WarlordSelectionPayload) -> Self:
        return cls(
            unit_selection_id=payload["unit_selection_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class DedicatedTransportCapacityProfile:
    transport_datasheet_id: str
    max_model_count: int
    allowed_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    source_id: str = "phase16d:dedicated-transport-capacity"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transport_datasheet_id",
            _validate_unprefixed_identifier(
                "DedicatedTransportCapacityProfile transport_datasheet_id",
                self.transport_datasheet_id,
                "datasheet:",
            ),
        )
        object.__setattr__(
            self,
            "max_model_count",
            _validate_positive_int(
                "DedicatedTransportCapacityProfile max_model_count",
                self.max_model_count,
            ),
        )
        object.__setattr__(
            self,
            "allowed_keywords",
            _validate_identifier_tuple(
                "DedicatedTransportCapacityProfile allowed_keywords",
                self.allowed_keywords,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "excluded_keywords",
            _validate_identifier_tuple(
                "DedicatedTransportCapacityProfile excluded_keywords",
                self.excluded_keywords,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DedicatedTransportCapacityProfile source_id", self.source_id),
        )

    def to_payload(self) -> DedicatedTransportCapacityProfilePayload:
        return {
            "transport_datasheet_id": self.transport_datasheet_id,
            "max_model_count": self.max_model_count,
            "allowed_keywords": list(self.allowed_keywords),
            "excluded_keywords": list(self.excluded_keywords),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DedicatedTransportCapacityProfilePayload) -> Self:
        return cls(
            transport_datasheet_id=payload["transport_datasheet_id"],
            max_model_count=payload["max_model_count"],
            allowed_keywords=tuple(payload["allowed_keywords"]),
            excluded_keywords=tuple(payload["excluded_keywords"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class DedicatedTransportManifest:
    transport_unit_selection_id: str
    embarked_unit_selection_ids: tuple[str, ...]
    capacity_profile: DedicatedTransportCapacityProfile
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transport_unit_selection_id",
            _validate_unprefixed_identifier(
                "DedicatedTransportManifest transport_unit_selection_id",
                self.transport_unit_selection_id,
                "unit-selection:",
            ),
        )
        embarked_ids = _validate_unprefixed_identifier_tuple(
            "DedicatedTransportManifest embarked_unit_selection_ids",
            self.embarked_unit_selection_ids,
            "unit-selection:",
            min_length=0,
        )
        if self.transport_unit_selection_id in embarked_ids:
            raise ArmyMusteringError("DedicatedTransportManifest cannot embark itself.")
        object.__setattr__(self, "embarked_unit_selection_ids", embarked_ids)
        if type(self.capacity_profile) is not DedicatedTransportCapacityProfile:
            raise ArmyMusteringError(
                "DedicatedTransportManifest capacity_profile must be a "
                "DedicatedTransportCapacityProfile."
            )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DedicatedTransportManifest source_id", self.source_id),
        )

    def transport_unit_instance_id(self, *, army_id: str) -> str:
        requested_army_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
        return f"{requested_army_id}:{self.transport_unit_selection_id}"

    def embarked_unit_instance_ids(self, *, army_id: str) -> tuple[str, ...]:
        requested_army_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
        return tuple(
            sorted(f"{requested_army_id}:{unit_id}" for unit_id in self.embarked_unit_selection_ids)
        )

    def to_payload(self) -> DedicatedTransportManifestPayload:
        return {
            "transport_unit_selection_id": self.transport_unit_selection_id,
            "embarked_unit_selection_ids": list(self.embarked_unit_selection_ids),
            "capacity_profile": self.capacity_profile.to_payload(),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DedicatedTransportManifestPayload) -> Self:
        return cls(
            transport_unit_selection_id=payload["transport_unit_selection_id"],
            embarked_unit_selection_ids=tuple(payload["embarked_unit_selection_ids"]),
            capacity_profile=DedicatedTransportCapacityProfile.from_payload(
                payload["capacity_profile"]
            ),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class RosterLegalityViolation:
    violation_code: str
    message: str
    unit_selection_id: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("RosterLegalityViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("RosterLegalityViolation message", self.message),
        )
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_optional_unprefixed_identifier(
                "RosterLegalityViolation unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_optional_identifier("RosterLegalityViolation source_id", self.source_id),
        )

    def to_payload(self) -> RosterLegalityViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "unit_selection_id": self.unit_selection_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: RosterLegalityViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            unit_selection_id=payload["unit_selection_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class RosterLegalityReport:
    battle_size: BattleSize
    violations: tuple[RosterLegalityViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "battle_size", _battle_size_from_token(self.battle_size))
        object.__setattr__(
            self,
            "violations",
            _validate_roster_legality_violation_tuple(
                "RosterLegalityReport violations",
                self.violations,
            ),
        )

    @property
    def is_legal(self) -> bool:
        return not self.violations

    def assert_legal(self) -> None:
        if self.is_legal:
            return
        first = self.violations[0]
        raise ArmyMusteringError(
            f"RosterLegalityReport is invalid: {first.violation_code}: {first.message}"
        )

    def to_payload(self) -> RosterLegalityReportPayload:
        return {
            "battle_size": self.battle_size.value,
            "is_legal": self.is_legal,
            "violations": [violation.to_payload() for violation in self.violations],
        }

    @classmethod
    def from_payload(cls, payload: RosterLegalityReportPayload) -> Self:
        report = cls(
            battle_size=_battle_size_from_token(payload["battle_size"]),
            violations=tuple(
                RosterLegalityViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
        )
        if report.is_legal != payload["is_legal"]:
            raise ArmyMusteringError("RosterLegalityReport is_legal payload drift.")
        return report


@dataclass(frozen=True, slots=True)
class ArmyMusterRequest:
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetId
    detachment_selection: DetachmentSelection
    unit_selections: tuple[UnitMusterSelection, ...]
    attachment_declarations: tuple[AttachmentDeclaration, ...] = ()
    unit_points: tuple[RosterUnitPointValue, ...] = ()
    enhancement_assignments: tuple[EnhancementAssignment, ...] = ()
    warlord_selection: WarlordSelection | None = None
    dedicated_transport_manifests: tuple[DedicatedTransportManifest, ...] = ()
    roster_legality_required: bool = False
    battle_size: BattleSize = BattleSize.STRIKE_FORCE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("ArmyMusterRequest army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ArmyMusterRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "catalog_id",
            _validate_unprefixed_identifier(
                "ArmyMusterRequest catalog_id",
                self.catalog_id,
                "catalog:",
            ),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier(
                "ArmyMusterRequest source_package_id",
                self.source_package_id,
            ),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise ArmyMusteringError("ArmyMusterRequest ruleset_id must be a RulesetId.")
        if type(self.detachment_selection) is not DetachmentSelection:
            raise ArmyMusteringError(
                "ArmyMusterRequest detachment_selection must be a DetachmentSelection."
            )
        unit_selections = _validate_unit_muster_selection_tuple(
            "ArmyMusterRequest unit_selections",
            self.unit_selections,
        )
        _validate_unique_unit_selection_ids(unit_selections)
        object.__setattr__(self, "unit_selections", unit_selections)
        attachment_declarations = _validate_attachment_declaration_tuple(
            "ArmyMusterRequest attachment_declarations",
            self.attachment_declarations,
        )
        _validate_unique_attachment_source_ids(attachment_declarations)
        object.__setattr__(self, "attachment_declarations", attachment_declarations)
        unit_points = _validate_roster_unit_point_tuple(
            "ArmyMusterRequest unit_points",
            self.unit_points,
        )
        _validate_unique_roster_unit_points(unit_points)
        object.__setattr__(self, "unit_points", unit_points)
        enhancement_assignments = _validate_enhancement_assignment_tuple(
            "ArmyMusterRequest enhancement_assignments",
            self.enhancement_assignments,
        )
        _validate_unique_enhancement_assignments(enhancement_assignments)
        object.__setattr__(self, "enhancement_assignments", enhancement_assignments)
        object.__setattr__(
            self,
            "warlord_selection",
            _validate_optional_warlord_selection(self.warlord_selection),
        )
        manifests = _validate_dedicated_transport_manifest_tuple(
            "ArmyMusterRequest dedicated_transport_manifests",
            self.dedicated_transport_manifests,
        )
        _validate_unique_dedicated_transport_manifests(manifests)
        object.__setattr__(self, "dedicated_transport_manifests", manifests)
        object.__setattr__(
            self,
            "roster_legality_required",
            _validate_bool(
                "ArmyMusterRequest roster_legality_required", self.roster_legality_required
            ),
        )
        object.__setattr__(self, "battle_size", _battle_size_from_token(self.battle_size))

    def to_payload(self) -> ArmyMusterRequestPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "detachment_selection": self.detachment_selection.to_payload(),
            "unit_selections": [selection.to_payload() for selection in self.unit_selections],
            "attachment_declarations": [
                declaration.to_payload() for declaration in self.attachment_declarations
            ],
            "unit_points": [point.to_payload() for point in self.unit_points],
            "enhancement_assignments": [
                assignment.to_payload() for assignment in self.enhancement_assignments
            ],
            "warlord_selection": (
                None if self.warlord_selection is None else self.warlord_selection.to_payload()
            ),
            "dedicated_transport_manifests": [
                manifest.to_payload() for manifest in self.dedicated_transport_manifests
            ],
            "roster_legality_required": self.roster_legality_required,
            "battle_size": self.battle_size.value,
        }

    @classmethod
    def from_payload(cls, payload: ArmyMusterRequestPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            catalog_id=payload["catalog_id"],
            source_package_id=payload["source_package_id"],
            ruleset_id=_ruleset_id_from_payload(payload["ruleset_id"]),
            detachment_selection=DetachmentSelection.from_payload(payload["detachment_selection"]),
            unit_selections=tuple(
                UnitMusterSelection.from_payload(selection)
                for selection in payload["unit_selections"]
            ),
            attachment_declarations=tuple(
                AttachmentDeclaration.from_payload(declaration)
                for declaration in payload["attachment_declarations"]
            ),
            unit_points=tuple(
                RosterUnitPointValue.from_payload(point) for point in payload["unit_points"]
            ),
            enhancement_assignments=tuple(
                EnhancementAssignment.from_payload(assignment)
                for assignment in payload["enhancement_assignments"]
            ),
            warlord_selection=(
                None
                if payload["warlord_selection"] is None
                else WarlordSelection.from_payload(payload["warlord_selection"])
            ),
            dedicated_transport_manifests=tuple(
                DedicatedTransportManifest.from_payload(manifest)
                for manifest in payload["dedicated_transport_manifests"]
            ),
            roster_legality_required=payload["roster_legality_required"],
            battle_size=_battle_size_from_token(payload["battle_size"]),
        )


@dataclass(frozen=True, slots=True)
class AttachedUnitFormation:
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: tuple[str, ...] = ()
    support_unit_instance_ids: tuple[str, ...] = ()
    component_unit_instance_ids: tuple[str, ...] = ()
    source_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attached_unit_instance_id",
            _validate_attached_unit_instance_id(
                "AttachedUnitFormation attached_unit_instance_id",
                self.attached_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_instance_id",
            _validate_identifier(
                "AttachedUnitFormation bodyguard_unit_instance_id",
                self.bodyguard_unit_instance_id,
            ),
        )
        leader_ids = _validate_identifier_tuple(
            "AttachedUnitFormation leader_unit_instance_ids",
            self.leader_unit_instance_ids,
            min_length=0,
        )
        support_ids = _validate_identifier_tuple(
            "AttachedUnitFormation support_unit_instance_ids",
            self.support_unit_instance_ids,
            min_length=0,
        )
        if not leader_ids and not support_ids:
            raise ArmyMusteringError("AttachedUnitFormation requires a leader or support unit.")
        component_ids = _validate_identifier_tuple(
            "AttachedUnitFormation component_unit_instance_ids",
            self.component_unit_instance_ids,
            min_length=2,
        )
        expected_component_ids = tuple(
            sorted((self.bodyguard_unit_instance_id, *leader_ids, *support_ids))
        )
        if component_ids != expected_component_ids:
            raise ArmyMusteringError(
                "AttachedUnitFormation component_unit_instance_ids must match components."
            )
        object.__setattr__(self, "leader_unit_instance_ids", leader_ids)
        object.__setattr__(self, "support_unit_instance_ids", support_ids)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AttachedUnitFormation source_id", self.source_id),
        )

    def to_payload(self) -> AttachedUnitFormationPayload:
        return {
            "attached_unit_instance_id": self.attached_unit_instance_id,
            "bodyguard_unit_instance_id": self.bodyguard_unit_instance_id,
            "leader_unit_instance_ids": list(self.leader_unit_instance_ids),
            "support_unit_instance_ids": list(self.support_unit_instance_ids),
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: AttachedUnitFormationPayload) -> Self:
        return cls(
            attached_unit_instance_id=payload["attached_unit_instance_id"],
            bodyguard_unit_instance_id=payload["bodyguard_unit_instance_id"],
            leader_unit_instance_ids=tuple(payload["leader_unit_instance_ids"]),
            support_unit_instance_ids=tuple(payload["support_unit_instance_ids"]),
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ArmyDefinition:
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetId
    detachment_selection: DetachmentSelection
    units: tuple[UnitInstance, ...]
    attached_units: tuple[AttachedUnitFormation, ...] = ()
    unit_points: tuple[RosterUnitPointValue, ...] = ()
    enhancement_assignments: tuple[EnhancementAssignment, ...] = ()
    warlord_selection: WarlordSelection | None = None
    dedicated_transport_manifests: tuple[DedicatedTransportManifest, ...] = ()
    roster_legality_report: RosterLegalityReport = field(
        default_factory=lambda: RosterLegalityReport(battle_size=BattleSize.STRIKE_FORCE)
    )
    battle_size: BattleSize = BattleSize.STRIKE_FORCE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("ArmyDefinition army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ArmyDefinition player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "catalog_id",
            _validate_unprefixed_identifier(
                "ArmyDefinition catalog_id",
                self.catalog_id,
                "catalog:",
            ),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("ArmyDefinition source_package_id", self.source_package_id),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise ArmyMusteringError("ArmyDefinition ruleset_id must be a RulesetId.")
        if type(self.detachment_selection) is not DetachmentSelection:
            raise ArmyMusteringError(
                "ArmyDefinition detachment_selection must be a DetachmentSelection."
            )
        units = _validate_unit_instance_tuple("ArmyDefinition units", self.units)
        _validate_unique_unit_instance_ids(units)
        _validate_unit_ids_scoped_to_army(army_id=self.army_id, units=units)
        object.__setattr__(self, "units", units)
        attached_units = _validate_attached_unit_formation_tuple(
            "ArmyDefinition attached_units",
            self.attached_units,
        )
        _validate_attached_unit_formations_reference_units(
            army_id=self.army_id,
            units=units,
            attached_units=attached_units,
        )
        object.__setattr__(self, "attached_units", attached_units)
        unit_points = _validate_roster_unit_point_tuple(
            "ArmyDefinition unit_points",
            self.unit_points,
        )
        _validate_unique_roster_unit_points(unit_points)
        object.__setattr__(self, "unit_points", unit_points)
        enhancement_assignments = _validate_enhancement_assignment_tuple(
            "ArmyDefinition enhancement_assignments",
            self.enhancement_assignments,
        )
        _validate_unique_enhancement_assignments(enhancement_assignments)
        object.__setattr__(self, "enhancement_assignments", enhancement_assignments)
        object.__setattr__(
            self,
            "warlord_selection",
            _validate_optional_warlord_selection(self.warlord_selection),
        )
        manifests = _validate_dedicated_transport_manifest_tuple(
            "ArmyDefinition dedicated_transport_manifests",
            self.dedicated_transport_manifests,
        )
        _validate_unique_dedicated_transport_manifests(manifests)
        object.__setattr__(self, "dedicated_transport_manifests", manifests)
        if type(self.roster_legality_report) is not RosterLegalityReport:
            raise ArmyMusteringError(
                "ArmyDefinition roster_legality_report must be a RosterLegalityReport."
            )
        object.__setattr__(self, "roster_legality_report", self.roster_legality_report)
        object.__setattr__(self, "battle_size", _battle_size_from_token(self.battle_size))
        if self.roster_legality_report.battle_size is not self.battle_size:
            raise ArmyMusteringError("ArmyDefinition roster_legality_report battle_size drift.")

    def stable_identity(self) -> str:
        return f"army:{self.army_id}"

    def unit_by_id(self, unit_instance_id: str) -> UnitInstance:
        requested_id = _validate_unprefixed_identifier(
            "unit_instance_id",
            unit_instance_id,
            "unit:",
        )
        for unit in self.units:
            if unit.unit_instance_id == requested_id:
                return unit
        raise ArmyMusteringError("ArmyDefinition unit_instance_id was not found.")

    def to_payload(self) -> ArmyDefinitionPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "detachment_selection": self.detachment_selection.to_payload(),
            "units": [unit.to_payload() for unit in self.units],
            "attached_units": [attached.to_payload() for attached in self.attached_units],
            "unit_points": [point.to_payload() for point in self.unit_points],
            "enhancement_assignments": [
                assignment.to_payload() for assignment in self.enhancement_assignments
            ],
            "warlord_selection": (
                None if self.warlord_selection is None else self.warlord_selection.to_payload()
            ),
            "dedicated_transport_manifests": [
                manifest.to_payload() for manifest in self.dedicated_transport_manifests
            ],
            "roster_legality_report": self.roster_legality_report.to_payload(),
            "battle_size": self.battle_size.value,
        }

    @classmethod
    def from_payload(cls, payload: ArmyDefinitionPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            catalog_id=payload["catalog_id"],
            source_package_id=payload["source_package_id"],
            ruleset_id=_ruleset_id_from_payload(payload["ruleset_id"]),
            detachment_selection=DetachmentSelection.from_payload(payload["detachment_selection"]),
            units=tuple(_unit_instance_from_payload(unit) for unit in payload["units"]),
            attached_units=tuple(
                AttachedUnitFormation.from_payload(attached)
                for attached in payload["attached_units"]
            ),
            unit_points=tuple(
                RosterUnitPointValue.from_payload(point) for point in payload["unit_points"]
            ),
            enhancement_assignments=tuple(
                EnhancementAssignment.from_payload(assignment)
                for assignment in payload["enhancement_assignments"]
            ),
            warlord_selection=(
                None
                if payload["warlord_selection"] is None
                else WarlordSelection.from_payload(payload["warlord_selection"])
            ),
            dedicated_transport_manifests=tuple(
                DedicatedTransportManifest.from_payload(manifest)
                for manifest in payload["dedicated_transport_manifests"]
            ),
            roster_legality_report=RosterLegalityReport.from_payload(
                payload["roster_legality_report"]
            ),
            battle_size=_battle_size_from_token(payload["battle_size"]),
        )


def muster_army(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] = (),
) -> ArmyDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ArmyMusteringError("catalog must be an ArmyCatalog.")
    if type(request) is not ArmyMusterRequest:
        raise ArmyMusteringError("request must be an ArmyMusterRequest.")
    _validate_request_matches_catalog(catalog=catalog, request=request)
    try:
        faction, _detachments = validate_detachment_selection(
            catalog=catalog,
            selection=request.detachment_selection,
            battle_size=request.battle_size,
        )
    except ListValidationError as exc:
        raise ArmyMusteringError("ArmyMusterRequest detachment selection is invalid.") from exc

    try:
        factory = UnitFactory(catalog=catalog, model_geometries=model_geometries)
    except UnitFactoryError as exc:
        raise ArmyMusteringError("ArmyMusterRequest model geometries are invalid.") from exc
    units: list[UnitInstance] = []
    datasheets_by_selection_id: dict[str, DatasheetDefinition] = {}
    for selection in request.unit_selections:
        try:
            datasheet = validate_unit_selection_for_army(
                catalog=catalog,
                selection=selection,
                faction=faction,
                detachment_selection=request.detachment_selection,
                battle_size=request.battle_size,
            )
            datasheets_by_selection_id[selection.unit_selection_id] = datasheet
            units.append(
                factory.instantiate_unit(
                    army_id=request.army_id,
                    selection=selection,
                    datasheet=datasheet,
                )
            )
        except (ListValidationError, UnitFactoryError) as exc:
            raise ArmyMusteringError("ArmyMusterRequest unit selection is invalid.") from exc
    resolved_units, attached_units = _resolve_attached_unit_formations(
        request=request,
        units=tuple(units),
        datasheets_by_selection_id=datasheets_by_selection_id,
    )
    roster_legality_report = validate_roster_legality(catalog=catalog, request=request)
    if request.roster_legality_required:
        roster_legality_report.assert_legal()
    resolved_units = _apply_warlord_keyword_if_selected(
        request=request,
        units=resolved_units,
        roster_legality_report=roster_legality_report,
    )
    resolved_units = _apply_shadow_legion_keyword_grants(
        request=request,
        units=resolved_units,
    )
    return ArmyDefinition(
        army_id=request.army_id,
        player_id=request.player_id,
        catalog_id=request.catalog_id,
        source_package_id=request.source_package_id,
        ruleset_id=request.ruleset_id,
        detachment_selection=request.detachment_selection,
        units=resolved_units,
        attached_units=attached_units,
        unit_points=request.unit_points,
        enhancement_assignments=request.enhancement_assignments,
        warlord_selection=request.warlord_selection,
        dedicated_transport_manifests=request.dedicated_transport_manifests,
        roster_legality_report=roster_legality_report,
        battle_size=request.battle_size,
    )


def validate_roster_legality(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
) -> RosterLegalityReport:
    if type(catalog) is not ArmyCatalog:
        raise ArmyMusteringError("catalog must be an ArmyCatalog.")
    if type(request) is not ArmyMusterRequest:
        raise ArmyMusteringError("request must be an ArmyMusterRequest.")
    _validate_request_matches_catalog(catalog=catalog, request=request)
    try:
        policy = battle_size_mustering_policy(request.battle_size)
        faction, detachments = validate_detachment_selection(
            catalog=catalog,
            selection=request.detachment_selection,
            battle_size=request.battle_size,
        )
    except ListValidationError as exc:
        return RosterLegalityReport(
            battle_size=request.battle_size,
            violations=(
                RosterLegalityViolation(
                    violation_code="detachment_selection_invalid",
                    message=str(exc),
                    source_id="phase16d:detachment-selection",
                ),
            ),
        )

    violations: list[RosterLegalityViolation] = []
    datasheets_by_selection_id: dict[str, DatasheetDefinition] = {}
    selection_by_id = {
        selection.unit_selection_id: selection for selection in request.unit_selections
    }
    for selection in request.unit_selections:
        try:
            datasheets_by_selection_id[selection.unit_selection_id] = (
                validate_unit_selection_for_army(
                    catalog=catalog,
                    selection=selection,
                    faction=faction,
                    detachment_selection=request.detachment_selection,
                    battle_size=request.battle_size,
                )
            )
        except ListValidationError as exc:
            violations.append(
                RosterLegalityViolation(
                    violation_code="unit_selection_invalid",
                    message=str(exc),
                    unit_selection_id=selection.unit_selection_id,
                    source_id="phase16d:unit-selection",
                )
            )
            inspection_datasheet = (
                _space_marine_chapter_inspection_datasheet_for_rejected_selection(
                    catalog=catalog,
                    request=request,
                    faction=faction,
                    selection=selection,
                )
            )
            if inspection_datasheet is not None:
                datasheets_by_selection_id[selection.unit_selection_id] = inspection_datasheet

    _append_unit_point_violations(
        catalog=catalog,
        request=request,
        policy_points_limit=policy.points_limit,
        violations=violations,
    )
    _append_unit_limit_violations(
        request=request,
        datasheets_by_selection_id=datasheets_by_selection_id,
        unit_limit=policy.unit_limit,
        battleline_unit_limit=policy.battleline_unit_limit,
        violations=violations,
    )
    _append_warlord_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_enhancement_violations(
        catalog=catalog,
        request=request,
        selected_detachment_enhancement_ids=tuple(
            enhancement_id
            for detachment in detachments
            for enhancement_id in detachment.enhancement_ids
        ),
        datasheets_by_selection_id=datasheets_by_selection_id,
        enhancement_limit=policy.enhancement_limit,
        violations=violations,
    )
    _append_daemonic_pact_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_drukhari_corsairs_and_travelling_players_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_freeblades_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_shadow_legion_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_space_marine_chapter_violations(
        request=request,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_dedicated_transport_manifest_violations(
        request=request,
        selection_by_id=selection_by_id,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    return RosterLegalityReport(
        battle_size=request.battle_size,
        violations=tuple(sorted(violations, key=_roster_violation_sort_key)),
    )


def _append_unit_point_violations(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    policy_points_limit: int,
    violations: list[RosterLegalityViolation],
) -> None:
    points_by_selection_id = {point.unit_selection_id: point for point in request.unit_points}
    for selection in request.unit_selections:
        if selection.unit_selection_id not in points_by_selection_id:
            violations.append(
                RosterLegalityViolation(
                    violation_code="source_awaiting_unit_points",
                    message="Roster path requires source-backed unit points.",
                    unit_selection_id=selection.unit_selection_id,
                    source_id="phase16d:unit-points",
                )
            )
    known_selection_ids = {selection.unit_selection_id for selection in request.unit_selections}
    for point in request.unit_points:
        if point.unit_selection_id not in known_selection_ids:
            violations.append(
                RosterLegalityViolation(
                    violation_code="unit_points_unknown_unit",
                    message="RosterUnitPointValue references an unknown unit selection.",
                    unit_selection_id=point.unit_selection_id,
                    source_id=point.source_id,
                )
            )
    enhancement_points_by_id = {
        enhancement.enhancement_id: enhancement.points
        for enhancement in catalog.enhancements
        if enhancement.points is not None
    }
    total_points = sum(point.points for point in request.unit_points) + sum(
        enhancement_points_by_id[assignment.enhancement_id]
        for assignment in request.enhancement_assignments
        if assignment.enhancement_id in enhancement_points_by_id
    )
    if total_points > policy_points_limit:
        violations.append(
            RosterLegalityViolation(
                violation_code="points_limit_exceeded",
                message="Roster exceeds the battle-size points limit.",
                source_id="phase16d:points-limit",
            )
        )


def _append_unit_limit_violations(
    *,
    request: ArmyMusterRequest,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    unit_limit: int,
    battleline_unit_limit: int,
    violations: list[RosterLegalityViolation],
) -> None:
    selections_by_datasheet_id: dict[str, list[str]] = {}
    for selection in request.unit_selections:
        selections_by_datasheet_id.setdefault(selection.datasheet_id, []).append(
            selection.unit_selection_id
        )
    for datasheet_id, selection_ids in selections_by_datasheet_id.items():
        first_selection_id = sorted(selection_ids)[0]
        datasheet = datasheets_by_selection_id.get(first_selection_id)
        if datasheet is None:
            continue
        limit = (
            battleline_unit_limit if _datasheet_has_keyword(datasheet, "BATTLELINE") else unit_limit
        )
        if len(selection_ids) > limit:
            violations.append(
                RosterLegalityViolation(
                    violation_code="unit_limit_exceeded",
                    message="Roster exceeds battle-size unit limit for a datasheet.",
                    unit_selection_id=first_selection_id,
                    source_id=f"phase16d:unit-limit:{datasheet_id}",
                )
            )
        if _datasheet_has_keyword(datasheet, "EPIC HERO") and len(selection_ids) > 1:
            violations.append(
                RosterLegalityViolation(
                    violation_code="epic_hero_not_unique",
                    message="EPIC HERO units are unique in a roster.",
                    unit_selection_id=first_selection_id,
                    source_id=f"phase16d:epic-hero:{datasheet_id}",
                )
            )


def _append_warlord_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    if request.warlord_selection is None:
        violations.append(
            RosterLegalityViolation(
                violation_code="missing_warlord_selection",
                message="Roster requires one selected Warlord.",
                source_id="phase16d:warlord",
            )
        )
        return
    datasheet = datasheets_by_selection_id.get(request.warlord_selection.unit_selection_id)
    if datasheet is None:
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_unknown_unit",
                message="WarlordSelection references an unknown unit selection.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
        return
    if not _datasheet_has_keyword(datasheet, "CHARACTER"):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_character_required",
                message="WarlordSelection requires a CHARACTER unit.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
    forbidden_source_id = _datasheet_warlord_forbidden_source_id(datasheet)
    if forbidden_source_id is not None:
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_forbidden",
                message="WarlordSelection target has a rule that says it cannot be Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=forbidden_source_id,
            )
        )
    if _is_daemonic_pact_datasheet(datasheet, faction.faction_keywords):
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_warlord_forbidden",
                message="Daemonic Pact Legiones Daemonica units cannot be selected as Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=DAEMONIC_PACT_SOURCE_ID,
            )
        )
    elif drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_drukhari_corsairs_and_travelling_players_forbidden",
                message=(
                    "Corsairs and Travelling Players HARLEQUINS or ANHRATHE units cannot "
                    "be selected as Warlord."
                ),
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
            )
        )
    elif freeblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_freeblades_forbidden",
                message="Freeblades Imperial Knights models cannot be selected as Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=FREEBLADES_SOURCE_ID,
            )
        )
    elif not set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_faction_keyword_required",
                message="WarlordSelection must share the army faction keyword.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
    _append_supreme_commander_warlord_violations(
        warlord_selection=request.warlord_selection,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )


def _append_supreme_commander_warlord_violations(
    *,
    warlord_selection: WarlordSelection,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    required_source_by_selection_id = {
        selection_id: source_id
        for selection_id, datasheet in datasheets_by_selection_id.items()
        if (source_id := _datasheet_requires_warlord_source_id(datasheet)) is not None
    }
    if not required_source_by_selection_id:
        return
    eligible_required_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id in required_source_by_selection_id
            if _datasheet_can_be_selected_warlord(
                datasheet=datasheets_by_selection_id[selection_id],
                faction=faction,
            )
        )
    )
    if not eligible_required_selection_ids:
        first_required_selection_id = sorted(required_source_by_selection_id)[0]
        violations.append(
            RosterLegalityViolation(
                violation_code="supreme_commander_warlord_conflict",
                message=(
                    "Supreme Commander requires a Warlord from that set, but every such "
                    "unit is blocked from being Warlord."
                ),
                unit_selection_id=first_required_selection_id,
                source_id=required_source_by_selection_id[first_required_selection_id],
            )
        )
        return
    if warlord_selection.unit_selection_id in set(eligible_required_selection_ids):
        return
    first_eligible_selection_id = eligible_required_selection_ids[0]
    violations.append(
        RosterLegalityViolation(
            violation_code="supreme_commander_warlord_required",
            message=(
                "When one or more eligible Supreme Commander units are in the army, "
                "one of them must be selected as Warlord."
            ),
            unit_selection_id=warlord_selection.unit_selection_id,
            source_id=required_source_by_selection_id[first_eligible_selection_id],
        )
    )


def _datasheet_can_be_selected_warlord(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if not _datasheet_has_keyword(datasheet, "CHARACTER"):
        return False
    if _datasheet_warlord_forbidden_source_id(datasheet) is not None:
        return False
    if _is_daemonic_pact_datasheet(datasheet, faction.faction_keywords):
        return False
    if drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    ):
        return False
    return bool(set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords))


def _datasheet_requires_warlord_source_id(datasheet: DatasheetDefinition) -> str | None:
    for ability in datasheet.abilities:
        value = _ability_mustering_warlord_value(ability)
        if value == MUSTERING_WARLORD_REQUIRED:
            return ability.source_id
    return None


def _datasheet_warlord_forbidden_source_id(datasheet: DatasheetDefinition) -> str | None:
    for ability in datasheet.abilities:
        if _ability_mustering_warlord_value(ability) == MUSTERING_WARLORD_FORBIDDEN:
            return ability.source_id
    return None


def _ability_mustering_warlord_value(ability: DatasheetAbilityDescriptor) -> str | None:
    payload = ability.rule_ir_payload
    if payload is None or MUSTERING_WARLORD_RULE_KEY not in payload:
        return None
    value = payload[MUSTERING_WARLORD_RULE_KEY]
    if type(value) is not str:
        raise ArmyMusteringError("mustering_warlord descriptor value must be a string.")
    if value not in {MUSTERING_WARLORD_REQUIRED, MUSTERING_WARLORD_FORBIDDEN}:
        raise ArmyMusteringError("mustering_warlord descriptor value is unsupported.")
    return value


def _append_enhancement_violations(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    selected_detachment_enhancement_ids: tuple[str, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    enhancement_limit: int,
    violations: list[RosterLegalityViolation],
) -> None:
    effective_enhancement_limit = _effective_enhancement_limit(
        request=request,
        enhancement_limit=enhancement_limit,
    )
    if len(request.detachment_selection.enhancement_ids) > effective_enhancement_limit:
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_limit_exceeded",
                message="Roster exceeds the battle-size Enhancement limit.",
                source_id="phase16d:enhancement-limit",
            )
        )
    selected_ids = set(request.detachment_selection.enhancement_ids)
    detachment_allowed_ids = set(selected_detachment_enhancement_ids)
    catalog_enhancement_by_id = {
        enhancement.enhancement_id: enhancement for enhancement in catalog.enhancements
    }
    attached_group_by_selection_id = _attached_group_by_selection_id(request)
    enhancement_count_by_attached_group: dict[tuple[str, ...], int] = {}
    assignment_count_by_enhancement_id: dict[str, int] = {}
    for assignment in request.enhancement_assignments:
        assignment_count_by_enhancement_id[assignment.enhancement_id] = (
            assignment_count_by_enhancement_id.get(assignment.enhancement_id, 0) + 1
        )
        if assignment.enhancement_id not in selected_ids:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_not_selected",
                    message="EnhancementAssignment must use a selected Enhancement.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        if assignment.enhancement_id not in detachment_allowed_ids:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_not_allowed_by_detachment",
                    message="EnhancementAssignment is not granted by the selected detachment.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        enhancement = catalog_enhancement_by_id.get(assignment.enhancement_id)
        if enhancement is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_unknown",
                    message="EnhancementAssignment references an unknown Enhancement.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        elif enhancement.points is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="source_awaiting_enhancement_points",
                    message="EnhancementAssignment requires source-backed Enhancement points.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=enhancement.source_id,
                )
            )
        datasheet = datasheets_by_selection_id.get(assignment.target_unit_selection_id)
        if datasheet is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_unknown_target",
                    message="EnhancementAssignment target unit selection is unknown.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
            continue
        is_corsair_coterie_enhancement = (
            enhancement is not None
            and _request_uses_corsair_coterie(request)
            and _is_corsair_coterie_enhancement_id(enhancement.enhancement_id)
        )
        is_upgrade = enhancement is not None and _enhancement_is_upgrade(enhancement)
        if is_corsair_coterie_enhancement:
            if enhancement is None:
                raise ArmyMusteringError("Corsair Coterie Enhancement is missing.")
            _append_corsair_coterie_enhancement_target_violations(
                enhancement=enhancement,
                datasheet=datasheet,
                assignment=assignment,
                violations=violations,
            )
        elif is_upgrade and _datasheet_has_keyword(datasheet, "CHARACTER"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="upgrade_character_forbidden",
                    message="Upgrades can be assigned only to non-CHARACTER units.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        elif not is_upgrade and not _datasheet_has_keyword(datasheet, "CHARACTER"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_character_required",
                    message="Enhancements can be assigned only to CHARACTER units.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        if _datasheet_has_keyword(datasheet, "EPIC HERO"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="epic_hero_enhancement_forbidden",
                    message="EPIC HERO units cannot receive Enhancements.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        if enhancement is not None:
            _append_enhancement_target_requirement_violations(
                enhancement=enhancement,
                datasheet=datasheet,
                assignment=assignment,
                violations=violations,
            )
        attached_group = attached_group_by_selection_id.get(assignment.target_unit_selection_id)
        if attached_group is not None:
            enhancement_count_by_attached_group[attached_group] = (
                enhancement_count_by_attached_group.get(attached_group, 0) + 1
            )
    for enhancement_id, assignment_count in assignment_count_by_enhancement_id.items():
        enhancement = catalog_enhancement_by_id.get(enhancement_id)
        if enhancement is None:
            continue
        if _request_uses_corsair_coterie(request) and _is_corsair_coterie_enhancement_id(
            enhancement_id
        ):
            if assignment_count > 1:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="enhancement_repeated_assignment_forbidden",
                        message="A Corsair Enhancement can be assigned to only one unit.",
                        source_id=enhancement.source_id,
                    )
                )
            continue
        if _enhancement_is_upgrade(enhancement):
            if assignment_count > 3:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="upgrade_assignment_limit_exceeded",
                        message="A selected Upgrade can be assigned to at most three units.",
                        source_id=enhancement.source_id,
                    )
                )
            continue
        if assignment_count > 1:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_repeated_assignment_forbidden",
                    message="A standard Enhancement can be assigned to only one unit.",
                    source_id=enhancement.source_id,
                )
            )
    for attached_group, count in enhancement_count_by_attached_group.items():
        if count > 1:
            violations.append(
                RosterLegalityViolation(
                    violation_code="attached_squad_enhancement_limit_exceeded",
                    message="An attached squad can have at most one Enhancement or Upgrade.",
                    unit_selection_id=attached_group[0],
                    source_id="phase16d:attached-squad-enhancement-limit",
                )
            )


def _effective_enhancement_limit(
    *,
    request: ArmyMusterRequest,
    enhancement_limit: int,
) -> int:
    if not _request_uses_corsair_coterie(request):
        return enhancement_limit
    return max(enhancement_limit, len(CORSAIR_COTERIE_ENHANCEMENT_IDS))


def _append_corsair_coterie_enhancement_target_violations(
    *,
    enhancement: EnhancementDefinition,
    datasheet: DatasheetDefinition,
    assignment: EnhancementAssignment,
    violations: list[RosterLegalityViolation],
) -> None:
    if not _datasheet_has_keyword(datasheet, ANHRATHE_KEYWORD):
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_anhrathe_required",
                message="Corsair Enhancements can be assigned only to ANHRATHE units.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    if enhancement.enhancement_id == "archraider" and not _datasheet_has_keyword(
        datasheet, CHARACTER_KEYWORD
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_archraider_character_required",
                message="Archraider can be assigned only to ANHRATHE CHARACTER units.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    if enhancement.enhancement_id == "voidstone" and not _datasheet_has_keyword(
        datasheet, INFANTRY_KEYWORD
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_voidstone_infantry_required",
                message="Voidstone can be assigned only to ANHRATHE INFANTRY units.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )


def _append_enhancement_target_requirement_violations(
    *,
    enhancement: EnhancementDefinition,
    datasheet: DatasheetDefinition,
    assignment: EnhancementAssignment,
    violations: list[RosterLegalityViolation],
) -> None:
    for keyword in enhancement.target_required_keywords:
        if _datasheet_has_keyword(datasheet, keyword):
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_target_keyword_required",
                message="EnhancementAssignment target unit is missing a required keyword.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    for keyword in enhancement.target_required_faction_keywords:
        if _datasheet_has_faction_keyword(datasheet, keyword):
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_target_faction_keyword_required",
                message=(
                    "EnhancementAssignment target unit is missing a required faction keyword."
                ),
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )


def _append_daemonic_pact_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    pact_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id, datasheet in datasheets_by_selection_id.items()
            if _is_daemonic_pact_datasheet(datasheet, faction.faction_keywords)
        )
    )
    if not pact_selection_ids:
        return
    if not any(
        daemonic_pact_datasheet_allowed_for_faction(
            datasheet=datasheets_by_selection_id[selection_id],
            faction=faction,
        )
        for selection_id in pact_selection_ids
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_base_faction_required",
                message=("Daemonic Pact requires a Chaos Knights or Heretic Astartes base army."),
                unit_selection_id=pact_selection_ids[0],
                source_id=DAEMONIC_PACT_SOURCE_ID,
            )
        )
    _append_daemonic_pact_base_model_violations(
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    _append_daemonic_pact_points_violation(
        request=request,
        pact_selection_ids=pact_selection_ids,
        violations=violations,
    )
    _append_daemonic_pact_enhancement_violations(
        request=request,
        pact_selection_ids=pact_selection_ids,
        violations=violations,
    )
    _append_daemonic_pact_god_ratio_violations(
        pact_selection_ids=pact_selection_ids,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )


def _append_daemonic_pact_base_model_violations(
    *,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    invalid_base_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id, datasheet in datasheets_by_selection_id.items()
            if not _is_daemonic_pact_datasheet(datasheet, faction.faction_keywords)
            and not _datasheet_has_any_keyword(datasheet, DAEMONIC_PACT_BASE_KEYWORDS)
        )
    )
    if invalid_base_selection_ids:
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_base_model_keyword_required",
                message=(
                    "Every non-Daemonic Pact model must have the Chaos Knights "
                    "or Heretic Astartes keyword."
                ),
                unit_selection_id=invalid_base_selection_ids[0],
                source_id=DAEMONIC_PACT_SOURCE_ID,
            )
        )


def _append_daemonic_pact_points_violation(
    *,
    request: ArmyMusterRequest,
    pact_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    points_by_selection_id = {point.unit_selection_id: point for point in request.unit_points}
    cap = DAEMONIC_PACT_POINTS_CAP_BY_BATTLE_SIZE.get(request.battle_size)
    if cap is None:
        raise ArmyMusteringError("Daemonic Pact points cap is unavailable for battle size.")
    total = sum(
        points_by_selection_id[selection_id].points
        for selection_id in pact_selection_ids
        if selection_id in points_by_selection_id
    )
    if total > cap:
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_points_limit_exceeded",
                message="Daemonic Pact Legiones Daemonica units exceed the battle-size limit.",
                unit_selection_id=pact_selection_ids[0],
                source_id=DAEMONIC_PACT_SOURCE_ID,
            )
        )


def _append_daemonic_pact_enhancement_violations(
    *,
    request: ArmyMusterRequest,
    pact_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    pact_selection_id_set = set(pact_selection_ids)
    for assignment in request.enhancement_assignments:
        if assignment.target_unit_selection_id not in pact_selection_id_set:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_enhancement_forbidden",
                message="Daemonic Pact Legiones Daemonica units cannot receive Enhancements.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=assignment.source_id,
            )
        )


def _append_daemonic_pact_god_ratio_violations(
    *,
    pact_selection_ids: tuple[str, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    for god_keyword in DAEMONIC_PACT_GOD_KEYWORDS:
        battleline_count = 0
        non_battleline_selection_ids: list[str] = []
        for selection_id in pact_selection_ids:
            datasheet = datasheets_by_selection_id[selection_id]
            if not _datasheet_has_keyword(datasheet, god_keyword):
                continue
            if _datasheet_has_keyword(datasheet, "BATTLELINE"):
                battleline_count += 1
            else:
                non_battleline_selection_ids.append(selection_id)
        if len(non_battleline_selection_ids) <= battleline_count:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_god_ratio_exceeded",
                message=(
                    "Daemonic Pact non-Battleline god-marked units cannot exceed "
                    "Battleline units with the same god keyword."
                ),
                unit_selection_id=sorted(non_battleline_selection_ids)[0],
                source_id=f"{DAEMONIC_PACT_SOURCE_ID}:{_canonical_keyword(god_keyword).lower()}",
            )
        )


def _append_drukhari_corsairs_and_travelling_players_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    allied_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id, datasheet in datasheets_by_selection_id.items()
            if drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
                datasheet=datasheet,
                faction=faction,
            )
        )
    )
    if not allied_selection_ids:
        return
    _append_drukhari_corsairs_and_travelling_players_points_violation(
        request=request,
        allied_selection_ids=allied_selection_ids,
        violations=violations,
    )
    _append_drukhari_corsairs_and_travelling_players_enhancement_violations(
        request=request,
        allied_selection_ids=allied_selection_ids,
        violations=violations,
    )


def _append_drukhari_corsairs_and_travelling_players_points_violation(
    *,
    request: ArmyMusterRequest,
    allied_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    points_by_selection_id = {point.unit_selection_id: point for point in request.unit_points}
    cap = DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_POINTS_CAP_BY_BATTLE_SIZE.get(
        request.battle_size
    )
    if cap is None:
        raise ArmyMusteringError(
            "Corsairs and Travelling Players points cap is unavailable for battle size."
        )
    total = sum(
        points_by_selection_id[selection_id].points
        for selection_id in allied_selection_ids
        if selection_id in points_by_selection_id
    )
    if total > cap:
        violations.append(
            RosterLegalityViolation(
                violation_code=("drukhari_corsairs_and_travelling_players_points_limit_exceeded"),
                message=(
                    "Corsairs and Travelling Players HARLEQUINS and ANHRATHE units "
                    "exceed the battle-size limit."
                ),
                unit_selection_id=allied_selection_ids[0],
                source_id=DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
            )
        )


def _append_drukhari_corsairs_and_travelling_players_enhancement_violations(
    *,
    request: ArmyMusterRequest,
    allied_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    allied_selection_id_set = set(allied_selection_ids)
    for assignment in request.enhancement_assignments:
        if assignment.target_unit_selection_id not in allied_selection_id_set:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="drukhari_corsairs_and_travelling_players_enhancement_forbidden",
                message=(
                    "Corsairs and Travelling Players HARLEQUINS or ANHRATHE units cannot "
                    "receive Enhancements."
                ),
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=assignment.source_id,
            )
        )


def _append_freeblades_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    freeblade_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id, datasheet in datasheets_by_selection_id.items()
            if freeblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction)
        )
    )
    if not freeblade_selection_ids:
        return
    if not all(
        _datasheet_has_any_keyword(datasheet, frozenset({FREEBLADES_REQUIRED_FACTION_KEYWORD}))
        for datasheet in datasheets_by_selection_id.values()
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="freeblades_imperium_army_required",
                message="Freeblades require every model in the army to have the IMPERIUM keyword.",
                unit_selection_id=freeblade_selection_ids[0],
                source_id=FREEBLADES_SOURCE_ID,
            )
        )
    selection_by_id = {
        selection.unit_selection_id: selection for selection in request.unit_selections
    }
    titanic_model_count = _freeblade_keyword_model_count(
        freeblade_selection_ids=freeblade_selection_ids,
        datasheets_by_selection_id=datasheets_by_selection_id,
        selection_by_id=selection_by_id,
        keyword=FREEBLADES_TITANIC_KEYWORD,
    )
    armiger_model_count = _freeblade_keyword_model_count(
        freeblade_selection_ids=freeblade_selection_ids,
        datasheets_by_selection_id=datasheets_by_selection_id,
        selection_by_id=selection_by_id,
        keyword=FREEBLADES_ARMIGER_KEYWORD,
    )
    if (
        titanic_model_count > 1
        or (titanic_model_count > 0 and armiger_model_count > 0)
        or armiger_model_count > 3
    ):
        _append_freeblades_limit_violation(
            freeblade_selection_ids=freeblade_selection_ids,
            violations=violations,
        )
    _append_freeblades_enhancement_violations(
        request=request,
        freeblade_selection_ids=freeblade_selection_ids,
        violations=violations,
    )


def _freeblade_keyword_model_count(
    *,
    freeblade_selection_ids: tuple[str, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    selection_by_id: dict[str, UnitMusterSelection],
    keyword: str,
) -> int:
    count = 0
    for selection_id in freeblade_selection_ids:
        datasheet = datasheets_by_selection_id[selection_id]
        if not _datasheet_has_keyword(datasheet, keyword):
            continue
        selection = selection_by_id.get(selection_id)
        if selection is None:
            raise ArmyMusteringError("Freeblades selection lookup failed.")
        count += _unit_selection_model_count(selection)
    return count


def _append_freeblades_limit_violation(
    *,
    freeblade_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    violations.append(
        RosterLegalityViolation(
            violation_code="freeblades_limit_exceeded",
            message=(
                "Freeblades can include either one TITANIC Imperial Knights model "
                "or up to three ARMIGER models."
            ),
            unit_selection_id=freeblade_selection_ids[0],
            source_id=FREEBLADES_SOURCE_ID,
        )
    )


def _append_freeblades_enhancement_violations(
    *,
    request: ArmyMusterRequest,
    freeblade_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    freeblade_selection_id_set = set(freeblade_selection_ids)
    for assignment in request.enhancement_assignments:
        if assignment.target_unit_selection_id not in freeblade_selection_id_set:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="freeblades_enhancement_forbidden",
                message="Freeblades Imperial Knights models cannot receive Enhancements.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=assignment.source_id,
            )
        )


def _append_shadow_legion_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    if not _request_uses_shadow_legion(request):
        return
    _append_shadow_legion_forbidden_unit_violations(
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )
    heretic_astartes_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id, datasheet in datasheets_by_selection_id.items()
            if _datasheet_has_faction_keyword(
                datasheet,
                SHADOW_LEGION_HERETIC_ASTARTES_KEYWORD,
            )
        )
    )
    for selection_id in heretic_astartes_selection_ids:
        datasheet = datasheets_by_selection_id[selection_id]
        if shadow_legion_thralls_datasheet_allowed_for_faction(
            datasheet=datasheet,
            faction=faction,
            detachment_selection=request.detachment_selection,
        ):
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="shadow_legion_thralls_heretic_astartes_unit_forbidden",
                message="Shadow Legion cannot include this Heretic Astartes datasheet.",
                unit_selection_id=selection_id,
                source_id=SHADOW_LEGION_SOURCE_ID,
            )
        )
    _append_shadow_legion_thralls_points_violation(
        request=request,
        heretic_astartes_selection_ids=heretic_astartes_selection_ids,
        violations=violations,
    )


def _append_shadow_legion_forbidden_unit_violations(
    *,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    for selection_id, datasheet in sorted(datasheets_by_selection_id.items()):
        if _datasheet_is_belakor(datasheet):
            continue
        if not _datasheet_is_shadow_legion_forbidden_unit(datasheet):
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="shadow_legion_forbidden_daemon_prince_or_epic_hero",
                message=(
                    "Shadow Legion cannot include Daemon Prince, Daemon Prince with Wings, "
                    "or Epic Hero units other than Be'lakor."
                ),
                unit_selection_id=selection_id,
                source_id=SHADOW_LEGION_SOURCE_ID,
            )
        )


def _append_shadow_legion_thralls_points_violation(
    *,
    request: ArmyMusterRequest,
    heretic_astartes_selection_ids: tuple[str, ...],
    violations: list[RosterLegalityViolation],
) -> None:
    if not heretic_astartes_selection_ids:
        return
    points_by_selection_id = {point.unit_selection_id: point for point in request.unit_points}
    cap = SHADOW_LEGION_POINTS_CAP_BY_BATTLE_SIZE.get(request.battle_size)
    if cap is None:
        raise ArmyMusteringError("Shadow Legion Thralls points cap is unavailable.")
    total = sum(
        points_by_selection_id[selection_id].points
        for selection_id in heretic_astartes_selection_ids
        if selection_id in points_by_selection_id
    )
    if total > cap:
        violations.append(
            RosterLegalityViolation(
                violation_code="shadow_legion_thralls_points_limit_exceeded",
                message="Shadow Legion Heretic Astartes units exceed the battle-size limit.",
                unit_selection_id=heretic_astartes_selection_ids[0],
                source_id=SHADOW_LEGION_SOURCE_ID,
            )
        )


def _append_space_marine_chapter_violations(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    if not _request_uses_space_marines_chapter_rules(request=request, faction=faction):
        return
    chapter_keywords_by_selection_id = {
        selection_id: _space_marine_chapter_keywords_for_datasheet(datasheet)
        for selection_id, datasheet in datasheets_by_selection_id.items()
        if _datasheet_has_faction_keyword(datasheet, ADEPTUS_ASTARTES_KEYWORD)
    }
    _append_space_marine_multiple_chapter_violations(
        chapter_keywords_by_selection_id=chapter_keywords_by_selection_id,
        violations=violations,
    )
    selected_chapters = frozenset(
        chapter for chapters in chapter_keywords_by_selection_id.values() for chapter in chapters
    )
    if BLACK_TEMPLARS_KEYWORD in selected_chapters:
        _append_black_templars_chapter_violations(
            datasheets_by_selection_id=datasheets_by_selection_id,
            violations=violations,
        )
    if SPACE_WOLVES_KEYWORD in selected_chapters:
        _append_space_wolves_chapter_violations(
            datasheets_by_selection_id=datasheets_by_selection_id,
            violations=violations,
        )
    if DEATHWATCH_KEYWORD in selected_chapters:
        _append_deathwatch_chapter_violations(
            chapter_keywords_by_selection_id=chapter_keywords_by_selection_id,
            datasheets_by_selection_id=datasheets_by_selection_id,
            violations=violations,
        )


def _append_space_marine_multiple_chapter_violations(
    *,
    chapter_keywords_by_selection_id: dict[str, frozenset[str]],
    violations: list[RosterLegalityViolation],
) -> None:
    selected_chapters = {
        chapter for chapters in chapter_keywords_by_selection_id.values() for chapter in chapters
    }
    if len(selected_chapters) <= 1:
        return
    first_selection_id = sorted(
        selection_id
        for selection_id, chapters in chapter_keywords_by_selection_id.items()
        if chapters
    )[0]
    violations.append(
        RosterLegalityViolation(
            violation_code="space_marines_multiple_chapters",
            message=(
                "An Adeptus Astartes army cannot include units drawn from more than one Chapter."
            ),
            unit_selection_id=first_selection_id,
            source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
        )
    )
    for selection_id, chapters in sorted(chapter_keywords_by_selection_id.items()):
        if len(chapters) <= 1:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="space_marines_unit_multiple_chapter_keywords",
                message="A Space Marine datasheet cannot be drawn from more than one Chapter.",
                unit_selection_id=selection_id,
                source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
            )
        )


def _append_black_templars_chapter_violations(
    *,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    for selection_id, datasheet in sorted(datasheets_by_selection_id.items()):
        if _datasheet_has_faction_keyword(
            datasheet, ADEPTUS_ASTARTES_KEYWORD
        ) and _datasheet_has_keyword(datasheet, "PSYKER"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="space_marines_black_templars_psyker_forbidden",
                    message="Black Templars armies cannot include Adeptus Astartes Psyker models.",
                    unit_selection_id=selection_id,
                    source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
                )
            )
        if _canonical_name(datasheet.name) not in BLACK_TEMPLARS_FORBIDDEN_NON_CHAPTER_NAMES:
            continue
        if _datasheet_has_faction_keyword(datasheet, BLACK_TEMPLARS_KEYWORD):
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="space_marines_black_templars_vehicle_keyword_required",
                message=(
                    "Black Templars armies cannot include this vehicle unless it has the "
                    "Black Templars keyword."
                ),
                unit_selection_id=selection_id,
                source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
            )
        )


def _append_space_wolves_chapter_violations(
    *,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    for selection_id, datasheet in sorted(datasheets_by_selection_id.items()):
        if _canonical_name(datasheet.name) not in SPACE_WOLVES_FORBIDDEN_UNIT_NAMES:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="space_marines_space_wolves_unit_forbidden",
                message="Space Wolves armies cannot include this unit.",
                unit_selection_id=selection_id,
                source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
            )
        )


def _append_deathwatch_chapter_violations(
    *,
    chapter_keywords_by_selection_id: dict[str, frozenset[str]],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    for selection_id, datasheet in sorted(datasheets_by_selection_id.items()):
        if _datasheet_has_faction_keyword(
            datasheet, ADEPTUS_ASTARTES_KEYWORD
        ) and DEATHWATCH_KEYWORD not in chapter_keywords_by_selection_id.get(
            selection_id,
            frozenset(),
        ):
            violations.append(
                RosterLegalityViolation(
                    violation_code="space_marines_deathwatch_other_chapter_forbidden",
                    message=(
                        "Deathwatch armies cannot include Adeptus Astartes units drawn "
                        "from any other Chapter."
                    ),
                    unit_selection_id=selection_id,
                    source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
                )
            )
        if (
            _datasheet_has_faction_keyword(datasheet, AGENTS_OF_THE_IMPERIUM_KEYWORD)
            and _datasheet_has_any_keyword(datasheet, frozenset({DEATHWATCH_KEYWORD}))
            and _canonical_name(datasheet.name) not in DEATHWATCH_ALLOWED_AGENTS_UNIT_NAMES
        ):
            violations.append(
                RosterLegalityViolation(
                    violation_code="space_marines_deathwatch_agents_unit_forbidden",
                    message=(
                        "Deathwatch armies cannot include Agents of the Imperium "
                        "Deathwatch units other than Kill Team Cassius."
                    ),
                    unit_selection_id=selection_id,
                    source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
                )
            )
        if _canonical_name(datasheet.name) not in DEATHWATCH_FORBIDDEN_UNIT_NAMES:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="space_marines_deathwatch_unit_forbidden",
                message="Deathwatch armies cannot include this unit.",
                unit_selection_id=selection_id,
                source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
            )
        )


def _request_uses_space_marines_chapter_rules(
    *,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
) -> bool:
    return request.detachment_selection.faction_id == SPACE_MARINES_FACTION_ID or (
        _faction_has_keyword(faction, ADEPTUS_ASTARTES_KEYWORD)
    )


def _space_marine_chapter_inspection_datasheet_for_rejected_selection(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    selection: UnitMusterSelection,
) -> DatasheetDefinition | None:
    if not _request_uses_space_marines_chapter_rules(request=request, faction=faction):
        return None
    for datasheet in catalog.datasheets:
        if datasheet.datasheet_id != selection.datasheet_id:
            continue
        if _datasheet_has_faction_keyword(
            datasheet, AGENTS_OF_THE_IMPERIUM_KEYWORD
        ) and _datasheet_has_any_keyword(datasheet, frozenset({DEATHWATCH_KEYWORD})):
            return datasheet
        return None
    return None


def _space_marine_chapter_keywords_for_datasheet(
    datasheet: DatasheetDefinition,
) -> frozenset[str]:
    return frozenset(
        chapter
        for chapter in SPACE_MARINE_CHAPTER_KEYWORDS
        if _datasheet_has_faction_keyword(datasheet, chapter)
    )


def _datasheet_is_shadow_legion_forbidden_unit(datasheet: DatasheetDefinition) -> bool:
    canonical_name = _canonical_name(datasheet.name)
    if canonical_name in SHADOW_LEGION_FORBIDDEN_DAEMON_PRINCE_NAMES:
        return True
    return _datasheet_has_keyword(datasheet, "EPIC HERO")


def _append_dedicated_transport_manifest_violations(
    *,
    request: ArmyMusterRequest,
    selection_by_id: dict[str, UnitMusterSelection],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    manifest_by_transport_id = {
        manifest.transport_unit_selection_id: manifest
        for manifest in request.dedicated_transport_manifests
    }
    for selection_id, datasheet in datasheets_by_selection_id.items():
        if (
            _datasheet_has_keyword(datasheet, "DEDICATED TRANSPORT")
            and selection_id not in manifest_by_transport_id
        ):
            violations.append(
                RosterLegalityViolation(
                    violation_code="dedicated_transport_missing_starting_cargo",
                    message="Dedicated Transport requires a starting cargo manifest.",
                    unit_selection_id=selection_id,
                    source_id="phase16d:dedicated-transport-manifest",
                )
            )

    cargo_claims: set[str] = set()
    attached_group_by_selection_id = _attached_group_by_selection_id(request)
    for manifest in request.dedicated_transport_manifests:
        transport_datasheet = datasheets_by_selection_id.get(manifest.transport_unit_selection_id)
        if transport_datasheet is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_unknown_transport",
                    message="DedicatedTransportManifest references an unknown Transport.",
                    unit_selection_id=manifest.transport_unit_selection_id,
                    source_id=manifest.source_id,
                )
            )
            continue
        if not _datasheet_has_keyword(transport_datasheet, "TRANSPORT"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_transport_required",
                    message="DedicatedTransportManifest requires a TRANSPORT unit.",
                    unit_selection_id=manifest.transport_unit_selection_id,
                    source_id=manifest.source_id,
                )
            )
        if not _datasheet_has_keyword(transport_datasheet, "DEDICATED TRANSPORT"):
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_dedicated_transport_required",
                    message="DedicatedTransportManifest requires a DEDICATED TRANSPORT unit.",
                    unit_selection_id=manifest.transport_unit_selection_id,
                    source_id=manifest.source_id,
                )
            )
        if manifest.capacity_profile.transport_datasheet_id != transport_datasheet.datasheet_id:
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_capacity_datasheet_drift",
                    message="DedicatedTransportManifest capacity profile datasheet drift.",
                    unit_selection_id=manifest.transport_unit_selection_id,
                    source_id=manifest.capacity_profile.source_id,
                )
            )
        embarked_model_count = 0
        for cargo_selection_id in manifest.embarked_unit_selection_ids:
            cargo_selection = selection_by_id.get(cargo_selection_id)
            cargo_datasheet = datasheets_by_selection_id.get(cargo_selection_id)
            if cargo_selection is None or cargo_datasheet is None:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="transport_manifest_unknown_cargo",
                        message="DedicatedTransportManifest references unknown cargo.",
                        unit_selection_id=cargo_selection_id,
                        source_id=manifest.source_id,
                    )
                )
                continue
            if cargo_selection_id in cargo_claims:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="transport_manifest_duplicate_cargo",
                        message="A unit cannot start embarked in multiple Transports.",
                        unit_selection_id=cargo_selection_id,
                        source_id=manifest.source_id,
                    )
                )
            cargo_claims.add(cargo_selection_id)
            if not _transport_capacity_allows_datasheet(
                manifest.capacity_profile,
                cargo_datasheet,
            ):
                violations.append(
                    RosterLegalityViolation(
                        violation_code="transport_manifest_cargo_ineligible",
                        message="Cargo unit is not eligible for this Transport.",
                        unit_selection_id=cargo_selection_id,
                        source_id=manifest.capacity_profile.source_id,
                    )
                )
            embarked_model_count += _unit_selection_model_count(cargo_selection)
        _append_attached_group_manifest_violations(
            manifest=manifest,
            attached_group_by_selection_id=attached_group_by_selection_id,
            violations=violations,
        )
        if embarked_model_count > manifest.capacity_profile.max_model_count:
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_capacity_exceeded",
                    message="DedicatedTransportManifest exceeds Transport model capacity.",
                    unit_selection_id=manifest.transport_unit_selection_id,
                    source_id=manifest.capacity_profile.source_id,
                )
            )


def _append_attached_group_manifest_violations(
    *,
    manifest: DedicatedTransportManifest,
    attached_group_by_selection_id: dict[str, tuple[str, ...]],
    violations: list[RosterLegalityViolation],
) -> None:
    manifest_cargo = set(manifest.embarked_unit_selection_ids)
    checked_groups: set[tuple[str, ...]] = set()
    for cargo_selection_id in manifest.embarked_unit_selection_ids:
        group = attached_group_by_selection_id.get(cargo_selection_id)
        if group is None or group in checked_groups:
            continue
        checked_groups.add(group)
        if not set(group) <= manifest_cargo:
            violations.append(
                RosterLegalityViolation(
                    violation_code="transport_manifest_attached_unit_incomplete",
                    message="Attached rules units must embark as a complete component group.",
                    unit_selection_id=group[0],
                    source_id=manifest.source_id,
                )
            )


def _apply_warlord_keyword_if_selected(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
    roster_legality_report: RosterLegalityReport,
) -> tuple[UnitInstance, ...]:
    if request.warlord_selection is None:
        return units
    if any(
        _warlord_violation_blocks_keyword(violation)
        for violation in roster_legality_report.violations
    ):
        return units
    target_unit_id = f"{request.army_id}:{request.warlord_selection.unit_selection_id}"
    return tuple(
        replace(unit, keywords=tuple(sorted({*unit.keywords, "WARLORD"})))
        if unit.unit_instance_id == target_unit_id
        else unit
        for unit in units
    )


def _warlord_violation_blocks_keyword(violation: RosterLegalityViolation) -> bool:
    if type(violation) is not RosterLegalityViolation:
        raise ArmyMusteringError("Warlord violation lookup requires a RosterLegalityViolation.")
    return (
        violation.violation_code == "missing_warlord_selection"
        or violation.violation_code.startswith("warlord_")
        or violation.violation_code.endswith("_warlord_forbidden")
        or violation.violation_code.startswith("supreme_commander_warlord")
    )


def _apply_shadow_legion_keyword_grants(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
) -> tuple[UnitInstance, ...]:
    if not _request_uses_shadow_legion(request):
        return units
    granted_units: list[UnitInstance] = []
    for unit in units:
        added_keywords: list[str] = []
        if _unit_has_faction_keyword(unit, SHADOW_LEGION_LEGIONES_DAEMONICA_KEYWORD):
            added_keywords.append(SHADOW_LEGION_KEYWORD)
        if _unit_is_belakor(unit) or _unit_has_faction_keyword(
            unit,
            SHADOW_LEGION_HERETIC_ASTARTES_KEYWORD,
        ):
            added_keywords.extend((SHADOW_LEGION_KEYWORD, SHADOW_LEGION_UNDIVIDED_KEYWORD))
        if _unit_has_faction_keyword(unit, SHADOW_LEGION_HERETIC_ASTARTES_KEYWORD):
            added_keywords.append(SHADOW_LEGION_DEEP_STRIKE_KEYWORD)
        if not added_keywords:
            granted_units.append(unit)
            continue
        granted_units.append(
            replace(
                unit,
                keywords=tuple(sorted(dict.fromkeys((*unit.keywords, *added_keywords)))),
            )
        )
    return tuple(granted_units)


def _attached_group_by_selection_id(
    request: ArmyMusterRequest,
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = {}
    for declaration in request.attachment_declarations:
        group = grouped.setdefault(declaration.bodyguard_unit_selection_id, set())
        group.add(declaration.bodyguard_unit_selection_id)
        group.add(declaration.source_unit_selection_id)
    by_selection_id: dict[str, tuple[str, ...]] = {}
    for group in grouped.values():
        group_tuple = tuple(sorted(group))
        for selection_id in group_tuple:
            by_selection_id[selection_id] = group_tuple
    return by_selection_id


def _transport_capacity_allows_datasheet(
    capacity_profile: DedicatedTransportCapacityProfile,
    datasheet: DatasheetDefinition,
) -> bool:
    if type(capacity_profile) is not DedicatedTransportCapacityProfile:
        raise ArmyMusteringError(
            "Transport capacity check requires DedicatedTransportCapacityProfile."
        )
    if type(datasheet) is not DatasheetDefinition:
        raise ArmyMusteringError("Transport capacity check requires DatasheetDefinition.")
    unit_keywords = {_canonical_keyword(keyword) for keyword in datasheet.keywords.keywords}
    allowed = {_canonical_keyword(keyword) for keyword in capacity_profile.allowed_keywords}
    excluded = {_canonical_keyword(keyword) for keyword in capacity_profile.excluded_keywords}
    if allowed and not unit_keywords.intersection(allowed):
        return False
    return not unit_keywords.intersection(excluded)


def _unit_selection_model_count(selection: UnitMusterSelection) -> int:
    if type(selection) is not UnitMusterSelection:
        raise ArmyMusteringError("Model-count lookup requires UnitMusterSelection.")
    return sum(part.model_count for part in selection.model_profile_selections)


def _datasheet_has_keyword(datasheet: DatasheetDefinition, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {
        _canonical_keyword(stored_keyword) for stored_keyword in datasheet.keywords.keywords
    }


def _datasheet_has_faction_keyword(datasheet: DatasheetDefinition, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {
        _canonical_keyword(stored_keyword) for stored_keyword in datasheet.keywords.faction_keywords
    }


def _datasheet_has_any_keyword(
    datasheet: DatasheetDefinition,
    keywords: frozenset[str],
) -> bool:
    requested_keywords = {_canonical_keyword(keyword) for keyword in keywords}
    stored_keywords = {
        _canonical_keyword(stored_keyword)
        for stored_keyword in (
            *datasheet.keywords.keywords,
            *datasheet.keywords.faction_keywords,
        )
    }
    return bool(requested_keywords & stored_keywords)


def _faction_has_keyword(faction: FactionDefinition, keyword: str) -> bool:
    if type(faction) is not FactionDefinition:
        raise ArmyMusteringError("Faction keyword lookup requires FactionDefinition.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {
        _canonical_keyword(stored_keyword) for stored_keyword in faction.faction_keywords
    }


def _is_daemonic_pact_datasheet(
    datasheet: DatasheetDefinition,
    selected_faction_keywords: tuple[str, ...],
) -> bool:
    if not _datasheet_has_faction_keyword(datasheet, DAEMONIC_PACT_FACTION_KEYWORD):
        return False
    selected_keywords = {_canonical_keyword(keyword) for keyword in selected_faction_keywords}
    datasheet_faction_keywords = {
        _canonical_keyword(keyword) for keyword in datasheet.keywords.faction_keywords
    }
    return not bool(selected_keywords & datasheet_faction_keywords)


def _enhancement_is_upgrade(enhancement: EnhancementDefinition) -> bool:
    return EnhancementSubtype.UPGRADE in enhancement.subtypes


def _request_uses_corsair_coterie(request: ArmyMusterRequest) -> bool:
    return (
        request.detachment_selection.faction_id == AELDARI_FACTION_ID
        and CORSAIR_COTERIE_DETACHMENT_ID in request.detachment_selection.detachment_ids
    )


def _is_corsair_coterie_enhancement_id(enhancement_id: str) -> bool:
    return enhancement_id in CORSAIR_COTERIE_ENHANCEMENT_IDS


def _request_uses_shadow_legion(request: ArmyMusterRequest) -> bool:
    return (
        request.detachment_selection.faction_id == SHADOW_LEGION_FACTION_ID
        and SHADOW_LEGION_DETACHMENT_ID in request.detachment_selection.detachment_ids
    )


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {
        _canonical_keyword(stored_keyword) for stored_keyword in unit.faction_keywords
    }


def _unit_is_belakor(unit: UnitInstance) -> bool:
    return _canonical_name(unit.name) == SHADOW_LEGION_BELAKOR_NAME


def _datasheet_is_belakor(datasheet: DatasheetDefinition) -> bool:
    return _canonical_name(datasheet.name) == SHADOW_LEGION_BELAKOR_NAME


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace("_", " ")


def _canonical_name(value: str) -> str:
    return "".join(
        character
        for character in _validate_identifier("name", value).upper()
        if character.isalnum()
    )


def _roster_violation_sort_key(
    violation: RosterLegalityViolation,
) -> tuple[str, str, str, str]:
    return (
        violation.violation_code,
        "" if violation.unit_selection_id is None else violation.unit_selection_id,
        "" if violation.source_id is None else violation.source_id,
        violation.message,
    )


def _resolve_attached_unit_formations(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
) -> tuple[tuple[UnitInstance, ...], tuple[AttachedUnitFormation, ...]]:
    if not request.attachment_declarations:
        _validate_required_support_attachments(
            request=request,
            datasheets_by_selection_id=datasheets_by_selection_id,
            attached_source_selection_ids=set(),
        )
        return units, ()
    units_by_selection_id = {
        unit.unit_instance_id.removeprefix(f"{request.army_id}:"): unit for unit in units
    }
    grouped: dict[str, dict[AttachmentRole, UnitInstance]] = {}
    for declaration in request.attachment_declarations:
        source_unit = units_by_selection_id.get(declaration.source_unit_selection_id)
        bodyguard_unit = units_by_selection_id.get(declaration.bodyguard_unit_selection_id)
        if source_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration source unit was not mustered.")
        if bodyguard_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration bodyguard unit was not mustered.")
        source_datasheet = datasheets_by_selection_id[declaration.source_unit_selection_id]
        bodyguard_datasheet = datasheets_by_selection_id[declaration.bodyguard_unit_selection_id]
        eligibility = _attachment_eligibility_for_datasheet(source_datasheet)
        if bodyguard_datasheet.datasheet_id not in eligibility.allowed_bodyguard_datasheet_ids:
            raise ArmyMusteringError(
                "AttachmentDeclaration bodyguard datasheet is not allowed by source datasheet."
            )
        role_group = grouped.setdefault(declaration.bodyguard_unit_selection_id, {})
        if eligibility.role in role_group:
            raise ArmyMusteringError(
                "AttachmentDeclaration exceeds one Leader or one Support per bodyguard."
            )
        role_group[eligibility.role] = source_unit

    _validate_required_support_attachments(
        request=request,
        datasheets_by_selection_id=datasheets_by_selection_id,
        attached_source_selection_ids={
            declaration.source_unit_selection_id for declaration in request.attachment_declarations
        },
    )

    formations: list[AttachedUnitFormation] = []
    roles_by_unit_id: dict[str, str] = {}
    claimed_component_ids: set[str] = set()
    for bodyguard_selection_id in sorted(grouped):
        bodyguard_unit = units_by_selection_id[bodyguard_selection_id]
        role_group = grouped[bodyguard_selection_id]
        leader_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, unit in role_group.items()
                if role is AttachmentRole.LEADER
            )
        )
        support_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, unit in role_group.items()
                if role is AttachmentRole.SUPPORT
            )
        )
        component_ids = tuple(sorted((bodyguard_unit.unit_instance_id, *leader_ids, *support_ids)))
        overlap = claimed_component_ids.intersection(component_ids)
        if overlap:
            raise ArmyMusteringError(
                "AttachmentDeclaration cannot place a unit in multiple attached units."
            )
        claimed_component_ids.update(component_ids)
        attached_unit_id = f"attached-unit:{request.army_id}:{bodyguard_selection_id}"
        source_id = f"attached-unit-join:{request.army_id}:{bodyguard_selection_id}"
        formations.append(
            AttachedUnitFormation(
                attached_unit_instance_id=attached_unit_id,
                bodyguard_unit_instance_id=bodyguard_unit.unit_instance_id,
                leader_unit_instance_ids=leader_ids,
                support_unit_instance_ids=support_ids,
                component_unit_instance_ids=component_ids,
                source_id=source_id,
            )
        )
        roles_by_unit_id[bodyguard_unit.unit_instance_id] = "bodyguard"
        for unit_id in leader_ids:
            roles_by_unit_id[unit_id] = "leader"
        for unit_id in support_ids:
            roles_by_unit_id[unit_id] = "support"

    return (
        tuple(
            _unit_with_attached_role_evidence(
                unit,
                role=roles_by_unit_id.get(unit.unit_instance_id),
            )
            for unit in units
        ),
        tuple(sorted(formations, key=lambda formation: formation.attached_unit_instance_id)),
    )


def _validate_required_support_attachments(
    *,
    request: ArmyMusterRequest,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    attached_source_selection_ids: set[str],
) -> None:
    for selection in request.unit_selections:
        datasheet = datasheets_by_selection_id[selection.unit_selection_id]
        if (
            _datasheet_has_attachment_role(datasheet=datasheet, role=AttachmentRole.SUPPORT)
            and selection.unit_selection_id not in attached_source_selection_ids
        ):
            raise ArmyMusteringError(
                "Support units must be declared as part of an attached unit during mustering."
            )


def _datasheet_has_attachment_role(
    *,
    datasheet: DatasheetDefinition,
    role: AttachmentRole,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ArmyMusteringError("Attachment role lookup requires a DatasheetDefinition.")
    if type(role) is not AttachmentRole:
        raise ArmyMusteringError("Attachment role lookup requires an AttachmentRole.")
    return any(eligibility.role is role for eligibility in datasheet.attachment_eligibilities)


def _attachment_eligibility_for_datasheet(
    datasheet: DatasheetDefinition,
) -> AttachmentEligibility:
    if type(datasheet) is not DatasheetDefinition:
        raise ArmyMusteringError("Attachment eligibility lookup requires a DatasheetDefinition.")
    eligibilities: tuple[AttachmentEligibility, ...] = datasheet.attachment_eligibilities
    if not eligibilities:
        raise ArmyMusteringError(
            "AttachmentDeclaration source datasheet has no attachment eligibility."
        )
    if len(eligibilities) > 1:
        raise ArmyMusteringError(
            "AttachmentDeclaration source datasheet must declare exactly one attachment role."
        )
    for eligibility in eligibilities:
        return eligibility
    raise ArmyMusteringError(
        "AttachmentDeclaration source datasheet has no attachment eligibility."
    )


def _unit_with_attached_role_evidence(
    unit: UnitInstance,
    *,
    role: str | None,
) -> UnitInstance:
    if role is None:
        return unit
    evidence = {f"runtime-attached-unit:{role}"}
    if role in {"leader", "support"}:
        evidence.add(f"attached-role:{role}")
    return replace(
        unit,
        keywords=tuple(sorted({*unit.keywords, "ATTACHED_UNIT"})),
        own_models=tuple(
            replace(
                model,
                source_ids=tuple(sorted({*model.source_ids, *evidence})),
            )
            for model in unit.own_models
        ),
    )


def _validate_request_matches_catalog(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
) -> None:
    if request.catalog_id != catalog.catalog_id:
        raise ArmyMusteringError("ArmyMusterRequest catalog_id does not match catalog.")
    if request.source_package_id != catalog.source_package_id:
        raise ArmyMusteringError("ArmyMusterRequest source_package_id does not match catalog.")
    if request.ruleset_id != catalog.ruleset_id:
        raise ArmyMusteringError("ArmyMusterRequest ruleset_id does not match catalog.")


def _ruleset_id_from_payload(payload: RulesetIdPayload) -> RulesetId:
    try:
        return RulesetId.from_payload(payload)
    except RulesetError as exc:
        raise ArmyMusteringError("ruleset_id payload is invalid.") from exc


def _battle_size_from_token(token: object) -> BattleSize:
    try:
        return battle_size_from_token(token)
    except ListValidationError as exc:
        raise ArmyMusteringError("battle_size token is invalid.") from exc


def _unit_instance_from_payload(payload: UnitInstancePayload) -> UnitInstance:
    try:
        return UnitInstance.from_payload(payload)
    except UnitFactoryError as exc:
        raise ArmyMusteringError("ArmyDefinition unit payload is invalid.") from exc


def _validate_unit_muster_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitMusterSelection, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    validated: list[UnitMusterSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not UnitMusterSelection:
            raise ArmyMusteringError(f"{field_name} must contain UnitMusterSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_attachment_declaration_tuple(
    field_name: str,
    values: object,
) -> tuple[AttachmentDeclaration, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[AttachmentDeclaration] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not AttachmentDeclaration:
            raise ArmyMusteringError(f"{field_name} must contain AttachmentDeclaration values.")
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda declaration: (
                declaration.bodyguard_unit_selection_id,
                declaration.source_unit_selection_id,
            ),
        )
    )


def _validate_roster_unit_point_tuple(
    field_name: str,
    values: object,
) -> tuple[RosterUnitPointValue, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[RosterUnitPointValue] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RosterUnitPointValue:
            raise ArmyMusteringError(f"{field_name} must contain RosterUnitPointValue values.")
        validated.append(value)
    return tuple(sorted(validated, key=lambda point: point.unit_selection_id))


def _validate_enhancement_assignment_tuple(
    field_name: str,
    values: object,
) -> tuple[EnhancementAssignment, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[EnhancementAssignment] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not EnhancementAssignment:
            raise ArmyMusteringError(f"{field_name} must contain EnhancementAssignment values.")
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda assignment: (
                assignment.target_unit_selection_id,
                assignment.enhancement_id,
            ),
        )
    )


def _validate_optional_warlord_selection(value: object | None) -> WarlordSelection | None:
    if value is None:
        return None
    if type(value) is not WarlordSelection:
        raise ArmyMusteringError("warlord_selection must be a WarlordSelection.")
    return value


def _validate_dedicated_transport_manifest_tuple(
    field_name: str,
    values: object,
) -> tuple[DedicatedTransportManifest, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[DedicatedTransportManifest] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DedicatedTransportManifest:
            raise ArmyMusteringError(
                f"{field_name} must contain DedicatedTransportManifest values."
            )
        validated.append(value)
    return tuple(sorted(validated, key=lambda manifest: manifest.transport_unit_selection_id))


def _validate_roster_legality_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[RosterLegalityViolation, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[RosterLegalityViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RosterLegalityViolation:
            raise ArmyMusteringError(f"{field_name} must contain RosterLegalityViolation values.")
        validated.append(value)
    return tuple(sorted(validated, key=_roster_violation_sort_key))


def _validate_unique_unit_selection_ids(selections: tuple[UnitMusterSelection, ...]) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.unit_selection_id in seen:
            raise ArmyMusteringError("ArmyMusterRequest unit_selections must have unique IDs.")
        seen.add(selection.unit_selection_id)


def _validate_unique_attachment_source_ids(
    declarations: tuple[AttachmentDeclaration, ...],
) -> None:
    seen: set[str] = set()
    for declaration in declarations:
        if declaration.source_unit_selection_id in seen:
            raise ArmyMusteringError(
                "ArmyMusterRequest attachment_declarations must have unique source unit IDs."
            )
        seen.add(declaration.source_unit_selection_id)


def _validate_unique_roster_unit_points(points: tuple[RosterUnitPointValue, ...]) -> None:
    seen: set[str] = set()
    for point in points:
        if point.unit_selection_id in seen:
            raise ArmyMusteringError("RosterUnitPointValue values must be unique by unit.")
        seen.add(point.unit_selection_id)


def _validate_unique_enhancement_assignments(
    assignments: tuple[EnhancementAssignment, ...],
) -> None:
    seen_targets: set[str] = set()
    for assignment in assignments:
        if assignment.target_unit_selection_id in seen_targets:
            raise ArmyMusteringError(
                "EnhancementAssignment target units must not receive multiple Enhancements "
                "or Upgrades."
            )
        seen_targets.add(assignment.target_unit_selection_id)


def _validate_unique_dedicated_transport_manifests(
    manifests: tuple[DedicatedTransportManifest, ...],
) -> None:
    seen_transports: set[str] = set()
    seen_cargo: set[str] = set()
    for manifest in manifests:
        if manifest.transport_unit_selection_id in seen_transports:
            raise ArmyMusteringError(
                "DedicatedTransportManifest values must be unique by Transport."
            )
        seen_transports.add(manifest.transport_unit_selection_id)
        for cargo_unit_selection_id in manifest.embarked_unit_selection_ids:
            if cargo_unit_selection_id in seen_cargo:
                raise ArmyMusteringError(
                    "DedicatedTransportManifest cargo units must not be duplicated."
                )
            seen_cargo.add(cargo_unit_selection_id)


def _validate_unit_instance_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitInstance, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    validated: list[UnitInstance] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not UnitInstance:
            raise ArmyMusteringError(f"{field_name} must contain UnitInstance values.")
        validated.append(value)
    return tuple(validated)


def _validate_attached_unit_formation_tuple(
    field_name: str,
    values: object,
) -> tuple[AttachedUnitFormation, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[AttachedUnitFormation] = []
    seen_ids: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not AttachedUnitFormation:
            raise ArmyMusteringError(f"{field_name} must contain AttachedUnitFormation values.")
        if value.attached_unit_instance_id in seen_ids:
            raise ArmyMusteringError(f"{field_name} must not contain duplicate attached IDs.")
        seen_ids.add(value.attached_unit_instance_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda formation: formation.attached_unit_instance_id))


def _validate_unique_unit_instance_ids(units: tuple[UnitInstance, ...]) -> None:
    seen: set[str] = set()
    for unit in units:
        if unit.unit_instance_id in seen:
            raise ArmyMusteringError("ArmyDefinition units must have unique IDs.")
        seen.add(unit.unit_instance_id)


def _validate_attached_unit_formations_reference_units(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...],
) -> None:
    requested_army_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
    unit_ids = {unit.unit_instance_id for unit in units}
    claimed_component_ids: set[str] = set()
    for attached_unit in attached_units:
        if not attached_unit.attached_unit_instance_id.startswith(
            f"attached-unit:{requested_army_id}:"
        ):
            raise ArmyMusteringError("AttachedUnitFormation attached ID must be scoped to army_id.")
        if attached_unit.attached_unit_instance_id in unit_ids:
            raise ArmyMusteringError("AttachedUnitFormation identity must not be a physical unit.")
        for component_id in attached_unit.component_unit_instance_ids:
            if component_id not in unit_ids:
                raise ArmyMusteringError("AttachedUnitFormation references an unknown unit.")
            if component_id in claimed_component_ids:
                raise ArmyMusteringError("AttachedUnitFormation component units must not overlap.")
            claimed_component_ids.add(component_id)


def _validate_unit_ids_scoped_to_army(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
) -> None:
    for unit in units:
        if not unit.unit_instance_id.startswith(f"{army_id}:"):
            raise ArmyMusteringError("ArmyDefinition unit IDs must be scoped to army_id.")


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ArmyMusteringError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ArmyMusteringError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier_tuple(
    field_name: str,
    values: object,
    prefix: str,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_unprefixed_identifier(f"{field_name} value", value, prefix)
        if identifier in seen:
            raise ArmyMusteringError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ArmyMusteringError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_attached_unit_instance_id(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if not identifier.startswith("attached-unit:"):
        raise ArmyMusteringError(f"{field_name} must use attached-unit identity.")
    return identifier


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ArmyMusteringError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_optional_unprefixed_identifier(
    field_name: str,
    value: object | None,
    prefix: str,
) -> str | None:
    if value is None:
        return None
    return _validate_unprefixed_identifier(field_name, value, prefix)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ArmyMusteringError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    return stripped


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ArmyMusteringError(f"{field_name} must be a bool.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ArmyMusteringError(f"{field_name} must be an integer.")
    if value < 1:
        raise ArmyMusteringError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ArmyMusteringError(f"{field_name} must be an integer.")
    if value < 0:
        raise ArmyMusteringError(f"{field_name} must not be negative.")
    return value
