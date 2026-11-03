"""Authenticated historical source setup shared by provenance quality checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools import performance_tool_inputs as inputs
from tools import performance_tool_inputs_v4 as scopes

ROOT = Path(__file__).resolve().parents[2]


def historical_source_report() -> dict[str, Any]:
    old = scopes.registered_scope()
    raw = (ROOT / old.report_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "a4e21f5863cc46e33df79f2a03c9cc15a1bd575118e147bf32ebd298074b3f6a"
    )
    return inputs.input_object(json.loads(raw))


def historical_snapshot_inputs() -> dict[str, str]:
    common = historical_source_report()["input_binding"]["common"]
    expected = {path: digest for path, digest in common.items() if f"{10}th-edition" in path}
    observed = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in expected}
    assert observed == expected
    assert inputs.digest(observed) == (
        "b877588db3f751f764fb74e9b9d5a1e3c3ab2525480e2954d2598520492b3557"
    )
    return observed


def retired_identity_tokens() -> tuple[str, ...]:
    return (f"warhammer-40000-{10}th", f"{10}th-edition")
