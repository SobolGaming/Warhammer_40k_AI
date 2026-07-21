from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from tools.aeldari_ability_semantic_descriptions import (
    DESCRIPTION_ARTIFACT_PATH,
    DESCRIPTION_TEXT_PATH,
    DOCUMENTATION_BUCKET_STILL_NEEDED,
    DOCUMENTATION_BUCKET_SUPPORTED,
    aeldari_ability_semantic_descriptions,
    load_aeldari_ability_semantic_descriptions,
)
from tools.aeldari_datasheet_semantic_coverage import (
    COVERAGE_PATH,
    OVERLAY_PACK_PATH,
    RELEASE_MANIFEST_PATH,
    SEMANTIC_BUCKET_ALL_CONSUMED,
    SEMANTIC_BUCKET_BRIDGE_BLOCKED,
    SEMANTIC_BUCKET_HOST_NEEDED,
    SEMANTIC_BUCKET_UNSUPPORTED_IR,
    SEMANTIC_BUCKETS,
    SOURCE_ARTIFACT_TABLES,
    SOURCE_JSON_DIR,
    TACOMA_OVERLAY_PACK_PATH,
    aeldari_datasheet_semantic_coverage,
    load_aeldari_datasheet_semantic_coverage,
)
from tools.aeldari_support_report import aeldari_datasheet_support_markdown
from tools.faction_pack_datasheet_review import (
    SOURCE_DATASHEETS_PATH,
    DatasheetSourceTreatment,
    faction_pack_datasheet_review,
    faction_pack_datasheet_review_markdown,
    faction_pack_datasheet_reviews,
    reviewed_faction_ids,
)
from tools.generate_ability_support_matrix import (
    DatasheetSupportRow,
    ability_support_matrix_rows,
    datasheet_support_rows,
    faction_support_markdown_files,
)
from tools.generate_aeldari_ability_semantic_descriptions import (
    generated_aeldari_ability_semantic_descriptions,
)
from tools.generate_aeldari_datasheet_semantic_coverage import (
    generated_aeldari_datasheet_semantic_coverage,
)

from warhammer40k_core.engine.ability_coverage import AbilityCoverageSupportStage
from warhammer40k_core.engine.catalog_movement_end_reactive_normal_move_support import (
    CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_prebattle_redeploy import (
    CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_DICE_RESULT_OVERRIDE_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
    CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
)
from warhammer40k_core.engine.core_descriptor_consumption import (
    CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID,
    CORE_LEADER_ATTACHMENT_CONSUMER_ID,
    CORE_SCOUTS_PREBATTLE_CONSUMER_ID,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    faction_pdf_records,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES,
    AELDARI_RANGERS_HEIGHT_OVERRIDES,
)
from warhammer40k_core.rules.wahapedia_schema import WahapediaJsonArtifact

AELDARI_COMPLETE_IDS = frozenset({"000000605", "000004193", "000004194", "000004195", "000004196"})
AELDARI_UPDATE_IDS = frozenset(
    {
        "000000571",
        "000000575",
        "000000582",
        "000000584",
        "000000585",
        "000000587",
        "000000592",
        "000000593",
        "000000594",
        "000000595",
        "000000596",
        "000000599",
        "000000600",
        "000000601",
        "000000603",
        "000000606",
        "000000607",
        "000000609",
        "000002531",
        "000002535",
        "000002541",
        "000002542",
        "000003918",
        "000003921",
    }
)
AELDARI_COMPLETE_PAGE_REFERENCES = {
    "000000605": "Complete Datasheets, physical PDF pages 16-17",
    "000004193": "Complete Datasheets, physical PDF pages 12-13",
    "000004194": "Complete Datasheets, physical PDF pages 14-15",
    "000004195": "Complete Datasheets, physical PDF pages 18-19",
    "000004196": "Complete Datasheets, physical PDF pages 20-21",
}


def test_reviews_cover_every_non_daemons_faction_pack() -> None:
    expected_pdf_records = {
        record.faction_id: record
        for record in faction_pdf_records()
        if record.faction_id != "chaos-daemons"
    }

    assert reviewed_faction_ids() == expected_pdf_records.keys()
    assert len(faction_pack_datasheet_reviews()) == 27
    for review in faction_pack_datasheet_reviews():
        expected_pdf = expected_pdf_records[review.faction_id]
        assert review.faction_name == expected_pdf.faction_name
        assert review.pdf_filename == expected_pdf.pdf_filename
        assert review.pdf_sha256 == expected_pdf.sha256


def test_every_review_is_an_exhaustive_explicit_source_partition_with_matching_names() -> None:
    payload = cast(dict[str, Any], json.loads(SOURCE_DATASHEETS_PATH.read_text(encoding="utf-8")))
    source_rows = cast(list[dict[str, Any]], payload["rows"])
    source_by_id = {cast(str, row["fields"]["id"]): row for row in source_rows}

    for review in faction_pack_datasheet_reviews():
        expected_ids = {
            cast(str, row["fields"]["id"])
            for row in source_rows
            if row["fields"]["faction_id"] == review.source_faction_id
            and row["fields"]["source_id"] == review.source_id
            and row["fields"]["virtual"] == "false"
        } | set(review.additional_source_datasheet_ids)
        rows_by_treatment = {
            treatment: review.rows_for(treatment) for treatment in DatasheetSourceTreatment
        }
        treatment_ids = {
            treatment: {row.datasheet_id for row in rows if row.datasheet_id is not None}
            for treatment, rows in rows_by_treatment.items()
        }

        assert set().union(*treatment_ids.values()) == expected_ids
        assert treatment_ids[DatasheetSourceTreatment.COMPLETE_PDF].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.RULES_UPDATE]
        )
        assert treatment_ids[DatasheetSourceTreatment.COMPLETE_PDF].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.UNCHANGED_PREDECESSOR]
        )
        assert treatment_ids[DatasheetSourceTreatment.RULES_UPDATE].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.UNCHANGED_PREDECESSOR]
        )
        assert sum(review.treatment_counts().values()) == len(review.rows)
        for row in review.rows:
            if row.datasheet_id is not None:
                assert row.datasheet_name == source_by_id[row.datasheet_id]["fields"]["name"]
            if row.treatment is not DatasheetSourceTreatment.UNCHANGED_PREDECESSOR:
                assert row.pdf_page_reference


