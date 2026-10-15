from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17_source_overlays import (
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    THIRTY_NINE_K_PRO_TARGET_EDITION,
    CatalogVersion,
    DataPackageId,
    ExternalReferenceDiscoveryMethod,
    ExternalReferenceKind,
    ExternalReferenceLookupError,
    NormalizedSourceRow,
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
    Path,
    RuleEffectKind,
    RuntimeContentModuleFamily,
    SourceOverlayError,
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReferenceCatalog,
    SourceReferenceCatalogPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    _abilities_artifact,
    _catalog_version,
    _official_source_identities,
    _operation,
    _overlay_pack,
    _overlay_package_id,
    _previous_source_edition,
    _reference_package_id,
    _release_manifest,
    _row_by_id,
    _source_package_id,
    _source_row_ids,
    _updated_row_after_first_operation,
    apply_source_overlays,
    apply_source_release_overlays,
    build_source_reference_catalog,
    build_source_release_overlay_report,
    build_thirty_nine_k_pro_reference_lookup,
    catalog_rule_clauses_from_record,
    chaos_daemons_july,
    chaos_daemons_july_updates,
    chaos_daemons_june_manifest,
    chaos_space_marines_army_rule,
    command_point_consumer_ids_for_clause,
    date,
    emperors_children_july,
    emperors_children_june_manifest,
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_source_promotion_2026_07,
    faction_subrules_2026_27,
    generated_manifest,
    hashlib,
    json,
    july_faction_packs_2026_07,
    load_official_source_manifest,
    parameter_payload,
    pytest,
    source_row_hash,
    stratagem_phase_use_exception,
    thousand_sons_july,
    thousand_sons_june_manifest,
)
from tests.shared.repository_root import REPOSITORY_ROOT


@pytest.mark.parametrize(
    ("reference_kind", "query", "reference_url", "reference_id"),
    [
        (
            ExternalReferenceKind.FACTION,
            "Aeldari",
            "https://39k.pro/faction/VpM8N0uc-Q0",
            "VpM8N0uc-Q0",
        ),
        (
            ExternalReferenceKind.DATASHEET,
            "Intercessor Squad",
            "https://39k.pro/datasheet/Tw1hCD7xdlA",
            "Tw1hCD7xdlA",
        ),
        (
            ExternalReferenceKind.DETACHMENT,
            "Gladius Task Force",
            "https://39k.pro/detachment/--1EtXzGAuw",
            "--1EtXzGAuw",
        ),
    ],
)
def test_phase17_39k_pro_lookup_verifies_observed_complete_reference_urls(
    reference_kind: ExternalReferenceKind,
    query: str,
    reference_url: str,
    reference_id: str,
) -> None:
    parent_faction_url = (
        "https://39k.pro/faction/VpM8N0uc-Q0"
        if reference_kind is ExternalReferenceKind.DETACHMENT
        else None
    )
    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=reference_kind,
        query=query,
        parent_faction_url=parent_faction_url,
    )

    reference = lookup.verify_reference_url(reference_url)

    assert reference.reference_id == reference_id
    assert reference.reference_url == reference_url
    assert reference.to_payload()["is_verified"] is True


@pytest.mark.parametrize(
    "reference_url",
    [
        "http://39k.pro/faction/VpM8N0uc-Q0",
        "https://example.com/faction/VpM8N0uc-Q0",
        "https://39k.pro/faction/../detachment/--1EtXzGAuw",
        "https://39k.pro/faction/VpM8N0uc-Q0?query=invalid",
    ],
)
def test_phase17_39k_pro_lookup_rejects_untrusted_reference_urls(reference_url: str) -> None:
    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=ExternalReferenceKind.FACTION,
        query="Aeldari",
    )

    with pytest.raises(ExternalReferenceLookupError):
        lookup.verify_reference_url(reference_url)


def test_phase17_39k_pro_lookup_rejects_reference_kind_mismatch() -> None:
    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=ExternalReferenceKind.FACTION,
        query="Aeldari",
    )

    with pytest.raises(ExternalReferenceLookupError, match="expected_kind"):
        lookup.verify_reference_url("https://39k.pro/detachment/--1EtXzGAuw")


