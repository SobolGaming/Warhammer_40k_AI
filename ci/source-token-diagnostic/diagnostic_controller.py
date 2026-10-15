"""One baseline diagnostic, original50s execution limit, no acceptance or retries."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path

from ci_attribution_supervisor import run_owned
from manifest_campaign import authenticate, environment, sha


def main() -> None:
    root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    harness = Path(__file__).resolve().parent
    first = float(os.environ["DIAGNOSTIC_JOB_STARTED"])
    if (
        sys.platform != "linux"
        or sys.version_info[:3] != (3, 14, 5)
        or os.cpu_count() != 4
        or not __debug__
    ):
        raise ValueError("Original four-CPU Linux/Python3.14.5 with assertions required")
    if os.environ["GITHUB_RUN_ATTEMPT"] != "1" or output.exists() or output.is_relative_to(root):
        raise ValueError("One diagnostic attempt in fresh external evidence directory")
    manifest_path = harness / "diagnostic-manifest.json"
    if sha(manifest_path) != os.environ["DIAGNOSTIC_MANIFEST_SHA256"]:
        raise ValueError("Diagnostic manifest differs from review binding")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest["status"] != "reviewed-executable":
        raise ValueError("Prepared diagnostic is not yet executable")
    if {p.name for p in harness.iterdir()} != set(manifest["harness"]) | {manifest_path.name}:
        raise ValueError("Unexpected external harness member")
    for name, digest in manifest["harness"].items():
        path = harness / name
        if path.is_symlink() or sha(path) != digest:
            raise ValueError("Diagnostic harness drift")
    authenticate(root, manifest["base"])
    output.mkdir(parents=True)
    receipts = []
    complete = False
    host = {
        "python": sys.version,
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "cpuinfo": Path("/proc/cpuinfo").read_text(),
        "meminfo": Path("/proc/meminfo").read_text(),
    }
    (output / "host.json").write_text(json.dumps(host, indent=2) + "\n")

    def invoke(name: str, command: list[str], execution: int, envelope: int) -> None:
        # Absolute480s deadline reserves120s of the600s job for upload.
        if first + 480 - time.time() < envelope + 20:
            raise RuntimeError("Insufficient full diagnostic budget; no shortened workload")
        directory = output / name
        directory.mkdir()
        pending = {
            "name": name,
            "argv": command,
            "before_launch_epoch": time.time(),
            "before_launch_monotonic": time.monotonic(),
            "execution_seconds": execution,
            "envelope_seconds": envelope,
        }
        (directory / "pending.json").write_text(json.dumps(pending, indent=2) + "\n")
        with (
            (directory / "stdout.txt").open("w") as stdout,
            (directory / "stderr.txt").open("w") as stderr,
        ):
            result = run_owned(
                command,
                timeout=execution,
                cwd=root,
                env=environment(),
                stdout=stdout,
                stderr=stderr,
            )
        receipt = {**pending, **result, "after_cleanup_epoch": time.time()}
        receipts.append(receipt)
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if (
            result["exit_code"] != 0
            or result["timeout"]
            or result["descendants_remained"]
            or result["seconds"] > envelope
        ):
            raise RuntimeError("Diagnostic child incomplete; retain progress, no retry")

    try:
        python = str(root / ".venv/bin/python")
        invoke(
            "cleanup-preflight",
            [
                python,
                "-B",
                str(harness / "check_ci_attribution_supervisor.py"),
                "checks",
                str(output / "cleanup-cases"),
            ],
            110,
            120,
        )
        invoke(
            "baseline-micro",
            [
                python,
                "-B",
                str(harness / "diagnostic_micro.py"),
                str(root),
                str(output / "micro-progress"),
            ],
            50,
            60,
        )
        authenticate(root, manifest["base"])
        complete = True
    finally:
        (output / "terminal.json").write_text(
            json.dumps(
                {
                    "complete": complete,
                    "receipts": receipts,
                    "elapsed_from_first_timestamp": time.time() - first,
                    "qualification": (
                        "Diagnostic only. Original50s micro execution limit; "
                        "no performance acceptance samples, head arm or retry."
                    ),
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