def test_aeldari_treatments_are_the_exact_reviewed_sets() -> None:
    review = faction_pack_datasheet_review("aeldari")
    complete_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.COMPLETE_PDF)
    }
    updated_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.RULES_UPDATE)
    }
    unchanged_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.UNCHANGED_PREDECESSOR)
    }
    all_ids = {cast(str, row.datasheet_id) for row in review.rows}

    assert complete_ids == AELDARI_COMPLETE_IDS
    assert updated_ids == AELDARI_UPDATE_IDS
    assert unchanged_ids == all_ids - AELDARI_COMPLETE_IDS - AELDARI_UPDATE_IDS
    assert review.treatment_counts() == {
        DatasheetSourceTreatment.COMPLETE_PDF: 5,
        DatasheetSourceTreatment.RULES_UPDATE: 24,
        DatasheetSourceTreatment.UNCHANGED_PREDECESSOR: 41,
    }
    assert {
        cast(str, row.datasheet_id): row.pdf_page_reference
        for row in review.rows_for(DatasheetSourceTreatment.COMPLETE_PDF)
    } == AELDARI_COMPLETE_PAGE_REFERENCES


def test_aeldari_markdown_preserves_groups_provenance_and_exclusions() -> None:
    markdown = "\n".join(faction_pack_datasheet_review_markdown("aeldari"))

    assert "### Craftworlds / Asuryani" in markdown
    assert "### Anhrathe / Corsairs" in markdown
    assert "### Harlequins" in markdown
    assert "### Ynnari" in markdown
    assert "Prince Yriel (`000004193`) | `complete_pdf`" in markdown
    assert "Asurmen (`000000571`) | `rules_update`" in markdown
    assert "Eldrad Ulthran (`000000568`) | `unchanged_predecessor`" in markdown
    assert "48cf09f605dc29b42555d5800c239879c1fc590f85a6a45b0a1f14739b03f0a9" in markdown
    assert (
        "Warhammer Legends, Legends, Forge World, and Imperial Armour rows are excluded" in markdown
    )
    assert "(`000000569`)" not in markdown
    assert "(`000000628`)" not in markdown


def test_manifest_is_a_versioned_data_artifact() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "source_manifests"
        / "faction_pack_datasheet_review_v1.json"
    )
    payload = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))

    assert payload["schema_version"] == "1"
    assert payload["source_snapshot"]["datasheets_artifact_hash"]
    assert payload["source_snapshot"]["datasheets_sha256"]


