"""Supervise covered CI work: approval deadline differs from execution allowance."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType

from scripts.ci_attribution_supervisor import cleanup

APPROVAL_SECONDS = 27 * 60
EXECUTION_SECONDS = 30 * 60


def termination_due(elapsed: float, *, running: bool, execution_seconds: float) -> bool:
    return running and elapsed > execution_seconds


def approved(elapsed: float, *, exit_code: int, terminated: bool, approval_seconds: float) -> bool:
    return exit_code == 0 and not terminated and elapsed <= approval_seconds


def snapshot_coverage(report_dir: Path, coverage_file: Path | None) -> list[str]:
    if coverage_file is None:
        return []
    destination = report_dir / "partial-coverage"
    copied: list[str] = []
    for path in sorted(coverage_file.parent.glob(coverage_file.name + "*")):
        if path.is_file() and not path.is_symlink():
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / path.name
            shutil.copy2(path, target)
            copied.append(str(target))
    return copied


def supervise(
    command: list[str],
    *,
    report_dir: Path,
    approval_seconds: float = APPROVAL_SECONDS,
    execution_seconds: float = EXECUTION_SECONDS,
    poll_seconds: float = 0.05,
    termination_grace: float = 2.0,
) -> int:
    if os.name != "posix":
        raise ValueError("Covered CI supervision requires POSIX process groups.")
    if (
        not command
        or any(
            not math.isfinite(value) or value <= 0
            for value in (approval_seconds, execution_seconds, poll_seconds, termination_grace)
        )
        or approval_seconds > execution_seconds
    ):
        raise ValueError("Require a command and finite positive approval <= execution limits.")
    started = time.monotonic()
    environment = dict(os.environ)
    environment["BEHAVIOR_EXECUTION_DEADLINE"] = str(started + execution_seconds)
    report_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = report_dir / "covered-shard-status.json"
    interrupted = 0

    def interrupt(signum: int, _frame: FrameType | None) -> None:
        nonlocal interrupted
        interrupted = signum

    handlers = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
    process: subprocess.Popen[bytes] | None = None
    cleanup_done = False
    cleanup_error: str | None = None
    descendants_remained = False
    terminated = False
    termination_elapsed: float | None = None
    announced_late = False
    try:
        print(
            f"Covered work: approval <= {approval_seconds}s; "
            f"termination only > {execution_seconds}s.",
            flush=True,
        )
        with (report_dir / "covered-shard.log").open("wb") as output:
            process = subprocess.Popen(
                command,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            while True:
                status = process.poll()
                elapsed = time.monotonic() - started
                if status is not None:
                    completion_elapsed = elapsed
                    break
                if interrupted or termination_due(
                    elapsed, running=True, execution_seconds=execution_seconds
                ):
                    terminated = True
                    termination_elapsed = elapsed
                    completion_elapsed = elapsed
                    break
                if elapsed > approval_seconds and not announced_late:
                    print(
                        "Approval limit exceeded; continuing to retain complete results.",
                        flush=True,
                    )
                    announced_late = True
                time.sleep(poll_seconds)
        cleanup_done = True
        try:
            descendants_remained = cleanup(
                process, grace=termination_grace, kill_grace=termination_grace
            )
        except RuntimeError as error:
            # A failed cleanup is a failed gate; still retain all available diagnostics.
            cleanup_error = str(error)
        status = process.returncode
        if terminated:
            completion_elapsed = time.monotonic() - started
        # The child has finalized normal pytest reports before its exit. Preserve
        # available coverage fragments separately on failure; never invent a
        # combined file or mark a partial report complete.
        coverage = environment.get("COVERAGE_FILE")
        partials = snapshot_coverage(
            report_dir,
            Path(coverage)
            if coverage and (terminated or status != 0 or descendants_remained or cleanup_error)
            else None,
        )
        with (report_dir / "covered-shard.log").open(encoding="utf-8", errors="replace") as log:
            shutil.copyfileobj(log, sys.stdout)
        sys.stdout.flush()
        diagnostic_elapsed = time.monotonic() - started
        if status is None:
            cleanup_error = cleanup_error or "Workload exit was not observed."
        success = (
            not interrupted
            and not cleanup_error
            and not descendants_remained
            and approved(
                completion_elapsed,
                exit_code=status if status is not None else -1,
                terminated=terminated,
                approval_seconds=approval_seconds,
            )
        )
        reason = (
            "interrupted"
            if interrupted
            else "execution_limit_exceeded"
            if terminated
            else "cleanup_failed"
            if cleanup_error
            else "descendants_remained"
            if descendants_remained
            else "workload_failed"
            if status != 0
            else "approval_limit_exceeded"
            if not success
            else "passed"
        )
        receipt = {
            "schema": "covered-shard-deadline-v1",
            "shard_id": environment.get("SHARD_ID"),
            "command": command,
            "approval_seconds": approval_seconds,
            "execution_seconds": execution_seconds,
            "started_monotonic": started,
            "execution_deadline_monotonic": started + execution_seconds,
            "elapsed_seconds": completion_elapsed,
            "diagnostic_elapsed_seconds": diagnostic_elapsed,
            "workload_exit_code": status,
            "terminated": terminated,
            "cleanup_error": cleanup_error,
            "descendants_remained": descendants_remained,
            "termination_elapsed_seconds": termination_elapsed,
            "interrupt_signal": interrupted or None,
            "approved": success,
            "reason": reason,
            "partial_coverage_files": partials,
        }
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        temporary.replace(receipt_path)
        print(json.dumps(receipt), flush=True)
        return 0 if success else 1
    finally:
        try:
            if process is not None and not cleanup_done:
                cleanup(process, grace=termination_grace, kill_grace=termination_grace)
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--approval-seconds", type=float, default=APPROVAL_SECONDS)
    parser.add_argument("--execution-seconds", type=float, default=EXECUTION_SECONDS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    raise SystemExit(
        supervise(
            command,
            report_dir=args.report_dir,
            approval_seconds=args.approval_seconds,
            execution_seconds=args.execution_seconds,
        )
    )


if __name__ == "__main__":
    main()
