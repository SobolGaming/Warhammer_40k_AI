from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.core.faction_aliases import (
    ADEPTUS_CUSTODES_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryMeasurementKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
    ModelGeometryCatalogRecord,
)
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword
from warhammer40k_core.engine import cult_ambush as genestealer_cults_cult_ambush
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageAbilityDatasheetPairPayload,
    AbilityCoverageCategoryRowPayload,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_from_catalog,
    ability_coverage_rows_payload,
)
from warhammer40k_core.engine.army_mustering import (
    CULT_OF_DARK_GODS_SOURCE_ID,
    DAEMONIC_PACT_SOURCE_ID,
    DREADBLADES_SOURCE_ID,
    DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
    FREEBLADES_SOURCE_ID,
    SHADOW_LEGION_SOURCE_ID,
    SPACE_MARINE_CHAPTERS_SOURCE_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_registered_hook_ids
from warhammer40k_core.engine.faction_content.bundle import (
    DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentModuleFamily,
    RuntimeContentSemanticStatus,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule as adepta_sororitas_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_custodes import (
    army_rule as adeptus_custodes_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_mechanicus import (
    army_rule as adeptus_mechanicus_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.astra_militarum import (
    army_rule as astra_militarum_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.black_templars import (
    army_rule as black_templars_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
    army_rule as chaos_knights_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as chaos_space_marines_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule as death_guard_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import (
    army_rule as drukhari_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule as emperors_children_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.generated_manifest import (
    generated_runtime_content_rows,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
    army_rule as imperial_knights_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.leagues_of_votann import (
    army_rule as leagues_of_votann_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.orks import (
    army_rule as orks_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.space_marines import (
    army_rule as space_marines_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tau_empire import (
    army_rule as tau_empire_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    army_rule as thousand_sons_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tyranids import (
    army_rule as tyranids_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import apply_source_release_overlays
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_defiler_datasheet_overlay_2026_06 as chaos_defiler_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_detachments_2026_27,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageRow,
    Phase17ECoverageStatus,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
    CHAOS_DEFILER_HEIGHT_OVERRIDES,
)
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

DEFAULT_SOURCE_JSON_DIR = (
    Path("data")
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
DEFAULT_OUTPUT_DIR = Path("data") / "generated" / "ability_coverage"
DEFAULT_DOCS_PATH = Path("docs") / "ABILITY_SUPPORT_MATRIX_V2.md"
DEFAULT_FACTION_DOCS_DIR = Path("docs") / "factions"
GENERATED_BY_COMMAND = "uv run python tools/generate_ability_support_matrix.py"
RUNTIME_CONTENT_SEMANTIC_COVERAGE_SCHEMA_VERSION = "runtime-content-semantic-coverage-v1"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
DAEMON_WARGEAR_DATASHEET_IDS = ("000001112", "000001114", "000001115")
CHAOS_DEFILER_DATASHEET_IDS = chaos_defiler_overlay.DEFILER_DATASHEET_IDS
ABILITY_SUPPORT_DATASHEET_IDS = (*DAEMON_WARGEAR_DATASHEET_IDS, *CHAOS_DEFILER_DATASHEET_IDS)
DATASHEET_SUPPORT_FULL = "Full"
DATASHEET_SUPPORT_PLAYABLE = "Playable"
DATASHEET_SUPPORT_PARTIAL = "Partial"
DATASHEET_SUPPORT_CATALOG_ONLY = "Catalog-only"
DATASHEET_SUPPORT_BLOCKED = "Blocked"
DATASHEET_SUPPORT_UNKNOWN = "Unknown"
DATASHEET_SUPPORT_NONE = "None"
DATASHEET_SUPPORT_OVERALL_VALUES = frozenset(
    (
        DATASHEET_SUPPORT_FULL,
        DATASHEET_SUPPORT_PLAYABLE,
        DATASHEET_SUPPORT_PARTIAL,
        DATASHEET_SUPPORT_CATALOG_ONLY,
        DATASHEET_SUPPORT_BLOCKED,
        DATASHEET_SUPPORT_UNKNOWN,
    )
)
DATASHEET_SUPPORT_COMPONENT_VALUES = frozenset(
    (*DATASHEET_SUPPORT_OVERALL_VALUES, DATASHEET_SUPPORT_NONE)
)
MUSTERING_SUPPORT_FULL = "full"
MUSTERING_SUPPORT_PARTIAL = "partial"
MUSTERING_SUPPORT_SOURCE_ONLY = "source_only"
MUSTERING_SUPPORT_UNKNOWN = "unknown"
MUSTERING_SUPPORT_STAGE_VALUES = frozenset(
    (
        MUSTERING_SUPPORT_FULL,
        MUSTERING_SUPPORT_PARTIAL,
        MUSTERING_SUPPORT_SOURCE_ONLY,
        MUSTERING_SUPPORT_UNKNOWN,
    )
)
_FACTION_INDEX_ENGINE_CONSUMED_KINDS = frozenset(
    (
        Phase17ECoverageKind.FACTION_ARMY_RULE,
        Phase17ECoverageKind.DETACHMENT_RULE,
        Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
        Phase17ECoverageKind.DETACHMENT_STRATAGEM,
    )
)
_DATASHEET_ABILITY_FULL_STAGES = frozenset((AbilityCoverageSupportStage.ENGINE_CONSUMED,))
_DATASHEET_ABILITY_PLAYABLE_STAGES = frozenset((AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE,))
_DATASHEET_ABILITY_PARTIAL_STAGES = frozenset((AbilityCoverageSupportStage.DESCRIPTOR_ONLY,))
_DATASHEET_ABILITY_BLOCKING_STAGES = frozenset(
    (AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED,)
)
_SUPPORTED_WEAPON_KEYWORDS = frozenset(WeaponKeyword)
_SUPPORTED_WEAPON_ABILITY_KINDS = frozenset(AbilityKind)
REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)
BLOODLETTERS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000001114",
        model_name="Bloodreaper",
        height=1.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:bloodletters:bloodreaper:height",
        height_document_reference="Chaos Daemons Faction Pack p.28-29",
    ),
    ModelHeightOverride(
        datasheet_id="000001114",
        model_name="Bloodletters",
        height=1.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:bloodletters:bloodletters:height",
        height_document_reference="Chaos Daemons Faction Pack p.28-29",
    ),
)
FLESH_HOUNDS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000001112",
        model_name="Gore Hound",
        height=1.6,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:flesh-hounds:gore-hound:height",
        height_document_reference="Chaos Daemons Faction Pack p.26",
    ),
    ModelHeightOverride(
        datasheet_id="000001112",
        model_name="Flesh Hounds",
        height=1.6,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:flesh-hounds:height",
        height_document_reference="Chaos Daemons Faction Pack p.26",
    ),
)


@dataclass(frozen=True)
class SupportSectionRow:
    subject: str
    engine: str
    documentation: str
    tests: str
    overall: str
    notes: str


@dataclass(frozen=True)
class DetachmentRuleSupportRow:
    faction_id: str
    detachment_id: str
    faction: str
    detachment: str
    engine: str
    documentation: str
    tests: str
    overall: str
    notes: str


@dataclass(frozen=True)
class DatasheetGroupReviewRow:
    datasheet: str
    datasheet_id: str
    source_basis: str
    ir_coverage: str
    supported_semantics: str
    semantics_needed: str
    catalog_blockers: str


@dataclass(frozen=True)
class ChaosDaemonsDatasheetReviewGroup:
    allegiance: str
    rows: tuple[DatasheetGroupReviewRow, ...]


@dataclass(frozen=True)
class RuntimeHookInventoryRow:
    hook_id: str
    ability_or_rule_labels: tuple[str, ...]


class RuntimeContentSemanticStatusCountsPayload(TypedDict):
    placeholder: int
    partial: int
    implemented: int


class RuntimeContentDetachmentSemanticCoveragePayload(TypedDict):
    detachment_id: str
    detachment_name: str
    semantic_status: str
    execution_record_count: int
    source_ids: list[str]
    module_path: str


class RuntimeContentFactionSemanticCoveragePayload(TypedDict):
    faction_id: str
    faction_name: str
    semantic_status: str
    execution_record_count: int
    source_ids: list[str]
    module_path: str
    detachment_status_counts: RuntimeContentSemanticStatusCountsPayload
    detachments: list[RuntimeContentDetachmentSemanticCoveragePayload]


class RuntimeContentSemanticCoveragePayload(TypedDict):
    schema_version: str
    source_package_id: str
    source_package_hash: str
    faction_status_counts: RuntimeContentSemanticStatusCountsPayload
    detachment_status_counts: RuntimeContentSemanticStatusCountsPayload
    factions: list[RuntimeContentFactionSemanticCoveragePayload]


class MusteringSupportRowPayload(TypedDict):
    rule_id: str
    display_name: str
    faction_id: str | None
    allowed_base_faction_ids: list[str]
    source_id: str
    enforcement_surface: str
    support_stage: str
    enforcement_id: str
    tests_evidence: str
    notes: str


@dataclass(frozen=True)
class MusteringSupportRow:
    rule_id: str
    display_name: str
    faction_id: str | None
    allowed_base_faction_ids: tuple[str, ...]
    source_id: str
    enforcement_surface: str
    support_stage: str
    enforcement_id: str
    tests_evidence: str
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_mustering_text("MusteringSupportRow rule_id", self.rule_id),
        )
        if not self.rule_id.startswith("army-mustering:"):
            raise ValueError("MusteringSupportRow rule_id must use army-mustering namespace.")
        object.__setattr__(
            self,
            "display_name",
            _validate_mustering_text("MusteringSupportRow display_name", self.display_name),
        )
        if self.faction_id is not None:
            object.__setattr__(
                self,
                "faction_id",
                _validate_mustering_text("MusteringSupportRow faction_id", self.faction_id),
            )
        object.__setattr__(
            self,
            "allowed_base_faction_ids",
            _validate_mustering_text_tuple(
                "MusteringSupportRow allowed_base_faction_ids",
                self.allowed_base_faction_ids,
            ),
        )
        if self.faction_id is None and not self.allowed_base_faction_ids:
            raise ValueError("MusteringSupportRow requires faction_id or allowed_base_faction_ids.")
        object.__setattr__(
            self,
            "source_id",
            _validate_mustering_text("MusteringSupportRow source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "enforcement_surface",
            _validate_mustering_text(
                "MusteringSupportRow enforcement_surface",
                self.enforcement_surface,
            ),
        )
        object.__setattr__(
            self,
            "support_stage",
            _validate_mustering_support_stage(self.support_stage),
        )
        object.__setattr__(
            self,
            "enforcement_id",
            _validate_mustering_text("MusteringSupportRow enforcement_id", self.enforcement_id),
        )
        object.__setattr__(
            self,
            "tests_evidence",
            _validate_mustering_text("MusteringSupportRow tests_evidence", self.tests_evidence),
        )
        object.__setattr__(
            self,
            "notes",
            _validate_mustering_text("MusteringSupportRow notes", self.notes),
        )

    def to_payload(self) -> MusteringSupportRowPayload:
        return {
            "rule_id": self.rule_id,
            "display_name": self.display_name,
            "faction_id": self.faction_id,
            "allowed_base_faction_ids": list(self.allowed_base_faction_ids),
            "source_id": self.source_id,
            "enforcement_surface": self.enforcement_surface,
            "support_stage": self.support_stage,
            "enforcement_id": self.enforcement_id,
            "tests_evidence": self.tests_evidence,
            "notes": self.notes,
        }


class DatasheetSupportRowPayload(TypedDict):
    faction_id: str
    datasheet_id: str
    datasheet_name: str
    overall: str
    catalog_status: str
    model_geometry_status: str
    wargear_status: str
    weapon_keyword_status: str
    datasheet_ability_status: str
    faction_interaction_status: str
    tests_evidence: str
    notes: str
    ability_coverage_row_ids: list[str]
    detachment_ids: list[str]
    supported_detachment_ids: list[str]


@dataclass(frozen=True)
class DatasheetSupportRow:
    faction_id: str
    datasheet_id: str
    datasheet_name: str
    overall: str
    catalog_status: str
    model_geometry_status: str
    wargear_status: str
    weapon_keyword_status: str
    datasheet_ability_status: str
    faction_interaction_status: str
    tests_evidence: str
    notes: str
    ability_coverage_row_ids: tuple[str, ...]
    detachment_ids: tuple[str, ...]
    supported_detachment_ids: tuple[str, ...]

    def to_payload(self) -> DatasheetSupportRowPayload:
        return {
            "faction_id": self.faction_id,
            "datasheet_id": self.datasheet_id,
            "datasheet_name": self.datasheet_name,
            "overall": self.overall,
            "catalog_status": self.catalog_status,
            "model_geometry_status": self.model_geometry_status,
            "wargear_status": self.wargear_status,
            "weapon_keyword_status": self.weapon_keyword_status,
            "datasheet_ability_status": self.datasheet_ability_status,
            "faction_interaction_status": self.faction_interaction_status,
            "tests_evidence": self.tests_evidence,
            "notes": self.notes,
            "ability_coverage_row_ids": list(self.ability_coverage_row_ids),
            "detachment_ids": list(self.detachment_ids),
            "supported_detachment_ids": list(self.supported_detachment_ids),
        }


@dataclass(frozen=True)
class _ComponentEvidence:
    status: str
    notes: tuple[str, ...] = ()


_DETACHMENT_RULE_SUPPORT_OVERRIDES: dict[tuple[str, str], SupportSectionRow] = {
    (
        "aeldari",
        "path-of-the-outcast",
    ): SupportSectionRow(
        subject="Path of the Outcast",
        engine="Far-reaching Doom shooting-unit-selected hook",
        documentation="Source row, execution record, and generated matrix",
        tests="Focused hook, lifecycle, and hidden-target detection tests",
        overall="Full",
        notes=(
            "Runtime grants the +6 inch detection-range effect over the 11th Edition "
            "15 inch Hidden baseline and expires it after the source shoots."
        ),
    ),
    (
        "aeldari",
        "corsair-coterie",
    ): SupportSectionRow(
        subject="Corsair Coterie",
        engine=(
            "Relentless Raiders movement/charge completion mortal-wound hook, Void Thieves "
            "sticky objective-control hook, four enhancements, and six named Stratagem handlers"
        ),
        documentation="Adapter contract, architecture, and generated matrix",
        tests=(
            "Focused mustering, objective-control, movement-completion, turn-end, "
            "Stratagem-cost, runtime-modifier, Stratagem effect, targeting-restriction, "
            "and triggered-movement tests"
        ),
        overall="Full",
        notes=(
            "Includes Veterans of the Void mustering, objective-control ownership checks after "
            "sticky states, D6 2+ into D3 mortal wounds for enemies ending Normal/Advance/"
            "Fall Back/Charge moves on controlled objectives, Anhrathe sticky control, and "
            "Corsair Coterie Stratagem support."
        ),
    ),
    (
        "chaos-daemons",
        "blood-legion",
    ): SupportSectionRow(
        subject="Blood Legion",
        engine="Murdercall surge and Blood Tainted sticky-objective hooks",
        documentation="Source row, execution record, and generated matrix",
        tests="Focused triggered-move and phase-end objective-control tests",
        overall="Full",
        notes=(
            "Includes Khorne daemon, range, Aircraft, Battle-shock, and "
            "destruction-attribution gates."
        ),
    ),
    (
        "chaos-daemons",
        "cavalcade-of-chaos",
    ): SupportSectionRow(
        subject="Cavalcade of Chaos",
        engine=(
            "Unholy Avalanche Fall Back eligibility hook, three named Stratagem records, "
            "and two Enhancement bindings"
        ),
        documentation="Source row, execution record, and generated matrix",
        tests=("Focused Fall Back, Shoot, Charge, Stratagem, Enhancement, and handler-drift tests"),
        overall="Full",
        notes=(
            "Includes MOUNTED LEGIONES DAEMONICA Shoot and Charge permissions after Fall Back, "
            "Warp-Riders MOBILE, From Beyond the Veil ingress, Inescapable Manifestations "
            "Desperate Escape, Apocalyptic Steeds +1 Movement, and Soul-Shattering Charge "
            "melee targeting."
        ),
    ),
    (
        "chaos-daemons",
        "daemonic-incursion",
    ): SupportSectionRow(
        subject="Daemonic Incursion",
        engine="Warp Rifts generic IR reserve-arrival distance hook",
        documentation="Source row, execution record, and generated matrix",
        tests="Focused runtime hook and Deep Strike placement tests",
        overall="Full",
        notes=(
            "Allows qualifying LEGIONES DAEMONICA Deep Strike units wholly within Shadow "
            "of Chaos or within 6 inches of a matching named Greater Daemon anchor to use "
            "the 6 inch enemy distance."
        ),
    ),
    (
        "chaos-daemons",
        "shadow-legion",
    ): SupportSectionRow(
        subject="Shadow Legion",
        engine=(
            "Mustering restrictions and keyword grants, Murderer's Cowl Advance "
            "eligibility, Penumbral Puppetry hit modifiers, Gloam Rot wound "
            "modifiers, Shadow's Caress snap-target restriction, Leaping Shadows "
            "Scouts grants, Mantle of Gloom Objective Control aura, Malice Made "
            "Manifest Fight-start mortal wounds, and Disciples of Be'lakor Dark "
            "Pacts hooks"
        ),
        documentation="Adapter contract, decision catalog, README, and generated matrix",
        tests=(
            "Focused mustering, runtime hook, modifier, target-restriction, "
            "Scouts enhancement, Mantle of Gloom engagement aura, Malice Made "
            "Manifest target/FNP routing, out-of-phase shooting, Be'lakor "
            "auto-pass, and Feel No Pain routing tests"
        ),
        overall="Full",
        notes=(
            "Includes Shadow Legion/Undivided/Deep Strike keyword grants, Thralls of "
            "the First Prince roster caps and exclusions, attached rules-unit Scouts "
            "9 grants from Leaping Shadows, attached rules-unit Engagement Range OC "
            "reduction from Mantle of Gloom, Fight-start D6/D3 mortal wounds from "
            "Malice Made Manifest, Dark Pacts selected-to-shoot/fight grants for "
            "Undivided units, Be'lakor Leadership auto-pass, and Shadow-source D3 "
            "mortal-wound Feel No Pain continuation."
        ),
    ),
    (
        "emperors-children",
        "spectacle-of-slaughter",
    ): SupportSectionRow(
        subject="Spectacle of Slaughter",
        engine=(
            "Static RuleIR runtime bundle for the detachment rule, two enhancement "
            "bindings, and three Stratagem records"
        ),
        documentation="Source rows, generated matrix, and WS14 remediation status",
        tests="Lifecycle bundle, enhancement hook, Stratagem lifecycle, and runtime boundary tests",
        overall="Full",
        notes=(
            "Covers Entitled to Victory Fights First grants, Beguiling Grotesquerie "
            "Snap Shooting target restriction, Eager Patrons Move modifier, Honour Is "
            "for Fools Precision, Single-minded Strike charge transit permission, and "
            "Intoxicated by Triumph triggered movement."
        ),
    ),
    (
        "orks",
        "more-dakka",
    ): SupportSectionRow(
        subject="More Dakka!",
        engine=(
            "Static RuleIR runtime bundle for the detachment rule, four enhancement "
            "bindings, and six Stratagem records"
        ),
        documentation="Source rows, generated matrix, and WS14 runbook",
        tests="Lifecycle bundle, enhancement hook, Stratagem lifecycle, and runtime boundary tests",
        overall="Full",
        notes=(
            "Generic RuleIR rows execute from structured payloads through the "
            "lifecycle-scoped runtime bundle, including Call Dat Dakka through the "
            "public lifecycle decision entrypoint."
        ),
    ),
}

_RUNTIME_SOURCE_LABEL_OVERRIDES: Mapping[str, str] = {
    "phase17f:phase17e:aeldari:army-rule": "Battle Focus",
    "phase17f:phase17e:aeldari:path-of-the-outcast:enhancements": (
        "Path of the Outcast Enhancements"
    ),
    "phase17f:phase17e:aeldari:path-of-the-outcast:far-reaching-doom": ("Far-reaching Doom"),
    "phase17f:phase17e:astra-militarum:army-rule": "Voice of Command",
    "phase17f:phase17e:black-templars:army-rule": "Templar Vows",
    "phase17f:phase17e:chaos-daemons:army-rule": "The Shadow of Chaos",
    "phase17f:phase17e:chaos-daemons:blood-legion:rule": "Blood Legion",
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:enhancements": (
        "Cavalcade of Chaos Upgrades"
    ),
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:rule": "Unholy Avalanche",
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:stratagems": (
        "Cavalcade of Chaos Stratagems"
    ),
    "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule": "Warp Rifts",
    "phase17f:phase17e:chaos-daemons:shadow-legion:rule": "Shadow Legion",
    adepta_sororitas_army_rule.SOURCE_RULE_ID: "Acts of Faith",
    adeptus_custodes_army_rule.SOURCE_RULE_ID: "Martial Ka'tah",
    adeptus_mechanicus_army_rule.SOURCE_RULE_ID: "Doctrina Imperatives",
    adeptus_mechanicus_army_rule.HOOK_ID: "Doctrina Imperatives",
    adeptus_mechanicus_army_rule.PROTECTOR_HIT_MODIFIER_ID: (
        "Doctrina Imperatives - Protector Melee Hit Roll"
    ),
    adeptus_mechanicus_army_rule.WEAPON_PROFILE_MODIFIER_ID: (
        "Doctrina Imperatives - Weapon Profile"
    ),
    "phase17f:phase17e:chaos-knights:army-rule": "Harbingers of Dread",
    "phase17f:phase17e:chaos-space-marines:army-rule": "Dark Pacts",
    "phase17f:phase17e:death-guard:army-rule": "Nurgle's Gift",
    "phase17f:phase17e:drukhari:army-rule": "Power from Pain",
    "phase17f:phase17e:emperors-children:army-rule": "Thrill Seekers",
    genestealer_cults_cult_ambush.SOURCE_RULE_ID: "Cult Ambush",
    "phase17f:phase17e:imperial-knights:army-rule": "Code Chivalric",
    imperial_knights_army_rule.BONDSMAN_SOURCE_RULE_ID: "Bondsman",
    "phase17f:phase17e:leagues-of-votann:army-rule": "Prioritised Efficiency",
    "phase17g:space-marines:army-rule": "Oath of Moment",
    "phase17f:phase17e:tau-empire:army-rule": "For the Greater Good",
    "phase17f:phase17e:thousand-sons:army-rule": "Cabal of Sorcerers",
    tyranids_army_rule.SOURCE_RULE_ID: "Shadow in the Warp / Synapse",
    "phase17f:phase17e:world-eaters:army-rule": "Blessings of Khorne",
    "phase17g:aeldari:corsair-coterie:enhancements": "Corsair Coterie Enhancements",
    "phase17g:aeldari:corsair-coterie:relentless-raiders": "Corsair Coterie",
    "phase17g:aeldari:corsair-coterie:stratagems": "Corsair Coterie Stratagems",
}

_RUNTIME_ID_LABEL_OVERRIDES: Mapping[str, str] = {
    "phase17g:aeldari:corsair-coterie:stratagems:outcast-ambush:weapon-profile": ("Outcast Ambush"),
    "warhammer_40000_11th:aeldari:army_rule:fade_back": "Battle Focus - Fade Back",
    "warhammer_40000_11th:aeldari:army_rule:flitting_shadows": ("Battle Focus - Flitting Shadows"),
    "warhammer_40000_11th:aeldari:army_rule:opportunity_seized": (
        "Battle Focus - Opportunity Seized"
    ),
    "warhammer_40000_11th:aeldari:army_rule:star_engines": ("Battle Focus - Star Engines"),
    "warhammer_40000_11th:aeldari:army_rule:sudden_strike": ("Battle Focus - Sudden Strike"),
    "warhammer_40000_11th:aeldari:army_rule:swift_as_the_wind": (
        "Battle Focus - Swift as the Wind"
    ),
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command": ("Voice of Command"),
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:battle-shock": (
        "Voice of Command"
    ),
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:movement": (
        "Voice of Command - Move! Move! Move!"
    ),
    (
        "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:objective-control"
    ): "Voice of Command - Duty and Honour!",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:save-option": (
        "Voice of Command - Take Cover!"
    ),
    (
        "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:unit-characteristic"
    ): "Voice of Command - Duty and Honour!",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:weapon-profile": (
        "Voice of Command - Weapon Orders"
    ),
    chaos_knights_army_rule.HOOK_ID: "Harbingers of Dread",
    chaos_knights_army_rule.BATTLE_SHOCK_HOOK_ID: "Harbingers of Dread - Battle-shock",
    chaos_knights_army_rule.LEADERSHIP_MODIFIER_ID: (
        "Harbingers of Dread - Deathly Terror and Despair"
    ),
    chaos_knights_army_rule.DARKNESS_HIT_MODIFIER_ID: "Harbingers of Dread - Darkness",
    chaos_knights_army_rule.DOOM_WOUND_MODIFIER_ID: "Harbingers of Dread - Doom",
    imperial_knights_army_rule.HOOK_ID: "Code Chivalric",
    imperial_knights_army_rule.SETUP_HOOK_ID: "Code Chivalric - Oath Selection",
    imperial_knights_army_rule.UNIT_DESTROYED_HOOK_ID: "Code Chivalric",
    imperial_knights_army_rule.END_TURN_EVENT_HANDLER_ID: "Code Chivalric",
    imperial_knights_army_rule.END_BATTLE_ROUND_EVENT_HANDLER_ID: "Code Chivalric",
    imperial_knights_army_rule.END_TURN_SUBSCRIPTION_ID: "Code Chivalric",
    imperial_knights_army_rule.END_BATTLE_ROUND_SUBSCRIPTION_ID: "Code Chivalric",
    imperial_knights_army_rule.BONDSMAN_HOOK_ID: "Bondsman",
    f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:shooting": (
        "Code Chivalric - Martial Valour"
    ),
    f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:fight": (
        "Code Chivalric - Martial Valour"
    ),
    f"{imperial_knights_army_rule.HOOK_ID}:eager:movement-budget": (
        "Code Chivalric - Eager for the Challenge"
    ),
    f"{imperial_knights_army_rule.HOOK_ID}:eager:charge-roll": (
        "Code Chivalric - Eager for the Challenge"
    ),
    f"{imperial_knights_army_rule.HOOK_ID}:legacy:objective-control": (
        "Code Chivalric - Legacy Unsullied"
    ),
    f"{imperial_knights_army_rule.HOOK_ID}:legacy:leadership": (
        "Code Chivalric - Legacy Unsullied"
    ),
    tau_empire_army_rule.HOOK_ID: "For the Greater Good",
    tau_empire_army_rule.WEAPON_PROFILE_MODIFIER_ID: "For the Greater Good - Weapon Profile",
    adeptus_mechanicus_army_rule.HOOK_ID: "Doctrina Imperatives",
    adeptus_mechanicus_army_rule.PROTECTOR_HIT_MODIFIER_ID: (
        "Doctrina Imperatives - Protector Melee Hit Roll"
    ),
    adeptus_mechanicus_army_rule.WEAPON_PROFILE_MODIFIER_ID: (
        "Doctrina Imperatives - Weapon Profile"
    ),
    thousand_sons_army_rule.HOOK_ID: "Cabal of Sorcerers",
    thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID: (
        "Cabal of Sorcerers - Mortal Wound Feel No Pain"
    ),
    thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID: ("Cabal of Sorcerers - Weapon Profile"),
    genestealer_cults_cult_ambush.SOURCE_RULE_ID: "Cult Ambush",
    genestealer_cults_cult_ambush.BATTLE_FORMATION_HOOK_ID: "Cult Ambush",
    genestealer_cults_cult_ambush.UNIT_DESTROYED_HOOK_ID: "Cult Ambush",
    genestealer_cults_cult_ambush.TURN_END_HOOK_ID: "Cult Ambush",
    tyranids_army_rule.HOOK_ID: "Shadow in the Warp / Synapse",
    tyranids_army_rule.BATTLE_SHOCK_HOOK_ID: "Shadow in the Warp / Synapse - Battle-shock",
    tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID: (
        "Shadow in the Warp / Synapse - Weapon Profile"
    ),
    SPACE_MARINE_CHAPTERS_SOURCE_ID: "Space Marine Chapters",
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:archraider": ("Archraider"),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:archraider:lord_of_deceit": (
        "Archraider"
    ),
    (
        "warhammer_40000_11th:aeldari:detachment:corsair_coterie:archraider:lord_of_deceit_choice"
    ): "Archraider",
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:archraider:select_model": (
        "Archraider"
    ),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:infamy": "Infamy",
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:infamy:objective_control": ("Infamy"),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:relentless_raiders": (
        "Relentless Raiders"
    ),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:void_thieves": ("Void Thieves"),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:voidstone": "Voidstone",
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:voidstone:save_option": ("Voidstone"),
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:webway_pathstone": (
        "Webway Pathstone"
    ),
    (
        "warhammer_40000_11th:aeldari:detachment:corsair_coterie:webway_pathstone:deep_strike"
    ): "Webway Pathstone",
    (
        "warhammer_40000_11th:aeldari:detachment:corsair_coterie:webway_pathstone:turn_end_reserves"
    ): "Webway Pathstone",
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:assassins_eye_upgrade": (
        "Assassins' Eye"
    ),
    (
        "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:camouflaged_snipers_upgrade"
    ): "Camouflaged Snipers",
    "warhammer_40000_11th:aeldari:path_of_the_outcast:far_reaching_doom:selected_shooting_unit": (
        "Far-reaching Doom"
    ),
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted": ("Blood Tainted"),
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall": ("Murdercall"),
    (
        "warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:"
        "apocalyptic_steeds_upgrade"
    ): "Apocalyptic Steeds Upgrade",
    (
        "warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:"
        "soul_shattering_charge_upgrade"
    ): "Soul-Shattering Charge Upgrade",
    "warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:unholy_avalanche": (
        "Unholy Avalanche"
    ),
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts": ("Warp Rifts"),
    "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:daemon_lord_of_khorne": (
        "Daemon Lord of Khorne"
    ),
    "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:relentless_carnage": (
        "Relentless Carnage"
    ),
    (
        "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:"
        "relentless_carnage:mortal-wound-fnp"
    ): "Relentless Carnage - Mortal Wound Feel No Pain",
    "warhammer_40000_11th:chaos_daemons:datasheet:lord_of_change:daemon_lord_of_tzeentch": (
        "Daemon Lord of Tzeentch"
    ),
    "warhammer_40000_11th:chaos_daemons:datasheet:plaguebearers:infected_outbreak": (
        "Infected Outbreak"
    ),
    adepta_sororitas_army_rule.BATTLE_ROUND_START_HOOK_ID: "Acts of Faith",
    adepta_sororitas_army_rule.UNIT_DESTROYED_HOOK_ID: "Acts of Faith",
    adeptus_custodes_army_rule.DACATARAI_HOOK_ID: "Martial Ka'tah - Dacatarai",
    adeptus_custodes_army_rule.RENDAX_HOOK_ID: "Martial Ka'tah - Rendax",
    adeptus_custodes_army_rule.WEAPON_PROFILE_MODIFIER_ID: "Martial Ka'tah - Weapon Profile",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:battle-shock-failed": (
        "Power from Pain"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:command-phase-start": (
        "Power from Pain"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:enemy-unit-destroyed": (
        "Power from Pain"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-fight": (
        "Power from Pain - Hatred Eternal"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-shooting": (
        "Power from Pain - Hatred Eternal"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-advance": (
        "Power from Pain - Lithe Agility"
    ),
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-charge": (
        "Power from Pain - Lithe Agility"
    ),
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:rage_fuelled_invigoration": (
        "Blessings of Khorne - Rage-fuelled Invigoration"
    ),
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:total_carnage": (
        "Blessings of Khorne - Total Carnage"
    ),
    (
        "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:"
        "unbridled_bloodlust:charge_roll"
    ): "Blessings of Khorne - Unbridled Bloodlust",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:weapon-profile-keywords": (
        "Blessings of Khorne"
    ),
    "warhammer_40000_11th:orks:army_rule:waaagh": "Waaagh!",
    "warhammer_40000_11th:orks:army_rule:waaagh:advance-eligibility": "Waaagh!",
    "warhammer_40000_11th:orks:army_rule:waaagh:invulnerable-save": "Waaagh!",
    "warhammer_40000_11th:orks:army_rule:waaagh:weapon-profile": "Waaagh!",
}


