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


def test_july_chaos_space_marines_defiler_artifact_links_daemonforge_runtime() -> None:
    artifact = july_faction_packs_2026_07.chaos_space_marines_defiler()
    contribution = chaos_space_marines_army_rule.runtime_contribution()

    assert artifact.datasheet_id == chaos_space_marines_army_rule.DEFILER_DAEMONFORGE_DATASHEET_ID
    assert (
        artifact.source_ability_id == chaos_space_marines_army_rule.DEFILER_DAEMONFORGE_ABILITY_ID
    )
    assert artifact.semantic_execution_status == "executable_generic_runtime"
    assert artifact.provider_activation_status == "current_default"
    assert contribution.contribution_id == artifact.runtime_provider_id
    assert tuple(
        binding.modifier_id for binding in contribution.attack_reroll_permission_bindings
    ) == tuple(artifact.runtime_consumer_ids)


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
__all__ += ["command_point_consumer_ids_for_clause", "date", "emperors_children_july"]
__all__ += ["emperors_children_june_manifest", "faction_coverage_2026_27"]
__all__ += ["faction_execution_2026_27", "faction_source_promotion_2026_07"]
__all__ += ["faction_subrules_2026_27", "generated_manifest", "hashlib", "json"]
__all__ += ["load_official_source_manifest", "parameter_payload", "pytest", "source_row_hash"]
__all__ += ["stratagem_phase_use_exception", "thousand_sons_july", "thousand_sons_june_manifest"]
