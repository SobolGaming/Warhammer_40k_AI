"""Explicit transaction-boundary contract controls for pure admission tooling."""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import Token
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

import pytest
from tools import performance_history_snapshot as history
from tools import performance_preflight as preflight

pytestmark = pytest.mark.stubbed


class _Storage(Protocol):
    limit: int
    retained: int
    active: bool
    owner: tuple[int, int]
    path_plan_charge: int
    entries: dict[tuple[Callable[..., Any], str], tuple[bytes, str]]

    def digest(self, path: str, raw: bytes) -> str: ...


class _Lease(Protocol):
    active: bool
    charge: int
    result: dict[str, bytes]
    repository: tuple[object, ...]
    phase: tuple[str, ...]
    dependencies: tuple[object, ...]

    def revoke(self) -> None: ...


class _Internals(Protocol):
    _DIGESTS: contextvars.ContextVar[_Storage | None]
    _ADMISSION_TRANSACTION: contextvars.ContextVar[_Lease | None]

    def _Digests(self, limit: int) -> _Storage: ...

    def _source_members(
        self,
        root: Path,
        names: list[str],
        *,
        observe_ancestors: bool,
        read_limit: int | None = None,
    ) -> Iterator[tuple[str, int, bytes]]: ...

    def new_storage(self, limit: int) -> _Storage:
        return self._Digests(limit)

    def current_storage(self) -> _Storage | None:
        return self._DIGESTS.get()

    def bind_storage(self, value: _Storage | None) -> Token[_Storage | None]:
        return self._DIGESTS.set(value)

    def reset_storage(self, token: Token[_Storage | None]) -> None:
        self._DIGESTS.reset(token)

    def current_transaction(self) -> _Lease | None:
        return self._ADMISSION_TRANSACTION.get()

    def members(
        self,
        root: Path,
        names: list[str],
        *,
        observe_ancestors: bool,
        read_limit: int | None = None,
    ) -> Iterator[tuple[str, int, bytes]]:
        return self._source_members(
            root, names, observe_ancestors=observe_ancestors, read_limit=read_limit
        )


internals = cast(_Internals, preflight)
PHASE = ("root", "phase", "authenticated-history")


def phase_identity(_: Path) -> tuple[str, ...]:
    return PHASE


def inactive_identity(_: Path) -> None:
    return None


def other_identity(_: Path) -> tuple[str, ...]:
    return ("other-phase",)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "member").write_bytes(b"original")
    monkeypatch.setattr(history, "proof_identity", phase_identity)
    return tmp_path


@contextmanager
def storage(limit: int = 1024 * 1024) -> Generator[_Storage]:
    value = _Internals.new_storage(internals, limit)
    token = _Internals.bind_storage(internals, value)
    try:
        yield value
    finally:
        value.active = False
        _Internals.reset_storage(internals, token)


def original(root: Path) -> dict[str, bytes]:
    raw = (root / "member").read_bytes()
    if raw != b"original":
        raise ValueError("invalid current member")
    return {"member": raw}


def test_transaction_uses_complete_start_end_and_defensive_results(root: Path) -> None:
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache:
        with preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
            first = preflight.grouped_admission(root, acquire)
            first["member"] = b"caller mutation"
            first["extra"] = b"unrelated"
            assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
            assert len(calls) == 1
            assert cache.retained > 0
        assert calls == [root, root]
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


