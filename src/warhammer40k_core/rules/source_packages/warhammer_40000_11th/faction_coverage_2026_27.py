from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_source_promotion_2026_07,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)

EDITION_ID = "warhammer_40000_11th"
SOURCE_EDITION = "11th"
SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-07"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Phase 17E July Faction Coverage"
SOURCE_VERSION = "2026-07-22"
SOURCE_DATE = "2026-07-22"
UPSTREAM_IDENTITY = faction_source_promotion_2026_07.SOURCE_PACKAGE_ID
IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17e-faction-coverage-v3"


class Phase17EFactionCoverageError(ValueError):
    """Raised when Phase 17E faction coverage data violates CORE V2 invariants."""


class Phase17ECoverageKind(StrEnum):
    FACTION_ARMY_RULE = "faction_army_rule"
    DETACHMENT_RULE = "detachment_rule"
    DETACHMENT_ENHANCEMENT = "detachment_enhancement"
    DETACHMENT_STRATAGEM = "detachment_stratagem"
    DETACHMENT_ENHANCEMENT_DESCRIPTORS = "detachment_enhancement_descriptors"
    DETACHMENT_STRATAGEM_DESCRIPTORS = "detachment_stratagem_descriptors"
    DATASHEET_INTAKE = "datasheet_intake"


class Phase17ECoverageStatus(StrEnum):
    IMPLEMENTED = "implemented"
    GENERIC_SUPPORTED = "generic_supported"
    NAMED_HANDLER_REQUIRED = "named_handler_required"
    UNSUPPORTED = "unsupported"


# fmt: off
class Phase17EUnsupportedReason(StrEnum):
    DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS = "datasheet_intake_requires_generated_source_rows"  # noqa: E501

