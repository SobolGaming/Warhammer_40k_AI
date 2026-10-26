"""Invocation-local pure proof reuse and fresh, owned source scans.

No filesystem or Git result is cached. Each scan reads every byte again and checks
ownership afresh. Pure hashes may reuse identical complete bytes within one bounded
invocation; only checked ancestors within the current scan share ownership checks.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path, PosixPath, PurePath
from typing import Any, cast

# Bound retained raw payload independently of the complete source/input corpus.
_DIGEST_LIMIT = 512 * 1024 * 1024

# Complete immutable operands for the one CI60 admission proof.
AdmissionOperands = tuple[tuple[str, int, bytes], ...]
AdmissionValidator = Callable[[AdmissionOperands, tuple[str, ...]], None]


_PathPlan = tuple[tuple[str, ...], str]
_PathKey = tuple[type[Path], str, str, tuple[object, ...]]


def _posix_path_dependencies() -> tuple[object, ...]:
    """Only the pure constructor/parser operations skipped by an owned plan."""
    parser = cast(Any, PosixPath).parser
    methods = (
        "__new__",
        "__init__",
        "is_absolute",
        "drive",
        "root",
        "parts",
        "_raw_path",
        "_tail",
        "__str__",
        "as_posix",
        "_parse_path",
        "_format_parsed_parts",
    )
    return (
        Path,
        PosixPath,
        PurePath,
        *(
            getattr(value, "__func__", value)
            for name in methods
            for value in (getattr(PosixPath, name),)
        ),
        parser,
        parser.sep,
        parser.altsep,
        parser.splitroot,
        parser.splitdrive,
        parser.join,
        os.fspath,
        os.name,
    )


_POSIX_PATH_DEPENDENCIES = _posix_path_dependencies()


def _literal_member_plan(root_name: str, name: str) -> _PathPlan:
    relative = Path(name)
    if (
        relative.is_absolute()
        or relative.drive
        or relative.as_posix() != name
        or ".." in relative.parts
    ):
        raise ValueError("Noncanonical D07 member: " + name)
    parents = []
    path = root_name
    for component in ("", *relative.parts[:-1]):
        if component:
            path = path.rstrip("/") + "/" + component
        parents.append(path)
    return tuple(parents), root_name.rstrip("/") + "/" + name


def _path_plan_size(key: _PathKey, plan: _PathPlan) -> int:
    # Strings/tuples are the only newly retained objects. Count shared strings
    # conservatively more than once; existing global classes/callables are not copied.
    return (
        sys.getsizeof(key)
        + sys.getsizeof(key[1])
        + sys.getsizeof(key[2])
        + sys.getsizeof(key[3])
        + sys.getsizeof(plan)
        + sys.getsizeof(plan[0])
        + sum(sys.getsizeof(value) for value in plan[0])
        + sys.getsizeof(plan[1])
    )


class _Digests:
    def __init__(self, limit: int = _DIGEST_LIMIT) -> None:
        self.limit = limit
        self.retained = 0
        self.entries: dict[tuple[Callable[..., Any], str], tuple[bytes, str]] = {}
        self.active = True
        self.path_plans: dict[_PathKey, _PathPlan] | None = None
        self.path_plan_charge = 0
        self.owner = (os.getpid(), threading.get_ident())
        self.ci60_handoff: _Ci60AdmissionHandoff | None = None
        self.admissions: dict[
            tuple[AdmissionValidator, tuple[str, ...], tuple[Callable[..., Any], ...]],
            AdmissionOperands,
        ] = {}

    def admission(
        self,
        validator: AdmissionValidator,
        operands: AdmissionOperands,
        identity: tuple[str, ...],
        dependencies: tuple[Callable[..., Any], ...],
    ) -> None:
        key = validator, identity, dependencies
        previous = self.admissions.get(key) if self.active else None
        if previous is not None and previous == operands:
            # Adopt equal active-snapshot byte objects after the complete comparison.
            self.admissions[key] = operands
            return
        if previous is not None:
            self.retained -= sum(len(raw) for _, _, raw in previous)
            del self.admissions[key]
        validator(operands, identity)
        required = sum(len(raw) for _, _, raw in operands)
        if self.active and required <= self.limit - self.retained:
            self.admissions[key] = operands
            self.retained += required

    def member_plan(self, root: Path, root_name: str, name: str) -> _PathPlan:
        key = type(root), root.as_posix(), name, _POSIX_PATH_DEPENDENCIES
        if self.path_plans is not None and key in self.path_plans:
            return self.path_plans[key]
        plan = _literal_member_plan(root_name, name)
        prospective = {} if self.path_plans is None else dict(self.path_plans)
        prospective[key] = plan
        old_dictionary = 0 if self.path_plans is None else sys.getsizeof(self.path_plans)
        required = _path_plan_size(key, plan) + sys.getsizeof(prospective) - old_dictionary
        if required <= self.limit - self.retained:
            self.path_plans = prospective
            self.path_plan_charge += required
            self.retained += required
        return plan

    def digest(self, path: str, raw: bytes) -> str:
        function = hashlib.sha256
        key = (function, path)
        previous = self.entries.get(key)
        if previous is not None and previous[0] == raw:
            return previous[1]
        result = function(raw).hexdigest()
        if previous is not None:
            self.retained -= len(previous[0])
            del self.entries[key]
        if len(raw) <= self.limit - self.retained:
            self.entries[key] = (raw, result)
            self.retained += len(raw)
        return result


_DIGESTS: ContextVar[_Digests | None] = ContextVar("digests", default=None)


def _source_digest(path: str, raw: bytes) -> str:
    digests = _DIGESTS.get()
    return hashlib.sha256(raw).hexdigest() if digests is None else digests.digest(path, raw)


_PROOFS: ContextVar[set[tuple[Callable[..., None], bytes, bytes, str]] | None] = ContextVar(
    "proofs", default=None
)

_OWNERS: ContextVar[
    dict[tuple[Callable[..., dict[str, str]], str, bytes | None], dict[str, str]] | None
] = ContextVar("owners", default=None)


def invocation[F: Callable[..., Any]](function: F) -> F:
    """Each validation, including the independent post-smoke call, starts empty."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = _PROOFS.set(set())
        owners_token = _OWNERS.set({})
        digests = _Digests()
        digests_token = _DIGESTS.set(digests)
        try:
            return function(*args, **kwargs)
        finally:
            digests.active = False
            if digests.ci60_handoff is not None:
                digests.ci60_handoff.revoke(digests)
                digests.ci60_handoff = None
            digests.admissions.clear()
            digests.entries.clear()
            digests.path_plans = None
            digests.path_plan_charge = 0
            digests.retained = 0
            _DIGESTS.reset(digests_token)
            _OWNERS.reset(owners_token)
            _PROOFS.reset(token)

    return cast(F, wrapped)