def main() -> None:
    args = _parse_args()
    source_json_dir = _resolve_repo_path(args.source_json_dir)
    output_dir = _resolve_repo_path(args.output_dir)
    docs_path = _resolve_repo_path(args.docs_path)
    faction_docs_dir = _resolve_repo_path(args.faction_docs_dir)
    package = _ability_support_catalog_package(source_json_dir=source_json_dir)
    rows = _ability_support_matrix_rows_from_package(package)
    category_rows = ability_coverage_category_rows(rows)
    datasheet_rows = _datasheet_support_rows_from_package(
        package=package,
        ability_rows=rows,
    )
    mustering_rows = mustering_support_rows()
    row_payloads = ability_coverage_rows_payload(rows)
    category_payloads = ability_coverage_category_rows_payload(category_rows)
    datasheet_payloads = datasheet_support_rows_payload(datasheet_rows)
    mustering_payloads = mustering_support_rows_payload(mustering_rows)
    runtime_semantic_payload = runtime_content_semantic_coverage_payload()

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "ability_coverage_rows.json", row_payloads)
    _write_json(output_dir / "ability_support_category_rows.json", category_payloads)
    _write_json(output_dir / "datasheet_support_rows.json", datasheet_payloads)
    _write_json(output_dir / "mustering_support_rows.json", mustering_payloads)
    _write_json(output_dir / "runtime_content_semantic_coverage.json", runtime_semantic_payload)
    docs_path.write_text(
        support_matrix_markdown(
            category_payloads,
            runtime_semantic_coverage=runtime_semantic_payload,
        ),
        encoding="utf-8",
    )
    faction_docs_dir.mkdir(parents=True, exist_ok=True)
    for filename, markdown in faction_support_markdown_files(
        datasheet_support_rows=datasheet_rows,
        ability_rows=rows,
    ).items():
        (faction_docs_dir / filename).write_text(markdown, encoding="utf-8")


def ability_support_matrix_rows(
    *,
    source_json_dir: Path = DEFAULT_SOURCE_JSON_DIR,
) -> tuple[AbilityCoverageRow, ...]:
    return _ability_support_matrix_rows_from_package(
        _ability_support_catalog_package(source_json_dir=source_json_dir)
    )


def datasheet_support_rows(
    *,
    source_json_dir: Path = DEFAULT_SOURCE_JSON_DIR,
) -> tuple[DatasheetSupportRow, ...]:
    package = _ability_support_catalog_package(source_json_dir=source_json_dir)
    ability_rows = _ability_support_matrix_rows_from_package(package)
    return _datasheet_support_rows_from_package(package=package, ability_rows=ability_rows)


def runtime_content_semantic_coverage_payload() -> RuntimeContentSemanticCoveragePayload:
    rows = tuple(generated_runtime_content_rows())
    faction_rows_by_id = {
        row.content_id: row
        for row in rows
        if row.family is RuntimeContentModuleFamily.FACTION
        and row.support_status is RuntimeContentSupportStatus.SUPPORTED
    }
    detachment_rows_by_id = {
        row.content_id: row
        for row in rows
        if row.family is RuntimeContentModuleFamily.DETACHMENT
        and row.support_status is RuntimeContentSupportStatus.SUPPORTED
    }
    source_package_ids = tuple(sorted({row.source_package_id for row in rows}))
    source_package_hashes = tuple(
        sorted({row.source_package_hash for row in rows if row.source_package_hash is not None})
    )
    if len(source_package_ids) != 1 or len(source_package_hashes) != 1:
        raise ValueError("Runtime content semantic coverage requires one source package identity.")

    faction_payloads: list[RuntimeContentFactionSemanticCoveragePayload] = []
    for faction_row in faction_detachments_2026_27.faction_rows():
        runtime_faction_row = faction_rows_by_id.get(faction_row.faction_id)
        if runtime_faction_row is None:
            raise ValueError("Runtime content semantic coverage is missing a faction manifest row.")
        detachment_payloads: list[RuntimeContentDetachmentSemanticCoveragePayload] = []
        runtime_detachment_rows = []
        for detachment_row in faction_detachments_2026_27.detachment_rows():
            if detachment_row.faction_id != faction_row.faction_id:
                continue
            runtime_detachment_row = detachment_rows_by_id.get(detachment_row.detachment_id)
            if runtime_detachment_row is None:
                raise ValueError(
                    "Runtime content semantic coverage is missing a detachment manifest row."
                )
            runtime_detachment_rows.append(runtime_detachment_row)
            detachment_payloads.append(
                {
                    "detachment_id": detachment_row.detachment_id,
                    "detachment_name": detachment_row.name,
                    "semantic_status": runtime_detachment_row.semantic_status.value,
                    "execution_record_count": len(runtime_detachment_row.execution_record_ids),
                    "source_ids": list(runtime_detachment_row.source_ids),
                    "module_path": _required_module_path(runtime_detachment_row.module_path),
                }
            )
        faction_payloads.append(
            {
                "faction_id": faction_row.faction_id,
                "faction_name": faction_row.name,
                "semantic_status": runtime_faction_row.semantic_status.value,
                "execution_record_count": len(runtime_faction_row.execution_record_ids),
                "source_ids": list(runtime_faction_row.source_ids),
                "module_path": _required_module_path(runtime_faction_row.module_path),
                "detachment_status_counts": _runtime_semantic_status_counts(
                    tuple(row.semantic_status for row in runtime_detachment_rows)
                ),
                "detachments": detachment_payloads,
            }
        )

    return {
        "schema_version": RUNTIME_CONTENT_SEMANTIC_COVERAGE_SCHEMA_VERSION,
        "source_package_id": source_package_ids[0],
        "source_package_hash": source_package_hashes[0],
        "faction_status_counts": _runtime_semantic_status_counts(
            tuple(row.semantic_status for row in faction_rows_by_id.values())
        ),
        "detachment_status_counts": _runtime_semantic_status_counts(
            tuple(row.semantic_status for row in detachment_rows_by_id.values())
        ),
        "factions": faction_payloads,
    }


def datasheet_support_rows_payload(
    rows: tuple[DatasheetSupportRow, ...],
) -> list[DatasheetSupportRowPayload]:
    if type(rows) is not tuple:
        raise ValueError("Datasheet support rows must be a tuple.")
    for row in rows:
        if type(row) is not DatasheetSupportRow:
            raise ValueError("Datasheet support payloads require DatasheetSupportRow values.")
    return [row.to_payload() for row in rows]


