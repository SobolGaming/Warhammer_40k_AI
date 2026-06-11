from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_patch import (
    PatchedSourceArtifact,
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

    output_dir.mkdir(parents=True, exist_ok=True)
    patched_artifacts: list[PatchedSourceArtifact] = []
    for artifact_path in artifact_paths:
        artifact = WahapediaJsonArtifact.from_payload(
            cast(
                WahapediaJsonArtifactPayload,
                json.loads(artifact_path.read_text(encoding="utf-8")),
            )
        )
        patched = apply_transition_patch_package(
            artifact=artifact,
            patch_package=patch_package,
            raise_on_blocking=raise_on_blocking,
        )
        (output_dir / f"{patched.source_table}.patched.json").write_bytes(patched.to_json_bytes())
        patched_artifacts.append(patched)

    (output_dir / "transition_patch_package.json").write_text(
        json.dumps(patch_package.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return tuple(patched_artifacts)


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
