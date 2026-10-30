"""Measure trusted authoritative command forks on real canonical session states.

Fixture construction, semantic checks and profiler work are outside timings.
The first sample is the first measured fork of that prepared record; fixture
construction can already warm dependencies. This is not full-game evidence.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
import platform
import statistics
import time
from pathlib import Path
from types import CodeType
from typing import TYPE_CHECKING

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from warhammer40k_core.adapters.session_protocol import AuthoritativeSession

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "issue590-authoritative-command-fork-v1"


def _sample(record: AuthoritativeSession, *, profile: bool = False) -> dict[str, object]:
    expected = record.adapter_session.authoritative_history_payload()
    profiler = cProfile.Profile()
    if profile:
        profiler.enable()
    started = time.perf_counter()
    clone = record.fork_for_command()
    elapsed = time.perf_counter() - started
    if profile:
        profiler.disable()
    assert clone is not record
    assert clone.adapter_session is not record.adapter_session
    assert clone.adapter_session.authoritative_history_payload() == expected
    assert record.adapter_session.authoritative_history_payload() == expected
    for original, copied in (
        (record.command_journal, clone.command_journal),
        (record.revision_snapshots, clone.revision_snapshots),
        (record.revision_history, clone.revision_history),
    ):
        assert copied is not original
        assert copied == original
    assert clone.ruleset_id == record.ruleset_id
    assert clone.to_persistence_payload() == record.to_persistence_payload()
    counts: dict[str, int] = {}
    if profile:
        for entry in profiler.getstats():
            code = entry.code
            if isinstance(code, CodeType) and code.co_name in {
                "fork_for_command",
                "authoritative_history_payload",
                "_validate_revision_history",
            }:
                key = f"{Path(code.co_filename).name}:{code.co_name}"
                counts[key] = counts.get(key, 0) + entry.callcount
    return {"seconds": elapsed, "complete": True, "work_counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("At least three samples are required.")
    _select_runtime_src(args.runtime_src)
    from tests.shared.category_migration.phase18f_session_commands import (
        _create_session,
        _start_command,
    )

    from warhammer40k_core.adapters.server import AdapterGameServer
    from warhammer40k_core.build_identity import verified_engine_build_identity

    server = AdapterGameServer()
    prepared_at = time.perf_counter()
    session_id = _create_session(server, game_id="issue590-measured-command-fork")
    preparation_seconds = time.perf_counter() - prepared_at
    rows = []
    for checkpoint in ("created", "started"):
        if checkpoint == "started":
            prepared_at = time.perf_counter()
            _start_command(server, session_id, "issue590-measured-command-start")
            preparation_seconds = time.perf_counter() - prepared_at
        record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
        samples = [_sample(record) for _ in range(args.samples)]
        times = [float(str(sample["seconds"])) for sample in samples]
        row = {
            "checkpoint": checkpoint,
            "operation": "fork",
            "session_revision": record.session_revision,
            "retained_snapshots": len(record.revision_snapshots),
            "journal_entries": len(record.command_journal),
            "preparation_seconds": preparation_seconds,
            "samples": samples,
            "first_sample_seconds": times[0],
            "warm_samples_seconds": times[1:],
            "mean_seconds": statistics.mean(times),
            "median_seconds": statistics.median(times),
            "maximum_seconds": max(times),
            "completion_rate": 1,
            "profile": _sample(record, profile=True),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "AuthoritativeSession.fork_for_command only; preparation, equality and persistence "
            "validation excluded; first measured then warm calls; dependencies may already be "
            "warm from preparation"
        ),
        "input_hash_algorithm": "sha256-normalized-text-lf",
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_command_fork.py",
                "scripts/measure_order63.py",
                "tests/shared/category_migration/phase18f_session_commands.py",
            )
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
