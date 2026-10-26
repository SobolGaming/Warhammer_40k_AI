"""Complete phase-private history for the reviewed qualification40 protocol."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

Domain = Literal["plain60", "safe60", "plain30"]
_DOMAINS: tuple[Domain, ...] = ("plain60", "safe60", "plain30")
_LIMITS = {"plain60": 60.0, "safe60": 60.0, "plain30": 30.0}
_MAX_OBJECT = 64 * 1024 * 1024
_MAX_RETAINED = 512 * 1024 * 1024
_ACTIVE: ContextVar[Snapshot | None] = ContextVar("historical_phase", default=None)
_WITNESSES: ContextVar[list[dict[str, object]] | None] = ContextVar(
    "history_witnesses", default=None
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _oid(value: str) -> str:
    if len(value) != 40 or set(value) - set("0123456789abcdef"):
        raise ValueError("History requires a full native SHA1 identity.")
    return value


def _path(name: str) -> str:
    if any(p in {"", ".", ".."} for p in name.split("/")) or any(c in name for c in "\\\0\r\n"):
        raise ValueError("History requires a canonical literal member.")
    return name


def _argv(root: Path, domain: Domain, args: tuple[str, ...]) -> list[str]:
    if domain not in _DOMAINS:
        raise ValueError("Unknown history acquisition domain.")
    return [
        "git",
        *(["-c", f"safe.directory={root.as_posix()}"] if domain == "safe60" else []),
        *args,
    ]


def _closed(
    root: Path, domain: Domain, args: tuple[str, ...], *, limit: int, payload: bytes = b""
) -> bytes:
    """Bound the whole exchange, both output streams, EOF and successful termination."""
    command = _argv(root, domain, args)
    deadline = time.monotonic() + _LIMITS[domain]
    child = subprocess.Popen(
        command,
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    assert child.stdin is not None
    assert child.stdout is not None
    assert child.stderr is not None
    streams = (child.stdin, child.stdout, child.stderr)
    result, error = bytearray(), bytearray()
    pending = memoryview(payload)
    successful = False
    open_outputs = {child.stdout.fileno(): result, child.stderr.fileno(): error}
    try:
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
        while open_outputs or not child.stdin.closed:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, _LIMITS[domain])
            if not child.stdin.closed:
                if pending:
                    try:
                        written = os.write(child.stdin.fileno(), pending[:65536])
                    except BlockingIOError:
                        written = 0
                    pending = pending[written:]
                else:
                    child.stdin.close()
            progress = False
            for descriptor, target in list(open_outputs.items()):
                try:
                    block = os.read(descriptor, 65536)
                except BlockingIOError:
                    continue
                progress = True
                if not block:
                    del open_outputs[descriptor]
                    continue
                bound = limit if target is result else 65536
                if len(target) + len(block) > bound:
                    raise ValueError("History subprocess exceeded its declared output bound.")
                target.extend(block)
            if not progress:
                time.sleep(0.001)
        code = child.wait(timeout=max(0.001, deadline - time.monotonic()))
        if code:
            raise subprocess.CalledProcessError(code, command, bytes(result), bytes(error))
        successful = True
        return bytes(result)
    finally:
        orphaned = False
        if os.name == "posix":
            completed = child.poll() is not None
            try:
                os.killpg(child.pid, signal.SIGKILL)
                orphaned = completed
            except ProcessLookupError:
                if child.poll() is None:
                    child.kill()
        elif child.poll() is None:
            child.kill()
        child.wait(timeout=1)
        for stream in streams:
            stream.close()
        if orphaned and successful:
            raise ValueError("History subprocess left a descendant after completion.")


@dataclass(frozen=True, slots=True)
class Member:
    domain: Domain
    commit: str
    path: str
    mode: str
    oid: str
    size: int
    sha256: str
    authorities: tuple[str, ...]


class _Builder:
    """Unpublished native objects; never invokes current admission or snapshot lookup."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.objects: dict[tuple[Domain, str], tuple[str, bytes]] = {}
        self.trees: dict[tuple[Domain, str], dict[str, tuple[str, str]]] = {}
        self.roots: dict[tuple[Domain, str], str] = {}
        self.members: dict[tuple[Domain, str, str], Member] = {}
        self.contents: dict[tuple[Domain, str, str], bytes] = {}
        self.facts: dict[tuple[Domain, tuple[str, ...]], bytes] = {}
        self.authorities: dict[str, str] = {}
        self.retained = 0
        self.declarations: dict[tuple[Domain, str, str], set[tuple[str, str | None]]] = {}

    def objects_for(self, domain: Domain, oids: set[str]) -> None:
        missing = sorted(oid for oid in oids if (domain, _oid(oid)) not in self.objects)
        if not missing:
            return
        payload = "".join(oid + "\n" for oid in missing).encode()
        checked = _closed(
            self.root,
            domain,
            ("cat-file", "--batch-check"),
            limit=len(missing) * 128,
            payload=payload,
        )
        rows = checked.splitlines()
        if len(rows) != len(missing):
            raise ValueError("History object inventory is incomplete.")
        declarations: list[tuple[str, str, int]] = []
        for oid, row in zip(missing, rows, strict=True):
            parts = row.split(b" ")
            if (
                len(parts) != 3
                or parts[0] != oid.encode()
                or parts[1] not in {b"blob", b"tree", b"commit"}
            ):
                raise ValueError("History object identity/type is malformed.")
            encoded_size = parts[2]
            if (
                not encoded_size.isdigit()
                or str(int(encoded_size)).encode() != encoded_size
                or int(encoded_size) > _MAX_OBJECT
            ):
                raise ValueError("History object size is not admitted.")
            declarations.append((oid, parts[1].decode(), int(encoded_size)))
        declared_size = sum(size for _, _, size in declarations)
        if declared_size > _MAX_RETAINED - self.retained:
            raise ValueError("History declared native bytes exceed the phase resource bound.")
        output = _closed(
            self.root,
            domain,
            ("cat-file", "--batch"),
            limit=sum(size + 128 for _, _, size in declarations),
            payload=payload,
        )
        offset = 0
        for oid, kind, size in declarations:
            header = f"{oid} {kind} {size}\n".encode()
            if output[offset : offset + len(header)] != header:
                raise ValueError("History object header changed during acquisition.")
            start = offset + len(header)
            raw = output[start : start + size]
            if len(raw) != size or output[start + size : start + size + 1] != b"\n":
                raise ValueError("History object framing is incomplete.")
            native = hashlib.sha1(
                f"{kind} {size}\0".encode() + raw, usedforsecurity=False
            ).hexdigest()
            if native != oid:
                raise ValueError("History native object content changed.")
            self.objects[domain, oid] = kind, raw
            self.retained += size
            offset = start + size + 1
        if offset != len(output):
            raise ValueError("History object exchange has surplus output.")

    def tree(self, domain: Domain, oid: str) -> dict[str, tuple[str, str]]:
        key = domain, oid
        if key in self.trees:
            return self.trees[key]
        self.objects_for(domain, {oid})
        kind, raw = self.objects[key]
        if kind != "tree":
            raise ValueError("History path parent is not a native tree.")
        rows: dict[str, tuple[str, str]] = {}
        offset = 0
        while offset < len(raw):
            end = raw.find(b"\0", offset)
            header = raw[offset:end].split(b" ", 1)
            if end < 0 or len(header) != 2 or end + 21 > len(raw):
                raise ValueError("History native tree is malformed.")
            mode, encoded = header
            name = encoded.decode()
            _path(name)
            if (
                "/" in name
                or name in rows
                or mode not in {b"40000", b"100644", b"100755", b"120000", b"160000"}
            ):
                raise ValueError("History native tree member is malformed.")
            rows[name] = mode.decode(), raw[end + 1 : end + 21].hex()
            offset = end + 21
        self.trees[key] = rows
        return rows

    def commit(self, domain: Domain, revision: str) -> str:
        key = domain, _oid(revision)
        if key not in self.roots:
            self.objects_for(domain, {revision})
            kind, raw = self.objects[key]
            first = raw.split(b"\n", 1)[0]
            if kind != "commit" or not first.startswith(b"tree "):
                raise ValueError("History selector is not a native commit.")
            self.roots[key] = _oid(first[5:].decode())
        return self.roots[key]

    def bindings(
        self, domain: Domain, revision: str, names: set[str]
    ) -> dict[str, tuple[str, str]]:
        result = {}
        pending = [(self.commit(domain, revision), "", names)]
        while pending:
            self.objects_for(domain, {oid for oid, _, _ in pending})
            following = []
            for oid, prefix, wanted in pending:
                rows = self.tree(domain, oid)
                children: dict[str, set[str]] = {}
                for name in wanted:
                    _path(name)
                    component, separator, tail = name.partition("/")
                    if component not in rows:
                        raise ValueError("History declared member is missing: " + prefix + name)
                    mode, member_oid = rows[component]
                    if separator:
                        if mode != "40000":
                            raise ValueError("History declared parent is not a tree.")
                        children.setdefault(component, set()).add(tail)
                    else:
                        if mode not in {"100644", "100755"}:
                            raise ValueError("History declared member is not a regular blob.")
                        result[prefix + component] = mode, member_oid
                for name, tails in children.items():
                    following.append((rows[name][1], prefix + name + "/", tails))
            pending = following
        if result.keys() != names:
            raise ValueError("History native membership is incomplete.")
        return result

    def add(
        self, domain: Domain, revision: str, pins: Mapping[str, str | None], authority: str
    ) -> dict[str, bytes]:
        if not pins:
            return {}
        for name, pin in pins.items():
            self.declarations.setdefault((domain, revision, name), set()).add((authority, pin))
        bindings = self.bindings(domain, revision, set(pins))
        self.objects_for(domain, {oid for _, oid in bindings.values()})
        result = {}
        for name, pin in pins.items():
            mode, oid = bindings[name]
            kind, raw = self.objects[domain, oid]
            if kind != "blob" or (pin is not None and _sha(raw) != pin):
                raise ValueError("History original member pin changed: " + name)
            key = domain, revision, name
            previous = self.members.get(key)
            authorities = tuple(sorted({authority, *(previous.authorities if previous else ())}))
            self.members[key] = Member(
                domain, revision, name, mode, oid, len(raw), _sha(raw), authorities
            )
            self.contents[key] = raw
            result[name] = raw
        return result

    def fact(self, domain: Domain, args: tuple[str, ...], authority: str) -> bytes:
        if args[0] == "merge-base":
            _oid(args[-1])
            _oid(args[-2])
            limit = 0
        elif args[:2] == ("diff", "--name-only"):
            _oid(args[-1])
            _oid(args[-2])
            limit = 16 * 1024 * 1024
        elif args[:4] == ("--literal-pathspecs", "ls-tree", "-r", "-z"):
            _oid(args[4])
            limit = 4096
        elif args[:3] == ("ls-tree", "-r", "--name-only"):
            _oid(args[3])
            limit = 16 * 1024 * 1024
        else:
            raise ValueError("Undeclared historical proof kind.")
        raw = _closed(self.root, domain, args, limit=limit)
        self.facts[domain, args] = raw
        self.authorities[authority + ":" + _digest([domain, args])] = _sha(raw)
        return raw

    def all_paths(self, domain: Domain, revision: str) -> set[str]:
        pending = [(self.commit(domain, revision), "")]
        paths = set()
        while pending:
            self.objects_for(domain, {oid for oid, _ in pending})
            following = []
            for oid, prefix in pending:
                for name, (mode, child) in self.tree(domain, oid).items():
                    if mode == "40000":
                        following.append((child, prefix + name + "/"))
                    else:
                        paths.add(prefix + name)
            pending = following
        return paths

    def finish(self) -> None:
        """A fresh closed availability/type/size pass precedes publication."""
        for domain in _DOMAINS:
            selected = sorted(oid for d, oid in self.objects if d == domain)
            if not selected:
                continue
            raw = _closed(
                self.root,
                domain,
                ("cat-file", "--batch-check"),
                limit=len(selected) * 128,
                payload="".join(oid + "\n" for oid in selected).encode(),
            )
            expected = b"".join(
                (
                    f"{oid} {self.objects[domain, oid][0]} {len(self.objects[domain, oid][1])}\n"
                ).encode()
                for oid in selected
            )
            if raw != expected:
                raise ValueError("History availability changed during acquisition.")


