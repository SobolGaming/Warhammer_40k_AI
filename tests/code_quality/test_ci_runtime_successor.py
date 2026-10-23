"""Finite runtime correction preserves every earlier proof and rejects unrelated edits."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tools import performance_preflight_successor as successor

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", [*sorted(successor.CI_RUNTIME_BEFORE), successor.CI_RUNTIME_NEW])
def test_ci_runtime_edits_match_exact_independent_predecessor(name: str) -> None:
    record: dict[str, Any] = json.loads((ROOT / successor.CI_RUNTIME_RECORD).read_bytes())
    assert record["schema"] == "exact-ci-successor-v1"
    assert record["base"] == successor.CI_RUNTIME_BASE
    assert record["changes"].keys() == successor.CI_RUNTIME_BEFORE.keys() | {
        successor.CI_RUNTIME_NEW
    }
    before = (
        None
        if name == successor.CI_RUNTIME_NEW
        else subprocess.check_output(
            ["git", "show", successor.CI_RUNTIME_BASE + ":" + name], cwd=ROOT
        )
    )
    current = (ROOT / name).read_bytes()
    successor.assert_ci_runtime_transition(name, before, current, record["changes"][name])
    changed = current + b"\n# outside the finite runtime correction\n"
    row = copy.deepcopy(record["changes"][name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        successor.assert_ci_runtime_transition(name, before, changed, row)


def test_ci_runtime_transition_rejects_unlisted_sources_and_changed_predecessors() -> None:
    name = "tests/category_migration_preservation.py"
    record: dict[str, Any] = json.loads((ROOT / successor.CI_RUNTIME_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", successor.CI_RUNTIME_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    row = record["changes"][name]
    with pytest.raises(ValueError, match="identity or bytes"):
        successor.assert_ci_runtime_transition("tools/unreviewed.py", before, current, row)
    with pytest.raises(ValueError, match="identity or bytes"):
        successor.assert_ci_runtime_transition(name, before + b"\n", current, row)
