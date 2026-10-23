"""Finite static edits cannot absorb changed validation or fixture behavior."""

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
PREFLIGHT = "tests/code_quality/test_performance_preflight.py"


@pytest.fixture(scope="module")
def transitions() -> dict[str, Any]:
    record: dict[str, Any] = json.loads((ROOT / successor.STATIC_RECORD).read_bytes())
    assert record["schema"] == "exact-static-successor-v1"
    assert record["base"] == successor.STATIC_BASE
    assert record["changes"].keys() == successor.STATIC_BEFORE.keys()
    changes: dict[str, Any] = record["changes"]
    return changes


@pytest.fixture(scope="module")
def previous() -> dict[str, bytes]:
    return {
        name: subprocess.check_output(["git", "show", successor.STATIC_BASE + ":" + name], cwd=ROOT)
        for name in successor.STATIC_BEFORE
    }


@pytest.mark.parametrize("name", sorted(successor.STATIC_BEFORE))
def test_static_edits_match_independent_immutable_whole_module_recipes(
    name: str, transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    successor.assert_static_transition(
        name, previous[name], (ROOT / name).read_bytes(), transitions[name]
    )


@pytest.mark.parametrize(
    ("name", "before", "after"),
    [
        (
            PREFLIGHT,
            b"cast(_PreflightMechanisms, preflight)",
            b"cast(_GateMechanisms, preflight)",
        ),
        (
            PREFLIGHT,
            b"cast(_PreflightMechanisms, preflight)",
            b"cast(_PreflightMechanisms, gate)",
        ),
        (PREFLIGHT, b"windows: bool,", b"windows: str,"),
        (
            PREFLIGHT,
            b"return self._source_digest(path, raw)",
            b'return self._source_digest(path, b"changed")',
        ),
        (PREFLIGHT, b'assert calls == [b"before", b"edited"]', b"assert True"),
        (
            successor.STATIC_FIXTURE,
            b"SOURCE_ID as STICKY_SOURCE_ID",
            b"UNREVIEWED_SOURCE_ID as STICKY_SOURCE_ID",
        ),
        (
            successor.STATIC_FIXTURE,
            b'__all__ = ["STICKY_SOURCE_ID",',
            b'__all__ = ["UNREVIEWED_EXPORT", "STICKY_SOURCE_ID",',
        ),
        (
            successor.STATIC_FIXTURE,
            b'seed="section08-native-command"',
            b'seed="unreviewed-new-workload"',
        ),
    ],
)
def test_static_recipes_reject_changed_seams_assertions_and_fixture_behavior_even_if_repinned(
    name: str,
    before: bytes,
    after: bytes,
    transitions: dict[str, Any],
    previous: dict[str, bytes],
) -> None:
    current = (ROOT / name).read_bytes()
    assert before in current
    changed = current.replace(before, after, 1)
    assert changed != current
    row = copy.deepcopy(transitions[name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="whole-module"):
        successor.assert_static_transition(name, previous[name], changed, row)


@pytest.mark.parametrize("kind", ["missing_identity", "unknown_edit", "wrong_recipe_type"])
def test_static_transition_rejects_malformed_records(
    kind: str, transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    row = copy.deepcopy(transitions[PREFLIGHT])
    if kind == "missing_identity":
        row.pop("before_sha256")
    elif kind == "unknown_edit":
        row["recipe"]["edits"][0]["kind"] = "unchecked replacement"
    else:
        row["recipe"] = []
    with pytest.raises(ValueError, match="Static transition"):
        successor.assert_static_transition(
            PREFLIGHT, previous[PREFLIGHT], (ROOT / PREFLIGHT).read_bytes(), row
        )


def test_static_transition_rejects_unlisted_source(
    transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    with pytest.raises(ValueError, match="Static transition"):
        successor.assert_static_transition(
            "tests/support/unreviewed_fixture.py",
            previous[successor.STATIC_FIXTURE],
            (ROOT / successor.STATIC_FIXTURE).read_bytes(),
            transitions[successor.STATIC_FIXTURE],
        )


def test_static_historical_projection_rejects_unrelated_caller_bytes(
    previous: dict[str, bytes],
) -> None:
    raw = (ROOT / successor.STATIC_TEST).read_bytes()
    assert previous[successor.STATIC_TEST] != raw
    for supplied in (previous[successor.STATIC_TEST], raw + b"# unreviewed\n"):
        with pytest.raises(ValueError, match="caller supplied unrelated"):
            successor.static_predecessor(ROOT, successor.STATIC_TEST, supplied)
