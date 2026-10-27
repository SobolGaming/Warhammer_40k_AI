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

HISTORICAL_RECIPE = "tests/data/d07_geometry_containment_v1.json"
HISTORICAL_RECIPE_SHA256 = "9a48238773d43f9b0bca31a87921eea9854b71a242f0004ba98121f2b39dc676"
FNP_RECIPE = "tests/data/d07_geometry_containment_v2.json"
FNP_RECIPE_SHA256 = "f41c809e76eeec51ef4d2f723020c9035ef84bfbb42b0f109a09445ed3d87abe"
RECIPE = "tests/data/d07_geometry_containment_v3.json"
RECIPE_SHA256 = "3f1ff9c73b8df6d6581896f68d83dc9f43e70a627df7023a4219c5da39a5af2f"
CURRENT_RUNTIME_BASE = "d7b7650fa1c76ee5830a9ffc78522eba3a6a3209"
CURRENT_RUNTIME_COMMIT = "9fb03ba622df1b7524acb72e5990fc500bc50696"
CURRENT_SOURCE_SUBSTITUTIONS: dict[str, tuple[str, str]] = {
    "src/warhammer40k_core/_engine_build_manifest.json": (
        "b6b896a59ff7e2369a7b0f98d646959e52fe1f512aed81da5953e1dff3bccdc0",
        "de81bf5648c419d0aff27fa9b87e30b742ac3775d51ad3038f357abe247f241d",
    ),
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/generated_manifest.py": (
        "82bd099f7bef7a5ac80250308f53a049679b3356e5f0440a2e7ce3c487b9ff05",
        "ac7cde842c7d205c45ec52a3ac245fdff5f47449c30d728f235f73c11fa45065",
    ),
    "src/warhammer40k_core/engine/model_destruction_cause_authority.py": (
        "b4ec2cf988ee099490d10bd80d15faa23956e6a66b596dc117c1a7ed2224d83d",
        "89fd630f98562ca5c10cbeca1c0efe6cf224d8574ffcb8f1359a0986b7d4a93c",
    ),
    "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py": (
        "39e899cc655836022c77d81558470755f3a754f5a7847283f641b2f74fc48452",
        "223241ff32ca0c0ab5fecb0a8816a875b5c3e6e121c8ad033fe7d79e91cff5e2",
    ),
    "src/warhammer40k_core/engine/model_destruction_cause_producers.py": (
        "b4b2a2161bf241c4d0c64e44c542f649acf18b8989fe8c02a671d255b76ca139",
        "9542b0a0454ca2dc2265abf021406792aa6150b5f8a924aa50abe4675c9d2876",
    ),
    "src/warhammer40k_core/engine/retained_demise_removal.py": (
        "59e685da563e6cd0ed95bfe4d69e9c06e625a679f0f443ff3fc5c3bff5fad880",
        "48f911ed0726091b04dbd497dbab33f1952502578eed9d24dacf14b85d261c45",
    ),
    "src/warhammer40k_core/engine/retained_destruction_history.py": (
        "5a23f6af83cee991c0207073c43e58e13e1e2e80ac285acea07b1385102a5ead",
        "c1cd862e38ed2ad2aaefe829e5ffa29b11bc00fcfe3f0195923e65a0d31ce1ee",
    ),
}
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
    historical = read_owned_geometry_member(root, HISTORICAL_RECIPE)
    if _sha256(historical) != HISTORICAL_RECIPE_SHA256:
        raise ValueError("D07 historical recipe changed.")
    fnp_raw = read_owned_geometry_member(root, FNP_RECIPE)
    if _sha256(fnp_raw) != FNP_RECIPE_SHA256:
        raise ValueError("D07 reviewed FNP recipe changed.")
    raw = read_owned_geometry_member(root, RECIPE)
    if _sha256(raw) != RECIPE_SHA256:
        raise ValueError("D07 containment recipe changed.")
    recipe = cast(GeometryRecipe, json.loads(raw))
    if (
        recipe["version"] != "d07-geometry-containment-v3-reviewed-ci57-c5"
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
    # Keep the original AST rejection boundary ahead of the finite catalog proof.
    # This current catalog is not semantic qualification of the seven successors.
    expected_recipe = cast(GeometryRecipe, json.loads(fnp_raw))
    for name, (before, after) in CURRENT_SOURCE_SUBSTITUTIONS.items():
        if expected_recipe["source_files"][name] != before:
            raise ValueError("D07 reviewed runtime predecessor changed: " + name)
        expected_recipe["source_files"][name] = after
    expected_recipe["version"] = "d07-geometry-containment-v3-reviewed-ci57-c5"
    if recipe != expected_recipe:
        raise ValueError("D07 current catalog differs outside the seven reviewed successors.")