def test_non_daemons_semantic_support_rows_remain_in_faction_documents() -> None:
    ability_rows = ability_support_matrix_rows()
    support_rows = datasheet_support_rows()
    markdown_by_filename = faction_support_markdown_files(
        datasheet_support_rows=support_rows,
        ability_rows=ability_rows,
    )
    ability_rows_by_id = {row.coverage_row_id: row for row in ability_rows}

    non_daemons_rows = tuple(row for row in support_rows if row.faction_id != "chaos-daemons")
    assert {(row.faction_id, row.datasheet_id, row.overall) for row in non_daemons_rows} == {
        ("aeldari", "000000577", "Playable"),
        ("aeldari", "000000572", "Playable"),
        ("aeldari", "000000574", "Playable"),
        ("aeldari", "000000588", "Playable"),
        ("aeldari", "000000594", "Playable"),
        ("aeldari", "000000595", "Playable"),
        ("aeldari", "000000592", "Playable"),
        ("aeldari", "000000596", "Playable"),
        ("aeldari", "000000600", "Playable"),
        ("aeldari", "000000601", "Playable"),
        ("aeldari", "000000598", "Playable"),
        ("aeldari", "000000605", "Playable"),
        ("aeldari", "000000611", "Playable"),
        ("aeldari", "000000612", "Playable"),
        ("aeldari", "000000613", "Playable"),
        ("aeldari", "000002531", "Playable"),
        ("aeldari", "000002532", "Playable"),
        ("aeldari", "000002533", "Playable"),
        ("aeldari", "000002759", "Playable"),
        ("aeldari", "000003909", "Playable"),
        ("aeldari", "000004193", "Playable"),
        ("aeldari", "000004194", "Playable"),
        ("aeldari", "000004195", "Playable"),
        ("aeldari", "000004196", "Playable"),
        ("death-guard", "000004209", "Partial"),
        ("emperors-children", "000004208", "Partial"),
        ("thousand-sons", "000001030", "Playable"),
        ("world-eaters", "000004207", "Partial"),
    }
    rangers_infiltrators = next(
        row
        for row in ability_rows
        if row.datasheet_id == "000000592" and row.ability_name == "Infiltrators"
    )
    assert rangers_infiltrators.runtime_consumer_ids == (CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID,)
    for row in non_daemons_rows:
        markdown = markdown_by_filename[f"{row.faction_id}.md"]
        assert markdown.index("## Datasheet Source Review") < markdown.index(
            "## Datasheet / Unit Support"
        )
        if row.faction_id == "aeldari":
            support_markdown = markdown.split("## Datasheet / Unit Support", 1)[1]
            assert f"| {row.datasheet_name} (`{row.datasheet_id}`) |" in support_markdown
            assert "| All consumed |" in next(
                line
                for line in support_markdown.splitlines()
                if line.startswith(f"| {row.datasheet_name} (`{row.datasheet_id}`) |")
            )
        else:
            assert f"| {row.datasheet_name} (`{row.datasheet_id}`) | `{row.overall}` |" in markdown
        if row.faction_id == "aeldari":
            semantic_row = next(
                semantic_row
                for semantic_row in aeldari_datasheet_semantic_coverage().rows
                if semantic_row.datasheet_id == row.datasheet_id
            )
            support_markdown = markdown.split("## Datasheet / Unit Support", 1)[1]
            for ability in semantic_row.abilities:
                assert support_markdown.count(f"`{ability.ability_id}`") == 1
        else:
            for coverage_row_id in row.ability_coverage_row_ids:
                coverage_row = ability_rows_by_id[coverage_row_id]
                assert (
                    f"| {row.datasheet_name} (`{row.datasheet_id}`) | "
                    f"{coverage_row.ability_name} (`{coverage_row.ability_id}`) |"
                ) in markdown

    kharseth_support = next(row for row in non_daemons_rows if row.datasheet_id == "000004194")
    assert (
        kharseth_support.catalog_status,
        kharseth_support.model_geometry_status,
        kharseth_support.wargear_status,
        kharseth_support.weapon_keyword_status,
        kharseth_support.datasheet_ability_status,
    ) == ("Full", "Full", "Full", "Full", "Full")
    assert kharseth_support.faction_interaction_status == "Partial"
    assert "detachment support 2/15" in kharseth_support.notes
    kharseth_ability_rows = {
        ability_rows_by_id[row_id].ability_name: ability_rows_by_id[row_id]
        for row_id in kharseth_support.ability_coverage_row_ids
    }
    assert set(kharseth_ability_rows) == {
        "Leader",
        "Scouts",
        "Aethersense (Psychic)",
        "Fury of the Void (Psychic)",
        "Battle Focus",
    }
    assert all(
        row.support_stage.value == "engine_consumed" for row in kharseth_ability_rows.values()
    )
    assert kharseth_ability_rows["Leader"].runtime_consumer_ids == (
        CORE_LEADER_ATTACHMENT_CONSUMER_ID,
    )
    assert kharseth_ability_rows["Scouts"].runtime_consumer_ids == (
        CORE_SCOUTS_PREBATTLE_CONSUMER_ID,
    )
    assert kharseth_ability_rows["Battle Focus"].runtime_consumer_ids == (
        army_rule.FADE_BACK_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
        army_rule.OPPORTUNITY_SEIZED_HOOK_ID,
        army_rule.STAR_ENGINES_HOOK_ID,
        army_rule.SUDDEN_STRIKE_HOOK_ID,
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
    )

    world_eaters_markdown = markdown_by_filename["world-eaters.md"]
    assert "`catalog-ir:movement-transit-permission`" in world_eaters_markdown
    assert "`catalog-ir:setup-reactive-shoot-charge`" in world_eaters_markdown
    assert "Blessings of Khorne (`000008428`) | `faction` | `descriptor_only`" in (
        world_eaters_markdown
    )

    aeldari_markdown = markdown_by_filename["aeldari.md"]
    snapshot = aeldari_markdown.split("### Exact Ability Semantic Coverage", 1)[1].split(
        "## Detachment Rule Support", 1
    )[0]
    assert "### Unit Datasheet Source Treatments" not in snapshot
    semantic_coverage = aeldari_datasheet_semantic_coverage()
    for group_name in tuple(dict.fromkeys(row.group for row in semantic_coverage.rows)):
        table_row = next(
            line for line in snapshot.splitlines() if line.startswith(f"| {group_name} |")
        )
        cells = [cell.strip() for cell in table_row.strip("|").split(" | ")]
        for bucket_index, bucket in enumerate(SEMANTIC_BUCKETS, start=1):
            expected_labels = {
                f"{row.datasheet_name} (`{row.datasheet_id}`)"
                for row in semantic_coverage.rows
                if row.group == group_name and row.semantic_bucket == bucket
            }
            actual_labels: set[str] = (
                set() if cells[bucket_index] == "None" else set(cells[bucket_index].split("<br>"))
            )
            assert actual_labels == expected_labels


