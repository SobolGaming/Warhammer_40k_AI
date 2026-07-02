from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = [ROOT / "src", ROOT / "tests"]
ENGINE_DIR = ROOT / "src" / "warhammer40k_core" / "engine"
DEFAULT_RETURN_DOMAIN_ERRORS = frozenset({"PlacementError"})
EMPTY_DEFAULT_CALLS = frozenset({"dict", "frozenset", "list", "set", "tuple"})

# Add exact "relative/path.py:function_name:line" entries only after review.
ALLOWLIST: set[str] = set()


def _python_files() -> list[Path]:
    files: list[Path] = []
    for source_dir in SOURCE_DIRS:
        if source_dir.exists():
            files.extend(source_dir.rglob("*.py"))
    return sorted(files)


def _function_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
            return parent.name
        parent = parents.get(parent)
    return "<module>"


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def test_no_broad_exceptions() -> None:
    violations: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = _parent_map(tree)
        rel = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue

            is_bare = node.type is None
            is_exception = isinstance(node.type, ast.Name) and node.type.id in {
                "Exception",
                "BaseException",
            }

            if not (is_bare or is_exception):
                continue

            key = f"{rel}:{_function_name(node, parents)}:{node.lineno}"
            if key not in ALLOWLIST:
                violations.append(key)

    assert not violations, "Broad exception handlers are forbidden:\n" + "\n".join(violations)


def test_no_except_pass_blocks() -> None:
    violations: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = _parent_map(tree)
        rel = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if any(isinstance(stmt, ast.Pass) for stmt in node.body):
                violations.append(f"{rel}:{_function_name(node, parents)}:{node.lineno}")

    assert not violations, "`except: pass` / `except ...: pass` is forbidden:\n" + "\n".join(
        violations
    )


def test_multi_exception_handlers_are_parenthesized() -> None:
    violations: list[str] = []

    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        tokens = tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
        in_except = False
        depth = 0

        for token in tokens:
            if token.type == tokenize.NAME and token.string == "except":
                in_except = True
                depth = 0
                continue

            if not in_except:
                continue

            if token.type == tokenize.OP:
                if token.string in {"(", "[", "{"}:
                    depth += 1
                elif token.string in {")", "]", "}"}:
                    depth -= 1
                elif token.string == ":" and depth == 0:
                    in_except = False
                elif token.string == "," and depth == 0:
                    violations.append(f"{rel}:{token.start[0]}")
                    in_except = False

    assert not violations, (
        "Multi-exception handlers must use tuple parentheses so the source remains "
        "syntax-compatible with Python 3.13 parsers:\n" + "\n".join(violations)
    )


def test_no_placement_error_default_fallback_handlers_in_engine() -> None:
    violations: list[str] = []

    for path in sorted(ENGINE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = _parent_map(tree)
        rel = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _handler_error_name(node) not in DEFAULT_RETURN_DOMAIN_ERRORS:
                continue
            if _is_default_fallback_handler(node):
                violations.append(f"{rel}:{_function_name(node, parents)}:{node.lineno}")

    assert not violations, (
        "PlacementError handlers must not return empty/false/none defaults or continue. "
        "Use BattlefieldRuntimeState presence-query APIs for legal absence, and let "
        "corrupted state raise through typed domain errors:\n" + "\n".join(violations)
    )


def _handler_error_name(node: ast.ExceptHandler) -> str | None:
    if isinstance(node.type, ast.Name):
        return node.type.id
    if isinstance(node.type, ast.Attribute):
        return node.type.attr
    return None


def _is_default_fallback_handler(node: ast.ExceptHandler) -> bool:
    if len(node.body) != 1:
        return False
    statement = node.body[0]
    if isinstance(statement, ast.Continue):
        return True
    if not isinstance(statement, ast.Return):
        return False
    return _is_default_return_value(statement.value)


def _is_default_return_value(value: ast.expr | None) -> bool:
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False}
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    if (
        isinstance(value, ast.Call)
        and not value.args
        and not value.keywords
        and isinstance(value.func, ast.Name)
    ):
        return value.func.id in EMPTY_DEFAULT_CALLS
    return False