@dataclass(frozen=True, slots=True)
class _Lease:
    valid: Callable[[], bool]
    revoke: Callable[[], None]


def _new_lease() -> _Lease:
    pid, owner = os.getpid(), threading.get_ident()
    active = True

    def valid() -> bool:
        return active and pid == os.getpid() and owner == threading.get_ident()

    def revoke() -> None:
        nonlocal active
        active = False

    return _Lease(valid, revoke)


@dataclass(frozen=True, slots=True)
class Snapshot:
    root: Path
    _lease: _Lease
    members: Mapping[tuple[Domain, str, str], Member]
    contents: Mapping[tuple[Domain, str, str], bytes]
    facts: Mapping[tuple[Domain, tuple[str, ...]], bytes]
    semantic_digest: str
    phase_id: str
    certificate: str

    def blobs(
        self, root: Path, domain: Domain, revision: str, names: list[str]
    ) -> dict[str, bytes]:
        if not self._lease.valid() or _ACTIVE.get() is not self:
            raise ValueError("History phase capability is inactive or belongs to another owner.")
        if root != self.root or root.absolute() != root.resolve(strict=True):
            raise ValueError("History snapshot belongs to another repository.")
        _oid(revision)
        if not names or len(names) != len(set(names)):
            raise ValueError("History selection must contain unique members.")
        result = {}
        for name in names:
            key = domain, revision, _path(name)
            if key not in self.members:
                raise ValueError("Unknown active history member/domain.")
            result[name] = self.contents[key]
        return result