APPROVED_UNSUPPORTED_REASONS = frozenset({Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS})  # noqa: E501
_EXACT_SUBRULE_COVERAGE_KINDS = frozenset({Phase17ECoverageKind.DETACHMENT_ENHANCEMENT, Phase17ECoverageKind.DETACHMENT_STRATAGEM})  # noqa: E501
# fmt: on
DAEMONIC_INCURSION_WARP_RIFTS_RUNTIME_CONSUMER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts"
)
BLOOD_LEGION_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall",
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted",
)
DAEMONIC_INCURSION_RUNTIME_CONSUMER_IDS = (DAEMONIC_INCURSION_WARP_RIFTS_RUNTIME_CONSUMER_ID,)
SHADOW_LEGION_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "murderers-cowl:advance-eligibility",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "shadows-caress:snap-target-restriction",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:shooting:lethal_hits",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:shooting:sustained_hits_1",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:fight:lethal_hits",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:fight:sustained_hits_1",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:attack-sequence-completed",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:mortal-wound-fnp",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:penumbral-puppetry:hit-roll",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:gloam-rot:wound-roll",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:weapon-profile",
)
CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMER_IDS_BY_DETACHMENT_ID = {
    "blood-legion": BLOOD_LEGION_RUNTIME_CONSUMER_IDS,
    "daemonic-incursion": DAEMONIC_INCURSION_RUNTIME_CONSUMER_IDS,
}
AELDARI_BATTLE_FOCUS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:aeldari:army_rule:fade_back",
    "warhammer_40000_11th:aeldari:army_rule:flitting_shadows",
    "warhammer_40000_11th:aeldari:army_rule:opportunity_seized",
    "warhammer_40000_11th:aeldari:army_rule:star_engines",
    "warhammer_40000_11th:aeldari:army_rule:sudden_strike",
    "warhammer_40000_11th:aeldari:army_rule:swift_as_the_wind",
)
ADEPTA_SORORITAS_ACTS_OF_FAITH_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:adepta_sororitas:army_rule:acts_of_faith:battle-round-start",
    "warhammer_40000_11th:adepta_sororitas:army_rule:acts_of_faith:unit-destroyed",
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs:battle-round-start",
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs:bloody-rose:weapon-profile",
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs:fiery-heart:advance",
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs:fiery-heart:charge",
    "warhammer_40000_11th:adepta_sororitas:triumph_of_saint_katherine:relics_of_the_matriarchs:fiery-heart:movement",
)
ADEPTUS_CUSTODES_MARTIAL_KATAH_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah:dacatarai",
    "warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah:rendax",
    "warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah:weapon-profile",
)
ADEPTUS_MECHANICUS_DOCTRINA_IMPERATIVES_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:adeptus_mechanicus:army_rule:doctrina_imperatives",
    "warhammer_40000_11th:adeptus_mechanicus:army_rule:doctrina_imperatives:"
    "protector:melee-hit-roll",
    "warhammer_40000_11th:adeptus_mechanicus:army_rule:doctrina_imperatives:weapon-profile",
)
ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:battle-shock",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:movement",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:objective-control",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:save-option",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:unit-characteristic",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:weapon-profile",
)
CHAOS_DAEMONS_SHADOW_OF_CHAOS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",
)
CHAOS_KNIGHTS_HARBINGERS_OF_DREAD_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:battle-shock",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:darkness:hit-roll",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:doom:wound-roll",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:leadership",
)
CHAOS_SPACE_MARINES_DARK_PACTS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:attack_sequence_completed",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:lethal_hits",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:sustained_hits_1",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:mortal_wound_feel_no_pain",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:lethal_hits",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:sustained_hits_1",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:weapon_profile_modifier",
)
DEATH_GUARD_NURGLES_GIFT_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:armour-save-option",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:leadership",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:melee-hit-roll",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:movement-budget",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:objective-control",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:toughness",
)
DRUKHARI_POWER_FROM_PAIN_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:battle-shock-failed",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:command-phase-start",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:enemy-unit-destroyed",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-fight",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-shooting",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-advance",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-charge",
)
EMPERORS_CHILDREN_THRILL_SEEKERS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:advance-eligibility",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:charge-target-restriction",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:fall-back-eligibility",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:shooting-target-restriction",
)
GREY_KNIGHTS_GATE_OF_INFINITY_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:grey_knights:army_rule:gate_of_infinity",
)
GENESTEALER_CULTS_CULT_AMBUSH_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:genestealer_cults:army_rule:cult_ambush",
    "warhammer_40000_11th:genestealer_cults:army_rule:cult_ambush:initial_resurgence",
    "warhammer_40000_11th:genestealer_cults:army_rule:cult_ambush:marker_ingress",
    "warhammer_40000_11th:genestealer_cults:army_rule:cult_ambush:unit_destroyed",
)
IMPERIAL_KNIGHTS_CODE_CHIVALRIC_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:eager:charge-roll",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:eager:movement-budget",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:enemy-unit-destroyed",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:end-battle-round",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:end-turn",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:legacy:leadership",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:legacy:objective-control",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:martial-valour:fight",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:martial-valour:shooting",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:oath-selection",
)
LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:command-phase-start",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:hit-roll",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:wound-roll",
)
NECRONS_REANIMATION_PROTOCOLS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:necrons:army_rule:reanimation_protocols",
)
ORKS_WAAAGH_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:orks:army_rule:waaagh",
    "warhammer_40000_11th:orks:army_rule:waaagh:advance-eligibility",
    "warhammer_40000_11th:orks:army_rule:waaagh:invulnerable-save",
    "warhammer_40000_11th:orks:army_rule:waaagh:weapon-profile",
)
TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good",
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good:weapon-profile",
)
THOUSAND_SONS_CABAL_OF_SORCERERS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers",
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers:mortal-wound-feel-no-pain",
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers:weapon-profile",
)
TYRANIDS_SHADOW_IN_THE_WARP_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp",
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp:battle-shock",
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp:synapse:weapon-profile",
)
BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:black_templars:army_rule:templar_vows",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:charge-declaration",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:charge-targets",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:melee-precision",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:accept_any_challenge:wound-roll",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:suffer_not_the_unclean:fall-back",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:"
    "uphold_the_honour:objective-control",
)
SPACE_MARINES_OATH_OF_MOMENT_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:space_marines:army_rule:oath_of_moment",
    "warhammer_40000_11th:space_marines:army_rule:oath_of_moment:wound-roll",
)
WORLD_EATERS_BLESSINGS_OF_KHORNE_RUNTIME_CONSUMER_IDS = (
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:rage_fuelled_invigoration",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:total_carnage",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:"
    "unbridled_bloodlust:charge_roll",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:weapon-profile-keywords",
)
FACTION_ARMY_RULE_NAMES_BY_FACTION_ID = {
    "adepta-sororitas": "Acts of Faith",
    "adeptus-custodes": "Martial Ka'tah",
    "adeptus-mechanicus": "Doctrina Imperatives",
    "aeldari": "Battle Focus",
    "astra-militarum": "Voice of Command",
    "black-templars": "Templar Vows",
    "chaos-daemons": "The Shadow of Chaos",
    "chaos-knights": "Harbingers of Dread",
    "chaos-space-marines": "Dark Pacts",
    "death-guard": "Nurgle's Gift",
    "drukhari": "Power from Pain",
    "emperors-children": "Thrill Seekers",
    "genestealer-cults": "Cult Ambush",
    "grey-knights": "Gate of Infinity",
    "imperial-knights": "Code Chivalric",
    "leagues-of-votann": "Prioritised Efficiency",
    "necrons": "Reanimation Protocols",
    "orks": "Waaagh!",
    "space-marines": "Oath of Moment",
    "tau-empire": "For the Greater Good",
    "thousand-sons": "Cabal of Sorcerers",
    "tyranids": "Shadow in the Warp / Synapse",
    "world-eaters": "Blessings of Khorne",
}
FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID = {
    "adepta-sororitas": ADEPTA_SORORITAS_ACTS_OF_FAITH_RUNTIME_CONSUMER_IDS,
    "adeptus-custodes": ADEPTUS_CUSTODES_MARTIAL_KATAH_RUNTIME_CONSUMER_IDS,
    "adeptus-mechanicus": ADEPTUS_MECHANICUS_DOCTRINA_IMPERATIVES_RUNTIME_CONSUMER_IDS,
    "aeldari": AELDARI_BATTLE_FOCUS_RUNTIME_CONSUMER_IDS,
    "astra-militarum": ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMER_IDS,
    "black-templars": BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMER_IDS,
    "chaos-daemons": CHAOS_DAEMONS_SHADOW_OF_CHAOS_RUNTIME_CONSUMER_IDS,
    "chaos-knights": CHAOS_KNIGHTS_HARBINGERS_OF_DREAD_RUNTIME_CONSUMER_IDS,
    "chaos-space-marines": CHAOS_SPACE_MARINES_DARK_PACTS_RUNTIME_CONSUMER_IDS,
    "death-guard": DEATH_GUARD_NURGLES_GIFT_RUNTIME_CONSUMER_IDS,
    "drukhari": DRUKHARI_POWER_FROM_PAIN_RUNTIME_CONSUMER_IDS,
    "emperors-children": EMPERORS_CHILDREN_THRILL_SEEKERS_RUNTIME_CONSUMER_IDS,
    "genestealer-cults": GENESTEALER_CULTS_CULT_AMBUSH_RUNTIME_CONSUMER_IDS,
    "grey-knights": GREY_KNIGHTS_GATE_OF_INFINITY_RUNTIME_CONSUMER_IDS,
    "imperial-knights": IMPERIAL_KNIGHTS_CODE_CHIVALRIC_RUNTIME_CONSUMER_IDS,
    "leagues-of-votann": LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMER_IDS,
    "necrons": NECRONS_REANIMATION_PROTOCOLS_RUNTIME_CONSUMER_IDS,
    "orks": ORKS_WAAAGH_RUNTIME_CONSUMER_IDS,
    "space-marines": SPACE_MARINES_OATH_OF_MOMENT_RUNTIME_CONSUMER_IDS,
    "tau-empire": TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMER_IDS,
    "thousand-sons": THOUSAND_SONS_CABAL_OF_SORCERERS_RUNTIME_CONSUMER_IDS,
    "tyranids": TYRANIDS_SHADOW_IN_THE_WARP_RUNTIME_CONSUMER_IDS,
    "world-eaters": WORLD_EATERS_BLESSINGS_OF_KHORNE_RUNTIME_CONSUMER_IDS,
}


