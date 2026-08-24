from __future__ import annotations

import hashlib
import json
import math
import zipfile
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from tests.support.wahapedia_source_fixtures import wahapedia_source_artifacts
from tools.faction_pack_datasheet_review import (
    DatasheetSourceTreatment,
    faction_pack_datasheet_review,
)
from tools.generate_ability_support_matrix import (
    ABILITY_SUPPORT_DATASHEET_IDS,
    MAULERFIEND_DATASHEET_IDS,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_datasheet_keyword_lexicon import (
    build_keyword_sequence_parts,
    load_wahapedia_artifact,
)
from tools.wahapedia_csv_to_json import build_wahapedia_json_artifacts
from tools.wahapedia_fetch import (
    WahapediaFetchSource,
    discover_wahapedia_sources_from_export_specs,
    fetch_wahapedia_sources,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import DamagedEffectKind
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.army_points import calculate_mfm_army_points
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.html_sanitizer import (
    SourceHtmlSanitizationError,
    SourceHtmlSanitizationReport,
    SourceHtmlSanitizationReportPayload,
    contains_html_markup,
    sanitize_source_html,
)
from warhammer40k_core.rules.source_catalog import (
    SourceArtifactHash,
    SourceCatalogError,
    SourceFileChecksum,
    SourcePackageManifest,
    SourcePackageManifestPayload,
)
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayError,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_maulerfiend_datasheet_overlay_2026_07 as maulerfiend_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import MAULERFIEND_HEIGHT_OVERRIDES
from warhammer40k_core.rules.wahapedia_schema import (
    EditionSourceConfig,
    EditionSourceConfigPayload,
    NormalizedSourceRow,
    SourceTextFieldPayload,
    WahapediaArtifactBuildReport,
    WahapediaCsvRow,
    WahapediaCsvTable,
    WahapediaCsvTablePayload,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
    WahapediaSchemaError,
    WahapediaSourceSnapshot,
    WahapediaSourceSnapshotPayload,
    WahapediaTableSchema,
    build_wahapedia_artifact_report,
    schema_for_table,
)

ROOT = Path(__file__).resolve().parents[2]
WAHAPEDIA_2026_06_14_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)


def test_phase17a_csv_normalization_strips_html_and_preserves_structured_text() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    row = artifact.rows[0]
    text_fields = {text_field.column_name: text_field for text_field in row.text_fields}
    name = text_fields["name"]
    description = text_fields["description"]

    assert row.source_table == "Abilities"
    assert row.source_row_id == "ability-1:SM"
    assert row.source_package_id == _package_id()
    assert row.stable_source_id().endswith(":Abilities:ability-1:SM")
    assert row.runtime_fields_payload()["name"] == "Angels' Fury"
    assert name.sanitized_text == "Angels' Fury"
    assert name.normalized_text == "Angels' Fury"
    assert description.sanitized_text == (
        "roll d6 + 2 attacks within 12 inches.\n- feel no pain applies.\ndesigner note"
    )
    assert description.normalized_text == (
        'roll D6+2 attacks within 12".\n- Feel No Pain applies.\ndesigner note'
    )
    assert description.parsed_tokens.dice_expressions[0].span.text == "D6+2"
    assert description.parsed_tokens.distance_predicates[0].distance_inches == 12.0
    assert description.parsed_tokens.keywords[0].keyword == "Feel No Pain"
    assert "li" in description.html_sanitization.converted_tags
    assert description.html_sanitization.embedded_links == ("https://example.invalid/rule",)
    assert name.source_text_id.endswith(":Abilities:ability-1:SM:name")
    assert description.source_text_id.endswith(":Abilities:ability-1:SM:description")


def test_phase17a_generated_json_is_deterministic_and_round_trips() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    second_artifact = _abilities_artifact(_abilities_csv())
    payload = cast(
        WahapediaJsonArtifactPayload,
        json.loads(artifact.to_json_bytes()),
    )

    assert artifact.to_json_bytes() == second_artifact.to_json_bytes()
    assert WahapediaJsonArtifact.from_payload(payload).to_payload() == artifact.to_payload()

    payload["artifact_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(WahapediaSchemaError, match="artifact_hash"):
        WahapediaJsonArtifact.from_payload(payload)


def test_phase17a_runtime_bound_artifact_fields_contain_no_raw_html() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    raw_blob = artifact.to_json_bytes().decode()

    assert "<p>" in raw_blob
    for row in artifact.rows:
        for value in row.runtime_fields_payload().values():
            assert not contains_html_markup(value)
        for text_field in row.text_fields:
            assert not contains_html_markup(text_field.sanitized_text)
            assert not contains_html_markup(text_field.normalized_text)


def test_phase17a_source_manifest_hash_changes_on_source_or_artifact_drift() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    source_file = SourceFileChecksum(
        path="Abilities.csv",
        checksum_sha256=hashlib.sha256(_abilities_csv().encode()).hexdigest(),
        size_bytes=len(_abilities_csv().encode()),
    )
    drifted_source_file = SourceFileChecksum(
        path="Abilities.csv",
        checksum_sha256=hashlib.sha256(b"drifted").hexdigest(),
        size_bytes=len(b"drifted"),
    )
    snapshot = WahapediaSourceSnapshot(
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export:2026-06-01",
        source_edition="warhammer-40000-11th",
        source_files=(source_file,),
    )
    drifted_snapshot = WahapediaSourceSnapshot(
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export:2026-06-01",
        source_edition="warhammer-40000-11th",
        source_files=(drifted_source_file,),
    )
    manifest = snapshot.manifest(artifacts=(artifact.source_artifact_hash(),))
    drifted_manifest = drifted_snapshot.manifest(artifacts=(artifact.source_artifact_hash(),))
    payload = cast(
        SourcePackageManifestPayload,
        json.loads(json.dumps(manifest.to_payload(), sort_keys=True)),
    )

    assert manifest.package_hash() != drifted_manifest.package_hash()
    assert SourcePackageManifest.from_payload(payload).to_payload() == manifest.to_payload()

    payload["source_files"][0]["checksum_sha256"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(SourceCatalogError, match="package_hash"):
        SourcePackageManifest.from_payload(payload)


def test_phase17a_every_normalized_row_has_required_provenance() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    row_payload = artifact.to_payload()["rows"][0]

    assert row_payload["source_package_id"] == _package_id().to_payload()
    assert row_payload["source_table"] == "Abilities"
    assert row_payload["source_row_id"] == "ability-1:SM"
    assert row_payload["source_row_number"] == 2


def test_phase17a_failure_report_groups_malformed_rows_by_reason() -> None:
    table = WahapediaCsvTable.from_csv_text(
        table_name="Abilities",
        csv_text=(
            "id,faction_id,name,description\n"
            ',SM,Missing ID,"Roll D6."\n'
            'duplicate,SM,First,"Roll D6."\n'
            'duplicate,SM,Second,"Roll D3."\n'
            'empty,SM,Empty," "\n'
        ),
    )
    report = build_wahapedia_artifact_report(
        source_package_id=_package_id(),
        table=table,
        schema=schema_for_table("Abilities"),
    )
    grouped = report.diagnostics_by_reason()

    assert set(grouped) == {
        "duplicate_source_row_id",
        "malformed_csv_row",
        "missing_source_row_id",
    }
    assert len(grouped["duplicate_source_row_id"]) == 1
    assert len(grouped["missing_source_row_id"]) == 1
    assert len(grouped["malformed_csv_row"]) == 1
    assert len(report.rows) == 1
    with pytest.raises(WahapediaSchemaError, match="diagnostics"):
        WahapediaJsonArtifact.from_csv_table(
            source_package_id=_package_id(),
            table=table,
        )


def test_phase17a_failure_report_groups_missing_required_columns() -> None:
    table = WahapediaCsvTable.from_csv_text(
        table_name="Abilities",
        csv_text='id,faction_id,name\nability-1,SM,"Missing description"\n',
    )
    report = build_wahapedia_artifact_report(
        source_package_id=_package_id(),
        table=table,
    )

    assert set(report.diagnostics_by_reason()) == {"missing_column"}
    with pytest.raises(WahapediaSchemaError, match="Unsupported Wahapedia source table"):
        schema_for_table("Unsupported")


def test_phase17a_html_sanitizer_handles_blocks_tables_scripts_and_stale_payloads() -> None:
    report = sanitize_source_html(
        source_id="html:edge",
        raw_html=(
            "<section>Alpha<br/>Beta<table><tr><th>Head</th><td>Cell</td></tr></table>"
            "<script>hidden</script><custom>Shown</custom><a>No href</a></section>"
        ),
    )
    payload = cast(
        SourceHtmlSanitizationReportPayload,
        json.loads(json.dumps(report.to_payload(), sort_keys=True)),
    )

    assert "hidden" not in report.sanitized_text
    assert report.sanitized_text == "Alpha\nBeta\nHead | Cell |\nShownNo href"
    assert {"br", "section", "table", "tr", "th", "td", "a"} & set(report.converted_tags)
    assert {"script", "custom"} <= set(report.stripped_tags)
    assert SourceHtmlSanitizationReport.from_payload(payload).to_payload() == report.to_payload()

    payload["sanitized_text"] = "drifted"
    with pytest.raises(SourceHtmlSanitizationError, match="stale"):
        SourceHtmlSanitizationReport.from_payload(payload)
    with pytest.raises(SourceHtmlSanitizationError):
        sanitize_source_html(source_id="bad", raw_html=cast(str, 1))
    with pytest.raises(SourceHtmlSanitizationError):
        contains_html_markup(cast(str, 1))
    with pytest.raises(SourceHtmlSanitizationError):
        SourceHtmlSanitizationReport(
            source_id=" ",
            raw_html="x",
            sanitized_text="x",
            converted_tags=(),
        )
    with pytest.raises(SourceHtmlSanitizationError):
        SourceHtmlSanitizationReport(
            source_id="html:bad-tag",
            raw_html="x",
            sanitized_text="x",
            converted_tags=(" ",),
        )


def test_phase17a_csv_table_payloads_and_shape_failures_are_explicit() -> None:
    table = WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=_abilities_csv())
    payload = cast(
        WahapediaCsvTablePayload,
        json.loads(json.dumps(table.to_payload(), sort_keys=True)),
    )

    assert WahapediaCsvTable.from_payload(payload).to_payload() == table.to_payload()
    with pytest.raises(WahapediaSchemaError, match="table_name"):
        WahapediaCsvTable.from_csv_text(table_name=" ", csv_text=_abilities_csv())
    with pytest.raises(WahapediaSchemaError, match="csv_text"):
        WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=cast(str, 1))
    with pytest.raises(WahapediaSchemaError, match="header"):
        WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text="")
    with pytest.raises(WahapediaSchemaError, match="duplicates"):
        WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text="id,id\n1,2\n")
    with pytest.raises(WahapediaSchemaError, match="unterminated multiline field"):
        WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text="id,name\n1\n")
    with pytest.raises(WahapediaSchemaError, match="row_number"):
        WahapediaCsvRow(row_number=1, values=(("id", "x"),))
    with pytest.raises(WahapediaSchemaError, match="duplicate"):
        WahapediaCsvRow(row_number=2, values=(("id", "x"), ("id", "y")))


