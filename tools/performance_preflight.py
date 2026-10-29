"""Invocation-local proof reuse, fresh scans and explicit admission transactions.

Default scans read every byte and ownership afresh. An explicit verify_live
transaction may lend one complete CI60 result between fresh start/end admissions;
a reverted transient mutation inside that boundary may be unobserved. Transactions
never cross invocations or independent preflight/postflight history phases.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path, PosixPath, PurePath
from types import BuiltinFunctionType, FunctionType
from typing import Any, cast

# Bound retained raw payload independently of the complete source/input corpus.
_DIGEST_LIMIT = 512 * 1024 * 1024
_GIT_POINTER_LIMIT = 64 * 1024

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
            transaction = _ADMISSION_TRANSACTION.get() or _ADMISSION_GUARD.get()
            if transaction is not None and transaction.storage is digests:
                transaction.revoke()
                _ADMISSION_TRANSACTION.set(None)
                _ADMISSION_GUARD.set(None)
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
        self.computation_only = False
        self.dependencies: tuple[object, ...] = ()

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
        if self.computation_only and self.dependencies != _ci60_computation_bindings(
            self.validators
        ):
            raise ValueError("CI60 computation dependency changed.")

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
    *,
    computation_only: bool = False,
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
    state.computation_only = computation_only
    if computation_only:
        state.dependencies = _ci60_computation_bindings(validators)
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
    if state.computation_only:
        state.revoke(digests)
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
    if digests is not None and state is not None and state.computation_only:
        if repository is None:
            state.revoke(digests)
        else:
            state.check(repository)
            from tools.performance_history_snapshot import proof_identity

            if identity is not None or proof_identity(repository) is not None:
                state.revoke(digests)
        if (
            digests.active
            and state.capturing
            and not state.revoked
            and validator in state.validators
        ):
            digests.admission(validator, operands, state.bootstrap_identity, dependencies)
        else:
            validator(operands, () if identity is None else identity)
        return
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


class _AdmissionTransaction:
    """Private complete CI60 result for one explicitly bounded verification."""

    def __init__(
        self,
        root: Path,
        storage: _Digests,
        phase: tuple[str, ...],
        fresh: Callable[[Path], dict[str, bytes]],
        bindings: Callable[[], tuple[object, ...]],
    ) -> None:
        self.root = root
        self.storage = storage
        self.phase = phase
        self.fresh = fresh
        self.bindings = bindings
        self.dependencies = bindings()
        self.owner = (os.getpid(), threading.get_ident())
        self.repository = self.repository_identity(root)
        self.active = True
        self.result: dict[str, bytes] = {}
        self.charge = 0

    @staticmethod
    def repository_identity(root: Path) -> tuple[object, ...]:
        if root.absolute() != root.resolve(strict=True):
            raise ValueError("Admission transaction requires a physical repository.")
        result: list[object] = [root.as_posix()]
        for path in (root, root / ".git"):
            value = path.lstat()
            if path.is_symlink() or path.is_junction():
                raise ValueError("Admission transaction metadata became aliased.")
            result.extend(
                (path.resolve(strict=True).as_posix(), value.st_dev, value.st_ino, value.st_mode)
            )
            if path != root and stat.S_ISREG(value.st_mode):
                if value.st_size > _GIT_POINTER_LIMIT:
                    raise ValueError("Admission transaction metadata pointer became oversized.")
                pointer = tuple(
                    _source_members(
                        root, [".git"], observe_ancestors=True, read_limit=_GIT_POINTER_LIMIT
                    )
                )
                if (
                    type(pointer) is not tuple
                    or len(pointer) != 1
                    or len(pointer[0]) != 3
                    or pointer[0][0] != ".git"
                    or type(pointer[0][1]) is not int
                    or type(pointer[0][2]) is not bytes
                    or len(pointer[0][2]) > _GIT_POINTER_LIMIT
                ):
                    raise ValueError("Admission transaction metadata pointer observation changed.")
                result.append(pointer)
        result.append(
            tuple(
                sorted(
                    (name, value)
                    for name, value in os.environ.items()
                    if name.startswith(("GIT_", "LC_"))
                    or name in {"PATH", "HOME", "XDG_CONFIG_HOME", "LANG", "SYSTEMROOT"}
                )
            )
        )
        return tuple(result)

    def check(self, root: Path, *, closing: bool = False) -> None:
        from tools.performance_history_snapshot import proof_identity

        if (
            self.active == closing
            or self.owner != (os.getpid(), threading.get_ident())
            or not self.storage.active
            or self.storage.owner != self.owner
            or _DIGESTS.get() is not self.storage
            or root != self.root
            or self.repository_identity(root) != self.repository
            or proof_identity(root) != self.phase
            or self.bindings() != self.dependencies
        ):
            raise ValueError("Admission transaction identity or dependencies changed.")

    def retain(self, values: dict[str, bytes]) -> bool:
        if type(values) is not dict or any(
            type(name) is not str or type(raw) is not bytes for name, raw in values.items()
        ):
            raise ValueError("Admission transaction requires an immutable byte result.")
        # Charge copied keys/mapping and every retained payload conservatively,
        # including bytes already retained by another independent pure proof.
        required = (
            sys.getsizeof(self)
            + sys.getsizeof(values)
            + sum(sys.getsizeof(name) + sys.getsizeof(raw) for name, raw in values.items())
        )
        required += _transaction_payload_size((self.repository, self.phase, self.dependencies))
        for key, (raw, _) in tuple(self.storage.entries.items()):
            if required <= self.storage.limit - self.storage.retained:
                break
            self.storage.retained -= len(raw)
            del self.storage.entries[key]
        if required > self.storage.limit - self.storage.retained:
            return False
        self.result = dict(values)
        self.charge = required
        self.storage.retained += required
        return True

    def revoke(self) -> None:
        self.active = False
        self.result.clear()
        self.repository = ()
        self.phase = ()
        self.dependencies = ()
        self.storage.retained -= self.charge
        self.charge = 0


def _transaction_payload_size(value: object) -> int:
    """Charge the immutable tuple/string/byte data owned by this finite lease."""
    if isinstance(value, tuple):
        return sys.getsizeof(value) + sum(_transaction_payload_size(item) for item in value)
    if isinstance(value, (str, bytes)):
        return sys.getsizeof(value)
    return 0


_ADMISSION_TRANSACTION: ContextVar[_AdmissionTransaction | None] = ContextVar(
    "admission_transaction", default=None
)
_ADMISSION_GUARD: ContextVar[_AdmissionTransaction | None] = ContextVar(
    "admission_transaction_guard", default=None
)


def grouped_admission(
    root: Path,
    fresh: Callable[[Path], dict[str, bytes]],
) -> dict[str, bytes]:
    """Default calls remain fresh; only a live explicit transaction may lend bytes."""
    state = _ADMISSION_TRANSACTION.get()
    if state is None:
        if _ADMISSION_GUARD.get() is not None:
            raise ValueError("Admission transaction boundary acquisition cannot borrow.")
        return fresh(root)
    state.check(root)
    if fresh is not state.fresh:
        raise ValueError("Admission transaction entry point changed.")
    return dict(state.result)


@contextmanager
def ci60_transaction(
    root: Path,
    fresh: Callable[[Path], dict[str, bytes]],
    bindings: Callable[[], tuple[object, ...]],
) -> Iterator[None]:
    """Fresh complete start/end checks bound reuse to one verify_live body.

    A reverted transient mutation wholly inside this boundary may be unobserved.
    Insufficient capacity publishes no transaction: the original fully fresh
    nested calls remain authoritative, without a grouped equality guarantee.
    """
    from tools.performance_history_snapshot import proof_identity

    if _ADMISSION_TRANSACTION.get() is not None or _ADMISSION_GUARD.get() is not None:
        raise ValueError("Nested admission transactions are not admitted.")
    storage = _DIGESTS.get()
    if storage is None or not storage.active:
        yield
        return
    if storage.owner != (os.getpid(), threading.get_ident()):
        raise ValueError("Admission transaction invocation identity changed.")
    phase = proof_identity(root)
    handoff = storage.ci60_handoff
    if handoff is not None and handoff.computation_only:
        if phase is not None:
            handoff.revoke(storage)
        yield
        return
    if phase is None:
        yield
        return
    metadata = (root / ".git").lstat()
    if (
        (root / ".git").is_symlink()
        or (root / ".git").is_junction()
        or not (
            stat.S_ISDIR(metadata.st_mode)
            or (
                stat.S_ISREG(metadata.st_mode)
                and metadata.st_nlink == 1
                and metadata.st_size <= _GIT_POINTER_LIMIT
            )
        )
    ):
        yield
        return
    state = _AdmissionTransaction(root, storage, phase, fresh, bindings)
    cleanup_state: _AdmissionTransaction | None = state
    token = None
    guard_token = _ADMISSION_GUARD.set(state)
    guard_active = True
    try:
        values = fresh(root)
        state.check(root)
        if not state.retain(values):
            del values
            state.revoke()
            cleanup_state = None
            del state
            _ADMISSION_GUARD.reset(guard_token)
            guard_active = False
            yield
            return
        del values
        token = _ADMISSION_TRANSACTION.set(state)
        try:
            yield
        finally:
            # Disable dispatch before complete end acquisition. On a body error,
            # a passing end preserves that exact exception; a failed end retains
            # it as Python's explicit exception context rather than swallowing it.
            state.check(root)
            state.active = False
            previous_token, token = token, None
            _ADMISSION_TRANSACTION.reset(previous_token)
            observed = fresh(root)
            state.check(root, closing=True)
            if observed != state.result:
                raise ValueError("Admission transaction complete result changed.")
    finally:
        if cleanup_state is not None:
            cleanup_state.revoke()
        try:
            if token is not None:
                _ADMISSION_TRANSACTION.reset(token)
        finally:
            if guard_active:
                _ADMISSION_GUARD.reset(guard_token)


def _admission_binding(value: object) -> object:
    """Snapshot definitions/defaults of the finite declared binding objects."""
    if isinstance(value, FunctionType):
        defaults = value.__defaults__ or ()
        keywords = tuple(sorted((value.__kwdefaults__ or {}).items()))
        if any(
            type(item) not in (type(None), bool, int, float, str, bytes)
            for item in (*defaults, *(item for _, item in keywords))
        ):
            raise ValueError("Admission transaction function defaults changed.")
        return value, value.__code__, defaults, keywords
    if isinstance(value, tuple):
        return tuple(_admission_binding(item) for item in value)
    return value


def ci60_repository_identity(root: Path) -> tuple[object, ...]:
    """Fresh repository boundary using the existing transaction identity checks."""
    return _AdmissionTransaction.repository_identity(root)


def ci60_admission_bindings() -> tuple[object, ...]:
    """Finite bindings used by the complete admission path, not mutable results."""
    import ast

    from tools import performance_ci60_qualification as q
    from tools import performance_ci69_members as ci69
    from tools import performance_history_snapshot as history
    from tools import performance_policy as policy
    from tools import performance_preflight_successor as successor

    q_namespace = vars(q)
    ci69_namespace = vars(ci69)
    policy_namespace = vars(policy)
    if (
        not {"ci69", "ast", "json", "hashlib"} <= q_namespace.keys()
        or not {"ast", "json", "hashlib"} <= ci69_namespace.keys()
        or not {"ast", "hashlib"} <= policy_namespace.keys()
        or q_namespace["ci69"] is not ci69
        or q_namespace["ast"] is not ast
        or q_namespace["json"] is not json
        or q_namespace["hashlib"] is not hashlib
        or ci69_namespace["ast"] is not ast
        or ci69_namespace["json"] is not json
        or ci69_namespace["hashlib"] is not hashlib
        or policy_namespace["ast"] is not ast
        or policy_namespace["hashlib"] is not hashlib
    ):
        raise ValueError("Admission transaction pure module alias changed.")
    owner = policy.owner_hashes
    if not isinstance(owner, FunctionType) or "__wrapped__" not in vars(owner):
        raise ValueError("Admission transaction owner dependency changed.")
    functions = (
        *(
            getattr(q, name)
            for name in (
                "fresh_admission",
                "_derivation_source",
                "_transaction_absence",
                "_current_derivation_transition",
                "_admitted_derivation",
                "_prelude_transition",
                "_derivation_transition",
                "_preceding_self",
                "_prelude_preimage",
                "digest",
                "git",
                "history",
            )
        ),
        ci69.validate_cutover,
        ci69.expected_observed,
        ci69.retirement_rows,
        ci69.prelude_members,
        ci69.retirement_absence,
        ci69.retired_test_source,
        ci69.current_source_projection,
        owner,
        vars(owner)["__wrapped__"],
        policy.digest,
        history.proof_identity,
        history.historical,
        history.eligible_blobs,
        *(getattr(history, name) for name in ("_oid", "_path")),
        history.Snapshot.blobs,
        *(getattr(successor, name) for name in ("read_frozen_blobs", "_blobs", "_git")),
        admission_proof,
        source_members,
        _source_members,
        _member_plan,
        _literal_member_plan,
        _posix_path_dependencies,
        _same_read,
        _same_file,
        _Digests.admission,
        _Digests.member_plan,
        _path_plan_size,
        _Ci60AdmissionHandoff.check,
        _Ci60AdmissionHandoff._repository,
    )
    if any(not isinstance(function, FunctionType) for function in functions):
        raise ValueError("Admission transaction function dependency changed.")
    selectors = (
        q.BASE,
        q.FREEZE,
        q.SELF,
        q.NAMESPACE,
        q.ASSESSMENT,
        q.MAP,
        q.CONTROLS,
        q.DERIVATION_BASE,
        q.DERIVATION_FREEZE,
        q.DERIVATION_NAMESPACE,
        q.DERIVATION_MEMBERS,
        q.DERIVATION_CONTROLS,
        q.DERIVATION_INPUTS,
        q.PRELUDE_BASE,
        q.PRELUDE_FREEZE,
        q.PRELUDE_NAMESPACE,
        q.PRELUDE_MEMBERS,
        q.PRELUDE_CONTROLS,
        q.PRELUDE_NEW,
        q.PRELUDE_INPUTS,
        q.TRANSACTION_TEST,
        q.TRANSACTION_SHARDS,
        q.PRELUDE_OBSERVED,
        ci69.CONTROL_MEMBERS,
        ci69.INPUT_ADDITIONS,
        ci69.OBSERVED_ADDITIONS,
        ci69.CUTOVER_PATH,
        ci69.CUTOVER_NEW,
        ci69.CUTOVER_ADDED_INPUTS,
        ci69.RUNTIME_SUCCESSORS,
        ci69.RETIRED_TESTS,
        ci69.RETIREMENT_NAMESPACE,
    )
    if any(
        type(value) not in (str, type(None), frozenset)
        or (type(value) is frozenset and any(type(name) is not str for name in value))
        for value in selectors
    ):
        raise ValueError("Admission transaction selector dependency changed.")
    objects = (
        *functions,
        *selectors,
        _GIT_POINTER_LIMIT,
        ci60_admission_bindings,
        _admission_binding,
        _transaction_payload_size,
        _DIGESTS,
        _OWNERS,
        _ADMISSION_GUARD,
        _POSIX_PATH_DEPENDENCIES,
        json.loads,
        json.dumps,
        hashlib.sha256,
        hashlib.sha1,
        ast.parse,
        ast.dump,
        ast.iter_fields,
        ast.walk,
        ast.iter_child_nodes,
        ast.AST,
        ast.Call,
        ast.Attribute,
        ast.iter_fields,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Module,
        os.getpid,
        threading.get_ident,
        os.lstat,
        os.fstat,
        os.fspath,
        os.path.isjunction,
        stat.S_ISDIR,
        stat.S_ISREG,
        os.name,
        Path,
        PosixPath,
        PurePath,
        Path.resolve,
        Path.absolute,
        Path.lstat,
        Path.open,
        Path.as_posix,
        Path.is_absolute,
        Path.is_relative_to,
        Path.parts,
        io.open,
        subprocess.check_output,
        _posix_path_dependencies(),
    )
    return tuple(_admission_binding(value) for value in objects)


def _ci60_computation_bindings(
    validators: tuple[AdmissionValidator, AdmissionValidator],
) -> tuple[object, ...]:
    """Only the audited pure closure graph may enter computation-only reuse."""
    import ast

    from tools import performance_ci60_qualification as q
    from tools import performance_ci69_members as ci69
    from tools import performance_policy as policy

    selected = tuple(
        getattr(q, name) for name in ("_current_derivation_transition", "_admitted_derivation")
    )
    if validators != selected:
        raise ValueError("CI60 computation validators changed; exact two pure validators required.")
    owner = policy.owner_hashes
    raw_owner = vars(owner).get("__wrapped__") if isinstance(owner, FunctionType) else None
    pure = (
        *(
            getattr(q, name)
            for name in (
                "_current_derivation_transition",
                "_prelude_transition",
                "_derivation_transition",
                "_admitted_derivation",
                "digest",
            )
        ),
        ci69.validate_cutover,
        ci69.expected_observed,
        ci69.retirement_rows,
        ci69.prelude_members,
        policy.digest,
        raw_owner,
    )
    if any(not isinstance(function, FunctionType) or function.__closure__ for function in pure):
        raise ValueError("CI60 computation pure closure changed.")
    dependencies = (
        json.loads,
        json.dumps,
        hashlib.sha256,
        hashlib.sha1,
        ast.parse,
        ast.dump,
        ast.iter_fields,
        ast.walk,
        ast.iter_child_nodes,
    )
    if any(
        not isinstance(value, (FunctionType, BuiltinFunctionType))
        or (isinstance(value, FunctionType) and value.__closure__)
        for value in dependencies
    ):
        raise ValueError("CI60 computation dependency closure changed.")
    closure = owner.__closure__ if isinstance(owner, FunctionType) else None
    if (
        not isinstance(owner, FunctionType)
        or owner.__code__.co_freevars != ("function",)
        or closure is None
        or len(closure) != 1
    ):
        raise ValueError("CI60 computation owner closure changed.")
    try:
        captured = closure[0].cell_contents
    except ValueError as error:
        raise ValueError("CI60 computation owner closure became empty.") from error
    if captured is not raw_owner:
        raise ValueError("CI60 computation owner closure changed.")
    return (
        *ci60_admission_bindings(),
        _admission_binding(_ci60_computation_bindings),
        _admission_binding(ci60_computation),
        _admission_binding(q.admission_validators),
        captured,
    )


def ci60_computation[T](root: Path, acquire: Callable[[], T]) -> T:
    """One test-local CPU scope; every live admission remains fully fresh."""
    from tools import performance_ci60_qualification as q
    from tools.performance_history_snapshot import proof_identity

    if (
        _DIGESTS.get() is not None
        or proof_identity(root) is not None
        or not (root / q.NAMESPACE).is_dir()
    ):
        return acquire()

    @invocation
    def compute() -> T:
        owners = _OWNERS.set(None)
        proofs = _PROOFS.set(None)
        try:
            with ci60_bootstrap_admission(
                root, q.admission_validators(), acquire, computation_only=True
            ) as result:
                return result
        finally:
            _PROOFS.reset(proofs)
            _OWNERS.reset(owners)

    return compute()


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
    root: Path, names: list[str], *, observe_ancestors: bool, read_limit: int | None = None
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
            if read_limit is None:
                raw = stream.read()
            else:
                if type(read_limit) is not int or read_limit < 0:
                    raise ValueError("Owned read limit must be a nonnegative integer.")
                raw = stream.read(read_limit + 1)
                if len(raw) > read_limit:
                    raise ValueError("Admission transaction metadata pointer exceeded read limit.")
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
