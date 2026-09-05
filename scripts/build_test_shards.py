from __future__ import annotations

import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from statistics import median
from typing import TypedDict, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
EXCLUDED_TEST_DIRECTORIES = {"benchmarks", "code_quality"}
SHARD_STRATEGY = "largest-processing-time-by-median-file-duration"


class ProfileEvidence(TypedDict):
    source: str
    junit_sha256: list[str]
    test_cases: int
    test_files: int


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
    parser.add_argument(
        "--junit",
        type=Path,
        action="append",
        help="Complete run: XML file or directory of shard XMLs; repeat for medians.",
    )
    parser.add_argument(
        "--profile-source",
        action="append",
        help="Run URL, commit and runner description, one per --junit.",
    )
    parser.add_argument("--shard-count", type=int, default=8)
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
    if args.profile_source is None or len(args.profile_source) != len(args.junit):
        parser.error("one --profile-source is required per --junit")
    durations, profiles = _profile_medians(tuple(args.junit), tuple(args.profile_source))
    durations = _rounded_durations(durations)
    shards = _balanced_shards(durations=durations, shard_count=args.shard_count)
    _write_manifests(output_dir=output_dir, shards=shards, durations=durations, profiles=profiles)
    return 0


def _behavioral_test_files() -> tuple[str, ...]:
    paths = (
        path
        for path in TESTS_ROOT.rglob("test_*.py")
        if not EXCLUDED_TEST_DIRECTORIES.intersection(path.relative_to(TESTS_ROOT).parts)
    )
    return tuple(sorted(path.relative_to(REPOSITORY_ROOT).as_posix() for path in paths))


def _profile_medians(
    paths: tuple[Path, ...],
    sources: tuple[str, ...],
) -> tuple[dict[str, float], tuple[ProfileEvidence, ...]]:
    if not paths or len(paths) != len(sources) or any(not source.strip() for source in sources):
        raise SystemExit("Each complete JUnit run requires a non-empty source description.")
    profiles: list[ProfileEvidence] = []
    measurements: list[dict[str, float]] = []
    for path, source in zip(paths, sources, strict=True):
        durations, hashes, case_count = _read_junit_profile(path)
        measurements.append(durations)
        profiles.append(
            ProfileEvidence(
                source=source,
                junit_sha256=list(hashes),
                test_cases=case_count,
                test_files=len(durations),
            )
        )
    return (
        {name: median(run[name] for run in measurements) for name in measurements[0]},
        tuple(profiles),
    )


def _durations_from_junit(junit_path: Path) -> dict[str, float]:
    return _read_junit_profile(junit_path)[0]


def _read_junit_profile(junit_path: Path) -> tuple[dict[str, float], tuple[str, ...], int]:
    paths = tuple(sorted(junit_path.rglob("*.xml"))) if junit_path.is_dir() else (junit_path,)
    if not paths or any(not path.is_file() for path in paths):
        raise SystemExit(f"JUnit profile does not exist or is empty: {junit_path}")
    durations: dict[str, float] = {}
    seen: set[tuple[str, str, str]] = set()
    hashes: list[str] = []
    expected = frozenset(_behavioral_test_files())
    for path in paths:
        content = path.read_bytes()
        hashes.append(hashlib.sha256(content).hexdigest())
        root = ET.fromstring(content)
        for suite in root.iter("testsuite"):
            declared = suite.get("tests")
            if (
                declared is None
                or not declared.isdecimal()
                or int(declared) != len(list(suite.iter("testcase")))
            ):
                raise SystemExit(f"JUnit suite testcase count is missing or drifted: {path}")
        for testcase in root.iter("testcase"):
            if any(testcase.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise SystemExit(f"JUnit profile contains unsuccessful cases: {path}")
            duration_text = testcase.get("time")
            if duration_text is None:
                raise SystemExit("Every JUnit testcase must contain a time attribute.")
            test_file = _test_file_from_testcase(testcase, expected=expected)
            name = testcase.get("name")
            if not name:
                raise SystemExit("Every JUnit testcase must have a non-empty name.")
            identity = (test_file, testcase.get("classname", ""), name)
            if identity in seen:
                raise SystemExit(f"Duplicate JUnit testcase: {identity}")
            seen.add(identity)
            try:
                duration = float(duration_text)
            except ValueError as error:
                raise SystemExit(
                    f"JUnit testcase has an invalid duration: {duration_text}"
                ) from error
            if not math.isfinite(duration) or duration < 0.0:
                raise SystemExit(
                    f"JUnit testcase duration must be finite and non-negative: {duration_text}"
                )
            durations[test_file] = durations.get(test_file, 0.0) + duration
    missing = sorted(set(expected) - set(durations))
    unexpected = sorted(set(durations) - set(expected))
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations, tuple(sorted(hashes)), len(seen)


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
    profiles: tuple[ProfileEvidence, ...] = (),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_manifest in output_dir.glob("shard-*.txt"):
        stale_manifest.unlink()
    for shard in shards:
        manifest_path = output_dir / f"shard-{shard.shard_id}.txt"
        manifest_path.write_text("\n".join(shard.test_files) + "\n", encoding="utf-8")
    summary = _summary_payload(shards=shards, durations=durations, profiles=profiles)
    (output_dir / "durations.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _check_manifests(output_dir=output_dir, shard_count=len(shards))


def _check_manifests(*, output_dir: Path, shard_count: int) -> None:
    expected = set(_behavioral_test_files())
    manifest_names = {path.name for path in output_dir.glob("shard-*.txt")}
    if manifest_names != {f"shard-{index}.txt" for index in range(1, shard_count + 1)}:
        raise SystemExit("Shard manifest count does not match --shard-count.")
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
    profiles = _summary_profiles(summary)
    expected_summary = _summary_payload(shards=shards, durations=durations, profiles=profiles)
    if summary != expected_summary:
        raise SystemExit("Shard duration summary does not match the committed manifests.")


def _summary_payload(
    *,
    shards: tuple[Shard, ...],
    durations: dict[str, float],
    profiles: tuple[ProfileEvidence, ...] = (),
) -> dict[str, object]:
    return {
        "strategy": SHARD_STRATEGY,
        "profiles": list(profiles),
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


def _summary_profiles(summary: object) -> tuple[ProfileEvidence, ...]:
    if not isinstance(summary, dict) or not isinstance(summary.get("profiles"), list):
        raise SystemExit("Shard summary requires profile evidence.")
    profiles = cast(list[object], summary["profiles"])
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {
            "source",
            "junit_sha256",
            "test_cases",
            "test_files",
        }:
            raise SystemExit("Shard profile evidence fields are invalid.")
        if not isinstance(item["source"], str) or not item["source"].strip():
            raise SystemExit("Shard profile requires a source description.")
        hashes = item["junit_sha256"]
        if (
            not isinstance(hashes, list)
            or not hashes
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or set(value) - set("0123456789abcdef")
                for value in hashes
            )
        ):
            raise SystemExit("Shard profile requires SHA-256 report identities.")
        if any(type(item[key]) is not int or item[key] < 1 for key in ("test_cases", "test_files")):
            raise SystemExit("Shard profile requires positive inventory counts.")
    return tuple(cast(ProfileEvidence, item) for item in profiles)


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
