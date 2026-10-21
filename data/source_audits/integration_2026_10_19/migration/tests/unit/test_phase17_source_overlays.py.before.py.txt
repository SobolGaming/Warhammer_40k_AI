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
    (
        "reference_kind",
        "query",
        "parent_faction_url",
        "expected_method",
        "expected_discovery_url",
    ),
    [
        (
            ExternalReferenceKind.FACTION,
            "Aeldari",
            None,
            ExternalReferenceDiscoveryMethod.FACTION_NAVIGATION,
            "https://39k.pro/",
        ),
        (
            ExternalReferenceKind.DATASHEET,
            "Intercessor Squad",
            None,
            ExternalReferenceDiscoveryMethod.DATASHEET_SEARCH,
            "https://39k.pro/search?q=Intercessor%20Squad",
        ),
        (
            ExternalReferenceKind.DETACHMENT,
            "Gladius Task Force",
            "https://39k.pro/faction/VpM8N0uc-Q0",
            ExternalReferenceDiscoveryMethod.FACTION_DETACHMENT_NAVIGATION,
            "https://39k.pro/faction/VpM8N0uc-Q0",
        ),
    ],
)
def test_phase17_39k_pro_lookup_builds_kind_specific_discovery_routes(
    reference_kind: ExternalReferenceKind,
    query: str,
    parent_faction_url: str | None,
    expected_method: ExternalReferenceDiscoveryMethod,
    expected_discovery_url: str,
) -> None:
    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=reference_kind,
        query=query,
        parent_faction_url=parent_faction_url,
    )

    assert lookup.discovery_method is expected_method
    assert lookup.discovery_url == expected_discovery_url
    assert lookup.to_payload()["reference_verification_required"] is True
    assert json.loads(json.dumps(lookup.to_payload(), sort_keys=True)) == lookup.to_payload()


def test_phase17_39k_pro_lookup_rejects_wrong_edition_kind_and_discovery_context() -> None:
    with pytest.raises(ExternalReferenceLookupError, match=r"only.*11th Edition"):
        build_thirty_nine_k_pro_reference_lookup(
            target_edition="warhammer-40000-12th",
            reference_kind=ExternalReferenceKind.FACTION,
            query="Aeldari",
        )
    with pytest.raises(ExternalReferenceLookupError, match="ExternalReferenceKind"):
        build_thirty_nine_k_pro_reference_lookup(
            target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
            reference_kind=cast(ExternalReferenceKind, "faction"),
            query="Aeldari",
        )
    with pytest.raises(ExternalReferenceLookupError, match="parent_faction_url"):
        build_thirty_nine_k_pro_reference_lookup(
            target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
            reference_kind=ExternalReferenceKind.DETACHMENT,
            query="Gladius Task Force",
        )
    with pytest.raises(ExternalReferenceLookupError, match="expected_kind"):
        build_thirty_nine_k_pro_reference_lookup(
            target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
            reference_kind=ExternalReferenceKind.DETACHMENT,
            query="Gladius Task Force",
            parent_faction_url="https://39k.pro/detachment/--1EtXzGAuw",
        )


def test_phase17_source_overlay_update_preserves_raw_overlay_text_in_references() -> None:
    artifact = _abilities_artifact()
    raw_overlay_text = "<p>Roll D6 within 12 inches.</p>"
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", raw_overlay_text),),
            ),
        )
    )
    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0]
    description = _row_by_id(overlay_artifact, "ability-1:SM").text_fields[1]
    reference_catalog = build_source_reference_catalog(
        package_id=_reference_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=(overlay_artifact,),
    )
    reference = reference_catalog.source_text_by_id(description.source_text_id)

    assert (
        _row_by_id(overlay_artifact, "ability-1:SM").runtime_fields_payload()["description"]
        == "Roll D6 within 12 inches."
    )
    assert reference.raw_text == raw_overlay_text
    assert reference.sanitized_text == "Roll D6 within 12 inches."
    assert reference.normalized_text == 'Roll D6 within 12".'