def proof_identity(root: Path) -> tuple[str, ...] | None:
    """A live owner-scoped phase identity for pure admission derivations."""
    active = _ACTIVE.get()
    if active is None:
        return None
    if not active._lease.valid():
        raise ValueError("History phase capability is inactive or belongs to another owner.")
    if root != active.root or root.absolute() != root.resolve(strict=True):
        raise ValueError("History snapshot belongs to another repository.")
    return root.as_posix(), active.phase_id, active.semantic_digest


def eligible_blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes] | None:
    active = _ACTIVE.get()
    return None if active is None else active.blobs(root, "plain60", revision, names)


def historical(
    root: Path, domain: Domain, args: tuple[str, ...], fresh: Callable[[], bytes]
) -> bytes:
    active = _ACTIVE.get()
    if active is None:
        return fresh()
    if len(args) == 2 and args[0] == "show":
        revision, separator, name = args[1].partition(":")
        if not separator:
            raise ValueError("History show requires a literal full-commit member.")
        return active.blobs(root, domain, revision, [name])[name]
    if not active._lease.valid():
        raise ValueError("History phase capability is inactive or belongs to another owner.")
    if root != active.root or root.absolute() != root.resolve(strict=True):
        raise ValueError("History snapshot belongs to another repository.")
    key = domain, args
    if key not in active.facts:
        raise ValueError("Unknown active history proof/domain.")
    return active.facts[key]