def test_phase17a_source_file_checksums_use_checked_paths(tmp_path: Path) -> None:
    source_path = tmp_path / "Abilities.csv"
    source_path.write_text(_abilities_csv(), encoding="utf-8")
    checksum = SourceFileChecksum.from_path(root=tmp_path, path=source_path)
    artifact_hash = SourceArtifactHash(
        artifact_name="Abilities.json",
        artifact_hash=hashlib.sha256(b"artifact").hexdigest(),
    )

    assert checksum.path == "Abilities.csv"
    assert checksum.stable_identity().startswith("source-file:Abilities.csv:")
    assert SourceFileChecksum.from_payload(checksum.to_payload()) == checksum
    assert SourceArtifactHash.from_payload(artifact_hash.to_payload()) == artifact_hash

    with pytest.raises(SourceCatalogError, match="inside root"):
        SourceFileChecksum.from_path(root=tmp_path, path=tmp_path.parent / "outside.csv")
    with pytest.raises(SourceCatalogError, match="Path"):
        SourceFileChecksum.from_path(root=cast(Path, "bad"), path=source_path)
    with pytest.raises(SourceCatalogError, match="SHA-256"):
        SourceFileChecksum(path="bad.csv", checksum_sha256="ABC", size_bytes=1)
    with pytest.raises(SourceCatalogError, match="negative"):
        SourceFileChecksum(
            path="bad.csv",
            checksum_sha256=hashlib.sha256(b"bad").hexdigest(),
            size_bytes=-1,
        )
    with pytest.raises(SourceCatalogError, match="unique"):
        SourcePackageManifest(
            package_id=_package_id(),
            catalog_version=_catalog_version(),
            upstream_identity="wahapedia-export",
            source_edition="warhammer-40000-11th",
            source_files=(checksum, checksum),
        )
    with pytest.raises(SourceCatalogError, match="unique"):
        SourcePackageManifest(
            package_id=_package_id(),
            catalog_version=_catalog_version(),
            upstream_identity="wahapedia-export",
            source_edition="warhammer-40000-11th",
            source_files=(checksum,),
            artifacts=(artifact_hash, artifact_hash),
        )


