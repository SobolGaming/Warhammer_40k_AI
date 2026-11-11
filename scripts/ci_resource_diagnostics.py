"""Read-only Linux resource snapshots; never decide or change workload outcomes."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def _read(path: Path, *, scope: str) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return {
            "available": False,
            "path": str(path),
            "scope": scope,
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    return {"available": True, "path": str(path), "scope": scope, "text": text}


def snapshot(*, phase: str, root: Path = Path("/")) -> dict[str, object]:
    if phase not in {"before", "after"}:
        raise ValueError("Resource snapshot phase must be before or after.")
    vmstat = _read(root / "proc/vmstat", scope="host-wide cumulative; may include unrelated work")
    membership = _read(root / "proc/self/cgroup", scope="snapshot process cgroup membership")
    unified: str | None = None
    if membership["available"]:
        rows = str(membership["text"]).splitlines()
        matches = [row.removeprefix("0::") for row in rows if row.startswith("0::")]
        if len(matches) == 1:
            path = PurePosixPath(matches[0])
            if path.is_absolute() and ".." not in path.parts:
                unified = path.as_posix()
    cgroup: dict[str, object] = {
        "available": False,
        "reason": "No supported unified cgroup path at the standard /sys/fs/cgroup mount",
        "membership": membership,
    }
    if unified is not None:
        directory = root / "sys/fs/cgroup" / unified.lstrip("/")
        readings = {
            name: _read(
                directory / name,
                scope="visible cgroup lifetime, including children; not per-worker attribution",
            )
            for name in (
                "memory.events",
                "memory.events.local",
                "memory.current",
                "memory.peak",
                "memory.max",
                "memory.swap.current",
                "memory.swap.peak",
            )
        }
        cgroup = {
            "available": any(value["available"] for value in readings.values()),
            "version": 2,
            "membership": membership,
            "relative_path": unified,
            "mount_assumption": "standard /sys/fs/cgroup; unavailable files remain explicit",
            "readings": readings,
        }
    oom: dict[str, object] = {"available": False, "reason": "oom_kill counter unavailable"}
    if vmstat["available"]:
        counter_rows = [line.split() for line in str(vmstat["text"]).splitlines()]
        values = [row[1] for row in counter_rows if len(row) == 2 and row[0] == "oom_kill"]
        if len(values) == 1 and values[0].isdigit():
            oom = {"available": True, "value": int(values[0])}
    return {
        "schema": "covered-workload-resource-snapshot-v1",
        "phase": phase,
        "captured_utc": datetime.now(UTC).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "pid": os.getpid(),
        "scope": "Inner covered-workload shell before work or on EXIT; no counter is reset",
        "host_oom_kill": {**oom, "source": vmstat},
        "cgroup": cgroup,
        "worker_exit_code": None,
        "worker_exit_code_availability": "Unknown; no public nonblocking worker-exit API used",
        "interpretation": "A counter increase is diagnostic correlation, not proof of a "
        "particular worker's cause of death. memory.peak is the cgroup lifetime peak, "
        "not this workload's measured peak. Missing after snapshots remain incomplete.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(snapshot(phase=args.phase), indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
