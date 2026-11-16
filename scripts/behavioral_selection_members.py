"""Pure byte-bound membership validators shared by finite test admissions."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath


def _selection_no_links(root: Path, path: Path) -> None:
    if not path.is_relative_to(root):
        raise SystemExit("Test selection escaped repository: " + str(path))
    for member in (path, *path.parents):
        if member == root:
            break
        if member.is_symlink():
            raise SystemExit("Test selection contains a symlink alias: " + str(member))


def _selection_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise SystemExit("Duplicate cutover field: " + key)
        value[key] = item
    return value


def _selection_members(
    value: object, root: Path, *, current: dict[str, dict[str, object]] | None = None
) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict) or not value:
        raise SystemExit("Cutover members must be a nonempty object.")
    result: dict[str, dict[str, object]] = {}
    for name, item in value.items():
        if (
            not isinstance(name, str)
            or name != PurePosixPath(name).as_posix()
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            or ":" in name
            or not name.startswith("tests/")
            or not PurePosixPath(name).name.startswith("test_")
            or not name.endswith(".py")
            or not isinstance(item, dict)
            or item.keys() != {"mode", "blob_sha1", "sha256", "bytes"}
            or item["mode"] not in {"100644", "100755"}
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
        ):
            raise SystemExit("Malformed cutover member: " + str(name))
        for key, size in (("sha256", 64), ("blob_sha1", 40)):
            token = item[key]
            if (
                not isinstance(token, str)
                or len(token) != size
                or set(token) - set("0123456789abcdef")
            ):
                raise SystemExit("Malformed cutover digest: " + name)
        path = root / name
        _selection_no_links(root, path)
        if not path.is_file():
            raise SystemExit("Missing declared cutover member: " + name)
        observed = item if current is None else current.get(name, item)
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False)
        if (
            len(raw) != observed["bytes"]
            or hashlib.sha256(raw).hexdigest() != observed["sha256"]
            or blob.hexdigest() != observed["blob_sha1"]
        ):
            raise SystemExit("Cutover member bytes changed: " + name)
        if os.name != "nt" and bool(path.stat().st_mode & 0o100) != (observed["mode"] == "100755"):
            raise SystemExit("Cutover member mode changed: " + name)
        result[name] = item
    if len({name.casefold() for name in result}) != len(result):
        raise SystemExit("Case aliases in cutover membership.")
    return result