def _identity(
    root: Path, base_ref: str, pr_head: str | None, *, domain_state: bool
) -> dict[str, object]:
    from tools.performance_preflight import source_hashes

    if root.absolute() != root.resolve(strict=True) or root.is_symlink() or root.is_junction():
        raise ValueError("History requires a physical repository root.")
    git_path = shutil.which("git")
    if git_path is None:
        raise ValueError("History Git executable is unavailable.")
    paths = [root, Path(git_path).resolve(strict=True)]
    result: dict[str, object] = {"root": str(root), "pr_head": pr_head, "base_ref": base_ref}
    for label, args in (
        ("head", ("rev-parse", "--verify", "HEAD^{commit}")),
        ("base", ("rev-parse", "--verify", base_ref + "^{commit}")),
        ("git_dir", ("rev-parse", "--absolute-git-dir")),
        ("common_dir", ("rev-parse", "--git-common-dir")),
        ("worktree", ("rev-parse", "--show-toplevel")),
    ):
        value = _closed(root, "safe60", args, limit=8192).decode().strip()
        result[label] = value
        if label in {"git_dir", "common_dir", "worktree"}:
            paths.append((root / value).resolve(strict=True))
    if Path(str(result["worktree"])).resolve(strict=True) != root:
        raise ValueError("History worktree differs from the supplied root.")
    result["physical"] = [(str(path), path.stat().st_dev, path.stat().st_ino) for path in paths]
    result["dependencies"] = source_hashes(root, {"pyproject.toml", "uv.lock"})
    if domain_state:
        result["environment"] = _digest(
            sorted(
                (name, value)
                for name, value in os.environ.items()
                if name.startswith(("GIT_", "LC_"))
                or name in {"PATH", "HOME", "XDG_CONFIG_HOME", "LANG", "SYSTEMROOT"}
            )
        )
        result["configuration"] = {
            domain: _sha(
                _closed(
                    root, domain, ("config", "--null", "--list", "--show-origin"), limit=1024 * 1024
                )
            )
            for domain in _DOMAINS
        }
        result["replacements"] = _sha(
            _closed(
                root,
                "plain60",
                ("for-each-ref", "--format=%(refname) %(objectname)", "refs/replace"),
                limit=1024 * 1024,
            )
        )
    return result


def _unpinned(names: Iterable[str]) -> dict[str, None]:
    return dict.fromkeys(names)


