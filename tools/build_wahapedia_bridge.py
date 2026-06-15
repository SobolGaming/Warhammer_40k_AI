from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.wahapedia_bridge import build_wahapedia_canonical_bridge_artifacts
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)


def load_wahapedia_artifact(path: Path) -> WahapediaJsonArtifact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("Wahapedia artifact JSON must contain an object.")
    return WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build canonical bridge JSON from Wahapedia artifacts."
    )
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--artifact", action="append", type=Path, required=True)
    parser.add_argument("--datasheet-id", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=tuple(load_wahapedia_artifact(path) for path in args.artifact),
        bridge_package_id=DataPackageId(
            namespace=args.namespace,
            package_name=args.package_name,
            version=args.package_version,
        ),
        datasheet_ids=tuple(args.datasheet_id),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for artifact in bridge_artifacts:
        output_path = args.output_dir / f"{artifact.source_table}.json"
        output_path.write_text(
            json.dumps(artifact.to_payload(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