def test_aeldari_semantic_coverage_bridges_every_exact_ability() -> None:
    artifact = aeldari_datasheet_semantic_coverage()
    rows_by_id = {row.datasheet_id: row for row in artifact.rows}

    assert len(rows_by_id) == 70
    assert sum(len(row.abilities) for row in artifact.rows) == 145
    assert Counter(row.semantic_bucket for row in artifact.rows) == {
        SEMANTIC_BUCKET_ALL_CONSUMED: 25,
        SEMANTIC_BUCKET_HOST_NEEDED: 6,
        SEMANTIC_BUCKET_UNSUPPORTED_IR: 39,
    }
    assert {
        row.datasheet_id: row.pdf_page_reference
        for row in artifact.rows
        if row.treatment == DatasheetSourceTreatment.COMPLETE_PDF.value
    } == AELDARI_COMPLETE_PAGE_REFERENCES
    assert rows_by_id["000000597"].semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert rows_by_id["000000603"].semantic_bucket == SEMANTIC_BUCKET_HOST_NEEDED
    assert rows_by_id["000000571"].semantic_bucket == SEMANTIC_BUCKET_UNSUPPORTED_IR
    assert rows_by_id["000002531"].semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert rows_by_id["000002532"].semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    night_spinner = rows_by_id["000000611"]
    assert night_spinner.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in night_spinner.abilities
    } == {
        "Monofilament Web": (
            "engine_consumed",
            (CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,),
        ),
    }
    rangers = rows_by_id["000000592"]
    assert rangers.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in rangers.abilities
    } == {
        "Path of the Outcast": (
            "engine_consumed",
            (CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,),
        ),
    }
    kharseth = rows_by_id["000004194"]
    assert kharseth.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in kharseth.abilities
    } == {
        "Aethersense (Psychic)": (
            "engine_consumed",
            (CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,),
        ),
        "Fury of the Void (Psychic)": (
            "engine_consumed",
            (CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,),
        ),
    }
    prince_yriel = rows_by_id["000004193"]
    assert prince_yriel.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in prince_yriel.abilities
    } == {
        "Piratical Hero": (
            "engine_consumed",
            (
                CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
                CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
                f"{CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID}:sustained-hits",
            ),
        ),
        "Prince of Corsairs": (
            "engine_consumed",
            (CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,),
        ),
    }
    vypers = rows_by_id["000000605"]
    assert vypers.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in vypers.abilities
    } == {
        "Harassment Fire": (
            "engine_consumed",
            (CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,),
        ),
    }
    starfangs = rows_by_id["000004195"]
    assert starfangs.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in starfangs.abilities
    } == {
        "Hallucinogen Grenades": (
            "engine_consumed",
            (CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID,),
        ),
    }
    skyreavers = rows_by_id["000004196"]
    assert skyreavers.semantic_bucket == SEMANTIC_BUCKET_ALL_CONSUMED
    assert {
        ability.ability_name: (ability.support_stage.value, ability.runtime_consumer_ids)
        for ability in skyreavers.abilities
    } == {
        "Raid and Run": (
            "engine_consumed",
            ("catalog-ir:fight-end-triggered-movement",),
        ),
    }
    assert all(row.semantic_bucket != SEMANTIC_BUCKET_BRIDGE_BLOCKED for row in artifact.rows)
    assert set(dict(artifact.source_artifact_hashes)) == set(SOURCE_ARTIFACT_TABLES)
    for row in artifact.rows:
        for ability in row.abilities:
            if ability.support_stage.value == "engine_consumed":
                assert ability.runtime_consumer_ids
                assert not ability.diagnostic_reasons
                assert ability.semantic_consumers
                assert all(semantic.runtime_consumer_ids for semantic in ability.semantic_consumers)
    psychic_guidance = next(
        ability
        for ability in rows_by_id["000000597"].abilities
        if ability.ability_name == "Psychic Guidance"
    )
    assert psychic_guidance.support_stage.value == "engine_consumed"
    assert psychic_guidance.runtime_consumer_ids == (
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID,
    )
    assert tuple(
        (semantic.semantic_kind, semantic.runtime_consumer_ids)
        for semantic in psychic_guidance.semantic_consumers
    ) == (
        ("set_characteristic", (CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID,)),
        ("modify_dice_roll", (CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,)),
    )
    assert CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID in (
        consumer_id
        for semantic in psychic_guidance.semantic_consumers
        for consumer_id in semantic.runtime_consumer_ids
    )
    inescapable_accuracy = next(
        ability
        for ability in rows_by_id["000000607"].abilities
        if ability.ability_name == "Inescapable Accuracy"
    )
    assert inescapable_accuracy.support_stage.value == "generic_ir_executable"
    assert not inescapable_accuracy.runtime_consumer_ids
    rangers_text = next(
        ability.raw_text
        for ability in rows_by_id["000000592"].abilities
        if ability.ability_name == "Path of the Outcast"
    )
    starweaver_text = next(
        ability.raw_text
        for ability in rows_by_id["000002541"].abilities
        if ability.ability_name == "Rapid Embarkation"
    )
    aspect_token_text = next(
        ability.raw_text
        for ability in rows_by_id["000000593"].abilities
        if ability.ability_name == "Aspect Shrine Token"
    )
    assert 'ends a move within 8"' in rangers_text
    assert "in a turn it disembarked from this TRANSPORT" in starweaver_text
    assert "Designer's Note" not in aspect_token_text
    aspect_token_rows = tuple(
        ability
        for datasheet_id in {
            "000000593",
            "000000594",
            "000000595",
            "000000596",
            "000000600",
            "000000601",
            "000000607",
        }
        for ability in rows_by_id[datasheet_id].abilities
        if ability.ability_name == "Aspect Shrine Token"
    )
    assert len(aspect_token_rows) == 7
    assert all(row.support_stage.value == "engine_consumed" for row in aspect_token_rows)
    assert all(
        row.runtime_consumer_ids == (CATALOG_IR_DICE_RESULT_OVERRIDE_CONSUMER_ID,)
        for row in aspect_token_rows
    )