def _catalog(root: Path, base: str) -> _Builder:
    from tools import cumulative_preservation as c
    from tools import performance_category_migration as legacy
    from tools import performance_preflight_successor as p
    from tools import performance_qualification_successor as s
    from tools import quality_runtime_successor as q
    from tools import thousand_sons_perils_preservation as t

    b = _Builder(root)
    pf, sf, tf, qf, cf = (
        p.FREEZE_COMMIT,
        s.FREEZE_COMMIT,
        t.FREEZE_COMMIT,
        q.FREEZE,
        c.SOURCE_COMMIT,
    )
    if any(value is None for value in (pf, sf, tf, qf, cf)):
        raise ValueError("History catalog has an unactivated original owner.")
    pf, sf, tf, qf, cf = cast(tuple[str, str, str, str, str], (pf, sf, tf, qf, cf))
    pbytes = b.add(
        "plain60",
        pf,
        {**p.PINS, **p.ANCHORS, **_unpinned([p.SELF, p.ASSESSMENT])},
        "preflight.freeze",
    )
    b.add("plain60", qf, {**q.PINS, **_unpinned([q.SELF, q.ASSESSMENT])}, "quality.freeze")
    before = q.BEFORE | q.SNAPSHOT_BEFORE
    b.add(
        "plain60",
        q.BASE,
        {n: pin for n, pin in before.items() if n != q.ASSESSMENT},
        "quality.original-preimages",
    )
    b.add("plain30", q.BASE, before, "quality.previous")
    b.fact("plain30", ("merge-base", "--is-ancestor", q.BASE, qf), "quality.ancestry")
    changed = b.fact("plain30", ("diff", "--name-only", q.BASE, qf), "quality.changed")
    if set(changed.decode().splitlines()) != q.PINS.keys() | {q.SELF, q.ASSESSMENT}:
        raise ValueError("History quality catalog differs from its original finite membership.")
    for revision, pins in (
        (p.STATIC_BASE, p.STATIC_BEFORE),
        (p.CI_BASE, p.CI_BEFORE),
        (p.CI_FORMAT_BASE, p.CI_FORMAT_BEFORE),
        (p.CI_COMPAT_BASE, p.CI_COMPAT_BEFORE),
        (p.CI_TRANSPORT_BASE, p.CI_TRANSPORT_BEFORE),
        (p.CI_RUNTIME_BASE, p.CI_RUNTIME_BEFORE),
    ):
        b.add("plain60", revision, pins, "preflight.transition:" + revision)
        b.fact("plain60", ("merge-base", "--is-ancestor", revision, pf), "preflight.ancestry")
    for revision, name in ((p.CI_BASE, p.CI_NEW), (p.CI_RUNTIME_BASE, p.CI_RUNTIME_NEW)):
        if b.fact(
            "plain60",
            ("--literal-pathspecs", "ls-tree", "-r", "-z", revision, "--", name),
            "preflight.absence",
        ):
            raise ValueError("History added path was present in its original base.")
    b.fact("plain60", ("merge-base", "--is-ancestor", p.BASE, pf), "preflight.ancestry")
    changed = b.fact("plain60", ("diff", "--name-only", p.BASE, pf), "preflight.changed")
    if set(changed.decode().splitlines()) != p.PINS.keys() | {p.SELF, p.ASSESSMENT}:
        raise ValueError("History preflight finite membership changed.")
    native_paths = b.all_paths("plain60", p.BASE)
    tree_names = b.fact(
        "plain60", ("ls-tree", "-r", "--name-only", p.BASE), "preflight.complete-tree"
    )
    if set(tree_names.decode().splitlines()) != native_paths:
        raise ValueError("History complete tree differs from native tree objects.")
    b.add(
        "plain60",
        p.BASE,
        _unpinned((p.PINS.keys() & native_paths) | p.ANCHORS.keys() | t.CHANGED | {p.ASSESSMENT}),
        "preflight.predecessors",
    )
    tbytes = b.add("plain60", tf, _unpinned(t.CHANGED), "perils.freeze")
    b.add("plain60", t.BASE, _unpinned({t.STAGE, t.CUMULATIVE, t.TEST}), "perils.predecessors")
    for start, end, authority in (
        (t.BASE, tf, "perils"),
        (s.ACCEPTED, sf, "qualification"),
        (s.PRODUCING_COMMIT, sf, "qualification.producing"),
    ):
        b.fact("plain60", ("merge-base", "--is-ancestor", start, end), authority + ".ancestry")
    if (
        set(
            b.fact("plain60", ("diff", "--name-only", t.BASE, tf), "perils.changed")
            .decode()
            .splitlines()
        )
        != t.CHANGED
    ):
        raise ValueError("History perils finite membership changed.")
    fixed = {s.SELF, s.MAP, p.ASSESSMENT} | {
        s.NAMESPACE + "/" + suffix
        for suffix in (
            "accepted-source.json",
            "changed-members.json",
            "control-transitions.json",
            "producing-inputs.json",
            "added-operations.json",
            "measurement-provenance.json",
            "tool-input-roles-v3.json",
        )
    }
    frozen = b.add("plain60", sf, _unpinned(fixed), "qualification.fixed")
    accepted = json.loads(frozen[s.NAMESPACE + "/accepted-source.json"])
    producing = json.loads(frozen[s.NAMESPACE + "/producing-inputs.json"])
    if _digest(accepted) != s.SOURCE_SHA256 or _digest(producing) != s.PRODUCING_INPUT_DIGEST:
        raise ValueError("History qualification original input authorities changed.")
    declared = json.loads(frozen[s.NAMESPACE + "/changed-members.json"])
    changed_members = (
        b.fact("plain60", ("diff", "--name-only", s.ACCEPTED, sf), "qualification.changed")
        .decode()
        .splitlines()
    )
    if (
        not isinstance(declared, list)
        or len(set(declared)) != len(declared)
        or sorted(changed_members) != declared
    ):
        raise ValueError("History qualification changed-members authority is malformed.")
    frozen.update(b.add("plain60", sf, _unpinned(declared), "qualification.changed-members"))
    rows = json.loads(frozen[s.NAMESPACE + "/control-transitions.json"])
    if len(rows) != 8 or len({r["path"] for r in rows}) != 8:
        raise ValueError("History qualification must retain all eight control rows.")
    b.add(
        "plain60",
        s.ACCEPTED,
        {r["path"]: r["before_sha256"] for r in rows} | {s.MAP: None},
        "qualification.control-transitions",
    )
    for row in rows:
        if _sha(frozen[row["path"]]) != row["after_sha256"]:
            raise ValueError("History qualification transition pin changed.")
        c.assert_recipe(
            b.contents["plain60", s.ACCEPTED, row["path"]], frozen[row["path"]], row["recipe"]
        )
    b.add(
        "plain60",
        s.PRODUCING_COMMIT,
        {
            name: producing[name]
            for name in (s.SELF, s.MAP, "tests/code_quality/test_qualification40_successor.py")
        },
        "qualification.producing-inputs",
    )
    provenance = json.loads(frozen[s.NAMESPACE + "/measurement-provenance.json"])
    roles = json.loads(frozen[s.NAMESPACE + "/tool-input-roles-v3.json"])
    dynamic = {roles["inventories_path"]}
    for row in provenance.values():
        for side in ("base", "head"):
            dynamic.add(row[side]["path"])
            dynamic.update(row[side]["receipt_paths"])
    if not dynamic <= set(declared):
        raise ValueError("History dynamic role escaped its authenticated changed-members.")
    b.add("plain60", sf, _unpinned(dynamic), "qualification.provenance-and-roles")
    registry_name = c.NAMESPACE + "/registry.json"
    registry_raw = b.add("safe60", cf, {registry_name: c.REGISTRY_SHA}, "cumulative.registry")[
        registry_name
    ]
    registry = json.loads(registry_raw)
    if registry["schema"] != c.SCHEMA or registry["accepted_source"] != c.SOURCE_ID:
        raise ValueError("History cumulative registry authority changed.")
    registry_members = b.add(
        "safe60",
        cf,
        {
            c.NAMESPACE + "/" + n: registry["members"][n]
            for n in ("control-transformations.json", "accepted-source.json")
        },
        "cumulative.registry-members",
    )
    integration = registry["integration_members"]
    if not isinstance(integration, list) or len(integration) != len(set(integration)):
        raise ValueError("History cumulative integration declaration is malformed.")
    b.add("plain60", cf, _unpinned(integration), "cumulative.integration-members")
    b.add(
        "safe60", cf, _unpinned(c.CONTROLS | c.SOURCE_ARCHIVES), "cumulative.controls-and-archives"
    )
    transformations = json.loads(registry_members[c.NAMESPACE + "/control-transformations.json"])
    if {r["path"] for r in transformations} != legacy.CONTROLS or len(transformations) != len(
        legacy.CONTROLS
    ):
        raise ValueError("History cumulative original control membership changed.")
    for revision, key in (
        (str(legacy.SOURCE_COMMIT), "legacy_sha256"),
        (c.CONTENT_BASE, "pr587_sha256"),
        (c.ACCEPTED, "accepted_sha256"),
    ):
        stage_pins: dict[str, str | None] = {row["path"]: row[key] for row in transformations}
        if key == "legacy_sha256":
            stage_pins[legacy.SELF] = None
        obtained = b.add(
            "safe60", revision, stage_pins, "cumulative.control-transformations:" + key
        )
        if key == "legacy_sha256":
            raw = obtained[legacy.SELF]
            marker = b"\nSOURCE_COMMIT: str | None = None"
            if raw.count(marker) != 1:
                raise ValueError("History cumulative original activation changed.")
            activated = raw.replace(
                marker, f'\nSOURCE_COMMIT: str | None = "{revision}"'.encode(), 1
            )
            if _sha(activated) != next(r[key] for r in transformations if r["path"] == legacy.SELF):
                raise ValueError("History cumulative activated control pin changed.")
    b.add(
        "safe60",
        base,
        _unpinned(["src/warhammer40k_core/_engine_build_manifest.json"]),
        "runner.base-runtime",
    )
    for label, raw in (
        ("preflight", pbytes[p.SELF]),
        ("perils", tbytes[t.SELF]),
        ("registry", registry_raw),
    ):
        b.authorities[label] = _sha(raw)
    b.authorities["qualification.accepted-source"] = s.SOURCE_SHA256
    b.authorities["qualification.producing-inputs"] = s.PRODUCING_INPUT_DIGEST
    _reconcile(b)
    from tools.performance_ci60_qualification import extend_catalog

    extend_catalog(b)
    return b


