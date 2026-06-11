from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_patch import (
    SourceTransitionPatchPackage,
    SourceTransitionPatchPackagePayload,
)


def build_transition_patch_package(
    *,
    input_path: Path,
    output_path: Path,
) -> SourceTransitionPatchPackage:
    payload = cast(
        SourceTransitionPatchPackagePayload,
        json.loads(input_path.read_text(encoding="utf-8")),
    )
    package = SourceTransitionPatchPackage.from_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(package.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canonicalize and validate a Phase 17A.1 transition patch package."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    build_transition_patch_package(
        input_path=Path(args.input),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