def mustering_support_rows() -> tuple[MusteringSupportRow, ...]:
    rows = (
        MusteringSupportRow(
            rule_id="army-mustering:daemonic-pact",
            display_name="Daemonic Pact",
            faction_id="chaos-daemons",
            allowed_base_faction_ids=("chaos-knights", "chaos-space-marines"),
            source_id=DAEMONIC_PACT_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_daemonic_pact_violations",
            tests_evidence=(
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_daemonic_pact_allows_legiones_daemonica_allies; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_daemonic_pact_reports_roster_violations; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_daemonic_pact_points_cap_scales_by_battle_size"
            ),
            notes=(
                "Allows LEGIONES DAEMONICA allies for Chaos Knights or Heretic Astartes "
                "armies, enforces battle-size points caps, god Battleline ratios, base-model "
                "keywords, and allied Warlord/Enhancement restrictions."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:dreadblades",
            display_name="Dreadblades",
            faction_id="chaos-knights",
            allowed_base_faction_ids=("chaos",),
            source_id=DREADBLADES_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_dreadblades_violations",
            tests_evidence=(
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_dreadblades_allows_one_titanic_or_three_war_dogs_for_chaos_armies; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_dreadblades_reports_roster_violations"
            ),
            notes=(
                "Allows Chaos armies to include either one TITANIC Chaos Knights model or up "
                "to three WAR DOG models, and forbids allied Enhancements and Warlords."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:cult-of-the-dark-gods",
            display_name="Cult of the Dark Gods",
            faction_id="chaos-space-marines",
            allowed_base_faction_ids=("chaos-space-marines",),
            source_id=CULT_OF_DARK_GODS_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation/army_factory",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_cult_of_dark_gods_violations",
            tests_evidence=(
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_cult_of_dark_gods_allows_cult_units_and_replaces_faction_keywords; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_cult_of_dark_gods_points_cap_scales_by_battle_size"
            ),
            notes=(
                "Allows selected cult datasheets in Heretic Astartes armies, enforces "
                "battle-size points caps, and replaces faction keywords during army creation."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:drukhari-corsairs-and-travelling-players",
            display_name="Corsairs and Travelling Players",
            faction_id="drukhari",
            allowed_base_faction_ids=("drukhari",),
            source_id=DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_drukhari_corsairs_and_travelling_players_violations",
            tests_evidence=(
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_drukhari_corsairs_and_travelling_players_allows_allies; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_drukhari_corsairs_reports_roster_violations; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_drukhari_corsairs_rejects_other_faction_allies"
            ),
            notes=(
                "Allows non-DRUKHARI HARLEQUINS and ANHRATHE allies under Incursion, Strike "
                "Force, and Onslaught caps; forbids allied Warlords and Enhancements."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:freeblades",
            display_name="Freeblades",
            faction_id="imperial-knights",
            allowed_base_faction_ids=("imperium",),
            source_id=FREEBLADES_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_freeblades_violations",
            tests_evidence=(
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_freeblades_allows_one_titanic_or_three_armigers_for_"
                "imperium_armies; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_freeblades_reports_roster_violations; "
                "tests/unit/test_phase9c_mustering.py::"
                "test_phase17g_freeblades_rejects_non_imperium_faction_access"
            ),
            notes=(
                "Allows Imperium armies to include either one TITANIC Imperial Knights model "
                "or up to three ARMIGER models, and forbids allied Enhancements and Warlords."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:shadow-legion-thralls-of-the-first-prince",
            display_name="Shadow Legion Thralls of the First Prince",
            faction_id="chaos-daemons",
            allowed_base_faction_ids=("chaos-daemons",),
            source_id=SHADOW_LEGION_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation/army_factory",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_shadow_legion_violations",
            tests_evidence=(
                "tests/unit/test_phase17g_chaos_daemons_shadow_legion.py::"
                "test_shadow_legion_mustering_grants_keywords_and_deep_strike; "
                "tests/unit/test_phase17g_chaos_daemons_shadow_legion.py::"
                "test_shadow_legion_roster_reports_thralls_and_forbidden_units"
            ),
            notes=(
                "Enforces Shadow Legion detachment restrictions, Heretic Astartes Thralls "
                "allow-list and points caps, forbidden Daemon Prince/Epic Hero selections, "
                "and grants Shadow Legion, Undivided, and Deep Strike keywords."
            ),
        ),
        MusteringSupportRow(
            rule_id="army-mustering:space-marine-chapters",
            display_name="Space Marine Chapters",
            faction_id="space-marines",
            allowed_base_faction_ids=("space-marines",),
            source_id=SPACE_MARINE_CHAPTERS_SOURCE_ID,
            enforcement_surface="army_mustering/list_validation",
            support_stage=MUSTERING_SUPPORT_FULL,
            enforcement_id="army_mustering:_append_space_marine_chapter_violations",
            tests_evidence=(
                "tests/unit/test_phase17g_space_marines_army_rule.py::"
                "test_space_marine_chapters_enforce_black_templars_and_space_wolves; "
                "tests/unit/test_phase17g_space_marines_army_rule.py::"
                "test_space_marine_chapters_enforce_deathwatch_restrictions"
            ),
            notes=(
                "Enforces one-Chapter roster restrictions plus Black Templars, Space Wolves, "
                "and Deathwatch forbidden-unit gates for Adeptus Astartes armies."
            ),
        ),
    )
    return tuple(sorted(rows, key=lambda row: row.rule_id))


def mustering_support_rows_payload(
    rows: tuple[MusteringSupportRow, ...],
) -> list[MusteringSupportRowPayload]:
    if type(rows) is not tuple:
        raise ValueError("Mustering support rows must be a tuple.")
    for row in rows:
        if type(row) is not MusteringSupportRow:
            raise ValueError("Mustering support payloads require MusteringSupportRow values.")
    return [row.to_payload() for row in rows]


def _ability_support_catalog_package(
    *,
    source_json_dir: Path = DEFAULT_SOURCE_JSON_DIR,
) -> CanonicalCatalogPackage:
    source_json_dir = _resolve_repo_path(source_json_dir)
    artifacts = _load_source_artifacts(source_json_dir)
    overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=artifacts,
        release_manifest=chaos_defiler_overlay.source_release_manifest(),
        overlay_packs=(chaos_defiler_overlay.overlay_pack(),),
    )
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=overlaid_artifacts,
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=ABILITY_SUPPORT_DATASHEET_IDS,
        height_overrides=(
            CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES
            + BLOODLETTERS_HEIGHT_OVERRIDES
            + FLESH_HOUNDS_HEIGHT_OVERRIDES
            + CHAOS_DEFILER_HEIGHT_OVERRIDES
        ),
    )
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )


def _ability_support_matrix_rows_from_package(
    package: CanonicalCatalogPackage,
) -> tuple[AbilityCoverageRow, ...]:
    if type(package) is not CanonicalCatalogPackage:
        raise ValueError("Ability support matrix rows require a canonical catalog package.")
    rows = ability_coverage_rows_from_catalog(
        package.army_catalog,
        datasheet_ids=ABILITY_SUPPORT_DATASHEET_IDS,
    )
    return (*rows, *_runtime_faction_army_rule_rows())


def _datasheet_support_rows_from_package(
    *,
    package: CanonicalCatalogPackage,
    ability_rows: tuple[AbilityCoverageRow, ...],
) -> tuple[DatasheetSupportRow, ...]:
    if type(package) is not CanonicalCatalogPackage:
        raise ValueError("Datasheet support rows require a canonical catalog package.")
    if type(ability_rows) is not tuple:
        raise ValueError("Datasheet support rows require ability rows.")
    for row in ability_rows:
        if type(row) is not AbilityCoverageRow:
            raise ValueError("Datasheet support rows require AbilityCoverageRow values.")
    rows_by_datasheet = _ability_coverage_rows_by_datasheet_id(ability_rows)
    geometry_by_profile_id = _geometry_by_profile_id(package.model_geometries)
    faction_doc_ids_by_name = _faction_doc_ids_by_name()
    support_rows: list[DatasheetSupportRow] = []
    for datasheet in package.army_catalog.datasheets:
        faction_id = _faction_doc_id_for_datasheet(
            catalog=package.army_catalog,
            datasheet_id=datasheet.datasheet_id,
            faction_keywords=datasheet.keywords.faction_keywords,
            faction_doc_ids_by_name=faction_doc_ids_by_name,
        )
        datasheet_rows = rows_by_datasheet.get(datasheet.datasheet_id, ())
        catalog = _catalog_status(datasheet=datasheet)
        geometry = _model_geometry_status(
            datasheet=datasheet,
            geometry_by_profile_id=geometry_by_profile_id,
        )
        wargear = _wargear_status(
            catalog=package.army_catalog,
            datasheet_id=datasheet.datasheet_id,
            default_or_allowed_wargear_ids=_datasheet_default_or_allowed_wargear_ids(datasheet),
            ability_rows=datasheet_rows,
        )
        weapon_keywords = _weapon_keyword_status(
            catalog=package.army_catalog,
            wargear_ids=_datasheet_default_or_allowed_wargear_ids(datasheet),
        )
        datasheet_abilities = _datasheet_ability_status(datasheet_rows)
        faction_interactions = _faction_interaction_status(
            faction_id=faction_id,
            ability_rows=datasheet_rows,
            detachment_support_rows=_detachment_rule_support_rows_for_faction(faction_id),
        )
        overall = _overall_datasheet_status(
            catalog=catalog.status,
            model_geometry=geometry.status,
            wargear=wargear.status,
            weapon_keywords=weapon_keywords.status,
            datasheet_abilities=datasheet_abilities.status,
            faction_interactions=faction_interactions.status,
            ability_rows=datasheet_rows,
        )
        notes = _datasheet_support_notes(
            overall=overall,
            catalog=catalog,
            model_geometry=geometry,
            wargear=wargear,
            weapon_keywords=weapon_keywords,
            datasheet_abilities=datasheet_abilities,
            faction_interactions=faction_interactions,
        )
        detachment_rows = _faction_interaction_detachment_rows(faction_id)
        detachment_ids = tuple(row.detachment_id for row in detachment_rows)
        supported_detachment_ids = tuple(
            row.detachment_id for row in detachment_rows if _detachment_rule_is_supported(row)
        )
        support_rows.append(
            DatasheetSupportRow(
                faction_id=faction_id,
                datasheet_id=datasheet.datasheet_id,
                datasheet_name=datasheet.name,
                overall=overall,
                catalog_status=catalog.status,
                model_geometry_status=geometry.status,
                wargear_status=wargear.status,
                weapon_keyword_status=weapon_keywords.status,
                datasheet_ability_status=datasheet_abilities.status,
                faction_interaction_status=faction_interactions.status,
                tests_evidence=_datasheet_tests_evidence(datasheet_rows),
                notes=notes,
                ability_coverage_row_ids=tuple(row.coverage_row_id for row in datasheet_rows),
                detachment_ids=detachment_ids,
                supported_detachment_ids=supported_detachment_ids,
            )
        )
    return tuple(
        sorted(
            support_rows,
            key=lambda row: (row.faction_id, row.datasheet_name.lower(), row.datasheet_id),
        )
    )


def _ability_coverage_rows_by_datasheet_id(
    rows: tuple[AbilityCoverageRow, ...],
) -> dict[str, tuple[AbilityCoverageRow, ...]]:
    grouped: dict[str, list[AbilityCoverageRow]] = {}
    for row in rows:
        if type(row) is not AbilityCoverageRow:
            raise ValueError("Ability coverage grouping requires AbilityCoverageRow values.")
        grouped.setdefault(row.datasheet_id, []).append(row)
    return {
        datasheet_id: tuple(sorted(group_rows, key=_ability_coverage_detail_sort_key))
        for datasheet_id, group_rows in grouped.items()
    }


def _ability_coverage_detail_sort_key(
    row: AbilityCoverageRow,
) -> tuple[str, str, str, str]:
    return (
        row.source_kind.value,
        row.ability_name.lower(),
        row.ability_id,
        row.source_wargear_id or "",
    )


def _geometry_by_profile_id(
    records: tuple[ModelGeometryCatalogRecord, ...],
) -> dict[str, ModelGeometryCatalogRecord]:
    if type(records) is not tuple:
        raise ValueError("Datasheet support geometry records must be a tuple.")
    by_profile_id: dict[str, ModelGeometryCatalogRecord] = {}
    for record in records:
        if type(record) is not ModelGeometryCatalogRecord:
            raise ValueError("Datasheet support geometry records must contain catalog records.")
        if record.model_profile_id in by_profile_id:
            raise ValueError("Datasheet support geometry records must not duplicate profiles.")
        by_profile_id[record.model_profile_id] = record
    return by_profile_id


def _faction_doc_ids_by_name() -> dict[str, str]:
    return {row.name: row.faction_id for row in faction_detachments_2026_27.faction_rows()}


def _faction_doc_id_for_datasheet(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    faction_keywords: tuple[str, ...],
    faction_doc_ids_by_name: Mapping[str, str],
) -> str:
    if type(catalog) is not ArmyCatalog:
        raise ValueError("Datasheet support faction matching requires an ArmyCatalog.")
    if not faction_keywords:
        raise ValueError("Datasheet support faction matching requires faction keywords.")
    matches = tuple(
        faction
        for faction in catalog.factions
        if set(faction.faction_keywords).intersection(faction_keywords)
    )
    if len(matches) != 1:
        raise ValueError(
            f"Datasheet support requires exactly one catalog faction for {datasheet_id}."
        )
    faction_id = faction_doc_ids_by_name.get(matches[0].name)
    if faction_id is None:
        raise ValueError("Datasheet support catalog faction has no generated faction document.")
    return faction_id


def _catalog_status(*, datasheet: object) -> _ComponentEvidence:
    from warhammer40k_core.core.datasheet import DatasheetDefinition

    if type(datasheet) is not DatasheetDefinition:
        raise ValueError("Datasheet support catalog status requires a DatasheetDefinition.")
    missing: list[str] = []
    if not datasheet.source_ids:
        missing.append("datasheet source IDs")
    if not datasheet.model_profiles:
        missing.append("model profiles")
    if not datasheet.composition:
        missing.append("unit composition")
    if not datasheet.keywords.keywords:
        missing.append("keywords")
    if not datasheet.keywords.faction_keywords:
        missing.append("faction keywords")
    if not datasheet.wargear_options:
        missing.append("wargear options")
    if missing:
        return _component(DATASHEET_SUPPORT_BLOCKED, _missing_note("Missing catalog data", missing))
    return _component(DATASHEET_SUPPORT_FULL)


def _model_geometry_status(
    *,
    datasheet: object,
    geometry_by_profile_id: Mapping[str, ModelGeometryCatalogRecord],
) -> _ComponentEvidence:
    from warhammer40k_core.core.datasheet import DatasheetDefinition

    if type(datasheet) is not DatasheetDefinition:
        raise ValueError("Datasheet support geometry status requires a DatasheetDefinition.")
    missing_geometry: list[str] = []
    incomplete_geometry: list[str] = []
    for profile in datasheet.model_profiles:
        geometry_record = geometry_by_profile_id.get(profile.model_profile_id)
        if geometry_record is None:
            missing_geometry.append(profile.model_profile_id)
            continue
        if geometry_record.height.height_inches <= 0.0:
            incomplete_geometry.append(f"{profile.model_profile_id}: missing height")
        if not _geometry_record_has_accepted_evidence(geometry_record):
            incomplete_geometry.append(f"{profile.model_profile_id}: unaccepted evidence")
    if missing_geometry:
        return _component(
            DATASHEET_SUPPORT_BLOCKED,
            _missing_note("Missing model geometry", missing_geometry),
        )
    if incomplete_geometry:
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            _missing_note("Incomplete model geometry evidence", incomplete_geometry),
        )
    return _component(DATASHEET_SUPPORT_FULL)


def _geometry_record_has_accepted_evidence(record: ModelGeometryCatalogRecord) -> bool:
    evidence_by_id = {evidence.evidence_id: evidence for evidence in record.evidence}
    linked_evidence_ids = {record.height.evidence_id, record.footprint.evidence_id}
    if record.support_base is not None:
        linked_evidence_ids.add(record.support_base.evidence_id)
    if record.z_offset is not None:
        linked_evidence_ids.add(record.z_offset.evidence_id)
    for evidence_id in linked_evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            return False
        if evidence.reviewer_status is not GeometryReviewStatus.ACCEPTED:
            return False
        if evidence.measurement_kind not in {
            GeometryMeasurementKind.FOOTPRINT,
            GeometryMeasurementKind.SUPPORT_BASE,
            GeometryMeasurementKind.Z_OFFSET,
            GeometryMeasurementKind.HEIGHT,
        }:
            return False
    return True


def _datasheet_default_or_allowed_wargear_ids(datasheet: object) -> tuple[str, ...]:
    from warhammer40k_core.core.datasheet import DatasheetDefinition

    if type(datasheet) is not DatasheetDefinition:
        raise ValueError("Datasheet support wargear IDs require a DatasheetDefinition.")
    return tuple(
        sorted(
            {
                wargear_id
                for option in datasheet.wargear_options
                for wargear_id in (*option.default_wargear_ids, *option.allowed_wargear_ids)
            }
        )
    )


def _wargear_status(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    default_or_allowed_wargear_ids: tuple[str, ...],
    ability_rows: tuple[AbilityCoverageRow, ...],
) -> _ComponentEvidence:
    wargear_by_id = {item.wargear_id: item for item in catalog.wargear}
    ability_wargear_ids = {
        row.source_wargear_id for row in ability_rows if row.source_wargear_id is not None
    }
    required_wargear_ids = tuple(sorted({*default_or_allowed_wargear_ids, *ability_wargear_ids}))
    if not required_wargear_ids:
        return _component(
            DATASHEET_SUPPORT_BLOCKED,
            f"Missing required wargear links for `{datasheet_id}`.",
        )
    missing = tuple(
        wargear_id for wargear_id in required_wargear_ids if wargear_id not in wargear_by_id
    )
    if missing:
        return _component(DATASHEET_SUPPORT_BLOCKED, _missing_note("Missing wargear", missing))
    incomplete_profiles = tuple(
        profile.profile_id
        for wargear_id in required_wargear_ids
        for profile in wargear_by_id[wargear_id].weapon_profiles
        if not profile.source_ids
    )
    if incomplete_profiles:
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            _missing_note("Incomplete weapon profile source evidence", incomplete_profiles),
        )
    return _component(DATASHEET_SUPPORT_FULL)


def _weapon_keyword_status(
    *,
    catalog: ArmyCatalog,
    wargear_ids: tuple[str, ...],
) -> _ComponentEvidence:
    wargear_by_id = {item.wargear_id: item for item in catalog.wargear}
    weapon_keywords: set[WeaponKeyword] = set()
    weapon_ability_kinds: set[AbilityKind] = set()
    unsupported: list[str] = []
    for wargear_id in wargear_ids:
        wargear = wargear_by_id[wargear_id]
        for profile in wargear.weapon_profiles:
            weapon_keywords.update(profile.keywords)
            weapon_ability_kinds.update(ability.ability_kind for ability in profile.abilities)
            unsupported.extend(
                keyword.value
                for keyword in profile.keywords
                if keyword not in _SUPPORTED_WEAPON_KEYWORDS
            )
            unsupported.extend(
                ability.ability_kind.value
                for ability in profile.abilities
                if ability.ability_kind not in _SUPPORTED_WEAPON_ABILITY_KINDS
            )
    if unsupported:
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            _missing_note("Unsupported weapon keyword abilities", tuple(sorted(unsupported))),
        )
    if not weapon_keywords and not weapon_ability_kinds:
        return _component(DATASHEET_SUPPORT_NONE)
    labels = tuple(
        sorted(
            {
                *(keyword.value for keyword in weapon_keywords),
                *(ability_kind.value for ability_kind in weapon_ability_kinds),
            }
        )
    )
    return _component(DATASHEET_SUPPORT_FULL, "Supported weapon keywords: " + ", ".join(labels))


def _datasheet_ability_status(
    ability_rows: tuple[AbilityCoverageRow, ...],
) -> _ComponentEvidence:
    if not ability_rows:
        return _component(DATASHEET_SUPPORT_NONE)
    blocking_notes: list[str] = []
    playable_notes: list[str] = []
    partial_notes: list[str] = []
    for row in ability_rows:
        ability_label = f"`{row.ability_id}` {row.ability_name}"
        if row.diagnostic_reasons:
            blocking_notes.append(
                f"{ability_label}: diagnostics {_inline_code_list(row.diagnostic_reasons)}"
            )
        if row.support_stage in _DATASHEET_ABILITY_BLOCKING_STAGES:
            blocking_notes.append(f"{ability_label}: `{row.support_stage.value}`")
        elif row.support_stage in _DATASHEET_ABILITY_PLAYABLE_STAGES:
            playable_notes.append(f"{ability_label}: `{row.support_stage.value}`")
        elif row.support_stage in _DATASHEET_ABILITY_PARTIAL_STAGES:
            partial_notes.append(f"{ability_label}: `{row.support_stage.value}`")
        elif row.support_stage in _DATASHEET_ABILITY_FULL_STAGES:
            if (
                row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
                and not row.runtime_consumer_ids
            ):
                blocking_notes.append(f"{ability_label}: missing runtime consumer")
        else:
            partial_notes.append(f"{ability_label}: `{row.support_stage.value}`")
    if blocking_notes:
        return _component(DATASHEET_SUPPORT_BLOCKED, *tuple(blocking_notes))
    if partial_notes:
        return _component(DATASHEET_SUPPORT_PARTIAL, *tuple(partial_notes))
    if playable_notes:
        return _component(DATASHEET_SUPPORT_PLAYABLE, *tuple(playable_notes))
    return _component(DATASHEET_SUPPORT_FULL)


def _faction_interaction_status(
    *,
    faction_id: str,
    ability_rows: tuple[AbilityCoverageRow, ...],
    detachment_support_rows: tuple[DetachmentRuleSupportRow, ...],
) -> _ComponentEvidence:
    faction_rows = tuple(
        row for row in ability_rows if row.source_kind is CatalogAbilitySourceKind.FACTION
    )
    if not faction_rows and not detachment_support_rows:
        return _component(DATASHEET_SUPPORT_NONE)
    supported_detachments = tuple(
        row for row in detachment_support_rows if _detachment_rule_is_supported(row)
    )
    detachment_note = (
        f"detachment support {len(supported_detachments)}/{len(detachment_support_rows)}"
        if detachment_support_rows
        else "no generated detachment support rows"
    )
    if not faction_rows:
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            f"No source-backed faction ability row; {detachment_note}.",
        )
    faction_rows_supported = all(
        row.support_stage in _DATASHEET_ABILITY_FULL_STAGES and not row.diagnostic_reasons
        for row in faction_rows
    )
    if not faction_rows_supported:
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            f"Faction ability row is not fully consumed; {detachment_note}.",
        )
    if detachment_support_rows and len(supported_detachments) != len(detachment_support_rows):
        supported_ids = tuple(row.detachment_id for row in supported_detachments)
        return _component(
            DATASHEET_SUPPORT_PARTIAL,
            (
                f"Faction army rule consumed; {detachment_note}. Supported detachment IDs: "
                f"{_inline_code_list(supported_ids)}."
            ),
        )
    return _component(DATASHEET_SUPPORT_FULL, f"Faction army rule consumed; {detachment_note}.")


def _faction_interaction_detachment_rows(
    faction_id: str,
) -> tuple[DetachmentRuleSupportRow, ...]:
    return _detachment_rule_support_rows_for_faction(faction_id)


def _overall_datasheet_status(
    *,
    catalog: str,
    model_geometry: str,
    wargear: str,
    weapon_keywords: str,
    datasheet_abilities: str,
    faction_interactions: str,
    ability_rows: tuple[AbilityCoverageRow, ...],
) -> str:
    evidence_statuses = (
        catalog,
        model_geometry,
        wargear,
        weapon_keywords,
        datasheet_abilities,
    )
    if DATASHEET_SUPPORT_UNKNOWN in evidence_statuses:
        return DATASHEET_SUPPORT_UNKNOWN
    if DATASHEET_SUPPORT_BLOCKED in evidence_statuses:
        return DATASHEET_SUPPORT_BLOCKED
    if not ability_rows and weapon_keywords == DATASHEET_SUPPORT_NONE:
        return DATASHEET_SUPPORT_CATALOG_ONLY
    if DATASHEET_SUPPORT_PARTIAL in evidence_statuses:
        return DATASHEET_SUPPORT_PARTIAL
    if DATASHEET_SUPPORT_PLAYABLE in evidence_statuses:
        return DATASHEET_SUPPORT_PLAYABLE
    if faction_interactions == DATASHEET_SUPPORT_PARTIAL:
        return DATASHEET_SUPPORT_PLAYABLE
    return DATASHEET_SUPPORT_FULL


def _datasheet_support_notes(
    *,
    overall: str,
    catalog: _ComponentEvidence,
    model_geometry: _ComponentEvidence,
    wargear: _ComponentEvidence,
    weapon_keywords: _ComponentEvidence,
    datasheet_abilities: _ComponentEvidence,
    faction_interactions: _ComponentEvidence,
) -> str:
    notes = tuple(
        note
        for component in (
            catalog,
            model_geometry,
            wargear,
            weapon_keywords,
            datasheet_abilities,
            faction_interactions,
        )
        if component.status
        in {DATASHEET_SUPPORT_BLOCKED, DATASHEET_SUPPORT_PARTIAL, DATASHEET_SUPPORT_PLAYABLE}
        for note in component.notes
    )
    if notes:
        return " ".join(notes)
    if overall == DATASHEET_SUPPORT_FULL:
        return "No known blockers."
    if overall == DATASHEET_SUPPORT_PLAYABLE:
        return "No known blockers; some faction or detachment interaction proof is partial."
    if overall == DATASHEET_SUPPORT_CATALOG_ONLY:
        return "Catalog row is present, but semantic runtime support is not proven."
    return "No known blockers."


def _datasheet_tests_evidence(ability_rows: tuple[AbilityCoverageRow, ...]) -> str:
    runtime_consumer_ids = tuple(
        sorted(
            {
                runtime_consumer_id
                for row in ability_rows
                for runtime_consumer_id in row.runtime_consumer_ids
            }
        )
    )
    if runtime_consumer_ids:
        return (
            f"Runtime consumers: {_inline_code_list(runtime_consumer_ids)}; coverage artifact only"
        )
    return "coverage artifact only"


def _component(status: str, *notes: str) -> _ComponentEvidence:
    if status not in DATASHEET_SUPPORT_COMPONENT_VALUES:
        raise ValueError(f"Unsupported datasheet support status: {status}.")
    return _ComponentEvidence(status=status, notes=tuple(note for note in notes if note))