def _reconcile(b: _Builder) -> None:
    """Reapply the original finite historical authorities before publication."""
    from tools import cumulative_preservation as c
    from tools import performance_category_migration as legacy
    from tools import performance_preflight_successor as p
    from tools import performance_qualification_successor as s
    from tools import quality_runtime_successor as q
    from tools import thousand_sons_perils_preservation as t

    def payload(domain: Domain, revision: str | None, name: str) -> bytes:
        if revision is None:
            raise ValueError("History authority is not activated.")
        return b.contents[domain, revision, name]

    def record(domain: Domain, revision: str | None, name: str) -> Any:
        return json.loads(payload(domain, revision, name))

    for revision, name, marker in (
        (p.FREEZE_COMMIT, p.SELF, b"\nFREEZE_COMMIT: str | None = None"),
        (s.FREEZE_COMMIT, s.SELF, b"\nFREEZE_COMMIT: str | None = None"),
        (t.FREEZE_COMMIT, t.SELF, b"\nFREEZE_COMMIT: str | None = None"),
        (q.FREEZE, q.SELF, b"\nFREEZE: str | None = None"),
    ):
        if payload("plain60", revision, name).count(marker) != 1:
            raise ValueError("History original freeze activation occurrence changed.")
    if payload("safe60", c.SOURCE_COMMIT, c.SELF).count(b"\nSOURCE_COMMIT: str | None = None") != 1:
        raise ValueError("History cumulative source activation occurrence changed.")
    before = q.BEFORE | q.SNAPSHOT_BEFORE
    transition = record("plain60", q.FREEZE, q.RECORD)
    if (
        q.BEFORE.keys() & q.SNAPSHOT_BEFORE.keys()
        or transition.keys() != {"schema", "base", "changes"}
        or transition["schema"] != "exact-ci-quality-v1"
        or transition["base"] != q.BASE
        or transition["changes"].keys() != before.keys() - {q.ASSESSMENT}
    ):
        raise ValueError("History quality transition authority changed.")
    for name, row in transition["changes"].items():
        current = payload("plain60", q.FREEZE, name)
        if row["after_sha256"] != q.PINS[name]:
            raise ValueError("History quality current pin changed.")
        p._assert_ci_edits(payload("plain60", q.BASE, name), current, row, before[name], False)
    frozen = {
        name: payload("plain60", p.FREEZE_COMMIT, name)
        for name in p.PINS.keys() | p.ANCHORS.keys() | {p.SELF}
    }
    comparison = dict(frozen)
    for base, path, pins, additions in (
        (p.CI_RUNTIME_BASE, p.CI_RUNTIME_RECORD, p.CI_RUNTIME_BEFORE, {p.CI_RUNTIME_NEW}),
        (p.CI_TRANSPORT_BASE, p.CI_TRANSPORT_RECORD, p.CI_TRANSPORT_BEFORE, set()),
        (p.CI_COMPAT_BASE, p.CI_COMPAT_RECORD, p.CI_COMPAT_BEFORE, set()),
        (p.CI_BASE, p.CI_RECORD, p.CI_BEFORE, {p.CI_NEW}),
        (p.CI_FORMAT_BASE, p.CI_FORMAT_RECORD, p.CI_FORMAT_BEFORE, set()),
    ):
        transition = json.loads(frozen[path])
        if (
            transition.keys() != {"schema", "base", "changes"}
            or transition["schema"] != "exact-ci-successor-v1"
            or transition["base"] != base
            or transition["changes"].keys() != pins.keys() | additions
        ):
            raise ValueError("History original CI transition authority changed.")
        for name, row in transition["changes"].items():
            old = None if name in additions else payload("plain60", base, name)
            p._assert_ci_edits(old, comparison[name], row, pins.get(name), name in additions)
        if base in {p.CI_RUNTIME_BASE, p.CI_TRANSPORT_BASE, p.CI_COMPAT_BASE}:
            comparison.update({name: payload("plain60", base, name) for name in pins})
    transition = json.loads(frozen[p.STATIC_RECORD])
    if (
        transition.keys() != {"schema", "base", "changes"}
        or transition["schema"] != "exact-static-successor-v1"
        or transition["base"] != p.STATIC_BASE
        or transition["changes"].keys() != p.STATIC_BEFORE.keys()
    ):
        raise ValueError("History original static transition authority changed.")
    for name in p.STATIC_BEFORE:
        p.assert_static_transition(
            name,
            payload("plain60", p.STATIC_BASE, name),
            comparison[name],
            transition["changes"][name],
        )
    source = record("safe60", c.SOURCE_COMMIT, c.NAMESPACE + "/accepted-source.json")
    if _digest(source) != c.SOURCE_ID:
        raise ValueError("History cumulative accepted source authority changed.")
    transformations = record(
        "safe60", c.SOURCE_COMMIT, c.NAMESPACE + "/control-transformations.json"
    )
    stage_rows = record("plain60", s.FREEZE_COMMIT, s.NAMESPACE + "/control-transitions.json")
    stage_projection = {
        row["path"]: payload("plain60", s.ACCEPTED, row["path"]) for row in stage_rows
    }
    for row in transformations:
        name = row["path"]
        historical = payload("safe60", str(legacy.SOURCE_COMMIT), name)
        if name == legacy.SELF:
            historical = historical.replace(
                b"\nSOURCE_COMMIT: str | None = None",
                f'\nSOURCE_COMMIT: str | None = "{legacy.SOURCE_COMMIT}"'.encode(),
                1,
            )
        baseline = payload("safe60", c.CONTENT_BASE, name)
        accepted = payload("safe60", c.ACCEPTED, name)
        current = (
            stage_projection[name]
            if name in stage_projection
            else payload("safe60", c.SOURCE_COMMIT, name)
        )
        for data, key in (
            (historical, "legacy_sha256"),
            (baseline, "pr587_sha256"),
            (accepted, "accepted_sha256"),
            (current, "current_sha256"),
        ):
            if _sha(data) != row[key]:
                raise ValueError("History original cumulative control pin changed.")
        c.assert_recipe(historical, accepted, row["historical_to_accepted"])
        c.assert_recipe(baseline, accepted, row["baseline_to_accepted"])
        c.assert_recipe(accepted, current, row["accepted_to_integration"])
    provenance = record("plain60", s.FREEZE_COMMIT, s.NAMESPACE + "/measurement-provenance.json")
    measured = record("plain60", s.FREEZE_COMMIT, s.NAMESPACE + "/producing-inputs.json")
    if len(provenance) != 12:
        raise ValueError("History qualification cohort must contain twelve families.")
    for row in provenance.values():
        if row["base_revision"] != c.CONTENT_BASE or row["head_input_digest"] != _digest(measured):
            raise ValueError("History producing cohort authority changed.")
        for side in ("base", "head"):
            arm = row[side]
            data = record("plain60", s.FREEZE_COMMIT, arm["path"])
            if _digest(data) != arm["canonical_sha256"] or arm["completed"] is not True:
                raise ValueError("History raw producing report authority changed.")
            for name in arm["receipt_paths"]:
                receipt = record("plain60", s.FREEZE_COMMIT, name)
                if receipt["exit_code"] != 0 or receipt["timeout"] or receipt["source_drift"]:
                    raise ValueError("History producing receipt did not complete.")
    roles = record("plain60", s.FREEZE_COMMIT, s.NAMESPACE + "/tool-input-roles-v3.json")
    inventories = record("plain60", s.FREEZE_COMMIT, roles["inventories_path"])
    if (
        roles["schema"] != "tool-input-roles-v3"
        or roles["base_revision"] != c.CONTENT_BASE
        or _digest(inventories) != roles["inventories_sha256"]
    ):
        raise ValueError("History source-token inventory authority changed.")
    common = {
        name: pin
        for name, pin in inventories["base"].items()
        if inventories["head"].get(name) == pin
    }
    changed = (inventories["base"].keys() | inventories["head"].keys()) - common.keys()
    if (
        set(roles["roles"]) != changed
        or any(
            role
            not in {"runtime-or-generator-treatment", "side-derived-output", "untimed-governance"}
            for role in roles["roles"].values()
        )
        or _digest(common) != roles["common_sha256"]
    ):
        raise ValueError("History source-token complete role authority changed.")