def test_phase17_source_overlay_applies_add_update_and_supersede_operations() -> None:
    artifact = _abilities_artifact()
    row = artifact.rows[0]
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update-angels-fury",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(row),
                fields=(("description", "<p>Roll D6 within 12 inches.</p>"),),
            ),
            _operation(
                op_id="add-new-detachment-rule",
                order_index=2,
                kind=SourceOverlayOperationKind.ADD_ROW,
                source_row_id="ability-2:SM",
                expected_preimage_hash=None,
                fields=(
                    ("id", "ability-2"),
                    ("faction_id", "SM"),
                    ("name", "New Rule"),
                    ("description", "Add 1 to the roll."),
                ),
            ),
            _operation(
                op_id="supersede-old-text",
                order_index=3,
                kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(
                    _updated_row_after_first_operation(artifact, package_hash_placeholder=False)
                ),
                fields=(),
            ),
        )
    )

    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0]
    ability_1 = _row_by_id(overlay_artifact, "ability-1:SM")
    ability_2 = _row_by_id(overlay_artifact, "ability-2:SM")
    payload = cast(
        OverlaySourceArtifactPayload,
        json.loads(json.dumps(overlay_artifact.to_payload(), sort_keys=True)),
    )

    assert ability_1.runtime_fields_payload()["description"] == "Roll D6 within 12 inches."
    assert ability_1.runtime_fields_payload()["core_v2_superseded_by"] == "supersede-old-text"
    assert ability_2.runtime_fields_payload()["name"] == "New Rule"
    assert OverlaySourceArtifact.from_payload(payload).to_payload() == overlay_artifact.to_payload()


def test_phase17_source_overlay_rejects_stale_preimage_and_duplicate_field_edits() -> None:
    artifact = _abilities_artifact()
    stale_package = _overlay_pack(
        operations=(
            _operation(
                op_id="stale",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=hashlib.sha256(b"stale").hexdigest(),
                fields=(("description", "Roll D3."),),
            ),
        )
    )

    rejected = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(stale_package.package_id,)),
        overlay_packs=(stale_package,),
        raise_on_blocking=False,
    )[0]

    assert rejected.blocking_diagnostics()[0].reason.value == "target_drift"
    with pytest.raises(SourceOverlayError, match="duplicate field edit"):
        _overlay_pack(
            operations=(
                _operation(
                    op_id="first",
                    order_index=1,
                    kind=SourceOverlayOperationKind.UPDATE_ROW,
                    source_row_id="ability-1:SM",
                    expected_preimage_hash=source_row_hash(artifact.rows[0]),
                    fields=(("description", "Roll D3."),),
                ),
                _operation(
                    op_id="second",
                    order_index=2,
                    kind=SourceOverlayOperationKind.UPDATE_ROW,
                    source_row_id="ability-1:SM",
                    expected_preimage_hash=source_row_hash(artifact.rows[0]),
                    fields=(("description", "Roll D6."),),
                ),
            )
        )


def test_phase17_source_release_manifest_rejects_empty_bridge_and_non_11th_target() -> None:
    native_manifest = SourceReleaseManifest(
        release_id="core-11-native-wahapedia-test",
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        base_source_edition="warhammer-40000-11th",
        target_edition="warhammer-40000-11th",
        overlay_package_ids=(),
    )

    assert native_manifest.overlay_package_ids == ()
    with pytest.raises(SourceOverlayError, match="target_edition must be 11th Edition"):
        SourceReleaseManifest(
            release_id="core-11-invalid-target-test",
            catalog_version=_catalog_version(),
            base_source_package_id=_source_package_id(),
            base_source_edition="warhammer-40000-11th",
            target_edition="warhammer-40000-future",
            overlay_package_ids=(),
        )
    with pytest.raises(SourceOverlayError, match="bridge releases require at least one"):
        _release_manifest(overlay_package_ids=())


