from __future__ import annotations

import argparse
import json
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
