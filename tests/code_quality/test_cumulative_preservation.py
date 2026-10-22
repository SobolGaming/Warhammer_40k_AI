"""Exact successor admission must fail at each real corruption boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from tools import cumulative_preservation as cumulative
from tools import performance_category_migration as legacy
from tools import performance_policy as policy
from tools import performance_reconstruction_campaign as reconstruction
from tools import performance_tool_inputs as original

ROOT = Path(__file__).resolve().parents[2]


def test_finite_owner_and_operation_union_preserves_all_prior_obligations() -> None:
    record = cumulative._registry(ROOT)
    ledger = cumulative._json(ROOT, cumulative.NAMESPACE + "/owner-ledger.json")
    assert len(ledger) == len({(r["path"], r["owner"]) for r in ledger}) == 153
    assert Counter(r["disposition"] for r in ledger) == {
        "needs_new_behavioral_guard": 97,
        "documented_approved_bugfix": 44,
        "unresolved": 10,
        "proven_equivalence": 2,
    }
    assert all(
        r["independent_row"]["decision"].startswith("ACCEPT")
        for r in ledger
        if r["disposition"] in {"needs_new_behavioral_guard", "unresolved"}
    )
    prior = json.loads(
        (ROOT / cumulative.NAMESPACE / "map/assessment-map-additions.json.txt").read_bytes()
    )
    accepted = subprocess.check_output(
        ["git", "show", cumulative.ACCEPTED + ":" + original.MAP_PATH], cwd=ROOT
    )
    old = json.loads(accepted)
    new = json.loads((ROOT / original.MAP_PATH).read_bytes())
    assert {k: v for k, v in new.items() if k != "operations"} == {
        k: v for k, v in old.items() if k != "operations"
    }
    additions = new["operations"].keys() - old["operations"].keys()
    assert len(additions) == 52
    assert all(new["operations"][k] == v for k, v in old["operations"].items())
    assert additions == set(prior["added_operations"])
    assert {
        (p, owner)
        for k in additions
        for p in new["operations"][k]["paths"]
        for owner in new["operations"][k]["owners"]
    } == {(r["path"], r["owner"]) for r in ledger}
    for k in additions:
        op = new["operations"][k]
        assert len(op["paths"]) == 1
        assert op["mandatory"]
        assert op["sensitive"]
        assert all(not any(c in s for c in "*?[") for s in op["paths"] + op["owners"])
    assert record["accepted_source"] == cumulative.SOURCE_ID
    cumulative.verify_owner_ledger(ROOT)


def test_explicit_content_route_retains_historical_measurement_identity() -> None:
    report = policy.read_object(ROOT / reconstruction.REPORT)
    before = json.dumps(report, sort_keys=True)
    measured, binding, receipt = cumulative.retained_inputs(
        ROOT,
        current=policy.runtime_inputs(ROOT),
        report=report,
        base=legacy.BASE,
        runtime_id=reconstruction.RUNTIME,
    )
    assert original.digest(measured) == reconstruction.MEASURED_DIGEST
    assert binding is None
    assert len(receipt) == 64
    assert json.dumps(report, sort_keys=True) == before
    assert cumulative.CONTENT_BASE != legacy.BASE
    assert len(cumulative.verify_baseline(ROOT)) == 64
    # No replacement ancestry, graft or synthetic merge is installed.
    for name in ("info/grafts", "shallow", "objects/info/alternates"):
        assert not (ROOT / ".git" / name).exists()
    assert not subprocess.check_output(["git", "replace", "--list"], cwd=ROOT)
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", legacy.SOURCE_COMMIT, "HEAD"], cwd=ROOT
        ).returncode
        != 0
    )
    with pytest.raises(subprocess.CalledProcessError):
        legacy.reviewed_control_hashes(ROOT)


@pytest.fixture(scope="module")
def copy_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cumulative-sensitivities")
    shutil.copytree(
        ROOT,
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"
        ),
    )
    git_dir = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT)
        .decode()
        .strip()
    )
    (root / ".git").write_text("gitdir: " + git_dir + "\n")
    assert len(cumulative.verify_live(root)) == 64
    return root


@pytest.mark.parametrize(
    "name",
    [
        "uv.lock",
        "ci/test_shards/shard-1.txt",
        "tests/conftest.py",
        "src/warhammer40k_core/engine/sequencing.py",
        "tests/support/section08_native_mission.py",
        "docs/FOCUSED_DEFECT_CHECKPOINT.md",
        "data/source_audits/d07/original-tests.json",
    ],
)
def test_actual_dependency_selection_owner_assertion_or_authority_drift_refuses(
    copy_source: Path,
    name: str,
) -> None:
    path = copy_source / name
    before = path.read_bytes()
    try:
        path.write_bytes(before + b"\nchanged input\n")
        with pytest.raises(ValueError, match="Reviewed migration source/data changed"):
            cumulative.verify_live(copy_source)
    finally:
        path.write_bytes(before)


@pytest.mark.parametrize("kind", ["omit", "extra", "repin", "owner", "assertion", "review"])
def test_registry_and_accepted_evidence_cannot_be_rewritten(copy_source: Path, kind: str) -> None:
    namespace = copy_source / cumulative.NAMESPACE
    target = namespace / (
        "owner-ledger.json"
        if kind == "owner"
        else "d07-recipes.json"
        if kind == "assertion"
        else "evidence/task-37/RESULT37.json.txt"
    )
    before = target.read_bytes()
    registry = namespace / "registry.json"
    prior = registry.read_bytes()
    extra = namespace / "unreviewed.txt"
    try:
        if kind == "omit":
            target.unlink()
        elif kind == "extra":
            extra.write_text("unreviewed")
        else:
            target.write_bytes(before + b" ")
            if kind == "repin":
                data = json.loads(prior)
                data["members"][target.relative_to(namespace).as_posix()] = hashlib.sha256(
                    target.read_bytes()
                ).hexdigest()
                registry.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Cumulative"):
            cumulative._registry(copy_source)
    finally:
        target.write_bytes(before)
        registry.write_bytes(prior)
        if extra.exists():
            extra.unlink()


@pytest.mark.parametrize("kind", ["file_symlink", "directory_symlink", "hardlink", "root_symlink"])
def test_physical_ownership_refuses_aliases(copy_source: Path, tmp_path: Path, kind: str) -> None:
    import os

    target = copy_source / "src/warhammer40k_core/engine/sequencing.py"
    moved = tmp_path / "original.py"
    link = tmp_path / "aliased-root"
    directory = copy_source / "src/warhammer40k_core/engine"
    moved_directory = copy_source / "src/warhammer40k_core/engine-held"
    try:
        if kind == "root_symlink":
            link.symlink_to(copy_source, target_is_directory=True)
            with pytest.raises(ValueError, match="Aliased"):
                cumulative.verify_live(link)
        elif kind == "directory_symlink":
            directory.rename(moved_directory)
            directory.symlink_to(moved_directory, target_is_directory=True)
            with pytest.raises(ValueError, match=r"Aliased|membership"):
                cumulative.verify_live(copy_source)
        else:
            target.rename(moved)
            if kind == "hardlink":
                os.link(moved, target)
            else:
                target.symlink_to(moved)
            with pytest.raises(ValueError, match=r"Aliased|owned regular"):
                cumulative.verify_live(copy_source)
    finally:
        if link.is_symlink():
            link.unlink()
        if directory.is_symlink():
            directory.unlink()
            moved_directory.rename(directory)
        if moved.exists():
            target.unlink()
            moved.rename(target)


def test_every_d07_recipe_is_independently_sensitive_to_extra_or_removed_assertion() -> None:
    recipes = cumulative._json(ROOT, cumulative.NAMESPACE + "/d07-recipes.json")
    from tests.category_migration_preservation import read_historical_test_bytes

    refused = []
    for path, recipe in recipes.items():
        before = (ROOT / cumulative.NAMESPACE / "predecessors" / (path + ".txt")).read_bytes()
        current = read_historical_test_bytes(ROOT, path).replace(b"\r\n", b"\n")
        cumulative.assert_recipe(before, current, recipe)
        # Even a recomputed current hash cannot authorize another AST occurrence.
        forged = current + b"\nassert False, 'unreviewed assertion'\n"
        recipe["after_sha256"] = hashlib.sha256(forged).hexdigest()
        with pytest.raises(ValueError, match="whole-module"):
            cumulative.assert_recipe(before, forged, recipe)
        tree = ast.parse(current)
        assertions = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
        if assertions:
            assertions[0].test = ast.Constant(value=True)
        else:
            # Shared helper/type modules carry structure, rather than test asserts.
            literal = next(
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            )
            literal.value += ":unreviewed-helper-statement"
        with pytest.raises(ValueError, match="whole-module"):
            cumulative.assert_recipe(before, ast.unparse(tree).encode(), recipe)
        refused.append(path)
    assert len(refused) == 33


@pytest.mark.parametrize(
    "name",
    [
        "tests/ignored_collector.py",
        "src/warhammer40k_core/ignored_owner.py",
        "conformance/typescript/src/ignored_extra.ts",
    ],
)
def test_ignored_consumer_inputs_do_not_escape_membership(copy_source: Path, name: str) -> None:
    path = copy_source / name
    ignore = copy_source / ".gitignore"
    before = ignore.read_bytes()
    try:
        path.write_text("# extra consumer\n")
        ignore.write_bytes(before + b"\n" + name.encode() + b"\n")
        with pytest.raises(ValueError, match="membership"):
            cumulative.verify_live(copy_source)
    finally:
        path.unlink()
        ignore.write_bytes(before)


@pytest.mark.parametrize(
    "path",
    [
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_category_migration_preservation.py",
        "tools/core_rules_order95_audit.py",
    ],
)
def test_three_changed_controls_require_exact_transformations(path: str) -> None:
    rows = cumulative._json(ROOT, cumulative.NAMESPACE + "/control-transformations.json")
    row = next(r for r in rows if r["path"] == path)
    before = subprocess.check_output(
        ["git", "show", cumulative.CONTENT_BASE + ":" + path], cwd=ROOT
    )
    after = subprocess.check_output(["git", "show", cumulative.ACCEPTED + ":" + path], cwd=ROOT)
    cumulative.assert_recipe(before, after, row["baseline_to_accepted"])
    forged = after + b"\nassert False, 'unreviewed control'\n"
    row["baseline_to_accepted"]["after_sha256"] = hashlib.sha256(forged).hexdigest()
    with pytest.raises(ValueError, match="whole-module"):
        cumulative.assert_recipe(before, forged, row["baseline_to_accepted"])


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/test_order97_facade_evidence.py",
        "tests/unit/test_phase13b_shooting_declarations.py",
    ],
)
def test_d09_successor_does_not_repin_historical_after_or_assertions(path: str) -> None:
    from tests.category_migration_preservation import read_historical_test_bytes
    from tests.d09_test_preservation_helpers import preserved_d09_predecessor_test_bytes

    recipe = cumulative._json(ROOT, cumulative.NAMESPACE + "/d09-recipes.json")[path]
    stage = (ROOT / cumulative.NAMESPACE / recipe["d09_stage"]).read_bytes()
    current = read_historical_test_bytes(ROOT, path).replace(b"\r\n", b"\n")
    assert hashlib.sha256(stage).hexdigest() == recipe["d09_after_sha256"]
    predecessor = preserved_d09_predecessor_test_bytes(path, stage)
    assert hashlib.sha256(predecessor).hexdigest() == recipe["d09_before_sha256"]
    assert hashlib.sha256(predecessor).hexdigest() == recipe["d07_effective_sha256"]
    cumulative.assert_recipe(stage, current, recipe)
    with pytest.raises(ValueError, match="whole-module"):
        cumulative.assert_recipe(stage, current + b"\nassert False\n", recipe)
