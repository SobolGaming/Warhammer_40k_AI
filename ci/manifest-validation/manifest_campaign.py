"""Bounded serial ABBA reconstruction or ABBAAB source-token validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from ci_attribution_supervisor import run_owned

BASE = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
ORDERS = {
    "reconstruction": ("base", "head", "head", "base"),
    "source_token": ("base", "head", "head", "base", "base", "head"),
}
CEILINGS = {"reconstruction": 1380, "source_token": 3480}


def write(path, data):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=30)


def authenticate(root, side):
    if git(root, "rev-parse", "HEAD").decode().strip() != side["revision"]:
        raise ValueError("Wrong implementation revision")
    if git(root, "rev-parse", "HEAD^{tree}").decode().strip() != side["tree"]:
        raise ValueError("Wrong implementation tree")
    if git(root, "status", "--porcelain", "-uall"):
        raise ValueError("Implementation checkout dirty")
    paths = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
    if paths != set(side["source"]):
        raise ValueError("Source membership changed")
    for relative, expected in side["source"].items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Nonregular bound source")
        raw = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if blob != expected:
            raise ValueError("Source bytes changed: " + relative)
    for prefix, pattern in (("src", "*.py"), ("contracts", "*")):
        actual = {
            p.relative_to(root).as_posix() for p in (root / prefix).rglob(pattern) if p.is_file()
        }
        expected = {
            p
            for p in paths
            if p.startswith(prefix + "/") and (prefix != "src" or p.endswith(".py"))
        }
        if actual != expected:
            raise ValueError("Ignored source/copy corpus injection")


def environment():
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("PYTHON", "PYTEST", "COVERAGE", "TEST_TIMING", "ATTRIBUTION", "RESTORE_")
        )
    }
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    return env


def optional_file(path):
    try:
        return {"value": Path(path).read_text(), "error": None}
    except FileNotFoundError:
        return {"value": None, "error": "FileNotFoundError"}


def reconstruction_results(directories, manifest):
    outcomes = None
    dependencies = None
    reports = []
    for side, directory in directories:
        raw = json.loads((directory / "raw.json").read_bytes())
        semantic = json.loads((directory / "semantic.json").read_bytes())
        if (
            not semantic["complete"]
            or semantic["runtime_build_id"] != manifest["sides"][side]["runtime_build_id"]
        ):
            raise ValueError("Semantic completion/runtime mismatch")
        if outcomes is not None and semantic["outcomes"] != outcomes:
            raise ValueError("Exact cross-arm lifecycle/view/event/replay outcome drift")
        current_dependencies = (semantic["python"], semantic["dependencies"])
        if dependencies is not None and current_dependencies != dependencies:
            raise ValueError("Dependency/interpreter mismatch")
        outcomes, dependencies = semantic["outcomes"], current_dependencies
        reports.append(raw)
    comparisons = []
    # Both complete seven-sample repetitions must pass; never pool/select favorable samples.
    for old_index, new_index in ((0, 1), (3, 2)):
        before = {r["checkpoint"] + "/" + r["operation"]: r for r in reports[old_index]["rows"]}
        after = {r["checkpoint"] + "/" + r["operation"]: r for r in reports[new_index]["rows"]}
        if (
            set(before) != set(manifest["reconstruction_spec"]["cases"])
            or before.keys() != after.keys()
        ):
            raise ValueError("Required reconstruction cases missing")
        for case in before:
            b, h = (
                [r["seconds"] for r in before[case]["samples"]],
                [r["seconds"] for r in after[case]["samples"]],
            )
            if len(b) != 7 or len(h) != 7 or not all(math.isfinite(v) and v > 0 for v in b + h):
                raise ValueError("Required seven positive samples missing")
            mean_limit, maximum_limit = 1.25 * statistics.mean(b) + 0.05, 1.5 * max(b) + 0.10
            passed = statistics.mean(h) <= mean_limit and max(h) <= maximum_limit
            comparisons.append(
                {
                    "base_index": old_index,
                    "head_index": new_index,
                    "case": case,
                    "base": b,
                    "head": h,
                    "mean_limit": mean_limit,
                    "maximum_limit": maximum_limit,
                    "passed": passed,
                }
            )
    return comparisons, all(row["passed"] for row in comparisons)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=tuple(ORDERS), required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--head", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    harness = Path(__file__).resolve().parent
    roots = {"base": args.base.resolve(), "head": args.head.resolve()}
    output = args.output.resolve()
    if (
        sys.platform != "linux"
        or not __debug__
        or os.cpu_count() != 4
        or sys.version_info[:3] != (3, 14, 5)
    ):
        raise ValueError("Native four-CPU Linux/Python3.14.5 with assertions required")
    if os.environ["GITHUB_RUN_ATTEMPT"] != "1" or output.exists():
        raise ValueError("Exactly one attempt into a fresh output directory")
    if roots["base"] == roots["head"] or any(
        output.is_relative_to(r) or harness.is_relative_to(r) for r in roots.values()
    ):
        raise ValueError("Independent source trees and external evidence/harness required")
    if sha(args.manifest) != os.environ["MANIFEST_VALIDATION_SHA256"]:
        raise ValueError("Review-bound manifest drift")
    manifest = json.loads(args.manifest.read_bytes())
    if manifest["status"] != "reviewed-executable" or manifest["sides"]["base"]["revision"] != BASE:
        raise ValueError("Preparation manifest is not executable")
    if (
        manifest["head_snapshot_seal"]
        != "a1f5748301b5a9e53e5d0372def87af91379381d417c34d7936bbf95b797ac47"
    ):
        raise ValueError("Optimization snapshot differs from this reviewed proposal")
    for name, expected in manifest["harness"].items():
        if (harness / name).is_symlink() or sha(harness / name) != expected:
            raise ValueError("External harness bytes changed")
    if {p.name for p in harness.iterdir()} != set(manifest["harness"]) | {"manifest.json"}:
        raise ValueError("Unexpected harness membership")
    for side, root in roots.items():
        authenticate(root, manifest["sides"][side])
    output.mkdir(parents=True)
    started, first = time.monotonic(), float(os.environ["MANIFEST_JOB_STARTED"])
    ceiling = CEILINGS[args.mode]

    def remaining():
        return min(ceiling - (time.monotonic() - started), ceiling - (time.time() - first))

    write(
        output / "host.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "cpuinfo": optional_file("/proc/cpuinfo"),
            "meminfo": optional_file("/proc/meminfo"),
            "cpu_max": optional_file("/sys/fs/cgroup/cpu.max"),
            "memory_max": optional_file("/sys/fs/cgroup/memory.max"),
            "runner": {
                k: os.environ.get(k)
                for k in (
                    "RUNNER_NAME",
                    "ImageOS",
                    "ImageVersion",
                    "GITHUB_RUN_ID",
                    "GITHUB_RUN_ATTEMPT",
                )
            },
        },
    )
    receipts, directories = [], []
    complete = False

    def invoke(name, command, cwd, cap):
        for side, root in roots.items():
            authenticate(root, manifest["sides"][side])
        if remaining() < cap + 65:
            raise RuntimeError(
                "Insufficient absolute time for full child and postcheck; no reduced workload"
            )
        directory = output / name
        directory.mkdir()
        measured = ["/usr/bin/time", "-v", "-o", str(directory / "resource.txt"), *command]
        write(
            directory / "pending.json",
            {"command": measured, "envelope_seconds": cap, "execution_seconds": cap - 10},
        )
        with (
            (directory / "stdout.txt").open("w") as stdout,
            (directory / "stderr.txt").open("w") as stderr,
        ):
            result = run_owned(
                measured, timeout=cap - 10, cwd=cwd, env=environment(), stdout=stdout, stderr=stderr
            )
        receipts.append({"name": name, "command": measured, "cap": cap, **result})
        write(directory / "receipt.json", receipts[-1])
        write(output / "receipts.json", receipts)
        if (
            result["exit_code"] != 0
            or result["timeout"]
            or result["cancel_signal"] is not None
            or result["descendants_remained"]
            or result["seconds"] > cap
        ):
            raise RuntimeError("Failed/incomplete child; stop without retry")
        for side, root in roots.items():
            authenticate(root, manifest["sides"][side])
        if remaining() < 5:
            raise RuntimeError("Postcheck exhausted absolute deadline")
        return directory

    try:
        invoke(
            "cleanup-preflight",
            [
                sys.executable,
                "-B",
                str(harness / "check_ci_attribution_supervisor.py"),
                "checks",
                str(output / "cleanup-cases"),
            ],
            harness,
            60 if args.mode == "reconstruction" else 120,
        )
        if args.mode == "reconstruction":
            for index, side in enumerate(ORDERS[args.mode]):
                directory = output / f"original-{index}-{side}"
                command = [
                    str(roots["head"] / ".venv/bin/python"),
                    "-B",
                    str(harness / "reconstruction_worker.py"),
                    "--workload",
                    str(roots["head"]),
                    "--runtime",
                    str(roots[side]),
                    "--revision",
                    manifest["sides"][side]["revision"],
                    "--output",
                    str(directory),
                ]
                invoke(directory.name, command, roots["head"], 300)
                directories.append((side, directory))
            comparisons, passed = reconstruction_results(directories, manifest)
            write(output / "relative-budgets.json", comparisons)
            if not passed:
                raise RuntimeError("Unchanged relative budget failed")
        else:
            from source_token_arm import run_source_token

            run_source_token(roots, harness, output, manifest, invoke)
        complete = remaining() >= 5
    finally:
        write(
            output / "terminal.json",
            {
                "complete": complete,
                "mode": args.mode,
                "order": ORDERS[args.mode],
                "receipts": receipts,
                "controller_seconds": time.monotonic() - started,
                "job_elapsed_seconds": time.time() - first,
                "remaining_seconds": remaining(),
                "qualification": (
                    "Raw matched validation; policy evidence admission and "
                    "whole-pipeline acceptance remain separate."
                ),
            },
        )
    if not complete or remaining() <= 0:
        raise RuntimeError("Campaign incomplete at first-timestamp deadline")


if __name__ == "__main__":
    main()
