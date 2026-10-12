"""Verify D09 maintenance before applying unchanged D07 predecessor pins."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESERVATION_SHA256 = "a7d6949a94a38a31d0779bb065840b4ba3c4f344c4893debcbadc4076619f575"


def preserved_d09_predecessor_test_bytes(path: str, current: bytes) -> bytes:
    """Pin complete current bytes and independently prove original AST preservation."""
    manifest_raw = (ROOT / "data/source_audits/d09/test-preservation.json").read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest() == PRESERVATION_SHA256
    manifest = json.loads(manifest_raw)
    rows = {row["path"]: row for row in manifest["files"]}
    assert set(rows) == {
        "tests/unit/test_order97_facade_evidence.py",
        "tests/unit/test_phase13b_shooting_declarations.py",
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
        if name != pin["maintained_fixture_function"]:
            assert ast.dump(before) == ast.dump(after)
    new_other_nodes = {ast.dump(node) for node in new.body if not isinstance(node, ast.FunctionDef)}
    assert all(
        ast.dump(node) in new_other_nodes
        for node in old.body
        if not isinstance(node, ast.FunctionDef)
    )
    # D07's archival digest/assertion/decorator checks still run on their exact
    # predecessor bytes, after the complete D09 bytes and retained originals
    # have both been checked above. No D07 source, provenance or pin is rewritten.
    return original