class Phase17EFactionPdfRecordPayload(TypedDict):
    faction_id: str
    faction_name: str
    package_id: str
    title: str
    source_date: str
    pdf_filename: str
    sha256: str
    bytes: int
    source_id: str


class Phase17ECoverageRowPayload(TypedDict):
    descriptor_id: str
    coverage_kind: str
    status: str
    faction_id: str
    faction_name: str
    source_ids: list[str]
    source_pdf_package_id: str
    rule_name: str
    detachment_id: str | None
    detachment_name: str | None
    force_disposition_id: str | None
    detachment_point_cost: int | None
    is_new_for_eleventh: bool | None
    rule_id: str | None
    timing_descriptor: str | None
    rule_category: str | None
    runtime_support_status: str | None
    runtime_consumer_ids: list[str]
    handler_id: str | None
    rule_ir_hash: str | None
    unsupported_reason: str | None


class Phase17ECoveragePackagePayload(TypedDict):
    edition_id: str
    source_edition: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    upstream_identity: str
    imported_at_schema_version: str
    source_payload_checksum_sha256: str
    pdf_records: list[Phase17EFactionPdfRecordPayload]
    coverage_rows: list[Phase17ECoverageRowPayload]
    status_counts: dict[str, int]
    unsupported_count: int
    unapproved_unsupported_count: int


@dataclass(frozen=True, slots=True)
class Phase17EFactionPdfRecord:
    faction_id: str
    faction_name: str
    package_id: str
    title: str
    source_date: str
    pdf_filename: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(
            self,
            "faction_name",
            _validate_non_empty_text("faction_name", self.faction_name),
        )
        object.__setattr__(self, "package_id", _validate_identifier("package_id", self.package_id))
        object.__setattr__(self, "title", _validate_non_empty_text("title", self.title))
        object.__setattr__(
            self,
            "source_date",
            _validate_non_empty_text("source_date", self.source_date),
        )
        object.__setattr__(
            self,
            "pdf_filename",
            _validate_pdf_filename(self.pdf_filename),
        )
        object.__setattr__(self, "sha256", _validate_sha256("sha256", self.sha256))
        if type(self.bytes) is not int:
            raise Phase17EFactionCoverageError("Phase17E PDF bytes must be an integer.")
        if self.bytes <= 0:
            raise Phase17EFactionCoverageError("Phase17E PDF bytes must be positive.")

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:source-pdf:{self.faction_id}"

    def to_payload(self) -> Phase17EFactionPdfRecordPayload:
        return {
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "package_id": self.package_id,
            "title": self.title,
            "source_date": self.source_date,
            "pdf_filename": self.pdf_filename,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: Phase17EFactionPdfRecordPayload) -> Self:
        return cls(
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            package_id=payload["package_id"],
            title=payload["title"],
            source_date=payload["source_date"],
            pdf_filename=payload["pdf_filename"],
            sha256=payload["sha256"],
            bytes=payload["bytes"],
        )