def _validate_mustering_text(field_name: str, value: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _validate_mustering_text_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ValueError(f"{field_name} must be a tuple.")
    return tuple(_validate_mustering_text(field_name, value) for value in values)


def _validate_mustering_support_stage(value: str) -> str:
    if type(value) is not str or value not in MUSTERING_SUPPORT_STAGE_VALUES:
        raise ValueError("MusteringSupportRow support_stage is not supported.")
    return value


def _missing_note(prefix: str, values: Iterable[str]) -> str:
    return f"{prefix}: {_inline_code_list(tuple(values))}."


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the CORE V2 ability support matrix artifacts."
    )
    parser.add_argument("--source-json-dir", type=Path, default=DEFAULT_SOURCE_JSON_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-path", type=Path, default=DEFAULT_DOCS_PATH)
    parser.add_argument("--faction-docs-dir", type=Path, default=DEFAULT_FACTION_DOCS_DIR)
    return parser.parse_args()


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _load_source_artifacts(source_json_dir: Path) -> tuple[WahapediaJsonArtifact, ...]:
    if not source_json_dir.is_dir():
        raise ValueError("Ability support matrix source JSON directory must exist.")
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in REQUIRED_TABLES:
        artifact_path = source_json_dir / f"{table_name}.json"
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if type(payload) is not dict:
            raise ValueError("Wahapedia source artifact JSON must contain an object.")
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _runtime_semantic_status_counts(
    statuses: tuple[RuntimeContentSemanticStatus, ...],
) -> RuntimeContentSemanticStatusCountsPayload:
    return {
        "placeholder": sum(
            1 for status in statuses if status is RuntimeContentSemanticStatus.PLACEHOLDER
        ),
        "partial": sum(1 for status in statuses if status is RuntimeContentSemanticStatus.PARTIAL),
        "implemented": sum(
            1 for status in statuses if status is RuntimeContentSemanticStatus.IMPLEMENTED
        ),
    }


def _required_module_path(module_path: str | None) -> str:
    if module_path is None:
        raise ValueError("Runtime content semantic coverage row lacks module path.")
    return module_path


def _runtime_faction_army_rule_rows() -> tuple[AbilityCoverageRow, ...]:
    return (
        _implemented_faction_army_rule_row(
            faction_id=adepta_sororitas_army_rule.ADEPTA_SORORITAS_FACTION_ID,
            ability_id=adepta_sororitas_army_rule.HOOK_ID,
            ability_name=adepta_sororitas_army_rule.ACTS_OF_FAITH_ABILITY_NAME,
            semantic_category="faction.army_rule.acts_of_faith",
            runtime_consumer_ids=_adepta_sororitas_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=ADEPTUS_CUSTODES_FACTION_ID,
            ability_id=adeptus_custodes_army_rule.HOOK_ID,
            ability_name="Martial Ka'tah",
            semantic_category="faction.army_rule.martial_katah",
            runtime_consumer_ids=_adeptus_custodes_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=adeptus_mechanicus_army_rule.ADEPTUS_MECHANICUS_FACTION_ID,
            ability_id=adeptus_mechanicus_army_rule.HOOK_ID,
            ability_name="Doctrina Imperatives",
            semantic_category="faction.army_rule.doctrina_imperatives",
            runtime_consumer_ids=_adeptus_mechanicus_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
            ability_id=chaos_space_marines_army_rule.HOOK_ID,
            ability_name="Dark Pacts",
            semantic_category="faction.army_rule.dark_pacts",
            runtime_consumer_ids=_chaos_space_marines_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=death_guard_army_rule.DEATH_GUARD_FACTION_ID,
            ability_id=death_guard_army_rule.HOOK_ID,
            ability_name="Nurgle's Gift",
            semantic_category="faction.army_rule.nurgles_gift",
            runtime_consumer_ids=_death_guard_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=world_eaters_army_rule.WORLD_EATERS_FACTION_ID,
            ability_id=world_eaters_army_rule.HOOK_ID,
            ability_name="Blessings of Khorne",
            semantic_category="faction.army_rule.blessings_of_khorne",
            runtime_consumer_ids=_world_eaters_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=orks_army_rule.ORKS_FACTION_ID,
            ability_id=orks_army_rule.HOOK_ID,
            ability_name="Waaagh!",
            semantic_category="faction.army_rule.waaagh",
            runtime_consumer_ids=_orks_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=black_templars_army_rule.BLACK_TEMPLARS_FACTION_ID,
            ability_id=black_templars_army_rule.HOOK_ID,
            ability_name="Templar Vows",
            semantic_category="faction.army_rule.templar_vows",
            runtime_consumer_ids=_black_templars_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=chaos_knights_army_rule.CHAOS_KNIGHTS_FACTION_ID,
            ability_id=chaos_knights_army_rule.HOOK_ID,
            ability_name="Harbingers of Dread",
            semantic_category="faction.army_rule.harbingers_of_dread",
            runtime_consumer_ids=_chaos_knights_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=imperial_knights_army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
            ability_id=imperial_knights_army_rule.HOOK_ID,
            ability_name="Code Chivalric",
            semantic_category="faction.army_rule.code_chivalric",
            runtime_consumer_ids=_imperial_knights_code_chivalric_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=imperial_knights_army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
            ability_id=imperial_knights_army_rule.BONDSMAN_HOOK_ID,
            ability_name="Bondsman",
            semantic_category="faction.army_rule.bondsman",
            runtime_consumer_ids=_imperial_knights_bondsman_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=astra_militarum_army_rule.ASTRA_MILITARUM_FACTION_ID,
            ability_id=astra_militarum_army_rule.HOOK_ID,
            ability_name="Voice of Command",
            semantic_category="faction.army_rule.voice_of_command",
            runtime_consumer_ids=_astra_militarum_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=emperors_children_army_rule.EMPERORS_CHILDREN_FACTION_ID,
            ability_id=emperors_children_army_rule.HOOK_ID,
            ability_name="Thrill Seekers",
            semantic_category="faction.army_rule.thrill_seekers",
            runtime_consumer_ids=_emperors_children_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=space_marines_army_rule.SPACE_MARINES_FACTION_ID,
            ability_id=space_marines_army_rule.HOOK_ID,
            ability_name="Oath of Moment",
            semantic_category="faction.army_rule.oath_of_moment",
            runtime_consumer_ids=_space_marines_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=tau_empire_army_rule.TAU_EMPIRE_FACTION_ID,
            ability_id=tau_empire_army_rule.HOOK_ID,
            ability_name="For the Greater Good",
            semantic_category="faction.army_rule.for_the_greater_good",
            runtime_consumer_ids=_tau_empire_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=thousand_sons_army_rule.THOUSAND_SONS_FACTION_ID,
            ability_id=thousand_sons_army_rule.HOOK_ID,
            ability_name="Cabal of Sorcerers",
            semantic_category="faction.army_rule.cabal_of_sorcerers",
            runtime_consumer_ids=_thousand_sons_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id=genestealer_cults_cult_ambush.GENESTEALER_CULTS_FACTION_ID,
            ability_id=genestealer_cults_cult_ambush.SOURCE_RULE_ID,
            ability_name="Cult Ambush",
            semantic_category="faction.army_rule.cult_ambush",
            runtime_consumer_ids=(
                genestealer_cults_cult_ambush.SOURCE_RULE_ID,
                genestealer_cults_cult_ambush.BATTLE_FORMATION_HOOK_ID,
                genestealer_cults_cult_ambush.UNIT_DESTROYED_HOOK_ID,
                genestealer_cults_cult_ambush.TURN_END_HOOK_ID,
            ),
        ),
        _implemented_faction_army_rule_row(
            faction_id=tyranids_army_rule.TYRANIDS_FACTION_ID,
            ability_id=tyranids_army_rule.HOOK_ID,
            ability_name="Shadow in the Warp / Synapse",
            semantic_category="faction.army_rule.shadow_in_the_warp_synapse",
            runtime_consumer_ids=_tyranids_runtime_consumer_ids(),
        ),
        _implemented_faction_army_rule_row(
            faction_id="drukhari",
            ability_id=drukhari_army_rule.HOOK_ID,
            ability_name="Power from Pain",
            semantic_category="faction.army_rule.power_from_pain",
            runtime_consumer_ids=(
                drukhari_army_rule.CONTRIBUTION_ID,
                drukhari_army_rule.HOOK_ID,
            ),
        ),
        _implemented_faction_army_rule_row(
            faction_id="drukhari",
            ability_id="phase17g:drukhari:corsairs-and-travelling-players",
            ability_name="Corsairs and Travelling Players",
            semantic_category="faction.army_rule.corsairs_and_travelling_players",
            runtime_consumer_ids=("army-mustering:drukhari-corsairs-and-travelling-players",),
        ),
        _implemented_faction_army_rule_row(
            faction_id=leagues_of_votann_army_rule.LEAGUES_OF_VOTANN_FACTION_ID,
            ability_id=leagues_of_votann_army_rule.HOOK_ID,
            ability_name="Prioritised Efficiency",
            semantic_category="faction.army_rule.prioritised_efficiency",
            runtime_consumer_ids=_leagues_of_votann_runtime_consumer_ids(),
        ),
    )


def _implemented_faction_army_rule_row(
    *,
    faction_id: str,
    ability_id: str,
    ability_name: str,
    semantic_category: str,
    runtime_consumer_ids: tuple[str, ...],
) -> AbilityCoverageRow:
    faction_row = _source_faction_row(faction_id)
    return AbilityCoverageRow(
        catalog_id="runtime-content-warhammer-40000-11th",
        datasheet_id=faction_row.faction_id,
        datasheet_name=faction_row.name,
        ability_id=ability_id,
        ability_name=ability_name,
        source_kind=CatalogAbilitySourceKind.FACTION,
        source_wargear_id=None,
        catalog_support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        support_stage=AbilityCoverageSupportStage.ENGINE_CONSUMED,
        semantic_categories=(semantic_category,),
        runtime_consumer_ids=runtime_consumer_ids,
    )


def _source_faction_row(faction_id: str) -> faction_detachments_2026_27.SourceFactionRow:
    for row in faction_detachments_2026_27.faction_rows():
        if row.faction_id == faction_id:
            return row
    raise ValueError("Ability support matrix runtime row references unknown faction.")


def _adepta_sororitas_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = adepta_sororitas_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.battle_round_start_hook_bindings),
                *(binding.hook_id for binding in contribution.unit_destroyed_hook_bindings),
            }
        )
    )


def _adeptus_custodes_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = adeptus_custodes_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(
                    binding.hook_id
                    for binding in contribution.fight_unit_selected_grant_hook_bindings
                ),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _adeptus_mechanicus_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = adeptus_mechanicus_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.battle_round_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _chaos_space_marines_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = chaos_space_marines_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(
                    binding.hook_id
                    for binding in contribution.shooting_unit_selected_grant_hook_bindings
                ),
                *(
                    binding.hook_id
                    for binding in contribution.fight_unit_selected_grant_hook_bindings
                ),
                *(
                    binding.hook_id
                    for binding in contribution.attack_sequence_completed_hook_bindings
                ),
                *(
                    binding.hook_id
                    for binding in contribution.mortal_wound_feel_no_pain_hook_bindings
                ),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _death_guard_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = death_guard_army_rule.runtime_contribution()
    unit_characteristic_modifier_ids = tuple(
        binding.modifier_id for binding in contribution.unit_characteristic_modifier_bindings
    )
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.battle_formation_hook_bindings),
                *unit_characteristic_modifier_ids,
                *(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings),
                *(binding.modifier_id for binding in contribution.save_option_modifier_bindings),
                *(
                    binding.modifier_id
                    for binding in contribution.movement_budget_modifier_bindings
                ),
                *(
                    binding.modifier_id
                    for binding in contribution.objective_control_modifier_bindings
                ),
            }
        )
    )


def _world_eaters_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = world_eaters_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                world_eaters_army_rule.TOTAL_CARNAGE_HOOK_ID,
                *(binding.hook_id for binding in contribution.battle_round_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.charge_roll_modifier_bindings),
                *(
                    binding.hook_id
                    for binding in contribution.fight_activation_ability_hook_bindings
                ),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _orks_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = orks_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.command_phase_start_hook_bindings),
                *(binding.hook_id for binding in contribution.advance_eligibility_hook_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
                *(binding.modifier_id for binding in contribution.save_option_modifier_bindings),
            }
        )
    )


def _black_templars_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = black_templars_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.battle_round_start_hook_bindings),
                *(binding.hook_id for binding in contribution.charge_declaration_hook_bindings),
                *(
                    binding.hook_id
                    for binding in contribution.charge_target_restriction_hook_bindings
                ),
                *(binding.hook_id for binding in contribution.fall_back_hook_bindings),
                *(
                    binding.hook_id
                    for binding in contribution.phase_end_objective_control_hook_bindings
                ),
                *(binding.modifier_id for binding in contribution.wound_roll_modifier_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _chaos_knights_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = chaos_knights_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.battle_round_start_hook_bindings),
                *(binding.hook_id for binding in contribution.battle_shock_hook_bindings),
                *(
                    binding.modifier_id
                    for binding in contribution.unit_characteristic_modifier_bindings
                ),
                *(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings),
                *(binding.modifier_id for binding in contribution.wound_roll_modifier_bindings),
            }
        )
    )


def _imperial_knights_code_chivalric_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = imperial_knights_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                contribution.contribution_id,
                *(binding.handler_id for binding in contribution.event_handler_bindings),
                *(binding.hook_id for binding in contribution.battle_formation_hook_bindings),
                *(binding.hook_id for binding in contribution.unit_destroyed_hook_bindings),
                *(binding.hook_id for binding in contribution.shooting_unit_selected_hook_bindings),
                *(binding.hook_id for binding in contribution.fight_unit_selected_hook_bindings),
                *(
                    binding.modifier_id
                    for binding in contribution.movement_budget_modifier_bindings
                ),
                *(binding.modifier_id for binding in contribution.charge_roll_modifier_bindings),
                *(
                    binding.modifier_id
                    for binding in contribution.objective_control_modifier_bindings
                ),
                *(
                    binding.modifier_id
                    for binding in contribution.unit_characteristic_modifier_bindings
                ),
            }
        )
    )


def _imperial_knights_bondsman_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = imperial_knights_army_rule.runtime_contribution()
    return tuple(
        sorted(
            binding.hook_id
            for binding in contribution.command_phase_start_hook_bindings
            if binding.source_id == imperial_knights_army_rule.BONDSMAN_SOURCE_RULE_ID
        )
    )


def _astra_militarum_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = astra_militarum_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.command_phase_start_hook_bindings),
                *(binding.hook_id for binding in contribution.battle_shock_hook_bindings),
                *(
                    binding.modifier_id
                    for binding in contribution.unit_characteristic_modifier_bindings
                ),
                *(
                    binding.modifier_id
                    for binding in contribution.movement_budget_modifier_bindings
                ),
                *(
                    binding.modifier_id
                    for binding in contribution.objective_control_modifier_bindings
                ),
                *(binding.modifier_id for binding in contribution.save_option_modifier_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _emperors_children_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = emperors_children_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.advance_eligibility_hook_bindings),
                *(binding.hook_id for binding in contribution.fall_back_hook_bindings),
                *(
                    binding.hook_id
                    for binding in contribution.shooting_target_restriction_hook_bindings
                ),
                *(
                    binding.hook_id
                    for binding in contribution.charge_target_restriction_hook_bindings
                ),
            }
        )
    )


def _space_marines_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = space_marines_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                SPACE_MARINE_CHAPTERS_SOURCE_ID,
                *(binding.hook_id for binding in contribution.command_phase_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.wound_roll_modifier_bindings),
            }
        )
    )


def _tau_empire_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = tau_empire_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.shooting_phase_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _thousand_sons_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = thousand_sons_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.shooting_phase_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
                *(
                    binding.hook_id
                    for binding in contribution.mortal_wound_feel_no_pain_hook_bindings
                ),
            }
        )
    )


def _tyranids_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = tyranids_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.command_phase_start_hook_bindings),
                *(binding.hook_id for binding in contribution.battle_shock_hook_bindings),
                *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
            }
        )
    )


def _leagues_of_votann_runtime_consumer_ids() -> tuple[str, ...]:
    contribution = leagues_of_votann_army_rule.runtime_contribution()
    return tuple(
        sorted(
            {
                *(binding.hook_id for binding in contribution.command_phase_start_hook_bindings),
                *(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings),
                *(binding.modifier_id for binding in contribution.wound_roll_modifier_bindings),
            }
        )
    )


def support_matrix_markdown(
    category_rows: list[AbilityCoverageCategoryRowPayload],
    *,
    runtime_semantic_coverage: RuntimeContentSemanticCoveragePayload | None = None,
) -> str:
    runtime_semantic_payload = (
        runtime_content_semantic_coverage_payload()
        if runtime_semantic_coverage is None
        else runtime_semantic_coverage
    )
    lines = [
        "# Ability Support Matrix V2",
        "",
        (
            f"Generated by `{GENERATED_BY_COMMAND}`. Do not hand-edit the generated JSON or "
            "this Markdown summary."
        ),
        "",
        "This matrix summarizes the category-first support artifact in",
        "`data/generated/ability_coverage/ability_support_category_rows.json`.",
        "The raw per-ability rows remain available in",
        "`data/generated/ability_coverage/ability_coverage_rows.json`.",
        "Pregame mustering and list-construction rows are generated separately in",
        "`data/generated/ability_coverage/mustering_support_rows.json`.",
        "Runtime faction-content semantic status is generated separately in",
        "`data/generated/ability_coverage/runtime_content_semantic_coverage.json`.",
        "",
        "Support stages:",
        "",
        (
            "- `descriptor_only`: catalog descriptor exists, but no structured executable IR is "
            "available."
        ),
        (
            "- `ir_compiled_unsupported`: rule text compiled to IR with preserved diagnostics, "
            "but the IR is not supported."
        ),
        (
            "- `generic_ir_executable`: rule text compiled to supported generic IR and can "
            "execute through the generic IR handler, but is not necessarily consumed by a "
            "phase/query host."
        ),
        (
            "- `engine_consumed`: a structured descriptor, supported generic IR, or "
            "implementation-backed runtime content is consumed by a phase/query host through a "
            "named runtime consumer."
        ),
    ]
    lines.extend(_runtime_content_semantic_coverage_markdown(runtime_semantic_payload))
    lines.extend(_structured_support_sections_markdown())
    lines.extend(
        (
            "",
            (
                "Unknown Abilities are descriptors that are present in the canonical catalog but "
                "are not yet parsed into a supported IR template or tied to a runtime consumer. "
                "Parsed-but-unconsumed IR remains separated by its semantic category and support "
                "stage instead of being collapsed into Unknown Abilities."
            ),
            "",
            (
                "Broad CORE V1-to-CORE V2 category forecasting is intentionally deferred until "
                "current-edition faction-pack modifications are complete. Until then, this report "
                "only marks support from the current canonical rows, typed IR, descriptor "
                "consumers, explicitly declared runtime-content rows, and tests proving the "
                "behavior."
            ),
        )
    )
    lines.extend(_runtime_hook_inventory_markdown(category_rows))
    lines.append("")
    return "\n".join(lines)


def _runtime_content_semantic_coverage_markdown(
    payload: RuntimeContentSemanticCoveragePayload,
) -> list[str]:
    faction_counts = payload["faction_status_counts"]
    detachment_counts = payload["detachment_status_counts"]
    lines = [
        "",
        "## Runtime Content Semantic Coverage",
        "",
        (
            "Load support and semantic execution support are distinct. A row with "
            "`support_status: supported` has an importable runtime module; its "
            "`semantic_status` records whether source-backed gameplay execution is still a "
            "placeholder, partially implemented, or implemented."
        ),
        "",
        ("| Family | Placeholder | Partial | Implemented |"),
        "| --- | ---: | ---: | ---: |",
        _runtime_semantic_count_row("Faction", faction_counts),
        _runtime_semantic_count_row("Detachment", detachment_counts),
        "",
        (
            "| Faction | Faction semantic status | Placeholder detachments | "
            "Partial detachments | Implemented detachments |"
        ),
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in payload["factions"]:
        counts = row["detachment_status_counts"]
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row["faction_name"]),
                    f"`{_markdown_text(row['semantic_status'])}`",
                    str(counts["placeholder"]),
                    str(counts["partial"]),
                    str(counts["implemented"]),
                )
            )
            + " |"
        )
    return lines


def _runtime_semantic_count_row(
    label: str,
    counts: RuntimeContentSemanticStatusCountsPayload,
) -> str:
    return (
        "| "
        + " | ".join(
            (
                _markdown_text(label),
                str(counts["placeholder"]),
                str(counts["partial"]),
                str(counts["implemented"]),
            )
        )
        + " |"
    )


def faction_support_markdown_files(
    *,
    datasheet_support_rows: tuple[DatasheetSupportRow, ...] | None = None,
    ability_rows: tuple[AbilityCoverageRow, ...] | None = None,
) -> dict[str, str]:
    if datasheet_support_rows is None or ability_rows is None:
        package = _ability_support_catalog_package()
        if ability_rows is None:
            ability_rows = _ability_support_matrix_rows_from_package(package)
        if datasheet_support_rows is None:
            datasheet_support_rows = _datasheet_support_rows_from_package(
                package=package,
                ability_rows=ability_rows,
            )
    ability_rows_by_id = {row.coverage_row_id: row for row in ability_rows}
    return {
        f"{faction_row.faction_id}.md": _faction_support_markdown(
            faction_row,
            datasheet_support_rows=tuple(
                row for row in datasheet_support_rows if row.faction_id == faction_row.faction_id
            ),
            ability_rows_by_id=ability_rows_by_id,
        )
        for faction_row in faction_detachments_2026_27.faction_rows()
    }