def test_aeldari_rangers_catalog_geometry_is_source_reviewed() -> None:
    assert len(AELDARI_RANGERS_HEIGHT_OVERRIDES) == 1
    geometry = AELDARI_RANGERS_HEIGHT_OVERRIDES[0]
    assert geometry.datasheet_id == "000000592"
    assert geometry.model_name == "Rangers"
    assert geometry.height == 2.0
    assert geometry.height_source_id == "geometry-review:aeldari:rangers:height"
    assert "Aeldari Designers' Notes" in geometry.height_document_reference
    assert CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID == "descriptor:prebattle:infiltrators"


def test_aeldari_night_spinner_catalog_geometry_is_source_reviewed() -> None:
    assert len(AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES) == 1
    geometry = AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES[0]
    assert geometry.datasheet_id == "000000611"
    assert geometry.model_name == "Night Spinner"
    assert geometry.height == 2.75
    assert geometry.height_source_id == "geometry-review:aeldari:night-spinner:height"
    assert "Warhammer Event Companion" in geometry.height_document_reference


def test_aeldari_semantic_coverage_artifacts_are_current() -> None:
    overlay_pack, tacoma_overlay_pack, release_manifest, coverage_payload = (
        generated_aeldari_datasheet_semantic_coverage()
    )

    assert json.loads(COVERAGE_PATH.read_text(encoding="utf-8")) == coverage_payload
    assert json.loads(OVERLAY_PACK_PATH.read_text(encoding="utf-8")) == (overlay_pack.to_payload())
    assert json.loads(TACOMA_OVERLAY_PACK_PATH.read_text(encoding="utf-8")) == (
        tacoma_overlay_pack.to_payload()
    )
    assert tacoma_overlay_pack.operations[0].source_reference == (
        tacoma_open_2026.FRAME_KEYWORD_ADDITIONS_SOURCE_ID
    )
    assert json.loads(RELEASE_MANIFEST_PATH.read_text(encoding="utf-8")) == (
        release_manifest.to_payload()
    )
    assert json.loads(DESCRIPTION_ARTIFACT_PATH.read_text(encoding="utf-8")) == (
        generated_aeldari_ability_semantic_descriptions()
    )


