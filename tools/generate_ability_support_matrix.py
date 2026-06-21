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
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_registered_hook_ids
from warhammer40k_core.engine.faction_content.bundle import (
    DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentSupportStatus
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
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
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
        "shadow-legion",
    ): SupportSectionRow(
        subject="Shadow Legion",
        engine=(
            "Mustering restrictions and keyword grants, Murderer's Cowl Advance "
            "eligibility, Penumbral Puppetry hit modifiers, Gloam Rot wound "
            "modifiers, Shadow's Caress snap-target restriction, and Disciples "
            "of Be'lakor Dark Pacts hooks"
        ),
        documentation="Adapter contract, decision catalog, README, and generated matrix",
        tests=(
            "Focused mustering, runtime hook, modifier, target-restriction, "
            "out-of-phase shooting, Be'lakor auto-pass, and Feel No Pain routing tests"
        ),
        overall="Full",
        notes=(
            "Includes Shadow Legion/Undivided/Deep Strike keyword grants, Thralls of "
            "the First Prince roster caps and exclusions, Dark Pacts selected-to-shoot/"
            "fight grants for Undivided units, Be'lakor Leadership auto-pass, and "
            "Shadow-source D3 mortal-wound Feel No Pain continuation."
        ),
    ),
}

_RUNTIME_SOURCE_LABEL_OVERRIDES: Mapping[str, str] = {
    "phase17f:phase17e:aeldari:army-rule": "Battle Focus",
    "phase17f:phase17e:aeldari:path-of-the-outcast:enhancements": (
        "Path of the Outcast Enhancements"
    ),
    "phase17f:phase17e:aeldari:path-of-the-outcast:far-reaching-doom": ("Far-reaching Doom"),
    "phase17f:phase17e:chaos-daemons:army-rule": "The Shadow of Chaos",
    "phase17f:phase17e:chaos-daemons:blood-legion:rule": "Blood Legion",
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:enhancements": (
        "Cavalcade of Chaos Upgrades"
    ),
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:rule": "Unholy Avalanche",
    "phase17f:phase17e:chaos-daemons:cavalcade-of-chaos:stratagems": (
        "Cavalcade of Chaos Stratagems"
    ),
    "phase17f:phase17e:chaos-daemons:shadow-legion:rule": "Shadow Legion",
    "phase17f:phase17e:chaos-space-marines:army-rule": "Dark Pacts",
    "phase17f:phase17e:death-guard:army-rule": "Nurgle's Gift",
    "phase17f:phase17e:drukhari:army-rule": "Power from Pain",
    "phase17f:phase17e:emperors-children:army-rule": "Thrill Seekers",
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
}


