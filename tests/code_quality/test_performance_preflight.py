"""Fresh physical scans, pure proof isolation, and independent smoke revalidation."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
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


@preflight.invocation
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


@preflight.invocation
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

    assert preflight.source_hashes(tmp_path, {"source.py"}) == {
        "source.py": hashlib.sha256(b"before").hexdigest()
    }
    monkeypatch.setattr(os, "fstat", mutate)
    with pytest.raises(ValueError, match="changed during owned read"):
        preflight.source_hashes(tmp_path, {"source.py"})


def _read_metadata(*, ctime: int, changed: str = "") -> os.stat_result:
    fields = {"mode": 0o100644, "ino": 2, "dev": 3, "nlink": 1, "size": 6, "mtime": 5}
    if changed:
        fields[changed] += 1
    return os.stat_result(
        (
            fields["mode"],
            fields["ino"],
            fields["dev"],
            fields["nlink"],
            0,
            0,
            fields["size"],
            0,
            0,
            0,
        ),
        {"st_mtime_ns": fields["mtime"], "st_ctime_ns": ctime},
    )


def test_owned_read_compares_windows_ctime_within_each_api_channel() -> None:
    path = _read_metadata(ctime=10)
    handle = _read_metadata(ctime=20)
    assert preflight._same_read(path, handle, handle, path, windows=True)
    assert not preflight._same_read(path, handle, handle, path, windows=False)
    for windows in (False, True):
        assert preflight._same_read(path, path, path, path, windows=windows)


def test_owned_read_rejects_ctime_drift_in_either_api_channel() -> None:
    for windows in (False, True):
        times = [10, 20 if windows else 10, 20 if windows else 10, 10]
        for index in range(4):
            observations = [_read_metadata(ctime=value) for value in times]
            observations[index] = _read_metadata(ctime=times[index] + 1)
            assert not preflight._same_read(*observations, windows=windows)


@pytest.mark.parametrize("field", ["mode", "ino", "dev", "nlink", "size", "mtime"])
def test_owned_read_rejects_cross_api_metadata_drift(field: str) -> None:
    path = _read_metadata(ctime=10)
    for windows in (False, True):
        handle = _read_metadata(ctime=20 if windows else 10, changed=field)
        assert not preflight._same_read(path, handle, handle, path, windows=windows)


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


@preflight.invocation
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
    expected = {
        name: hashlib.sha256(read_owned_geometry_member(tmp_path, name)).hexdigest()
        for name in contents
    }
    assert preflight.source_hashes(tmp_path, set(contents)) == expected
    assert preflight.source_hashes(tmp_path, set(contents)) == expected


def test_native_discovery_matches_original_ignored_and_symlink_membership(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    files = (
        "src/deep/.ignored.data",
        "src/deep/source.py",
        "tests/.hidden/ignored.py",
        "tests/nested/UPPER.PY",
        "tests/nested/not-selected.txt",
        "tools/.ignored/tool.py",
        "scripts/nested/script.py",
        "contracts/.hidden/schema.json",
        "conformance/typescript/src/.ignored/input.ts",
        "conformance/typescript/src/UPPER.TS",
        "conformance/typescript/src/not-selected.py",
        "outside/not-selected.py",
    )
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"source")
    external = tmp_path / "external"
    external.mkdir()
    (external / "must-not-follow.py").write_bytes(b"outside")
    (root / "tests/nested/linked.py").symlink_to(external, target_is_directory=True)
    (root / "tests/nested/unselected-link").symlink_to(external, target_is_directory=True)
    (root / "src/linked-directory").symlink_to(external, target_is_directory=True)
    (root / "scripts/missing.py").symlink_to(external / "missing.py")
    (root / "tools/linked.py").symlink_to(external / "must-not-follow.py")
    (root / "tests/nested/ordinary-directory.py").mkdir()
    original: set[str] = set()
    for prefix, pattern in (
        ("src", "*"),
        ("tests", "*.py"),
        ("tools", "*.py"),
        ("scripts", "*.py"),
        ("contracts", "*"),
        ("conformance/typescript/src", "*.ts"),
    ):
        original.update(
            path.relative_to(root).as_posix()
            for path in (root / prefix).rglob(pattern)
            if path.is_file() or path.is_symlink()
        )
    actual = preflight.discovered_sources(root)
    assert actual == original
    assert "tests/nested/linked.py" in actual
    assert "src/linked-directory" in actual
    assert "scripts/missing.py" in actual
    assert not any("must-not-follow" in name for name in actual)
    assert "tests/nested/ordinary-directory.py" not in actual
    assert "outside/not-selected.py" not in actual
    assert preflight.discovered_sources(tmp_path / "absent") == set()


def test_generated_inventory_changes_only_reviewed_perils_metadata() -> None:
    from tools import performance_preflight_successor as successor
    from tools import thousand_sons_perils_preservation as perils
    from tools.core_rules_order135_audit import LiveSymbols

    root = Path(__file__).resolve().parents[2]
    old_raw = subprocess.check_output(
        ["git", "show", successor.BASE + ":" + successor.INVENTORY], cwd=root
    )
    expected = json.loads(old_raw)
    live = LiveSymbols(root)
    node = perils.TEST + "::test_twist_of_fate_modifies_ap_and_rejects_drift_or_closed_window"
    current = live.test(node)
    original_assertions = expected["tests"][node]["assertions"]
    assertions = iter(current["assertions"])
    assert all(
        any(assertion == candidate for candidate in assertions) for assertion in original_assertions
    )
    old_test = perils.preceding_test(root, perils.TEST, (root / perils.TEST).read_bytes())
    old_tree = ast.parse(old_test)
    old_function = next(
        child
        for child in old_tree.body
        if isinstance(child, ast.FunctionDef) and child.name == node.split("::")[1]
    )
    assert expected["tests"][node]["complete_current_body"] == ast.unparse(old_function)
    assert expected["current_files_observed"][perils.TEST] == {
        "bytes": len(old_test),
        "sha256": hashlib.sha256(old_test).hexdigest(),
    }
    expected["current_files_observed"][perils.TEST] = live.files[perils.TEST]
    for reference, record in expected["tests"].items():
        if reference.startswith(perils.TEST + "::"):
            record["file_sha256"] = live.files[perils.TEST]["sha256"]
    expected["tests"][node] = current
    actual = (root / successor.INVENTORY).read_bytes()
    assert (
        actual
        == (json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    )
    assert hashlib.sha256(actual).hexdigest() == successor.PINS[successor.INVENTORY]


@preflight.invocation
def test_inventory_history_projection_revalidates_live_bytes_and_rejects_unrelated_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_preflight_successor as successor

    root = Path(__file__).resolve().parents[2]
    direct_git = successor._git
    current = (root / successor.INVENTORY).read_bytes()
    old = direct_git(root, "show", successor.BASE + ":" + successor.INVENTORY)
    assert current != old
    target = tmp_path / successor.INVENTORY
    target.parent.mkdir(parents=True)
    target.write_bytes(current)

    def original_git(_root: Path, *args: str) -> bytes:
        return direct_git(root, *args)

    monkeypatch.setattr(successor, "_git", original_git)
    for supplied in (current, old):
        assert successor.preceding_control(tmp_path, successor.INVENTORY, supplied) == old
    with pytest.raises(ValueError, match="caller supplied unrelated bytes"):
        successor.preceding_control(tmp_path, successor.INVENTORY, current + b" ")

    # Neither a warm invocation nor authenticated historical caller bytes may
    # hide subsequent live drift, even when the file's timestamps are restored.
    metadata = target.stat()
    changed = current.replace(b'"runtime_pass_claimed": false', b'"runtime_pass_claimed": true ')
    assert changed != current
    assert len(changed) == len(current)
    target.write_bytes(changed)
    os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    for supplied in (current, old):
        with pytest.raises(ValueError, match="Preflight source"):
            successor.preceding_control(tmp_path, successor.INVENTORY, supplied)


@pytest.mark.parametrize("coordinated_pin", [False, True])
def test_generated_inventory_freeze_rejects_unlisted_leaf_and_repin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coordinated_pin: bool
) -> None:
    from tools import performance_preflight_successor as successor

    root = Path(__file__).resolve().parents[2]
    direct_git = successor._git
    for name in successor.PINS.keys() | {successor.SELF}:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())

    def original_git(_root: Path, *args: str) -> bytes:
        return direct_git(root, *args)

    monkeypatch.setattr(successor, "_git", original_git)
    assert successor._freeze(tmp_path) == successor.FREEZE_COMMIT
    path = tmp_path / successor.INVENTORY
    payload = json.loads(path.read_bytes())
    assert payload["runtime_pass_claimed"] is False
    payload["runtime_pass_claimed"] = True
    changed = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(changed)
    if coordinated_pin:
        old_pin = successor.PINS[successor.INVENTORY]
        new_pin = hashlib.sha256(changed).hexdigest()
        monkeypatch.setattr(successor, "PINS", successor.PINS | {successor.INVENTORY: new_pin})
        control = tmp_path / successor.SELF
        raw = control.read_bytes()
        assert raw.count(old_pin.encode()) == 1
        control.write_bytes(raw.replace(old_pin.encode(), new_pin.encode(), 1))
    with pytest.raises(ValueError, match=r"Preflight successor activation|Preflight source"):
        successor._freeze(tmp_path)


def test_pure_source_hash_memo_is_exact_bounded_and_validator_specific(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert preflight._DIGEST_LIMIT == 512 * 1024 * 1024
    calls: list[str] = []
    sha = hashlib.sha256

    def first(raw: bytes) -> Any:
        calls.append("first")
        return sha(raw)

    def second(raw: bytes) -> Any:
        calls.append("second")
        return sha(raw)

    monkeypatch.setattr(preflight, "hashlib", SimpleNamespace(sha256=first))
    memo = preflight._Digests(8)
    assert memo.digest("a", b"1234") == sha(b"1234").hexdigest()
    assert memo.digest("a", b"1234") == sha(b"1234").hexdigest()
    assert calls == ["first"]
    assert memo.digest("b", b"1234") == sha(b"1234").hexdigest()
    assert len(calls) == 2
    assert memo.retained == 8
    assert memo.digest("a", b"5678") == sha(b"5678").hexdigest()
    assert len(calls) == 3
    assert memo.retained == 8
    assert memo.digest("overflow", b"more") == sha(b"more").hexdigest()
    assert len(memo.entries) == 2
    assert memo.retained == 8
    assert memo.digest("a", b"larger-than-cap") == sha(b"larger-than-cap").hexdigest()
    assert memo.retained == 4
    assert (first, "a") not in memo.entries
    monkeypatch.setattr(preflight, "hashlib", SimpleNamespace(sha256=second))
    assert memo.digest("b", b"1234") == sha(b"1234").hexdigest()
    assert calls[-1] == "second"
    assert memo.retained == 8
    assert sum(len(raw) for raw, _ in memo.entries.values()) == memo.retained <= memo.limit


def test_pure_source_hash_memo_resets_after_nested_exceptions_and_new_invocations() -> None:
    assert preflight._DIGESTS.get() is None
    scopes: list[preflight._Digests] = []

    @preflight.invocation
    def outer() -> None:
        current = preflight._DIGESTS.get()
        assert current is not None
        assert current.retained == 0
        scopes.append(current)
        preflight._source_digest("a", b"original")
        assert current.retained == len(b"original")

        @preflight.invocation
        def inner() -> None:
            nested = preflight._DIGESTS.get()
            assert nested is not None
            assert nested is not current
            assert nested.retained == 0
            preflight._source_digest("a", b"changed")
            raise ValueError("nested failure")

        with pytest.raises(ValueError, match="nested failure"):
            inner()
        assert preflight._DIGESTS.get() is current
        assert current.retained == len(b"original")
        raise ValueError("outer failure")

    for _ in range(2):
        with pytest.raises(ValueError, match="outer failure"):
            outer()
        assert preflight._DIGESTS.get() is None
    assert scopes[0] is not scopes[1]
    assert all(scope.retained == 0 and not scope.entries for scope in scopes)