def test_july_faction_pack_ledger_matches_current_and_predecessor_manifests() -> None:
    root = REPOSITORY_ROOT
    current = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
    )
    predecessors = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_faction_pack_predecessors_2026_06.yaml"
    )
    deathwatch_id = faction_source_promotion_2026_07.DEATHWATCH_PACKAGE_ID
    successors = {
        package_id: identity
        for package_id, identity in current.items()
        if package_id != deathwatch_id
    }
    retained_predecessors = {**predecessors, deathwatch_id: current[deathwatch_id]}
    ledger = july_faction_packs_2026_07.delta_ledger()

    july_faction_packs_2026_07.audit_manifest_links(
        ledger=ledger,
        successor_packages=successors,
        predecessor_packages=retained_predecessors,
    )

    assert len(ledger.pack_reviews) == 27
    assert all(review.review_items for review in ledger.pack_reviews)
    assert "gw-11e-deathwatch-faction-pack-2026-06" not in {
        review.predecessor_package_id for review in ledger.pack_reviews
    }
    dispositions = {
        item.disposition for review in ledger.pack_reviews for item in review.review_items
    }
    assert dispositions == {
        "rules_updates_already_applied",
        "in_scope_source_only",
        "in_scope_runtime_affected",
        "excluded_imperial_armour",
        "excluded_legends",
    }


def test_july_datasheet_preview_preserves_inventory_and_support_boundaries() -> None:
    datasheets = july_faction_packs_2026_07.datasheets()
    preview = july_faction_packs_2026_07.datasheet_support_preview()
    rows_by_id = {row.datasheet_id: row for row in datasheets.rows}

    assert {(row.datasheet_id, row.datasheet_name) for row in datasheets.rows} == {
        ("000000724", "Ratlings"),
        ("000000969", "Defiler"),
        ("000003834", "Tempestus Aquilons"),
        ("000004210", "Thulia Ghuld"),
        ("000004216", "Commissar Yarrick"),
        ("000004221", "Wazdakka Gutsmek"),
        ("000004225", "The Red Terror"),
    }
    assert datasheets.excluded_content_categories == ["imperial-armour", "legends"]
    assert {
        datasheet_id
        for datasheet_id, row in rows_by_id.items()
        if row.inventory_status == "historical_predecessor_only"
    } == {"000000724", "000003834"}
    assert all(row.historical_provenance_retained for row in datasheets.rows)
    assert all(row.runtime_support_claim == "unknown" for row in datasheets.rows)
    assert all(row.semantic_execution_status == "blocked" for row in datasheets.rows)
    assert "Mobile" in {
        operation.replacement_value for operation in rows_by_id["000004210"].overlay_operations
    }
    assert "Mobile" in {
        operation.replacement_value for operation in rows_by_id["000004225"].overlay_operations
    }
    assert {
        operation.target_source_row_id
        for operation in rows_by_id["000004225"].overlay_operations
        if operation.operation_kind == "remove_ability"
    } == {"000004225:5"}
    datasheet_reference = next(
        artifact
        for artifact in july_faction_packs_2026_07.source_package().staged_data_artifacts
        if artifact.artifact_id == datasheets.artifact_id
    )
    july_faction_packs_2026_07.audit_datasheet_preview_links(
        datasheets=datasheets,
        preview=preview,
        datasheet_artifact_sha256=datasheet_reference.artifact_sha256,
    )