def _faction_support_markdown(
    faction_row: faction_detachments_2026_27.SourceFactionRow,
    *,
    datasheet_support_rows: tuple[DatasheetSupportRow, ...],
    ability_rows_by_id: Mapping[str, AbilityCoverageRow],
) -> str:
    pdf_record = _faction_pdf_record(faction_row.faction_id)
    coverage_rows = tuple(
        row
        for row in faction_coverage_2026_27.coverage_rows()
        if row.faction_id == faction_row.faction_id
    )
    army_rule_rows = _coverage_rows_for_kind(
        coverage_rows,
        Phase17ECoverageKind.FACTION_ARMY_RULE,
    )
    detachment_rule_rows = _coverage_rows_for_kind(
        coverage_rows,
        Phase17ECoverageKind.DETACHMENT_RULE,
    )
    detachment_support_rows = _detachment_rule_support_rows_for_faction(
        faction_row.faction_id,
    )
    enhancement_rows = _coverage_rows_for_kind(
        coverage_rows,
        Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
    )
    stratagem_rows = _coverage_rows_for_kind(
        coverage_rows,
        Phase17ECoverageKind.DETACHMENT_STRATAGEM,
    )
    exact_rows = (*enhancement_rows, *stratagem_rows)
    engine_consumed_row_count = _engine_consumed_coverage_row_count(
        (*army_rule_rows, *detachment_rule_rows, *exact_rows)
    )
    supported_detachment_count = sum(
        1 for row in detachment_support_rows if _detachment_rule_is_supported(row)
    )
    lines = [
        f"# {faction_row.name} Support Matrix",
        "",
        (
            f"Generated by `{GENERATED_BY_COMMAND}`. Do not hand-edit this generated "
            "faction support file."
        ),
        "",
        (
            "Source PDF: "
            f"[{_markdown_text(pdf_record.pdf_filename)}]"
            f"(<../../data/raw/faction_packs/{pdf_record.pdf_filename}>)"
        ),
        "",
        "## Summary",
        "",
        (
            "| Detachment rules | Supported detachment rules | Exact Enhancements | "
            "Exact Stratagems | Engine-consumed rows |"
        ),
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {len(detachment_rule_rows)} | {supported_detachment_count} | "
            f"{len(enhancement_rows)} | {len(stratagem_rows)} | {engine_consumed_row_count} |"
        ),
    ]
    if faction_row.faction_id == CHAOS_DAEMONS_FACTION_ID:
        lines.extend(_chaos_daemons_semantic_snapshot_markdown())
    lines.extend(_faction_detachment_rule_support_markdown(detachment_support_rows))
    lines.extend(
        _faction_datasheet_support_markdown(
            faction_row=faction_row,
            rows=datasheet_support_rows,
            ability_rows_by_id=ability_rows_by_id,
        )
    )
    lines.extend(_faction_detachment_rule_coverage_rows_markdown(detachment_rule_rows))
    lines.extend(_faction_exact_rule_rows_markdown("Enhancements", enhancement_rows))
    lines.extend(_faction_exact_rule_rows_markdown("Stratagems", stratagem_rows))
    lines.append("")
    return "\n".join(lines)


def _engine_consumed_coverage_row_count(rows: Iterable[Phase17ECoverageRow]) -> int:
    return sum(1 for row in rows if _coverage_row_is_engine_consumed(row))


def _coverage_row_is_engine_consumed(row: Phase17ECoverageRow) -> bool:
    return row.status is Phase17ECoverageStatus.IMPLEMENTED or bool(row.runtime_consumer_ids)


def _faction_detachment_rule_support_markdown(
    rows: tuple[DetachmentRuleSupportRow, ...],
) -> list[str]:
    lines = [
        "",
        "## Detachment Rule Support",
        "",
        (
            "This table reports semantic engine support. `Full` means the current CORE V2 "
            "scope has gameplay hooks plus focused tests; `None` means only source rows "
            "and generated scaffold exist."
        ),
        "",
        "| Detachment | Overall support | Engine support | Tests | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row.detachment),
                    f"`{_markdown_text(row.overall)}`",
                    _markdown_text(row.engine),
                    _markdown_text(row.tests),
                    _markdown_text(row.notes),
                )
            )
            + " |"
        )
    return lines


def _chaos_daemons_semantic_snapshot_markdown() -> list[str]:
    lines = [
        "",
        "## Semantic Support Snapshot",
        "",
        (
            "This generated snapshot answers the support question directly. Detachment-rule "
            "support uses the semantic support table below. Exact Enhancement and Stratagem "
            "support is stricter: a source row is fully supported here only when it carries "
            "runtime consumer IDs. Datasheet support is fully supported only for source-review "
            "rows whose IR coverage is `All consumed`."
        ),
    ]
    lines.extend(_chaos_daemons_detachment_snapshot_markdown())
    lines.extend(_chaos_daemons_exact_enhancement_snapshot_markdown())
    lines.extend(_chaos_daemons_exact_stratagem_snapshot_markdown())
    lines.extend(_chaos_daemons_datasheet_snapshot_markdown())
    return lines


def _chaos_daemons_detachment_snapshot_markdown() -> list[str]:
    rows = _detachment_rule_support_rows_for_faction(CHAOS_DAEMONS_FACTION_ID)
    fully_supported = tuple(row.detachment for row in rows if _detachment_rule_is_supported(row))
    needs_support = tuple(row.detachment for row in rows if not _detachment_rule_is_supported(row))
    return [
        "",
        "### Detachments",
        "",
        "| Fully supported | Still needs semantic support |",
        "| --- | --- |",
        f"| {_markdown_line_list(fully_supported)} | {_markdown_line_list(needs_support)} |",
    ]


def _chaos_daemons_exact_enhancement_snapshot_markdown() -> list[str]:
    rows = tuple(
        (
            row.detachment_name,
            row.name,
            bool(row.runtime_consumer_ids),
        )
        for row in faction_subrules_2026_27.enhancement_rows()
        if row.faction_id == CHAOS_DAEMONS_FACTION_ID
    )
    return _chaos_daemons_exact_source_rows_snapshot_markdown(
        title="Enhancements",
        rows=rows,
    )


def _chaos_daemons_exact_stratagem_snapshot_markdown() -> list[str]:
    rows = tuple(
        (
            row.detachment_name,
            row.name,
            bool(row.runtime_consumer_ids),
        )
        for row in faction_subrules_2026_27.stratagem_rows()
        if row.faction_id == CHAOS_DAEMONS_FACTION_ID
    )
    return _chaos_daemons_exact_source_rows_snapshot_markdown(
        title="Stratagems",
        rows=rows,
    )


def _chaos_daemons_exact_source_rows_snapshot_markdown(
    *,
    title: str,
    rows: tuple[tuple[str, str, bool], ...],
) -> list[str]:
    lines = [
        "",
        f"### {title}",
        "",
        (
            "| Detachment | Fully supported / runtime consumers registered | "
            "Still source-only / needs semantic registration |"
        ),
        "| --- | --- | --- |",
    ]
    for detachment_name in sorted({row[0] for row in rows}):
        supported = tuple(
            sorted(
                rule_name
                for detachment, rule_name, is_supported in rows
                if (detachment == detachment_name and is_supported)
            )
        )
        needs_support = tuple(
            sorted(
                rule_name
                for detachment, rule_name, is_supported in rows
                if (detachment == detachment_name and not is_supported)
            )
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(detachment_name),
                    _markdown_line_list(supported),
                    _markdown_line_list(needs_support),
                )
            )
            + " |"
        )
    return lines


def _chaos_daemons_datasheet_snapshot_markdown() -> list[str]:
    lines = [
        "",
        "### Unit Datasheets",
        "",
        (
            "| Allegiance | Fully supported (`All consumed`) | IR parsed; host needed | "
            "Unsupported IR | Bridge/catalog blocked |"
        ),
        "| --- | --- | --- | --- | --- |",
    ]
    for group in _chaos_daemons_datasheet_review_groups():
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(group.allegiance),
                    _chaos_daemons_datasheet_names_for_status(group.rows, "All consumed"),
                    _chaos_daemons_datasheet_names_for_status(group.rows, "IR parsed; host needed"),
                    _chaos_daemons_datasheet_names_for_status(group.rows, "Unsupported IR"),
                    _chaos_daemons_datasheet_names_for_status(group.rows, "Bridge/catalog blocked"),
                )
            )
            + " |"
        )
    return lines


def _chaos_daemons_datasheet_names_for_status(
    rows: tuple[DatasheetGroupReviewRow, ...],
    ir_coverage: str,
) -> str:
    return _markdown_line_list(
        f"{row.datasheet} (`{row.datasheet_id}`)"
        for row in sorted(
            rows,
            key=lambda review_row: (review_row.datasheet.lower(), review_row.datasheet_id),
        )
        if row.ir_coverage == ir_coverage
    )


def _faction_datasheet_support_markdown(
    *,
    faction_row: faction_detachments_2026_27.SourceFactionRow,
    rows: tuple[DatasheetSupportRow, ...],
    ability_rows_by_id: Mapping[str, AbilityCoverageRow],
) -> list[str]:
    sorted_rows = tuple(
        sorted(rows, key=lambda row: (row.datasheet_name.lower(), row.datasheet_id))
    )
    lines = [
        "",
        "## Datasheet / Unit Support",
        "",
        (
            "This table reports datasheet-level playability evidence. `Full` means "
            "catalog/model/wargear/geometry data is present and every known datasheet/"
            "wargear ability row is engine-consumed by named runtime consumers, with no "
            "unsupported diagnostics. `Playable` means core unit operation is available but "
            "one or more non-blocking generic IR, ability-detail, faction, or detachment "
            "proofs are incomplete. `Partial` means at least one known ability or interaction is "
            "descriptor-only or unsupported. `Catalog-only` means the unit is present but no "
            "semantic ability/runtime support is proven. `Blocked` means a known unsupported "
            "rule, missing geometry, missing wargear, or missing required source data "
            "prevents safe play."
        ),
        "",
    ]
    if faction_row.faction_id == "chaos-daemons":
        lines.extend(_chaos_daemons_datasheet_review_markdown())
    lines.extend(
        (
            (
                "| Datasheet | Overall | Catalog | Models / geometry | Wargear | "
                "Weapon keywords | Datasheet abilities | Faction / detachment interactions | "
                "Tests / evidence | Notes |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        )
    )
    if not sorted_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    f"No generated catalog datasheets for {_markdown_text(faction_row.name)}",
                    f"`{DATASHEET_SUPPORT_UNKNOWN}`",
                    DATASHEET_SUPPORT_UNKNOWN,
                    DATASHEET_SUPPORT_UNKNOWN,
                    DATASHEET_SUPPORT_UNKNOWN,
                    DATASHEET_SUPPORT_NONE,
                    DATASHEET_SUPPORT_NONE,
                    DATASHEET_SUPPORT_NONE,
                    "coverage artifact only",
                    (
                        "Generated catalog/support artifacts do not contain datasheet rows "
                        "for this faction."
                    ),
                )
            )
            + " |"
        )
        return lines
    for row in sorted_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _datasheet_label(row),
                    f"`{_markdown_text(row.overall)}`",
                    _markdown_text(row.catalog_status),
                    _markdown_text(row.model_geometry_status),
                    _markdown_text(row.wargear_status),
                    _markdown_text(row.weapon_keyword_status),
                    _markdown_text(row.datasheet_ability_status),
                    _markdown_text(_faction_interaction_cell(row)),
                    _markdown_text(row.tests_evidence),
                    _markdown_text(row.notes),
                )
            )
            + " |"
        )
    detail_rows = tuple(row for row in sorted_rows if row.overall != DATASHEET_SUPPORT_FULL)
    if not detail_rows:
        return lines
    lines.extend(
        (
            "",
            "### Datasheet Ability Details",
            "",
            (
                "| Datasheet | Ability | Source kind | Support stage | Semantic categories | "
                "Runtime consumers | Diagnostics |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- |",
        )
    )
    for row in detail_rows:
        if not row.ability_coverage_row_ids:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _datasheet_label(row),
                        "No AbilityCoverageRow",
                        "",
                        "",
                        "",
                        "",
                        "No generated ability coverage rows for this datasheet.",
                    )
                )
                + " |"
            )
            continue
        for coverage_row_id in row.ability_coverage_row_ids:
            coverage_row = ability_rows_by_id.get(coverage_row_id)
            if coverage_row is None:
                raise ValueError(
                    "Datasheet support detail row references unknown ability coverage."
                )
            lines.append(
                "| "
                + " | ".join(
                    (
                        _datasheet_label(row),
                        _ability_detail_label(coverage_row),
                        f"`{_markdown_text(coverage_row.source_kind.value)}`",
                        f"`{_markdown_text(coverage_row.support_stage.value)}`",
                        _inline_code_list(coverage_row.semantic_categories),
                        _inline_code_list(coverage_row.runtime_consumer_ids),
                        _inline_code_list(coverage_row.diagnostic_reasons),
                    )
                )
                + " |"
            )
    return lines


def _chaos_daemons_datasheet_review_markdown() -> list[str]:
    lines: list[str] = []
    lines.extend(_chaos_daemons_khorne_review_markdown())
    lines.extend(
        _chaos_daemons_allegiance_review_markdown(
            heading="Tzeentch",
            intro=(
                "This source-review table covers Chaos Daemons datasheets in the "
                "11th edition Chaos Daemons Faction Pack pages 38-63. Those PDF pages "
                "are authoritative for Tzeentch datasheets in this review and supersede "
                "Wahapedia rows where both sources have a unit. Wahapedia-only Tzeentch "
                "rows absent from the PDF are excluded from this review."
            ),
            rows=_chaos_daemons_tzeentch_review_rows(),
        )
    )
    lines.extend(
        _chaos_daemons_allegiance_review_markdown(
            heading="Nurgle",
            intro=(
                "This source-review table covers Chaos Daemons datasheets in the "
                "11th edition Chaos Daemons Faction Pack pages 64-87. Those PDF pages "
                "are authoritative for Nurgle datasheets in this review and supersede "
                "Wahapedia rows where both sources have a unit. Wahapedia-only Nurgle "
                "rows absent from the PDF are excluded from this review."
            ),
            rows=_chaos_daemons_nurgle_review_rows(),
        )
    )
    lines.extend(
        _chaos_daemons_allegiance_review_markdown(
            heading="Slaanesh",
            intro=(
                "This source-review table covers Chaos Daemons datasheets in the "
                "11th edition Chaos Daemons Faction Pack pages 88-111. Those PDF pages "
                "are authoritative for Slaanesh datasheets in this review and supersede "
                "Wahapedia rows where both sources have a unit. Wahapedia-only Slaanesh "
                "rows absent from the PDF are excluded from this review."
            ),
            rows=_chaos_daemons_slaanesh_review_rows(),
        )
    )
    lines.extend(
        _chaos_daemons_allegiance_review_markdown(
            heading="Undivided",
            intro=(
                "This source-review table covers Chaos Daemons datasheets in the "
                "11th edition Chaos Daemons Faction Pack pages 112-119 that do not belong "
                "to a formal Khorne, Tzeentch, Nurgle, or Slaanesh allegiance section. "
                "The PDF does not use an `Undivided` keyword for these rows, but Shadow "
                "Legion rules refer to them as Undivided. Wahapedia-only no-god rows absent "
                "from the PDF are excluded from this review."
            ),
            rows=_chaos_daemons_undivided_review_rows(),
        )
    )
    return lines


def _chaos_daemons_datasheet_review_groups() -> tuple[ChaosDaemonsDatasheetReviewGroup, ...]:
    return (
        ChaosDaemonsDatasheetReviewGroup("Khorne", _chaos_daemons_khorne_review_rows()),
        ChaosDaemonsDatasheetReviewGroup("Tzeentch", _chaos_daemons_tzeentch_review_rows()),
        ChaosDaemonsDatasheetReviewGroup("Nurgle", _chaos_daemons_nurgle_review_rows()),
        ChaosDaemonsDatasheetReviewGroup("Slaanesh", _chaos_daemons_slaanesh_review_rows()),
        ChaosDaemonsDatasheetReviewGroup("Undivided", _chaos_daemons_undivided_review_rows()),
    )


def _chaos_daemons_allegiance_review_markdown(
    *,
    heading: str,
    intro: str,
    rows: tuple[DatasheetGroupReviewRow, ...],
) -> list[str]:
    lines = [
        f"### {heading}",
        "",
        (
            f"{intro} `All consumed` means every known non-core datasheet or wargear "
            "ability is currently consumed by a named runtime host. `IR parsed; host needed` "
            "means the rule text compiles to supported structured IR but at least one compiled "
            "semantic still has no phase/query consumer. `Unsupported IR` means at least one "
            "known ability still compiles with unsupported diagnostics. `Bridge/catalog blocked` "
            "means a source-shape or catalog-normalization gap blocks safe generated catalog use "
            "even when some ability text can be reviewed."
        ),
        "",
        (
            "| Datasheet | Source basis | IR coverage | Supported semantics | "
            "IR semantics still needed | Bridge / catalog blockers |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(
        rows, key=lambda review_row: (review_row.datasheet.lower(), review_row.datasheet_id)
    ):
        lines.append(_chaos_daemons_review_row_markdown(row))
    lines.append("")
    return lines


def _chaos_daemons_khorne_review_markdown() -> list[str]:
    lines = [
        "### Khorne",
        "",
        (
            "This source-review table covers Chaos Daemons datasheets that carry the "
            "`Khorne` keyword. The 11th edition Chaos Daemons Faction Pack pages 14-37 "
            "are authoritative for this 11th edition review. Wahapedia-only discontinued "
            "Khorne-labeled rows, including An'ggrath the Unbound and Chaos Lord On "
            "Juggernaut, are excluded. The PDF Karanak datasheet supersedes the duplicate "
            "Wahapedia Karanak row, so it is not counted separately. "
            "`All consumed` means every known non-core datasheet or wargear ability is "
            "currently consumed by a named runtime host. `IR parsed; host needed` means "
            "the rule text compiles to supported structured IR but at least one compiled "
            "semantic still has no phase/query consumer. `Unsupported IR` means at least "
            "one known ability still compiles with unsupported diagnostics. "
            "`Bridge/catalog blocked` means a source-shape or catalog-normalization gap "
            "blocks safe generated catalog use even when some ability text can be reviewed."
        ),
        "",
        (
            "| Datasheet | Source basis | IR coverage | Supported semantics | "
            "IR semantics still needed | Bridge / catalog blockers |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(
        _chaos_daemons_khorne_review_rows(),
        key=lambda review_row: (review_row.datasheet.lower(), review_row.datasheet_id),
    ):
        lines.append(_chaos_daemons_review_row_markdown(row))
    lines.append("")
    return lines


def _chaos_daemons_review_row_markdown(row: DatasheetGroupReviewRow) -> str:
    return (
        "| "
        + " | ".join(
            (
                f"{_markdown_text(row.datasheet)} (`{_markdown_text(row.datasheet_id)}`)",
                _markdown_text(row.source_basis),
                _markdown_text(row.ir_coverage),
                _markdown_text(row.supported_semantics),
                _markdown_text(row.semantics_needed),
                _markdown_text(row.catalog_blockers),
            )
        )
        + " |"
    )


def _chaos_daemons_khorne_review_rows() -> tuple[DatasheetGroupReviewRow, ...]:
    return (
        DatasheetGroupReviewRow(
            datasheet="Bloodcrushers",
            datasheet_id="000001115",
            source_basis="PDF pages 30-31; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, Brass Stampede move-completed mortal wounds, The Shadow of "
                "Chaos, Daemonic Icon Leadership, and Instrument of Chaos charge modifier."
            ),
            semantics_needed="None.",
            catalog_blockers="No known datasheet-level blockers.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Bloodletters",
            datasheet_id="000001114",
            source_basis="PDF pages 28-29; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, Daemonic Icon Leadership, and "
                "Instrument of Chaos charge modifier are consumed."
            ),
            semantics_needed=(
                "Bane of Cowards compiles to Desperate Escape test and roll-modifier IR, "
                "but still needs a phase/query consumer."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Bloodmaster",
            datasheet_id="000001455",
            source_basis="PDF pages 20-21; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike and The Shadow of Chaos are consumed; Bloodmaster wound "
                "modifier compiles to generic IR."
            ),
            semantics_needed=(
                "A Gory Path unsupported diagnostics; Bloodmaster selected-unit wound "
                "modifier host; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Bloodthirster",
            datasheet_id="000002582",
            source_basis="PDF pages 16-17; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, Deadly Demise descriptor evidence, The Shadow of Chaos, "
                "Daemon Lord of Khorne hit-roll aura, Greater Daemon of Khorne Shadow aura, "
                "and Relentless Carnage end-of-Fight mortal wounds are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Flesh Hounds",
            datasheet_id="000001112",
            source_basis="PDF pages 32-33; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, Hunters from the Warp reserve placement, The Shadow of Chaos, "
                "and Collar of Khorne Feel No Pain."
            ),
            semantics_needed="None.",
            catalog_blockers="No known datasheet-level blockers.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Karanak",
            datasheet_id="000001104",
            source_basis="PDF pages 26-27; supersedes Wahapedia and duplicate row 000004102.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Pack Leader Advance/Charge rerolls, Prey of the Blood God "
                "tracked-target rerolls/reselect, The Shadow of Chaos, and Brass Collar of "
                "Bloody Vengeance Feel No Pain."
            ),
            semantics_needed="Leader row consumer evidence.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Rendmaster On Blood Throne",
            datasheet_id="000001111",
            source_basis="PDF pages 24-25; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Champion Slayer wound rerolls and lost-wound restoration, "
                "and The Shadow of Chaos."
            ),
            semantics_needed="Blood Throne aura/targeted bonus unsupported diagnostics.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Skarbrand",
            datasheet_id="000001105",
            source_basis="PDF pages 14-15; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Murderlust Advance-and-Charge, and The Shadow of Chaos."
            ),
            semantics_needed=(
                "Deadly Demise descriptor consumer evidence; Greater Daemon of Khorne "
                "Shadow aura host; Rage Embodied characteristic-modifier aura host."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Skull Altar",
            datasheet_id="000001588",
            source_basis="PDF pages 36-37; supersedes Wahapedia.",
            ir_coverage="Bridge/catalog blocked",
            supported_semantics="Infiltrators and The Shadow of Chaos are known structured paths.",
            semantics_needed=(
                "Shadow of Khorne aura; Cover and Fortification datasheet terrain semantics; "
                "Fortification hit-roll and Desperate Escape exceptions."
            ),
            catalog_blockers=(
                "No-equipment/no-option source rows are normalized; Hull footprint geometry "
                "still requires an explicit geometry override."
            ),
        ),
        DatasheetGroupReviewRow(
            datasheet="Skull Cannon",
            datasheet_id="000001116",
            source_basis="PDF pages 34-35; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics="Deep Strike and The Shadow of Chaos are consumed.",
            semantics_needed="Skulls of the Fallen Battle-shock trigger unsupported diagnostics.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Skullmaster",
            datasheet_id="000001456",
            source_basis="PDF pages 22-23; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike and The Shadow of Chaos are consumed; Skullmaster's Fury "
                "compiles to generic weapon-ability grant IR."
            ),
            semantics_needed=(
                "Devastating Charge unsupported diagnostics; Skullmaster's Fury runtime host; "
                "Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Skulltaker",
            datasheet_id="000001106",
            source_basis="PDF pages 18-19; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Lord of Decapitations Devastating Wounds grant, and The Shadow "
                "of Chaos."
            ),
            semantics_needed=(
                "Skulls for Khorne unsupported diagnostics; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
    )


