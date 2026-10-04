"""Every engine path producer/reconstructor must retain per-model M authority."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_engine_movement_path_contexts_apply_model_permission() -> None:
    checked: set[str] = set()
    violations: list[str] = []
    for path in (ROOT / "src/warhammer40k_core/engine").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "to_path_validation_context"
            ):
                continue
            checked.add(path.relative_to(ROOT).as_posix())
            keyword = parents[node]
            outer = parents[keyword]
            if not (
                isinstance(keyword, ast.keyword)
                and keyword.arg == "context"
                and isinstance(outer, ast.Call)
                and isinstance(outer.func, ast.Name)
                and outer.func.id == "model_movement_path_context"
                and any(item.arg == "model" for item in outer.keywords)
            ):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, violations
    assert checked == {
        "src/warhammer40k_core/engine/base_contact_fight_history.py",
        "src/warhammer40k_core/engine/charge_path_contexts.py",
        "src/warhammer40k_core/engine/consolidation_model_constraints.py",
        "src/warhammer40k_core/engine/fight_movement_paths.py",
        "src/warhammer40k_core/engine/fight_movement_source.py",
        "src/warhammer40k_core/engine/phases/movement_resolvers.py",
        "src/warhammer40k_core/engine/scout_movement_paths.py",
        "src/warhammer40k_core/engine/triggered_movement_resolution.py",
    }
