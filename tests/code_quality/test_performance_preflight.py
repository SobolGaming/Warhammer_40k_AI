"""Fresh physical scans, pure proof isolation, and independent smoke revalidation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest
from scripts import check_performance_policy as gate
from tools import performance_preflight as preflight


def test_recipe_cache_is_local_exact_and_validator_specific() -> None:
    calls: list[str] = []

    @preflight.recipe_proof
    def first(before: bytes, current: bytes, recipe: dict[str, Any]) -> None:
        calls.append("first")
        if before != current or recipe != {"edits": []}:
            raise ValueError("changed proof")

    @preflight.recipe_proof
    def second(before: bytes, current: bytes, recipe: dict[str, Any]) -> None:
        calls.append("second")
        raise ValueError("independent validator")

    @preflight.invocation
    def validate() -> None:
        first(b"source", b"source", {"edits": []})
        first(b"source", b"source", {"edits": []})
        with pytest.raises(ValueError, match="changed proof"):
            first(b"source", b"changed", {"edits": []})
        with pytest.raises(ValueError, match="changed proof"):
            first(b"source", b"source", {"edits": [1]})
        with pytest.raises(ValueError, match="independent validator"):
            second(b"source", b"source", {"edits": []})

    validate()
    validate()
    assert calls == ["first", "first", "first", "second"] * 2
    first(b"source", b"source", {"edits": []})
    first(b"source", b"source", {"edits": []})
    assert calls[-2:] == ["first", "first"]


def test_owned_scan_reads_new_bytes_even_with_restored_mtime(tmp_path: Path) -> None:
    path = tmp_path / "source.py"
    path.write_bytes(b"before")
    before = path.stat()
    assert preflight.source_hashes(tmp_path, {"source.py"}) == {
        "source.py": hashlib.sha256(b"before").hexdigest()
    }
    path.write_bytes(b"edited")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert preflight.source_hashes(tmp_path, {"source.py"}) == {
        "source.py": hashlib.sha256(b"edited").hexdigest()
    }


@pytest.mark.parametrize("kind", ["file_link", "directory_link", "hardlink", "root_link"])
def test_owned_scan_rejects_aliases(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    directory = root / "nested"
    directory.mkdir()
    path = directory / "source.py"
    path.write_bytes(b"original")
    if kind == "file_link":
        target = tmp_path / "target.py"
        path.rename(target)
        path.symlink_to(target)
    elif kind == "directory_link":
        target = tmp_path / "target"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
    elif kind == "hardlink":
        os.link(path, tmp_path / "alias.py")
    else:
        link = tmp_path / "root-alias"
        link.symlink_to(root, target_is_directory=True)
        root = link
    with pytest.raises(ValueError, match=r"Aliased|owned regular"):
        preflight.source_hashes(root, {"nested/source.py"})


def test_owned_scan_rejects_midread_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "source.py"
    path.write_bytes(b"before")
    original = os.fstat
    calls = 0

    def mutate(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"edited")
        return original(fd)

    monkeypatch.setattr(os, "fstat", mutate)
    with pytest.raises(ValueError, match="changed during owned read"):
        preflight.source_hashes(tmp_path, {"source.py"})


def test_public_smoke_gate_revalidates_and_refuses_midrun_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"before")
    calls: list[bytes] = []
    receipts: list[dict[str, object]] = []

    def validate(root: Path, base_ref: str, *, pr_head: str | None) -> dict[str, object]:
        current = source.read_bytes()
        calls.append(current)
        return {"input_digest": hashlib.sha256(current).hexdigest()}

    def smoke(root: Path, output: Path, *, binding: dict[str, object]) -> dict[str, object]:
        source.write_bytes(b"edited")
        return {"status": "passed"}

    def receipt(output: Path, report: dict[str, object]) -> None:
        receipts.append(dict(report))

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "validate_current", validate)
    monkeypatch.setattr(gate, "run_smoke", smoke)
    monkeypatch.setattr(gate, "_write_receipt", receipt)
    with pytest.raises(ValueError, match="changed during the required smoke"):
        gate._check_and_run("exact-base", None, tmp_path / "receipt.json")
    assert calls == [b"before", b"edited"]
    assert receipts == [{"status": "failed", "inputs_unchanged": False}]


def test_perils_admission_has_only_an_exact_governance_exception() -> None:
    from tools.performance_policy import _governance

    assert _governance("tools/thousand_sons_perils_preservation.py")
    assert not _governance("tools/thousand_sons_unreviewed_runtime.py")


def test_owner_cache_uses_exact_inputs_defensive_copies_and_exception_cleanup() -> None:
    calls: list[tuple[str, bytes | None]] = []

    @preflight.owner_proof
    def owner(path: str, content: bytes | None) -> dict[str, str]:
        calls.append((path, content))
        return {"owner": repr((path, content))}

    @preflight.invocation
    def validate() -> None:
        result = owner("a.py", b"one")
        expected = dict(result)
        result["owner"] = "caller mutation"
        assert owner("a.py", b"one") == expected
        assert owner("b.py", b"one") != expected
        assert owner("a.py", b"two") != expected
        assert owner("a.py", None) != expected
        raise ValueError("scope ended")

    with pytest.raises(ValueError, match="scope ended"):
        validate()
    assert len(calls) == 4
    owner("a.py", b"one")
    owner("a.py", b"one")
    assert len(calls) == 6


def test_owned_scan_matches_independent_original_reader(tmp_path: Path) -> None:
    from tests.d07_geometry_containment import read_owned_geometry_member

    contents = {
        "source.py": b"# exact source\r\n",
        "nested/deep/evidence.bin": bytes(range(256)),
        "nested/a spaced name.txt": b"immutable evidence\n",
    }
    for name, raw in contents.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    assert preflight.source_hashes(tmp_path, set(contents)) == {
        name: hashlib.sha256(read_owned_geometry_member(tmp_path, name)).hexdigest()
        for name in contents
    }
