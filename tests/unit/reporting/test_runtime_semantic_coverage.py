from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from tools.generate_ability_support_matrix import runtime_content_semantic_coverage_payload

from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentSemanticStatus,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.generated_manifest import (
    generated_runtime_content_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
)


def test_runtime_semantic_coverage_preserves_manifest_evidence() -> None:
    payload = runtime_content_semantic_coverage_payload()
    manifest_rows = generated_runtime_content_rows()
    faction_rows = {
        row.content_id: row
        for row in manifest_rows
        if row.family is RuntimeContentModuleFamily.FACTION
        and row.support_status is RuntimeContentSupportStatus.SUPPORTED
    }
    detachment_rows = {
        row.content_id: row
        for row in manifest_rows
        if row.family is RuntimeContentModuleFamily.DETACHMENT
        and row.support_status is RuntimeContentSupportStatus.SUPPORTED
    }

    source_factions = faction_detachments_2026_27.faction_rows()
    source_detachments = faction_detachments_2026_27.detachment_rows()
    assert tuple(row["faction_id"] for row in payload["factions"]) == tuple(
        row.faction_id for row in source_factions
    )
    assert payload["faction_status_counts"] == _status_counts(faction_rows.values())
    assert payload["detachment_status_counts"] == _status_counts(detachment_rows.values())

    for source_faction, faction_payload in zip(source_factions, payload["factions"], strict=True):
        manifest_row = faction_rows[source_faction.faction_id]
        assert faction_payload["faction_name"] == source_faction.name
        assert faction_payload["semantic_status"] == manifest_row.semantic_status.value
        assert faction_payload["execution_record_count"] == len(manifest_row.execution_record_ids)
        assert faction_payload["source_ids"] == list(manifest_row.source_ids)
        assert faction_payload["module_path"] == manifest_row.module_path

        owned_detachments = tuple(
            row for row in source_detachments if row.faction_id == source_faction.faction_id
        )
        assert tuple(row["detachment_id"] for row in faction_payload["detachments"]) == tuple(
            row.detachment_id for row in owned_detachments
        )
        assert faction_payload["detachment_status_counts"] == _status_counts(
            detachment_rows[row.detachment_id] for row in owned_detachments
        )
        for source_detachment, detachment_payload in zip(
            owned_detachments,
            faction_payload["detachments"],
            strict=True,
        ):
            detachment_manifest = detachment_rows[source_detachment.detachment_id]
            assert detachment_payload == {
                "detachment_id": source_detachment.detachment_id,
                "detachment_name": source_detachment.name,
                "semantic_status": detachment_manifest.semantic_status.value,
                "execution_record_count": len(detachment_manifest.execution_record_ids),
                "source_ids": list(detachment_manifest.source_ids),
                "module_path": detachment_manifest.module_path,
            }


def test_runtime_semantic_coverage_has_one_source_package_identity() -> None:
    payload = runtime_content_semantic_coverage_payload()
    manifest_rows = generated_runtime_content_rows()

    assert {row.source_package_id for row in manifest_rows} == {payload["source_package_id"]}
    assert {
        row.source_package_hash for row in manifest_rows if row.source_package_hash is not None
    } == {payload["source_package_hash"]}


def _status_counts(rows: Iterable[RuntimeContentManifestRow]) -> dict[str, int]:
    counts = Counter(row.semantic_status for row in rows)
    return {status.value: counts[status] for status in RuntimeContentSemanticStatus}
