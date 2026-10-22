"""Invocation-local pure proof reuse and fresh, owned source scans.

No filesystem or Git result is cached. Each scan reads every byte again and checks
ownership afresh. Only the already checked ancestors within that scan are shared.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, cast

_PROOFS: ContextVar[set[tuple[Callable[..., None], bytes, bytes, str]] | None] = ContextVar(
    "proofs", default=None
)


def invocation[F: Callable[..., Any]](function: F) -> F:
    """Each validation, including the independent post-smoke call, starts empty."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = _PROOFS.set(set())
        try:
            return function(*args, **kwargs)
        finally:
            _PROOFS.reset(token)

    return cast(F, wrapped)


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


def source_hashes(root: Path, names: set[str]) -> dict[str, str]:
    """Read all owned files, checking each directory once per fresh scan.

    Directory and file identities are checked again after reading. Observed
    renames, links, replacements and concurrent writes fail even if bytes match.
    """
    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased cumulative root.")
    directories: dict[Path, os.stat_result] = {}
    result = {}
    for name in sorted(names):
        relative = Path(name)
        if (
            relative.is_absolute()
            or relative.drive
            or relative.as_posix() != name
            or ".." in relative.parts
        ):
            raise ValueError("Noncanonical D07 member: " + name)
        path = root
        for component in ("", *relative.parts[:-1]):
            path = path / component
            if path not in directories:
                metadata = path.lstat()
                if not stat.S_ISDIR(metadata.st_mode) or path.is_junction():
                    raise ValueError("Aliased D07 member: " + name)
                directories[path] = metadata
        path = root / relative
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or path.is_junction():
            raise ValueError("D07 member must be an owned regular file: " + name)
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read()
            closed = os.fstat(stream.fileno())
        after = path.lstat()
        if (
            not _same_file(before, opened)
            or not _same_file(opened, closed)
            or not _same_file(closed, after)
        ):
            raise ValueError("Cumulative source changed during owned read: " + name)
        result[name] = hashlib.sha256(raw).hexdigest()
    for path, before in directories.items():
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_mode) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
        ) or path.is_junction():
            raise ValueError("Cumulative source directory changed during owned scan.")
    return result


def _same_file(before: os.stat_result, after: os.stat_result) -> bool:
    return all(
        getattr(before, field) == getattr(after, field)
        for field in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    )
