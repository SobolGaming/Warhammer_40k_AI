"""Bounded four-worker real pytest CLI runner with a separate process watchdog."""

from __future__ import annotations

import argparse
import importlib.util
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

from scripts.quality_evidence import (
    SCHEMA,
    WORKERS,
    EvidenceError,
    Journal,
    artifact_name,
    atomic_json,
    context,
    dependency_identity,
    encoded,
    inventory,
    pytest_arguments,
    read_json,
    require,
    seal,
    sha,
    source_identity,
    validate_lane,
)


@dataclass(frozen=True)
class Deadlines:
    """External tiny controls may construct shorter deadlines; CLI never accepts them."""

    interrupt: float = 570
    terminate: float = 585
    kill: float = 590
    reap: float = 595

    def __post_init__(self) -> None:
        require(
            0 < self.interrupt < self.terminate < self.kill < self.reap <= 595,
            "Invalid bounded supervisor deadlines",
        )


DEFAULT_DEADLINES = Deadlines()


def signal_group(group: int, sig: int) -> bool:
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        return False
    return True


def watchdog(read_fd: int, ack_fd: int, directory: Path, binding: str, deadlines: Deadlines) -> int:
    """Pipe EOF covers supervisor loss; own deadline survives a blocked supervisor."""
    journal = Journal(directory, "watchdog", binding)
    journal.emit("watchdog_start", pid=os.getpid(), deadlines=deadlines.__dict__)
    selector = selectors.DefaultSelector()
    selector.register(read_fd, selectors.EVENT_READ)
    started = time.monotonic()
    groups: set[int] = set()
    pending = b""
    cancelled_at: float | None = None
    sent: set[int] = set()
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
    boundaries = (deadlines.interrupt, deadlines.terminate, deadlines.kill)
    failed = False
    try:
        os.write(ack_fd, b"R")
        while True:
            now = time.monotonic()
            elapsed = now - started
            for index, sig in enumerate(signals):
                due = elapsed >= boundaries[index]
                if cancelled_at is not None:
                    due = due or now - cancelled_at >= (0, 2, 4)[index]
                if due and index not in sent:
                    sent.add(index)
                    failed = True
                    for group in groups:
                        signal_group(group, sig)
                    journal.emit("signal", signal=int(sig), groups=sorted(groups), elapsed=elapsed)
            if elapsed >= deadlines.reap or (cancelled_at is not None and now - cancelled_at >= 6):
                for group in groups:
                    signal_group(group, signal.SIGKILL)
                journal.emit("watchdog_end", exit_status=1, reason="bounded shutdown")
                return 1
            if not selector.select(timeout=0.05):
                continue
            raw = os.read(read_fd, 4096)
            if not raw:
                for group in groups:
                    signal_group(group, signal.SIGKILL)
                journal.emit("watchdog_end", exit_status=1, reason="supervisor pipe lost")
                return 1
            pending += raw
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                command, _, argument = line.decode("ascii").partition(" ")
                if command == "group":
                    group = int(argument)
                    groups.add(group)
                    journal.emit("group", pgid=group, elapsed=elapsed)
                    os.write(ack_fd, b"G")
                    if sent:
                        signal_group(group, signal.SIGKILL)
                elif command == "closed":
                    group = int(argument)
                    require(group in groups, "Unknown supervised process group")
                    # A successful controller may still leave subprocesses behind.
                    if signal_group(group, 0):
                        failed = True
                        signal_group(group, signal.SIGKILL)
                        journal.emit("orphan_group", pgid=group)
                    groups.remove(group)
                    journal.emit("closed", pgid=group)
                elif command == "cancel":
                    failed = True
                    if cancelled_at is None:
                        cancelled_at = time.monotonic()
                    journal.emit("cancel", signal=argument)
                elif command == "finish":
                    require(not groups, "Supervisor finished with live process groups")
                    journal.emit("watchdog_end", exit_status=int(failed), reason="finished")
                    return int(failed)
                else:
                    raise EvidenceError("Unknown supervisor command")
    finally:
        for group in groups:
            signal_group(group, signal.SIGKILL)
        selector.close()
        os.close(read_fd)
        os.close(ack_fd)