class _Ci60AdmissionHandoff:
    """Single-use ownership for the two audited CI60 pure proofs."""

    def __init__(
        self, root: Path, validators: tuple[AdmissionValidator, AdmissionValidator]
    ) -> None:
        self.root = root
        self.repository = self._repository(root)
        self.owner = (os.getpid(), threading.get_ident())
        self.validators = validators
        self.bootstrap_identity = ("ci60-bootstrap", *self.repository, str(id(self)))
        self.capturing = False
        self.used = False
        self.revoked = False
        self.phase_identity: tuple[str, ...] | None = None

    @staticmethod
    def _repository(root: Path) -> tuple[str, ...]:
        if root.absolute() != root.resolve(strict=True):
            raise ValueError("CI60 admission handoff requires a physical repository.")
        metadata = root.stat()
        return root.as_posix(), str(metadata.st_dev), str(metadata.st_ino)

    def check(self, root: Path) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise ValueError("CI60 admission handoff belongs to another owner.")
        if root != self.root or self._repository(root) != self.repository:
            raise ValueError("CI60 admission handoff belongs to another repository.")

    def discard(self, digests: _Digests, identity: tuple[str, ...]) -> None:
        for key, operands in tuple(digests.admissions.items()):
            if key[0] in self.validators and key[1] == identity:
                digests.retained -= sum(len(raw) for _, _, raw in operands)
                del digests.admissions[key]

    def revoke(self, digests: _Digests) -> None:
        self.capturing = False
        self.revoked = True
        self.discard(digests, self.bootstrap_identity)
        if self.phase_identity is not None:
            self.discard(digests, self.phase_identity)