@contextmanager
def witnesses(records: list[dict[str, object]]) -> Iterator[None]:
    token = _WITNESSES.set(records)
    try:
        yield
    finally:
        _WITNESSES.reset(token)


def _seal(builder: _Builder, identity: dict[str, object], runtime: str, phase_id: str) -> Snapshot:
    root = builder.root
    if (
        builder.declarations.keys() != builder.members.keys()
        or builder.members.keys() != builder.contents.keys()
    ):
        raise ValueError("History declared/acquired catalog mismatch.")
    for key, member in builder.members.items():
        domain, revision, name = key
        raw = builder.contents[key]
        if (
            (member.domain, member.commit, member.path) != key
            or member.size != len(raw)
            or member.sha256 != _sha(raw)
        ):
            raise ValueError("History member differs from its acquired identity.")
        oid = builder.roots[domain, revision]
        parts = name.split("/")
        for component in parts[:-1]:
            mode, oid = builder.trees[domain, oid][component]
            if mode != "40000":
                raise ValueError("History published path is not a native tree.")
        mode, oid = builder.trees[domain, oid][parts[-1]]
        if (
            mode != member.mode
            or oid != member.oid
            or builder.objects[domain, oid] != ("blob", raw)
        ):
            raise ValueError("History published member differs from its native path.")
        declarations = builder.declarations[key]
        if set(member.authorities) != {authority for authority, _ in declarations} or any(
            pin is not None and pin != member.sha256 for _, pin in declarations
        ):
            raise ValueError("History published member differs from its original authority.")
    members = dict(builder.members)
    semantic = {
        "identity": {key: identity.get(key) for key in ("base", "head", "pr_head")},
        "runtime": runtime,
        "authorities": dict(builder.authorities),
        "members": [asdict(member) for _, member in sorted(members.items())],
        "proofs": [
            [domain, args, _sha(raw)] for (domain, args), raw in sorted(builder.facts.items())
        ],
        "commit_trees": [
            [domain, revision, tree] for (domain, revision), tree in sorted(builder.roots.items())
        ],
        "tree_edges": [
            [domain, oid, [[name, mode, child] for name, (mode, child) in sorted(rows.items())]]
            for (domain, oid), rows in sorted(builder.trees.items())
        ],
        "declared_count": len(members),
        "acquired_count": len(builder.contents),
        "native_objects": [
            [domain, oid, kind, len(raw)]
            for (domain, oid), (kind, raw) in sorted(builder.objects.items())
        ],
    }
    if members.keys() != builder.contents.keys():
        raise ValueError("History declared/acquired catalog mismatch.")
    return Snapshot(
        root,
        _new_lease(),
        MappingProxyType(members),
        MappingProxyType(dict(builder.contents)),
        MappingProxyType(dict(builder.facts)),
        _digest(semantic),
        phase_id,
        json.dumps(
            semantic | {"observation_identity": identity}, sort_keys=True, separators=(",", ":")
        ),
    )


