"""Authenticate narrow D10 fixture maintenance before unchanged historical pins."""

import ast
import hashlib
import json
from pathlib import Path

from tests.s25_test_preservation_helpers import preserved_s25_predecessor_test_bytes

ROOT = Path(__file__).resolve().parents[1]
PRESERVATION_SHA256 = "c06f024250834310afaa16871f5d6be826e62aed100e06d40d05acf3d55f26ec"


def preserved_d10_predecessor_test_bytes(path: str, current: bytes) -> bytes:
    current = preserved_s25_predecessor_test_bytes(path, current)
    manifest_raw = (ROOT / "data/source_audits/d10/test-preservation.json").read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest() == PRESERVATION_SHA256
    rows = {row["path"]: row for row in json.loads(manifest_raw)["files"]}
    assert set(rows) == {
        "tests/unit/test_order97_attack_evidence.py",
        "tests/unit/test_phase13b_shooting_phase_declarations.py",
    }
    if path not in rows:
        return current
    pin = rows[path]
    assert hashlib.sha256(current).hexdigest() == pin["after_sha256"]
    archive_path = pin["baseline_archive"]
    assert isinstance(archive_path, str)
    original = (ROOT / archive_path).read_bytes()
    assert hashlib.sha256(original).hexdigest() == pin["before_sha256"]
    old = ast.parse(original)
    new = ast.parse(current)
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
    assert list(old_functions) == pin["original_functions"]
    assert old_functions.keys() <= new_functions.keys()
    assert sorted(new_functions.keys() - old_functions.keys()) == pin["added_functions"]
    for name, before in old_functions.items():
        after = new_functions[name]
        assert [ast.dump(node) for node in before.decorator_list] == [
            ast.dump(node) for node in after.decorator_list
        ]
        assert [ast.dump(node) for node in ast.walk(before) if isinstance(node, ast.Assert)] == [
            ast.dump(node) for node in ast.walk(after) if isinstance(node, ast.Assert)
        ]
        binding = pin["setup_catalog_rebindings"].get(name)
        if binding is not None:
            first = before.body[0]
            assert isinstance(first, ast.Assign)
            assert isinstance(first.value, ast.Call)
            assert isinstance(first.value.func, ast.Name)
            assert first.value.func.id == binding["before_factory"]
            first.value.func.id = binding["after_factory"]
            assert ast.dump(before) == ast.dump(after)
        elif name != pin["maintained_fixture_function"]:
            assert ast.dump(before) == ast.dump(after)

    # Formatting may coalesce imports; preserve every original module/name/alias
    # and every original non-import/non-function statement without substitution.
    def imports(tree: ast.Module) -> set[str]:
        return {
            repr(
                (
                    type(node).__name__,
                    node.module if isinstance(node, ast.ImportFrom) else None,
                    node.level if isinstance(node, ast.ImportFrom) else 0,
                    alias.name,
                    alias.asname,
                )
            )
            for node in tree.body
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }

    assert imports(old) <= imports(new)
    new_other = {
        ast.dump(node)
        for node in new.body
        if not isinstance(node, ast.FunctionDef | ast.Import | ast.ImportFrom)
    }
    assert all(
        ast.dump(node) in new_other
        for node in old.body
        if not isinstance(node, ast.FunctionDef | ast.Import | ast.ImportFrom)
    )
    return original
