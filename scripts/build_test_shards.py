from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
EXCLUDED_TEST_DIRECTORIES = {"benchmarks", "code_quality"}
SHARD_STRATEGY = "largest-processing-time-by-historical-file-duration"


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
    durations = _rounded_durations(_durations_from_junit(args.junit.resolve()))
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
    expected = frozenset(_behavioral_test_files())
    for testcase in root.iter("testcase"):
        duration_text = testcase.get("time")
        if duration_text is None:
            raise SystemExit("Every JUnit testcase must contain a time attribute.")
        test_file = _test_file_from_testcase(testcase, expected=expected)
        try:
            duration = float(duration_text)
        except ValueError as error:
            raise SystemExit(f"JUnit testcase has an invalid duration: {duration_text}") from error
        if not math.isfinite(duration) or duration < 0.0:
            raise SystemExit(
                f"JUnit testcase duration must be finite and non-negative: {duration_text}"
            )
        durations[test_file] = durations.get(test_file, 0.0) + duration

    expected_set = set(expected)
    measured = set(durations)
    missing = sorted(expected_set - measured)
    unexpected = sorted(measured - expected_set)
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations


def _test_file_from_testcase(
    testcase: ET.Element,
    *,
    expected: frozenset[str],
) -> str:
    file_attribute = testcase.get("file")
    if file_attribute is not None:
        normalized = file_attribute.replace("\\", "/")
        file_path = PurePosixPath(normalized)
        if file_path.is_absolute() or ".." in file_path.parts:
            raise SystemExit(f"JUnit testcase file is not repository-relative: {file_attribute}")
        test_file = file_path.as_posix()
        if test_file not in expected:
            raise SystemExit(f"JUnit testcase file is not a behavioral test: {file_attribute}")
        return test_file

    classname = testcase.get("classname")
    if classname is None:
        raise SystemExit("Every JUnit testcase must contain a file or classname attribute.")
    classname_parts = classname.split(".")
    for part_count in range(len(classname_parts), 0, -1):
        candidate = "/".join(classname_parts[:part_count]) + ".py"
        if candidate in expected:
            return candidate
    raise SystemExit(f"JUnit testcase classname does not identify a behavioral test: {classname}")


def _rounded_durations(durations: dict[str, float]) -> dict[str, float]:
    return {path: round(duration, 3) for path, duration in durations.items()}


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
    summary = _summary_payload(shards=shards, durations=durations)
    (output_dir / "durations.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _check_manifests(output_dir=output_dir, shard_count=len(shards))


def _check_manifests(*, output_dir: Path, shard_count: int) -> None:
    expected = set(_behavioral_test_files())
    seen: dict[str, int] = {}
    manifest_entries: dict[int, tuple[str, ...]] = {}
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
        manifest_entries[shard_id] = entries
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
    try:
        summary: object = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Shard duration summary is not valid JSON: {summary_path}") from error
    durations = _summary_durations(summary=summary, expected=expected)
    shards = _balanced_shards(durations=durations, shard_count=shard_count)
    for shard in shards:
        if manifest_entries[shard.shard_id] != shard.test_files:
            manifest_path = output_dir / f"shard-{shard.shard_id}.txt"
            raise SystemExit(
                f"Shard manifest does not match the duration-balanced assignment: {manifest_path}"
            )
    expected_summary = _summary_payload(shards=shards, durations=durations)
    if summary != expected_summary:
        raise SystemExit("Shard duration summary does not match the committed manifests.")


def _summary_payload(
    *,
    shards: tuple[Shard, ...],
    durations: dict[str, float],
) -> dict[str, object]:
    return {
        "strategy": SHARD_STRATEGY,
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


def _summary_durations(*, summary: object, expected: set[str]) -> dict[str, float]:
    if not isinstance(summary, dict):
        raise SystemExit("Shard duration summary must be a JSON object.")
    summary_fields = cast(dict[str, object], summary)
    files_value = summary_fields.get("files")
    if not isinstance(files_value, dict):
        raise SystemExit("Shard duration summary must contain a files object.")
    files = cast(dict[object, object], files_value)
    durations: dict[str, float] = {}
    for path, duration in files.items():
        if not isinstance(path, str):
            raise SystemExit("Shard duration summary file paths must be strings.")
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise SystemExit(f"Shard duration for {path} must be numeric.")
        normalized_duration = float(duration)
        if not math.isfinite(normalized_duration) or normalized_duration < 0.0:
            raise SystemExit(f"Shard duration for {path} must be finite and non-negative.")
        durations[path] = normalized_duration

    measured = set(durations)
    missing = sorted(expected - measured)
    unexpected = sorted(measured - expected)
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations


def _coverage_error(*, missing: list[str], unexpected: list[str]) -> str:
    details = ["Behavioral test shard coverage is not exact."]
    if missing:
        details.append("Missing test files:\n" + "\n".join(missing))
    if unexpected:
        details.append("Unexpected test files:\n" + "\n".join(unexpected))
    return "\n".join(details)


if __name__ == "__main__":
    raise SystemExit(main())