def _chaos_daemons_tzeentch_review_rows() -> tuple[DatasheetGroupReviewRow, ...]:
    return (
        DatasheetGroupReviewRow(
            datasheet="Blue Horrors",
            datasheet_id="000002583",
            source_basis="PDF pages 52-53; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Infiltrators, The Shadow of Chaos, and Sullen Malevolence "
                "Leadership modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Split model-addition semantics; Exploding Horrors self-destruction and "
                "mortal-wound routing."
            ),
            catalog_blockers="PDF-backed Split composition normalization still needs review.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Burning Chariot",
            datasheet_id="000001128",
            source_basis="PDF pages 62-63; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Eldritch Flames post-shoot Benefit "
                "of Cover denial are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Changecaster",
            datasheet_id="000001462",
            source_basis="PDF pages 50-51; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and ranged Sustained Hits 1 grant "
                "semantics are structured paths."
            ),
            semantics_needed="Post-shoot Battle-shock trigger and Leader row consumer evidence.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Exalted Flamer",
            datasheet_id="000001126",
            source_basis="PDF pages 58-59; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Blazing Warpfire Assault grant "
                "semantics are structured paths."
            ),
            semantics_needed=(
                "Flames of Change aflame target state with Move, Advance, and Charge "
                "modifiers; Manifestation of Destruction restrictions; Leader row consumer "
                "evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Fateskimmer",
            datasheet_id="000001463",
            source_basis="PDF pages 44-45; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, Fateskimmer melee Lethal Hits grant, "
                "and Rider of Immaterial Winds turn-end reserves semantics are structured "
                "paths."
            ),
            semantics_needed="Leader row consumer evidence for Screamers attachments.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Flamers",
            datasheet_id="000001125",
            source_basis="PDF pages 56-57; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Bounding Leaps Fall Back and shoot "
                "semantics are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Fluxmaster",
            datasheet_id="000001464",
            source_basis="PDF pages 46-47; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and led-unit hit modifier semantics are "
                "structured paths."
            ),
            semantics_needed=(
                "Altered Reality dice-result substitution and Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Kairos Fateweaver",
            datasheet_id="000001117",
            source_basis="PDF pages 38-39; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, and The Shadow of Chaos are known structured paths."
            ),
            semantics_needed=(
                "Greater Daemon of Tzeentch Shadow aura host; Leadership-test CP gain; "
                "One Head Looks Back Stratagem-cost increase."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Lord of Change",
            datasheet_id="000001120",
            source_basis="PDF pages 40-41; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, The Shadow of Chaos, Master of Magicks "
                "named weapon ability choice semantics, Greater Daemon of Tzeentch Shadow "
                "aura, and Daemon Lord of Tzeentch ranged Strength aura are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Pink Horrors",
            datasheet_id="000002584",
            source_basis="PDF pages 54-55; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, Daemonic Icon Leadership, and "
                "Instrument of Chaos charge modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Split model-addition semantics and Blue Horrors datasheet handoff when "
                "no Pink Horror models remain."
            ),
            catalog_blockers="PDF-backed Split composition normalization still needs review.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Screamers",
            datasheet_id="000001127",
            source_basis="PDF pages 60-61; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics="Deep Strike and The Shadow of Chaos are consumed.",
            semantics_needed="Slashing Dive moved-over mortal wounds with PathWitness evidence.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="The Blue Scribes",
            datasheet_id="000001119",
            source_basis="PDF pages 48-49; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Lone Operative, The Shadow of Chaos, and Psychic wound-roll "
                "modifier semantics are structured paths."
            ),
            semantics_needed="Sorcerous Barrages variable mortal-wound routing.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="The Changeling",
            datasheet_id="000001118",
            source_basis="PDF pages 42-43; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Lone Operative, Stealth, and The Shadow of Chaos are consumed."
            ),
            semantics_needed=(
                "Formless Horror pre-target Battle-shock and target-denial trigger; Mischief "
                "and Confusion random hit/no-shoot outcome."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
    )


def _chaos_daemons_nurgle_review_rows() -> tuple[DatasheetGroupReviewRow, ...]:
    return (
        DatasheetGroupReviewRow(
            datasheet="Beasts of Nurgle",
            datasheet_id="000001134",
            source_basis="PDF pages 82-83; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                'Deadly Demise 1, Deep Strike, Scouts 6", and The Shadow of Chaos are '
                "known structured paths."
            ),
            semantics_needed="Grotesque Regeneration end-of-phase healing.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Epidemius",
            datasheet_id="000001129",
            source_basis="PDF pages 72-73; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and led-unit 4+ invulnerable save "
                "semantics are structured paths."
            ),
            semantics_needed=(
                "Tally of Pestilence destroyed-model counter and Command phase CP reward; "
                "Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Feculent Gnarlmaw",
            datasheet_id="000001470",
            source_basis="PDF pages 86-87; supersedes Wahapedia.",
            ir_coverage="Bridge/catalog blocked",
            supported_semantics=(
                "Infiltrators, The Shadow of Chaos, and Shroud of Flies Stealth grant are "
                "known structured paths."
            ),
            semantics_needed=(
                "Diseased Cover terrain semantics; Shroud of Flies aura host; Fortification "
                "hit-roll and Desperate Escape exceptions."
            ),
            catalog_blockers=(
                "No-equipment/no-option source rows are normalized; Hull footprint geometry "
                "still requires an explicit geometry override."
            ),
        ),
        DatasheetGroupReviewRow(
            datasheet="Great Unclean One",
            datasheet_id="000001130",
            source_basis="PDF pages 66-67; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, Feel No Pain 6+, The Shadow of Chaos, and "
                "Daemon Lord of Nurgle Toughness modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Greater Daemon of Nurgle Shadow aura host; Nurgle's Rot Toughness debuff "
                "host; Reverberating Summons Plaguebearer revival."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Horticulous Slimux",
            datasheet_id="000001466",
            source_basis="PDF pages 76-77; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Beast Handler charge reroll semantics "
                "are structured paths."
            ),
            semantics_needed=(
                "Heroic Intervention Stratagem cost and extra-use semantics; Seed the Garden "
                "terrain Shadow extension; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Nurglings",
            datasheet_id="000001133",
            source_basis="PDF pages 80-81; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Infiltrators, The Shadow of Chaos, and Mischief Makers melee "
                "hit modifier semantics are structured paths."
            ),
            semantics_needed="Engagement-range aura host for Mischief Makers.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Plague Drones",
            datasheet_id="000001135",
            source_basis="PDF pages 84-85; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, Daemonic Icon Leadership, and "
                "Instrument of Chaos charge modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Death's Heads post-shoot tracked target and friendly Nurgle Daemons wound "
                "reroll host."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Plaguebearers",
            datasheet_id="000001132",
            source_basis="PDF pages 78-79; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, Daemonic Icon Leadership, and "
                "Instrument of Chaos charge modifier semantics, and Infected Outbreak "
                "sticky-objective control are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Poxbringer",
            datasheet_id="000001467",
            source_basis="PDF pages 68-69; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Feel No Pain 5+, The Shadow of Chaos, and critical-hit-on-5+ "
                "semantics are structured paths."
            ),
            semantics_needed=(
                "Feculent Despair Battle-shock modifier aura host; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Rotigus",
            datasheet_id="000001465",
            source_basis="PDF pages 64-65; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, Feel No Pain 6+, The Shadow of Chaos, and "
                "Virulent Blessing damage modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Greater Daemon of Nurgle Shadow aura host; Deluge Move and OC aura host; "
                "targeted damage bonus phase/query host."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Sloppity Bilepiper",
            datasheet_id="000001468",
            source_basis="PDF pages 74-75; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, led-unit Move modifier, and Advance "
                "reroll semantics are structured paths."
            ),
            semantics_needed=(
                "Disease of Mirth fight-start Battle-shock tests; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Spoilpox Scrivener",
            datasheet_id="000001469",
            source_basis="PDF pages 70-71; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, melee Sustained Hits 1 grant, and "
                "led-model OC modifier semantics are structured paths."
            ),
            semantics_needed="Leader row consumer evidence.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
    )


def _chaos_daemons_slaanesh_review_rows() -> tuple[DatasheetGroupReviewRow, ...]:
    return (
        DatasheetGroupReviewRow(
            datasheet="Contorted Epitome",
            datasheet_id="000001647",
            source_basis="PDF pages 98-99; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Fights First, The Shadow of Chaos, and Swallow Energy Feel "
                "No Pain semantics are structured paths."
            ),
            semantics_needed=(
                "Horrible Fascination random shooting debuff/no-shoot outcome and possible "
                "self mortal wounds; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Daemonettes",
            datasheet_id="000001142",
            source_basis="PDF pages 106-107; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Fights First, The Shadow of Chaos, Daemonic Icon Leadership, "
                "and Instrument of Chaos charge modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Horrifying Beauty fight-start Battle-shock test with below-half-strength "
                "Leadership modifier."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Fiends",
            datasheet_id="000001143",
            source_basis="PDF pages 108-109; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Soporific Musk Desperate Escape "
                "test and modifier semantics are structured paths."
            ),
            semantics_needed="Fall Back trigger host for Soporific Musk.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Hellflayers",
            datasheet_id="000001144",
            source_basis=(
                "PDF pages 102-103; supersedes Wahapedia and excludes singular row 000004101."
            ),
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and charge-completed melee Strength and "
                "Damage modifier semantics are structured paths."
            ),
            semantics_needed="Runtime host for Cutting Down the Foe after Charge moves.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Infernal Enrapturess",
            datasheet_id="000001589",
            source_basis="PDF pages 92-93; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Fights First, Leader, and The Shadow of Chaos are known "
                "structured paths."
            ),
            semantics_needed=(
                "Harmonic Alignment bodyguard-model return; Discordant Disruption Hazardous "
                "grant to enemy Psykers."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Keeper of Secrets",
            datasheet_id="000001137",
            source_basis="PDF pages 90-91; supersedes Wahapedia.",
            ir_coverage="Bridge/catalog blocked",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, The Shadow of Chaos, Mesmerising Form hit "
                "modifier, and Shining Aegis save semantics are structured paths."
            ),
            semantics_needed=(
                "Greater Daemon of Slaanesh Shadow aura host; Daemon Lord of Slaanesh AP aura host."
            ),
            catalog_blockers=(
                "Optional one-of wargear choice is not represented by current additive "
                "wargear-option semantics."
            ),
        ),
        DatasheetGroupReviewRow(
            datasheet="Seekers",
            datasheet_id="000001145",
            source_basis="PDF pages 110-111; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                'Deep Strike, Scouts 9", The Shadow of Chaos, Unholy Speed Advance/Charge '
                "rerolls, Daemonic Icon Leadership, and Instrument of Chaos charge modifier."
            ),
            semantics_needed="None.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Shalaxi Helbane",
            datasheet_id="000001648",
            source_basis="PDF pages 88-89; supersedes Wahapedia.",
            ir_coverage="All consumed",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, The Shadow of Chaos, No Prey Too Great "
                "Advance/Charge rerolls, Monarch of the Hunt quarry rerolls, and Greater "
                "Daemon of Slaanesh Shadow aura are consumed."
            ),
            semantics_needed="None.",
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Syll'esske",
            datasheet_id="000001649",
            source_basis="PDF pages 96-97; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Prince of Slaanesh critical wound "
                "modifier semantics are structured paths."
            ),
            semantics_needed=(
                "Delightful Agonies destroyed-model resurrection; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="The Masque of Slaanesh",
            datasheet_id="000001136",
            source_basis="PDF pages 94-95; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Fights First, Lone Operative, The Shadow of Chaos, and "
                "Dazzling Acrobatics charge-after-Advance/Fall Back semantics are "
                "structured paths."
            ),
            semantics_needed=(
                "Eternal Dance fight-start selected-enemy wound modifier and enemy wound "
                "modifier host."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Tormentbringer",
            datasheet_id="000004100",
            source_basis=(
                "PDF pages 100-101; supersedes Wahapedia and older chariot row 000001141."
            ),
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, The Shadow of Chaos, and Tormentbringer melee Sustained Hits "
                "1 aura grant semantics are structured paths."
            ),
            semantics_needed=(
                "Hysterical Frenzy fight-on-death trigger; Leader row consumer evidence."
            ),
            catalog_blockers=(
                "Leader target normalization must ignore excluded singular Hellflayer row "
                "000004101."
            ),
        ),
        DatasheetGroupReviewRow(
            datasheet="Tranceweaver",
            datasheet_id="000001138",
            source_basis="PDF pages 104-105; supersedes Wahapedia.",
            ir_coverage="IR parsed; host needed",
            supported_semantics=(
                "Deep Strike, Fights First, The Shadow of Chaos, and hit-reroll semantics "
                "are structured paths."
            ),
            semantics_needed=(
                "Objective-range conditional full hit reroll; Symphony of Pain battle-shocked "
                "target host; Leader row consumer evidence."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
    )


def _chaos_daemons_undivided_review_rows() -> tuple[DatasheetGroupReviewRow, ...]:
    return (
        DatasheetGroupReviewRow(
            datasheet="Be'lakor",
            datasheet_id="000001148",
            source_basis="PDF pages 112-113; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D6, Stealth, and The Shadow of Chaos are known "
                "structured paths."
            ),
            semantics_needed=(
                "The Dark Master Shadow aura; Shadow Form choice host; Wreathed in Shadows "
                "target restriction; Pall of Despair Battle-shock and healing; Shadow Lord "
                "hit-reroll aura; Supreme Commander mustering."
            ),
            catalog_blockers="Representative height remains unreviewed outside this report.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Daemon Prince of Chaos",
            datasheet_id="000001149",
            source_basis="PDF pages 116-117; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D3, The Shadow of Chaos, Daemonic Lord Lone "
                "Operative condition, Prince of Darkness Stealth aura, and Daemonic "
                "Allegiance keyword choice semantics are structured paths."
            ),
            semantics_needed=(
                "Daemonic Allegiance characteristic modifiers; Unholy Vigour once-per-battle "
                "invulnerable-save timing; aura runtime hosts."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Daemon Prince of Chaos with Wings",
            datasheet_id="000002758",
            source_basis="PDF pages 118-119; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D3, The Shadow of Chaos, Malefic Destruction "
                "Attacks modifier, and Harbinger of Death named weapon ability choice "
                "semantics are structured paths. Daemonic Allegiance keyword choice is "
                "represented as a mustering option."
            ),
            semantics_needed=(
                "Daemonic Allegiance characteristic modifiers; Fight-start host for Malefic "
                "Destruction and Harbinger of Death."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
        DatasheetGroupReviewRow(
            datasheet="Soul Grinder",
            datasheet_id="000001151",
            source_basis="PDF pages 114-115; supersedes Wahapedia.",
            ir_coverage="Unsupported IR",
            supported_semantics=(
                "Deep Strike, Deadly Demise D3, The Shadow of Chaos, and the "
                "warpsword-to-warpclaw replacement option are known structured paths. "
                "Daemonic Allegiance keyword and additional equipment choice is "
                "represented as a mustering option."
            ),
            semantics_needed=(
                "Scuttling Walker movement through friendly Monster/Vehicle models and terrain."
            ),
            catalog_blockers="No known catalog blocker.",
        ),
    )


def _datasheet_label(row: DatasheetSupportRow) -> str:
    return f"{_markdown_text(row.datasheet_name)} (`{_markdown_text(row.datasheet_id)}`)"


def _ability_detail_label(row: AbilityCoverageRow) -> str:
    return f"{_markdown_text(row.ability_name)} (`{_markdown_text(row.ability_id)}`)"


def _faction_interaction_cell(row: DatasheetSupportRow) -> str:
    if row.faction_interaction_status == DATASHEET_SUPPORT_NONE:
        return DATASHEET_SUPPORT_NONE
    if not row.detachment_ids:
        return row.faction_interaction_status
    return (
        f"{row.faction_interaction_status}; supported detachments "
        f"{len(row.supported_detachment_ids)}/{len(row.detachment_ids)} "
        f"({_inline_code_list(row.supported_detachment_ids)})"
    )


def _faction_detachment_rule_coverage_rows_markdown(
    rows: tuple[Phase17ECoverageRow, ...],
) -> list[str]:
    lines = [
        "",
        "## Detachment Rule Coverage Rows",
        "",
        (
            "These rows expose the underlying Phase17E source coverage and handler IDs. "
            "Use the support table above for semantic support status."
        ),
        "",
        "| Detachment | Rule | Coverage row | Support status | Handler / block | Source IDs |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(_required_text(row.detachment_name)),
                    _markdown_text(row.rule_name),
                    f"`{_markdown_text(row.descriptor_id)}`",
                    _coverage_status_text(row),
                    _handler_or_block_text(row),
                    _inline_code_list(row.source_ids),
                )
            )
            + " |"
        )
    return lines


def _faction_pdf_record(faction_id: str) -> faction_coverage_2026_27.Phase17EFactionPdfRecord:
    for record in faction_coverage_2026_27.faction_pdf_records():
        if record.faction_id == faction_id:
            return record
    raise ValueError("Faction support Markdown row is missing PDF source coverage.")


def _faction_exact_rule_rows_markdown(
    title: str,
    rows: tuple[Phase17ECoverageRow, ...],
) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        (
            "| Detachment | Rule | Rule ID | Timing | Category | Support status | "
            "Handler / block | Runtime consumers | Source IDs |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not rows:
        lines.append("| No exact source rows generated yet |  |  |  |  |  |  |  |  |")
        return lines
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(_required_text(row.detachment_name)),
                    _markdown_text(row.rule_name),
                    f"`{_markdown_text(_required_text(row.rule_id))}`",
                    _markdown_text(_required_text(row.timing_descriptor)),
                    _markdown_text(_required_text(row.rule_category)),
                    _coverage_status_text(row),
                    _handler_or_block_text(row),
                    _inline_code_list(row.runtime_consumer_ids),
                    _inline_code_list(row.source_ids),
                )
            )
            + " |"
        )
    return lines


def _coverage_rows_for_kind(
    rows: tuple[Phase17ECoverageRow, ...],
    kind: Phase17ECoverageKind,
) -> tuple[Phase17ECoverageRow, ...]:
    return tuple(sorted((row for row in rows if row.coverage_kind is kind), key=_coverage_sort_key))


def _coverage_sort_key(row: Phase17ECoverageRow) -> tuple[str, str, str]:
    return (
        "" if row.detachment_id is None else row.detachment_id,
        row.rule_name.lower(),
        row.descriptor_id,
    )


def _coverage_status_text(row: Phase17ECoverageRow) -> str:
    if row.runtime_support_status is None:
        return f"`{row.status.value}`"
    return f"`{row.status.value}` / `{row.runtime_support_status.value}`"


def _handler_or_block_text(row: Phase17ECoverageRow) -> str:
    if row.handler_id is not None:
        return f"`{_markdown_text(row.handler_id)}`"
    if row.unsupported_reason is not None:
        return f"`{row.unsupported_reason.value}`"
    return ""


def _required_text(value: str | None) -> str:
    if value is None:
        raise ValueError("Faction support Markdown row is missing required text.")
    return value


