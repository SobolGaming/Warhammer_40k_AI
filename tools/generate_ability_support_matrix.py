from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.core.faction_aliases import CHAOS_SPACE_MARINES_FACTION_ID
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
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
from warhammer40k_core.engine.army_mustering import SPACE_MARINE_CHAPTERS_SOURCE_ID
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_registered_hook_ids
from warhammer40k_core.engine.faction_content.bundle import (
    DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentSupportStatus
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
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_detachments_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageRow,
    Phase17ECoverageStatus,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
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
DAEMON_WARGEAR_DATASHEET_IDS = ("000001112", "000001114", "000001115")
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
class RuntimeHookInventoryRow:
    hook_id: str
    ability_or_rule_labels: tuple[str, ...]


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
        engine="Warp Rifts reserve-arrival distance hook",
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
    "phase17f:phase17e:chaos-knights:army-rule": "Harbingers of Dread",
    "phase17f:phase17e:chaos-space-marines:army-rule": "Dark Pacts",
    "phase17f:phase17e:death-guard:army-rule": "Nurgle's Gift",
    "phase17f:phase17e:drukhari:army-rule": "Power from Pain",
    "phase17f:phase17e:emperors-children:army-rule": "Thrill Seekers",
    "phase17f:phase17e:imperial-knights:army-rule": "Code Chivalric",
    "phase17f:phase17e:leagues-of-votann:army-rule": "Prioritised Efficiency",
    "phase17g:space-marines:army-rule": "Oath of Moment",
    "phase17f:phase17e:tau-empire:army-rule": "For the Greater Good",
    "phase17f:phase17e:world-eaters:army-rule": "Blessings of Khorne",
    "phase17g:aeldari:corsair-coterie:enhancements": "Corsair Coterie Enhancements",
    "phase17g:aeldari:corsair-coterie:relentless-raiders": "Corsair Coterie",
    "phase17g:aeldari:corsair-coterie:stratagems": "Corsair Coterie Stratagems",
}

_RUNTIME_ID_LABEL_OVERRIDES: Mapping[str, str] = {
    "phase17g:aeldari:corsair-coterie:stratagems:cloak-and-shadow:target-restriction": (
        "Cloak and Shadow"
    ),
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
    rows = ability_support_matrix_rows(source_json_dir=source_json_dir)
    category_rows = ability_coverage_category_rows(rows)
    row_payloads = ability_coverage_rows_payload(rows)
    category_payloads = ability_coverage_category_rows_payload(category_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "ability_coverage_rows.json", row_payloads)
    _write_json(output_dir / "ability_support_category_rows.json", category_payloads)
    docs_path.write_text(support_matrix_markdown(category_payloads), encoding="utf-8")
    faction_docs_dir.mkdir(parents=True, exist_ok=True)
    for filename, markdown in faction_support_markdown_files().items():
        (faction_docs_dir / filename).write_text(markdown, encoding="utf-8")


def ability_support_matrix_rows(
    *,
    source_json_dir: Path = DEFAULT_SOURCE_JSON_DIR,
) -> tuple[AbilityCoverageRow, ...]:
    source_json_dir = _resolve_repo_path(source_json_dir)
    artifacts = _load_source_artifacts(source_json_dir)
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=artifacts,
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=DAEMON_WARGEAR_DATASHEET_IDS,
        height_overrides=(
            CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES
            + BLOODLETTERS_HEIGHT_OVERRIDES
            + FLESH_HOUNDS_HEIGHT_OVERRIDES
        ),
    )
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    rows = ability_coverage_rows_from_catalog(
        package.army_catalog,
        datasheet_ids=DAEMON_WARGEAR_DATASHEET_IDS,
    )
    return (*rows, *_runtime_faction_army_rule_rows())


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


def _runtime_faction_army_rule_rows() -> tuple[AbilityCoverageRow, ...]:
    return (
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
            ability_name=imperial_knights_army_rule.CODE_CHIVALRIC_ABILITY_NAME,
            semantic_category="faction.army_rule.code_chivalric",
            runtime_consumer_ids=_imperial_knights_runtime_consumer_ids(),
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
            ability_name=tau_empire_army_rule.FOR_THE_GREATER_GOOD_ABILITY_NAME,
            semantic_category="faction.army_rule.for_the_greater_good",
            runtime_consumer_ids=_tau_empire_runtime_consumer_ids(),
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


def _imperial_knights_runtime_consumer_ids() -> tuple[str, ...]:
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
) -> str:
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
            "execute through the generic IR handler."
        ),
        (
            "- `engine_consumed`: a structured descriptor, supported generic IR, or "
            "implementation-backed runtime content is consumed by a phase/query host through a "
            "named runtime consumer."
        ),
    ]
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


def faction_support_markdown_files() -> dict[str, str]:
    return {
        f"{faction_row.faction_id}.md": _faction_support_markdown(faction_row)
        for faction_row in faction_detachments_2026_27.faction_rows()
    }


def _faction_support_markdown(
    faction_row: faction_detachments_2026_27.SourceFactionRow,
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
    engine_consumed_row_count = sum(
        1
        for row in (*army_rule_rows, *detachment_rule_rows, *exact_rows)
        if row.status is Phase17ECoverageStatus.IMPLEMENTED
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
    lines.extend(_faction_detachment_rule_support_markdown(detachment_support_rows))
    lines.extend(_faction_detachment_rule_coverage_rows_markdown(detachment_rule_rows))
    lines.extend(_faction_exact_rule_rows_markdown("Enhancements", enhancement_rows))
    lines.extend(_faction_exact_rule_rows_markdown("Stratagems", stratagem_rows))
    lines.append("")
    return "\n".join(lines)


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
            "records, or registered runtime-content contributions."
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
    inventory.setdefault(hook_id, set()).add(label)


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
            if row.coverage_kind
            in {
                Phase17ECoverageKind.FACTION_ARMY_RULE,
                Phase17ECoverageKind.DETACHMENT_RULE,
                Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
                Phase17ECoverageKind.DETACHMENT_STRATAGEM,
            }
            and row.status is Phase17ECoverageStatus.IMPLEMENTED
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