def test_phase17_source_release_requires_exact_supplied_overlay_packs() -> None:
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "Roll D6 within 12 inches."),),
            ),
        )
    )
    extra_package = _overlay_pack(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="core-11-source-overlay-extra",
            version="2026-06-01",
        ),
        operations=(
            _operation(
                op_id="add-extra",
                order_index=1,
                kind=SourceOverlayOperationKind.ADD_ROW,
                source_row_id="ability-extra:SM",
                expected_preimage_hash=None,
                fields=(
                    ("id", "ability-extra"),
                    ("faction_id", "SM"),
                    ("name", "Extra Rule"),
                    ("description", "Add 1 to the roll."),
                ),
            ),
        ),
    )

    with pytest.raises(SourceOverlayError, match="exactly match the release manifest"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package, extra_package),
        )
    with pytest.raises(SourceOverlayError, match="duplicate package IDs"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package, package),
        )


def test_phase17_source_overlay_cli_writes_diagnostics_before_blocking(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    artifact = _abilities_artifact()
    stale_package = _overlay_pack(
        operations=(
            _operation(
                op_id="stale",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=hashlib.sha256(b"stale").hexdigest(),
                fields=(("description", "Roll D6."),),
            ),
        )
    )
    (input_dir / "Abilities.json").write_bytes(artifact.to_json_bytes())

    with pytest.raises(SourceOverlayError, match="failed with diagnostics"):
        apply_source_overlays(
            input_dir=input_dir,
            output_dir=output_dir,
            release_manifest=_release_manifest(overlay_package_ids=(stale_package.package_id,)),
            overlay_packs=(stale_package,),
        )
    diagnostics = json.loads((output_dir / "source_overlay_diagnostics.json").read_text())

    assert diagnostics["diagnostics"][0]["reason"] == "target_drift"


def test_phase17_source_overlay_missing_source_table_blocks_and_reports(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            SourceOverlayOperation(
                op_id="missing-table",
                order_index=1,
                operation_kind=SourceOverlayOperationKind.ADD_ROW,
                target_edition="warhammer-40000-11th",
                source_table="Missing_Table",
                source_row_id="missing-1",
                source_reference="gw-11e-transition-update:p1",
                effective_date="2026-06-01",
                reason="Test missing source table.",
                expected_preimage_hash=None,
                fields=(("id", "missing-1"),),
            ),
        )
    )

    with pytest.raises(SourceOverlayError, match="missing_source_table"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package,),
        )
    report = build_source_release_overlay_report(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )

    assert report.release_diagnostics[0].reason.value == "missing_source_table"
    assert report.blocking_diagnostics()[0].reason.value == "missing_source_table"

    (input_dir / "Abilities.json").write_bytes(artifact.to_json_bytes())
    with pytest.raises(SourceOverlayError, match="failed with diagnostics"):
        apply_source_overlays(
            input_dir=input_dir,
            output_dir=output_dir,
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package,),
        )
    diagnostics = json.loads((output_dir / "source_overlay_diagnostics.json").read_text())

    assert diagnostics["diagnostics"] == [
        {
            "blocking": True,
            "message": "Overlay operation references a missing source table.",
            "op_id": "missing-table",
            "reason": "missing_source_table",
            "source_row_id": "missing-1",
            "source_table": "Missing_Table",
        }
    ]