@dataclass(frozen=True, slots=True)
class Phase17ECoverageRow:
    descriptor_id: str
    coverage_kind: Phase17ECoverageKind
    status: Phase17ECoverageStatus
    faction_id: str
    faction_name: str
    source_ids: tuple[str, ...]
    source_pdf_package_id: str
    rule_name: str
    detachment_id: str | None = None
    detachment_name: str | None = None
    force_disposition_id: str | None = None
    detachment_point_cost: int | None = None
    is_new_for_eleventh: bool | None = None
    rule_id: str | None = None
    timing_descriptor: str | None = None
    rule_category: str | None = None
    runtime_support_status: faction_subrules_2026_27.SourceSubruleRuntimeStatus | None = None
    runtime_consumer_ids: tuple[str, ...] = ()
    handler_id: str | None = None
    rule_ir_hash: str | None = None
    unsupported_reason: Phase17EUnsupportedReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "descriptor_id",
            _validate_identifier("descriptor_id", self.descriptor_id),
        )
        object.__setattr__(self, "coverage_kind", _coverage_kind_from_token(self.coverage_kind))
        status = _coverage_status_from_token(self.status)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(
            self,
            "faction_name",
            _validate_non_empty_text("faction_name", self.faction_name),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )
        object.__setattr__(
            self,
            "source_pdf_package_id",
            _validate_identifier("source_pdf_package_id", self.source_pdf_package_id),
        )
        object.__setattr__(self, "rule_name", _validate_non_empty_text("rule_name", self.rule_name))
        if self.detachment_id is not None:
            object.__setattr__(
                self,
                "detachment_id",
                _validate_identifier("detachment_id", self.detachment_id),
            )
        if self.detachment_name is not None:
            object.__setattr__(
                self,
                "detachment_name",
                _validate_non_empty_text("detachment_name", self.detachment_name),
            )
        if self.force_disposition_id is not None:
            object.__setattr__(
                self,
                "force_disposition_id",
                _validate_identifier("force_disposition_id", self.force_disposition_id),
            )
        if self.detachment_point_cost is not None:
            _validate_detachment_point_cost(self.detachment_point_cost)
        if self.is_new_for_eleventh is not None and type(self.is_new_for_eleventh) is not bool:
            raise Phase17EFactionCoverageError("is_new_for_eleventh must be a boolean.")
        if self.rule_id is not None:
            object.__setattr__(self, "rule_id", _validate_identifier("rule_id", self.rule_id))
        if self.timing_descriptor is not None:
            object.__setattr__(
                self,
                "timing_descriptor",
                _validate_non_empty_text("timing_descriptor", self.timing_descriptor),
            )
        if self.rule_category is not None:
            object.__setattr__(
                self,
                "rule_category",
                _validate_non_empty_text("rule_category", self.rule_category),
            )
        runtime_support_status = self.runtime_support_status
        if runtime_support_status is not None:
            runtime_support_status = _runtime_support_status_from_token(runtime_support_status)
            object.__setattr__(self, "runtime_support_status", runtime_support_status)
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_identifier_tuple(
                "runtime_consumer_ids",
                self.runtime_consumer_ids,
                allow_empty=True,
            ),
        )
        if self.handler_id is not None:
            object.__setattr__(
                self,
                "handler_id",
                _validate_identifier("handler_id", self.handler_id),
            )
        if self.rule_ir_hash is not None:
            object.__setattr__(
                self, "rule_ir_hash", _validate_sha256("rule_ir_hash", self.rule_ir_hash)
            )
            status = Phase17ECoverageStatus.GENERIC_SUPPORTED
            object.__setattr__(self, "status", status)
            object.__setattr__(self, "handler_id", None)
        unsupported_reason = self.unsupported_reason
        if unsupported_reason is not None:
            unsupported_reason = _unsupported_reason_from_token(unsupported_reason)
            object.__setattr__(self, "unsupported_reason", unsupported_reason)

        if status is Phase17ECoverageStatus.UNSUPPORTED and unsupported_reason is None:
            raise Phase17EFactionCoverageError("Unsupported coverage rows require a reason.")
        if status is not Phase17ECoverageStatus.UNSUPPORTED and unsupported_reason is not None:
            raise Phase17EFactionCoverageError(
                "Only unsupported coverage rows can include unsupported_reason."
            )
        if status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED and self.handler_id is None:
            raise Phase17EFactionCoverageError(
                "Named-handler-required coverage rows require handler_id."
            )
        if status is Phase17ECoverageStatus.GENERIC_SUPPORTED and self.rule_ir_hash is None:
            raise Phase17EFactionCoverageError(
                "Generic-supported coverage rows require rule_ir_hash."
            )
        if status is Phase17ECoverageStatus.IMPLEMENTED and self.handler_id is None:
            raise Phase17EFactionCoverageError("Implemented coverage rows require handler_id.")
        if self.coverage_kind in _EXACT_SUBRULE_COVERAGE_KINDS:
            if (
                self.rule_id is None
                or self.timing_descriptor is None
                or self.rule_category is None
                or runtime_support_status is None
            ):
                raise Phase17EFactionCoverageError(
                    "Exact subrule coverage rows require rule metadata."
                )
        elif self.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE:
            if (
                self.rule_id is not None
                or self.timing_descriptor is not None
                or self.rule_category is not None
            ):
                raise Phase17EFactionCoverageError(
                    "Faction army rule coverage rows cannot include exact subrule metadata."
                )
            if runtime_support_status is not None and not self.runtime_consumer_ids:
                raise Phase17EFactionCoverageError(
                    "Faction army rule runtime support requires runtime consumers."
                )
            if self.runtime_consumer_ids and runtime_support_status is None:
                raise Phase17EFactionCoverageError(
                    "Faction army rule runtime consumers require runtime support status."
                )
        elif self.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE:
            if (
                self.rule_id is not None
                or self.timing_descriptor is not None
                or self.rule_category is not None
            ):
                raise Phase17EFactionCoverageError(
                    "Detachment rule coverage rows cannot include exact subrule metadata."
                )
            if runtime_support_status is not None and not self.runtime_consumer_ids:
                raise Phase17EFactionCoverageError(
                    "Detachment rule runtime support requires runtime consumers."
                )
            if self.runtime_consumer_ids and runtime_support_status is None:
                raise Phase17EFactionCoverageError(
                    "Detachment rule runtime consumers require runtime support status."
                )
        elif (
            self.rule_id is not None
            or self.timing_descriptor is not None
            or self.rule_category is not None
            or runtime_support_status is not None
            or self.runtime_consumer_ids
        ):
            raise Phase17EFactionCoverageError(
                "Only exact subrule coverage rows can include rule metadata."
            )

    @property
    def is_unsupported(self) -> bool:
        return self.status is Phase17ECoverageStatus.UNSUPPORTED

    @property
    def is_approved_unsupported(self) -> bool:
        return (
            self.status is Phase17ECoverageStatus.UNSUPPORTED
            and self.unsupported_reason in APPROVED_UNSUPPORTED_REASONS
        )

    def to_payload(self) -> Phase17ECoverageRowPayload:
        return {
            "descriptor_id": self.descriptor_id,
            "coverage_kind": self.coverage_kind.value,
            "status": self.status.value,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "source_ids": list(self.source_ids),
            "source_pdf_package_id": self.source_pdf_package_id,
            "rule_name": self.rule_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "force_disposition_id": self.force_disposition_id,
            "detachment_point_cost": self.detachment_point_cost,
            "is_new_for_eleventh": self.is_new_for_eleventh,
            "rule_id": self.rule_id,
            "timing_descriptor": self.timing_descriptor,
            "rule_category": self.rule_category,
            "runtime_support_status": (
                None if self.runtime_support_status is None else self.runtime_support_status.value
            ),
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "handler_id": self.handler_id,
            "rule_ir_hash": self.rule_ir_hash,
            "unsupported_reason": (
                None if self.unsupported_reason is None else self.unsupported_reason.value
            ),
        }

    @classmethod
    def from_payload(cls, payload: Phase17ECoverageRowPayload) -> Self:
        unsupported_reason = payload["unsupported_reason"]
        runtime_support_status = payload["runtime_support_status"]
        return cls(
            descriptor_id=payload["descriptor_id"],
            coverage_kind=_coverage_kind_from_token(payload["coverage_kind"]),
            status=_coverage_status_from_token(payload["status"]),
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            source_ids=tuple(payload["source_ids"]),
            source_pdf_package_id=payload["source_pdf_package_id"],
            rule_name=payload["rule_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            force_disposition_id=payload["force_disposition_id"],
            detachment_point_cost=payload["detachment_point_cost"],
            is_new_for_eleventh=payload["is_new_for_eleventh"],
            rule_id=payload["rule_id"],
            timing_descriptor=payload["timing_descriptor"],
            rule_category=payload["rule_category"],
            runtime_support_status=(
                None
                if runtime_support_status is None
                else _runtime_support_status_from_token(runtime_support_status)
            ),
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
            handler_id=payload["handler_id"],
            rule_ir_hash=payload["rule_ir_hash"],
            unsupported_reason=(
                None
                if unsupported_reason is None
                else _unsupported_reason_from_token(unsupported_reason)
            ),
        )


@dataclass(frozen=True, slots=True)
class Phase17ECoveragePackage:
    pdf_records: tuple[Phase17EFactionPdfRecord, ...]
    coverage_rows: tuple[Phase17ECoverageRow, ...]

    def __post_init__(self) -> None:
        pdf_records = _validate_pdf_records(self.pdf_records)
        rows = _validate_coverage_rows(self.coverage_rows, pdf_records)
        object.__setattr__(self, "pdf_records", pdf_records)
        object.__setattr__(self, "coverage_rows", rows)

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Phase17ECoverageStatus}
        for row in self.coverage_rows:
            counts[row.status.value] += 1
        return counts

    def unsupported_rows(self) -> tuple[Phase17ECoverageRow, ...]:
        return tuple(row for row in self.coverage_rows if row.is_unsupported)

    def unapproved_unsupported_rows(self) -> tuple[Phase17ECoverageRow, ...]:
        return tuple(
            row
            for row in self.coverage_rows
            if row.is_unsupported and not row.is_approved_unsupported
        )

    def payload_without_checksum(self) -> Phase17ECoveragePackagePayload:
        unsupported_rows = self.unsupported_rows()
        unapproved_rows = self.unapproved_unsupported_rows()
        return {
            "edition_id": EDITION_ID,
            "source_edition": SOURCE_EDITION,
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_title": SOURCE_TITLE,
            "source_version": SOURCE_VERSION,
            "source_date": SOURCE_DATE,
            "upstream_identity": UPSTREAM_IDENTITY,
            "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
            "source_payload_checksum_sha256": "",
            "pdf_records": [record.to_payload() for record in self.pdf_records],
            "coverage_rows": [row.to_payload() for row in self.coverage_rows],
            "status_counts": self.status_counts(),
            "unsupported_count": len(unsupported_rows),
            "unapproved_unsupported_count": len(unapproved_rows),
        }

    def source_payload_checksum_sha256(self) -> str:
        return _sha256_payload(self.payload_without_checksum())

    def to_payload(self) -> Phase17ECoveragePackagePayload:
        payload = self.payload_without_checksum()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: Phase17ECoveragePackagePayload) -> Self:
        package = cls(
            pdf_records=tuple(
                Phase17EFactionPdfRecord.from_payload(record) for record in payload["pdf_records"]
            ),
            coverage_rows=tuple(
                Phase17ECoverageRow.from_payload(row) for row in payload["coverage_rows"]
            ),
        )
        if package.source_payload_checksum_sha256() != payload["source_payload_checksum_sha256"]:
            raise Phase17EFactionCoverageError("Phase17E coverage payload checksum is stale.")
        return package


