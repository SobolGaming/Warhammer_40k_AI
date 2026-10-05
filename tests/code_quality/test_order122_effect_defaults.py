"""Default Core lifetimes keep one live/historical derivation and pinned source."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_default_lifetimes_use_only_the_selected_immutable_core_permission() -> None:
    raw = (ROOT / "data/source_audits/order97/selected-sources.json").read_bytes()
    audit = json.loads((ROOT / "data/source_audits/order122/source.audit.json").read_bytes())
    selected = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["selected_sources_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["selected_core_rows"] == [selected["rule:01:01.02.02:1"]]
    assert audit["requirements"] == ["01.02.02-obligation-05", "01.02.02-obligation-06"]
    assert audit["current_faction_admission"] is False


@pytest.mark.parametrize(
    "name",
    [
        "rule_execution.py",
        "generic_effect_history.py",
        "primary_mission_objective_control_source_authority.py",
    ],
)
def test_live_and_historical_generic_effect_owners_share_default_derivation(name: str) -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / name).read_text(encoding="utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "expiration_for_clause_effect" in calls
    assert "expiration_for_duration" not in calls