def test_phase17a_wahapedia_fetch_rejects_escape_paths_before_download(tmp_path: Path) -> None:
    output_dir = tmp_path / "downloads"
    traversal_target = tmp_path / "outside.csv"
    absolute_target = tmp_path / "absolute.csv"

    with pytest.raises(ValueError, match="relative and must not contain"):
        fetch_wahapedia_sources(
            sources=(
                WahapediaFetchSource(
                    url="https://example.invalid/Abilities.csv",
                    relative_path="../outside.csv",
                ),
            ),
            output_dir=output_dir,
            package_id=_package_id(),
            catalog_version=_catalog_version(),
            upstream_identity="wahapedia-export",
            source_edition="warhammer-40000-11th",
        )
    assert not traversal_target.exists()

    with pytest.raises(ValueError, match="relative"):
        fetch_wahapedia_sources(
            sources=(
                WahapediaFetchSource(
                    url="https://example.invalid/Abilities.csv",
                    relative_path=str(absolute_target),
                ),
            ),
            output_dir=output_dir,
            package_id=_package_id(),
            catalog_version=_catalog_version(),
            upstream_identity="wahapedia-export",
            source_edition="warhammer-40000-11th",
        )
    assert not absolute_target.exists()


def test_phase17a_generated_artifact_uses_raw_source_file_checksum(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    raw_csv = (
        b'\xef\xbb\xbfid,faction_id,name,description\r\nability-1,SM,Angels Fury,"Roll D6."\r\n'
    )
    csv_path = input_dir / "Abilities.csv"
    csv_path.write_bytes(raw_csv)
    decoded_csv_text = csv_path.read_text(encoding="utf-8-sig")

    manifest = build_wahapedia_json_artifacts(
        input_dir=input_dir,
        output_dir=output_dir,
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export",
        source_edition="warhammer-40000-11th",
    )
    artifact_payload = cast(
        WahapediaJsonArtifactPayload,
        json.loads((output_dir / "Abilities.json").read_bytes()),
    )
    raw_checksum = hashlib.sha256(raw_csv).hexdigest()

    assert hashlib.sha256(decoded_csv_text.encode()).hexdigest() != raw_checksum
    assert not csv_path.exists()
    assert manifest.source_files[0].checksum_sha256 == raw_checksum
    assert artifact_payload["source_checksum_sha256"] == raw_checksum
    assert WahapediaJsonArtifact.from_payload(artifact_payload).source_checksum_sha256 == (
        raw_checksum
    )


def test_phase17a_tooling_parses_wahapedia_pipe_delimited_csv_with_bom(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    raw_csv = b"\xef\xbb\xbfid|faction_id|name|description\r\nability-1|SM|Angels Fury|Roll D6.\r\n"
    (input_dir / "Abilities.csv").write_bytes(raw_csv)

    manifest = build_wahapedia_json_artifacts(
        input_dir=input_dir,
        output_dir=output_dir,
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export",
        source_edition="warhammer-40000-11th",
        csv_delimiter="|",
    )
    artifact_payload = cast(
        WahapediaJsonArtifactPayload,
        json.loads((output_dir / "Abilities.json").read_bytes()),
    )

    assert manifest.source_files[0].checksum_sha256 == hashlib.sha256(raw_csv).hexdigest()
    assert artifact_payload["rows"][0]["fields"]["name"] == "Angels Fury"
    assert not (input_dir / "Abilities.csv").exists()


def test_phase17a_tooling_can_keep_input_csvs_for_local_debugging(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    raw_csv = b"id|faction_id|name|description\r\nability-1|SM|Angels Fury|Roll D6.\r\n"
    csv_path = input_dir / "Abilities.csv"
    csv_path.write_bytes(raw_csv)

    build_wahapedia_json_artifacts(
        input_dir=input_dir,
        output_dir=output_dir,
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export",
        source_edition="warhammer-40000-11th",
        csv_delimiter="|",
        keep_input_csvs=True,
    )

    assert csv_path.read_bytes() == raw_csv


def test_phase17a_tooling_strips_wahapedia_trailing_empty_export_column(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    raw_csv = b"id|faction_id|name|description|\r\nability-1|SM|Angels Fury|Roll D6.|\r\n"
    (input_dir / "Abilities.csv").write_bytes(raw_csv)

    build_wahapedia_json_artifacts(
        input_dir=input_dir,
        output_dir=output_dir,
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export",
        source_edition="warhammer-40000-11th",
        csv_delimiter="|",
    )
    artifact_payload = cast(
        WahapediaJsonArtifactPayload,
        json.loads((output_dir / "Abilities.json").read_bytes()),
    )

    assert artifact_payload["rows"][0]["fields"] == {
        "description": "Roll D6.",
        "faction_id": "SM",
        "id": "ability-1",
        "name": "Angels Fury",
    }


def test_phase17a_tooling_repairs_wahapedia_unquoted_multiline_fields() -> None:
    table = WahapediaCsvTable.from_csv_text(
        table_name="Stratagems",
        csv_text=(
            "faction_id|name|id|type|cp_cost|legend|turn|phase|detachment|detachment_id|"
            "description|\n"
            "AdM|THREAT-COGITATION TARGETERS|strat-1|Wargear Stratagem|1|"
            "Supplementary routines identify targets\n"
            "rapid elimination.|Your turn|Shooting phase|Eradication Cohort|det-1|"
            "<b>WHEN:</b> Your Shooting phase.|\n"
        ),
        delimiter="|",
    )
    artifact = WahapediaJsonArtifact.from_csv_table(
        source_package_id=_package_id(),
        table=table,
    )
    legend = next(field for field in artifact.rows[0].text_fields if field.column_name == "legend")

    assert artifact.rows[0].source_row_id == "strat-1"
    assert legend.raw_text == "Supplementary routines identify targets\nrapid elimination."


def test_phase17a_abilities_blank_faction_id_uses_global_source_identity() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\nability-core,,Firing Deck,"Roll D6."\n'
    )

    assert artifact.rows[0].source_row_id == "ability-core:global"


def test_phase17a_datasheet_keyword_identity_preserves_model_scope_and_blank_tokens() -> None:
    table = WahapediaCsvTable.from_csv_text(
        table_name="Datasheets_keywords",
        csv_text=(
            "datasheet_id,keyword,model,is_faction_keyword\n"
            "ds-1,Fly,MODEL A,false\n"
            "ds-1,Fly,MODEL B,false\n"
            "ds-2,,,true\n"
        ),
    )
    artifact = WahapediaJsonArtifact.from_csv_table(
        source_package_id=_package_id(),
        table=table,
    )

    assert [row.source_row_id for row in artifact.rows] == [
        "ds-1:Fly:MODEL A:false:2",
        "ds-1:Fly:MODEL B:false:3",
        "ds-2:blank-keyword:global:true:4",
    ]
    assert artifact.rows[2].text_fields == ()


def test_phase17a_datasheet_keyword_lexicon_matches_source_snapshot() -> None:
    datasheet_keywords_artifact = load_wahapedia_artifact(
        path=WAHAPEDIA_2026_06_14_JSON_DIR / "Datasheets_keywords.json",
        expected_table="Datasheets_keywords",
    )
    factions_artifact = load_wahapedia_artifact(
        path=WAHAPEDIA_2026_06_14_JSON_DIR / "Factions.json",
        expected_table="Factions",
    )
    expected_parts = build_keyword_sequence_parts(
        datasheet_keywords_artifact=datasheet_keywords_artifact,
        factions_artifact=factions_artifact,
    )

    assert (
        datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        == expected_parts
    )
    assert "KHORNE" in expected_parts
    assert "LEGIONES DAEMONICA" in expected_parts
    assert "INFANTRY" in expected_parts
    assert "SPACE MARINES" in expected_parts
    assert "CHAOS DAEMONS" in expected_parts


def test_phase17a_maulerfiend_counted_replacement_is_generic_across_source_variants() -> None:
    variant_details = {
        ("chaos-space-marines", "000000968"): (
            "CSM",
            "000000968:magma-cutters",
            DatasheetSourceTreatment.UNCHANGED_PREDECESSOR,
        ),
        ("thousand-sons", "000001029"): (
            "TS",
            "000001029:magma-cutter",
            DatasheetSourceTreatment.RULES_UPDATE,
        ),
        ("world-eaters", "000002639"): (
            "WE",
            "000002639:magma-cutter",
            DatasheetSourceTreatment.RULES_UPDATE,
        ),
        ("emperors-children", "000004091"): (
            "EC",
            "000004091:magma-cutters",
            DatasheetSourceTreatment.UNCHANGED_PREDECESSOR,
        ),
    }
    variant_catalog_expectations = {
        "000000968": {
            "faction_keyword": "HERETIC ASTARTES",
            "movement": 10,
            "keywords": ("CHAOS", "DAEMON", "MAULERFIEND", "VEHICLE", "WALKER"),
            "abilities": ("Dark Pacts", "Deadly Demise", "Siege Crawler"),
            "magma_name": "Magma cutters",
            "magma_skill": 3,
            "magma_keywords": ("Melta",),
            "magma_abilities": ("melta:2",),
            "fists_attacks": 6,
            "height_source_id": "geometry-review:chaos-space-marines:maulerfiend:height",
            "footprint_source_id": (
                "gw-11e-warhammer-event-companion-v1-1-2026-07:"
                "base-size:page-69-chaos-space-marines-maulerfiend"
            ),
        },
        "000001029": {
            "faction_keyword": "THOUSAND SONS",
            "movement": 10,
            "keywords": (
                "CHAOS",
                "DAEMON",
                "MAULERFIEND",
                "TZEENTCH",
                "VEHICLE",
                "WALKER",
            ),
            "abilities": ("Deadly Demise", "Snarling Protector"),
            "magma_name": "Magma cutter",
            "magma_skill": 3,
            "magma_keywords": ("Melta",),
            "magma_abilities": ("melta:2",),
            "fists_attacks": 6,
            "height_source_id": "geometry-review:thousand-sons:maulerfiend:height",
            "footprint_source_id": (
                "gw-11e-warhammer-event-companion-v1-1-2026-07:"
                "base-size:page-90-thousand-sons-maulerfiend"
            ),
        },
        "000002639": {
            "faction_keyword": "WORLD EATERS",
            "movement": 12,
            "keywords": (
                "CHAOS",
                "DAEMON",
                "KHORNE",
                "MAULERFIEND",
                "VEHICLE",
                "WALKER",
            ),
            "abilities": (
                "Blessings of Khorne",
                "Deadly Demise",
                "Savage Exaltation",
                "The Scent of Blood",
            ),
            "magma_name": "Magma cutter",
            "magma_skill": 4,
            "magma_keywords": ("Melta", "Rapid Fire"),
            "magma_abilities": ("melta:2", "rapid-fire:1"),
            "fists_attacks": 8,
            "height_source_id": "geometry-review:world-eaters:maulerfiend:height",
            "footprint_source_id": (
                "gw-11e-warhammer-event-companion-v1-1-2026-07:"
                "base-size:page-93-world-eaters-maulerfiend"
            ),
        },
        "000004091": {
            "faction_keyword": "EMPEROR'S CHILDREN",
            "movement": 10,
            "keywords": (
                "CHAOS",
                "DAEMON",
                "MAULERFIEND",
                "SLAANESH",
                "VEHICLE",
                "WALKER",
            ),
            "abilities": ("Deadly Demise", "Glutton for Punishment", "Thrill Seekers"),
            "magma_name": "Magma cutters",
            "magma_skill": 3,
            "magma_keywords": ("Melta",),
            "magma_abilities": ("melta:2",),
            "fists_attacks": 6,
            "height_source_id": "geometry-review:emperors-children:maulerfiend:height",
            "footprint_source_id": (
                "gw-11e-warhammer-event-companion-v1-1-2026-07:"
                "base-size:page-74-emperors-children-maulerfiend"
            ),
        },
    }
    datasheet_ids = tuple(datasheet_id for _, datasheet_id in variant_details)
    source_artifacts = apply_source_release_overlays(
        source_artifacts=wahapedia_source_artifacts(),
        release_manifest=maulerfiend_overlay.source_release_manifest(),
        overlay_packs=(maulerfiend_overlay.overlay_pack(),),
    )
    source_datasheets = next(
        artifact for artifact in source_artifacts if artifact.source_table == "Datasheets"
    )
    source_identity_by_id: dict[str, tuple[str, str]] = {}
    for row in source_datasheets.rows:
        if row.source_row_id in datasheet_ids:
            fields = row.runtime_fields_payload()
            source_identity_by_id[row.source_row_id] = (fields["name"], fields["faction_id"])
    assert source_identity_by_id == {
        datasheet_id: ("Maulerfiend", source_faction_id)
        for (_, datasheet_id), (source_faction_id, _, _) in variant_details.items()
    }

    for (faction_id, datasheet_id), (_, _, expected_treatment) in variant_details.items():
        review_rows = tuple(
            row
            for row in faction_pack_datasheet_review(faction_id).rows
            if row.datasheet_id == datasheet_id
        )
        assert len(review_rows) == 1
        assert review_rows[0].datasheet_name == "Maulerfiend"
        assert review_rows[0].treatment is expected_treatment

    death_guard_review = faction_pack_datasheet_review("death-guard")
    assert not any(row.datasheet_name == "Maulerfiend" for row in death_guard_review.rows)
    assert not any(
        row.runtime_fields_payload()["faction_id"] == death_guard_review.source_faction_id
        and row.runtime_fields_payload()["name"] == "Maulerfiend"
        for row in source_datasheets.rows
    )

    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=source_artifacts,
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="maulerfiend-cross-faction-bridge-test",
            version="phase17a-test",
        ),
        datasheet_ids=datasheet_ids,
        height_overrides=MAULERFIEND_HEIGHT_OVERRIDES,
    )
    package = build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="maulerfiend-cross-faction-catalog-test",
            version="phase17a-test",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-maulerfiend-cross-faction-test",
            source_date=date(2026, 6, 14),
        ),
        source_artifacts=bridge_artifacts,
    )
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )

    # This certifies shared bridge/mustering identity, not faction-local ability execution.
    for (faction_id, datasheet_id), (_, magma_wargear_id, _) in variant_details.items():
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        model_profile = datasheet.model_profiles[0]
        expected = variant_catalog_expectations[datasheet_id]
        magma_profile = next(
            wargear.weapon_profiles[0]
            for wargear in package.army_catalog.wargear
            if wargear.wargear_id == magma_wargear_id
        )
        lasher_profile = next(
            wargear.weapon_profiles[0]
            for wargear in package.army_catalog.wargear
            if wargear.wargear_id == f"{datasheet_id}:lasher-tendrils"
        )
        fists_profile = next(
            wargear.weapon_profiles[0]
            for wargear in package.army_catalog.wargear
            if wargear.wargear_id == f"{datasheet_id}:maulerfiend-fists"
        )
        geometry = next(
            record
            for record in package.model_geometries
            if record.model_profile_id == model_profile.model_profile_id
        )
        assert (datasheet.composition[0].min_models, datasheet.composition[0].max_models) == (
            1,
            1,
        )
        assert {
            value.characteristic.value: (value.value_kind.value, value.final)
            for value in model_profile.characteristics
        } == {
            "ballistic_skill": ("source_dash", 0),
            "invulnerable_save": ("numeric", 5),
            "leadership": ("numeric", 6),
            "movement": ("numeric", expected["movement"]),
            "objective_control": ("numeric", 3),
            "save": ("numeric", 3),
            "toughness": ("numeric", 10),
            "weapon_skill": ("source_dash", 0),
            "wounds": ("numeric", 12),
        }
        assert tuple(sorted(datasheet.keywords.keywords)) == expected["keywords"]
        assert datasheet.keywords.faction_keywords == (expected["faction_keyword"],)
        assert (
            tuple(sorted(ability.name for ability in datasheet.abilities)) == expected["abilities"]
        )
        assert tuple(
            (effect.effect_kind, effect.modifier, effect.wounds_min, effect.wounds_max)
            for effect in datasheet.damaged_effects
        ) == ((DamagedEffectKind.HIT_ROLL_MODIFIER, -1, 1, 4),)
        assert model_profile.characteristic(Characteristic.MOVEMENT).final == expected["movement"]
        assert model_profile.base_size.to_payload() == {
            "kind": "oval",
            "diameter_mm": None,
            "length_mm": 120.0,
            "width_mm": 92.0,
        }
        assert math.isclose(geometry.height.height_inches, 90.0 / 25.4, abs_tol=1e-12)
        assert expected["height_source_id"] in {
            evidence.source_id for evidence in geometry.evidence
        }
        assert (
            next(
                evidence
                for evidence in geometry.evidence
                if evidence.evidence_id == f"{model_profile.model_profile_id}:footprint"
            ).source_id
            == expected["footprint_source_id"]
        )
        magma_damage_dice = magma_profile.damage_profile.dice_expression
        assert (
            magma_profile.name,
            magma_profile.range_profile.kind.value,
            magma_profile.range_profile.distance_inches,
            magma_profile.attack_profile.fixed_attacks,
            magma_profile.skill.final,
            magma_profile.strength.final,
            magma_profile.armor_penetration.final,
            magma_profile.damage_profile.fixed_damage,
            (
                None
                if magma_damage_dice is None
                else (
                    magma_damage_dice.quantity,
                    magma_damage_dice.sides,
                    magma_damage_dice.modifier,
                )
            ),
            tuple(keyword.value for keyword in magma_profile.keywords),
            tuple(ability.ability_id for ability in magma_profile.abilities),
        ) == (
            expected["magma_name"],
            "distance",
            6,
            2,
            expected["magma_skill"],
            9,
            -4,
            None,
            (1, 6, 0),
            expected["magma_keywords"],
            expected["magma_abilities"],
        )
        fists_damage_dice = fists_profile.damage_profile.dice_expression
        assert (
            fists_profile.name,
            fists_profile.range_profile.kind.value,
            fists_profile.range_profile.distance_inches,
            fists_profile.attack_profile.fixed_attacks,
            fists_profile.skill.final,
            fists_profile.strength.final,
            fists_profile.armor_penetration.final,
            fists_profile.damage_profile.fixed_damage,
            (
                None
                if fists_damage_dice is None
                else (
                    fists_damage_dice.quantity,
                    fists_damage_dice.sides,
                    fists_damage_dice.modifier,
                )
            ),
            tuple(keyword.value for keyword in fists_profile.keywords),
            tuple(ability.ability_id for ability in fists_profile.abilities),
        ) == (
            "Maulerfiend fists",
            "melee",
            None,
            expected["fists_attacks"],
            3,
            14,
            -2,
            None,
            (1, 6, 1),
            (),
            (),
        )
        assert (
            lasher_profile.name,
            lasher_profile.range_profile.kind.value,
            lasher_profile.range_profile.distance_inches,
            lasher_profile.attack_profile.fixed_attacks,
            lasher_profile.skill.final,
            lasher_profile.strength.final,
            lasher_profile.armor_penetration.final,
            lasher_profile.damage_profile.fixed_damage,
            tuple(keyword.value for keyword in lasher_profile.keywords),
            tuple(ability.ability_id for ability in lasher_profile.abilities),
        ) == (
            "Lasher tendrils",
            "melee",
            None,
            6,
            3,
            7,
            -1,
            1,
            ("Extra Attacks",),
            (),
        )
        default_unit = factory.instantiate_unit(
            army_id=f"{faction_id}-army",
            datasheet=datasheet,
            selection=UnitMusterSelection(
                unit_selection_id=f"{faction_id}-maulerfiend-default",
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile.model_profile_id,
                        model_count=datasheet.composition[0].min_models,
                    ),
                ),
            ),
        )
        assert default_unit.own_models[0].wargear_ids == (
            f"{datasheet_id}:lasher-tendrils",
            f"{datasheet_id}:maulerfiend-fists",
        )
        selection = UnitMusterSelection(
            unit_selection_id=f"{faction_id}-maulerfiend-magma-cutters",
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=model_profile.model_profile_id,
                    model_count=datasheet.composition[0].min_models,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=f"{datasheet_id}:magma-cutters:option-1",
                    model_profile_id=model_profile.model_profile_id,
                    wargear_ids=(magma_wargear_id,),
                ),
            ),
        )
        reconstructed_identity_rows: list[tuple[tuple[int, str], ...]] = []
        for _ in range(2):
            unit = factory.instantiate_unit(
                army_id=f"{faction_id}-army",
                datasheet=datasheet,
                selection=selection,
            )
            model = unit.own_models[0]
            assert model.wargear_ids == (
                f"{datasheet_id}:maulerfiend-fists",
                magma_wargear_id,
                magma_wargear_id,
            )
            magma_instances = tuple(
                weapon
                for weapon in equipped_weapon_instances_for_model(model)
                if weapon.wargear_id == magma_wargear_id
            )
            assert tuple(weapon.copy_ordinal for weapon in magma_instances) == (1, 2)
            assert len({weapon.weapon_instance_id for weapon in magma_instances}) == 2
            reconstructed_identity_rows.append(
                tuple(
                    (weapon.copy_ordinal, weapon.weapon_instance_id) for weapon in magma_instances
                )
            )
        assert reconstructed_identity_rows[0] == reconstructed_identity_rows[1]


