from __future__ import annotations

import argparse
from pathlib import Path


def check_shard_coverage(root: Path, *, shard_count: int) -> tuple[Path, ...]:
    """Require exactly one nonempty coverage file from each expected artifact."""
    if shard_count < 1:
        raise SystemExit("Coverage shard count must be positive.")
    expected_artifacts = {f"behavior-coverage-{shard}" for shard in range(1, shard_count + 1)}
    if not root.is_dir() or {path.name for path in root.iterdir()} != expected_artifacts:
        raise SystemExit("Downloaded coverage artifact inventory is not exact.")
    files: list[Path] = []
    for shard in range(1, shard_count + 1):
        artifact = root / f"behavior-coverage-{shard}"
        expected_name = f".coverage.{shard}"
        if not artifact.is_dir() or {path.name for path in artifact.iterdir()} != {expected_name}:
            raise SystemExit(
                f"Coverage artifact {artifact.name} must contain only {expected_name}."
            )
        path = artifact / expected_name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Coverage file {path} is missing or empty.")
        files.append(path)
    return tuple(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify exact downloaded shard coverage inputs.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--shard-count", type=int, required=True)
    args = parser.parse_args()
    files = check_shard_coverage(args.root, shard_count=args.shard_count)
    print(f"Verified {len(files)} complete shard coverage artifacts.")


if __name__ == "__main__":
    main()
