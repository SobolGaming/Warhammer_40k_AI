from __future__ import annotations

import ast
from functools import cache
from pathlib import Path


@cache
def source_for(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@cache
def ast_for(path: Path) -> ast.Module:
    return ast.parse(source_for(path), filename=str(path))


@cache
def combined_source_for(paths: tuple[Path, ...]) -> str:
    return "\n".join(source_for(path) for path in paths)


@cache
def function_sources_for(paths: tuple[Path, ...]) -> dict[str, str]:
    functions: dict[str, str] = {}
    for path in paths:
        module_source = source_for(path)
        for node in ast_for(path).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            function_source = ast.get_source_segment(module_source, node)
            if function_source is None:
                raise AssertionError(f"Function {node.name} has no source segment in {path}.")
            functions[node.name] = function_source
    return functions


def function_source_for(paths: tuple[Path, ...], function_name: str) -> str:
    functions = function_sources_for(paths)
    if function_name not in functions:
        raise AssertionError(f"Function {function_name} not found.")
    return functions[function_name]


@cache
def python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.py"), key=lambda path: path.as_posix()))
