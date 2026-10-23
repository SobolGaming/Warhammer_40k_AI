"""Fresh immutable batching preserves the original member and control decisions."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from tools import cumulative_preservation as cumulative
from tools import performance_preflight_successor as stage
from tools import performance_qualification_successor as qualification
from tools.performance_tool_inputs import digest

ROOT = Path(__file__).resolve().parents[2]
OWNER = "tools/cumulative_preservation.py"


class _GitAccess(Protocol):
    def _git(self, root: Path, *args: str) -> bytes: ...

    def function(self) -> Callable[..., bytes]:
        return self._git


def test_integration_batch_matches_original_function_members_and_control_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = subprocess.check_output(
        ["git", "show", stage.CI_TRANSPORT_BASE + ":" + OWNER], cwd=ROOT
    )
    assert hashlib.sha256(before).hexdigest() == stage.CI_TRANSPORT_BEFORE[OWNER]
    original_git = _GitAccess.function(cast(_GitAccess, cumulative))
    original_blobs = stage.read_frozen_blobs
    original_successor = qualification.expected_source
    original_controls = cumulative.reviewed_control_hashes
    boundaries: list[int] = []
    individual: list[tuple[str, bytes]] = []
    batches: list[tuple[list[str], dict[str, bytes]]] = []
    inputs: list[dict[str, str]] = []
    prefix = str(cumulative.SOURCE_COMMIT) + ":"

    def observe_git(root: Path, *args: str) -> bytes:
        result = original_git(root, *args)
        if len(args) == 2 and args[0] == "show" and args[1].startswith(prefix):
            individual.append((args[1][len(prefix) :], result))
        return result

    def observe_controls(root: Path) -> dict[str, str]:
        result = original_controls(root)
        boundaries.append(len(individual))
        return result

    def observe_blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
        result = original_blobs(root, revision, names)
        if revision == cumulative.SOURCE_COMMIT:
            batches.append((list(names), result))
        return result

    def observe_successor(root: Path, previous: dict[str, str]) -> dict[str, str]:
        inputs.append(dict(previous))
        return original_successor(root, previous)

    monkeypatch.setattr(cumulative, "_git", observe_git)
    monkeypatch.setattr(cumulative, "reviewed_control_hashes", observe_controls)
    monkeypatch.setattr(stage, "read_frozen_blobs", observe_blobs)
    monkeypatch.setattr(qualification, "expected_source", observe_successor)
    functions: list[ast.stmt] = [
        node
        for node in ast.parse(before).body
        if isinstance(node, ast.FunctionDef) and node.name == "expected_source"
    ]
    assert len(functions) == 1
    namespace = dict(vars(cumulative))
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "immutable-599-owner", "exec"),
        namespace,
    )
    original = cast(Callable[[Path], dict[str, str]], namespace["expected_source"])
    expected = original(ROOT)
    assert len(boundaries) == 1
    members = individual[boundaries[0] :]
    assert len(members) == 83
    actual = cumulative.expected_source(ROOT)
    assert actual == expected
    assert len(boundaries) == 2
    assert individual[boundaries[1] :] == []
    assert batches == [([name for name, _ in members], dict(members))]
    assert len(inputs) == 2
    assert inputs[0] == inputs[1]
    controls = original_controls(ROOT)
    accepted: dict[str, str] = json.loads(
        (ROOT / cumulative.NAMESPACE / "accepted-source.json").read_bytes()
    )
    assert digest(accepted) == cumulative.SOURCE_ID
    reconstructed = accepted | {
        name: controls.get(name, hashlib.sha256(raw).hexdigest()) for name, raw in members
    }
    assert inputs == [reconstructed, reconstructed]
    member_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in members}
    overrides = controls.keys() & member_hashes.keys()
    assert overrides == {
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_d07_upper_floor_preservation.py",
        "tests/code_quality/test_performance_category_migration.py",
        OWNER,
    }
    assert {name for name in overrides if controls[name] != member_hashes[name]} == {
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_performance_category_migration.py",
        OWNER,
    }


def test_immutable_batch_rereads_and_rejects_actual_object_tamper(tmp_path: Path) -> None:
    def git(*args: str, payload: bytes | None = None) -> bytes:
        return subprocess.check_output(["git", *args], cwd=tmp_path, input=payload, timeout=10)

    git("init", "--quiet")
    oid = git("hash-object", "-w", "--stdin", payload=b"before").decode().strip()
    tree = git("mktree", payload=f"100644 blob {oid}\tmember.py\n".encode()).decode().strip()
    revision = (
        git(
            "-c",
            "user.name=probe",
            "-c",
            "user.email=probe@example.invalid",
            "commit-tree",
            tree,
            "-m",
            "owned immutable transport probe",
        )
        .decode()
        .strip()
    )
    blobs = stage.read_frozen_blobs
    assert blobs(tmp_path, revision, ["member.py"]) == {"member.py": b"before"}
    object_path = tmp_path / ".git" / "objects" / oid[:2] / oid[2:]
    object_path.rename(object_path.with_name(object_path.name + ".original"))
    object_path.write_bytes(zlib.compress(b"blob 6\0edited"))
    with pytest.raises(ValueError, match="bytes differ from the selected object"):
        blobs(tmp_path, revision, ["member.py"])


@pytest.mark.parametrize("name", sorted(stage.CI_TRANSPORT_BEFORE))
def test_transport_proof_preserves_exact_immutable_preimage(name: str) -> None:
    record: dict[str, Any] = json.loads((ROOT / stage.CI_TRANSPORT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", stage.CI_TRANSPORT_BASE + ":" + name], cwd=ROOT
    )
    current = (ROOT / name).read_bytes()
    if name in stage.CI_RUNTIME_BEFORE:
        stage.ci_comparison(ROOT, name, current)
        current = subprocess.check_output(
            ["git", "show", stage.CI_RUNTIME_BASE + ":" + name], cwd=ROOT
        )
        assert hashlib.sha256(current).hexdigest() == stage.CI_RUNTIME_BEFORE[name]
    stage.assert_ci_transport_transition(name, before, current, record["changes"][name])


def test_transport_proof_cannot_drop_control_overrides_even_if_repinned() -> None:
    record: dict[str, Any] = json.loads((ROOT / stage.CI_TRANSPORT_RECORD).read_bytes())
    before = subprocess.check_output(
        ["git", "show", stage.CI_TRANSPORT_BASE + ":" + OWNER], cwd=ROOT
    )
    current = (ROOT / OWNER).read_bytes()
    stage.ci_comparison(ROOT, OWNER, current)
    current = subprocess.check_output(
        ["git", "show", stage.CI_RUNTIME_BASE + ":" + OWNER], cwd=ROOT
    )
    assert hashlib.sha256(current).hexdigest() == stage.CI_RUNTIME_BEFORE[OWNER]
    stage.assert_ci_transport_transition(OWNER, before, current, record["changes"][OWNER])
    expression = b"controls.get(name, _sha(raw))"
    assert current.count(expression) == 1
    changed = current.replace(expression, b"_sha(raw)", 1)
    row = copy.deepcopy(record["changes"][OWNER])
    row["after_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        stage.assert_ci_transport_transition(OWNER, before, changed, row)


def test_integration_batch_rejects_duplicate_member_selection() -> None:
    with pytest.raises(ValueError, match="unique members"):
        stage.read_frozen_blobs(ROOT, str(cumulative.SOURCE_COMMIT), [OWNER, OWNER])
