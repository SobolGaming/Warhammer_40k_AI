from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from warhammer40k_core import __version__, build_identity

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "warhammer40k_core"
MANIFEST_PATH = PACKAGE_ROOT / "_engine_build_manifest.json"
GENERATOR_PATH = ROOT / "scripts" / "build_engine_build_identity.py"


@dataclass(frozen=True, slots=True)
class _TestAuthoritativeResource:
    logical_path: str
    content: bytes


def test_current_engine_build_id_is_a_verified_runtime_tree_fingerprint() -> None:
    identity = build_identity.verified_engine_build_identity()
    build_id = build_identity.current_engine_build_id()
    match = re.fullmatch(
        rf"{re.escape(build_identity.ENGINE_BUILD_ID_PREFIX)}(?P<fingerprint>[0-9a-f]{{64}})",
        build_id,
    )

    assert match is not None
    assert build_id == identity.build_id
    assert match.group("fingerprint") == identity.fingerprint
    assert identity.algorithm == build_identity.ENGINE_BUILD_FINGERPRINT_ALGORITHM
    assert identity.schema_version == build_identity.ENGINE_BUILD_MANIFEST_SCHEMA_VERSION
    assert identity.resource_count > 0
    assert build_id != f"warhammer40k-core-v2:{__version__}"


def test_generated_engine_build_manifest_is_current_and_covers_runtime_resources() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    expected = build_identity.build_engine_manifest_payload()
    expected_paths = _expected_authoritative_resource_paths()

    assert manifest == expected
    assert manifest_text == build_identity.canonical_engine_build_manifest_text(expected)
    assert manifest["resource_count"] == len(manifest["resources"])
    assert [resource["path"] for resource in manifest["resources"]] == list(expected_paths)
    assert "warhammer40k_core/py.typed" in expected_paths
    assert any(path.startswith("warhammer40k_core/contracts/schemas/") for path in expected_paths)


def test_engine_build_manifest_generator_check_mode_passes() -> None:
    completed = subprocess.run(
        (sys.executable, str(GENERATOR_PATH), "--check"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "Engine build identity is current:" in completed.stdout


@pytest.mark.stubbed
def test_same_package_version_with_different_source_content_has_different_build_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_version = __version__
    logical_path = "warhammer40k_core/example_runtime.py"
    first_resources = (
        _TestAuthoritativeResource(
            logical_path=logical_path,
            content=b"RUNTIME_RULE = 1\n",
        ),
    )
    second_resources = (
        _TestAuthoritativeResource(
            logical_path=logical_path,
            content=b"RUNTIME_RULE = 2\n",
        ),
    )

    monkeypatch.setattr(build_identity, "_authoritative_resources", lambda: first_resources)
    first = build_identity.build_engine_manifest_payload()
    monkeypatch.setattr(build_identity, "_authoritative_resources", lambda: second_resources)
    second = build_identity.build_engine_manifest_payload()

    assert __version__ == package_version
    assert first["algorithm"] == second["algorithm"]
    assert first["build_id"].startswith(build_identity.ENGINE_BUILD_ID_PREFIX)
    assert second["build_id"].startswith(build_identity.ENGINE_BUILD_ID_PREFIX)
    assert first["build_id"] != f"warhammer40k-core-v2:{package_version}"
    assert second["build_id"] != f"warhammer40k-core-v2:{package_version}"
    assert first["fingerprint"] != second["fingerprint"]
    assert first["build_id"] != second["build_id"]


def test_engine_build_id_assignments_use_the_central_verified_api() -> None:
    assignments: list[Path] = []
    violations: list[str] = []
    central_module = PACKAGE_ROOT / "build_identity.py"
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path == central_module:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            value: ast.expr | None = None
            target_names: tuple[str, ...] = ()
            if isinstance(node, ast.Assign):
                value = node.value
                target_names = tuple(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                value = node.value
                target_names = (node.target.id,)
            if "ENGINE_BUILD_ID" not in target_names:
                continue
            assignments.append(path)
            if not _is_verified_build_id_call(value):
                violations.append(
                    f"{path.relative_to(ROOT).as_posix()}: ENGINE_BUILD_ID must come from "
                    "current_engine_build_id()"
                )

    assert assignments, "The audit must cover the adapter build-identity constants."
    assert not violations, "\n".join(violations)


def _expected_authoritative_resource_paths() -> tuple[str, ...]:
    paths: set[str] = set()
    for path in PACKAGE_ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative_path = path.relative_to(PACKAGE_ROOT)
        if relative_path.as_posix() == "_engine_build_manifest.json":
            continue
        if path.name == "py.typed" or path.suffix in {".json", ".py"}:
            paths.add(f"warhammer40k_core/{relative_path.as_posix()}")
    source_schema_root = ROOT / "contracts" / "schemas"
    for path in source_schema_root.rglob("*"):
        if path.is_file():
            relative_path = path.relative_to(source_schema_root)
            paths.add(f"warhammer40k_core/contracts/schemas/{relative_path.as_posix()}")
    return tuple(sorted(paths))


def _is_verified_build_id_call(value: ast.expr | None) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "current_engine_build_id"
        and not value.args
        and not value.keywords
    )