def test_aeldari_semantic_descriptions_exactly_partition_every_reviewed_ability() -> None:
    coverage = aeldari_datasheet_semantic_coverage()
    descriptions = aeldari_ability_semantic_descriptions()
    descriptions_by_identity = {row.identity: row for row in descriptions.rows}
    expected_by_identity = {
        (datasheet.datasheet_id, ability.source_row_id, ability.ability_id): ability
        for datasheet in coverage.rows
        for ability in datasheet.abilities
    }

    assert len(descriptions.rows) == 145
    assert descriptions_by_identity.keys() == expected_by_identity.keys()
    assert Counter(row.documentation_bucket for row in descriptions.rows) == {
        DOCUMENTATION_BUCKET_SUPPORTED: 60,
        DOCUMENTATION_BUCKET_STILL_NEEDED: 85,
    }
    prose_payload = cast(
        dict[str, Any],
        json.loads(DESCRIPTION_TEXT_PATH.read_text(encoding="utf-8")),
    )
    prose_rows = cast(list[dict[str, Any]], prose_payload["descriptions"])
    assert prose_payload["schema_version"] == "2"
    assert len(prose_rows) == 145
    assert all(
        set(row) == {"ability_id", "description", "evidence_sha256"}
        and len(cast(str, row["evidence_sha256"])) == 64
        for row in prose_rows
    )
    support_markdown = faction_support_markdown_files()["aeldari.md"].split(
        "## Datasheet / Unit Support", 1
    )[1]
    for description in descriptions.rows:
        assert support_markdown.count(f"`{description.ability_id}`") == 1
        assert description.description in support_markdown


@pytest.mark.parametrize("evidence_change", ["source_hash", "support_stage", "runtime_consumer"])
def test_aeldari_description_generation_rejects_changed_coverage_with_stale_prose_fingerprint(
    evidence_change: str,
) -> None:
    coverage = aeldari_datasheet_semantic_coverage()
    datasheet = coverage.rows[0]
    ability = datasheet.abilities[0]
    if evidence_change == "source_hash":
        changed_ability = replace(ability, raw_text_sha256="0" * 64)
    elif evidence_change == "support_stage":
        changed_ability = replace(
            ability,
            support_stage=AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE,
        )
    else:
        changed_ability = replace(
            ability,
            runtime_consumer_ids=(*ability.runtime_consumer_ids, "test:changed-consumer"),
        )
    changed_datasheet = replace(
        datasheet,
        abilities=(changed_ability, *datasheet.abilities[1:]),
    )
    changed_coverage = replace(
        coverage,
        rows=(changed_datasheet, *coverage.rows[1:]),
    )

    with pytest.raises(ValueError, match="human prose evidence fingerprint drifted"):
        generated_aeldari_ability_semantic_descriptions(coverage=changed_coverage)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("raw_text_sha256", "0" * 64),
        ("semantic_consumers", []),
        ("runtime_consumer_ids", []),
        ("diagnostic_reasons", ["mutated-diagnostic"]),
    ],
)
def test_aeldari_semantic_description_loader_rejects_exact_evidence_drift(
    tmp_path: Path,
    field_name: str,
    replacement: object,
) -> None:
    payload = _mutable_aeldari_description_payload()
    descriptions = cast(list[dict[str, Any]], payload["descriptions"])
    descriptions[0][field_name] = replacement
    description_path = _write_aeldari_description_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="prose drifted from exact ability evidence"):
        load_aeldari_ability_semantic_descriptions(
            description_path=description_path,
            coverage=aeldari_datasheet_semantic_coverage(),
        )


def test_aeldari_semantic_description_loader_rejects_support_stage_drift(
    tmp_path: Path,
) -> None:
    payload = _mutable_aeldari_description_payload()
    descriptions = cast(list[dict[str, Any]], payload["descriptions"])
    descriptions[0]["support_stage"] = "generic_ir_executable"
    descriptions[0]["documentation_bucket"] = DOCUMENTATION_BUCKET_STILL_NEEDED
    description_path = _write_aeldari_description_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="prose drifted from exact ability evidence"):
        load_aeldari_ability_semantic_descriptions(
            description_path=description_path,
            coverage=aeldari_datasheet_semantic_coverage(),
        )


