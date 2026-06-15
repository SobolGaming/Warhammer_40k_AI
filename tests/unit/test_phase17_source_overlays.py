from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from tools.apply_source_overlays import apply_source_overlays

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
    SourceOverlayError,
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.source_reference_generation import (
    SourceReferenceCatalog,
    SourceReferenceCatalogPayload,
    build_source_reference_catalog,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


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


def _updated_row_after_first_operation(
    artifact: WahapediaJsonArtifact,
    *,
    package_hash_placeholder: bool,
) -> NormalizedSourceRow:
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update-angels-fury",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "<p>Roll D6 within 12 inches.</p>"),),
            ),
        )
    )
    if package_hash_placeholder:
        assert package.package_hash()
    return apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0].rows[0]


def _operation(
    *,
    op_id: str,
    order_index: int,
    kind: SourceOverlayOperationKind,
    source_row_id: str,
    expected_preimage_hash: str | None,
    fields: tuple[tuple[str, str], ...],
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=kind,
        target_edition="warhammer-40000-11th",
        source_table="Abilities",
        source_row_id=source_row_id,
        source_reference="gw-11e-transition-update:p1",
        effective_date="2026-06-01",
        reason="Apply 11e transition update.",
        expected_preimage_hash=expected_preimage_hash,
        fields=fields,
    )


def _overlay_pack(
    *,
    operations: tuple[SourceOverlayOperation, ...],
    package_id: DataPackageId | None = None,
) -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=package_id if package_id is not None else _overlay_package_id(),
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        target_edition="warhammer-40000-11th",
        effective_date="2026-06-01",
        operations=operations,
    )


def _release_manifest(
    *,
    overlay_package_ids: tuple[DataPackageId, ...],
) -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="core-11-from-wahapedia-bridge-test",
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        base_source_edition=_previous_source_edition(),
        target_edition="warhammer-40000-11th",
        overlay_package_ids=overlay_package_ids,
    )


def _abilities_artifact() -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(
            table_name="Abilities",
            csv_text='id,faction_id,name,description\nability-1,SM,Angels Fury,"Roll D3."\n',
        ),
    )


def _row_by_id(artifact: OverlaySourceArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="bridge-2026-06-01",
    )


def _overlay_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-overlay",
        version="2026-06-01",
    )


def _reference_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-reference",
        version="2026-06-01",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="core-11-from-wahapedia-bridge-test",
        source_date=date(2026, 6, 1),
    )


def _previous_source_edition() -> str:
    return "warhammer-40000-" + "1" + "0th"