def phase17e_coverage_package() -> Phase17ECoveragePackage:
    pdf_records = faction_pdf_records()
    rows: list[Phase17ECoverageRow] = []
    pdf_by_faction_id = {record.faction_id: record for record in pdf_records}
    detachment_rows_by_faction_id: dict[str, list[faction_detachments_2026_27.SourceDetachmentRow]]
    detachment_rows_by_faction_id = {}
    detachment_rows_by_owner_id: dict[
        tuple[str, str],
        faction_detachments_2026_27.SourceDetachmentRow,
    ]
    detachment_rows_by_owner_id = {}
    for detachment_row in faction_detachments_2026_27.detachment_rows():
        detachment_rows_by_faction_id.setdefault(detachment_row.faction_id, []).append(
            detachment_row
        )
        detachment_rows_by_owner_id[(detachment_row.faction_id, detachment_row.detachment_id)] = (
            detachment_row
        )

    for faction_row in faction_detachments_2026_27.faction_rows():
        pdf_record = _pdf_record_for_faction(pdf_by_faction_id, faction_row.faction_id)
        rows.append(_army_rule_row(faction_row=faction_row, pdf_record=pdf_record))
        rows.append(_datasheet_intake_row(faction_row=faction_row, pdf_record=pdf_record))
        for detachment_row in sorted(
            detachment_rows_by_faction_id.get(faction_row.faction_id, ()),
            key=lambda row: row.detachment_id,
        ):
            rows.extend(_detachment_rows(detachment_row=detachment_row, pdf_record=pdf_record))

    for enhancement_source_row in faction_subrules_2026_27.enhancement_rows():
        detachment_row = _detachment_row_for_subrule(
            detachment_rows_by_owner_id,
            faction_id=enhancement_source_row.faction_id,
            detachment_id=enhancement_source_row.detachment_id,
        )
        rows.append(
            _enhancement_row(
                source_row=enhancement_source_row,
                detachment_row=detachment_row,
                pdf_record=_pdf_record_for_faction(
                    pdf_by_faction_id,
                    enhancement_source_row.faction_id,
                ),
            )
        )
    for stratagem_source_row in faction_subrules_2026_27.stratagem_rows():
        detachment_row = _detachment_row_for_subrule(
            detachment_rows_by_owner_id,
            faction_id=stratagem_source_row.faction_id,
            detachment_id=stratagem_source_row.detachment_id,
        )
        rows.append(
            _stratagem_row(
                source_row=stratagem_source_row,
                detachment_row=detachment_row,
                pdf_record=_pdf_record_for_faction(
                    pdf_by_faction_id,
                    stratagem_source_row.faction_id,
                ),
            )
        )

    return Phase17ECoveragePackage(
        pdf_records=pdf_records,
        coverage_rows=_promote_current_successor_rows(tuple(rows)),
    )


def faction_pdf_records() -> tuple[Phase17EFactionPdfRecord, ...]:
    return _PDF_RECORDS


def coverage_rows() -> tuple[Phase17ECoverageRow, ...]:
    return phase17e_coverage_package().coverage_rows


