"""Sensitivity controls for the bounded D07 geometry verifier only."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path
from typing import cast

import pytest

from tests import d07_geometry_containment as geometry

ROOT = Path(__file__).resolve().parents[2]
RETRY_OWNER = "src/warhammer40k_core/engine/phases/movement_escape_mortals.py"
CASUALTY_OWNER = "src/warhammer40k_core/engine/desperate_escape_mortal_wounds.py"


@pytest.fixture(scope="module")
def preserved_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("d07-geometry")
    shutil.copytree(ROOT / "src", root / "src")
    recipe = cast(geometry.GeometryRecipe, json.loads((ROOT / geometry.RECIPE).read_bytes()))
    for name in (geometry.RECIPE, geometry.ARCHIVE, *recipe["source_evidence"]):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
    return root


def _changed_geometry(kind: str) -> bytes:
    tree = ast.parse((ROOT / geometry.LIVE).read_bytes())
    proposal = tree.body[19]
    assert isinstance(proposal, ast.FunctionDef)
    branch = proposal.body[21]
    assert isinstance(branch, ast.If)
    if kind == "fourth_retry_statement":
        branch.body.insert(16, ast.Pass())
    elif kind == "duplicate_retry_occurrence":
        branch.body.insert(
            16,
            ast.parse(
                "from warhammer40k_core.engine.phases.movement_escape_mortals "
                "import completed_escape_retry"
            ).body[0],
        )
    elif kind == "retry_condition":
        retry = branch.body[15]
        assert isinstance(retry, ast.If)
        retry.test = ast.Constant(value=True)
    elif kind == "other_geometry_branch":
        # A preexisting geometry rejection condition outside the three additions.
        other = branch.body[12]
        assert isinstance(other, ast.If)
        other.test = ast.Constant(value=False)
    elif kind == "other_function":
        other_function = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n is not proposal
        )
        other_function.body.append(ast.Pass())
    elif kind == "module_statement":
        tree.body.append(ast.parse("d07_unrelated_initializer = 1").body[0])
    elif kind == "delegation_attribution":
        continuation = tree.body[28]
        assert isinstance(continuation, ast.FunctionDef)
        failed = continuation.body[0]
        assert isinstance(failed, ast.If)
        returned = failed.body[1]
        assert isinstance(returned, ast.Return)
        assert isinstance(returned.value, ast.Call)
        keyword = next(k for k in returned.value.keywords if k.arg == "action_result")
        keyword.value = ast.Constant(value=None)
    elif kind == "decorator":
        proposal.decorator_list.append(ast.Name(id="unreviewed_decorator", ctx=ast.Load()))
    else:
        raise ValueError("Unknown D07 mutation: " + kind)
    return ast.unparse(ast.fix_missing_locations(tree)).encode()


def test_d07_geometry_exact_containment_positive(preserved_root: Path) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)


@pytest.mark.parametrize(
    "kind",
    [
        "fourth_retry_statement",
        "duplicate_retry_occurrence",
        "retry_condition",
        "other_geometry_branch",
        "other_function",
        "module_statement",
        "delegation_attribution",
        "decorator",
    ],
)
def test_d07_bounded_ast_rejects_unlisted_changes_even_without_byte_pins(kind: str) -> None:
    old = (ROOT / geometry.ARCHIVE).read_bytes()
    with pytest.raises(ValueError, match="D07"):
        geometry.assert_bounded_geometry(old, _changed_geometry(kind))


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (geometry.LIVE, b"def _apply_movement_proposal_decision(", b"def changed_owner("),
        (
            RETRY_OWNER,
            b"proposal.actor_id != action.actor_id",
            b"proposal.actor_id == action.actor_id",
        ),
        (RETRY_OWNER, b"application.target_unit_instance_id", b"application.application_id"),
        (CASUALTY_OWNER, b"DestructionSourceKind.ABILITY", b"DestructionSourceKind.ATTACK"),
        (CASUALTY_OWNER, b"spill_over=True", b"spill_over=False"),
    ],
)
def test_d07_warm_live_drift_rejects_before_archive_access(
    preserved_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    before: bytes,
    after: bytes,
) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)
    target = preserved_root / path
    raw = target.read_bytes()
    assert raw.count(before) >= 1
    target.write_bytes(raw.replace(before, after, 1))
    reads: list[str] = []
    original_read = geometry.read_owned_geometry_member

    def tracked_read(root: Path, name: str) -> bytes:
        reads.append(name)
        return original_read(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", tracked_read)
    try:
        with pytest.raises(ValueError, match="D07 live runtime input changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
        assert geometry.ARCHIVE not in reads
    finally:
        target.write_bytes(raw)


def test_d07_recomputed_current_pin_cannot_admit_fourth_statement(
    preserved_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_path = preserved_root / geometry.LIVE
    recipe_path = preserved_root / geometry.RECIPE
    live = live_path.read_bytes()
    frozen = recipe_path.read_bytes()
    changed = _changed_geometry("fourth_retry_statement")
    recipe = json.loads(frozen)
    recipe["source_files"][geometry.LIVE] = hashlib.sha256(changed).hexdigest()
    repinned = (json.dumps(recipe, indent=2) + "\n").encode()
    live_path.write_bytes(changed)
    recipe_path.write_bytes(repinned)
    monkeypatch.setattr(geometry, "RECIPE_SHA256", hashlib.sha256(repinned).hexdigest())
    try:
        with pytest.raises(ValueError, match="outside the exact"):
            geometry.verify_d07_geometry_containment(preserved_root)
    finally:
        live_path.write_bytes(live)
        recipe_path.write_bytes(frozen)


@pytest.mark.parametrize("change", ["extra", "missing", "recipe", "archive"])
def test_d07_membership_recipe_and_archive_are_bound(preserved_root: Path, change: str) -> None:
    target = (
        preserved_root
        / {
            "extra": "src/warhammer40k_core/d07_unreviewed.py",
            "missing": RETRY_OWNER,
            "recipe": geometry.RECIPE,
            "archive": geometry.ARCHIVE,
        }[change]
    )
    raw = target.read_bytes() if target.exists() else None
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes((raw or b"") + b"\n# unreviewed\n")
    try:
        with pytest.raises(ValueError, match="D07"):
            geometry.verify_d07_geometry_containment(preserved_root)
    finally:
        if raw is None:
            target.unlink()
        else:
            target.write_bytes(raw)