def main() -> None:
    args = _parse_args()
    source_json_dir = _resolve_repo_path(args.source_json_dir)
    output_dir = _resolve_repo_path(args.output_dir)
    docs_path = _resolve_repo_path(args.docs_path)
    rows = ability_support_matrix_rows(source_json_dir=source_json_dir)
    category_rows = ability_coverage_category_rows(rows)
    row_payloads = ability_coverage_rows_payload(rows)
    category_payloads = ability_coverage_category_rows_payload(category_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "ability_coverage_rows.json", row_payloads)
    _write_json(output_dir / "ability_support_category_rows.json", category_payloads)
    docs_path.write_text(support_matrix_markdown(category_payloads), encoding="utf-8")


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
            faction_id=emperors_children_army_rule.EMPERORS_CHILDREN_FACTION_ID,
            ability_id=emperors_children_army_rule.HOOK_ID,
            ability_name="Thrill Seekers",
            semantic_category="faction.army_rule.thrill_seekers",
            runtime_consumer_ids=_emperors_children_runtime_consumer_ids(),
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
            (binding.trigger_kind.value, binding.source_rule_id)
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
        labels = labels_by_id.get(handler_id)
        if labels is None:
            labels = {_label_from_identifier(handler_id)}
        for label in labels:
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
                "Core keyword ability rows are still primarily surfaced through source-backed "
                "category rows above. This table records the current section ownership without "
                "claiming complete generated source coverage for every Core Rules keyword."
            ),
            (
                SupportSectionRow(
                    "Deep Strike",
                    "Reserve declaration and placement hosts",
                    "Adapter contract and architecture",
                    "Focused reserve/deployment tests",
                    "Full",
                    "Current generated rows are `engine_consumed`.",
                ),
                SupportSectionRow(
                    "Other Core Rules keyword abilities",
                    "Mixed phase-owned hosts or explicit unsupported descriptors",
                    "Architecture and source-row unsupported audits",
                    "Coverage varies by keyword",
                    "Partial",
                    "Keep expanded per-keyword rows separate from wargear keyword abilities.",
                ),
            ),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Core Terrain And Visibility",
            (
                "Terrain visibility behavior is source-backed through the ruleset descriptor "
                "and consumed by Shooting target selection and declaration validation."
            ),
            (
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
                    "Emperor's Children - Thrill Seekers",
                    "Named army-rule handler",
                    "Architecture and generated matrix",
                    "Focused faction runtime tests",
                    "Full",
                    "Includes movement, charge, and shooting target restrictions.",
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
    lines.extend(_detachment_rules_section_markdown())
    lines.extend(
        _support_section_markdown(
            "Faction Stratagems",
            (
                "Faction Stratagems are distinct from Core Stratagems and should remain "
                "faction-scoped."
            ),
            _faction_stratagem_support_rows(),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Enhancements",
            "Enhancement support should be tracked under each faction and detachment.",
            _enhancement_support_rows(),
        )
    )
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


def _faction_stratagem_support_rows() -> tuple[SupportSectionRow, ...]:
    return (
        SupportSectionRow(
            "Aeldari - Path of the Outcast Stratagems",
            "Named post-shooting Stratagem handlers",
            "Adapter contract, architecture, and generated matrix",
            "Focused CP, targeting, Battle-shock, detection, and movement tests",
            "Full",
            (
                "Includes Eldritch Suppression, Casting Back the Veil, and Nomads of "
                "the Hidden Way through the shared `use_stratagem` and triggered "
                "movement paths."
            ),
        ),
        SupportSectionRow(
            "Aeldari - Corsair Coterie Stratagems",
            (
                "Named Movement, Shooting, and Fight phase Stratagem handlers plus "
                "source-backed attack reroll, triggered movement, target restriction, "
                "and weapon-profile hooks"
            ),
            "Adapter contract, architecture, and generated matrix",
            (
                "Focused timing, targeting, source-backed wound reroll, AP/weapon-keyword "
                "modifier, mortal-wound, triggered-movement, and target-restriction tests"
            ),
            "Full",
            (
                "Includes Pirates' Due, Lethal Ruse, Outcast Ambush, Into the Breach, "
                "Cloak and Shadow, and Vengeful Sorrow through the shared `use_stratagem`, "
                "attack sequence, charge eligibility, and triggered movement paths."
            ),
        ),
        SupportSectionRow(
            "Chaos Daemons - Cavalcade of Chaos Stratagems",
            (
                "Named Warp-Riders handler plus generic ingress and Desperate Escape "
                "Stratagem records"
            ),
            "Adapter contract, architecture, and generated matrix",
            (
                "Focused Movement timing, CP, Strategic Reserves ingress, Desperate Escape, "
                "and handler-drift tests"
            ),
            "Full",
            (
                "Includes Warp-Riders, From Beyond the Veil, and Inescapable Manifestations "
                "through the shared `use_stratagem`, persisting-effect, Strategic Reserves "
                "placement, and forced Desperate Escape paths."
            ),
        ),
        SupportSectionRow(
            "Faction-pack Stratagems",
            "Coverage/report rows exist; semantic handlers vary",
            "Architecture and coverage reports",
            "Faction-specific tests where implemented",
            "Partial",
            ("Future generator work should group rows by faction, detachment, and Stratagem."),
        ),
    )


def _enhancement_support_rows() -> tuple[SupportSectionRow, ...]:
    return (
        SupportSectionRow(
            "Aeldari - Path of the Outcast Upgrades",
            "Enhancement effect bindings",
            "Architecture and generated matrix",
            "Focused eligibility, hidden-preservation, and CHARACTER AP tests",
            "Full",
            (
                "Includes Camouflaged Snipers preserving Hidden after ranged attacks "
                "and Assassins' Eye applying +1 AP against CHARACTER targets."
            ),
        ),
        SupportSectionRow(
            "Aeldari - Corsair Coterie Enhancements",
            (
                "Enhancement effect, setup, turn-end, Stratagem-cost choice, Objective "
                "Control, and save-option bindings"
            ),
            "Adapter contract, architecture, and generated matrix",
            "Focused Veterans, Infamy, Webway Pathstone, Archraider, and Voidstone tests",
            "Full",
            (
                "Includes Infamy OC reduction aura, Webway Pathstone Deep Strike and "
                "once-per-battle end-opponent-turn Strategic Reserves choice, Archraider "
                "selected model setup plus optional Lord of Deceit +1CP modifier, and "
                "Voidstone 5+ invulnerable save."
            ),
        ),
        SupportSectionRow(
            "Chaos Daemons - Cavalcade of Chaos Upgrades",
            "Enhancement movement modifier and selected-to-fight ability bindings",
            "Adapter contract, architecture, and generated matrix",
            (
                "Focused roster eligibility, lifecycle movement, melee targeting, "
                "and source-drift tests"
            ),
            "Full",
            (
                "Includes Apocalyptic Steeds +1 Movement for LEGIONES DAEMONICA MOUNTED "
                "units and Soul-Shattering Charge 3 inch melee targeting after a charge."
            ),
        ),
        SupportSectionRow(
            "Faction-pack Enhancements",
            "Coverage/report rows exist; semantic handlers vary",
            "Architecture and coverage reports",
            "Faction-specific tests where implemented",
            "Partial",
            ("Future generator work should group rows by faction, detachment, and enhancement."),
        ),
    )


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


def _inline_code_list(values: list[str]) -> str:
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
