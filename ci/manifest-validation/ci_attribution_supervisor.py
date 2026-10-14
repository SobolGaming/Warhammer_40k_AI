"""Own one POSIX process group through launch, cancellation, failure and bounded cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def signal_group(pid: int, signum: int) -> bool:
    """An already absent owned group is an explicit terminal state, not an error fallback."""
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        return False
    return True


def cleanup(process: subprocess.Popen, grace: float = 2.0, kill_grace: float = 2.0) -> bool:
    """Reap the leader and prove group absence, or fail within the cleanup deadline."""
    process.poll()  # Reaps an already exited direct child.
    remained = signal_group(process.pid, signal.SIGTERM)
    for signum, allowance in ((signal.SIGTERM, grace), (signal.SIGKILL, kill_grace)):
        signal_group(process.pid, signum)
        deadline = time.monotonic() + allowance
        while True:
            leader_reaped = process.poll() is not None
            group_absent = not signal_group(process.pid, 0)
            if leader_reaped and group_absent:
                return remained
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
    raise RuntimeError(f"Owned group {process.pid} not confirmed terminated/reaped within bound")


def run_owned(command: list[str], *, timeout: float, **popen_kwargs) -> dict[str, object]:
    """Signal handlers only set state; finally owns cleanup even if launch/wait raises."""
    cancelled: list[int] = []
    previous: list[tuple[int, object]] = []
    process = None
    timed_out = False
    descendants_remained = False
    code = None
    started = time.monotonic()

    def cancel(signum: int, _frame: object) -> None:
        # No file I/O or exception here: Popen must return ownership before unwinding.
        if not cancelled:
            cancelled.append(signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous.append((signum, signal.signal(signum, cancel)))
        if not cancelled:
            process = subprocess.Popen(command, start_new_session=True, **popen_kwargs)
            deadline = started + timeout
            while not cancelled:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    code = process.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    continue
                break
    finally:
        # Cleanup cannot be bypassed by cancellation, controller exceptions or receipt errors.
        # Keep recording SIGINT/SIGTERM through cleanup; neither may interrupt the reap.
        try:
            if process is not None:
                descendants_remained = cleanup(process)
        finally:
            for signum, handler in reversed(previous):
                signal.signal(signum, handler)
    if cancelled:
        code = 128 + cancelled[0]
    elif timed_out:
        code = 124
    return {
        "exit_code": code,
        "timeout": timed_out,
        "cancel_signal": cancelled[0] if cancelled else None,
        "pid": process.pid if process is not None else None,
        "seconds": time.monotonic() - started,
        "cleanup_complete": True,
        "descendants_remained": descendants_remained,
    }
