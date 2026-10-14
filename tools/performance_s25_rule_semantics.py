"""Exact-source applicability of the approved bounded S25 rule-repair smoke."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

BASE = "b652c9f8148963a5a9f9a79d5ddf5e9bd230d971"
SCOPE = "docs/performance/policy-v3/s25-rule-semantics.json"


def s25_rule_semantics_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    """Match full file/owner hashes; preserve every unrelated detailed obligation."""
    if base != BASE or category != "rule_semantics":
        return frozenset()
    raw: object = json.loads((Path(__file__).resolve().parents[1] / SCOPE).read_bytes())
    if not isinstance(raw, dict):
        raise TypeError("S25 performance scope must be an object.")
    scope = cast(dict[str, object], raw)
    changes, operations = scope.get("changes"), scope.get("smoke_operations")
    if not isinstance(changes, dict) or not isinstance(operations, dict):
        raise TypeError("S25 performance scope lacks exact changes/operations.")
    changed_rows = cast(dict[str, object], changes)
    operation_rows = cast(dict[str, object], operations)
    if scope.get("base") != base or changed_rows.get(path) != change or path not in changed_rows:
        return frozenset()
    names = operation_rows.get(path)
    if not isinstance(names, list):
        raise TypeError("S25 performance scope needs explicit operation names.")
    name_values = cast(list[object], names)
    if not name_values or not all(isinstance(name, str) and name for name in name_values):
        raise ValueError("S25 performance scope needs explicit operation names.")
    result = frozenset(cast(list[str], name_values))
    if len(result) != len(name_values) or "cache-policy" in result:
        raise ValueError("S25 rule scope cannot exempt caches or duplicate operations.")
    return result