def _runtime_hook_inventory_markdown(
    category_rows: list[AbilityCoverageCategoryRowPayload],
) -> list[str]:
    lines = [
        "",
        "## Runtime Hook Inventory",
        "",
        (
            "This bottom inventory lists the hook, modifier, effect, handler, and runtime "
            "consumer IDs currently surfaced by generated category rows, Core Stratagem "
            "records, or registered runtime-content contributions. Pregame mustering/list "
            "construction enforcement is reported in the Mustering / List Construction "
            "Support section instead of this phase/query inventory."
        ),
        "",
        "| Hook / consumer | Abilities / rules |",
        "| --- | --- |",
    ]
    for row in _runtime_hook_inventory_rows(category_rows):
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{_markdown_text(row.hook_id)}`",
                    _hook_ability_or_rule_labels_text(row.ability_or_rule_labels),
                )
            )
            + " |"
        )
    return lines


def _runtime_hook_inventory_rows(
    category_rows: list[AbilityCoverageCategoryRowPayload],
) -> tuple[RuntimeHookInventoryRow, ...]:
    inventory: dict[str, set[str]] = {}
    for hook_id in catalog_rule_ir_registered_hook_ids():
        inventory.setdefault(hook_id, set())
    for row in category_rows:
        for consumer_id in row["runtime_consumer_ids"]:
            for label in _category_runtime_consumer_labels(
                row,
                consumer_id=consumer_id,
            ):
                _add_inventory_entry(inventory, hook_id=consumer_id, label=label)

    labels_by_id = _runtime_content_labels_by_id()
    for record in eleventh_edition_core_stratagem_catalog_records():
        _add_inventory_entry(
            inventory,
            hook_id=record.definition.handler_id,
            label=record.definition.name,
        )
    for contribution in _runtime_content_contributions():
        _add_runtime_content_inventory_entries(
            inventory=inventory,
            contribution=contribution,
            labels_by_id=labels_by_id,
        )

    return tuple(
        RuntimeHookInventoryRow(
            hook_id=hook_id,
            ability_or_rule_labels=tuple(sorted(labels)),
        )
        for hook_id, labels in sorted(inventory.items())
    )


def _category_runtime_consumer_labels(
    row: AbilityCoverageCategoryRowPayload,
    *,
    consumer_id: str,
) -> tuple[str, ...]:
    label_override = _RUNTIME_ID_LABEL_OVERRIDES.get(consumer_id)
    if label_override is not None:
        return (label_override,)
    ability_names = tuple(row["ability_names"])
    if ability_names:
        return ability_names
    return (row["category_name"],)


def _runtime_content_labels_by_id() -> dict[str, set[str]]:
    labels_by_id: dict[str, set[str]] = {}
    for contribution in _runtime_content_contributions():
        for ability_record in contribution.ability_records:
            _add_inventory_entry(
                labels_by_id,
                hook_id=ability_record.definition.handler_id,
                label=ability_record.definition.name,
            )
        for stratagem_record in contribution.stratagem_records:
            _add_inventory_entry(
                labels_by_id,
                hook_id=stratagem_record.definition.handler_id,
                label=stratagem_record.definition.name,
            )
        for binding in contribution.enhancement_effect_bindings:
            _add_inventory_entry(
                labels_by_id,
                hook_id=binding.effect_id,
                label=_enhancement_label(binding.enhancement_id),
            )
    return labels_by_id


def _runtime_content_contributions() -> tuple[RuntimeContentContribution, ...]:
    module_paths = tuple(
        sorted(
            {
                row.module_path
                for row in generated_runtime_content_rows()
                if row.support_status is RuntimeContentSupportStatus.SUPPORTED
                and row.module_path is not None
            }
        )
    )
    contributions: list[RuntimeContentContribution] = []
    for module_path in module_paths:
        module = importlib.import_module(module_path)
        factory_candidate = module.__dict__.get("runtime_contribution")
        if not callable(factory_candidate):
            raise TypeError("Runtime content module must expose runtime_contribution().")
        factory = cast(Callable[[], RuntimeContentContribution], factory_candidate)
        contribution = factory()
        if type(contribution) is not RuntimeContentContribution:
            raise TypeError("Runtime content module returned invalid RuntimeContentContribution.")
        if contribution.contribution_id == DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID:
            contribution = contribution.with_contribution_id(module.__name__)
        contributions.append(contribution)
    return tuple(contributions)


def _add_runtime_content_inventory_entries(
    *,
    inventory: dict[str, set[str]],
    contribution: RuntimeContentContribution,
    labels_by_id: Mapping[str, set[str]],
) -> None:
    for ability_record in contribution.ability_records:
        _add_inventory_entry(
            inventory,
            hook_id=ability_record.definition.handler_id,
            label=ability_record.definition.name,
        )
    for stratagem_record in contribution.stratagem_records:
        _add_inventory_entry(
            inventory,
            hook_id=stratagem_record.definition.handler_id,
            label=stratagem_record.definition.name,
        )
    _add_handler_bindings(
        inventory,
        (binding.handler_id for binding in contribution.ability_handler_bindings),
        labels_by_id,
    )
    _add_handler_bindings(
        inventory,
        (binding.handler_id for binding in contribution.stratagem_handler_bindings),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.subscription_id, binding.source_rule_id)
            for binding in contribution.event_subscriptions
        ),
        labels_by_id,
    )
    _add_handler_bindings(
        inventory,
        (binding.handler_id for binding in contribution.event_handler_bindings),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.battle_formation_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.battle_round_start_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        ((binding.hook_id, binding.source_id) for binding in contribution.turn_end_hook_bindings),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.command_phase_start_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.fight_phase_end_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.unit_destroyed_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.battle_shock_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.advance_eligibility_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.advance_move_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        ((binding.hook_id, binding.source_id) for binding in contribution.fall_back_hook_bindings),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.movement_end_surge_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.unit_move_completed_mortal_wound_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.mortal_wound_feel_no_pain_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.charge_declaration_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.shooting_target_restriction_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.charge_target_restriction_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.shooting_unit_selected_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.shooting_unit_selected_grant_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.shooting_end_surge_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.effect_id, binding.source_id)
            for binding in contribution.enhancement_effect_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.fight_activation_ability_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.fight_unit_selected_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.fight_unit_selected_grant_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.attack_sequence_completed_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.phase_end_objective_control_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.hook_id, binding.source_id)
            for binding in contribution.stratagem_cost_choice_hook_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.stratagem_cost_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.unit_characteristic_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.hit_roll_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.wound_roll_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.save_option_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.movement_budget_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.objective_control_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.charge_roll_modifier_bindings
        ),
        labels_by_id,
    )
    _add_hook_bindings(
        inventory,
        (
            (binding.modifier_id, binding.source_id)
            for binding in contribution.weapon_profile_modifier_bindings
        ),
        labels_by_id,
    )


def _add_hook_bindings(
    inventory: dict[str, set[str]],
    bindings: Iterable[tuple[str, str]],
    labels_by_id: Mapping[str, set[str]],
) -> None:
    for binding_id, source_id in bindings:
        for label in _runtime_binding_labels(
            identifier=binding_id,
            source_id=source_id,
            labels_by_id=labels_by_id,
        ):
            _add_inventory_entry(inventory, hook_id=binding_id, label=label)


def _add_handler_bindings(
    inventory: dict[str, set[str]],
    handler_ids: Iterable[str],
    labels_by_id: Mapping[str, set[str]],
) -> None:
    for handler_id in handler_ids:
        label_override = _RUNTIME_ID_LABEL_OVERRIDES.get(handler_id)
        labels_for_handler: set[str] | None
        if label_override is not None:
            labels_for_handler = {label_override}
        else:
            labels_for_handler = labels_by_id.get(handler_id)
            if labels_for_handler is None:
                labels_for_handler = {_label_from_identifier(handler_id)}
        for label in labels_for_handler:
            _add_inventory_entry(inventory, hook_id=handler_id, label=label)


def _runtime_binding_labels(
    *,
    identifier: str,
    source_id: str,
    labels_by_id: Mapping[str, set[str]],
) -> tuple[str, ...]:
    label_override = _RUNTIME_ID_LABEL_OVERRIDES.get(identifier)
    if label_override is not None:
        return (label_override,)
    labels = labels_by_id.get(identifier)
    if labels is not None:
        return tuple(sorted(labels))
    source_label = _RUNTIME_SOURCE_LABEL_OVERRIDES.get(source_id)
    if source_label is not None:
        return (source_label,)
    return (_label_from_identifier(identifier),)


def _add_inventory_entry(
    inventory: dict[str, set[str]],
    *,
    hook_id: str,
    label: str,
) -> None:
    if _is_mustering_report_id(hook_id):
        return
    inventory.setdefault(hook_id, set()).add(label)


def _is_mustering_report_id(identifier: str) -> bool:
    return identifier.startswith("army-mustering:")


def _hook_ability_or_rule_labels_text(labels: tuple[str, ...]) -> str:
    if not labels:
        return "No current generated rows"
    return "<br>".join(_markdown_text(label) for label in labels)


def _enhancement_label(enhancement_id: str) -> str:
    label = _RUNTIME_ID_LABEL_OVERRIDES.get(enhancement_id)
    if label is not None:
        return label
    return _label_from_identifier(enhancement_id)


def _label_from_identifier(identifier: str) -> str:
    token = identifier.split(":")[-1].replace("_", "-")
    words = tuple(word for word in token.split("-") if word)
    if not words:
        return identifier
    return " ".join(_title_word(word) for word in words)


def _title_word(word: str) -> str:
    upper_tokens = {
        "ap": "AP",
        "cp": "CP",
        "d3": "D3",
        "d6": "D6",
        "ir": "IR",
        "oc": "OC",
    }
    return upper_tokens.get(word, word.capitalize())


def _structured_support_sections_markdown() -> list[str]:
    lines = [
        "",
        "## Structured Support Sections",
        "",
        (
            "These sections organize the support matrix by the rule families adapters and "
            "engine owners usually reason about. `Full` means the current CORE V2 scope has "
            "engine/runtime support, documentation or contract coverage when adapter-visible, "
            "and focused tests. `Partial` means at least one known rule edge, generated "
            "source-row path, or runtime host remains incomplete. `None` means the source row "
            "and generated scaffold exist, but no semantic engine rule path is present."
        ),
    ]
    lines.extend(
        _support_section_markdown(
            "Core Keyword Abilities",
            (
                "Core keyword ability rows are source-backed through either semantic runtime "
                "handlers or phase-owned hosts that consume structured datasheet descriptors and "
                "canonical keywords."
            ),
            (
                SupportSectionRow(
                    "Deep Strike",
                    "Reserve declaration and placement hosts",
                    "Adapter contract, source-row registry, and architecture",
                    "Focused reserve, deployment, source-row, and replay tests",
                    "Full",
                    (
                        "The source row resolves through a phase-host handler while Reserve "
                        "declaration and setup placement consume the shared Deep Strike "
                        "datasheet/keyword classifier."
                    ),
                ),
                SupportSectionRow(
                    "Infiltrators",
                    "Deployment placement validation and enemy-distance gates",
                    "Adapter contract, source-row registry, and generated matrix",
                    "Focused keyword and descriptor-backed deployment tests",
                    "Full",
                    (
                        "Allows deployment outside the owning zone only when every attached "
                        "component has Infiltrators, then enforces more-than-8-inch enemy unit "
                        "and enemy deployment-zone distance gates."
                    ),
                ),
                SupportSectionRow(
                    "Scouts X",
                    (
                        "Pre-battle Scout Move, Scout reserve setup, and Dedicated "
                        "Transport Scout Move hosts"
                    ),
                    "Adapter contract and decision catalog",
                    "Focused pre-battle, setup smoke, and enhancement-grant tests",
                    "Full",
                    (
                        "Consumes structured Scouts descriptors for distance selection; "
                        "a SCOUTS keyword without a descriptor fails fast."
                    ),
                ),
                SupportSectionRow(
                    "Firing Deck X",
                    "Transport Shooting declaration and attack-pool source binding",
                    "Adapter contract, source-row registry, and generated matrix",
                    "Focused Transport resolver, Shooting declaration, and replay tests",
                    "Full",
                    (
                        "Consumes structured Firing Deck values, exposes eligible embarked "
                        "non-One-Shot ranged weapons, binds each contribution to source "
                        "unit/model evidence, and marks selected embarked units ineligible to "
                        "shoot."
                    ),
                ),
                SupportSectionRow(
                    "Leader",
                    "Muster-time attached-unit formation as leader components",
                    "Architecture, source-row registry, and adapter deployment contract",
                    "Focused mustering, attached rules-unit, deployment, and fight tests",
                    "Full",
                    (
                        "Consumes structured Leader declarations during army mustering, forms "
                        "first-class attached rules units, and preserves leader model ownership "
                        "through group-aware battlefield operations."
                    ),
                ),
                SupportSectionRow(
                    "Support",
                    "Muster-time attached-unit formation as support components",
                    "Architecture, source-row registry, and adapter deployment contract",
                    "Focused mustering, attached rules-unit, deployment, and transport tests",
                    "Full",
                    (
                        "Consumes structured Support declarations separately from Leader, "
                        "requires support units to attach legally, and preserves support model "
                        "ownership through attached rules-unit APIs."
                    ),
                ),
                SupportSectionRow(
                    "Deadly Demise X",
                    (
                        "Static source registration plus mandatory pre-removal "
                        "destruction-reaction resolver"
                    ),
                    "Architecture, source-row registry, and generated matrix",
                    "Focused descriptor, Shooting damage, FNP continuation, and replay tests",
                    "Full",
                    (
                        "Consumes structured Deadly Demise descriptors for fixed, D3, and D6 "
                        "mortal wounds; source-backed model registrations feed the existing "
                        "mandatory destruction-reaction path."
                    ),
                ),
                SupportSectionRow(
                    "Stealth",
                    "Shooting target candidate hit-roll penalty",
                    "Architecture, source-row registry, and generated matrix",
                    "Focused descriptor-backed Shooting target tests",
                    "Full",
                    (
                        "Consumes keyword or descriptor-backed Stealth on target rules units "
                        "and carries the -1 hit-roll modifier through accepted ranged pools."
                    ),
                ),
                SupportSectionRow(
                    "Lone Operative",
                    "Shooting target range gate",
                    "Adapter contract, source-row registry, and generated matrix",
                    "Focused keyword and descriptor-backed Shooting target tests",
                    "Full",
                    (
                        "Blocks target selection outside 12 inches using the shared Shooting "
                        "candidate legality path and records the Lone Operative rule ID."
                    ),
                ),
                SupportSectionRow(
                    "Feel No Pain X+",
                    "Static per-model source registration plus shared lost-wound resolver",
                    "Adapter contract, source-row registry, and generated matrix",
                    "Focused descriptor, damage, mortal-wound, and replay tests",
                    "Full",
                    (
                        "Consumes structured Feel No Pain threshold descriptors and feeds the "
                        "existing normal damage, mortal-wound, Hazardous, Explosives, and "
                        "Deadly Demise FNP continuation paths."
                    ),
                ),
                SupportSectionRow(
                    "Fights First",
                    "Static fight-order source registration plus Fight phase ordering bands",
                    "Adapter contract, source-row registry, and generated matrix",
                    "Focused descriptor-backed Fight-order tests",
                    "Full",
                    (
                        "Registers battle-long Fights First sources from structured descriptors "
                        "or canonical keywords and consumes them through the shared activation "
                        "ordering state."
                    ),
                ),
            ),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Core Rules",
            (
                "Core rule behavior is source-backed through canonical keywords, ruleset "
                "descriptors, or named runtime consumers, then consumed by Movement, Shooting "
                "target selection, attack resolution, and Stratagem effect hosts."
            ),
            (
                SupportSectionRow(
                    "TOWERING keyword",
                    "Terrain visibility exception and Plunging Fire eligibility",
                    "Ruleset descriptor, keyword lexicon, and generated matrix",
                    "Focused visibility/cover and Shooting declaration tests",
                    "Full",
                    (
                        "Consumes canonical TOWERING keywords in terrain line-of-sight "
                        "exception policy and lets TOWERING attackers claim Plunging Fire "
                        "against ground-level targets within 12 inches."
                    ),
                ),
                SupportSectionRow(
                    "TITANIC keyword",
                    ("Desperate Escape overflight exemption and Core Stratagem eligibility gates"),
                    "Source row, adapter contract, and generated matrix",
                    "Focused Fall Back/Desperate Escape and Fire Overwatch tests",
                    "Full",
                    (
                        "The source ability row registers TITANIC as a canonical keyword; "
                        "Movement treats FLY or TITANIC units as overflight-exempt for "
                        "Desperate Escape checks, and Fire Overwatch rejects TITANIC units "
                        "before CP spend."
                    ),
                ),
                SupportSectionRow(
                    "Hidden and Detection Range",
                    "Terrain visibility policy plus Shooting target detection gate",
                    "Architecture and adapter contract",
                    "Ruleset descriptor, Shooting target, and Path of the Outcast tests",
                    "Full",
                    (
                        "The 11th Edition descriptor enables Hidden with a 15 inch detection "
                        "range, terrain-area and keyword requirements, and hidden-status loss "
                        "after ranged attacks; detection modifiers are consumed from "
                        "engine-owned persisting effects."
                    ),
                ),
                SupportSectionRow(
                    "Plunging Fire",
                    "Shooting target evidence plus attack-sequence Ballistic Skill modifier",
                    "Ruleset descriptor, architecture, and generated matrix",
                    "Focused Shooting declaration, save, and fail-fast validation tests",
                    "Full",
                    (
                        "Adds `core-rules:plunging-fire` to accepted targeting evidence from "
                        "eligible terrain-floor or TOWERING range gates, then improves the "
                        "attack pool's Ballistic Skill in the shared attack sequence."
                    ),
                ),
                SupportSectionRow(
                    "Gone to Ground",
                    "Automatic Hidden detection penalty for Dense/Solid terrain",
                    "Ruleset descriptor, GameState history, adapter contract, and generated matrix",
                    "Focused Shooting target and ranged attack history tests",
                    "Full",
                    (
                        "Hidden models within Dense terrain features, represented by "
                        "`LineOfSightPolicy.DENSE_COVER`, subtract 3 inches from effective "
                        "Detection Range when they are not fully visible because of intervening "
                        "Solid terrain and their unit has not made ranged attacks in the current "
                        "or previous player turn. Accepted shooting declarations record "
                        "`RangedAttackHistoryRecord`; no player choice, Stratagem use, CP spend, "
                        "or retired Go to Ground Stratagem is involved."
                    ),
                ),
            ),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Wargear Keyword Abilities",
            (
                "Weapon and wargear keyword abilities are normalized into `WeaponKeyword` values "
                "or structured `AbilityDescriptor` records. Runtime code consumes these "
                "structured fields and does not parse raw rule text."
            ),
            _wargear_keyword_support_rows(),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Core Stratagems",
            (
                "Core Stratagem rows are source-backed and route through the shared "
                "Stratagem contract."
            ),
            (
                SupportSectionRow(
                    "Command Re-roll, Insane Bravery, New Orders, Rapid Ingress",
                    "Named handlers",
                    "Adapter contract and architecture",
                    "Focused decision/CP/replay tests",
                    "Full",
                    "Core Command/Movement Stratagem slice.",
                ),
                SupportSectionRow(
                    "Fire Overwatch, Smokescreen, Explosives",
                    "Named handlers",
                    "Adapter contract and architecture",
                    "Focused Shooting and reaction-window tests",
                    "Full",
                    "Shooting-coupled Core Stratagem slice.",
                ),
                SupportSectionRow(
                    "Heroic Intervention, Counteroffensive, Crushing Impact, Epic Challenge",
                    "Named handlers",
                    "Adapter contract and architecture",
                    "Focused Charge/Fight Stratagem tests",
                    "Full",
                    "Charge/Fight Core Stratagem slice.",
                ),
            ),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Faction Army Rules",
            "Faction army rules are grouped by faction-specific runtime consumers.",
            (
                SupportSectionRow(
                    "Chaos Daemons - The Shadow of Chaos",
                    "Named army-rule handler",
                    "Architecture and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    "Current generated rows are `engine_consumed`.",
                ),
                SupportSectionRow(
                    "Adepta Sororitas - Acts of Faith",
                    "Battle-round-start and unit-destroyed Miracle dice hooks",
                    "Source coverage, generated matrix, and runtime inventory",
                    "Focused Miracle dice gain, spend, serialization, and fail-fast tests",
                    "Full",
                    (
                        "Implements the updated Miracle dice gaining section: one D6 at "
                        "the start of each battle round and one D6 each time a friendly "
                        "ADEPTA SORORITAS unit is destroyed, persisted in the Miracle "
                        "dice pool with fixed non-rerollable values."
                    ),
                ),
                SupportSectionRow(
                    "Adeptus Custodes - Martial Ka'tah",
                    "Selected-to-fight stance grants plus melee weapon-profile modifier",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    (
                        "Focused grant, decision, runtime-modifier, source coverage, "
                        "and fail-fast tests"
                    ),
                    "Full",
                    (
                        "Implements Dacatarai and Rendax finite selected-to-fight options; "
                        "the accepted stance persists as a Fight phase effect and grants "
                        "[SUSTAINED HITS 1] or [LETHAL HITS] to melee weapon profiles."
                    ),
                ),
                SupportSectionRow(
                    "Adeptus Mechanicus - Doctrina Imperatives",
                    (
                        "Battle-round-start Imperative selection plus weapon-profile and "
                        "Protector melee hit-roll modifiers"
                    ),
                    "Adapter contract, source coverage, generated matrix, and runtime inventory",
                    (
                        "Focused battle-round selection, invalid-submission, attached-unit, "
                        "aura, and runtime-modifier tests"
                    ),
                    "Full",
                    (
                        "Implements Protector and Conqueror selections until the end of the "
                        "battle round for units with Doctrina Imperatives, including "
                        "ranged Heavy/Assault grants, BS/WS improvements, Protector melee "
                        "Hit-roll penalties, and Conqueror AP improvement with Battleline "
                        "or friendly Battleline proximity gates."
                    ),
                ),
                SupportSectionRow(
                    "Chaos Space Marines - Dark Pacts",
                    "Named army-rule handler",
                    "Adapter contract and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    (
                        "Uses selected-to-shoot and selected-to-fight grant decisions for "
                        "Lethal Hits or Sustained Hits 1, including out-of-phase shooting, then "
                        "resolves the post-attack Leadership test, failed-test D3 mortal wounds, "
                        "and any mortal-wound Feel No Pain continuation through engine hooks."
                    ),
                ),
                SupportSectionRow(
                    "Death Guard - Nurgle's Gift",
                    "Named army-rule handler",
                    "Architecture and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    "Includes contagion modifiers for supported characteristics and rolls.",
                ),
                SupportSectionRow(
                    "World Eaters - Blessings of Khorne",
                    "Named army-rule handler",
                    "Architecture and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    "Includes battle-round selection and supported blessing effects.",
                ),
                SupportSectionRow(
                    "Orks - Waaagh!",
                    "Named army-rule handler",
                    "Adapter contract, decision catalog, architecture, and generated matrix",
                    (
                        "Focused command-phase, advance eligibility, weapon-profile, "
                        "save-option, and validation tests"
                    ),
                    "Full",
                    (
                        "Implements optional once-per-battle Command phase Waaagh! call, "
                        "active until the start of the next own Command phase, including "
                        "Advance-then-Charge eligibility, melee Strength/Attacks modifiers, "
                        "and a 5+ invulnerable save."
                    ),
                ),
                SupportSectionRow(
                    "Black Templars - Templar Vows",
                    "Named army-rule handler",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    "Focused vow selection, modifier, charge, Fall Back, and objective tests",
                    "Full",
                    (
                        "Implements battle-round Templar Vow selection, Abhor the Witch "
                        "Precision and PSYKER charge requirements, Accept Any Challenge "
                        "wound modifiers, Suffer Not the Unclean charge-after-Fall-Back, "
                        "and Uphold the Honour sticky objective control."
                    ),
                ),
                SupportSectionRow(
                    "Chaos Knights - Harbingers of Dread",
                    "Named army-rule handler",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    (
                        "Focused Dread selection, forced Battle-shock, mortal-wound, "
                        "runtime-modifier, source ID, and fail-fast tests"
                    ),
                    "Full",
                    (
                        "Implements battle-round Dread selections and 2D6 rolls, Deathly "
                        "Terror/Despair Leadership auras, Dismay forced below-starting "
                        "Battle-shock tests, Delirium D3 mortal wounds, Doom wound modifiers, "
                        "and the Darkness Stealth hit modifier. Delirium mortal-wound "
                        "Feel No Pain continuation is explicitly deferred and emits a typed "
                        "unsupported event without applying wounds."
                    ),
                ),
                SupportSectionRow(
                    "Imperial Knights - Code Chivalric",
                    "Named army-rule handler plus setup/timing/runtime modifier hosts",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    (
                        "Focused oath selection, fulfilment, modifier, reroll, "
                        "and source coverage tests"
                    ),
                    "Full",
                    (
                        "Implements source-backed Code Chivalric oath selection, the updated "
                        "Reap a Great Tally battle-round check, Honoured CP rewards, Martial "
                        "Valour rerolls, Eager movement and charge modifiers, and Legacy OC "
                        "and Leadership modifiers."
                    ),
                ),
                SupportSectionRow(
                    "Imperial Knights - Bondsman",
                    "Named Command phase handler plus model-scoped persisting-effect host",
                    "Adapter contract, decision catalog, generated matrix, and runtime inventory",
                    "Focused command-phase selection, range, Armiger, drift, and expiry tests",
                    "Full",
                    (
                        "Implements the Bondsman command-phase source/target selection rule: "
                        "each eligible Bondsman-tagged Imperial Knights model selects one "
                        "friendly ARMIGER model within 12 inches that is not already affected; "
                        "the selected named Bondsman ability is recorded as a model-scoped "
                        "persisting effect until the start of that player's next turn."
                    ),
                ),
                SupportSectionRow(
                    "Imperial Knights - Freeblades",
                    "Shared mustering/list-validation host",
                    "Generated matrix and mustering tests",
                    "Focused mustering tests",
                    "Full",
                    (
                        "Allows Imperium armies to include either one TITANIC Imperial "
                        "Knights model or up to three ARMIGER models; allied Freeblades "
                        "cannot be Warlords or receive Enhancements."
                    ),
                ),
                SupportSectionRow(
                    "Astra Militarum - Voice of Command",
                    "Named army-rule handler",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    "Focused command-phase, Battle-shock, and runtime-modifier tests",
                    "Full",
                    (
                        "Implements Command phase Order selection, order replacement, "
                        "Battle-shock order cleanup, and all six Order modifiers through "
                        "shared decision and modifier hosts."
                    ),
                ),
                SupportSectionRow(
                    "Emperor's Children - Thrill Seekers",
                    "Named army-rule handler",
                    "Architecture and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    "Includes movement, charge, and shooting target restrictions.",
                ),
                SupportSectionRow(
                    "Grey Knights - Gate of Infinity",
                    "Named army-rule handler",
                    "Adapter contract, decision catalog, architecture, and generated matrix",
                    "Focused turn-end, reserves, cap, and attached-rules-unit tests",
                    "Full",
                    (
                        "Implements opponent Fight phase Gate of Infinity selections, "
                        "battle-size caps, complete choices, required next-Movement "
                        "Strategic Reserves arrival, and attached rules-unit component "
                        "validation."
                    ),
                ),
                SupportSectionRow(
                    "Space Marines - Oath of Moment and Space Marine Chapters",
                    "Named army-rule handler plus shared mustering/list-validation host",
                    (
                        "README, adapter contract, decision catalog, architecture, "
                        "and generated matrix"
                    ),
                    "Focused command-phase, reroll, wound-modifier, and mustering tests",
                    "Full",
                    (
                        "Implements Command phase Oath target selection, target-scoped "
                        "Hit-roll rerolls, Codex Space Marines Detachment Wound-roll "
                        "bonus gating, and Black Templars, Space Wolves, and Deathwatch "
                        "roster restrictions."
                    ),
                ),
                SupportSectionRow(
                    "T'au Empire - For the Greater Good",
                    "Shooting-phase-start faction-rule hook plus weapon-profile modifier",
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    "Focused shooting-start, invalid-submission, and runtime-modifier tests",
                    "Full",
                    (
                        "Implements Observer/Spotted selections, target-centric Guided "
                        "Ballistic Skill improvement, and Markerlight [IGNORES COVER]. "
                        "Selected-shooter-specific Guided identity is deferred if future "
                        "rules require it."
                    ),
                ),
                SupportSectionRow(
                    "Thousand Sons - Cabal of Sorcerers",
                    (
                        "Shooting-phase-start faction-rule hook plus weapon-profile and "
                        "mortal-wound Feel No Pain hooks"
                    ),
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    "Focused ritual, invalid-submission, movement, modifier, and wound tests",
                    "Full",
                    (
                        "Implements Shooting-start ritual selections, Psychic tests with "
                        "optional Channel the Warp perils, Destiny's Ruin hit rerolls, "
                        "Temporal Surge movement proposals and charge lockout, Doombolt "
                        "mortal wounds, and Twist of Fate AP modifiers."
                    ),
                ),
                SupportSectionRow(
                    "Genestealer Cults - Cult Ambush",
                    (
                        "Named army-rule handler plus faction-resource ledger, "
                        "destroyed-unit resurgence, marker placement, and marker ingress hosts"
                    ),
                    "Adapter contract, decision catalog, source coverage, and generated matrix",
                    (
                        "Focused setup, destroyed-unit, marker placement/removal, reserves, "
                        "ingress, invalid-submission, replay-safe record, and routing tests"
                    ),
                    "Full",
                    (
                        "Implements battle-size Resurgence points, optional destroyed-unit "
                        "replacement spending, Cult Ambush marker placement and removal, "
                        "marker-based ingress including battle round 1, Strategic Reserves "
                        "arrival, Rapid Ingress exclusion, and third-round auto-destroy "
                        "exemption."
                    ),
                ),
                SupportSectionRow(
                    "Tyranids - Shadow in the Warp and Synapse",
                    (
                        "Command-phase-start faction-rule hook plus Battle-shock and "
                        "weapon-profile modifiers"
                    ),
                    (
                        "README, adapter contract, decision catalog, source coverage, "
                        "and generated matrix"
                    ),
                    "Focused command-phase, Battle-shock, and runtime-modifier tests",
                    "Full",
                    (
                        "Implements once-per-battle Shadow in the Warp in either "
                        "player's Command phase, forced enemy Battle-shock tests, "
                        "Synapse 3D6 Battle-shock tests, Synapse-range Shadow "
                        "penalties, and melee Strength modifiers."
                    ),
                ),
                SupportSectionRow(
                    "Necrons - Reanimation Protocols",
                    "Named army-rule handler plus shared Healing Wounds resolver",
                    (
                        "README, adapter contract, decision catalog, architecture, "
                        "and generated matrix"
                    ),
                    "Focused command-phase healing, revival, and validation tests",
                    "Full",
                    (
                        "Implements Command phase rules-unit activation, source-backed "
                        "D3 healing, destroyed-model revival, attached rules-unit "
                        "identity, stale rules-unit rejection, and owning-player "
                        "healing selections."
                    ),
                ),
                SupportSectionRow(
                    "Leagues of Votann - Prioritised Efficiency",
                    "Named army-rule handler plus faction-resource ledger",
                    "README, generated matrix, and source coverage",
                    "Focused command-phase, scoring, mode, and runtime-modifier tests",
                    "Full",
                    (
                        "Implements deterministic Yield Point gains from Command phase "
                        "objective control, Hostile Acquisition and Fortify Takeover modes, "
                        "and mode-scoped Hit/Wound modifiers."
                    ),
                ),
                SupportSectionRow(
                    "Drukhari - Power from Pain",
                    "Named army-rule handler plus faction-resource ledger",
                    "README, faction integration note, adapter contract, and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    (
                        "Implements Pain token gain at own Command phase start, enemy "
                        "unit destruction, and enemy Battle-shock failure, plus optional "
                        "Lithe Agility empowerment for Advance and Charge rerolls and "
                        "Hatred Eternal selected-to-shoot/selected-to-fight empowerment "
                        "for attack hit rerolls."
                    ),
                ),
                SupportSectionRow(
                    "Drukhari - Corsairs and Travelling Players",
                    "Shared mustering/list-validation host",
                    "README, faction integration note, and generated matrix",
                    "Focused mustering tests",
                    "Full",
                    (
                        "Allows non-DRUKHARI HARLEQUINS and ANHRATHE allies under "
                        "Incursion, Strike Force, and Onslaught caps; forbids allied "
                        "Warlords and Enhancements. No player-facing decision or phase "
                        "runtime hook is introduced."
                    ),
                ),
            ),
        )
    )
    lines.extend(_mustering_support_markdown(mustering_support_rows()))
    lines.extend(_faction_index_section_markdown())
    lines.extend(
        _support_section_markdown(
            "Datasheet Abilities",
            "Datasheet abilities remain separate from core, wargear, faction, and detachment rows.",
            (
                SupportSectionRow(
                    "Known datasheet ability text",
                    "Descriptors or generated IR where available",
                    "Generated matrix and coverage reports",
                    "Focused tests where implemented",
                    "Partial",
                    "Current unparsed rows remain under Unknown Abilities until classified.",
                ),
            ),
        )
    )
    return lines


def _faction_index_section_markdown() -> list[str]:
    coverage_rows = faction_coverage_2026_27.coverage_rows()
    lines = [
        "",
        "## Factions",
        "",
        (
            "Faction-specific Detachment Rule, Enhancement, and Stratagem rows are split "
            "into generated per-faction files under `docs/factions/`. The exact rows expose "
            "their coverage row IDs, source IDs, timing/category metadata, and current "
            "support status. Supported detachment counts report semantic engine support, "
            "not just source-row intake."
        ),
        "",
        (
            "| Faction | Detachments | Supported detachment rules | Exact Enhancements | "
            "Exact Stratagems | Engine-consumed rows | File |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for faction_row in faction_detachments_2026_27.faction_rows():
        faction_rows = tuple(
            row for row in coverage_rows if row.faction_id == faction_row.faction_id
        )
        detachment_count = _coverage_kind_count(
            faction_rows,
            Phase17ECoverageKind.DETACHMENT_RULE,
        )
        enhancement_count = _coverage_kind_count(
            faction_rows,
            Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
        )
        stratagem_count = _coverage_kind_count(
            faction_rows,
            Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        )
        supported_detachment_count = sum(
            1
            for row in _detachment_rule_support_rows_for_faction(faction_row.faction_id)
            if _detachment_rule_is_supported(row)
        )
        engine_consumed_row_count = sum(
            1
            for row in faction_rows
            if row.coverage_kind in _FACTION_INDEX_ENGINE_CONSUMED_KINDS
            and _coverage_row_is_engine_consumed(row)
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(faction_row.name),
                    str(detachment_count),
                    str(supported_detachment_count),
                    str(enhancement_count),
                    str(stratagem_count),
                    str(engine_consumed_row_count),
                    f"[{_markdown_text(faction_row.faction_id)}](factions/{faction_row.faction_id}.md)",
                )
            )
            + " |"
        )
    return lines


def _coverage_kind_count(
    rows: tuple[Phase17ECoverageRow, ...],
    kind: Phase17ECoverageKind,
) -> int:
    return sum(1 for row in rows if row.coverage_kind is kind)


def _mustering_support_markdown(rows: tuple[MusteringSupportRow, ...]) -> list[str]:
    if type(rows) is not tuple:
        raise ValueError("Mustering support Markdown requires a tuple.")
    for row in rows:
        if type(row) is not MusteringSupportRow:
            raise ValueError("Mustering support Markdown requires MusteringSupportRow values.")
    lines = [
        "",
        "## Mustering / List Construction Support",
        "",
        (
            "This generated section reports pregame army-list rules enforced by "
            "`army_mustering.py`, `list_validation.py`, and army creation helpers. These "
            "rows are separate from the Runtime Hook Inventory, which is limited to "
            "phase/query hooks, modifiers, effects, handlers, and runtime consumers."
        ),
        "",
        (
            "| Rule | Rule ID | Source ID | Faction / allowed base factions | "
            "Enforcement surface | Support stage | Enforcement ID | Tests / evidence | Notes |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row.display_name),
                    f"`{_markdown_text(row.rule_id)}`",
                    f"`{_markdown_text(row.source_id)}`",
                    _mustering_scope_text(row),
                    f"`{_markdown_text(row.enforcement_surface)}`",
                    f"`{_markdown_text(row.support_stage)}`",
                    f"`{_markdown_text(row.enforcement_id)}`",
                    _markdown_text(row.tests_evidence),
                    _markdown_text(row.notes),
                )
            )
            + " |"
        )
    return lines


def _mustering_scope_text(row: MusteringSupportRow) -> str:
    scope_parts: list[str] = []
    if row.faction_id is not None:
        scope_parts.append(f"faction {_inline_code_list((row.faction_id,))}")
    if row.allowed_base_faction_ids:
        scope_parts.append(f"allowed base {_inline_code_list(row.allowed_base_faction_ids)}")
    return "; ".join(scope_parts)


def _support_section_markdown(
    title: str,
    description: str,
    rows: tuple[SupportSectionRow, ...],
) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        description,
        "",
        "| Subject | Engine support | Documentation | Tests | Overall | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row.subject),
                    _markdown_text(row.engine),
                    _markdown_text(row.documentation),
                    _markdown_text(row.tests),
                    _markdown_text(row.overall),
                    _markdown_text(row.notes),
                )
            )
            + " |"
        )
    return lines


def _detachment_rules_section_markdown() -> list[str]:
    lines = [
        "",
        "## Detachment Rules",
        "",
        (
            "Detachment rule support is source-row complete, but semantic engine support is "
            "only marked where the faction detachment module contributes gameplay hooks. "
            "Rows are grouped by faction through the `Faction` column."
        ),
        "",
        "| Faction | Detachment | Engine support | Documentation | Tests | Overall | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in _detachment_rule_support_rows():
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row.faction),
                    _markdown_text(row.detachment),
                    _markdown_text(row.engine),
                    _markdown_text(row.documentation),
                    _markdown_text(row.tests),
                    _markdown_text(row.overall),
                    _markdown_text(row.notes),
                )
            )
            + " |"
        )
    return lines


def _detachment_rule_support_rows() -> tuple[DetachmentRuleSupportRow, ...]:
    faction_names = {row.faction_id: row.name for row in faction_detachments_2026_27.faction_rows()}
    rows: list[DetachmentRuleSupportRow] = []
    for source_row in faction_detachments_2026_27.detachment_rows():
        override = _DETACHMENT_RULE_SUPPORT_OVERRIDES.get(
            (source_row.faction_id, source_row.detachment_id)
        )
        if override is None:
            rows.append(
                DetachmentRuleSupportRow(
                    faction_id=source_row.faction_id,
                    detachment_id=source_row.detachment_id,
                    faction=faction_names[source_row.faction_id],
                    detachment=source_row.name,
                    engine="Generated scaffold only",
                    documentation="Source row and generated module scaffold",
                    tests="Source-row/catalog coverage",
                    overall="None",
                    notes="No semantic detachment-rule hook is implemented.",
                )
            )
        else:
            rows.append(
                DetachmentRuleSupportRow(
                    faction_id=source_row.faction_id,
                    detachment_id=source_row.detachment_id,
                    faction=faction_names[source_row.faction_id],
                    detachment=source_row.name,
                    engine=override.engine,
                    documentation=override.documentation,
                    tests=override.tests,
                    overall=override.overall,
                    notes=override.notes,
                )
            )
    return tuple(rows)


def _detachment_rule_support_rows_for_faction(
    faction_id: str,
) -> tuple[DetachmentRuleSupportRow, ...]:
    return tuple(
        sorted(
            (row for row in _detachment_rule_support_rows() if row.faction_id == faction_id),
            key=lambda row: (row.detachment.lower(), row.detachment_id),
        )
    )


def _detachment_rule_is_supported(row: DetachmentRuleSupportRow) -> bool:
    return row.overall != "None"


def _wargear_keyword_support_rows() -> tuple[SupportSectionRow, ...]:
    return (
        _full_wargear_row(
            "[ANTI-X Y+] / [ANTI-NON-X Y+]",
            "Critical Wound thresholds from structured descriptors",
            "Includes slash-separated keyword groups and missing-keyword gates.",
        ),
        _full_wargear_row(
            "[ASSAULT]",
            "Advance shooting eligibility and Assault-only declaration filtering",
            "Consumes movement-state evidence.",
        ),
        _full_wargear_row(
            "[BLAST]",
            "Attack-count bonus from target model count",
            "Uses shared attack-count resolution.",
        ),
        _full_wargear_row(
            "[CLEAVE X]",
            "Structured attack-generation helper",
            "Preserves source descriptor data.",
        ),
        _full_wargear_row(
            "[CLOSE-QUARTERS] / [PISTOL]",
            "Engagement-aware ranged declaration and targeting rules",
            "`[PISTOL]` is treated as an alias.",
        ),
        _full_wargear_row(
            "[DEVASTATING WOUNDS]",
            "Critical Wound to mortal-wound damage routing",
            "Runs through grouped damage and mortal-wound hosts.",
        ),
        _full_wargear_row(
            "[EXTRA ATTACKS]",
            "Additional melee declaration path",
            "Does not replace the model's primary melee weapon.",
        ),
        _full_wargear_row(
            "[HAZARDOUS]",
            "Post-attack Hazardous roll and mortal-wound routing",
            "Uses shared damage-allocation/FNP path.",
        ),
        _full_wargear_row(
            "[HEAVY]",
            "Stationary-gated Hit-roll modifier",
            (
                "Includes own-Shooting-phase, out-of-phase denial, engagement, movement, "
                "Advance/Fall Back, and setup-this-turn gates."
            ),
        ),
        _full_wargear_row(
            "[HUNTER X]",
            "Target eligibility gate",
            "Matches at least one listed target keyword.",
        ),
        _full_wargear_row(
            "[IGNORES COVER]",
            "Removes Benefit of Cover for the attack",
            "Applies across terrain, Stealth, Smokescreen, Indirect Fire, and other cover sources.",
        ),
        _full_wargear_row(
            "[INDIRECT FIRE]",
            "Indirect targeting restrictions and modifiers",
            "Includes no-visible-target and no-reroll restrictions.",
        ),
        _full_wargear_row(
            "[LANCE]",
            "Charge-conditioned Wound-roll modifier",
            "Consumes charge-state evidence.",
        ),
        _full_wargear_row(
            "[LETHAL HITS]",
            "Critical Hit optional auto-wound decision",
            "Routes through the shared attack sequence.",
        ),
        _full_wargear_row(
            "[MELTA X]",
            "Range-conditioned Damage bonus",
            "Uses measured target range evidence.",
        ),
        _full_wargear_row(
            "[ONE SHOT]",
            "Battle-scoped weapon-use records in Shooting and Fight",
            "Returned destroyed models cannot reuse an already selected weapon.",
        ),
        _full_wargear_row(
            "[PRECISION]",
            "Attacker allocation-priority decision",
            "Uses visible eligible Character allocation groups.",
        ),
        _full_wargear_row(
            "[PSYCHIC]",
            "Psychic attack classification and modifier-ignore decision",
            "Psychic-only downstream rules consume `is_psychic_attack`.",
        ),
        _full_wargear_row(
            "[RAPID FIRE X]",
            "Range-conditioned attack-count bonus",
            "Uses measured target range evidence.",
        ),
        _full_wargear_row(
            "[SUSTAINED HITS X]",
            "Generated hits from Critical Hits",
            "Generated-hit wound contexts remain deterministic.",
        ),
        _full_wargear_row(
            "[TORRENT]",
            "Automatic Hit resolution",
            "Bypasses Hit rolls while preserving later attack sequence steps.",
        ),
        _full_wargear_row(
            "[TWIN-LINKED]",
            "Wound-roll reroll permission",
            "Consumes shared reroll semantics.",
        ),
    )


def _full_wargear_row(subject: str, engine: str, notes: str) -> SupportSectionRow:
    return SupportSectionRow(
        subject=subject,
        engine=engine,
        documentation="Architecture plus adapter contract/catalog when player-facing",
        tests="Focused unit and lifecycle tests",
        overall="Full",
        notes=notes,
    )


def _inline_code_list(values: Iterable[str]) -> str:
    values = tuple(values)
    if not values:
        return "None"
    return ", ".join(f"`{_markdown_text(value)}`" for value in values)


def _markdown_line_list(values: Iterable[str]) -> str:
    values = tuple(values)
    if not values:
        return "None"
    return "<br>".join(_markdown_text(value) for value in values)


def _source_kind_counts_text(values: dict[str, int]) -> str:
    if not values:
        return "None"
    return ", ".join(
        f"`{_markdown_text(source_kind)}`: {count}" for source_kind, count in sorted(values.items())
    )


def _ability_datasheet_pairs_text(
    values: list[AbilityCoverageAbilityDatasheetPairPayload],
) -> str:
    if not values:
        return "None"
    return "<br>".join(
        f"{_markdown_text(value['ability_name'])} ({_markdown_text(value['datasheet_name'])})"
        for value in values
    )


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|")


def _bridge_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="wahapedia-" + "1" + "0" + "e-bridge",
        version="phase17k-generated",
    )


def _catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="chaos-daemons-bridge-catalog",
        version="phase17k-generated",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17k",
        source_date=date(2026, 6, 10),
    )


if __name__ == "__main__":
    main()