class Supervisor:
    def __init__(self, directory: Path, binding: str, deadlines: Deadlines) -> None:
        self.directory, self.binding = directory, binding
        self.started = time.monotonic()
        self.deadlines = deadlines
        self.signals: list[int] = []
        self.previous: dict[int, Any] = {}
        read_fd, self.write_fd = os.pipe()
        self.ack_fd, ack_write = os.pipe()
        self.pid = os.fork()
        if self.pid == 0:
            os.close(self.write_fd)
            os.close(self.ack_fd)
            os.setsid()
            status = 3
            try:
                status = watchdog(read_fd, ack_write, directory, binding, deadlines)
            except (OSError, ValueError, TypeError, KeyError) as error:
                print(f"QUALITY WATCHDOG FAILED: {error}", file=sys.__stderr__, flush=True)
            finally:
                os._exit(status)
        os.close(read_fd)
        os.close(ack_write)
        try:
            self.acknowledge(b"R")
        except (EvidenceError, OSError) as error:
            os.close(self.write_fd)
            os.close(self.ack_fd)
            os.kill(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
            raise EvidenceError("Watchdog startup handshake failed") from error
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.previous[sig] = signal.signal(sig, self.cancel)

    def acknowledge(self, token: bytes) -> None:
        selector = selectors.DefaultSelector()
        selector.register(self.ack_fd, selectors.EVENT_READ)
        try:
            require(bool(selector.select(timeout=2)), "Watchdog registration timed out")
            require(os.read(self.ack_fd, 1) == token, "Watchdog registration was lost")
        finally:
            selector.close()

    def send(self, message: str) -> None:
        os.write(self.write_fd, (message + "\n").encode("ascii"))

    def cancel(self, sig: int, frame: FrameType | None) -> None:
        self.signals.append(sig)
        self.send("cancel " + str(sig))

    def run(self, command: list[str], root: Path, environment: dict[str, str], name: str) -> int:
        require(not self.signals, "Quality invocation was cancelled")
        log_path = self.directory / (name + ".log")
        with log_path.open("xb") as log:
            gate_read, gate_write = os.pipe()
            process: subprocess.Popen[bytes] | None = None
            registered = False
            selector = selectors.DefaultSelector()
            try:
                gated = [
                    sys.executable,
                    "-B",
                    "-m",
                    "scripts.quality_runner",
                    "_exec",
                    str(gate_read),
                    *command,
                ]
                process = subprocess.Popen(
                    gated,
                    cwd=root,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    pass_fds=(gate_read,),
                )
                self.send("group " + str(process.pid))
                self.acknowledge(b"G")
                registered = True
                os.write(gate_write, b"G")
                require(process.stdout is not None, "Missing pytest output pipe")
                assert process.stdout is not None
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    for key, _ in selector.select(timeout=0.05):
                        raw = os.read(key.fd, 65536)
                        if not raw:
                            selector.unregister(key.fileobj)
                        else:
                            log.write(raw)
                            log.flush()
                            os.fsync(log.fileno())
                            sys.stdout.buffer.write(raw)
                            sys.stdout.buffer.flush()
                    if time.monotonic() - self.started >= self.deadlines.reap:
                        signal_group(process.pid, signal.SIGKILL)
                        break
                remaining = max(0.01, self.deadlines.reap - (time.monotonic() - self.started))
                status = process.wait(timeout=remaining)
            finally:
                os.close(gate_read)
                os.close(gate_write)
                selector.close()
                if process is not None:
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.poll() is None:
                        signal_group(process.pid, signal.SIGKILL)
                        process.wait(timeout=2)
                    if registered:
                        self.send("closed " + str(process.pid))
            require(process is not None, "Supervised process was not created")
        atomic_json(
            self.directory / (name + "-process.json"),
            {
                "command": command,
                "pid": process.pid,
                "exit_status": status,
                "elapsed": time.monotonic() - self.started,
            },
        )
        return status

    def close(self) -> int:
        lost = False
        try:
            self.send("finish")
        except BrokenPipeError:
            lost = True
            print("QUALITY WATCHDOG PIPE LOST", file=sys.__stderr__, flush=True)
        os.close(self.write_fd)
        os.close(self.ack_fd)
        limit = time.monotonic() + 1
        while time.monotonic() < limit:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                for sig, handler in self.previous.items():
                    signal.signal(sig, handler)
                return 1 if lost else os.waitstatus_to_exitcode(status)
            time.sleep(0.01)
        os.kill(self.pid, signal.SIGKILL)
        os.waitpid(self.pid, 0)
        raise EvidenceError("Watchdog failed bounded reap")


def resources(root: Path) -> dict[str, Any]:
    affinity = sorted(os.sched_getaffinity(0))
    cgroup_root = Path("/sys/fs/cgroup")
    membership = Path("/proc/self/cgroup").read_text().splitlines()
    unified = [line.removeprefix("0::") for line in membership if line.startswith("0::")]
    require(len(unified) == 1, "CPU cgroup evidence unavailable")
    current = cgroup_root / unified[0].lstrip("/")
    require(current.is_dir(), "CPU cgroup is outside the mounted hierarchy")
    quotas = {}
    effective = float(len(affinity))
    while current.is_relative_to(cgroup_root):
        quota_path = current / "cpu.max"
        if quota_path.is_file():
            quota, period = quota_path.read_text().split()
            quotas[str(quota_path)] = [quota, period]
            if quota != "max":
                effective = min(effective, int(quota) / int(period))
        if current == cgroup_root:
            break
        current = current.parent
    require(bool(quotas), "CPU quota evidence unavailable")
    require(effective >= 4, "Quality lane requires four effective cores")
    memory_limit = cgroup_root / "memory.max"
    disk = shutil.disk_usage(root)
    return {
        "affinity": affinity,
        "cpu_count": os.cpu_count(),
        "cpu_quotas": quotas,
        "effective_cores": effective,
        "memory": Path("/proc/meminfo").read_text(),
        "memory_limit": memory_limit.read_text() if memory_limit.is_file() else "unavailable",
        "disk_free": disk.free,
        "disk_total": disk.total,
    }


def prepare(root: Path, directory: Path, expected: dict[str, str], shard: str) -> None:
    require(shard in {"1", "2", "3", "4"}, "Invalid quality shard")
    require(
        directory.resolve().is_relative_to(root / "reports/quality-timing"),
        "Quality evidence must stay under ignored quality-timing",
    )
    directory.mkdir(parents=True, exist_ok=False)
    producer = "quality-policy" if shard == "2" else "quality-shards"
    if expected["mode"] == "hosted":
        require(os.environ["GITHUB_JOB"] == producer, "Wrong hosted quality producer")
    start = {
        "producer": producer,
        "schema": SCHEMA,
        "context": expected,
        "shard": shard,
        "shard_count": 4,
        "workers": WORKERS,
    }
    atomic_json(directory / "start.json", start)
    atomic_json(
        directory / "supervisor.json",
        {"binding": sha(encoded(start)), "state": "declared", "exit_status": None},
    )


def run_lane(
    root: Path,
    directory: Path,
    scratch: Path,
    expected: dict[str, str],
    shard: str,
    *,
    deadlines: Deadlines = DEFAULT_DEADLINES,
) -> int:
    require(
        os.environ.get("GITHUB_ACTIONS") != "true" or deadlines == Deadlines(),
        "Hosted quality deadlines are fixed",
    )
    require(not scratch.resolve().is_relative_to(root), "Pytest scratch must be outside checkout")
    start = read_json(directory / "start.json")
    require(
        start
        == {
            "producer": "quality-policy" if shard == "2" else "quality-shards",
            "schema": SCHEMA,
            "context": expected,
            "shard": shard,
            "shard_count": 4,
            "workers": WORKERS,
        },
        "Prepared run identity differs",
    )
    binding = sha(encoded(start))
    supervisor = Supervisor(directory, binding, deadlines)
    outcome: dict[str, Any] = {
        "binding": binding,
        "state": "failed",
        "exit_status": 1,
        "signals": [],
        "children_reaped": False,
    }
    try:
        source = source_identity(root)
        dependencies = dependency_identity()
        inventories = inventory(root)
        selected = inventories["shards"][shard]
        project = importlib.util.find_spec("warhammer40k_core")
        require(project is not None and project.origin is not None, "Project import origin missing")
        assert project is not None
        assert project.origin is not None
        origin = Path(project.origin).resolve()
        require(
            origin == root / "src/warhammer40k_core/__init__.py", "Project import escaped checkout"
        )
        environment = dict(os.environ)
        environment.update(
            PYTHONDONTWRITEBYTECODE="1",
            XDG_CACHE_HOME=str(scratch / "cache"),
            HYPOTHESIS_STORAGE_DIRECTORY=str(scratch / "hypothesis"),
        )
        require(not environment.get("PYTHONPYCACHEPREFIX"), "Unbound external bytecode prefix")
        recorded_environment = {
            name: environment[name]
            for name in (
                "PYTHONDONTWRITEBYTECODE",
                "XDG_CACHE_HOME",
                "HYPOTHESIS_STORAGE_DIRECTORY",
            )
        }
        recorded_environment["project_origin"] = str(origin)
        commands = {
            mode: pytest_arguments(selected, directory, scratch / mode, collect=mode == "collect")
            for mode in ("collect", "execute")
        }
        atomic_json(
            directory / "admitted.json",
            {
                "binding": binding,
                "source": source,
                "dependencies": dependencies,
                "inventory": inventories,
                "commands": commands,
                "resources": resources(root),
                "config": sha((root / "pyproject.toml").read_bytes()),
                "environment": recorded_environment,
                "output_directory": str(directory),
                "scratch": str(scratch),
                "performance": (
                    {"sha256": sha((root / "reports/performance-smoke.json").read_bytes())}
                    if shard == "2"
                    else None
                ),
            },
        )
        environment["QUALITY_EVIDENCE_DIR"] = str(directory)
        environment["QUALITY_EVIDENCE_BINDING"] = binding
        environment.pop("TEST_TIMING_DIR", None)
        require(not environment.get("PYTEST_ADDOPTS"), "Unrecorded pytest options are forbidden")
        require(not environment.get("PYTEST_PLUGINS"), "Unrecorded pytest plugins are forbidden")
        require(not environment.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD"), "Plugin autoload drift")
        status = 0
        for mode in ("collect", "execute"):
            environment["QUALITY_EVIDENCE_MODE"] = mode
            status = supervisor.run(commands[mode], root, environment, mode)
            if status:
                break
        outcome.update(
            exit_status=status,
            source_after=source_identity(root),
            dependencies_after=dependency_identity(),
        )
        require(
            outcome["source_after"] == source and outcome["dependencies_after"] == dependencies,
            "Source/dependencies changed during pytest",
        )
        if shard == "2":
            destination = directory / "performance"
            destination.mkdir()
            shutil.copy2(root / "reports/performance-smoke.json", destination)
            shutil.copytree(
                root / "reports/performance-attempts", destination / "performance-attempts"
            )
        outcome["state"] = "completed" if status == 0 else "failed"
    except (
        EvidenceError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        outcome.update(state="failed", exit_status=1)
        outcome["error"] = {"type": type(error).__name__, "message": str(error)}
        print(
            f"QUALITY SUPERVISOR FAILED: {type(error).__name__}: {error}",
            file=sys.__stderr__,
            flush=True,
        )
    finally:
        watchdog_status = supervisor.close()
        outcome["signals"] = supervisor.signals
        outcome["children_reaped"] = True
        outcome["elapsed"] = time.monotonic() - supervisor.started
        if watchdog_status or supervisor.signals:
            outcome.update(state="failed", exit_status=1)
        atomic_json(directory / "supervisor.json", outcome, replace=True)
    if outcome["state"] == "completed":
        try:
            validate_lane(directory, expected, outcome["source_after"], inventories, shard, root)
        except (EvidenceError, OSError, KeyError, TypeError, ValueError) as error:
            outcome.update(
                state="failed",
                exit_status=1,
                error={"type": type(error).__name__, "message": str(error)},
            )
            atomic_json(directory / "supervisor.json", outcome, replace=True)
            print(f"QUALITY COMPLETION REJECTED: {error}", file=sys.__stderr__, flush=True)
    seal(directory)
    return 0 if outcome["state"] == "completed" else 1


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "_exec":
        descriptor = int(sys.argv[2])
        token = os.read(descriptor, 1)
        os.close(descriptor)
        if token != b"G":
            return 125
        os.execvpe(sys.argv[3], sys.argv[3:], os.environ)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--shard", required=True, choices=("1", "2", "3", "4"))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scratch", type=Path)
    options = parser.parse_args()
    root = Path.cwd().resolve()
    expected = context(root, options.context)
    directory = (
        options.output or root / "reports/quality-timing" / artifact_name(expected, options.shard)
    ).resolve()
    if options.action == "prepare":
        prepare(root, directory, expected, options.shard)
        return 0
    require(options.scratch is not None, "An outside-checkout scratch directory is required")
    return run_lane(root, directory, options.scratch.resolve(), expected, options.shard)


if __name__ == "__main__":
    raise SystemExit(main())
