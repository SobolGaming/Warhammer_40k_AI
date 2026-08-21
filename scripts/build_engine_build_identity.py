from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
MANIFEST_PATH = SRC_ROOT / "warhammer40k_core" / "_engine_build_manifest.json"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from warhammer40k_core.build_identity import (  # noqa: E402
    EngineBuildIdentityError,
    build_engine_manifest_payload,
    canonical_engine_build_manifest_text,
)


class EngineBuildIdentityGenerationError(RuntimeError):
    """Raised when the generated engine build manifest is stale or unavailable."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify the deterministic engine runtime identity manifest."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        expected_payload = build_engine_manifest_payload()
    except EngineBuildIdentityError as exc:
        raise EngineBuildIdentityGenerationError(
            "The authoritative engine runtime inventory could not be fingerprinted."
        ) from exc
    expected_text = canonical_engine_build_manifest_text(expected_payload)
    if args.check:
        _check_manifest(expected_text)
        print(f"Engine build identity is current: {expected_payload['build_id']}")
        return 0
    MANIFEST_PATH.write_text(expected_text, encoding="utf-8", newline="\n")
    _check_manifest(expected_text)
    print(f"Wrote engine build identity: {expected_payload['build_id']}")
    return 0


def _check_manifest(expected_text: str) -> None:
    if not MANIFEST_PATH.is_file():
        raise EngineBuildIdentityGenerationError("The generated engine build manifest is missing.")
    actual_text = MANIFEST_PATH.read_text(encoding="utf-8")
    if actual_text == expected_text:
        return
    difference = "".join(
        difflib.unified_diff(
            actual_text.splitlines(keepends=True),
            expected_text.splitlines(keepends=True),
            fromfile=str(MANIFEST_PATH),
            tofile="expected engine build manifest",
        )
    )
    raise EngineBuildIdentityGenerationError(
        "The generated engine build manifest is stale.\n" + difference
    )


if __name__ == "__main__":
    raise SystemExit(main())
