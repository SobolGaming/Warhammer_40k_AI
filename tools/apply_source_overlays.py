from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
    SourceOverlayDiagnostic,
    SourceOverlayError,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    build_source_release_overlay_report,
)
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact, PatchedSourceArtifactPayload
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)


def apply_source_overlays(
    *,
    input_dir: Path,
    output_dir: Path,
    release_manifest: SourceReleaseManifest,
    overlay_packs: tuple[SourceOverlayPack, ...],
    raise_on_blocking: bool = True,
) -> tuple[OverlaySourceArtifact, ...]:
    source_artifacts = _load_source_artifacts(input_dir)
    report = build_source_release_overlay_report(
        source_artifacts=source_artifacts,
        release_manifest=release_manifest,
        overlay_packs=overlay_packs,
    )
    overlay_artifacts = report.artifacts
    if report.blocking_diagnostics():
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_overlay_diagnostics(
            output_dir=output_dir,
            release_manifest=release_manifest,
            diagnostics=report.all_diagnostics(),
        )
        if raise_on_blocking:
            raise SourceOverlayError("Source overlay application failed with diagnostics.")
        return overlay_artifacts

    output_dir.mkdir(parents=True, exist_ok=True)
    for artifact in overlay_artifacts:
        (output_dir / f"{artifact.source_table}.overlay.json").write_bytes(artifact.to_json_bytes())
    (output_dir / "source_release_manifest.json").write_text(
        json.dumps(release_manifest.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    for pack in overlay_packs:
        (output_dir / f"{pack.package_id.package_name}.overlay-pack.json").write_text(
            json.dumps(pack.to_payload(), sort_keys=True, indent=2),
            encoding="utf-8",
        )
    return overlay_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply immutable edition source overlay packs to source artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release-manifest", required=True)
    parser.add_argument("--overlay-pack", action="append", required=True)
    args = parser.parse_args()

    release_manifest = SourceReleaseManifest.from_payload(
        cast(
            SourceReleaseManifestPayload,
            json.loads(Path(args.release_manifest).read_text(encoding="utf-8")),
        )
    )
    overlay_packs = tuple(
        SourceOverlayPack.from_payload(
            cast(
                SourceOverlayPackPayload,
                json.loads(Path(path).read_text(encoding="utf-8")),
            )
        )
        for path in args.overlay_pack
    )
    apply_source_overlays(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        release_manifest=release_manifest,
        overlay_packs=overlay_packs,
    )


def _load_source_artifacts(
    input_dir: Path,
) -> tuple[
    WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact,
    ...,
]:
    artifacts: list[WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact] = []
    for path in sorted(input_dir.glob("*.json")):
        if path.name in {"source_package_manifest.json", "source_snapshot.json"}:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "overlay_package_hashes" in payload:
            artifacts.append(
                OverlaySourceArtifact.from_payload(cast(OverlaySourceArtifactPayload, payload))
            )
        elif "patch_package_hash" in payload:
            artifacts.append(
                PatchedSourceArtifact.from_payload(cast(PatchedSourceArtifactPayload, payload))
            )
        elif "source_checksum_sha256" in payload:
            artifacts.append(
                WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
            )
    if not artifacts:
        raise ValueError("input_dir must contain at least one source artifact JSON file.")
    return tuple(artifacts)


def _write_overlay_diagnostics(
    *,
    output_dir: Path,
    release_manifest: SourceReleaseManifest,
    diagnostics: tuple[SourceOverlayDiagnostic, ...],
) -> None:
    output_dir.joinpath("source_overlay_diagnostics.json").write_text(
        json.dumps(
            {
                "schema_version": "phase17-source-overlay-diagnostics-v1",
                "release_hash": release_manifest.release_hash(),
                "diagnostics": [diagnostic.to_payload() for diagnostic in diagnostics],
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