def test_phase17a_current_maulerfiend_rules_updates_are_fail_closed_and_source_bound() -> None:
    pack = maulerfiend_overlay.overlay_pack()
    manifest = maulerfiend_overlay.source_release_manifest()
    assert manifest.overlay_package_ids == (pack.package_id,)
    assert maulerfiend_overlay.source_package_identity_payload() == {
        "source_package_id": pack.package_id.stable_identity(),
        "source_payload_checksum_sha256": pack.package_hash(),
        "source_date": "2026-07-22",
        "source_edition": "warhammer-40000-11th",
    }
    assert tuple(
        (operation.source_row_id, operation.source_reference) for operation in pack.operations
    ) == (
        (
            "000001029:2",
            "gw-11e-thousand-sons-faction-pack-2026-07:datasheet:000001029:rules-update:page-10",
        ),
        (
            "000002639:3",
            "gw-11e-world-eaters-faction-pack-2026-07:datasheet:000002639:rules-update:page-8",
        ),
    )

    overlaid = apply_source_release_overlays(
        source_artifacts=wahapedia_source_artifacts(),
        release_manifest=manifest,
        overlay_packs=(pack,),
    )
    abilities = next(
        artifact for artifact in overlaid if artifact.source_table == "Datasheets_abilities"
    )
    descriptions = {
        row.source_row_id: row.runtime_fields_payload()["description"]
        for row in abilities.rows
        if row.source_row_id in {"000001029:2", "000002639:3"}
    }
    assert descriptions == {
        "000001029:2": maulerfiend_overlay.THOUSAND_SONS_SNARLING_PROTECTOR_DESCRIPTION,
        "000002639:3": maulerfiend_overlay.WORLD_EATERS_SCENT_OF_BLOOD_DESCRIPTION,
    }

    stale_pack = replace(
        pack,
        operations=(
            replace(
                pack.operations[0],
                expected_preimage_hash=hashlib.sha256(b"stale").hexdigest(),
            ),
            pack.operations[1],
        ),
    )
    with pytest.raises(SourceOverlayError, match="target_drift"):
        apply_source_release_overlays(
            source_artifacts=wahapedia_source_artifacts(),
            release_manifest=manifest,
            overlay_packs=(stale_pack,),
        )


