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


def test_july_daemonic_manifestation_artifact_is_current_and_executable() -> None:
    artifact = july_faction_packs_2026_07.daemonic_manifestation()

    assert artifact.rule_name == "Daemonic Manifestation"
    assert artifact.predecessor_source_rule_id == "phase17f:phase17e:chaos-daemons:army-rule"
    assert artifact.semantic_execution_status == "executable_named_handler"
    assert artifact.provider_activation_status == "current_default"
    assert (
        artifact.named_handler_classification
        == "approved_successor_of_existing_army_rule_orchestrator"
    )
    assert artifact.named_handler_budget_execution_id == artifact.predecessor_source_rule_id
    assert artifact.decision_types == [
        "select_healing_model",
        "submit_healing_revival_placement",
    ]

    coverage_row = next(
        row
        for row in faction_coverage_2026_27.coverage_rows()
        if row.faction_id == "chaos-daemons"
        and row.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.FACTION_ARMY_RULE
    )
    execution_record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_row.descriptor_id
    )
    active_runtime_row = next(
        row
        for row in generated_manifest.generated_runtime_content_rows()
        if row.family is RuntimeContentModuleFamily.FACTION and row.content_id == "chaos-daemons"
    )

    assert coverage_row.descriptor_id == artifact.phase17e_descriptor_id
    assert coverage_row.rule_name == artifact.rule_name
    assert coverage_row.runtime_consumer_ids == tuple(artifact.runtime_consumer_ids)
    assert execution_record.execution_id == artifact.phase17f_execution_id
    assert execution_record.handler_id == artifact.runtime_consumer_ids[0]
    assert artifact.phase17f_execution_id in active_runtime_row.execution_record_ids
    assert artifact.predecessor_source_rule_id not in active_runtime_row.execution_record_ids
    assert artifact.predecessor_source_rule_id not in {
        record.execution_id for record in faction_execution_2026_27.execution_records()
    }


__all__: list[str] = []
__all__ += ["CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID", "CatalogVersion", "DataPackageId"]
__all__ += ["ExternalReferenceDiscoveryMethod", "ExternalReferenceKind"]
__all__ += ["ExternalReferenceLookupError", "NormalizedSourceRow", "OverlaySourceArtifact"]
__all__ += ["OverlaySourceArtifactPayload", "Path", "RuleEffectKind", "SourceOverlayError"]
__all__ += ["SourceOverlayOperation", "SourceOverlayOperationKind", "SourceOverlayPack"]
__all__ += ["SourceOverlayPackPayload", "SourceReferenceCatalog", "SourceReferenceCatalogPayload"]
__all__ += ["SourceReleaseManifest", "SourceReleaseManifestPayload"]
__all__ += ["THIRTY_NINE_K_PRO_TARGET_EDITION", "WahapediaCsvTable", "WahapediaJsonArtifact"]
__all__ += ["_abilities_artifact", "_catalog_version", "_official_source_identities"]
__all__ += ["_operation", "_overlay_pack", "_overlay_package_id", "_previous_source_edition"]
__all__ += ["_reference_package_id", "_release_manifest", "_row_by_id", "_source_package_id"]
__all__ += ["_source_row_ids", "_updated_row_after_first_operation", "apply_source_overlays"]
__all__ += ["apply_source_release_overlays", "build_source_reference_catalog"]
__all__ += ["build_source_release_overlay_report", "build_thirty_nine_k_pro_reference_lookup"]
__all__ += ["cast", "catalog_rule_clauses_from_record", "chaos_daemons_july"]
__all__ += ["chaos_daemons_july_updates", "chaos_daemons_june_manifest"]
__all__ += ["chaos_space_marines_army_rule", "command_point_consumer_ids_for_clause", "date"]
__all__ += ["emperors_children_july", "emperors_children_june_manifest"]
__all__ += ["faction_source_promotion_2026_07", "faction_subrules_2026_27", "hashlib", "json"]
__all__ += ["load_official_source_manifest", "parameter_payload", "pytest", "source_row_hash"]
__all__ += ["stratagem_phase_use_exception", "thousand_sons_july", "thousand_sons_june_manifest"]
