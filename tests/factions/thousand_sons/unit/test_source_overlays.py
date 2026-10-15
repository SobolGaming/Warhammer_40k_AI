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


def test_july_thousand_sons_defiler_artifact_and_provider_are_current() -> None:
    artifact = july_faction_packs_2026_07.thousand_sons_defiler()
    june = thousand_sons_june_manifest.runtime_contribution()
    current = thousand_sons_july.runtime_contribution()
    record = current.stratagem_records[0]
    exception = stratagem_phase_use_exception(record.definition)

    assert artifact.aligned_defiler_datasheet_ids == [
        "000001030",
        "000004207",
        "000004208",
        "000004209",
    ]
    assert artifact.audited_chaos_space_marines_datasheet_id == "000000969"
    assert artifact.old_rule_ir_semantics == "removed_minimum_hit_threshold"
    assert artifact.semantic_execution_status == "executable_generic_runtime"
    assert artifact.provider_activation_status == "current_default"
    assert june.contribution_id != artifact.runtime_provider_id
    assert june.stratagem_records == ()
    assert june.stratagem_cost_modifier_bindings == ()
    assert current.contribution_id == artifact.runtime_provider_id
    assert record.definition.handler_id == artifact.counteroffensive_handler_id
    assert exception is not None
    assert exception.source_ability_id == artifact.source_ability_id
    assert exception.eligible_datasheet_ids == (artifact.datasheet_id,)
    assert tuple(binding.modifier_id for binding in current.stratagem_cost_modifier_bindings) == (
        artifact.runtime_consumer_ids[1],
    )

    active_thousand_sons_row = next(
        row
        for row in generated_manifest.generated_runtime_content_rows()
        if row.owner_faction_id == "thousand-sons" and row.owner_detachment_id is None
    )
    assert active_thousand_sons_row.module_path is not None
    assert active_thousand_sons_row.module_path.endswith(".thousand_sons.july_2026")
    assert "july_2026_candidate" not in active_thousand_sons_row.module_path


__all__: list[str] = []
__all__ += ["CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID", "CatalogVersion", "DataPackageId"]
__all__ += ["ExternalReferenceDiscoveryMethod", "ExternalReferenceKind"]
__all__ += ["ExternalReferenceLookupError", "NormalizedSourceRow", "OverlaySourceArtifact"]
__all__ += ["OverlaySourceArtifactPayload", "Path", "RuleEffectKind"]
__all__ += ["RuntimeContentModuleFamily", "SourceOverlayError", "SourceOverlayOperation"]
__all__ += ["SourceOverlayOperationKind", "SourceOverlayPack", "SourceOverlayPackPayload"]
__all__ += ["SourceReferenceCatalog", "SourceReferenceCatalogPayload", "SourceReleaseManifest"]
__all__ += ["THIRTY_NINE_K_PRO_TARGET_EDITION", "SourceReleaseManifestPayload"]
__all__ += ["WahapediaCsvTable", "WahapediaJsonArtifact", "_abilities_artifact"]
__all__ += ["_catalog_version", "_official_source_identities", "_operation", "_overlay_pack"]
__all__ += ["_overlay_package_id", "_previous_source_edition", "_reference_package_id"]
__all__ += ["_release_manifest", "_row_by_id", "_source_package_id", "_source_row_ids"]
__all__ += ["_updated_row_after_first_operation", "apply_source_overlays"]
__all__ += ["apply_source_release_overlays", "build_source_reference_catalog"]
__all__ += ["build_source_release_overlay_report", "build_thirty_nine_k_pro_reference_lookup"]
__all__ += ["cast", "catalog_rule_clauses_from_record", "chaos_daemons_july"]
__all__ += ["chaos_daemons_july_updates", "chaos_daemons_june_manifest"]
__all__ += ["chaos_space_marines_army_rule", "command_point_consumer_ids_for_clause", "date"]
__all__ += ["emperors_children_july", "emperors_children_june_manifest"]
__all__ += ["faction_coverage_2026_27", "faction_execution_2026_27"]
__all__ += ["faction_source_promotion_2026_07", "faction_subrules_2026_27", "hashlib", "json"]
__all__ += ["load_official_source_manifest", "parameter_payload", "pytest", "source_row_hash"]