def _promote_current_successor_rows(
    rows: tuple[Phase17ECoverageRow, ...],
) -> tuple[Phase17ECoverageRow, ...]:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        july_faction_packs_2026_07,
    )

    successor = july_faction_packs_2026_07.exalted_patron().execution_record()
    current_runtime_status = faction_subrules_2026_27.SourceSubruleRuntimeStatus.ENGINE_CONSUMED
    if successor.runtime_support_status != current_runtime_status.value:
        raise Phase17EFactionCoverageError("July Exalted Patron successor must be engine-consumed.")
    promoted: list[Phase17ECoverageRow] = []
    replacements = 0
    for row in rows:
        if row.descriptor_id != successor.coverage_descriptor_id:
            promoted.append(row)
            continue
        promoted.append(
            replace(
                row,
                status=Phase17ECoverageStatus.GENERIC_SUPPORTED,
                source_ids=successor.source_ids,
                source_pdf_package_id=successor.source_pdf_package_id,
                runtime_support_status=current_runtime_status,
                runtime_consumer_ids=successor.runtime_consumer_ids,
                handler_id=None,
                rule_ir_hash=successor.rule_ir_hash,
            )
        )
        replacements += 1
    if replacements != 1:
        raise Phase17EFactionCoverageError(
            "July coverage package requires exactly one Exalted Patron predecessor."
        )
    return tuple(promoted)


