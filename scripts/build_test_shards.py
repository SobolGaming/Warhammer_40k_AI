from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
EXCLUDED_TEST_DIRECTORIES = {"benchmarks", "code_quality"}


@dataclass(frozen=True, slots=True)
class Shard:
    shard_id: int
    duration_seconds: float
    test_files: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify duration-balanced behavioral pytest shard manifests."
    )
    parser.add_argument("--check", action="store_true", help="Verify committed manifests.")
    parser.add_argument("--junit", type=Path, help="JUnit profile used to build manifests.")
    parser.add_argument("--shard-count", type=int, default=4)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "ci" / "test_shards",
    )
    args = parser.parse_args()
    if args.shard_count < 1:
        parser.error("--shard-count must be positive")
    output_dir = args.output_dir.resolve()
    if args.check:
        _check_manifests(output_dir=output_dir, shard_count=args.shard_count)
        return 0
    if args.junit is None:
        parser.error("--junit is required unless --check is used")
    durations = _durations_from_junit(args.junit.resolve())
    shards = _balanced_shards(durations=durations, shard_count=args.shard_count)
    _write_manifests(output_dir=output_dir, shards=shards, durations=durations)
    return 0


def _behavioral_test_files() -> tuple[str, ...]:
    paths = (
        path
        for path in TESTS_ROOT.rglob("test_*.py")
        if not EXCLUDED_TEST_DIRECTORIES.intersection(path.relative_to(TESTS_ROOT).parts)
    )
    return tuple(sorted(path.relative_to(REPOSITORY_ROOT).as_posix() for path in paths))


def _durations_from_junit(junit_path: Path) -> dict[str, float]:
    if not junit_path.is_file():
        raise SystemExit(f"JUnit profile does not exist: {junit_path}")
    root = ET.parse(junit_path).getroot()
    durations: dict[str, float] = {}
    for testcase in root.iter("testcase"):
        classname = testcase.get("classname")
        duration_text = testcase.get("time")
        if classname is None or duration_text is None:
            raise SystemExit("Every JUnit testcase must contain classname and time attributes.")
        test_file = f"{classname.replace('.', '/')}.py"
        if not test_file.startswith("tests/"):
            raise SystemExit(f"JUnit testcase is outside tests/: {classname}")
        durations[test_file] = durations.get(test_file, 0.0) + float(duration_text)

    expected = set(_behavioral_test_files())
    measured = set(durations)
    missing = sorted(expected - measured)
    unexpected = sorted(measured - expected)
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations


def _balanced_shards(*, durations: dict[str, float], shard_count: int) -> tuple[Shard, ...]:
    assignments: list[list[str]] = [[] for _ in range(shard_count)]
    totals = [0.0] * shard_count
    for test_file, duration in sorted(durations.items(), key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: (totals[index], index))
        assignments[shard_index].append(test_file)
        totals[shard_index] += duration
    return tuple(
        Shard(
            shard_id=index + 1,
            duration_seconds=totals[index],
            test_files=tuple(sorted(assignments[index])),
        )
        for index in range(shard_count)
    )


def _write_manifests(
    *,
    output_dir: Path,
    shards: tuple[Shard, ...],
    durations: dict[str, float],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_manifest in output_dir.glob("shard-*.txt"):
        stale_manifest.unlink()
    for shard in shards:
        manifest_path = output_dir / f"shard-{shard.shard_id}.txt"
        manifest_path.write_text("\n".join(shard.test_files) + "\n", encoding="utf-8")
    summary = {
        "strategy": "largest-processing-time-by-historical-file-duration",
        "shard_count": len(shards),
        "total_test_duration_seconds": round(sum(durations.values()), 3),
        "files": {path: round(duration, 3) for path, duration in sorted(durations.items())},
        "shards": [
            {
                "shard_id": shard.shard_id,
                "duration_seconds": round(shard.duration_seconds, 3),
                "test_file_count": len(shard.test_files),
            }
            for shard in shards
        ],
    }
    (output_dir / "durations.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _check_manifests(output_dir=output_dir, shard_count=len(shards))


def _check_manifests(*, output_dir: Path, shard_count: int) -> None:
    expected = set(_behavioral_test_files())
    seen: dict[str, int] = {}
    for shard_id in range(1, shard_count + 1):
        manifest_path = output_dir / f"shard-{shard_id}.txt"
        if not manifest_path.is_file():
            raise SystemExit(f"Missing shard manifest: {manifest_path}")
        entries = tuple(
            line.strip()
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if entries != tuple(sorted(entries)):
            raise SystemExit(f"Shard manifest must be sorted: {manifest_path}")
        for entry in entries:
            seen[entry] = seen.get(entry, 0) + 1

    missing = sorted(expected - set(seen))
    unexpected = sorted(set(seen) - expected)
    duplicates = sorted(path for path, count in seen.items() if count != 1)
    if missing or unexpected or duplicates:
        detail = _coverage_error(missing=missing, unexpected=unexpected)
        if duplicates:
            detail += "\nDuplicate test files:\n" + "\n".join(duplicates)
        raise SystemExit(detail)

    summary_path = output_dir / "durations.json"
    if not summary_path.is_file():
        raise SystemExit(f"Missing shard duration summary: {summary_path}")
    summary = cast(dict[str, object], json.loads(summary_path.read_text(encoding="utf-8")))
    if summary.get("shard_count") != shard_count:
        raise SystemExit("Shard duration summary count does not match the manifests.")


def _coverage_error(*, missing: list[str], unexpected: list[str]) -> str:
    details = ["Behavioral test shard coverage is not exact."]
    if missing:
        details.append("Missing test files:\n" + "\n".join(missing))
    if unexpected:
        details.append("Unexpected test files:\n" + "\n".join(unexpected))
    return "\n".join(details)


if __name__ == "__main__":
    raise SystemExit(main())
