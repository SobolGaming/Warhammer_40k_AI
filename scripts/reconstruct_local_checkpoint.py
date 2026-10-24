"""Offline explicit reconstruction; never overwrites a source or an existing file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from warhammer40k_core.adapters.checkpoint_reconstruction import (  # noqa: E402
    PROFILE_ID,
    reconstruct_local_checkpoint,
    verify_checkpoint_reconstruction,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=(PROFILE_ID,))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--verify", type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if args.verify is not None:
        package = json.loads(args.verify.read_bytes())
        session = verify_checkpoint_reconstruction(source.read_bytes(), package)
        print(f"Verified reconstructed checkpoint for {session.lifecycle.config.game_id}.")
        return 0
    output: Path = args.output.resolve()
    if output == source or output.exists():
        parser.error("Output must be a new file, separate from the original source.")
    package = reconstruct_local_checkpoint(source.read_bytes(), profile_id=args.profile)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(package, indent=2) + "\n")
    print(f"Created explicit reconstruction: {output}")
    print(f"Package content hash: {package['content_hash']}")
    print("Original preserved; exact replay applies to the reconstructed checkpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