@contextmanager
def ci60_bootstrap_admission[T](
    root: Path,
    validators: tuple[AdmissionValidator, AdmissionValidator],
    acquire: Callable[[], T],
) -> Iterator[T]:
    """Keep bootstrap proofs private through acquisition and revoke on every exit."""
    digests = _DIGESTS.get()
    if digests is None or not digests.active:
        yield acquire()
        return
    if digests.owner != (os.getpid(), threading.get_ident()):
        raise ValueError("CI60 admission invocation belongs to another owner.")
    if digests.ci60_handoff is not None or len(set(validators)) != 2:
        raise ValueError("CI60 admission requires one bootstrap and two validators.")
    state = _Ci60AdmissionHandoff(root, validators)
    digests.ci60_handoff = state
    try:
        state.capturing = True
        try:
            result = acquire()
        finally:
            state.capturing = False
        yield result
    finally:
        state.revoke(digests)
        digests.ci60_handoff = None


@contextmanager
def ci60_phase_admission(root: Path, identity: tuple[str, ...] | None) -> Iterator[None]:
    """Promote only the pending bootstrap into its first authenticated phase."""
    digests = _DIGESTS.get()
    state = None if digests is None else digests.ci60_handoff
    if digests is None or not digests.active or state is None:
        yield
        return
    state.check(root)
    from tools.performance_history_snapshot import proof_identity

    if identity is None or identity != proof_identity(root):
        raise ValueError("CI60 admission promotion requires its authenticated history phase.")
    if state.used or state.revoked:
        yield
        return
    state.used = True
    state.phase_identity = identity
    try:
        for key, operands in tuple(digests.admissions.items()):
            if key[0] in state.validators and key[1] == state.bootstrap_identity:
                promoted = key[0], identity, key[2]
                if promoted in digests.admissions:
                    raise ValueError("CI60 admission phase already has a proof.")
                del digests.admissions[key]
                digests.admissions[promoted] = operands
        yield
    finally:
        state.revoke(digests)


def admission_proof(
    validator: AdmissionValidator,
    operands: AdmissionOperands,
    identity: tuple[str, ...] | None,
    dependencies: tuple[Callable[..., Any], ...],
    *,
    repository: Path | None = None,
) -> None:
    """Reuse a complete pure proof only in its phase or explicit CI60 bootstrap."""
    digests = _DIGESTS.get()
    state = None if digests is None else digests.ci60_handoff
    if (
        digests is not None
        and digests.active
        and state is not None
        and not state.revoked
        and identity is not None
        and identity == state.phase_identity
        and validator in state.validators
        and repository is not None
    ):
        state.check(repository)
    if (
        digests is not None
        and digests.active
        and identity is None
        and state is not None
        and state.capturing
        and not state.revoked
        and validator in state.validators
        and repository is not None
    ):
        state.check(repository)
        digests.admission(validator, operands, state.bootstrap_identity, dependencies)
        return
    if digests is None or identity is None or not digests.active:
        validator(operands, () if identity is None else identity)
    else:
        digests.admission(validator, operands, identity, dependencies)


def recipe_proof[F: Callable[..., None]](function: F) -> F:
    """Reuse a successful pure whole-AST comparison only for identical inputs."""

    @wraps(function)
    def wrapped(before: bytes, current: bytes, recipe: dict[str, Any]) -> None:
        proofs = _PROOFS.get()
        key = (function, before, current, json.dumps(recipe, sort_keys=True, separators=(",", ":")))
        if proofs is not None and key in proofs:
            return
        function(before, current, recipe)
        if proofs is not None:
            proofs.add(key)

    return cast(F, wrapped)


def owner_proof[F: Callable[..., dict[str, str]]](function: F) -> F:
    """Memoize pure AST hashes by complete bytes; callers receive defensive copies."""

    @wraps(function)
    def wrapped(path: str, content: bytes | None) -> dict[str, str]:
        owners = _OWNERS.get()
        key = (function, path, content)
        if owners is not None and key in owners:
            return dict(owners[key])
        result = function(path, content)
        if owners is not None:
            owners[key] = dict(result)
        return result

    return cast(F, wrapped)


def discovered_sources(root: Path) -> set[str]:
    """Enumerate the same ignored-source corpus without per-member Path bookkeeping."""
    result: set[str] = set()
    for prefix, pattern in (
        ("src", "*"),
        ("tests", "*.py"),
        ("tools", "*.py"),
        ("scripts", "*.py"),
        ("contracts", "*"),
        ("conformance/typescript/src", "*.ts"),
    ):
        start = root / prefix
        if not start.is_dir():
            continue
        pending = [(str(start), prefix)]
        while pending:
            directory, relative = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    name = relative + "/" + entry.name
                    if entry.is_dir(follow_symlinks=False):
                        if os.path.isjunction(entry.path):
                            raise ValueError("Aliased cumulative source directory.")
                        pending.append((entry.path, name))
                    if fnmatch.fnmatch(entry.name, pattern) and (
                        entry.is_file() or entry.is_symlink()
                    ):
                        result.add(name)
    return result


