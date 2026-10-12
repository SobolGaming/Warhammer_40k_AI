"""Physical-copy authority and complete original evidence preservation."""

import ast
import json
from pathlib import Path

from tests.d10_test_preservation_helpers import preserved_d10_predecessor_test_bytes

ROOT = Path(__file__).resolve().parents[2]


def test_duplicate_guard_uses_authenticated_physical_copy_before_profile_consumers() -> None:
    source = ROOT / "src/warhammer40k_core/engine/phases/shooting_declaration_validation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_attack_pools_or_validation"
    )
    loop = next(node for node in owner.body if isinstance(node, ast.For))
    statements = [ast.unparse(node) for node in loop.body]
    lookup = next(
        i
        for i, node in enumerate(statements)
        if node.startswith("weapon = available_weapon_by_key.get(key)")
    )
    unavailable = next(
        i for i, node in enumerate(statements) if node.startswith("if weapon is None:")
    )
    guard = next(
        i
        for i, node in enumerate(statements)
        if node.startswith("if weapon['weapon_instance_id'] in seen_weapon_instance_ids:")
    )
    record = statements.index("seen_weapon_instance_ids.add(weapon['weapon_instance_id'])")
    profile = statements.index("weapon_profile = weapon['weapon_profile']")
    assert lookup < unavailable < guard < record < profile
    assert "duplicate_weapon_declaration" in statements[guard]
    assert "weapon_profile_id" not in statements[guard]
    assert "CTAN_POWER" not in statements[guard]
    for name in (
        "_validate_declaration_submission",
        "_validate_out_of_phase_declaration_submission",
    ):
        validator = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_attack_pools_or_validation"
            for node in ast.walk(validator)
        )


def test_complete_original_tests_keep_assertions_decorators_and_unrelated_ast() -> None:
    manifest = json.loads((ROOT / "data/source_audits/d10/test-preservation.json").read_bytes())
    assert manifest["base"] == "53256c54bf9b34596ac2247ca27622d9b8480af6"
    assert manifest["source_row_id"] == "rule:04:04.01.03:1"
    assert manifest["runtime_compatibility_shim"] is False
    for row in manifest["files"]:
        original = preserved_d10_predecessor_test_bytes(
            row["path"], (ROOT / row["path"]).read_bytes()
        )
        assert original == (ROOT / row["baseline_archive"]).read_bytes()
