"""Matched Firing Deck declaration and live eligibility query component costs."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "order65-firing-deck-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.firing_deck_helpers")
    queries = importlib.import_module("warhammer40k_core.engine.shooting_eligibility_state")
    units = importlib.import_module("warhammer40k_core.engine.rules_units")
    rows = []
    for contribute in (False, True):
        samples = []
        for _ in range(7):
            preparation = time.perf_counter()
            session, request, proposal = helpers.firing_deck_session(contribute=contribute)
            prepared = time.perf_counter()
            status = helpers.submit_firing_deck(session, request, proposal)
            declaration_end = time.perf_counter()
            assert status.status_kind.value == "waiting_for_decision"
            state = session.lifecycle.state
            assert state is not None
            view = units.rules_unit_view_by_id(state=state, unit_instance_id=helpers.PASSENGERS[1])
            started = time.perf_counter()
            reasons = [
                queries.shooting_state_restriction_reason(
                    state=state, rules_unit=view, player_id="player-a"
                )
                for _ in range(100)
            ]
            ended = time.perf_counter()
            samples.append(
                {
                    "preparation_seconds": prepared - preparation,
                    "declaration_seconds": declaration_end - prepared,
                    "hundred_queries_seconds": ended - started,
                    "restricted_queries": sum(reason == "firing_deck" for reason in reasons),
                    "complete": True,
                }
            )
        rows.append(
            {
                "contribute": contribute,
                "samples": samples,
                "summary": {
                    metric: {
                        "mean": statistics.mean(values),
                        "median": statistics.median(values),
                        "p95": max(values),
                        "maximum": max(values),
                    }
                    for metric in ("declaration_seconds", "hundred_queries_seconds")
                    for values in ([sample[metric] for sample in samples],)
                },
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "scenario": (
            "2 five-model infantry cargo units; 1 Transport; 5 enemy infantry; empty terrain; "
            "canonical seed and finite first-option shooting type"
        ),
        "timing_boundary": (
            "accepted declaration through next decision; fixture and unit-view preparation "
            "excluded; 100 shared eligibility queries separately"
        ),
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in ("uv.lock", "scripts/measure_order65.py", "tests/firing_deck_helpers.py")
        },
        "rows": rows,
        "completion_rate": 1,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def _select_runtime_src(runtime_src: Path) -> None:
    resolved = str(runtime_src.resolve())
    while resolved in sys.path:
        sys.path.remove(resolved)
    sys.path.insert(0, resolved)
    root = str(ROOT)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(1, root)


def _host_inventory() -> tuple[str, int]:
    if sys.platform == "win32":
        cpu = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor).Name",
            ],
            text=True,
        ).strip()
        memory = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            text=True,
        ).strip()
        return cpu, int(memory)
    if sys.platform == "darwin":
        return (
            subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip(),
            int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        )
    cpu = subprocess.check_output(
        ["sh", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"],
        text=True,
    ).strip()
    memory = subprocess.check_output(
        ["sh", "-c", "awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo"],
        text=True,
    ).strip()
    return cpu, int(memory)


if __name__ == "__main__":
    main()