def test_aeldari_semantic_description_loader_rejects_ability_partition_drift(
    tmp_path: Path,
) -> None:
    payload = _mutable_aeldari_description_payload()
    descriptions = cast(list[dict[str, Any]], payload["descriptions"])
    descriptions.pop()
    payload["exact_ability_count"] = len(descriptions)
    description_path = _write_aeldari_description_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="exactly partition reviewed abilities"):
        load_aeldari_ability_semantic_descriptions(
            description_path=description_path,
            coverage=aeldari_datasheet_semantic_coverage(),
        )


def test_aeldari_catalog_blocker_claim_requires_explicit_accepted_support_states() -> None:
    support_rows = tuple(row for row in datasheet_support_rows() if row.faction_id == "aeldari")
    rows_by_id: dict[str, DatasheetSupportRow] = {row.datasheet_id: row for row in support_rows}
    autarch = rows_by_id["000000577"]
    rows_by_id[autarch.datasheet_id] = replace(
        autarch,
        overall="Partial",
        model_geometry_status="Partial",
        notes="Exact model geometry remains under review.",
    )

    markdown = "\n".join(
        aeldari_datasheet_support_markdown(support_rows_by_datasheet_id=rows_by_id)
    )
    autarch_row = next(line for line in markdown.splitlines() if line.startswith("| Autarch (`"))

    assert "No known catalog blocker." not in autarch_row
    assert "overall `Partial`; models/geometry `Partial`" in autarch_row
    assert "Exact model geometry remains under review." in autarch_row


def test_aeldari_aspect_shrine_token_wargear_entitlement_rows_are_exact() -> None:
    artifact = WahapediaJsonArtifact.from_payload(
        json.loads((SOURCE_JSON_DIR / "Datasheets_options.json").read_text(encoding="utf-8"))
    )
    expected_hash_by_row_id = {
        "000000593:4": "3adc13093b65b07e484909eaef6c98ae7fde0043362f97c449c6a9b301c99877",
        "000000594:3": "9711b7c40d10a5d05749d1857e3943545debe9f5a573a0e0cf379a11776b1a1e",
        "000000595:2": "330be3d76f7b8dab17a5a260f6a461d844fc3cba24b92def1cc5ce5452ec0770",
        "000000596:2": "4bc4a8399f02deab4301de8a9708c96037519a8ee32234a26aa787f24a12edd1",
        "000000600:2": "333f7ac8c0c369bad3db82b1c35bbebb76fc5135c8de98d2555785d0dc36af82",
        "000000601:2": "fbeba86bc5545c70693048e6688220fa94d2d54d135f6a32dd51897efe925d62",
        "000000607:2": "5f3e515ecb9a803f578928cead69c96688b3073b06976da216410f0affa14fb5",
    }
    rows = {
        row.source_row_id: row
        for row in artifact.rows
        if "Aspect Shrine token" in row.runtime_fields_payload().get("description", "")
    }

    assert set(rows) == set(expected_hash_by_row_id)
    assert {row_id: source_row_hash(row) for row_id, row in rows.items()} == expected_hash_by_row_id
    assert {row.runtime_fields_payload()["description"] for row in rows.values()} == {
        "For every 5 models in this unit, it can have 1 Aspect Shrine token."
    }


@pytest.mark.parametrize(
    ("support_stage", "field_name", "replacement", "message"),
    [
        (
            "engine_consumed",
            "runtime_consumer_ids",
            [],
            "semantic consumers must be present in runtime consumers",
        ),
        (
            "engine_consumed",
            "diagnostic_reasons",
            ["unsupported_language"],
            "must not contain diagnostics",
        ),
        (
            "generic_ir_executable",
            "diagnostic_reasons",
            ["unsupported_language"],
            "must not contain blocking diagnostics",
        ),
        (
            "ir_compiled_unsupported",
            "diagnostic_reasons",
            [],
            "requires explicit diagnostic evidence",
        ),
    ],
)
def test_aeldari_semantic_loader_rejects_inconsistent_runtime_evidence(
    tmp_path: Path,
    support_stage: str,
    field_name: str,
    replacement: object,
    message: str,
) -> None:
    payload = _mutable_aeldari_coverage_payload()
    ability = _first_ability_payload_for_stage(payload, support_stage)
    ability[field_name] = replacement
    coverage_path = _write_aeldari_coverage_payload(tmp_path, payload)

    with pytest.raises(ValueError, match=message):
        load_aeldari_datasheet_semantic_coverage(coverage_path=coverage_path)