@pytest.mark.parametrize("enabled", [False, True], ids=["no-invocation", "no-history"])
def test_default_calls_remain_fresh(
    root: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    if enabled:
        monkeypatch.setattr(history, "proof_identity", inactive_identity)
    with (
        storage() if enabled else nullcontext(),
        preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
    ):
        assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
        (root / "member").write_bytes(b"invalid")
        with pytest.raises(ValueError, match="invalid current member"):
            preflight.grouped_admission(root, acquire)
    assert calls == [root, root]


def test_invalid_entry_never_publishes_result(root: Path) -> None:
    (root / "member").write_bytes(b"invalid")
    with storage() as cache:
        with (
            pytest.raises(ValueError, match="invalid current member"),
            preflight.ci60_transaction(root, original, lambda: (original,)),
        ):
            pytest.fail("invalid entry published")
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


@pytest.mark.parametrize("change", ["invalid", "accepted-different"])
def test_exit_rejects_persistent_change(root: Path, change: str) -> None:

    def acquire(path: Path) -> dict[str, bytes]:
        return original(path) if change == "invalid" else {"member": (path / "member").read_bytes()}

    with storage() as cache:
        match = "invalid current member" if change == "invalid" else "complete result changed"
        with (
            pytest.raises(ValueError, match=match),
            preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
        ):
            (root / "member").write_bytes(b"different")
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


def test_reverted_transient_change_is_explicitly_allowed_within_one_boundary(root: Path) -> None:
    with storage():
        with preflight.ci60_transaction(root, original, lambda: (original,)):
            (root / "member").write_bytes(b"temporary")
            assert preflight.grouped_admission(root, original) == {"member": b"original"}
            (root / "member").write_bytes(b"original")
        (root / "member").write_bytes(b"invalid")
        with (
            pytest.raises(ValueError, match="invalid current member"),
            preflight.ci60_transaction(root, original, lambda: (original,)),
        ):
            pytest.fail("next transaction reused old bytes")


@pytest.mark.parametrize("error", [ValueError("body failure"), KeyboardInterrupt("cancel")])
def test_body_failure_preserves_exception_and_always_checks_end(
    root: Path, error: BaseException
) -> None:
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache:
        with (
            pytest.raises(type(error)) as observed,
            preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
        ):
            raise error
        assert observed.value is error
        assert calls == [root, root]
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


def test_dual_failure_keeps_original_exception_context(root: Path) -> None:
    body_error = ValueError("body failure")

    def failing_body() -> None:
        (root / "member").write_bytes(b"invalid")
        raise body_error

    with storage() as cache:
        with (
            pytest.raises(ValueError, match="invalid current member") as observed,
            preflight.ci60_transaction(root, original, lambda: (original,)),
        ):
            failing_body()
        assert observed.value.__context__ is body_error
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


@pytest.mark.parametrize("changed", ["phase", "dependencies", "root", "entrypoint", "invocation"])
def test_active_lease_rejects_identity_drift(
    root: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    selector: list[object] = ["original"]

    def other_entrypoint(path: Path) -> dict[str, bytes]:
        return original(path)

    def bindings() -> tuple[object, ...]:
        return tuple(selector)

    with storage() as cache:
        with preflight.ci60_transaction(root, original, bindings), monkeypatch.context() as patch:
            path = root
            fresh: Callable[[Path], dict[str, bytes]] = original
            token = None
            if changed == "phase":
                patch.setattr(history, "proof_identity", other_identity)
            elif changed == "dependencies":
                selector[:] = ["changed"]
            elif changed == "root":
                path = root / "other"
            elif changed == "entrypoint":
                fresh = other_entrypoint
            else:
                token = _Internals.bind_storage(internals, _Internals.new_storage(internals, 1024))
            try:
                with pytest.raises(ValueError, match="transaction"):
                    preflight.grouped_admission(path, fresh)
            finally:
                if token is not None:
                    _Internals.reset_storage(internals, token)
                selector[:] = ["original"]
        assert cache.retained == 0


@pytest.mark.parametrize("owner", ["pid", "thread"])
def test_cross_owner_context_cannot_use_lease(
    root: Path, monkeypatch: pytest.MonkeyPatch, owner: str
) -> None:
    import threading

    with (
        storage(),
        preflight.ci60_transaction(root, original, lambda: (original,)),
        monkeypatch.context() as patch,
    ):
        if owner == "pid":
            current_pid = os.getpid()
            patch.setattr(os, "getpid", lambda: current_pid + 1)
        else:
            current_thread = threading.get_ident()
            patch.setattr(threading, "get_ident", lambda: current_thread + 1)
        with pytest.raises(ValueError, match="identity"):
            preflight.grouped_admission(root, original)


def test_same_owner_copy_participates_but_revoked_copy_cannot_escape(root: Path) -> None:
    with storage() as cache:
        with preflight.ci60_transaction(root, original, lambda: (original,)):
            copied = contextvars.copy_context()
            lease = _Internals.current_transaction(internals)
            assert lease is not None
            active_lengths = tuple(
                len(value) for value in (lease.repository, lease.phase, lease.dependencies)
            )
            assert all(active_lengths)
            assert copied.run(preflight.grouped_admission, root, original) == {
                "member": b"original"
            }
            with (
                pytest.raises(ValueError, match="Nested"),
                copied.run(preflight.ci60_transaction, root, original, lambda: (original,)),
            ):
                pytest.fail("nested transaction accepted")
        released_lengths = tuple(
            len(value) for value in (lease.repository, lease.phase, lease.dependencies)
        )
        assert released_lengths == (0, 0, 0)
        assert lease.charge == 0
        assert lease.result == {}
        lease.revoke()
        assert cache.retained == 0
        with pytest.raises(ValueError, match="identity"):
            copied.run(preflight.grouped_admission, root, original)


def test_complete_result_reservation_evicts_only_digest_entries(root: Path) -> None:
    with storage(16 * 1024) as cache:
        cache.digest("old", b"x" * (16 * 1024 - 1))
        assert cache.retained == 16 * 1024 - 1
        with preflight.ci60_transaction(root, original, lambda: (original,)):
            assert not cache.entries
            assert 0 < cache.retained <= cache.limit
            assert preflight.grouped_admission(root, original) == {"member": b"original"}
        assert cache.retained == 0


def test_tiny_capacity_retains_original_fresh_calls_and_allows_later_fit(root: Path) -> None:
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage(1) as cache:
        with preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
            assert _Internals.current_transaction(internals) is None
            assert cache.retained == 0
            assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
            (root / "member").write_bytes(b"invalid")
            with pytest.raises(ValueError, match="invalid current member"):
                preflight.grouped_admission(root, acquire)
            (root / "member").write_bytes(b"original")
        assert calls == [root, root, root]
        cache.limit = 1024 * 1024
        with preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
            assert _Internals.current_transaction(internals) is not None
            assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
        assert calls == [root] * 5
        assert cache.retained == 0


def test_expired_phase_cannot_inherit_transaction_result(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with storage(), preflight.ci60_transaction(root, original, lambda: (original,)):
        monkeypatch.setattr(history, "proof_identity", inactive_identity)
        with pytest.raises(ValueError, match="identity"):
            preflight.grouped_admission(root, original)
        monkeypatch.setattr(history, "proof_identity", phase_identity)


def test_transaction_rejects_storage_owned_by_another_context(root: Path) -> None:
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache:
        current = cache.owner
        cache.owner = (current[0] + 1, current[1])
        try:
            with (
                pytest.raises(ValueError, match="identity"),
                preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
            ):
                pytest.fail("foreign invocation published a transaction")
        finally:
            cache.owner = current
        assert calls == []
        assert cache.retained == 0


def test_escaped_manager_is_revoked_before_invocation_storage_is_cleared(root: Path) -> None:
    saved: list[Any] = []

    @preflight.invocation
    def escape() -> _Storage:
        cache = _Internals.current_storage(internals)
        assert cache is not None
        manager = preflight.ci60_transaction(root, original, lambda: (original,))
        manager.__enter__()
        saved.append(manager)
        assert cache.retained > 0
        return cache

    cache = escape()
    try:
        assert not cache.active
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None
    finally:
        with pytest.raises(ValueError, match="identity"):
            saved[0].__exit__(None, None, None)
    assert cache.retained == 0
    assert _Internals.current_transaction(internals) is None


def test_copied_context_is_revoked_before_fresh_end_acquisition(root: Path) -> None:
    copied: list[contextvars.Context] = []
    calls = 0

    def acquire(path: Path) -> dict[str, bytes]:
        nonlocal calls
        calls += 1
        if calls == 2:
            with pytest.raises(ValueError, match="identity"):
                copied[0].run(preflight.grouped_admission, root, acquire)
        return original(path)

    with storage() as cache:
        with preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
            copied.append(contextvars.copy_context())
        assert cache.retained == 0
    assert calls == 2


@pytest.mark.parametrize("boundary", [1, 2], ids=["entry", "end"])
def test_transaction_reentry_is_rejected_during_full_boundary_acquisition(
    root: Path, boundary: int
) -> None:
    calls = 0

    def acquire(path: Path) -> dict[str, bytes]:
        nonlocal calls
        calls += 1
        if calls == boundary:
            with (
                pytest.raises(ValueError, match="Nested"),
                preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
            ):
                pytest.fail("recursive acquisition opened another transaction")
            with pytest.raises(ValueError, match="boundary"):
                preflight.grouped_admission(root, acquire)
        return original(path)

    with storage() as cache, preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
        assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
    assert calls == 2
    assert cache.retained == 0


def test_cross_context_exit_error_still_revokes_result_and_charge(root: Path) -> None:
    @preflight.invocation
    def run() -> None:
        cache = _Internals.current_storage(internals)
        assert cache is not None
        manager = preflight.ci60_transaction(root, original, lambda: (original,))
        manager.__enter__()
        copied = contextvars.copy_context()
        with pytest.raises(ValueError, match="different Context"):
            copied.run(manager.__exit__, None, None, None)
        assert cache.retained == 0
        with pytest.raises(ValueError, match="identity"):
            preflight.grouped_admission(root, original)

    run()
    assert _Internals.current_transaction(internals) is None


def test_worktree_pointer_bytes_are_bound_with_protected_reads(root: Path) -> None:
    pointer = root / ".git"
    pointer.rmdir()
    before = b"gitdir: /retained/metadata\n"
    pointer.write_bytes(before)
    inode = pointer.stat().st_ino
    observed = preflight.source_members(root, [".git"])
    assert type(observed) is tuple
    assert len(observed) == 1
    assert observed[0][0] == ".git"
    assert type(observed[0][1]) is int
    assert type(observed[0][2]) is bytes
    assert observed[0][2] == before
    with storage() as cache, preflight.ci60_transaction(root, original, lambda: (original,)):
        assert cache.retained >= len(before)
        assert preflight.grouped_admission(root, original) == {"member": b"original"}
        pointer.write_bytes(b"gitdir: /different/location\n")
        assert pointer.stat().st_ino == inode
        with pytest.raises(ValueError, match="identity"):
            preflight.grouped_admission(root, original)
        pointer.write_bytes(before)


@pytest.mark.parametrize("kind", ["symlink", "hardlinked-pointer"])
def test_unsupported_metadata_uses_original_fresh_path(root: Path, kind: str) -> None:
    pointer = root / ".git"
    pointer.rmdir()
    if kind == "symlink":
        target = root / "metadata"
        target.mkdir()
        pointer.symlink_to(target, target_is_directory=True)
    else:
        pointer.write_bytes(b"gitdir: /retained/metadata\n")
        os.link(pointer, root / "other-pointer")
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache, preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
        assert _Internals.current_transaction(internals) is None
        assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
        (root / "member").write_bytes(b"invalid")
        with pytest.raises(ValueError, match="invalid current member"):
            preflight.grouped_admission(root, acquire)
        assert cache.retained == 0
    assert calls == [root, root]


@pytest.mark.parametrize(
    "variable", ["GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"]
)
def test_repository_selector_environment_cannot_borrow_old_result(
    root: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    with (
        storage(),
        preflight.ci60_transaction(root, original, lambda: (original,)),
        monkeypatch.context() as patch,
    ):
        patch.setenv(variable, "/different-task-repository")
        with pytest.raises(ValueError, match="identity"):
            preflight.grouped_admission(root, original)


@pytest.mark.parametrize(
    "changed",
    [
        "eligible_blobs",
        "history_oid",
        "history_path",
        "reader_api",
        "path_method",
        "tail_method_code",
        "keyword_default",
        "native_callable",
        "selector",
        "owner_wrapper",
        "fresh_code",
    ],
)
def test_actual_finite_binding_closure_rejects_callable_and_selector_drift(
    root: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    import io

    from tools import performance_ci60_qualification as q

    def replacement(*args: Any, **kwargs: Any) -> Any:
        return args, kwargs

    def other_relative(self: Path, other: Path) -> bool:
        return self == other

    with (
        storage(),
        preflight.ci60_transaction(root, original, preflight.ci60_admission_bindings),
        monkeypatch.context() as patch,
    ):
        if changed == "eligible_blobs":
            patch.setattr(history, "eligible_blobs", replacement)
        elif changed == "history_oid":
            patch.setattr(history, "_oid", replacement)
        elif changed == "history_path":
            patch.setattr(history, "_path", replacement)
        elif changed == "reader_api":
            patch.setattr(io, "open", replacement)
        elif changed == "path_method":
            patch.setattr(Path, "is_relative_to", other_relative)
        elif changed == "tail_method_code":
            patch.setattr(Path.is_relative_to, "__code__", other_relative.__code__)
        elif changed == "keyword_default":
            patch.setattr(vars(preflight)["_same_file"], "__kwdefaults__", {"compare_ctime": False})
        elif changed == "native_callable":
            patch.setattr(q, "git", len)
        elif changed == "selector":
            patch.setattr(q, "PRELUDE_CONTROLS", q.PRELUDE_CONTROLS | {"different-owner"})
        elif changed == "owner_wrapper":
            from tools import performance_policy as policy

            patch.setattr(policy, "owner_hashes", len)
        else:
            patch.setattr(q.fresh_admission, "__code__", replacement.__code__)
        with pytest.raises(ValueError, match="transaction"):
            preflight.grouped_admission(root, original)


def test_mutable_payload_cannot_be_published_as_immutable_lease(root: Path) -> None:
    mutable = bytearray(b"original")

    def acquire(_: Path) -> dict[str, bytes]:
        return cast(dict[str, bytes], {"member": mutable})

    with storage() as cache:
        with (
            pytest.raises(ValueError, match="immutable byte result"),
            preflight.ci60_transaction(root, acquire, lambda: (acquire,)),
        ):
            pytest.fail("mutable result published")
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None


def test_unsupported_mutable_function_default_fails_closed(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        storage(),
        preflight.ci60_transaction(root, original, preflight.ci60_admission_bindings),
        monkeypatch.context() as patch,
    ):
        patch.setattr(vars(preflight)["_same_file"], "__kwdefaults__", {"compare_ctime": []})
        with pytest.raises(ValueError, match="defaults changed"):
            preflight.grouped_admission(root, original)


def test_mutable_selector_before_entry_is_rejected_without_retaining_alias(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_ci60_qualification as q

    selected = set(q.PRELUDE_CONTROLS)
    calls: list[Path] = []

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache, monkeypatch.context() as patch:
        patch.setattr(q, "PRELUDE_CONTROLS", selected)
        with (
            pytest.raises(ValueError, match="selector"),
            preflight.ci60_transaction(root, acquire, preflight.ci60_admission_bindings),
        ):
            pytest.fail("mutable selector became a dependency alias")
        selected.add("mutated-in-place")
        assert cache.retained == 0
        assert _Internals.current_transaction(internals) is None
    assert calls == []


def test_oversized_pointer_falls_back_before_any_pointer_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = root / ".git"
    pointer.rmdir()
    pointer.write_bytes(b"x" * (64 * 1024 + 1))
    reads: list[list[str]] = []
    calls: list[Path] = []

    def forbidden_pointer_read(_: Path, names: list[str]) -> tuple[Any, ...]:
        reads.append(names)
        pytest.fail("oversized pointer was acquired")

    def acquire(path: Path) -> dict[str, bytes]:
        calls.append(path)
        return original(path)

    with storage() as cache, monkeypatch.context() as patch:
        patch.setattr(preflight, "source_members", forbidden_pointer_read)
        with preflight.ci60_transaction(root, acquire, lambda: (acquire,)):
            assert _Internals.current_transaction(internals) is None
            assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
            assert preflight.grouped_admission(root, acquire) == {"member": b"original"}
        assert cache.retained == 0
    assert reads == []
    assert calls == [root, root]


def test_worktree_pointer_complete_bytes_contribute_to_retained_charge(root: Path) -> None:
    with storage() as cache:
        with preflight.ci60_transaction(root, original, lambda: (original,)):
            directory_charge = cache.retained
        pointer = root / ".git"
        pointer.rmdir()
        raw = b"gitdir: /retained/" + b"a" * 8000 + b"\n"
        pointer.write_bytes(raw)
        with preflight.ci60_transaction(root, original, lambda: (original,)):
            assert cache.retained - directory_charge >= len(raw)
        assert cache.retained == cache.path_plan_charge
        assert 0 < cache.retained < len(raw)
        assert _Internals.current_transaction(internals) is None


def test_original_default_reader_matches_explicit_none_with_real_owned_bytes(root: Path) -> None:
    normal = tuple(_Internals.members(internals, root, ["member"], observe_ancestors=True))
    explicit = tuple(
        _Internals.members(internals, root, ["member"], observe_ancestors=True, read_limit=None)
    )
    assert normal == explicit == preflight.source_members(root, ["member"])
    assert normal[0][0] == "member"
    assert normal[0][2] == b"original"


def test_pointer_growth_after_stat_is_rejected_by_bounded_actual_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = root / ".git"
    pointer.rmdir()
    pointer.write_bytes(b"gitdir: /retained/metadata\n")
    original_open = Path.open
    read_sizes: list[int] = []

    class Reader:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream

        def fileno(self) -> int:
            return self.stream.fileno()

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return self.stream.read(size)

    @contextmanager
    def opened(path: Path, *args: Any, **kwargs: Any) -> Generator[Reader]:
        with cast(BinaryIO, original_open(path, *args, **kwargs)) as stream:
            if path == pointer:
                with original_open(pointer, "ab") as writer:
                    writer.write(b"x" * (64 * 1024 + 1))
            yield Reader(stream)

    with storage() as cache, monkeypatch.context() as patch:
        patch.setattr(Path, "open", opened)
        with (
            pytest.raises(ValueError, match="exceeded read limit"),
            preflight.ci60_transaction(root, original, lambda: (original,)),
        ):
            pytest.fail("growing pointer published a transaction")
        assert cache.retained == cache.path_plan_charge
        assert _Internals.current_transaction(internals) is None
    assert read_sizes == [64 * 1024 + 1]
    assert pointer.stat().st_size > 64 * 1024


@pytest.mark.parametrize(
    "changed",
    [
        "valid",
        "second-new",
        "removed-old",
        "new-test-already-old",
        "missing-new",
        "missing-d07-json",
        "missing-ci69-module",
    ],
)
def test_only_the_exact_declared_transaction_input_addition_is_admitted(changed: str) -> None:
    from tools import performance_ci60_qualification as q
    from tools import performance_ci69_members as ci69

    assert "tests/rules/section24/README.md" in q.PRELUDE_INPUTS
    assert "tests/measurement_native_api.py" in ci69.CUTOVER_ADDED_INPUTS

    previous = {"unchanged-prior-owner": "a", "changed-prior-owner": "b"}
    produced = (
        previous
        | {
            q.TRANSACTION_TEST: "current",
            "tests/data/d07_geometry_containment_v3.json": "current-d07",
            "tools/performance_ci69_members.py": "current-ci69",
            "changed-prior-owner": "c",
        }
        | dict.fromkeys(ci69.CUTOVER_ADDED_INPUTS, "current-cutover")
    )
    if changed == "second-new":
        produced["undeclared-extra-owner"] = "different"
    elif changed == "removed-old":
        del produced["unchanged-prior-owner"]
    elif changed == "new-test-already-old":
        previous[q.TRANSACTION_TEST] = "historical"
    elif changed == "missing-new":
        del produced[q.TRANSACTION_TEST]
    elif changed == "missing-d07-json":
        del produced["tests/data/d07_geometry_containment_v3.json"]
    elif changed == "missing-ci69-module":
        del produced["tools/performance_ci69_members.py"]
    predicate = cast(
        Callable[[dict[str, str], dict[str, str]], bool], vars(q)["_transaction_inputs_match"]
    )
    assert predicate(previous, produced) is (changed == "valid")
    if changed == "valid":
        without_adapter = produced.copy()
        del without_adapter["tests/measurement_native_api.py"]
        assert predicate(previous, without_adapter) is False


@pytest.mark.parametrize("observed", [b"", b"100644 blob authentic-existing-member"])
def test_exact_historical_absence_rejects_any_nonempty_native_result(observed: bytes) -> None:
    from tools import performance_ci60_qualification as q

    require_absence = cast(Callable[[bytes], None], vars(q)["_transaction_absence"])
    if observed:
        with pytest.raises(ValueError, match="existed"):
            require_absence(observed)
    else:
        assert require_absence(observed) is None


_COMPUTATION_CALLS: list[str] = []


def _compute_first(operands: preflight.AdmissionOperands, identity: tuple[str, ...]) -> None:
    _COMPUTATION_CALLS.append("first")
    if operands != (("member", 33188, b"original"), ("other", 33188, b"stable")):
        raise ValueError("invalid complete computation operands")


def _compute_second(operands: preflight.AdmissionOperands, identity: tuple[str, ...]) -> None:
    _COMPUTATION_CALLS.append("second")
    if operands != (("member", 33188, b"original"), ("other", 33188, b"stable")):
        raise ValueError("invalid complete computation operands")


@pytest.fixture
def computation_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tools import performance_ci60_qualification as q

    (root / q.NAMESPACE).mkdir(parents=True)
    (root / "other").write_bytes(b"stable")
    monkeypatch.setattr(history, "proof_identity", inactive_identity)
    monkeypatch.setattr(q, "_current_derivation_transition", _compute_first)
    monkeypatch.setattr(q, "_admitted_derivation", _compute_second)
    _COMPUTATION_CALLS.clear()
    return root


def _compute_observation(root: Path) -> preflight.AdmissionOperands:
    return preflight.source_members(root, ["member", "other"])


def _compute_validate(root: Path, operands: preflight.AdmissionOperands) -> None:
    for validator in (_compute_first, _compute_second):
        preflight.admission_proof(validator, operands, None, (validator,), repository=root)


def test_computation_only_scope_keeps_fresh_reads_and_isolates_calls(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[preflight.AdmissionOperands] = []
    calls: list[str] = []

    @preflight.owner_proof
    def owners(path: str, content: bytes | None) -> dict[str, str]:
        calls.append("owner")
        return {path: str(content)}

    @preflight.recipe_proof
    def recipe(before: bytes, current: bytes, value: dict[str, Any]) -> None:
        calls.append("recipe")

    def acquire() -> dict[str, str]:
        for _ in range(3):
            operands = _compute_observation(computation_root)
            observed.append(operands)
            _compute_validate(computation_root, operands)
            assert history.proof_identity(computation_root) is None
            assert _Internals.current_transaction(internals) is None
            owners("member", b"original")
            recipe(b"before", b"after", {})
        return {"complete": "result"}

    assert preflight.ci60_computation(computation_root, acquire) == {"complete": "result"}
    assert _COMPUTATION_CALLS == ["first", "second"]
    assert calls == ["owner", "recipe"] * 3
    assert len(observed) == 3
    assert observed[0] == observed[1] == observed[2]
    assert observed[0][0][2] is not observed[1][0][2]
    assert _Internals.current_storage(internals) is None
    preflight.ci60_computation(computation_root, acquire)
    assert _COMPUTATION_CALLS == ["first", "second"] * 2


@pytest.mark.parametrize("change", ["bytes", "mode", "order", "root"])
def test_computation_only_scope_revalidates_complete_operands(
    computation_root: Path, change: str
) -> None:
    def acquire() -> None:
        operands = _compute_observation(computation_root)
        _compute_validate(computation_root, operands)
        if change == "bytes":
            (computation_root / "member").write_bytes(b"tampered")
            changed = _compute_observation(computation_root)
        elif change == "mode":
            changed = (("member", 33216, b"original"), operands[1])
        elif change == "order":
            changed = tuple(reversed(operands))
        else:
            with pytest.raises(ValueError, match="another repository"):
                _compute_validate(computation_root.parent, operands)
            return
        with pytest.raises(ValueError, match="invalid complete computation operands"):
            _compute_validate(computation_root, changed)

    preflight.ci60_computation(computation_root, acquire)
    assert _Internals.current_storage(internals) is None


@pytest.mark.parametrize("change", ["function", "code", "closure", "selector", "json"])
def test_computation_only_scope_rejects_dependency_changes(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from tools import performance_ci60_qualification as q
    from tools import performance_policy as policy

    def acquire() -> None:
        operands = _compute_observation(computation_root)
        _compute_validate(computation_root, operands)
        owner = policy.owner_hashes
        closure = owner.__closure__
        assert closure is not None
        cell = closure[0]
        captured = cell.cell_contents
        try:
            with monkeypatch.context() as patch:
                if change == "function":
                    patch.setattr(q, "_admitted_derivation", _compute_first)
                elif change == "code":
                    patch.setattr(_compute_second, "__code__", _compute_first.__code__)
                elif change == "closure":
                    cell.cell_contents = _compute_first
                elif change == "selector":
                    patch.setattr(q, "BASE", "f" * 40)
                else:

                    def changed_json(value: object) -> dict[str, object]:
                        return {}

                    patch.setattr(json, "loads", changed_json)
                with pytest.raises(ValueError, match=r"computation.*changed"):
                    _compute_validate(computation_root, operands)
        finally:
            cell.cell_contents = captured

    preflight.ci60_computation(computation_root, acquire)
    assert _Internals.current_storage(internals) is None


@pytest.mark.parametrize("error", [ValueError("body failure"), KeyboardInterrupt("cancel")])
def test_computation_only_scope_revokes_on_failure(
    computation_root: Path, error: BaseException
) -> None:
    retained: list[_Storage] = []

    def acquire() -> None:
        cache = _Internals.current_storage(internals)
        assert cache is not None
        retained.append(cache)
        _compute_validate(computation_root, _compute_observation(computation_root))
        raise error

    with pytest.raises(type(error)) as observed:
        preflight.ci60_computation(computation_root, acquire)
    assert observed.value is error
    assert _Internals.current_storage(internals) is None
    assert retained[0].retained == 0
    assert not retained[0].active


def test_computation_only_scope_capacity_fallback_stays_fresh(computation_root: Path) -> None:
    def acquire() -> None:
        cache = _Internals.current_storage(internals)
        assert cache is not None
        cache.limit = 0
        for _ in range(2):
            _compute_validate(computation_root, _compute_observation(computation_root))
        assert cache.retained == 0

    preflight.ci60_computation(computation_root, acquire)
    assert _COMPUTATION_CALLS == ["first", "second"] * 2


def _compute_unselected(operands: preflight.AdmissionOperands, identity: tuple[str, ...]) -> None:
    pytest.fail("an unselected computation callback ran")


@pytest.mark.parametrize("direct", [False, True], ids=["changed-factory", "direct-wrong-pair"])
def test_computation_only_scope_rejects_unselected_callbacks(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch, direct: bool
) -> None:
    from tools import performance_ci60_qualification as q

    if not direct:
        monkeypatch.setattr(
            q, "admission_validators", lambda: (_compute_first, _compute_unselected)
        )
        with pytest.raises(ValueError, match="exact two pure validators"):
            preflight.ci60_computation(computation_root, lambda: None)
    else:

        @preflight.invocation
        def acquire() -> None:
            with preflight.ci60_bootstrap_admission(
                computation_root,
                (_compute_first, _compute_unselected),
                lambda: None,
                computation_only=True,
            ):
                pytest.fail("unselected callbacks were published")

        with pytest.raises(ValueError, match=r"two validators|exact two pure validators"):
            acquire()
    assert not _COMPUTATION_CALLS
    assert _Internals.current_storage(internals) is None


def test_computation_only_scope_cannot_promote_or_group_after_unexpected_phase(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected: list[tuple[str, ...] | None] = [None]
    fresh_calls: list[Path] = []

    def identity(root: Path) -> tuple[str, ...] | None:
        return selected[0]

    def fresh(root: Path) -> dict[str, bytes]:
        fresh_calls.append(root)
        raw = (root / "live").read_bytes()
        if raw != b"original":
            raise ValueError("changed live input")
        return {"live": raw}

    monkeypatch.setattr(history, "proof_identity", identity)
    (computation_root / "live").write_bytes(b"original")

    def acquire() -> None:
        operands = _compute_observation(computation_root)
        _compute_validate(computation_root, operands)
        selected[0] = PHASE
        with preflight.ci60_phase_admission(computation_root, PHASE):
            _compute_validate(computation_root, operands)
            with preflight.ci60_transaction(computation_root, fresh, lambda: (fresh,)):
                assert _Internals.current_transaction(internals) is None
                assert preflight.grouped_admission(computation_root, fresh) == {"live": b"original"}
                (computation_root / "live").write_bytes(b"changed")
                with pytest.raises(ValueError, match="changed live input"):
                    preflight.grouped_admission(computation_root, fresh)
        selected[0] = None
        _compute_validate(computation_root, operands)

    preflight.ci60_computation(computation_root, acquire)
    assert _COMPUTATION_CALLS == ["first", "second"] * 3
    assert fresh_calls == [computation_root] * 2
    assert _Internals.current_transaction(internals) is None
    assert _Internals.current_storage(internals) is None


@pytest.mark.parametrize("dependency", ["json", "hash"])
def test_computation_only_scope_rejects_preinstalled_mutable_dependency_closures(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch, dependency: str
) -> None:

    captured: list[object] = ["mutable"]

    def changed(*args: Any, **kwargs: Any) -> object:
        return captured[0]

    with monkeypatch.context() as patch:
        if dependency == "json":
            patch.setattr(json, "loads", changed)
        else:
            patch.setattr(hashlib, "sha256", changed)
        with pytest.raises(ValueError, match="dependency closure changed"):
            preflight.ci60_computation(computation_root, lambda: None)
    assert not _COMPUTATION_CALLS
    assert _Internals.current_storage(internals) is None


def test_computation_only_scope_rejects_callable_dependency_instances(
    computation_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    class MutableCallable:
        def __call__(self, *args: Any, **kwargs: Any) -> object:
            return {}

    with monkeypatch.context() as patch:
        patch.setattr(json, "loads", MutableCallable())
        with pytest.raises(ValueError, match="dependency closure changed"):
            preflight.ci60_computation(computation_root, lambda: None)
    assert not _COMPUTATION_CALLS
    assert _Internals.current_storage(internals) is None


def test_category_forwarder_real_pytest_reporter_lifetime(tmp_path: Path) -> None:
    """Run the actual fixture AST with pinned pytest, four workers and reporter."""
    import ast
    import json
    import sys

    from scripts.quality_runner import Deadlines, Supervisor

    assert os.name == "posix", "This supervised Linux-local control requires POSIX process groups"
    root = Path(__file__).resolve().parents[2]
    category = root / "tests/code_quality/test_performance_category_migration.py"
    source = category.read_text(encoding="utf-8")
    fixture = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "private_computation_scope"
    )
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "from pathlib import Path\nfrom collections.abc import Iterator\n"
        "from functools import wraps\nfrom types import SimpleNamespace\n"
        "from typing import Any, cast\n"
        "import pytest\nfrom tools import performance_preflight as preflight\n"
        "def original_verify(root, *, value, default='original-default'):\n"
        "    assert isinstance(root, Path) and default == 'original-default'\n"
        "    if value == 'error':\n"
        "        raise ValueError('forwarded error') from KeyError('original cause')\n"
        "    return value\n"
        "migration = SimpleNamespace(verify_current_inventory=original_verify)\n"
        + ast.unparse(fixture)
        + "\n@pytest.mark.parametrize('value', ['one', 'two', 'error'])\n"
        "def test_probe(value, tmp_path):\n"
        "    assert migration.verify_current_inventory is not original_verify\n"
        "    assert migration.verify_current_inventory(tmp_path, value=value) == value\n"
        "ORIGINAL_TEST = test_probe\n",
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "import pytest\nfrom scripts import quality_reporter as reporter\n"
        "@pytest.hookimpl(wrapper=True, trylast=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    report = yield\n"
        "    if call.when == 'call':\n"
        "        assert item.module.migration.verify_current_inventory "
        "is item.module.original_verify\n"
        "        assert item.obj is item.module.ORIGINAL_TEST\n"
        "        reporter.reporter().journal.emit('wrapper_restored', node=item.nodeid)\n"
        "    return report\n",
        encoding="utf-8",
    )
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\naddopts =\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    binding = "diagnostic-wrapper-lifetime"
    nodes = [f"test_probe.py::test_probe[{value}]" for value in ("one", "two", "error")]
    admitted = {
        "binding": binding,
        "inventory": {"shards": {"diagnostic": {"nodes": nodes}}},
    }
    (evidence / "admitted.json").write_text(json.dumps(admitted), encoding="utf-8")
    (evidence / "start.json").write_text('{"shard":"diagnostic"}', encoding="utf-8")
    environment = dict(os.environ)
    for name in ("PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        environment.pop(name, None)
    environment.update(
        PYTHONPATH=str(root) + os.pathsep + str(root / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        QUALITY_EVIDENCE_DIR=str(evidence),
        QUALITY_EVIDENCE_MODE="execute",
        QUALITY_EVIDENCE_BINDING=binding,
    )
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-c",
        str(ini),
        "-p",
        "xdist.plugin",
        "-p",
        "scripts.quality_reporter",
        "-n",
        "4",
        "--dist=worksteal",
        "--max-worker-restart=0",
        "-q",
        str(probe),
    ]
    supervisor = Supervisor(evidence, binding, Deadlines(45, 50, 55, 60))
    try:
        status = supervisor.run(command, tmp_path, environment, "probe")
    finally:
        watchdog_status = supervisor.close()
    log = (evidence / "probe.log").read_text(encoding="utf-8")
    assert status == 1, log
    assert watchdog_status == 0, log
    native = json.loads((evidence / "probe-process.json").read_text(encoding="utf-8"))
    assert native["exit_status"] == 1
    events = [
        json.loads(line)
        for journal in evidence.glob("execute-gw*.jsonl")
        for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    assert sorted(
        event["node"] for event in events if event["kind"] == "wrapper_restored"
    ) == sorted(nodes)
    calls = [event for event in events if event["kind"] == "phase_end" and event["phase"] == "call"]
    assert len(calls) == 3
    assert sorted(event["outcome"] for event in calls) == ["failed", "passed", "passed"]
    assert len([event for event in events if event["kind"] == "phase_end"]) == 9
    failures = "\n".join(
        path.read_text(encoding="utf-8") for path in evidence.glob("*failure*.json")
    )
    assert "forwarded error" in failures
    assert "original cause" in failures
