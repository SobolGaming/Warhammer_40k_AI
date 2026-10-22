"""Authenticate historical measurements without presenting them as current evidence.

Only evidence assertions use this resolver. Live semantic/work/cache/source checks
continue reading and executing the current checkout.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_BASE = "7f45d87d3094c76beb1be58e0cabb721dec21053"
INVENTORY = ROOT / "docs/performance/policy-v3/historical-evidence.json"
INVENTORY_SHA256 = "3f06d6111c24d6bd7d822738960e0b08744ac3202fb2d7fa0ca9c6ad2fafd690"


@lru_cache(maxsize=1)
def _inventory() -> dict[str, object]:
    raw = INVENTORY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError("Historical performance inventory changed without versioned supersession.")
    value = cast(dict[str, object], json.loads(raw))
    if value["source_commit"] != HISTORICAL_BASE:
        raise ValueError("Historical performance source revision drifted.")
    return value


def assert_historical_report(report: object) -> None:
    """Retain the recorded identity/outcomes; never assert a current runtime claim."""
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    records = cast(dict[str, dict[str, str]], _inventory()["reports"])
    matching = [name for name, row in records.items() if row["canonical_sha256"] == digest]
    if not matching:
        raise ValueError("Unregistered or modified historical performance report.")
    for name in matching:
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != records[name]["sha256"]:
            raise ValueError(f"Historical performance report bytes drifted: {name}")


@lru_cache(maxsize=256)
def historical_input_bytes(name: str) -> bytes:
    """Read a pinned historical input from its reachable immutable Git revision."""
    inputs = cast(dict[str, str], _inventory()["inputs_sha256"])
    if name not in inputs:
        raise ValueError(f"Unregistered historical performance input: {name}")
    payload = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "show",
            f"{HISTORICAL_BASE}:{name}",
        ],
        cwd=ROOT,
    )
    if hashlib.sha256(payload).hexdigest() != inputs[name]:
        raise ValueError(f"Historical performance input bytes drifted: {name}")
    return payload


def historical_input_text(name: str) -> str:
    return historical_input_bytes(name).decode("utf-8")


def verify_historical_inventory() -> None:
    records = cast(dict[str, dict[str, str]], _inventory()["reports"])
    for name, row in records.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Historical performance evidence changed: {name}")
