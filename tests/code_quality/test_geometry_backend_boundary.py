from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "warhammer40k_core"
SHAPELY_BACKEND = PACKAGE / "geometry" / "shapely_backend.py"


def test_shapely_imports_stay_inside_private_backend() -> None:
    violations: list[str] = []

    for path in sorted(PACKAGE.rglob("*.py")):
        if path == SHAPELY_BACKEND:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "shapely" or alias.name.startswith("shapely."):
                        violations.append(f"{rel}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module is not None and (module == "shapely" or module.startswith("shapely.")):
                    violations.append(f"{rel}:{node.lineno} imports {module}")
            elif isinstance(node, ast.Call) and _imports_shapely_dynamically(node):
                violations.append(f"{rel}:{node.lineno} dynamically imports shapely")

    assert not violations, "Shapely must stay behind geometry/shapely_backend.py:\n" + "\n".join(
        violations
    )


def _imports_shapely_dynamically(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "import_module":
        return False
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return False
    module_name = node.args[0].value
    return type(module_name) is str and (
        module_name == "shapely" or module_name.startswith("shapely.")
    )