def test_phase17a_all_current_maulerfiends_are_selected_and_mfm_priced() -> None:
    assert MAULERFIEND_DATASHEET_IDS == (
        "000000968",
        "000001029",
        "000002639",
        "000004091",
    )
    assert set(MAULERFIEND_DATASHEET_IDS) <= set(ABILITY_SUPPORT_DATASHEET_IDS)

    package = _ability_support_catalog_package(datasheet_ids=MAULERFIEND_DATASHEET_IDS)
    assert tuple(datasheet.datasheet_id for datasheet in package.army_catalog.datasheets) == (
        "000000968",
        "000001029",
        "000002639",
        "000004091",
    )
    assert not any(
        "DEATH GUARD" in datasheet.keywords.faction_keywords
        for datasheet in package.army_catalog.datasheets
    )

    current_rule_text = {
        (datasheet.datasheet_id, ability.name): ability.effect_description
        for datasheet in package.army_catalog.datasheets
        for ability in datasheet.abilities
        if (datasheet.datasheet_id, ability.name)
        in {
            ("000001029", "Snarling Protector"),
            ("000002639", "The Scent of Blood"),
        }
    }
    assert current_rule_text == {
        (
            "000001029",
            "Snarling Protector",
        ): maulerfiend_overlay.THOUSAND_SONS_SNARLING_PROTECTOR_DESCRIPTION,
        (
            "000002639",
            "The Scent of Blood",
        ): maulerfiend_overlay.WORLD_EATERS_SCENT_OF_BLOOD_DESCRIPTION,
    }

    variant_points = {
        "000000968": ("CSM", (130, 130, 130)),
        "000001029": ("TS", (120, 120, 130)),
        "000002639": ("WE", (140, 140, 150)),
        "000004091": ("EC", (120, 120, 130)),
    }
    for datasheet_id, (faction_id, expected_points) in variant_points.items():
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        model_profile_id = datasheet.model_profiles[0].model_profile_id
        unit_selections = tuple(
            UnitMusterSelection(
                unit_selection_id=f"{faction_id.lower()}-maulerfiend-{unit_number}",
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=1,
                    ),
                ),
            )
            for unit_number in range(1, 4)
        )
        calculation = calculate_mfm_army_points(
            catalog=package.army_catalog,
            request=ArmyMusterRequest(
                army_id=f"{faction_id.lower()}-maulerfiend-army",
                player_id="maulerfiend-points-player",
                catalog_id=package.army_catalog.catalog_id,
                source_package_id=package.army_catalog.source_package_id,
                ruleset_id=package.army_catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=faction_id,
                    detachment_ids=("maulerfiend-points-proof",),
                ),
                force_disposition_id="maulerfiend-points-proof",
                unit_selections=unit_selections,
            ),
        )
        assert tuple(
            (
                line.datasheet_id,
                line.mfm_unit_record_id,
                line.mfm_unit_id,
                line.unit_number,
                line.model_count,
                line.base_points,
                line.wargear_points,
                line.total_points,
            )
            for line in calculation.unit_lines
        ) == tuple(
            (
                datasheet_id,
                "units-maulerfiend",
                "maulerfiend",
                unit_number,
                1,
                points,
                0,
                points,
            )
            for unit_number, points in enumerate(expected_points, start=1)
        )
        assert tuple(
            (point.unit_selection_id, point.points)
            for point in calculation.roster_unit_point_values()
        ) == tuple(
            (selection.unit_selection_id, points)
            for selection, points in zip(unit_selections, expected_points, strict=True)
        )


