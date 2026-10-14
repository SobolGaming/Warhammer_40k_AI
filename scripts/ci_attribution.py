"""Bounded Linux-only diagnostic campaign; never replaces an ordinary CI gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ci_attribution_supervisor import run_owned

BASE = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
TREE = "6ed90ab9ac6ff06cd259ac96fe53995eae0a9cf1"
ADDITIONS = {
    ".github/workflows/linux-attribution.yml",
    "scripts/ci_attribution.py",
    "scripts/ci_attribution_plugin.py",
    "scripts/ci_attribution_profile.py",
    "scripts/ci_attribution_supervisor.py",
    "scripts/check_ci_attribution_supervisor.py",
    "scripts/check_ci_attribution_commands.py",
    "tests/code_quality/d02_assessment_history.py",
    "docs/performance/policy-v3/d02-final-history/assessment.json",
    "docs/performance/policy-v3/d02-final-history/operation-map.json",
    "docs/performance/policy-v3/d02-final-history/test_d02_performance_assessment.py.txt",
}
# The existing mandatory performance-policy gate validates this current PR metadata.
# No historical measurement, policy or baseline pin is exempt from byte preservation.
ASSESSMENT = "docs/performance/change-assessment.json"
OPERATION_MAP = "docs/performance/policy-v3/operation-map.json"
REVIEWED_OPERATION_MAP_SHA256 = "c8ab4110c144a5f133ba0290e09176f99d890d26fdde0a23fee7698bc3dc854e"
PRESERVED_D02_TEST = "tests/code_quality/test_d02_performance_assessment.py"
REVIEWED_D02_TEST_SHA256 = "4a2cc86f393649134f0669be775ac4f44dce749583567f999ecd052b355a8eb2"
CRITICAL = (
    "tests/unit/test_critical_hits.py::"
    "test_critical_consumers_through_facade_restore_and_replay[fight]"
)
QUALITY = (
    "tests/code_quality/test_phase18m_conformance_boundary.py::"
    "test_external_contract_write_mode_removes_orphan_generated_fixture"
)
RUNS = (
    ("critical", "control", 900),
    ("critical", "boundaries", 1200),
    ("quality", "control", 420),
    ("quality", "profile", 900),
)


def write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def tracked_snapshot() -> dict[str, str]:
    names = git("ls-files", "-z").decode().split("\0")[:-1]
    return {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in names}


def verify_baseline() -> dict[str, str]:
    if git("rev-parse", f"{BASE}^{{tree}}").decode().strip() != TREE:
        raise RuntimeError("Baseline tree differs from reviewed merged main")
    git("merge-base", "--is-ancestor", BASE, "HEAD")
    changes = git("diff", "--name-status", BASE, "HEAD").decode().splitlines()
    expected_changes = {f"A\t{path}" for path in ADDITIONS} | {
        f"M\t{OPERATION_MAP}",
        f"M\t{PRESERVED_D02_TEST}",
    }
    if set(changes) not in (expected_changes, expected_changes | {f"M\t{ASSESSMENT}"}):
        raise RuntimeError(
            "Unexpected diagnostic diff (only additions, pinned map/test and assessment allowed): "
            f"{changes!r}"
        )
    git("diff", "--exit-code", "HEAD", "--")
    expected = git("ls-tree", "-r", "-z", BASE).split(b"\0")[:-1]
    for entry in expected:
        metadata, name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        path = Path(name.decode())
        if kind != b"blob" or mode not in (b"100644", b"100755") or path.is_symlink():
            raise RuntimeError(f"Unexpected baseline object: {entry!r}")
        payload = path.read_bytes()
        actual = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        if path.as_posix() == OPERATION_MAP:
            if hashlib.sha256(payload).hexdigest() != REVIEWED_OPERATION_MAP_SHA256:
                raise RuntimeError("Diagnostic operation map differs from reviewed bytes")
            continue
        if path.as_posix() == PRESERVED_D02_TEST:
            if hashlib.sha256(payload).hexdigest() != REVIEWED_D02_TEST_SHA256:
                raise RuntimeError("D02 historical test binding differs from reviewed bytes")
            continue
        if actual != oid.decode() and path.as_posix() != ASSESSMENT:
            raise RuntimeError(f"Baseline bytes changed: {path}")
    return tracked_snapshot()


def proc_file(name: str) -> str | None:
    path = Path(name)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def complete(node: str, directory: Path) -> bool:
    path = directory / "timing/controller.json"
    if not path.exists():
        return False
    timing = json.loads(path.read_bytes())
    reports = timing["reports"]
    return (
        timing["exit_status"] == 0
        and timing["collected_nodeids"] == [node]
        and len(reports) == 3
        and {(r["phase"], r["outcome"]) for r in reports}
        == {("setup", "passed"), ("call", "passed"), ("teardown", "passed")}
        and all(r["nodeid"] == node for r in reports)
    )


def build_command(sample: str, mode: str, directory: Path) -> list[str]:
    """Construct only a declared workload, with every output outside the checkout."""
    if (sample, mode) not in {(sample, mode) for sample, mode, _cap in RUNS}:
        raise ValueError(f"Unknown diagnostic invocation: {sample}/{mode}")
    directory = directory.resolve()
    repository = Path(__file__).resolve().parents[1]
    if directory.is_relative_to(repository):
        raise ValueError("Diagnostic outputs must be outside the checkout")
    node = CRITICAL if sample == "critical" else QUALITY
    args = [
        "-p",
        "scripts.ci_attribution_plugin",
        node,
        "-q",
        "-n",
        "0",
        "--basetemp",
        str(directory / "tmp"),
        "-o",
        f"cache_dir={directory / 'cache'}",
        f"--junitxml={directory / 'junit.xml'}",
    ]
    args += (
        ["--cov=warhammer40k_core", "--cov-branch", "--cov-report=", "--cov-fail-under=0"]
        if sample == "critical"
        else ["--no-cov"]
    )
    return (
        [sys.executable, "-m", "pytest", *args]
        if mode != "profile"
        else [
            sys.executable,
            "scripts/ci_attribution_profile.py",
            str(directory / "pytest.prof"),
            "pytest",
            *args,
        ]
    )


def invoke(sample: str, mode: str, cap: int, output: Path) -> dict[str, object]:
    import resource

    directory = (output / f"{sample}-{mode}").resolve()
    command = build_command(sample, mode, directory)
    directory.mkdir()
    node = CRITICAL if sample == "critical" else QUALITY
    environment = os.environ.copy()
    environment.update(
        {
            "ATTRIBUTION_NODEID": node,
            "ATTRIBUTION_CHILD_PROFILES": str(int(sample == "quality" and mode == "profile")),
            "ATTRIBUTION_RUN_OUTPUT": str(directory),
            "ATTRIBUTION_BOUNDARIES": str(int(mode == "boundaries")),
            "TEST_TIMING_DIR": str(directory / "timing"),
            "COVERAGE_FILE": str(directory / ".coverage"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    receipt = {
        "sample": sample,
        "mode": mode,
        "nodeid": node,
        "command": command,
        "timeout_seconds": cap,
        "start_utc": datetime.now(UTC).isoformat(),
        "workers": 1,
        "xdist": False,
        "coverage_branch": sample == "critical",
        "application_cache": (
            "fresh process; OS page cache uncontrolled; paired second run may be warmer"
        ),
        "measurement": "pytest process including imports, collection, setup, call and teardown",
    }
    write(directory / "pending.json", receipt)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (
        (directory / "stdout.txt").open("w") as stdout,
        (directory / "stderr.txt").open("w") as stderr,
    ):
        outcome = run_owned(command, timeout=cap, env=environment, stdout=stdout, stderr=stderr)
    # Only write receipts after unconditional group cleanup; write failures cannot leak children.
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt.update(
        {
            **outcome,
            "cpu_user_seconds": after.ru_utime - before.ru_utime,
            "cpu_system_seconds": after.ru_stime - before.ru_stime,
            "campaign_child_maxrss_kib": after.ru_maxrss,
            "memory_qualification": (
                "Linux RUSAGE_CHILDREN high-water across waited children so far; "
                "not sum of concurrent RSS"
            ),
            "passed": (
                outcome["exit_code"] == 0
                and not outcome["descendants_remained"]
                and complete(node, directory)
            ),
        }
    )
    write(directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if sys.platform != "linux" or not __debug__:
        raise RuntimeError("Native Linux and enabled assertions are required")
    if os.cpu_count() != 4:
        raise RuntimeError("Expected baseline GitHub runner class with four logical CPUs")
    if os.environ["GITHUB_RUN_ATTEMPT"] != "1":
        raise RuntimeError("Automatic reruns are outside this one-attempt diagnostic approval")
    if output.is_relative_to(Path.cwd()):
        raise RuntimeError("All diagnostic artifacts must be outside the tracked checkout")
    output.mkdir(parents=True, exist_ok=False)
    baseline = verify_baseline()
    write(output / "before.json", baseline)
    write(
        output / "environment.json",
        {
            "baseline": BASE,
            "tree": TREE,
            "head": git("rev-parse", "HEAD").decode().strip(),
            "platform": platform.platform(),
            "python": sys.version,
            "logical_cpus": os.cpu_count(),
            "cpuinfo": proc_file("/proc/cpuinfo"),
            "meminfo": proc_file("/proc/meminfo"),
            "cpu_quota": proc_file("/sys/fs/cgroup/cpu.max"),
            "memory_limit": proc_file("/sys/fs/cgroup/memory.max"),
            "runner": {
                k: os.environ.get(k)
                for k in (
                    "RUNNER_OS",
                    "RUNNER_ARCH",
                    "RUNNER_NAME",
                    "ImageOS",
                    "ImageVersion",
                    "GITHUB_RUN_ID",
                    "GITHUB_RUN_ATTEMPT",
                    "GITHUB_SHA",
                )
            },
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in (
                    "pytest",
                    "pytest-cov",
                    "pytest-xdist",
                    "coverage",
                    "numpy",
                    "shapely",
                    "z3-solver",
                )
            },
            "dependency_cache": (
                "setup-uv restore disabled; fresh RUNNER_TEMP cache; "
                "same installed lock for all four runs"
            ),
            "resources": (
                "one GitHub runner, one pytest process; quality generator children run sequentially"
            ),
            "comparability": (
                "attribution only; single-process focus differs from four-worker CI contention; "
                "no speedup claim"
            ),
        },
    )
    rows = []
    for sample, mode, cap in RUNS:
        if mode != "control" and not rows[-1]["passed"]:
            rows.append(
                {
                    "sample": sample,
                    "mode": mode,
                    "passed": False,
                    "not_run": "control failed or timed out; independent other sample still runs",
                }
            )
        else:
            rows.append(invoke(sample, mode, cap, output))
        if rows[-1].get("cancel_signal") is not None:
            write(output / "campaign.json", rows)
            return int(rows[-1]["exit_code"])
        current = tracked_snapshot()
        write(output / f"after-{sample}-{mode}.json", current)
        if current != baseline:
            write(output / "source-mismatch.json", {"before": baseline, "after": current})
            raise RuntimeError("Tracked source changed during diagnostic; stop campaign")
        write(output / "campaign.json", rows)
    write(
        output / "artifact-hashes.json",
        {
            str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    )
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
