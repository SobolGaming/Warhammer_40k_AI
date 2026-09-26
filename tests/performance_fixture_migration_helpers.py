"""Exact fixture-only migrations for retained Order 80/86 performance baselines."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assert_order87_fixture_migration(
    base: dict[str, str], head: dict[str, str], *, changed_file: str
) -> None:
    migration = json.loads(
        (ROOT / "docs/performance/order87/inherited-fixture-migration.json").read_text()
    )["changed_files"][changed_file]
    assert base.keys() == head.keys()
    assert base[changed_file] == migration["base_sha256"]
    assert head[changed_file] == migration["head_sha256"]
    assert {name: digest for name, digest in base.items() if name != changed_file} == {
        name: digest for name, digest in head.items() if name != changed_file
    }
    tree = ast.parse((ROOT / changed_file).read_text())
    if changed_file == "tests/normal_move_occurrence_helpers.py":
        added_import = next(
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "warhammer40k_core.core.army_catalog"
        )
        assert ast.dump(added_import) == ast.dump(
            ast.parse("from warhammer40k_core.core.army_catalog import ArmyCatalog").body[0]
        )
        tree.body.remove(added_import)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "reaction_session"
        )
        assert function.args.kwonlyargs[-1].arg == "catalog"
        default = function.args.kw_defaults[-1]
        assert default is not None
        assert ast.dump(default) == "Constant(value=None)"
        function.args.kwonlyargs.pop()
        function.args.kw_defaults.pop()
        call = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "fight_lifecycle"
        )
        keyword = next(item for item in call.keywords if item.arg == "catalog")
        assert ast.dump(keyword.value) == "Name(id='catalog', ctx=Load())"
        call.keywords.remove(keyword)
        measurement = ast.parse((ROOT / "scripts/measure_order80.py").read_text())
        calls = [
            node
            for node in ast.walk(measurement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reaction_session"
        ]
        assert calls
        assert all(not any(k.arg == "catalog" for k in call.keywords) for call in calls)
    else:
        assert changed_file == "tests/phase11c_command_phase_helpers.py"
        changed_functions: list[str] = []
        for function_node in tree.body:
            if not isinstance(function_node, ast.FunctionDef):
                continue
            changes = [
                node
                for node in ast.walk(function_node)
                if isinstance(node, ast.Attribute) and node.attr == "current_wounds"
            ]
            if changes:
                changed_functions.append(function_node.name)
                assert len(changes) == 1
                changes[0].attr = "wounds_remaining"
        assert changed_functions == [
            "remove_first_models",
            "destroy_models_with_recorded_mortal_wounds",
        ]
        # The measured operation constructs an undamaged squad and queries its quarter.
        measurement = ast.parse((ROOT / "scripts/measure_order86.py").read_text())
        assert not any(
            isinstance(node, ast.Name) and node.id in changed_functions
            for node in ast.walk(measurement)
        )
    assert (
        hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
        == migration["baseline_module_ast_sha256"]
    )