def test_phase17a_datasheet_model_blank_name_is_optional_source_text() -> None:
    table = WahapediaCsvTable.from_csv_text(
        table_name="Datasheets_models",
        csv_text=(
            "datasheet_id,line,name,M,T,Sv,inv_sv,inv_sv_descr,W,Ld,OC,base_size,base_size_descr\n"
            "ds-1,1,,5,5,2+,-,,6,6+,1,40mm,\n"
        ),
    )
    artifact = WahapediaJsonArtifact.from_csv_table(
        source_package_id=_package_id(),
        table=table,
    )

    assert artifact.rows[0].source_row_id == "ds-1:1"
    assert "name" not in {field.column_name for field in artifact.rows[0].text_fields}


def test_phase17a_wahapedia_index_discovery_extracts_edition_csv_links() -> None:
    config = EditionSourceConfig.wahapedia_previous_edition_bridge()
    sources = discover_wahapedia_sources_from_export_specs(
        xlsx_bytes=_wahapedia_export_specs_xlsx(),
        source_config=config,
    )
    config_payload = cast(
        EditionSourceConfigPayload,
        json.loads(json.dumps(config.to_payload(), sort_keys=True)),
    )

    assert EditionSourceConfig.from_payload(config_payload) == config
    assert [source.relative_path for source in sources] == ["Abilities.csv", "Datasheets.csv"]
    assert sources[0].url == f"https://wahapedia.ru/{_previous_edition_slug()}/Abilities.csv"


