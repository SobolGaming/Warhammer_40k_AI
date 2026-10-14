"""Small Linux-only synthetic process-group checks; never imports the rules engine."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from ci_attribution_supervisor import run_owned


def wait_file(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Synthetic child did not become ready: {path}")
        time.sleep(0.01)


def child(directory: Path, mode: str) -> None:
    if mode == "early":
        return
    if mode == "stubborn":
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    subprocess.Popen([sys.executable, __file__, "grandchild", str(directory), mode])
    wait_file(directory / "grandchild-ready")
    (directory / "ready").touch()
    time.sleep(60)


def controller(directory: Path, mode: str) -> int:
    original = subprocess.Popen
    prior = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        (directory / "group.json").write_text(json.dumps({"pid": process.pid}))
        if mode == "launch-signal":
            os.kill(os.getpid(), signal.SIGINT)
        if mode == "exception":
            wait_file(directory / "ready")

            def fail_wait(*_args, **_kwargs):
                raise RuntimeError("synthetic controller exception after child ownership")

            process.wait = fail_wait
        return process

    child_mode = "early" if mode == "receipt-failure" else mode
    command = [sys.executable, __file__, "child", str(directory), child_mode]
    if mode == "launch-failure":
        command = [str(directory / "nonexistent-executable")]
    try:
        with patch("ci_attribution_supervisor.subprocess.Popen", launch):
            outcome = run_owned(command, timeout=0.6 if mode in ("timeout", "stubborn") else 8)
        if mode == "receipt-failure":
            # Cleanup must already be complete when receipt output fails.
            directory.write_text("cannot write a directory")
        (directory / "outcome.json").write_text(json.dumps(outcome))
        return int(outcome["exit_code"])
    finally:
        (directory / "handlers.json").write_text(
            json.dumps(
                {str(sig): signal.getsignal(sig) == handler for sig, handler in prior.items()}
            )
        )


def checks(output: Path) -> None:
    if sys.platform != "linux":
        raise RuntimeError(
            "These are real Linux process-group checks; no cross-OS equivalence claimed"
        )
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for mode in (
        "early",
        "sigint",
        "sigterm",
        "launch-signal",
        "exception",
        "timeout",
        "stubborn",
        "launch-failure",
        "receipt-failure",
    ):
        directory = Path(tempfile.mkdtemp(prefix=f"{mode}-", dir=output))
        with (directory / "stdout").open("w") as stdout, (directory / "stderr").open("w") as stderr:
            process = subprocess.Popen(
                [sys.executable, __file__, "controller", str(directory), mode],
                stdout=stdout,
                stderr=stderr,
            )
            try:
                if mode in ("sigint", "sigterm"):
                    wait_file(directory / "ready")
                    os.kill(process.pid, signal.SIGINT if mode == "sigint" else signal.SIGTERM)
                code = process.wait(timeout=12)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                # Check failure cannot leave a synthetic sleeper alive.
                group_file = directory / "group.json"
                if group_file.exists():
                    group = json.loads(group_file.read_bytes())["pid"]
                    try:
                        os.killpg(group, 0)
                    except ProcessLookupError:
                        group_absent = True
                    else:
                        group_absent = False
                        os.killpg(group, signal.SIGKILL)
                else:
                    group_absent = mode == "launch-failure"
            handlers = json.loads((directory / "handlers.json").read_bytes())
            expected = {
                "early": 0,
                "sigint": 130,
                "sigterm": 143,
                "launch-signal": 130,
                "exception": 1,
                "timeout": 124,
                "stubborn": 124,
                "launch-failure": 1,
                "receipt-failure": 1,
            }[mode]
            assert code == expected, (mode, code, expected)
            assert group_absent, (mode, "owned group survived controller exit")
            assert all(handlers.values()), (mode, "prior signal handlers not restored")
            results.append(
                {
                    "case": mode,
                    "exit": code,
                    "group_absent": group_absent,
                    "handlers_restored": True,
                }
            )
            (output / "results.json").write_text(json.dumps(results, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("checks", "controller", "child", "grandchild"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("mode", nargs="?", default="")
    args = parser.parse_args()
    if args.role == "checks":
        checks(args.directory)
    elif args.role == "controller":
        raise SystemExit(controller(args.directory, args.mode))
    elif args.role == "child":
        child(args.directory, args.mode)
    else:
        if args.mode == "stubborn":
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (args.directory / "grandchild-ready").touch()
        time.sleep(60)


if __name__ == "__main__":
    main()
