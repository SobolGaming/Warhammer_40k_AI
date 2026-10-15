"""Review candidate: one frozen implementation, two bounded serial diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from ci_attribution_supervisor import run_owned

HEAD = "1096f0526a892b0cb5d6fd93d5166df7b973fdea"
TREE = "255cb5f98af3dcf710a46a07901575b55e4b9da3"
NODE = (
    "tests/unit/test_critical_hits.py::"
    "test_critical_consumers_through_facade_restore_and_replay[fight]"
)
HARD_SECONDS = 1380
POSTCHECK_RESERVE = 60
FINAL_RESERVE = 5


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=30)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path, expected_digest):
    if digest(path) != expected_digest:
        raise ValueError("Manifest differs from independently reviewed binding")
    manifest = json.loads(path.read_bytes())
    if manifest["head"] != HEAD or manifest["tree"] != TREE:
        raise ValueError("Manifest implementation differs")
    return manifest


def check_sources(root, harness, manifest):
    if git(root, "rev-parse", "HEAD").decode().strip() != HEAD:
        raise ValueError("Frozen diagnostic implementation changed")
    if git(root, "rev-parse", "HEAD^{tree}").decode().strip() != TREE:
        raise ValueError("Frozen diagnostic tree changed")
    if git(root, "status", "--porcelain", "-uall"):
        raise ValueError("Diagnostic checkout is dirty")
    observed = set(git(root, "ls-files", "-z").decode().split("\0")[:-1])
    if observed != set(manifest["source"]):
        raise ValueError("Source membership drifted")
    for relative, expected in manifest["source"].items():
        path = root / relative
        data = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if path.is_symlink() or blob != expected:
            raise ValueError(f"Source bytes drifted: {relative}")
    for relative, expected in manifest["harness"].items():
        path = harness / relative
        if path.is_symlink() or digest(path) != expected:
            raise ValueError(f"Harness bytes drifted: {relative}")


def require_budget(remaining, seconds, stage):
    if remaining() < seconds:
        raise RuntimeError(f"First-timestamp deadline exhausted at {stage}")


def verify_for_launch(root, harness, manifest, remaining):
    check_sources(root, harness, manifest)
    require_budget(
        remaining, 600 + POSTCHECK_RESERVE + FINAL_RESERVE, "post-verification admission"
    )


def completion_status(receipts, remaining):
    return (
        remaining() >= FINAL_RESERVE
        and len(receipts) == 2
        and all(row["passed"] for row in receipts)
    )


def verify_after_invocation(root, harness, manifest, remaining):
    check_sources(root, harness, manifest)
    require_budget(remaining, FINAL_RESERVE, "required source post-check")


def publish_terminal(path, data, remaining):
    data["complete"] = data["complete"] and remaining() >= FINAL_RESERVE
    write(path, data)
    if remaining() <= 0:
        data["complete"] = False
        data["deadline_exhausted"] = True
        write(path, data)
    return data["complete"]


def command(root, output, mode):
    if mode not in ("control", "internal") or output.name != mode:
        raise ValueError("Only declared diagnostic modes are supported")
    if not root.is_absolute() or not output.is_absolute() or output.is_relative_to(root):
        raise ValueError("Absolute external output is required")
    return [
        str(root / ".venv/bin/python"),
        "-B",
        "-m",
        "pytest",
        "-p",
        "restore_internal_plugin",
        NODE,
        "-q",
        "-n",
        "0",
        "--restore-mode",
        mode,
        "--restore-output",
        str(output),
        "--basetemp",
        str(output / "tmp"),
        "-o",
        f"cache_dir={output / 'cache'}",
        f"--junitxml={output / 'junit.xml'}",
        "--cov=warhammer40k_core",
        "--cov-branch",
        "--cov-report=",
        "--cov-fail-under=0",
    ]


def environment(harness, output):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("PYTHON", "PYTEST", "COVERAGE", "TEST_TIMING", "ATTRIBUTION", "RESTORE_")
        )
    }
    env.update(
        {
            "PYTHONPATH": str(harness),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "RESTORE_OUTPUT_ROOT": str(output.parent),
            "COVERAGE_FILE": str(output / ".coverage"),
        }
    )
    return env


def read_host_file(path):
    try:
        return {"value": Path(path).read_text(), "error": None}
    except FileNotFoundError as error:
        return {"value": None, "error": type(error).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output, harness = (
        args.root.resolve(),
        args.output.resolve(),
        Path(__file__).resolve().parent,
    )
    if sys.platform != "linux" or not __debug__ or os.cpu_count() != 4:
        raise ValueError("Native four-logical-CPU Linux with assertions is required")
    if os.environ["GITHUB_RUN_ATTEMPT"] != "1":
        raise ValueError("Retries are outside the reviewed campaign")
    if output.is_relative_to(root) or harness.is_relative_to(root) or output.exists():
        raise ValueError("New external output and external harness required")
    manifest = read_manifest(args.manifest, os.environ["RESTORE_MANIFEST_SHA256"])
    check_sources(root, harness, manifest)
    output.mkdir(parents=True)
    started = time.monotonic()
    job_started = int(os.environ["RESTORE_JOB_STARTED"])

    def remaining():
        return min(
            HARD_SECONDS - (time.monotonic() - started), HARD_SECONDS - (time.time() - job_started)
        )

    write(
        output / "host.json",
        {
            "utc": datetime.now(UTC).isoformat(),
            "head": HEAD,
            "tree": TREE,
            "python": sys.version,
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "cpuinfo": read_host_file("/proc/cpuinfo"),
            "meminfo": read_host_file("/proc/meminfo"),
            "cpu_max": read_host_file("/sys/fs/cgroup/cpu.max"),
            "memory_max": read_host_file("/sys/fs/cgroup/memory.max"),
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in ("pytest", "pytest-cov", "coverage", "pytest-xdist", "shapely", "numpy")
            },
            "runner": {
                key: os.environ.get(key)
                for key in (
                    "RUNNER_NAME",
                    "ImageOS",
                    "ImageVersion",
                    "GITHUB_RUN_ID",
                    "GITHUB_RUN_ATTEMPT",
                )
            },
        },
    )
    receipts = []
    completed_loop = False
    try:
        preflight = output / "cleanup-preflight"
        preflight.mkdir()
        if remaining() < 1260:
            raise RuntimeError("Insufficient budget for preflight and two invocations")
        preflight_command = [
            sys.executable,
            "-B",
            str(harness / "check_ci_attribution_supervisor.py"),
            "checks",
            str(preflight / "checks"),
        ]
        with (
            (preflight / "stdout.txt").open("w") as stdout,
            (preflight / "stderr.txt").open("w") as stderr,
        ):
            result = run_owned(
                preflight_command, timeout=55, cwd=root, stdout=stdout, stderr=stderr
            )
        write(preflight / "receipt.json", result)
        if (
            result["exit_code"] != 0
            or result["timeout"]
            or result["cancel_signal"] is not None
            or result["descendants_remained"]
            or result["seconds"] > 60
        ):
            raise RuntimeError("Cleanup preflight did not pass within its 60-second reserve")
        for mode in ("control", "internal"):
            if remaining() < 600:
                raise RuntimeError("Insufficient remaining fixed invocation budget")
            verify_for_launch(root, harness, manifest, remaining)
            directory = output / mode
            directory.mkdir()
            argv = command(root, directory, mode)
            measured = ["/usr/bin/time", "-v", "-o", str(directory / "resource.txt"), *argv]
            receipt = {
                "mode": mode,
                "command": measured,
                "nodeid": NODE,
                "head": HEAD,
                "start_utc": datetime.now(UTC).isoformat(),
                "execution_cap_seconds": 590,
                "total_envelope_cap_seconds": 600,
                "coverage_branch": True,
                "workers": 1,
                "qualification": (
                    "Diagnostic only. Partial one-node coverage has no aggregate coverage "
                    "acceptance meaning. Filesystem caches uncontrolled."
                ),
            }
            write(directory / "pending.json", receipt)
            with (
                (directory / "stdout.txt").open("w") as stdout,
                (directory / "stderr.txt").open("w") as stderr,
            ):
                require_budget(remaining, 600 + POSTCHECK_RESERVE + FINAL_RESERVE, "child launch")
                result = run_owned(
                    measured,
                    timeout=590,
                    cwd=root,
                    env=environment(harness, directory),
                    stdout=stdout,
                    stderr=stderr,
                )
            receipt.update(result)
            receipt["finish_utc"] = datetime.now(UTC).isoformat()
            receipt["passed"] = False
            receipts.append(receipt)
            write(directory / "receipt.json", receipt)
            write(output / "receipts.json", receipts)
            verify_after_invocation(root, harness, manifest, remaining)
            if (
                result["exit_code"] != 0
                or result["timeout"]
                or result["cancel_signal"] is not None
                or result["descendants_remained"]
                or result["seconds"] > 600
            ):
                raise RuntimeError(
                    f"Original {mode} invocation failed; no subsequent invocation or retry"
                )
            attribution = json.loads((directory / "attribution.json").read_bytes())
            if (
                not attribution["complete"]
                or attribution["exitstatus"] != 0
                or attribution["active_depth"] != 0
                or attribution["telemetry_failures"]
            ):
                raise RuntimeError("Original node and phases were not completed")
            if mode == "internal" and not any(
                row["label"] == "restore" and row["phase"] == "call" for row in attribution["rows"]
            ):
                raise RuntimeError("Required internal restoration evidence missing")
            receipt["passed"] = True
            write(directory / "receipt.json", receipt)
            write(output / "receipts.json", receipts)
        completed_loop = True
    finally:
        complete = publish_terminal(
            output / "terminal.json",
            {
                "receipts": receipts,
                "controller_seconds": time.monotonic() - started,
                "job_elapsed_seconds": time.time() - job_started,
                "complete": completed_loop and completion_status(receipts, remaining),
                "deadline_remaining_seconds": remaining(),
                "qualification": (
                    "A completed diagnostic is attribution, "
                    "not a speedup or full CI acceptance result."
                ),
            },
            remaining,
        )
    require_budget(remaining, 0, "final receipt publication")
    if not complete:
        raise RuntimeError("Diagnostic incomplete at first-timestamp deadline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