def test_phase17a_wahapedia_index_discovery_rejects_wrong_edition_links() -> None:
    with pytest.raises(ValueError, match="requested edition"):
        discover_wahapedia_sources_from_export_specs(
            xlsx_bytes=_wahapedia_export_specs_xlsx(
                csv_base=f"/{EditionSourceConfig.wahapedia_11th().wahapedia_edition_slug}/"
            ),
            source_config=EditionSourceConfig.wahapedia_previous_edition_bridge(),
        )


def test_phase17a_wahapedia_index_discovery_canonicalizes_same_host_http_links() -> None:
    config = EditionSourceConfig.wahapedia_previous_edition_bridge()
    sources = discover_wahapedia_sources_from_export_specs(
        xlsx_bytes=_wahapedia_export_specs_xlsx(url_scheme="http"),
        source_config=config,
    )

    assert all(source.url.startswith("https://wahapedia.ru/") for source in sources)


def test_phase17a_wahapedia_payloads_reject_drift_and_invalid_links() -> None:
    artifact = _abilities_artifact(_abilities_csv())
    row = artifact.rows[0]
    row_payload = cast(
        SourceTextFieldPayload,
        json.loads(json.dumps(row.text_fields[0].to_payload(), sort_keys=True)),
    )
    snapshot = WahapediaSourceSnapshot(
        package_id=_package_id(),
        catalog_version=_catalog_version(),
        upstream_identity="wahapedia-export",
        source_edition="warhammer-40000-11th",
        source_files=(
            SourceFileChecksum(
                path="Abilities.csv",
                checksum_sha256=hashlib.sha256(_abilities_csv().encode()).hexdigest(),
                size_bytes=len(_abilities_csv().encode()),
            ),
        ),
    )
    snapshot_payload = cast(
        WahapediaSourceSnapshotPayload,
        json.loads(json.dumps(snapshot.to_payload(), sort_keys=True)),
    )

    assert WahapediaSourceSnapshot.from_payload(snapshot_payload).to_payload() == (
        snapshot.to_payload()
    )
    assert NormalizedSourceRow.from_payload(row.to_payload()).to_payload() == row.to_payload()

    row_payload["normalized_text"] = "drifted"
    with pytest.raises(WahapediaSchemaError, match="stale"):
        row.text_fields[0].from_payload(row_payload)

    with pytest.raises(WahapediaSchemaError, match="reference runtime fields"):
        NormalizedSourceRow(
            source_package_id=row.source_package_id,
            source_table=row.source_table,
            source_row_id=row.source_row_id,
            source_row_number=row.source_row_number,
            fields=(("id", row.source_row_id),),
            text_fields=row.text_fields,
        )
    with pytest.raises(WahapediaSchemaError, match="row package IDs"):
        WahapediaJsonArtifact(
            source_package_id=DataPackageId(
                namespace="other",
                package_name="source-mirror",
                version="11th-transition",
            ),
            source_table=artifact.source_table,
            source_checksum_sha256=artifact.source_checksum_sha256,
            rows=artifact.rows,
        )
    with pytest.raises(WahapediaSchemaError, match="row tables"):
        WahapediaJsonArtifact(
            source_package_id=artifact.source_package_id,
            source_table="Datasheets",
            source_checksum_sha256=artifact.source_checksum_sha256,
            rows=artifact.rows,
        )
    with pytest.raises(WahapediaSchemaError, match="duplicate"):
        WahapediaJsonArtifact(
            source_package_id=artifact.source_package_id,
            source_table=artifact.source_table,
            source_checksum_sha256=artifact.source_checksum_sha256,
            rows=(row, row),
        )


