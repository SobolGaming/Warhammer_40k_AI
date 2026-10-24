"""Fresh physical scans, pure proof isolation, and independent smoke revalidation."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, cast

import pytest
from scripts import check_performance_policy as gate
from tools import performance_preflight as preflight


class _DigestProbe(Protocol):
    @property
    def limit(self) -> int: ...

    @property
    def retained(self) -> int: ...

    @property
    def entries(self) -> Mapping[tuple[Callable[..., Any], str], tuple[bytes, str]]: ...

    def digest(self, path: str, raw: bytes) -> str: ...


class _DigestScope(Protocol):
    def get(self) -> _DigestProbe | None: ...


class _PreflightMechanisms(Protocol):
    @property
    def _DIGEST_LIMIT(self) -> int: ...

    @property
    def _DIGESTS(self) -> _DigestScope: ...

    def _Digests(self, limit: int = ...) -> _DigestProbe: ...

    def _source_digest(self, path: str, raw: bytes) -> str: ...

    def _same_read(
        self,
        before: os.stat_result,
        opened: os.stat_result,
        closed: os.stat_result,
        after: os.stat_result,
        *,
        windows: bool,
    ) -> bool: ...

    def digest_limit(self) -> int:
        return self._DIGEST_LIMIT

    def digest_scope(self) -> _DigestScope:
        return self._DIGESTS

    def digests(self, limit: int) -> _DigestProbe:
        return self._Digests(limit)

    def source_digest(self, path: str, raw: bytes) -> str:
        return self._source_digest(path, raw)

    def same_read(
        self,
        before: os.stat_result,
        opened: os.stat_result,
        closed: os.stat_result,
        after: os.stat_result,
        *,
        windows: bool,
    ) -> bool:
        return self._same_read(before, opened, closed, after, windows=windows)


class _GateMechanisms(Protocol):
    def _check_and_run(
        self, base_ref: str, pr_head: str | None, output: Path
    ) -> dict[str, object]: ...

    def check_and_run(self, base_ref: str, pr_head: str | None, output: Path) -> dict[str, object]:
        return self._check_and_run(base_ref, pr_head, output)


class _PolicyMechanisms(Protocol):
    def _governance(self, path: str) -> bool: ...

    def governance(self, path: str) -> bool:
        return self._governance(path)


class _GitCommand(Protocol):
    def __call__(self, root: Path, *args: str, payload: bytes | None = None) -> bytes: ...


class _SuccessorMechanisms(Protocol):
    def _git(self, root: Path, *args: str, payload: bytes | None = None) -> bytes: ...

    def _freeze(self, root: Path) -> str: ...

    def _blobs(self, root: Path, revision: str, names: list[str]) -> dict[str, bytes]: ...

    def git(self, root: Path, *args: str, payload: bytes | None = None) -> bytes:
        return self._git(root, *args, payload=payload)

    def git_function(self) -> _GitCommand:
        return self._git

    def freeze(self, root: Path) -> str:
        return self._freeze(root)

    def blobs(self, root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
        return self._blobs(root, revision, names)


# These views keep the real module objects and their monkeypatch targets. They
# describe only the private mechanisms whose boundaries these tests exercise.
# Unbound methods keep private access inside its declaring Protocol and forward
# to the same production functions; function capture returns the original object.
_preflight = cast(_PreflightMechanisms, preflight)
_gate = cast(_GateMechanisms, gate)


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


@pytest.mark.parametrize("same_bytes", [False, True])
def test_owned_windows_scan_rejects_write_at_final_path_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, same_bytes: bool
) -> None:
    path = tmp_path / "source.py"
    original = b"before"
    path.write_bytes(original)
    metadata = path.stat()
    observations: list[os.stat_result] = []
    reader_fd: int | None = None
    mutated = False
    final_path_observed = False
    final_handle_observed = False

    def observe_handle(fd: int) -> os.stat_result:
        nonlocal reader_fd, final_handle_observed
        reader_fd = fd
        result = os.fstat(fd)
        observations.append(result)
        if final_path_observed:
            final_handle_observed = True
        return result

    def observe_path(name: str) -> os.stat_result:
        nonlocal mutated, final_path_observed
        if name == path.as_posix() and len(observations) == 2:
            assert reader_fd is not None
            # The reader must remain open across this real final-query write.
            assert os.fstat(reader_fd) == observations[-1]
            path.write_bytes(original if same_bytes else b"edited")
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            assert os.fstat(reader_fd).st_ctime_ns != observations[-1].st_ctime_ns
            mutated = True
            final_path_observed = True
        return os.lstat(name)

    # Select the Windows path without changing os.name used by pathlib/pytest.
    monkeypatch.setattr(
        preflight,
        "os",
        SimpleNamespace(name="nt", path=os.path, lstat=observe_path, fstat=observe_handle),
    )
    with pytest.raises(ValueError, match="changed during owned read"):
        preflight.source_hashes(tmp_path, {path.name})
    assert mutated
    assert final_handle_observed
    assert len(observations) == 3
    assert path.stat().st_mtime_ns == metadata.st_mtime_ns
    assert path.read_bytes() == (original if same_bytes else b"edited")


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
    assert _PreflightMechanisms.same_read(_preflight, path, handle, handle, path, windows=True)
    assert not _PreflightMechanisms.same_read(_preflight, path, handle, handle, path, windows=False)
    for windows in (False, True):
        assert _PreflightMechanisms.same_read(_preflight, path, path, path, path, windows=windows)


def test_owned_read_rejects_ctime_drift_in_either_api_channel() -> None:
    for windows in (False, True):
        times = [10, 20 if windows else 10, 20 if windows else 10, 10]
        for index in range(4):
            observations = [_read_metadata(ctime=value) for value in times]
            observations[index] = _read_metadata(ctime=times[index] + 1)
            assert not _PreflightMechanisms.same_read(_preflight, *observations, windows=windows)


@pytest.mark.parametrize("field", ["mode", "ino", "dev", "nlink", "size", "mtime"])
def test_owned_read_rejects_cross_api_metadata_drift(field: str) -> None:
    path = _read_metadata(ctime=10)
    for windows in (False, True):
        handle = _read_metadata(ctime=20 if windows else 10, changed=field)
        assert not _PreflightMechanisms.same_read(
            _preflight, path, handle, handle, path, windows=windows
        )


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
        _GateMechanisms.check_and_run(_gate, "exact-base", None, tmp_path / "receipt.json")
    assert calls == [b"before", b"edited"]
    assert receipts == [{"status": "failed", "inputs_unchanged": False}]


def test_perils_admission_has_only_an_exact_governance_exception() -> None:
    from tools import performance_policy as policy

    policy_probe = cast(_PolicyMechanisms, policy)

    assert _PolicyMechanisms.governance(policy_probe, "tools/thousand_sons_perils_preservation.py")
    assert not _PolicyMechanisms.governance(
        policy_probe, "tools/thousand_sons_unreviewed_runtime.py"
    )


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

    successor_probe = cast(_SuccessorMechanisms, successor)

    root = Path(__file__).resolve().parents[2]
    direct_git = _SuccessorMechanisms.git_function(successor_probe)
    current = (root / successor.INVENTORY).read_bytes()
    old = direct_git(root, "show", successor.BASE + ":" + successor.INVENTORY)
    assert current != old
    target = tmp_path / successor.INVENTORY
    target.parent.mkdir(parents=True)
    target.write_bytes(current)

    def original_git(_root: Path, *args: str, payload: bytes | None = None) -> bytes:
        return direct_git(root, *args, payload=payload)

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
    from tools import quality_runtime_successor as ci54

    successor_probe = cast(_SuccessorMechanisms, successor)

    root = Path(__file__).resolve().parents[2]
    direct_git = _SuccessorMechanisms.git_function(successor_probe)
    owned = (
        successor.PINS.keys()
        | successor.ANCHORS.keys()
        | {successor.SELF}
        | ci54.PINS.keys()
        | {ci54.SELF, ci54.ASSESSMENT}
    )
    for name in owned:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    git_directory = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=root)
        .decode()
        .strip()
    )
    (tmp_path / ".git").write_text("gitdir: " + git_directory + chr(10))

    def original_git(_root: Path, *args: str, payload: bytes | None = None) -> bytes:
        return direct_git(root, *args, payload=payload)

    monkeypatch.setattr(successor, "_git", original_git)
    assert _SuccessorMechanisms.freeze(successor_probe, tmp_path) == successor.FREEZE_COMMIT
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
        _SuccessorMechanisms.freeze(successor_probe, tmp_path)


def test_pure_source_hash_memo_is_exact_bounded_and_validator_specific(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _PreflightMechanisms.digest_limit(_preflight) == 512 * 1024 * 1024
    calls: list[str] = []
    sha = hashlib.sha256

    def first(raw: bytes) -> Any:
        calls.append("first")
        return sha(raw)

    def second(raw: bytes) -> Any:
        calls.append("second")
        return sha(raw)

    monkeypatch.setattr(preflight, "hashlib", SimpleNamespace(sha256=first))
    memo = _PreflightMechanisms.digests(_preflight, 8)
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
    assert _PreflightMechanisms.digest_scope(_preflight).get() is None
    scopes: list[_DigestProbe] = []

    @preflight.invocation
    def outer() -> None:
        current = _PreflightMechanisms.digest_scope(_preflight).get()
        assert current is not None
        assert current.retained == 0
        scopes.append(current)
        _PreflightMechanisms.source_digest(_preflight, "a", b"original")
        assert current.retained == len(b"original")

        @preflight.invocation
        def inner() -> None:
            nested = _PreflightMechanisms.digest_scope(_preflight).get()
            assert nested is not None
            assert nested is not current
            assert nested.retained == 0
            _PreflightMechanisms.source_digest(_preflight, "a", b"changed")
            raise ValueError("nested failure")

        with pytest.raises(ValueError, match="nested failure"):
            inner()
        assert _PreflightMechanisms.digest_scope(_preflight).get() is current
        assert current.retained == len(b"original")
        raise ValueError("outer failure")

    for _ in range(2):
        with pytest.raises(ValueError, match="outer failure"):
            outer()
        assert _PreflightMechanisms.digest_scope(_preflight).get() is None
    assert scopes[0] is not scopes[1]
    assert all(scope.retained == 0 and not scope.entries for scope in scopes)


def test_frozen_blob_batch_matches_git_show_and_revalidates_each_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_preflight_successor as successor

    successor_probe = cast(_SuccessorMechanisms, successor)

    contents = {"a.txt": b"exact\n", "nested/a spaced[1].bin": bytes(range(256)), "empty": b""}
    _SuccessorMechanisms.git(successor_probe, tmp_path, "init", "--quiet")
    for name, content in contents.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _SuccessorMechanisms.git(successor_probe, tmp_path, "add", "--all")
    _SuccessorMechanisms.git(successor_probe, tmp_path, "update-index", "--chmod=+x", "a.txt")
    _SuccessorMechanisms.git(
        successor_probe,
        tmp_path,
        "-c",
        "user.name=Blob test",
        "-c",
        "user.email=blob@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "Exact blob fixture",
    )
    revision = (
        _SuccessorMechanisms.git(successor_probe, tmp_path, "rev-parse", "HEAD").decode().strip()
    )
    expected = {
        name: _SuccessorMechanisms.git(successor_probe, tmp_path, "show", revision + ":" + name)
        for name in contents
    }
    assert expected == contents
    direct_git = _SuccessorMechanisms.git_function(successor_probe)
    calls: list[tuple[str, ...]] = []

    def tracked(root: Path, *args: str, payload: bytes | None = None) -> bytes:
        calls.append(args)
        return direct_git(root, *args, payload=payload)

    monkeypatch.setattr(successor, "_git", tracked)
    assert (
        _SuccessorMechanisms.blobs(successor_probe, tmp_path, revision, list(contents)) == expected
    )
    (tmp_path / "a.txt").write_bytes(b"uncommitted live drift")
    assert (
        _SuccessorMechanisms.blobs(successor_probe, tmp_path, revision, list(contents)) == expected
    )
    assert len(calls) == 4
    assert calls[0] == calls[2]
    assert calls[1] == calls[3] == ("cat-file", "--batch")
    with pytest.raises(ValueError, match="Preflight Git tree membership"):
        _SuccessorMechanisms.blobs(successor_probe, tmp_path, revision, [*contents, "absent.txt"])


@pytest.mark.parametrize(
    "kind",
    [
        "missing_member",
        "extra_member",
        "duplicate_member",
        "nonregular",
        "tree_type",
        "tree_oid",
        "tree_framing",
        "missing_blob",
        "blob_oid",
        "blob_type",
        "negative_size",
        "noncanonical_size",
        "truncated",
        "separator",
        "trailing",
        "content",
    ],
)
def test_frozen_blob_batch_rejects_changed_members_and_malformed_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from tools import performance_preflight_successor as successor

    successor_probe = cast(_SuccessorMechanisms, successor)

    content = b"exact\0payload\n"
    size = str(len(content)).encode()
    oid = (
        hashlib.sha1(b"blob " + size + b"\0" + content, usedforsecurity=False).hexdigest().encode()
    )
    row = b"100644 blob " + oid + b"\ta.txt\0"
    batch = oid + b" blob " + size + b"\n" + content + b"\n"
    tree_changes = {
        "missing_member": b"",
        "extra_member": row + row.replace(b"a.txt", b"extra.txt"),
        "duplicate_member": row + row,
        "nonregular": row.replace(b"100644", b"120000"),
        "tree_type": row.replace(b"blob", b"tree"),
        "tree_oid": row.replace(oid, b"g" * 40),
        "tree_framing": row[:-1],
    }
    blob_changes = {
        "missing_blob": oid + b" missing\n",
        "blob_oid": batch.replace(oid, b"0" * 40, 1),
        "blob_type": batch.replace(b" blob ", b" tree ", 1),
        "negative_size": batch.replace(b" blob " + size, b" blob -1", 1),
        "noncanonical_size": batch.replace(b" blob " + size, b" blob 0" + size, 1),
        "truncated": batch[:-2],
        "separator": batch[:-1] + b"x",
        "trailing": batch + b"unrequested\n",
        "content": batch.replace(b"exact", b"other", 1),
    }

    def changed_git(_root: Path, *args: str, payload: bytes | None = None) -> bytes:
        if args == ("cat-file", "--batch"):
            assert payload == oid + b"\n"
            return blob_changes.get(kind, batch)
        assert args == ("--literal-pathspecs", "ls-tree", "-r", "-z", "1" * 40, "--", "a.txt")
        assert payload is None
        return tree_changes.get(kind, row)

    monkeypatch.setattr(successor, "_git", changed_git)
    with pytest.raises(ValueError, match="Preflight Git"):
        _SuccessorMechanisms.blobs(successor_probe, tmp_path, "1" * 40, ["a.txt"])


def test_frozen_blob_batch_rejects_nonliteral_or_ambiguous_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_preflight_successor as successor

    successor_probe = cast(_SuccessorMechanisms, successor)

    def unexpected_git(_root: Path, *args: str, payload: bytes | None = None) -> bytes:
        raise AssertionError("Invalid selectors must fail before Git access.")

    monkeypatch.setattr(successor, "_git", unexpected_git)
    for revision, names in (
        ("HEAD", ["a.txt"]),
        ("1" * 40, []),
        ("1" * 40, ["a.txt", "a.txt"]),
        ("1" * 40, ["../a.txt"]),
        ("1" * 40, ["/a.txt"]),
        ("1" * 40, ["nested//a.txt"]),
        ("1" * 40, ["a.txt\nother"]),
    ):
        with pytest.raises(ValueError, match="Preflight Git"):
            _SuccessorMechanisms.blobs(successor_probe, tmp_path, revision, names)


def _history_fixture(tmp_path: Path, *, packed: bool) -> tuple[Path, str, dict[str, bytes]]:
    root = tmp_path / "native"
    root.mkdir()
    contents = {"a": b"first\n", "nested/b": b"\0second\n", "empty": b""}
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    for name, raw in contents.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    subprocess.run(["git", "add", "--all"], cwd=root, check=True)
    subprocess.run(["git", "update-index", "--chmod=+x", "a"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=History fixture",
            "-c",
            "user.email=history@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "Native history control",
        ],
        cwd=root,
        check=True,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    if packed:
        subprocess.run(["git", "repack", "-ad"], cwd=root, check=True)
    return root, revision, contents


@pytest.mark.parametrize("domain", ["plain60", "safe60", "plain30"])
@pytest.mark.parametrize("packed", [False, True])
def test_history_native_domains_preserve_complete_commit_tree_blob_bindings(
    tmp_path: Path, domain: str, packed: bool
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=packed)
    builder = history._Builder(root)
    pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()}
    assert builder.add(domain, revision, pins, "native-test-authority") == contents
    assert builder.all_paths(domain, revision) == set(contents)
    builder.finish()
    assert builder.members.keys() == builder.contents.keys()
    for key, member in builder.members.items():
        assert key == (domain, revision, member.path)
        assert member.sha256 == pins[member.path]
        assert member.size == len(contents[member.path])
        assert member.mode == ("100755" if member.path == "a" else "100644")
        expected_oid = (
            subprocess.check_output(["git", "rev-parse", revision + ":" + member.path], cwd=root)
            .decode()
            .strip()
        )
        assert member.oid == expected_oid
    assert len(builder.roots) == 1
    assert builder.objects[domain, revision][0] == "commit"


@pytest.mark.parametrize("bad", ["pin", "missing", "commit", "domain", "nonliteral", "symlink"])
def test_history_native_acquisition_rejects_wrong_authority_or_member(
    tmp_path: Path, bad: str
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=False)
    builder = history._Builder(root)
    assert builder.add(
        "plain60", revision, {"a": hashlib.sha256(contents["a"]).hexdigest()}, "original"
    ) == {"a": contents["a"]}
    domain, selected, pins = "plain60", revision, {"a": None}
    if bad == "pin":
        pins = {"a": "0" * 64}
    elif bad == "missing":
        pins = {"missing": None}
    elif bad == "commit":
        selected = "HEAD"
    elif bad == "domain":
        domain = "other"
    elif bad == "nonliteral":
        pins = {"../a": None}
    else:
        subprocess.run(
            [
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                "120000," + builder.members["plain60", revision, "a"].oid + ",link",
            ],
            cwd=root,
            check=True,
        )
        tree = subprocess.check_output(["git", "write-tree"], cwd=root).decode().strip()
        selected = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "user.name=History fixture",
                    "-c",
                    "user.email=history@example.invalid",
                    "commit-tree",
                    tree,
                    "-p",
                    revision,
                ],
                cwd=root,
                input=b"Symlink rejection\n",
            )
            .decode()
            .strip()
        )
        pins = {"link": None}
    with pytest.raises(ValueError, match=r"History|history"):
        builder.add(domain, selected, pins, "negative")
    assert builder.add("plain60", revision, {"a": None}, "restored") == {"a": contents["a"]}


@pytest.mark.parametrize("kind", ["nonzero", "surplus", "truncated", "hash", "type", "size"])
def test_history_closed_protocol_rejects_synthetic_malformed_native_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=False)
    original = history._closed
    positive = history._Builder(root)
    assert positive.add("plain60", revision, {"a": None}, "positive") == {"a": contents["a"]}

    def corrupt(root: Path, domain: str, args: tuple[str, ...], **kwargs: Any) -> bytes:
        raw = cast(bytes, original(root, domain, args, **kwargs))
        if args != ("cat-file", "--batch"):
            return raw
        if kind == "nonzero":
            raise subprocess.CalledProcessError(3, args, raw)
        if kind == "surplus":
            return raw + b"extra"
        if kind == "truncated":
            return raw[:-1]
        if kind == "hash":
            split = raw.index(b"\n") + 1
            return raw[:split] + bytes([raw[split] ^ 1]) + raw[split + 1 :]
        if kind == "type":
            return raw.replace(b" commit ", b" blob ", 1)
        return raw.replace(b" commit ", b" commit 0", 1)

    monkeypatch.setattr(history, "_closed", corrupt)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        history._Builder(root).add("plain60", revision, {"a": None}, "negative")
    monkeypatch.setattr(history, "_closed", original)
    assert history._Builder(root).add("plain60", revision, {"a": None}, "restored") == {
        "a": contents["a"]
    }


@pytest.mark.parametrize("mode", ["nonzero", "timeout", "overflow", "cancellation", "blocked_pipe"])
def test_history_closed_process_requires_eof_zero_exit_and_reaps_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    import sys

    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    children: list[subprocess.Popen[bytes]] = []
    original_popen = subprocess.Popen
    original_read = os.read

    def tracked(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        child = original_popen(*args, **kwargs)
        children.append(child)
        if mode == "cancellation":
            monkeypatch.setattr(history.os, "read", cancelled)
        return child

    program = {
        "nonzero": "import sys; print('complete'); sys.exit(7)",
        "timeout": "import time; print('complete', flush=True); time.sleep(10)",
        "overflow": "import sys; sys.stdout.write('x'*100000)",
        "cancellation": "import time; time.sleep(10)",
        "blocked_pipe": (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(10)']); "
            "print('complete',flush=True)"
        ),
    }[mode]
    monkeypatch.setattr(history, "_argv", lambda *_: [sys.executable, "-B", "-c", program])
    monkeypatch.setattr(history.subprocess, "Popen", tracked)
    monkeypatch.setattr(history, "_LIMITS", {"plain60": 0.2})

    def cancelled(descriptor: int, count: int) -> bytes:
        raise KeyboardInterrupt("synthetic cancellation")

    error = {
        "nonzero": subprocess.CalledProcessError,
        "timeout": subprocess.TimeoutExpired,
        "overflow": ValueError,
        "cancellation": KeyboardInterrupt,
        "blocked_pipe": subprocess.TimeoutExpired,
    }[mode]
    with pytest.raises(error):
        history._closed(tmp_path, "plain60", ("synthetic",), limit=16)
    monkeypatch.setattr(history.os, "read", original_read)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert children[0].stdin is not None
    assert children[0].stdin.closed
    assert children[0].stdout is not None
    assert children[0].stdout.closed
    assert children[0].stderr is not None
    assert children[0].stderr.closed


def test_history_native_completion_detects_missing_object_after_acquisition(
    tmp_path: Path,
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=False)
    builder = history._Builder(root)
    assert builder.add("plain60", revision, {"a": None}, "positive") == {"a": contents["a"]}
    oid = builder.members["plain60", revision, "a"].oid
    path = root / ".git/objects" / oid[:2] / oid[2:]
    original = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(ValueError, match="availability"):
            builder.finish()
    finally:
        path.write_bytes(original)
    builder.finish()


@pytest.mark.parametrize("packed", [False, True])
def test_history_phase_owns_immutable_bytes_revokes_copied_context_and_reacquires(
    tmp_path: Path, packed: bool
) -> None:
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=packed)
    builder = history._Builder(root)
    assert builder.add("plain60", revision, {"a": None}, "native-authority") == {"a": contents["a"]}
    builder.finish()
    first = history._seal(builder, {"root": str(root)}, "fixture-runtime", "phase-one")
    original_certificate = first.certificate
    builder.contents.clear()
    builder.members.clear()
    with history._activate(first):
        assert first.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
        copied = contextvars.copy_context()
        view = first.blobs(root, "plain60", revision, ["a"])
        view["a"] = b"caller mutation"
        assert first.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
        with pytest.raises(TypeError):
            first.contents["plain60", revision, "a"] = b"mutation"
        with pytest.raises(TypeError):
            vars(first)
        with pytest.raises(TypeError):
            vars(first.members["plain60", revision, "a"])
        for domain, commit, names, selected_root in (
            ("safe60", revision, ["a"], root),
            ("plain60", "0" * 40, ["a"], root),
            ("plain60", revision, ["empty"], root),
            ("plain60", revision, ["a", "a"], root),
            ("plain60", revision, ["a"], tmp_path),
        ):
            with pytest.raises(ValueError, match=r"History|history"):
                first.blobs(selected_root, domain, commit, names)
        with pytest.raises(ValueError, match="Nested"), history._activate(first):
            raise AssertionError("Nested phase must never publish.")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(first.blobs, root, "plain60", revision, ["a"])
            with pytest.raises(ValueError, match="owner"):
                future.result()
        assert first.certificate == original_certificate
    assert history.eligible_blobs(root, revision, ["a"]) is None
    with pytest.raises(ValueError, match="inactive"):
        first.blobs(root, "plain60", revision, ["a"])
    with pytest.raises(ValueError, match="inactive"):
        copied.run(first.blobs, root, "plain60", revision, ["a"])
    second_builder = history._Builder(root)
    second_builder.add("plain60", revision, {"a": None}, "native-authority")
    second_builder.finish()
    second = history._seal(second_builder, {"root": str(root)}, "fixture-runtime", "phase-two")
    assert first.semantic_digest == second.semantic_digest
    assert first.phase_id != second.phase_id
    with history._activate(second):
        assert second.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
        with pytest.raises(ValueError, match="inactive"):
            copied.run(first.blobs, root, "plain60", revision, ["a"])
    third = history._seal(second_builder, {"root": str(root)}, "fixture-runtime", "phase-three")
    with pytest.raises(RuntimeError, match="body failure"), history._activate(third):
        raise RuntimeError("body failure")
    assert history.eligible_blobs(root, revision, ["a"]) is None
    assert third._lease.valid() is False


@pytest.mark.parametrize("packed", [False, True])
def test_history_published_operands_remain_stable_but_next_acquisition_is_fresh(
    tmp_path: Path, packed: bool
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=packed)
    builder = history._Builder(root)
    builder.add("plain60", revision, {"a": None}, "native-authority")
    builder.finish()
    snapshot = history._seal(builder, {"root": str(root)}, "fixture-runtime", "phase-one")
    objects = root / ".git/objects"
    held = root / ".git/objects-withheld"
    with history._activate(snapshot):
        objects.rename(held)
        objects.mkdir()
        try:
            assert snapshot.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
            with pytest.raises((ValueError, subprocess.CalledProcessError)):
                history._Builder(root).add("plain60", revision, {"a": None}, "fresh-phase")
            assert snapshot.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
        finally:
            objects.rmdir()
            held.rename(objects)
    restored = history._Builder(root)
    assert restored.add("plain60", revision, {"a": None}, "restored") == {"a": contents["a"]}
    restored.finish()


@pytest.mark.parametrize("failure", ["timeout", "nonzero"])
def test_history_postflight_failure_replaces_successful_smoke_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    calls = 0
    output = tmp_path / "receipt.json"
    attempt = tmp_path / "attempt.json"
    binding: dict[str, object] = {"input_digest": "positive-current-inputs"}

    def validate(root: Path, base_ref: str, *, pr_head: str | None) -> dict[str, object]:
        nonlocal calls
        calls += 1
        history._WITNESSES.get().append({"role": "preflight" if calls == 1 else "postflight"})
        if calls == 2:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(["git", "cat-file"], 60)
            raise subprocess.CalledProcessError(2, ["git", "cat-file"])
        return dict(binding)

    def smoke(root: Path, path: Path, *, binding: dict[str, object]) -> dict[str, object]:
        report = binding | {"status": "passed", "attempt_receipt": str(attempt)}
        cast(Any, gate)._write_receipt(path, report)
        assert json.loads(path.read_text())["status"] == "passed"
        return report

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "validate_current", validate)
    monkeypatch.setattr(gate, "run_smoke", smoke)
    error = subprocess.TimeoutExpired if failure == "timeout" else subprocess.CalledProcessError
    with pytest.raises(error):
        cast(Any, gate)._check_and_run("exact-base", None, output)
    receipt = json.loads(output.read_text())
    assert receipt == json.loads(attempt.read_text())
    assert receipt["status"] == "failed"
    assert receipt["inputs_unchanged"] is False
    assert receipt["history_phase_witnesses"] == [{"role": "preflight"}, {"role": "postflight"}]
    assert calls == 2
    assert history._WITNESSES.get() is None


def test_history_portable_digest_ignores_local_clone_and_pytest_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=False)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(root), str(clone)], check=True)
    for checkout in (root, clone):
        (checkout / "pyproject.toml").write_text("[project]\nname='native-history'\n")
        (checkout / "uv.lock").write_text("version = 1\n")
    first_identity = history._identity(root, revision, None, domain_state=True)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "another-consumer")
    second_identity = history._identity(clone, revision, None, domain_state=True)
    assert first_identity != second_identity
    first_builder, second_builder = history._Builder(root), history._Builder(clone)
    pins = {"a": hashlib.sha256(contents["a"]).hexdigest()}
    first_builder.add("plain60", revision, pins, "native-authority")
    second_builder.add("plain60", revision, pins, "native-authority")
    first = history._seal(first_builder, first_identity, "same-runtime", "one")
    second = history._seal(second_builder, second_identity, "same-runtime", "two")
    assert first.semantic_digest == second.semantic_digest
    assert first.certificate != second.certificate
    with history._activate(first):
        with pytest.raises(ValueError, match="another repository"):
            first.blobs(clone, "plain60", revision, ["a"])
        assert first.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}


@pytest.mark.parametrize("mutation", ["missing", "extra", "bytes", "mode", "oid", "authority"])
def test_history_publication_reconciles_native_members_and_original_declarations(
    tmp_path: Path, mutation: str
) -> None:
    from dataclasses import replace

    from tools import performance_history_snapshot

    history = cast(Any, performance_history_snapshot)
    root, revision, contents = _history_fixture(tmp_path, packed=False)
    builder = history._Builder(root)
    builder.add(
        "plain60", revision, {"a": hashlib.sha256(contents["a"]).hexdigest()}, "native-authority"
    )
    builder.finish()
    positive = history._seal(builder, {}, "runtime", "positive")
    with history._activate(positive):
        assert positive.blobs(root, "plain60", revision, ["a"]) == {"a": contents["a"]}
    key = "plain60", revision, "a"
    if mutation == "missing":
        del builder.contents[key]
    elif mutation == "extra":
        builder.contents["plain60", revision, "extra"] = b"extra"
    elif mutation == "bytes":
        builder.contents[key] = b"wrong"
    elif mutation == "mode":
        builder.members[key] = replace(builder.members[key], mode="120000")
    elif mutation == "oid":
        builder.members[key] = replace(builder.members[key], oid="0" * 40)
    else:
        builder.members[key] = replace(builder.members[key], authorities=("self-invented",))
    with pytest.raises(ValueError, match="History"):
        history._seal(builder, {}, "runtime", "negative")