def test_aeldari_semantic_loader_rejects_partially_consumed_engine_ability(
    tmp_path: Path,
) -> None:
    payload = _mutable_aeldari_coverage_payload()
    ability = _first_ability_payload_for_stage(payload, "engine_consumed")
    semantic_consumers = cast(list[dict[str, Any]], ability["semantic_consumers"])
    semantic_consumers[0]["runtime_consumer_ids"] = []
    coverage_path = _write_aeldari_coverage_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="requires every semantic"):
        load_aeldari_datasheet_semantic_coverage(coverage_path=coverage_path)


def test_aeldari_semantic_loader_rejects_omitted_effect_and_false_promotion(
    tmp_path: Path,
) -> None:
    payload = _mutable_aeldari_coverage_payload()
    datasheets = cast(list[dict[str, Any]], payload["datasheets"])
    wraithguard = next(
        datasheet for datasheet in datasheets if datasheet["datasheet_id"] == "000000597"
    )
    abilities = cast(list[dict[str, Any]], wraithguard["abilities"])
    psychic_guidance = next(
        ability for ability in abilities if ability["ability_name"] == "Psychic Guidance"
    )
    semantic_consumers = cast(list[dict[str, Any]], psychic_guidance["semantic_consumers"])
    psychic_guidance["semantic_consumers"] = [
        semantic
        for semantic in semantic_consumers
        if semantic["semantic_kind"] != "modify_dice_roll"
    ]
    psychic_guidance["support_stage"] = "engine_consumed"
    wraithguard["semantic_bucket"] = SEMANTIC_BUCKET_ALL_CONSUMED
    payload["semantic_bucket_counts"] = {
        SEMANTIC_BUCKET_ALL_CONSUMED: 3,
        SEMANTIC_BUCKET_HOST_NEEDED: 4,
        SEMANTIC_BUCKET_UNSUPPORTED_IR: 63,
    }
    coverage_path = _write_aeldari_coverage_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="effect inventory drifted"):
        load_aeldari_datasheet_semantic_coverage(coverage_path=coverage_path)


@pytest.mark.parametrize("table_name", SOURCE_ARTIFACT_TABLES)
def test_aeldari_semantic_loader_rejects_each_source_artifact_hash_mutation(
    tmp_path: Path,
    table_name: str,
) -> None:
    payload = _mutable_aeldari_coverage_payload()
    source_hashes = cast(dict[str, str], payload["source_artifact_hashes"])
    source_hashes[table_name] = "0" * 64
    coverage_path = _write_aeldari_coverage_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="source artifact hashes drifted"):
        load_aeldari_datasheet_semantic_coverage(coverage_path=coverage_path)


def test_aeldari_semantic_loader_rejects_unconsumed_evidence_fields(
    tmp_path: Path,
) -> None:
    payload = _mutable_aeldari_coverage_payload()
    ability = _first_ability_payload_for_stage(payload, "engine_consumed")
    ability["rule_ir_payload_sha256"] = "0" * 64
    coverage_path = _write_aeldari_coverage_payload(tmp_path, payload)

    with pytest.raises(ValueError, match=r"unexpected=.*rule_ir_payload_sha256"):
        load_aeldari_datasheet_semantic_coverage(coverage_path=coverage_path)


def _mutable_aeldari_coverage_payload() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(COVERAGE_PATH.read_text(encoding="utf-8")),
    )


def _first_ability_payload_for_stage(
    payload: dict[str, Any],
    support_stage: str,
) -> dict[str, Any]:
    datasheets = cast(list[dict[str, Any]], payload["datasheets"])
    for datasheet in datasheets:
        abilities = cast(list[dict[str, Any]], datasheet["abilities"])
        for ability in abilities:
            if ability["support_stage"] == support_stage:
                return ability
    raise AssertionError(f"Missing exact ability support stage: {support_stage}.")


def _write_aeldari_coverage_payload(
    tmp_path: Path,
    payload: dict[str, Any],
) -> Path:
    coverage_path = tmp_path / "aeldari-datasheet-semantic-coverage.json"
    coverage_path.write_text(json.dumps(payload), encoding="utf-8")
    return coverage_path


def _mutable_aeldari_description_payload() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(DESCRIPTION_ARTIFACT_PATH.read_text(encoding="utf-8")),
    )


def _write_aeldari_description_payload(
    tmp_path: Path,
    payload: dict[str, Any],
) -> Path:
    description_path = tmp_path / "aeldari-ability-semantic-descriptions.json"
    description_path.write_text(json.dumps(payload), encoding="utf-8")
    return description_path