def test_phase17a_schema_and_build_report_reject_invalid_construction() -> None:
    table = WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=_abilities_csv())
    empty_table = WahapediaCsvTable(
        table_name="Abilities",
        columns=("id", "name", "description"),
        rows=(),
        checksum_sha256=hashlib.sha256(b"").hexdigest(),
    )
    report = build_wahapedia_artifact_report(
        source_package_id=_package_id(),
        table=empty_table,
    )

    assert set(report.diagnostics_by_reason()) == {"empty_table"}
    assert report.to_payload()["diagnostics"][0]["reason"] == "empty_table"
    with pytest.raises(WahapediaSchemaError, match="diagnostics"):
        report.require_success()
    with pytest.raises(WahapediaSchemaError, match="source_package_id"):
        build_wahapedia_artifact_report(
            source_package_id=cast(DataPackageId, "bad"),
            table=table,
        )
    with pytest.raises(WahapediaSchemaError, match="schema table_name"):
        build_wahapedia_artifact_report(
            source_package_id=_package_id(),
            table=table,
            schema=schema_for_table("Datasheets"),
        )
    with pytest.raises(WahapediaSchemaError, match="required_columns"):
        WahapediaTableSchema(
            table_name="Bad",
            source_row_id_columns=("id",),
            text_columns=("description",),
            required_columns=("id",),
        )
    with pytest.raises(WahapediaSchemaError, match="rows"):
        WahapediaArtifactBuildReport(
            source_table="Abilities",
            rows=cast(tuple[NormalizedSourceRow, ...], ("bad",)),
            diagnostics=(),
        )
    with pytest.raises(WahapediaSchemaError, match="source_files"):
        replace(
            WahapediaSourceSnapshot(
                package_id=_package_id(),
                catalog_version=_catalog_version(),
                upstream_identity="wahapedia-export",
                source_edition="warhammer-40000-11th",
                source_files=(
                    SourceFileChecksum(
                        path="Abilities.csv",
                        checksum_sha256=hashlib.sha256(b"one").hexdigest(),
                        size_bytes=3,
                    ),
                ),
            ),
            source_files=(),
        )


def _abilities_artifact(csv_text: str) -> WahapediaJsonArtifact:
    table = WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=csv_text)
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_package_id(),
        table=table,
    )


def _abilities_csv() -> str:
    return (
        "id,faction_id,name,description\n"
        'ability-1,SM,Angels\u2019 Fury,"<p>roll d6 + 2 attacks within 12 inches.</p>'
        "<ul><li>feel no pain applies.</li></ul>"
        '<p><a href=""https://example.invalid/rule"">designer note</a></p>"\n'
    )


def _previous_edition_slug() -> str:
    return "wh40k" + "1" + "0ed"


def _wahapedia_export_specs_xlsx(
    *,
    csv_base: str | None = None,
    url_scheme: str = "https",
) -> bytes:
    if csv_base is None:
        csv_base = f"/{_previous_edition_slug()}/"
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<sheets>"
                '<sheet name="EN" sheetId="1" r:id="rId1"/>'
                "</sheets>"
                "</workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<hyperlinks>"
                '<hyperlink ref="A1" r:id="rId1"/>'
                '<hyperlink ref="A2" r:id="rId2"/>'
                "</hyperlinks>"
                "</worksheet>"
            ),
        )
        archive.writestr(
            "xl/worksheets/_rels/sheet1.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId2" Target="{url_scheme}://wahapedia.ru'
                f'{csv_base}Datasheets.csv"/>'
                f'<Relationship Id="rId1" Target="{url_scheme}://wahapedia.ru'
                f'{csv_base}Abilities.csv"/>'
                "</Relationships>"
            ),
        )
    return buffer.getvalue()


def _package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="11th-transition",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="phase17a-test",
        source_date=date(2026, 6, 1),
    )