@contextmanager
def _activate(snapshot: Snapshot) -> Iterator[Snapshot]:
    if _ACTIVE.get() is not None or not snapshot._lease.valid():
        raise ValueError("Nested or expired history phase.")
    token = _ACTIVE.set(snapshot)
    try:
        yield snapshot
    finally:
        snapshot._lease.revoke()
        _ACTIVE.reset(token)


@contextmanager
def phase(root: Path, base_ref: str, pr_head: str | None) -> Iterator[Snapshot]:
    """Each call acquires independently; nested phases reject before Git operations."""
    from tools.performance_preflight import source_hashes
    from tools.quality_runtime_successor import ASSESSMENT, owned
    from warhammer40k_core.build_identity import verified_engine_build_identity

    if _ACTIVE.get() is not None:
        raise ValueError("Nested history phases are not admitted.")
    records = _WITNESSES.get()
    phase_id = uuid.uuid4().hex
    witness: dict[str, object] = {
        "phase_id": phase_id,
        "role": "validation" if records is None else "preflight" if not records else "postflight",
        "status": "failed",
    }
    if records is not None:
        records.append(witness)
    identity = _identity(root, base_ref, pr_head, domain_state=True)
    runtime = verified_engine_build_identity().build_id
    assessment = json.loads(owned(root, ASSESSMENT))
    comparisons = assessment["comparisons"]
    from tools.performance_ci60_qualification import PR_BASE, comparison_paths

    expected_comparisons = comparison_paths(root)
    original_comparisons = {
        family: "docs/performance/current/qualification40-" + family + ".json"
        for family in expected_comparisons
    }
    if (
        identity["base"] != PR_BASE
        or assessment["base"] != identity["base"]
        or comparisons not in (expected_comparisons, original_comparisons)
    ):
        raise ValueError("History snapshot does not support this assessment cohort.")
    cohort = source_hashes(root, set(comparisons.values()) | {ASSESSMENT})
    builder = _catalog(root, str(identity["base"]))
    builder.finish()
    if (
        identity != _identity(root, base_ref, pr_head, domain_state=True)
        or runtime != verified_engine_build_identity().build_id
        or cohort != source_hashes(root, set(comparisons.values()) | {ASSESSMENT})
    ):
        raise ValueError("History acquisition boundary changed.")
    snapshot = _seal(builder, identity, runtime, phase_id)
    del builder
    live_identity = {
        key: value
        for key, value in identity.items()
        if key not in {"environment", "configuration", "replacements"}
    }
    witness.update(
        {
            "domain_identity": _digest(identity),
            "semantic_digest": snapshot.semantic_digest,
            "catalog": json.loads(snapshot.certificate),
        }
    )
    completed = False
    try:
        with _activate(snapshot):
            yield snapshot
        completed = True
    finally:
        if live_identity != _identity(root, base_ref, pr_head, domain_state=False):
            raise ValueError("History live repository identity changed during phase.")
        if completed:
            witness["status"] = "completed"
