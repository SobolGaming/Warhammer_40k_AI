"""Authenticate the original provenance-control fixture without repinning history."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tools.performance_tool_inputs import (
    APPLICABILITY,
    MAP_PATH,
    REPORT_ARCHIVE,
    SPEC_ARCHIVE,
    digest,
)

REVISION = "40a727563355ecd29cc981ad141dd194a5690a99"
INPUT_DIGEST = "5bca782a3ad86167109e6b80f4f18619a7620e3a4383adee58efd557974e85a9"
PROOF_SHA256 = "449161575a758d7e50c062b4610f08805ad3b1c61f085368b19d294b4fc85e84"
MAP_SHA256 = "31ab2200dee42a0d8f72902d51822c4d0f400680b0132aa8466215be2dab86e1"


def archival_fixture(root: Path, destination: Path) -> tuple[dict[str, str], dict[str, object]]:
    paths: dict[str, str] = {}
    tree = subprocess.check_output(["git", "ls-tree", "-r", "-z", REVISION], cwd=root)
    for row in tree.decode().split("\0"):
        if not row:
            continue
        metadata, path = row.split("\t", 1)
        mode, kind, oid = metadata.split()
        if path.startswith(
            ("src/", "tests/", "scripts/", "tools/", "contracts/schemas/")
        ) or path in {
            "uv.lock",
            "pyproject.toml",
            MAP_PATH,
            SPEC_ARCHIVE,
            REPORT_ARCHIVE,
            APPLICABILITY,
        }:
            assert kind == "blob"
            assert mode in {"100644", "100755"}
            paths[path] = oid
    names = sorted(paths)
    payload = subprocess.check_output(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input="".join(paths[name] + "\n" for name in names).encode(),
    )
    offset = 0
    inputs: dict[str, str] = {}
    documents: dict[str, bytes] = {}
    for name in names:
        boundary = payload.index(b"\n", offset)
        oid, kind, length = payload[offset:boundary].decode().split()
        assert oid == paths[name]
        assert kind == "blob"
        start, end = boundary + 1, boundary + 1 + int(length)
        raw = payload[start:end]
        assert payload[end : end + 1] == b"\n"
        offset = end + 1
        if name in {SPEC_ARCHIVE, REPORT_ARCHIVE, APPLICABILITY, MAP_PATH}:
            documents[name] = raw
        if name not in {SPEC_ARCHIVE, REPORT_ARCHIVE, APPLICABILITY}:
            inputs[name] = hashlib.sha256(raw).hexdigest()
    assert offset == len(payload)
    assert digest(inputs) == INPUT_DIGEST
    assert hashlib.sha256(documents[APPLICABILITY]).hexdigest() == PROOF_SHA256
    assert hashlib.sha256(documents[MAP_PATH]).hexdigest() == MAP_SHA256
    for name, raw in documents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (destination / ".git").write_text(f"gitdir: {(root / '.git').as_posix()}\n")
    return inputs, json.loads(documents[REPORT_ARCHIVE])
