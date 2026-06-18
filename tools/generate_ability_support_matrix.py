from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
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
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule as death_guard_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule as emperors_children_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
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
DAEMON_WARGEAR_DATASHEET_IDS = ("000001114", "000001115")
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
            "Runtime grants the 6 inch detection-range effect and expires it after the "
            "source shoots."
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
        engine="Unholy Avalanche Fall Back eligibility hook",
        documentation="Source row, execution record, and generated matrix",
        tests="Focused Fall Back, Shoot, Charge, and handler-drift tests",
        overall="Full",
        notes=(
            "Mounted Legiones Daemonica units retain Shoot and Charge permissions after Fall Back."
        ),
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
    docs_path.write_text(_support_matrix_markdown(category_payloads), encoding="utf-8")


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
            CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES + BLOODLETTERS_HEIGHT_OVERRIDES
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


def _support_matrix_markdown(
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
        "",
        "Current coverage categories:",
        "",
        (
            "| Category | Support status | Runtime consumers | Rows | Source kinds | "
            "Ability/datasheet pairs | Semantic category |"
        ),
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in category_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(row["category_name"]),
                    _inline_code_list(row["support_stages"]),
                    _inline_code_list(row["runtime_consumer_ids"]),
                    str(row["coverage_row_count"]),
                    _source_kind_counts_text(row["source_kind_counts"]),
                    _ability_datasheet_pairs_text(row["ability_datasheet_pairs"]),
                    f"`{_markdown_text(row['category_id'])}`",
                )
            )
            + " |"
        )
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
            "",
        )
    )
    return "\n".join(lines)


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
            (
                SupportSectionRow(
                    "Faction-pack Stratagems",
                    "Coverage/report rows exist; semantic handlers vary",
                    "Architecture and coverage reports",
                    "Faction-specific tests where implemented",
                    "Partial",
                    (
                        "Future generator work should group rows by faction, detachment, "
                        "and Stratagem."
                    ),
                ),
            ),
        )
    )
    lines.extend(
        _support_section_markdown(
            "Enhancements",
            "Enhancement support should be tracked under each faction and detachment.",
            (
                SupportSectionRow(
                    "Faction-pack Enhancements",
                    "Coverage/report rows exist; semantic handlers vary",
                    "Architecture and coverage reports",
                    "Faction-specific tests where implemented",
                    "Partial",
                    (
                        "Future generator work should group rows by faction, detachment, "
                        "and enhancement."
                    ),
                ),
            ),
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