def source_package_identity_payload() -> dict[str, str]:
    package = phase17e_coverage_package()
    return {
        "edition_id": EDITION_ID,
        "source_edition": SOURCE_EDITION,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "upstream_identity": UPSTREAM_IDENTITY,
        "source_payload_checksum_sha256": package.source_payload_checksum_sha256(),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def _army_rule_row(
    *,
    faction_row: faction_detachments_2026_27.SourceFactionRow,
    pdf_record: Phase17EFactionPdfRecord,
) -> Phase17ECoverageRow:
    runtime_consumer_ids = _faction_army_rule_runtime_consumer_ids(faction_row)
    return Phase17ECoverageRow(
        descriptor_id=f"phase17e:{faction_row.faction_id}:army-rule",
        coverage_kind=Phase17ECoverageKind.FACTION_ARMY_RULE,
        status=(
            Phase17ECoverageStatus.IMPLEMENTED
            if runtime_consumer_ids
            else Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
        ),
        faction_id=faction_row.faction_id,
        faction_name=faction_row.name,
        source_ids=(faction_row.source_id, pdf_record.source_id),
        source_pdf_package_id=pdf_record.package_id,
        rule_name=_faction_army_rule_name(faction_row),
        runtime_support_status=(
            faction_subrules_2026_27.SourceSubruleRuntimeStatus.ENGINE_CONSUMED
            if runtime_consumer_ids
            else None
        ),
        runtime_consumer_ids=runtime_consumer_ids,
        handler_id=(
            runtime_consumer_ids[0]
            if runtime_consumer_ids
            else f"phase17e:faction:{faction_row.faction_id}:army-rule"
        ),
    )


def _faction_army_rule_name(
    faction_row: faction_detachments_2026_27.SourceFactionRow,
) -> str:
    return FACTION_ARMY_RULE_NAMES_BY_FACTION_ID.get(
        faction_row.faction_id,
        f"{faction_row.name} army rule",
    )


def _faction_army_rule_runtime_consumer_ids(
    faction_row: faction_detachments_2026_27.SourceFactionRow,
) -> tuple[str, ...]:
    return tuple(
        sorted(FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID.get(faction_row.faction_id, ()))
    )


def _datasheet_intake_row(
    *,
    faction_row: faction_detachments_2026_27.SourceFactionRow,
    pdf_record: Phase17EFactionPdfRecord,
) -> Phase17ECoverageRow:
    return Phase17ECoverageRow(
        descriptor_id=f"phase17e:{faction_row.faction_id}:datasheet-intake",
        coverage_kind=Phase17ECoverageKind.DATASHEET_INTAKE,
        status=Phase17ECoverageStatus.UNSUPPORTED,
        faction_id=faction_row.faction_id,
        faction_name=faction_row.name,
        source_ids=(faction_row.source_id, pdf_record.source_id),
        source_pdf_package_id=pdf_record.package_id,
        rule_name=f"{faction_row.name} datasheet intake",
        unsupported_reason=Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS,
    )


def _detachment_rows(
    *,
    detachment_row: faction_detachments_2026_27.SourceDetachmentRow,
    pdf_record: Phase17EFactionPdfRecord,
) -> tuple[Phase17ECoverageRow, ...]:
    runtime_consumer_ids = _detachment_rule_runtime_consumer_ids(detachment_row)
    rule_ir_hash = generic_ir_support.generic_supported_detachment_rule_ir_hash(detachment_row)
    status = Phase17ECoverageStatus.GENERIC_SUPPORTED
    handler_id: str | None = None
    if rule_ir_hash is None and runtime_consumer_ids:
        status = Phase17ECoverageStatus.IMPLEMENTED
        handler_id = runtime_consumer_ids[0]
    elif rule_ir_hash is None:
        status = Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
        handler_id = f"phase17e:detachment:{detachment_row.detachment_id}:rule"
    return (
        Phase17ECoverageRow(
            descriptor_id=(
                f"phase17e:{detachment_row.faction_id}:{detachment_row.detachment_id}:rule"
            ),
            coverage_kind=Phase17ECoverageKind.DETACHMENT_RULE,
            status=status,
            faction_id=detachment_row.faction_id,
            faction_name=pdf_record.faction_name,
            source_ids=(detachment_row.source_id, pdf_record.source_id),
            source_pdf_package_id=pdf_record.package_id,
            rule_name=f"{detachment_row.name} detachment rule",
            detachment_id=detachment_row.detachment_id,
            detachment_name=detachment_row.name,
            force_disposition_id=detachment_row.force_disposition_id,
            detachment_point_cost=detachment_row.detachment_point_cost,
            is_new_for_eleventh=detachment_row.is_new_for_eleventh,
            runtime_support_status=(
                faction_subrules_2026_27.SourceSubruleRuntimeStatus.ENGINE_CONSUMED
                if runtime_consumer_ids
                else None
            ),
            runtime_consumer_ids=runtime_consumer_ids,
            handler_id=handler_id,
            rule_ir_hash=rule_ir_hash,
        ),
    )


def _detachment_rule_runtime_consumer_ids(
    detachment_row: faction_detachments_2026_27.SourceDetachmentRow,
) -> tuple[str, ...]:
    if detachment_row.faction_id == "chaos-daemons":
        return CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMER_IDS_BY_DETACHMENT_ID.get(
            detachment_row.detachment_id,
            (),
        )
    return ()


def _enhancement_row(
    *,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
    detachment_row: faction_detachments_2026_27.SourceDetachmentRow,
    pdf_record: Phase17EFactionPdfRecord,
) -> Phase17ECoverageRow:
    rule_ir_hash = generic_ir_support.generic_supported_enhancement_rule_ir_hash(source_row)
    status = _exact_subrule_coverage_status(source_row.runtime_consumer_ids)
    handler_id: str | None = _exact_subrule_handler_id(
        default_handler_id=f"phase17e:{source_row.faction_id}:{source_row.detachment_id}:"
        f"enhancement:{source_row.enhancement_id}",
        runtime_consumer_ids=source_row.runtime_consumer_ids,
    )
    if rule_ir_hash is not None:
        status = Phase17ECoverageStatus.GENERIC_SUPPORTED
        handler_id = None
    return Phase17ECoverageRow(
        descriptor_id=f"phase17e:{source_row.source_row_id}",
        coverage_kind=Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
        status=status,
        faction_id=source_row.faction_id,
        faction_name=source_row.faction_name,
        source_ids=(*source_row.all_source_ids, detachment_row.source_id, pdf_record.source_id),
        source_pdf_package_id=pdf_record.package_id,
        rule_name=source_row.name,
        detachment_id=source_row.detachment_id,
        detachment_name=source_row.detachment_name,
        force_disposition_id=detachment_row.force_disposition_id,
        detachment_point_cost=detachment_row.detachment_point_cost,
        is_new_for_eleventh=detachment_row.is_new_for_eleventh,
        rule_id=source_row.enhancement_id,
        timing_descriptor=source_row.timing_descriptor,
        rule_category=source_row.category,
        runtime_support_status=source_row.runtime_support_status,
        runtime_consumer_ids=source_row.runtime_consumer_ids,
        handler_id=handler_id,
        rule_ir_hash=rule_ir_hash,
    )


def _stratagem_row(
    *,
    source_row: faction_subrules_2026_27.SourceStratagemRow,
    detachment_row: faction_detachments_2026_27.SourceDetachmentRow,
    pdf_record: Phase17EFactionPdfRecord,
) -> Phase17ECoverageRow:
    rule_ir_hash = generic_ir_support.generic_supported_stratagem_rule_ir_hash(source_row)
    status = Phase17ECoverageStatus.GENERIC_SUPPORTED
    handler_id: str | None = None
    if rule_ir_hash is None:
        status = _exact_subrule_coverage_status(source_row.runtime_consumer_ids)
        handler_id = _exact_subrule_handler_id(
            default_handler_id=f"phase17e:{source_row.faction_id}:{source_row.detachment_id}:"
            f"stratagem:{source_row.stratagem_id}",
            runtime_consumer_ids=source_row.runtime_consumer_ids,
        )
    return Phase17ECoverageRow(
        descriptor_id=f"phase17e:{source_row.source_row_id}",
        coverage_kind=Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        status=status,
        faction_id=source_row.faction_id,
        faction_name=source_row.faction_name,
        source_ids=(*source_row.all_source_ids, detachment_row.source_id, pdf_record.source_id),
        source_pdf_package_id=pdf_record.package_id,
        rule_name=source_row.name,
        detachment_id=source_row.detachment_id,
        detachment_name=source_row.detachment_name,
        force_disposition_id=detachment_row.force_disposition_id,
        detachment_point_cost=detachment_row.detachment_point_cost,
        is_new_for_eleventh=detachment_row.is_new_for_eleventh,
        rule_id=source_row.stratagem_id,
        timing_descriptor=source_row.timing_descriptor,
        rule_category=source_row.category,
        runtime_support_status=source_row.runtime_support_status,
        runtime_consumer_ids=source_row.runtime_consumer_ids,
        handler_id=handler_id,
        rule_ir_hash=rule_ir_hash,
    )


def _pdf_record_for_faction(
    pdf_by_faction_id: dict[str, Phase17EFactionPdfRecord],
    faction_id: str,
) -> Phase17EFactionPdfRecord:
    record = pdf_by_faction_id.get(faction_id)
    if record is None:
        raise Phase17EFactionCoverageError("Phase17E faction is missing PDF source coverage.")
    return record


def _detachment_row_for_subrule(
    rows_by_owner_id: dict[tuple[str, str], faction_detachments_2026_27.SourceDetachmentRow],
    *,
    faction_id: str,
    detachment_id: str,
) -> faction_detachments_2026_27.SourceDetachmentRow:
    row = rows_by_owner_id.get((faction_id, detachment_id))
    if row is None:
        raise Phase17EFactionCoverageError("Exact subrule row references unknown detachment.")
    return row


def _exact_subrule_coverage_status(
    runtime_consumer_ids: tuple[str, ...],
) -> Phase17ECoverageStatus:
    if runtime_consumer_ids:
        return Phase17ECoverageStatus.IMPLEMENTED
    return Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED


def _exact_subrule_handler_id(
    *,
    default_handler_id: str,
    runtime_consumer_ids: tuple[str, ...],
) -> str:
    if runtime_consumer_ids:
        return runtime_consumer_ids[0]
    return default_handler_id


def _validate_pdf_records(
    records: tuple[Phase17EFactionPdfRecord, ...],
) -> tuple[Phase17EFactionPdfRecord, ...]:
    if type(records) is not tuple:
        raise Phase17EFactionCoverageError("Phase17E pdf_records must be a tuple.")
    source_faction_ids = {row.faction_id for row in faction_detachments_2026_27.faction_rows()}
    seen: set[str] = set()
    validated: list[Phase17EFactionPdfRecord] = []
    for record in records:
        if type(record) is not Phase17EFactionPdfRecord:
            raise Phase17EFactionCoverageError(
                "Phase17E pdf_records must contain Phase17EFactionPdfRecord values."
            )
        if record.faction_id in seen:
            raise Phase17EFactionCoverageError("Phase17E pdf_records must be unique by faction.")
        seen.add(record.faction_id)
        validated.append(record)
    if seen != source_faction_ids:
        raise Phase17EFactionCoverageError("Phase17E pdf_records must cover every source faction.")
    return tuple(sorted(validated, key=lambda record: record.faction_id))


def _validate_coverage_rows(
    rows: tuple[Phase17ECoverageRow, ...],
    pdf_records: tuple[Phase17EFactionPdfRecord, ...],
) -> tuple[Phase17ECoverageRow, ...]:
    if type(rows) is not tuple:
        raise Phase17EFactionCoverageError("Phase17E coverage_rows must be a tuple.")
    if not rows:
        raise Phase17EFactionCoverageError("Phase17E coverage_rows must not be empty.")
    pdf_package_ids = {record.package_id for record in pdf_records}
    source_faction_ids = {row.faction_id for row in faction_detachments_2026_27.faction_rows()}
    source_detachment_ids = {
        (row.faction_id, row.detachment_id) for row in faction_detachments_2026_27.detachment_rows()
    }
    seen: set[str] = set()
    validated: list[Phase17ECoverageRow] = []
    for row in rows:
        if type(row) is not Phase17ECoverageRow:
            raise Phase17EFactionCoverageError(
                "Phase17E coverage_rows must contain Phase17ECoverageRow values."
            )
        if row.descriptor_id in seen:
            raise Phase17EFactionCoverageError("Phase17E coverage_rows must be unique.")
        if row.faction_id not in source_faction_ids:
            raise Phase17EFactionCoverageError("Phase17E coverage row references unknown faction.")
        if row.source_pdf_package_id not in pdf_package_ids:
            raise Phase17EFactionCoverageError("Phase17E coverage row references unknown PDF.")
        if row.detachment_id is not None and (row.faction_id, row.detachment_id) not in (
            source_detachment_ids
        ):
            raise Phase17EFactionCoverageError(
                "Phase17E coverage row references unknown detachment."
            )
        seen.add(row.descriptor_id)
        validated.append(row)
    return tuple(sorted(validated, key=lambda row: row.descriptor_id))


def _coverage_kind_from_token(token: object) -> Phase17ECoverageKind:
    if type(token) is Phase17ECoverageKind:
        return token
    if type(token) is not str:
        raise Phase17EFactionCoverageError("Phase17E coverage kind token must be a string.")
    try:
        return Phase17ECoverageKind(token)
    except ValueError as exc:
        raise Phase17EFactionCoverageError(f"Unsupported Phase17E coverage kind: {token}.") from exc


def _coverage_status_from_token(token: object) -> Phase17ECoverageStatus:
    if type(token) is Phase17ECoverageStatus:
        return token
    if type(token) is not str:
        raise Phase17EFactionCoverageError("Phase17E coverage status token must be a string.")
    try:
        return Phase17ECoverageStatus(token)
    except ValueError as exc:
        raise Phase17EFactionCoverageError(
            f"Unsupported Phase17E coverage status: {token}."
        ) from exc


def _unsupported_reason_from_token(token: object) -> Phase17EUnsupportedReason:
    if type(token) is Phase17EUnsupportedReason:
        return token
    if type(token) is not str:
        raise Phase17EFactionCoverageError("Phase17E unsupported reason token must be a string.")
    try:
        return Phase17EUnsupportedReason(token)
    except ValueError as exc:
        raise Phase17EFactionCoverageError(
            f"Unsupported Phase17E unsupported reason: {token}."
        ) from exc


def _runtime_support_status_from_token(
    token: object,
) -> faction_subrules_2026_27.SourceSubruleRuntimeStatus:
    if type(token) is faction_subrules_2026_27.SourceSubruleRuntimeStatus:
        return token
    if type(token) is not str:
        raise Phase17EFactionCoverageError("Phase17E runtime support token must be a string.")
    try:
        return faction_subrules_2026_27.SourceSubruleRuntimeStatus(token)
    except ValueError as exc:
        raise Phase17EFactionCoverageError(
            f"Unsupported Phase17E runtime support status: {token}."
        ) from exc


_validate_identifier = IdentifierValidator(Phase17EFactionCoverageError)


def _validate_non_empty_text(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_pdf_filename(value: object) -> str:
    filename = _validate_identifier("pdf_filename", value)
    if "\\" in filename or "/" in filename or not filename.endswith(".pdf"):
        raise Phase17EFactionCoverageError("Phase17E pdf_filename must be a PDF filename.")
    return filename


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise Phase17EFactionCoverageError(f"Phase17E {field_name} must be a SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise Phase17EFactionCoverageError(
            f"Phase17E {field_name} must be a lowercase SHA-256 digest."
        )
    return digest


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise Phase17EFactionCoverageError(f"Phase17E {field_name} must be a tuple.")
    if not values and not allow_empty:
        raise Phase17EFactionCoverageError(f"Phase17E {field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise Phase17EFactionCoverageError(f"Phase17E {field_name} must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_detachment_point_cost(value: object) -> int:
    if type(value) is not int:
        raise Phase17EFactionCoverageError("Phase17E detachment_point_cost must be an integer.")
    if value < 1 or value > 3:
        raise Phase17EFactionCoverageError(
            "Phase17E detachment_point_cost must be between 1 and 3."
        )
    return value


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_PDF_RECORDS = _validate_pdf_records(
    tuple(
        Phase17EFactionPdfRecord(
            faction_id=record.faction_id,
            faction_name=record.faction_name,
            package_id=record.package_id,
            title=record.title,
            source_date=record.source_date,
            pdf_filename=record.pdf_path.rsplit("/", maxsplit=1)[-1],
            sha256=record.sha256,
            bytes=record.bytes,
        )
        for record in faction_source_promotion_2026_07.current_source_records()
    )
)
