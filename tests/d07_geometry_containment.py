"""Exact D07 geometry containment; never supplies archive bytes as a live owner.

This is a structural preservation check only. The separate live casualty/retry
controls and exact-head qualification remain necessary for behavioral approval.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import stat
from pathlib import Path
from typing import TypedDict, cast

RECIPE = "tests/data/d07_geometry_containment_v1.json"
RECIPE_SHA256 = "9a48238773d43f9b0bca31a87921eea9854b71a242f0004ba98121f2b39dc676"
LIVE = "src/warhammer40k_core/engine/phases/movement_resolution_flow.py"
ARCHIVE = "data/source_audits/d07/baseline/" + LIVE + ".txt"

# Exact statements independently anchor the AST proof; editable byte maps cannot
# expand this transformation. Indices refer to statement lists, not source lines.
RETRY_AST_SHA256 = "1a94d163848a5144dbec106729ea8465d6f9b42aa151c6634fc9313f5f656110"
BEFORE_FAILED_ROLL_SHA256 = "314912dde2f8458120e77bff17e3f1a66030e9fafc7084778f2e2c9e92b2b0c5"
AFTER_FAILED_ROLL_SHA256 = "0b5bf7f8c8dbcfd4fb0dddc672c1eef9c1490b9cfc8f134e2b5055c9c319608c"


class GeometryRecipe(TypedDict):
    version: str
    live: str
    archive: str
    archive_sha256: str
    source_files: dict[str, str]
    source_evidence: dict[str, str]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False, show_empty=True)


def read_owned_geometry_member(root: Path, name: str) -> bytes:
    relative = Path(name)
    if (
        relative.is_absolute()
        or relative.drive
        or relative.as_posix() != name
        or ".." in relative.parts
    ):
        raise ValueError("Noncanonical D07 member: " + name)
    path = root
    for component in relative.parts:
        path = path / component
        if path.is_symlink() or path.is_junction():
            raise ValueError("Aliased D07 member: " + name)
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("D07 member must be an owned regular file: " + name)
    return path.read_bytes()


def _function(tree: ast.Module, index: int, name: str) -> ast.FunctionDef:
    if index >= len(tree.body):
        raise ValueError("Missing D07 geometry owner: " + name)
    node = tree.body[index]
    if not isinstance(node, ast.FunctionDef) or node.name != name:
        raise ValueError("D07 geometry owner or module order changed: " + name)
    return node


def assert_bounded_geometry(old: bytes, current: bytes) -> None:
    """Prove the complete AST after reversing only four exact occurrences.

    Kept separate from raw hash checks so sensitivity controls can prove that
    repinning a current-file digest cannot weaken the transformation boundary.
    Callers needing raw provenance use verify_d07_geometry_containment instead.
    """
    predecessor = ast.parse(old)
    successor = ast.parse(current)
    proposal = _function(successor, 19, "_apply_movement_proposal_decision")
    fall_back = proposal.body[21]
    if not isinstance(fall_back, ast.If):
        raise TypeError("D07 Fall Back branch location changed.")
    retry = [_dump(n) for n in fall_back.body[13:16]]
    retry_digest = _sha256(json.dumps(retry, separators=(",", ":")).encode())
    if len(retry) != 3 or retry_digest != RETRY_AST_SHA256:
        raise ValueError("D07 requires the exact three retry statements at their exact occurrence.")
    continuation = _function(successor, 28, "_continue_desperate_escape_fall_back")
    if _sha256(_dump(continuation.body[0]).encode()) != AFTER_FAILED_ROLL_SHA256:
        raise ValueError("D07 failed-roll delegation changed.")
    original_continuation = _function(predecessor, 28, "_continue_desperate_escape_fall_back")
    if _sha256(_dump(original_continuation.body[0]).encode()) != BEFORE_FAILED_ROLL_SHA256:
        raise ValueError("D07 predecessor failed-roll branch changed.")
    restored = copy.deepcopy(successor)
    restored_proposal = _function(restored, 19, "_apply_movement_proposal_decision")
    restored_branch = restored_proposal.body[21]
    if not isinstance(restored_branch, ast.If):
        raise TypeError("D07 Fall Back branch location changed.")
    del restored_branch.body[13:16]
    restored_continuation = _function(restored, 28, "_continue_desperate_escape_fall_back")
    restored_continuation.body[0] = copy.deepcopy(original_continuation.body[0])
    if _dump(restored) != _dump(predecessor):
        raise ValueError("D07 geometry differs outside the exact retry/delegation occurrences.")


def verify_d07_geometry_containment(root: Path) -> None:
    """Revalidate actual live bytes and all runtime owners before reading the archive.

    No success cache and no predecessor-return API. Full src membership/bytes bind
    transitive and dynamic imports, initializers, packet types, casualty routing,
    native removal and attribution, without claiming their semantic qualification.
    """
    if root.is_symlink() or root.is_junction():
        raise ValueError("D07 root must be an owned directory.")
    root = root.resolve(strict=True)
    raw = read_owned_geometry_member(root, RECIPE)
    if _sha256(raw) != RECIPE_SHA256:
        raise ValueError("D07 containment recipe changed.")
    recipe = cast(GeometryRecipe, json.loads(raw))
    if (
        recipe["version"] != "d07-geometry-containment-v1"
        or recipe["live"] != LIVE
        or recipe["archive"] != ARCHIVE
    ):
        raise ValueError("D07 containment recipe identity changed.")
    members: set[str] = set()
    for path in (root / "src").rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Aliased D07 source member.")
        if path.is_file():
            members.add(path.relative_to(root).as_posix())
    if members != recipe["source_files"].keys():
        raise ValueError("D07 runtime source membership changed.")
    if len({name.casefold() for name in members}) != len(members):
        raise ValueError("D07 runtime source contains aliased names.")
    live = b""
    for name, expected in recipe["source_files"].items():
        actual = read_owned_geometry_member(root, name)
        if _sha256(actual) != expected:
            raise ValueError("D07 live runtime input changed: " + name)
        if name == LIVE:
            live = actual
    for name, expected in recipe["source_evidence"].items():
        if _sha256(read_owned_geometry_member(root, name)) != expected:
            raise ValueError("D07 source evidence changed: " + name)
    # Archive access occurs only after this invocation's live validation succeeds.
    old = read_owned_geometry_member(root, ARCHIVE)
    if _sha256(old) != recipe["archive_sha256"]:
        raise ValueError("D07 geometry archive changed.")
    assert_bounded_geometry(old, live)
