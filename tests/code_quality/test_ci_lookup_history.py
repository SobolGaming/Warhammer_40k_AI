"""The lookup-only test retains D07 history only after fresh complete-source admission."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from tools import performance_preflight_successor as successor

from tests import d07_geometry_containment as geometry

ROOT = Path(__file__).resolve().parents[2]
LOOKUP = "tests/code_quality/test_faction_content_runtime_structure.py"


def _historical_lookup() -> bytes:
    return subprocess.check_output(
        ["git", "show", successor.CI_RUNTIME_BASE + ":" + LOOKUP], cwd=ROOT, timeout=30
    )


def test_lookup_predecessor_preserves_the_original_d07_pin_after_live_admission() -> None:
    current = (ROOT / LOOKUP).read_bytes()
    before = _historical_lookup()
    originals = json.loads((ROOT / "data/source_audits/d07/original-tests.json").read_bytes())
    assert hashlib.sha256(current).hexdigest() == successor.PINS[LOOKUP]
    assert hashlib.sha256(before).hexdigest() == originals[LOOKUP]
    assert originals[LOOKUP] == successor.CI_RUNTIME_BEFORE[LOOKUP]
    assert current != before
    assert successor.static_predecessor(ROOT, LOOKUP, current) == before
    assert successor.static_predecessor(ROOT, LOOKUP, current.replace(b"\r\n", b"\n")) == (
        before.replace(b"\r\n", b"\n")
    )
    assert successor.static_predecessor(ROOT, "tests/unlisted_lookup.py", current) == current


@pytest.mark.parametrize("supplied", ["historical", "extra_bytes"])
def test_lookup_predecessor_rejects_unrelated_caller_bytes(supplied: str) -> None:
    current = (ROOT / LOOKUP).read_bytes()
    unrelated = _historical_lookup() if supplied == "historical" else current + b"\n"
    with pytest.raises(ValueError, match="Static predecessor caller supplied unrelated bytes"):
        successor.static_predecessor(ROOT, LOOKUP, unrelated)


def test_lookup_predecessor_rereads_physical_bytes_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = (ROOT / LOOKUP).read_bytes()
    before = _historical_lookup()
    physical = tmp_path / LOOKUP
    physical.parent.mkdir(parents=True)
    physical.write_bytes(current)
    read_owned = geometry.read_owned_geometry_member
    reads: list[bytes] = []

    def read_physical(root: Path, name: str) -> bytes:
        if root == ROOT and name == LOOKUP:
            raw = read_owned(tmp_path, name)
            reads.append(raw)
            return raw
        return read_owned(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", read_physical)
    assert successor.static_predecessor(ROOT, LOOKUP, current) == before
    assert reads
    assert all(raw == current for raw in reads)
    changed = current + b"\n# unreviewed physical lookup change\n"
    try:
        physical.write_bytes(changed)
        with pytest.raises(ValueError, match="Preflight source"):
            successor.static_predecessor(ROOT, LOOKUP, current)
        assert reads[-1] == changed
    finally:
        physical.write_bytes(current)
    assert successor.static_predecessor(ROOT, LOOKUP, current) == before
    assert reads[-1] == current