def test_july_chaos_daemons_runtime_artifact_is_current_and_contract_stable() -> None:
    artifact = july_faction_packs_2026_07.chaos_daemons_runtime_updates()

    assert artifact.provider_activation_status == "current_default"
    assert artifact.ingress_decision_type == "submit_placement_proposal"
    assert artifact.stratagem_cost_decision_type == "select_stratagem_cost_modifier_option"
    assert artifact.adapter_contract_status == "existing_contract_unchanged"
    assert chaos_daemons_july_updates.replacement_keywords_for_datasheet(
        chaos_daemons_july_updates.SCREAMERS_DATASHEET_ID
    ) == (
        "BEAST",
        "FLY",
        "CHAOS",
        "DAEMON",
        "TZEENTCH",
        "SCREAMERS",
    )
    unsupported = chaos_daemons_july_updates.unsupported_ability_rows()
    assert [(row.rule_name, row.semantic_execution_status) for row in unsupported] == [
        ("Altered Reality", "unsupported")
    ]
    june_contribution = chaos_daemons_june_manifest.runtime_contribution()
    current_contribution = chaos_daemons_july.runtime_contribution()
    assert all(
        record.definition.source_id != artifact.rows[0].source_row_id
        for record in june_contribution.stratagem_records
    )
    assert any(
        record.definition.source_id == artifact.rows[0].source_row_id
        for record in current_contribution.stratagem_records
    )


def test_july_exalted_patron_artifact_is_current_generic_rule_ir() -> None:
    artifact = july_faction_packs_2026_07.exalted_patron()
    rule_ir = artifact.rule_ir()
    execution_record = artifact.execution_record()

    assert artifact.provider_activation_status == "current_default"
    assert artifact.target_required_keywords == ["LORD EXULTANT"]
    assert artifact.removed_ability_ids == ["may_attach_to_flawless_blades"]
    assert tuple(effect.kind for clause in rule_ir.clauses for effect in clause.effects) == (
        RuleEffectKind.MODIFY_MOVE_DISTANCE,
    )
    assert parameter_payload(rule_ir.clauses[1].effects[0].parameters) == {"delta": 1}
    assert execution_record.rule_ir_hash == rule_ir.ir_hash()
    assert (
        emperors_children_july.runtime_contribution().contribution_id
        == artifact.runtime_provider_id
    )
    assert (
        emperors_children_june_manifest.runtime_contribution().contribution_id
        != artifact.runtime_provider_id
    )

    current_record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.execution_id == artifact.phase17f_execution_id
    )
    assert current_record == execution_record

    frenzied_host = next(
        row
        for row in july_faction_packs_2026_07.phase17f_execution().rows
        if row.source_row_id.endswith(":subrule:emperors-children:frenzied-host:frantic-focus")
    )
    assert frenzied_host.execution_status == "blocked_structured_semantics_required"
    assert frenzied_host.runtime_consumer_ids == []


def test_july_kairos_uses_existing_generic_stratagem_cost_semantics() -> None:
    record = next(
        record
        for record in chaos_daemons_july_updates.runtime_contribution().ability_records
        if record.datasheet_id == chaos_daemons_july_updates.KAIROS_DATASHEET_ID
    )
    clauses = catalog_rule_clauses_from_record(record)

    assert len(clauses) == 1
    assert command_point_consumer_ids_for_clause(clauses[0]) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )
    assert record.definition.source_id.startswith(july_faction_packs_2026_07.SOURCE_PACKAGE_ID)


__all__: list[str] = []
__all__ += ["CatalogVersion", "DataPackageId", "NormalizedSourceRow", "OverlaySourceArtifact"]
__all__ += ["OverlaySourceArtifactPayload", "Path", "RuntimeContentModuleFamily"]
__all__ += ["SourceOverlayError", "SourceOverlayOperation", "SourceOverlayPack"]
__all__ += ["SourceOverlayPackPayload", "SourceReferenceCatalog", "SourceReferenceCatalogPayload"]
__all__ += ["SourceReleaseManifest", "SourceReleaseManifestPayload", "WahapediaCsvTable"]
__all__ += ["WahapediaJsonArtifact", "_overlay_package_id", "_previous_source_edition"]
__all__ += ["_source_package_id", "_source_row_ids", "_updated_row_after_first_operation"]
__all__ += ["apply_source_overlays", "build_source_release_overlay_report"]
__all__ += ["chaos_space_marines_army_rule", "date", "faction_coverage_2026_27"]
__all__ += ["faction_subrules_2026_27", "generated_manifest", "hashlib"]
__all__ += ["load_official_source_manifest", "stratagem_phase_use_exception"]
__all__ += ["thousand_sons_july", "thousand_sons_june_manifest"]
