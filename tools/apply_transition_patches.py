from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_patch import (
    PatchedSourceArtifact,
    SourcePatchDiagnostic,
    SourcePatchDiagnosticReason,
    SourcePatchError,
    SourceTransitionPatchPackage,
    SourceTransitionPatchPackagePayload,
    apply_transition_patch_package,
)
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)


def apply_transition_patches(
    *,
    input_dir: Path,
    output_dir: Path,
    patch_package: SourceTransitionPatchPackage,
    raise_on_blocking: bool = True,
) -> tuple[PatchedSourceArtifact, ...]:
    artifact_paths = tuple(
        sorted(
            path for path in input_dir.glob("*.json") if path.name != "source_package_manifest.json"
        )
    )
    if not artifact_paths:
        raise ValueError("input_dir must contain at least one source artifact JSON file.")

    artifacts = tuple(_load_source_artifact(path) for path in artifact_paths)
    missing_table_diagnostics = _missing_source_table_diagnostics(
        artifacts=artifacts,
        patch_package=patch_package,
    )
    if missing_table_diagnostics:
        if raise_on_blocking:
            missing_tables = ", ".join(
                sorted({diagnostic.source_table for diagnostic in missing_table_diagnostics})
            )
            raise SourcePatchError(
                "Transition patch package references missing source artifact tables: "
                f"{missing_tables}."
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_diagnostics_artifact(
            output_dir=output_dir,
            patch_package=patch_package,
            diagnostics=missing_table_diagnostics,
        )
        return ()

    patched_artifacts = tuple(
        apply_transition_patch_package(
            artifact=artifact,
            patch_package=patch_package,
            raise_on_blocking=raise_on_blocking,
        )
        for artifact in artifacts
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for patched in patched_artifacts:
        (output_dir / f"{patched.source_table}.patched.json").write_bytes(patched.to_json_bytes())

    (output_dir / "transition_patch_package.json").write_text(
        json.dumps(patch_package.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return patched_artifacts


def _load_source_artifact(path: Path) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_payload(
        cast(
            WahapediaJsonArtifactPayload,
            json.loads(path.read_text(encoding="utf-8")),
        )
    )


def _missing_source_table_diagnostics(
    *,
    artifacts: tuple[WahapediaJsonArtifact, ...],
    patch_package: SourceTransitionPatchPackage,
) -> tuple[SourcePatchDiagnostic, ...]:
    artifact_tables = {artifact.source_table for artifact in artifacts}
    missing_tables = {
        operation.target.source_table
        for operation in patch_package.operations
        if operation.target.source_table not in artifact_tables
    }
    diagnostics = [
        SourcePatchDiagnostic(
            operation_id=operation.operation_id,
            source_table=operation.target.source_table,
            source_row_id=None,
            reason=SourcePatchDiagnosticReason.MISSING_SOURCE_TABLE,
            message=(
                "Patch target source table has no matching source artifact in the input directory."
            ),
            blocking=True,
        )
        for operation in patch_package.operations
        if operation.target.source_table in missing_tables
    ]
    return tuple(
        sorted(
            diagnostics,
            key=lambda diagnostic: (diagnostic.source_table, diagnostic.operation_id),
        )
    )


def _write_diagnostics_artifact(
    *,
    output_dir: Path,
    patch_package: SourceTransitionPatchPackage,
    diagnostics: tuple[SourcePatchDiagnostic, ...],
) -> None:
    output_dir.joinpath("transition_patch_diagnostics.json").write_text(
        json.dumps(
            {
                "schema_version": "phase17a1-transition-patch-diagnostics-v1",
                "patch_package_hash": patch_package.package_hash(),
                "missing_tables": sorted({diagnostic.source_table for diagnostic in diagnostics}),
                "diagnostics": [diagnostic.to_payload() for diagnostic in diagnostics],
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Phase 17A.1 transition patches to source-mirror artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--patch-package", required=True)
    parser.add_argument("--allow-diagnostics", action="store_true")
    args = parser.parse_args()

    patch_package = SourceTransitionPatchPackage.from_payload(
        cast(
            SourceTransitionPatchPackagePayload,
            json.loads(Path(args.patch_package).read_text(encoding="utf-8")),
        )
    )
    apply_transition_patches(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        patch_package=patch_package,
        raise_on_blocking=not args.allow_diagnostics,
    )


if __name__ == "__main__":
    main()