def test_phase17_source_overlay_and_reference_payloads_reject_hash_drift() -> None:
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "Roll D6 within 12 inches."),),
            ),
        )
    )
    manifest = _release_manifest(overlay_package_ids=(package.package_id,))
    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=manifest,
        overlay_packs=(package,),
    )[0]
    reference_catalog = build_source_reference_catalog(
        package_id=_reference_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=(overlay_artifact,),
    )
    pack_payload = cast(
        SourceOverlayPackPayload,
        json.loads(json.dumps(package.to_payload(), sort_keys=True)),
    )
    manifest_payload = cast(
        SourceReleaseManifestPayload,
        json.loads(json.dumps(manifest.to_payload(), sort_keys=True)),
    )
    reference_payload = cast(
        SourceReferenceCatalogPayload,
        json.loads(json.dumps(reference_catalog.to_payload(), sort_keys=True)),
    )

    assert SourceOverlayPack.from_payload(pack_payload) == package
    assert SourceReleaseManifest.from_payload(manifest_payload) == manifest
    assert SourceReferenceCatalog.from_payload(reference_payload).to_payload() == (
        reference_catalog.to_payload()
    )
    assert (
        reference_catalog.source_text_by_id(
            overlay_artifact.rows[0].text_fields[1].source_text_id
        ).normalized_text
        == 'Roll D6 within 12".'
    )

    pack_payload["package_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(SourceOverlayError, match="package_hash"):
        SourceOverlayPack.from_payload(pack_payload)
    reference_payload["catalog_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(ValueError, match="catalog_hash"):
        SourceReferenceCatalog.from_payload(reference_payload)


def test_july_runtime_affected_rows_link_to_stable_active_source_ids() -> None:
    root = REPOSITORY_ROOT
    source_json = (
        root
        / "data"
        / "source_snapshots"
        / "wahapedia"
        / ("".join(("1", "0", "th")) + "-edition")
        / "2026-06-14"
        / "json"
    )
    source_row_ids = {row.source_row_id for row in faction_subrules_2026_27.enhancement_rows()} | {
        row.source_row_id for row in faction_subrules_2026_27.stratagem_rows()
    }

    july_faction_packs_2026_07.audit_runtime_predecessor_references(
        ledger=july_faction_packs_2026_07.delta_ledger(),
        stable_reference_ids_by_kind={
            "phase17e_descriptor_id": {
                row.descriptor_id for row in faction_coverage_2026_27.coverage_rows()
            }
            | {
                july_faction_packs_2026_07.daemonic_manifestation().predecessor_source_rule_id.removeprefix(
                    "phase17f:"
                )
            },
            "source_row_id": source_row_ids,
            "datasheet_id": _source_row_ids(source_json / "Datasheets.json"),
            "datasheet_ability_id": _source_row_ids(source_json / "Datasheets_abilities.json"),
        },
    )


def test_july_load_only_rows_are_typed_linked_and_explicitly_blocked() -> None:
    detachments = july_faction_packs_2026_07.detachments()
    subrules = july_faction_packs_2026_07.subrules()
    phase17e = july_faction_packs_2026_07.phase17e_coverage()
    phase17f = july_faction_packs_2026_07.phase17f_execution()
    scaffolds = july_faction_packs_2026_07.runtime_scaffolds()

    assert {row.detachment_name for row in detachments.rows} == {
        "Equatorial Hordes",
        "Frenzied Host",
        "Vengeful Hosts",
    }
    frenzied_host = next(row for row in detachments.rows if row.detachment_name == "Frenzied Host")
    assert frenzied_host.tags == []
    assert frenzied_host.removed_tags == ["host"]
    assert {row.rule_name for row in subrules.rows} == {
        "Avenging Angel",
        "Concealed Krumpin'",
        "Dey're Over 'Ere",
        "Echojump",
        "Empyric Wellspring",
        "Eruption of Vitality",
        "Evasive Manoeuvres",
        "Foetid Resurgence",
        "Frantic Focus",
        "Fusillade",
        "Hagiomnifex",
        "Imperator Unleashed",
        "Infernal Puppeteer",
        "Jungle Know-wotz",
        "Kaleidoscopic Tempest",
        "Know No Fear",
        "Kunnin' Hunta",
        "Meteoric Onslaught",
        "Murdermind",
        "Mysterious Guardian",
        "On My Signal",
        "Ordained Sacrifice",
        "Orksbane",
        "Purge by Sectors",
        "Reletavistic Tether",
        "Sorrowscent Vulture",
        "Stragglerz",
        "Temporal Corridor",
        "Thieves of Pain",
        "Unkillable Scourge",
    }
    assert all(row.load_support_status == "loaded" for row in detachments.rows)
    assert all(row.load_support_status == "loaded" for row in subrules.rows)
    assert all(row.semantic_execution_status == "blocked" for row in detachments.rows)
    assert all(row.semantic_execution_status == "blocked" for row in subrules.rows)
    assert all(row.coverage_status == "unsupported" for row in phase17e.rows)
    assert all(
        row.execution_status == "blocked_structured_semantics_required" for row in phase17f.rows
    )
    assert all(row.named_handler_id is None for row in scaffolds.rows)
    july_faction_packs_2026_07.audit_load_only_artifact_links(
        detachments=detachments,
        subrules=subrules,
        phase17e=phase17e,
        phase17f=phase17f,
        runtime_scaffolds=scaffolds,
    )


def test_july_source_runtime_and_document_promotion_is_atomic() -> None:
    root = REPOSITORY_ROOT
    current = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
    )
    current_docs = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((root / "docs" / "factions").glob("*.md"))
    }
    phase17_package_ids = (
        faction_coverage_2026_27.SOURCE_PACKAGE_ID,
        faction_execution_2026_27.SOURCE_PACKAGE_ID,
    )
    runtime_rows = generated_manifest.generated_runtime_content_rows()
    runtime_package_ids = tuple(sorted({row.source_package_id for row in runtime_rows}))
    runtime_module_paths: dict[str, str] = {}
    for row in runtime_rows:
        if row.family is not RuntimeContentModuleFamily.FACTION:
            continue
        if row.owner_faction_id is None or row.module_path is None:
            raise AssertionError("Current faction runtime row is incomplete.")
        runtime_module_paths[row.owner_faction_id] = row.module_path
    source_records = faction_source_promotion_2026_07.current_source_records()
    current_package_ids = tuple(record.package_id for record in source_records)
    assert set(current) == set(current_package_ids)

    july_faction_packs_2026_07.audit_current_package_is_atomically_active(
        current_source_package_ids=current_package_ids,
        phase17_source_package_ids=phase17_package_ids,
        runtime_source_package_ids=runtime_package_ids,
        runtime_module_paths_by_faction=runtime_module_paths,
        generated_current_documents=current_docs,
    )

    current_source_by_faction = {record.faction_id: record.package_id for record in source_records}
    executable_statuses = {
        faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
        faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
    }
    assert all(
        record.source_pdf_package_id == current_source_by_faction[record.faction_id]
        for record in faction_execution_2026_27.execution_records()
        if record.execution_status in executable_statuses
    )
    source_set = faction_source_promotion_2026_07.current_source_set()
    deathwatch = next(
        record
        for record in source_set.records
        if record.faction_id == faction_source_promotion_2026_07.DEATHWATCH_FACTION_ID
    )
    assert (
        deathwatch.package_id,
        deathwatch.sha256,
        deathwatch.pdf_path,
    ) == (
        faction_source_promotion_2026_07.DEATHWATCH_PACKAGE_ID,
        faction_source_promotion_2026_07.DEATHWATCH_SHA256,
        faction_source_promotion_2026_07.DEATHWATCH_PDF_PATH,
    )
    assert deathwatch.predecessor_package_id is None
    provenance_only_ids = {
        record.faction_id
        for record in source_set.records
        if record.semantic_change_status == "provenance_only"
    }
    assert provenance_only_ids == faction_source_promotion_2026_07.NO_ACTION_FACTION_IDS
    assert source_set.excluded_content_categories == ["imperial-armour", "legends"]
    assert not (
        {"imperial-armour", "legends"}
        & {row.inventory_status for row in july_faction_packs_2026_07.datasheets().rows}
    )

    with pytest.raises(
        faction_source_promotion_2026_07.FactionSourcePromotionError,
        match="exact promoted set",
    ):
        july_faction_packs_2026_07.audit_current_package_is_atomically_active(
            current_source_package_ids=current_package_ids[:-1],
            phase17_source_package_ids=phase17_package_ids,
            runtime_source_package_ids=runtime_package_ids,
            runtime_module_paths_by_faction=runtime_module_paths,
            generated_current_documents=current_docs,
        )


__all__: list[str] = []
__all__ += ["CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID", "CatalogVersion"]
__all__ += ["ExternalReferenceDiscoveryMethod", "NormalizedSourceRow", "RuleEffectKind"]
__all__ += ["WahapediaCsvTable", "WahapediaJsonArtifact", "_overlay_package_id"]
__all__ += ["_previous_source_edition", "catalog_rule_clauses_from_record", "chaos_daemons_july"]
__all__ += ["chaos_daemons_july_updates", "chaos_daemons_june_manifest"]
__all__ += ["chaos_space_marines_army_rule", "command_point_consumer_ids_for_clause", "date"]
__all__ += ["emperors_children_july", "emperors_children_june_manifest"]
__all__ += ["load_official_source_manifest", "parameter_payload", "stratagem_phase_use_exception"]
__all__ += ["thousand_sons_july", "thousand_sons_june_manifest"]
