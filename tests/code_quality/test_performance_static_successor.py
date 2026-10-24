"""Finite static edits cannot absorb changed validation or fixture behavior."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import py_compile
import runpy
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from tools import performance_preflight_successor as successor
from tools import quality_runtime_successor as ci54
from tools.performance_preflight import discovered_sources

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = "tests/code_quality/test_performance_preflight.py"


@pytest.fixture(scope="module")
def transitions() -> dict[str, Any]:
    record: dict[str, Any] = json.loads((ROOT / successor.STATIC_RECORD).read_bytes())
    assert record["schema"] == "exact-static-successor-v1"
    assert record["base"] == successor.STATIC_BASE
    assert record["changes"].keys() == successor.STATIC_BEFORE.keys()
    changes: dict[str, Any] = record["changes"]
    return changes


@pytest.fixture(scope="module")
def previous() -> dict[str, bytes]:
    return {
        name: subprocess.check_output(["git", "show", successor.STATIC_BASE + ":" + name], cwd=ROOT)
        for name in successor.STATIC_BEFORE
    }


@pytest.mark.parametrize("name", sorted(successor.STATIC_BEFORE))
def test_static_edits_match_independent_immutable_whole_module_recipes(
    name: str, transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    successor.assert_static_transition(
        name,
        previous[name],
        successor.ci_comparison(ROOT, name, (ROOT / name).read_bytes()),
        transitions[name],
    )


@pytest.mark.parametrize(
    ("name", "before", "after"),
    [
        (
            PREFLIGHT,
            b"cast(_PreflightMechanisms, preflight)",
            b"cast(_GateMechanisms, preflight)",
        ),
        (
            PREFLIGHT,
            b"cast(_PreflightMechanisms, preflight)",
            b"cast(_PreflightMechanisms, gate)",
        ),
        (PREFLIGHT, b"windows: bool,", b"windows: str,"),
        (
            PREFLIGHT,
            b"return self._source_digest(path, raw)",
            b'return self._source_digest(path, b"changed")',
        ),
        (PREFLIGHT, b'assert calls == [b"before", b"edited"]', b"assert True"),
        (
            successor.STATIC_FIXTURE,
            b"SOURCE_ID as STICKY_SOURCE_ID",
            b"UNREVIEWED_SOURCE_ID as STICKY_SOURCE_ID",
        ),
        (
            successor.STATIC_FIXTURE,
            b'__all__ = ["STICKY_SOURCE_ID",',
            b'__all__ = ["UNREVIEWED_EXPORT", "STICKY_SOURCE_ID",',
        ),
        (
            successor.STATIC_FIXTURE,
            b'seed="section08-native-command"',
            b'seed="unreviewed-new-workload"',
        ),
    ],
)
def test_static_recipes_reject_changed_seams_assertions_and_fixture_behavior_even_if_repinned(
    name: str,
    before: bytes,
    after: bytes,
    transitions: dict[str, Any],
    previous: dict[str, bytes],
) -> None:
    current = (ROOT / name).read_bytes()
    assert before in current
    changed = current.replace(before, after, 1)
    assert changed != current
    row = copy.deepcopy(transitions[name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="whole-module"):
        successor.assert_static_transition(name, previous[name], changed, row)


@pytest.mark.parametrize("kind", ["missing_identity", "unknown_edit", "wrong_recipe_type"])
def test_static_transition_rejects_malformed_records(
    kind: str, transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    row = copy.deepcopy(transitions[PREFLIGHT])
    if kind == "missing_identity":
        row.pop("before_sha256")
    elif kind == "unknown_edit":
        row["recipe"]["edits"][0]["kind"] = "unchecked replacement"
    else:
        row["recipe"] = []
    with pytest.raises(ValueError, match="Static transition"):
        successor.assert_static_transition(
            PREFLIGHT, previous[PREFLIGHT], (ROOT / PREFLIGHT).read_bytes(), row
        )


def test_static_transition_rejects_unlisted_source(
    transitions: dict[str, Any], previous: dict[str, bytes]
) -> None:
    with pytest.raises(ValueError, match="Static transition"):
        successor.assert_static_transition(
            "tests/support/unreviewed_fixture.py",
            previous[successor.STATIC_FIXTURE],
            (ROOT / successor.STATIC_FIXTURE).read_bytes(),
            transitions[successor.STATIC_FIXTURE],
        )


def test_static_historical_projection_rejects_unrelated_caller_bytes(
    previous: dict[str, bytes],
) -> None:
    raw = (ROOT / successor.STATIC_TEST).read_bytes()
    assert previous[successor.STATIC_TEST] != raw
    for supplied in (previous[successor.STATIC_TEST], raw + b"# unreviewed\n"):
        with pytest.raises(ValueError, match="caller supplied unrelated"):
            successor.static_predecessor(ROOT, successor.STATIC_TEST, supplied)


@pytest.fixture(scope="module")
def ci_transitions() -> dict[str, Any]:
    record: dict[str, Any] = json.loads((ROOT / successor.CI_RECORD).read_bytes())
    assert record["schema"] == "exact-ci-successor-v1"
    assert record["base"] == successor.CI_BASE
    assert record["changes"].keys() == successor.CI_BEFORE.keys() | {successor.CI_NEW}
    changes: dict[str, Any] = record["changes"]
    return changes


@pytest.mark.parametrize("name", [*successor.CI_BEFORE, successor.CI_NEW])
def test_ci_transition_preserves_exact_import_bootstrap_and_mapping_edits(
    name: str, ci_transitions: dict[str, Any]
) -> None:
    before = (
        None
        if name == successor.CI_NEW
        else subprocess.check_output(["git", "show", successor.CI_BASE + ":" + name], cwd=ROOT)
    )
    current = successor.ci_comparison(ROOT, name, (ROOT / name).read_bytes())
    successor.assert_ci_transition(name, before, current, ci_transitions[name])


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("tests/__init__.py", b"dont_write_bytecode = True", b"dont_write_bytecode = False"),
        ("scripts/__init__.py", b'BYTECODE"] = "1"', b'BYTECODE"] = "0"'),
        (
            "tools/generate_aeldari_datasheet_semantic_coverage.py",
            b"source_artifacts = _load_source_artifacts(DEFAULT_SOURCE_JSON_DIR)",
            b"source_artifacts = {}",
        ),
        (
            "docs/performance/policy-v3/operation-map.json",
            b'"samples_per_case": 7',
            b'"samples_per_case": 1',
        ),
    ],
)
def test_ci_transition_rejects_unreviewed_behavior_even_with_updated_after_hash(
    name: str, old: bytes, new: bytes, ci_transitions: dict[str, Any]
) -> None:
    before = (
        None
        if name == successor.CI_NEW
        else subprocess.check_output(["git", "show", successor.CI_BASE + ":" + name], cwd=ROOT)
    )
    raw = successor.ci_comparison(ROOT, name, (ROOT / name).read_bytes())
    assert old in raw
    changed = raw.replace(old, new, 1)
    row = copy.deepcopy(ci_transitions[name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        successor.assert_ci_transition(name, before, changed, row)


def test_ci_transition_rejects_false_absence_and_malformed_edits(
    ci_transitions: dict[str, Any],
) -> None:
    name = successor.CI_NEW
    raw = (ROOT / name).read_bytes()
    with pytest.raises(ValueError, match="CI transition identity"):
        successor.assert_ci_transition(name, b"", raw, ci_transitions[name])
    row = copy.deepcopy(ci_transitions[name])
    row["edits"] = [{"before": None, "after": "unreviewed"}]
    with pytest.raises(ValueError, match="CI transition edit is malformed"):
        successor.assert_ci_transition(name, None, raw, row)


@pytest.mark.parametrize("package", ["scripts", "tests"])
def test_default_package_launch_prevents_own_bytecode_but_discovers_explicit_pyc(
    package: str, tmp_path: Path
) -> None:
    module = "tests.code_quality" if package == "tests" else package
    relative = module.replace(".", "/")
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    if package == "tests":
        (tmp_path / "tests/__init__.py").write_bytes((ROOT / "tests/__init__.py").read_bytes())
    (directory / "__init__.py").write_bytes((ROOT / relative / "__init__.py").read_bytes())
    source = tmp_path / "src" / "probe49.py"
    source.parent.mkdir()
    source.write_text("VALUE = 49\n")
    (directory / "probe.py").write_text(
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path('src').resolve()))\n"
        "import probe49\n"
        "assert probe49.VALUE == 49\n"
        "assert sys.dont_write_bytecode is True\n"
        "assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'\n"
        "child = subprocess.check_output([sys.executable, '-S', '-c', "
        "\"import sys; sys.path.insert(0, 'src'); import probe49; "
        'assert probe49.VALUE == 49; assert sys.dont_write_bytecode"])\n'
        "assert child == b''\n"
        "print(json.dumps({'value': probe49.VALUE, 'child': 'passed'}))\n"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    result = subprocess.run(
        [sys.executable, "-S", "-m", module + ".probe"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == {"value": 49, "child": "passed"}
    expected = discovered_sources(tmp_path)
    assert "src/probe49.py" in expected
    assert not list(source.parent.rglob("*.pyc"))
    # Explicit writes remain visible: the bootstrap must not exempt bytecode.
    compiled_name = py_compile.compile(str(source), doraise=True)
    assert compiled_name is not None
    compiled = Path(compiled_name)
    relative = compiled.relative_to(tmp_path).as_posix()
    assert compiled.is_file()
    assert discovered_sources(tmp_path) - expected == {relative}


@pytest.mark.parametrize("package", [False, True])
def test_aeldari_generator_uses_the_canonical_source_loader_in_both_routes(
    package: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "path", [str(ROOT / "tools"), *sys.path])
    namespace = runpy.run_path(
        str(ROOT / "tools/generate_aeldari_datasheet_semantic_coverage.py"),
        run_name="tools.ci49_probe" if package else "ci49_probe",
    )
    owner = import_module("tools.ability_support_sources" if package else "ability_support_sources")
    assert namespace["_load_source_artifacts"] is owner.load_source_artifacts


@pytest.mark.parametrize("name", sorted(successor.CI_FORMAT_BEFORE))
def test_ci_formatting_preserves_import_bindings_and_nonimport_ast(name: str) -> None:
    record: dict[str, Any] = json.loads((ROOT / successor.CI_FORMAT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", successor.CI_FORMAT_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    if name == "scripts/check_performance_policy.py":
        ci54.admit(ROOT)
        current = ci54.previous(ROOT, name, current)
    successor.assert_ci_transition(name, before, current, record["changes"][name])
    old_tree, new_tree = ast.parse(before), ast.parse(current)
    old_imports = [n for n in old_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    new_imports = [n for n in new_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert sorted(ast.dump(n) for n in old_imports) == sorted(ast.dump(n) for n in new_imports)
    old_tree.body = [n for n in old_tree.body if n not in old_imports]
    new_tree.body = [n for n in new_tree.body if n not in new_imports]
    assert ast.dump(old_tree) == ast.dump(new_tree)


def test_ci_formatting_cannot_absorb_changed_benchmark_samples() -> None:
    name = "scripts/benchmark_order88_strength.py"
    record: dict[str, Any] = json.loads((ROOT / successor.CI_FORMAT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", successor.CI_FORMAT_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    assert current.count(b"range(5)") == 1
    changed = current.replace(b"range(5)", b"range(1)", 1)
    row = copy.deepcopy(record["changes"][name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        successor.assert_ci_transition(name, before, changed, row)


@pytest.mark.parametrize("name", sorted(successor.CI_COMPAT_BEFORE))
def test_ci_relocation_and_map_seam_match_exact_immutable_preimages(name: str) -> None:
    record: dict[str, Any] = json.loads((ROOT / successor.CI_COMPAT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", successor.CI_COMPAT_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    if name == "tools/performance_qualification_successor.py":
        ci54.admit(ROOT)
        current = ci54.previous(ROOT, name, current)
    if name in successor.CI_RUNTIME_BEFORE:
        successor.ci_comparison(ROOT, name, current)
        current = subprocess.check_output(
            ["git", "show", successor.CI_RUNTIME_BASE + ":" + name], cwd=ROOT
        )
        assert hashlib.sha256(current).hexdigest() == successor.CI_RUNTIME_BEFORE[name]
    successor.assert_ci_compatibility_transition(name, before, current, record["changes"][name])


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        (
            "tests/code_quality/__init__.py",
            b"dont_write_bytecode = True",
            b"dont_write_bytecode = False",
        ),
        ("tests/__init__.py", b"\n", b"UNREVIEWED = True\n"),
        (
            "tools/performance_qualification_successor.py",
            b"if json.loads(current) != mapping:",
            b"if False:",
        ),
    ],
)
def test_ci_relocation_rejects_unreviewed_bootstrap_or_validation_even_if_repinned(
    name: str, old: bytes, new: bytes
) -> None:
    record: dict[str, Any] = json.loads((ROOT / successor.CI_COMPAT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", successor.CI_COMPAT_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    assert current.count(old) == 1
    changed = current.replace(old, new, 1)
    row = copy.deepcopy(record["changes"][name])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        successor.assert_ci_compatibility_transition(name, before, changed, row)


def test_quality_bootstrap_historical_view_rejects_unrelated_caller_bytes() -> None:
    name = successor.QUALITY_BOOTSTRAP
    current = (ROOT / name).read_bytes()
    assert successor.static_predecessor(ROOT, name, current) == b""
    for supplied in (b"", current + b"# unreviewed\n"):
        with pytest.raises(ValueError, match="caller supplied unrelated"):
            successor.static_predecessor(ROOT, name, supplied)