def _member_plan(root: Path, root_name: str, name: str, *, owned: bool) -> _PathPlan:
    storage = _DIGESTS.get()
    if (
        owned
        and os.name == "posix"
        and type(root) is PosixPath
        and type(name) is str
        and storage is not None
        and storage.active
        and storage.owner == (os.getpid(), threading.get_ident())
        and _posix_path_dependencies() == _POSIX_PATH_DEPENDENCIES
        and root.is_absolute()
    ):
        return storage.member_plan(root, root_name, name)
    return _literal_member_plan(root_name, name)


def _source_members(
    root: Path, names: list[str], *, observe_ancestors: bool
) -> Iterator[tuple[str, int, bytes]]:
    """Read owned bytes; the CI60 caller also observes ancestors before each member.

    Directory and file identities are checked again after reading. Observed
    renames, links, replacements and concurrent writes fail even if bytes match.
    """
    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased cumulative root.")
    directories: dict[str, os.stat_result] = {}
    root_name = root.as_posix().rstrip("/") or "/"
    root_parts = root.parts
    for name in names:
        parents, member_name = _member_plan(root, root_name, name, owned=observe_ancestors)
        for path in parents:
            if observe_ancestors or path not in directories:
                metadata = os.lstat(path)
                if not stat.S_ISDIR(metadata.st_mode) or os.path.isjunction(path):
                    raise ValueError("Aliased D07 member: " + name)
                previous = directories.get(path)
                if previous is not None and (
                    previous.st_dev,
                    previous.st_ino,
                    previous.st_mode,
                ) != (metadata.st_dev, metadata.st_ino, metadata.st_mode):
                    raise ValueError("Cumulative source directory changed during owned scan.")
                directories[path] = metadata
        path = member_name
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or os.path.isjunction(path):
            raise ValueError("D07 member must be an owned regular file: " + name)
        member = Path(path)
        if observe_ancestors:
            resolved = member.resolve(strict=True)
            contained = (
                resolved.parts[: len(root_parts)] == root_parts
                if os.name == "posix" and root.is_absolute()
                else resolved.is_relative_to(root)
            )
            if not contained:
                raise ValueError("D07 member must be an owned regular file: " + name)
        windows = os.name == "nt"
        with member.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read()
            closed = os.fstat(stream.fileno())
            if windows:
                # Keep ChangeTime observable through the final path query;
                # Windows lstat's creation-time ctime cannot detect this write.
                after = os.lstat(path)
                final = os.fstat(stream.fileno())
                if not _same_file(closed, final):
                    raise ValueError("Cumulative source changed during owned read: " + name)
        if not windows:
            after = os.lstat(path)
        if not _same_read(before, opened, closed, after, windows=windows):
            raise ValueError("Cumulative source changed during owned read: " + name)
        yield name, before.st_mode, raw
    for path, before in directories.items():
        after = os.lstat(path)
        if (before.st_dev, before.st_ino, before.st_mode) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
        ) or os.path.isjunction(path):
            raise ValueError("Cumulative source directory changed during owned scan.")


def source_hashes(root: Path, names: set[str]) -> dict[str, str]:
    """Fresh owned reads with the existing invocation-local digest budget."""
    return {
        name: _source_digest(name, raw)
        for name, _, raw in _source_members(root, sorted(names), observe_ancestors=False)
    }


def source_members(root: Path, names: list[str]) -> AdmissionOperands:
    """Complete ordered bytes with fresh ancestry at every member observation."""
    return tuple(_source_members(root, names, observe_ancestors=True))


def _same_read(
    before: os.stat_result,
    opened: os.stat_result,
    closed: os.stat_result,
    after: os.stat_result,
    *,
    windows: bool,
) -> bool:
    # Windows Python can expose creation time through lstat's ctime and change
    # time through fstat's ctime. Both channels must remain stable independently;
    # compare all other identity/content metadata across the two APIs as well.
    return (
        (not windows or _same_file(before, after))
        and _same_file(before, opened, compare_ctime=not windows)
        and _same_file(opened, closed)
        and _same_file(closed, after, compare_ctime=not windows)
    )


def _same_file(
    before: os.stat_result, after: os.stat_result, *, compare_ctime: bool = True
) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns if compare_ctime else None,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns if compare_ctime else None,
    )
