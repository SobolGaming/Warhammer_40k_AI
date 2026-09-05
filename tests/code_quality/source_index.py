from __future__ import annotations

import ast
import re
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
        # AST columns are UTF-8 byte offsets; split only Python physical newlines.
        # ast.get_source_segment re-splits the entire file for every function.
        lines = re.split(rb"(?<=\n)|(?<=\r)(?!\n)", source_for(path).encode("utf-8"))
        for node in ast_for(path).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.end_lineno is None or node.end_col_offset is None:
                raise AssertionError(f"Function {node.name} has no source segment in {path}.")
            first, last = node.lineno - 1, node.end_lineno - 1
            if first == last:
                segment = lines[first][node.col_offset : node.end_col_offset]
            else:
                segment = (
                    lines[first][node.col_offset :]
                    + b"".join(lines[first + 1 : last])
                    + lines[last][: node.end_col_offset]
                )
            functions[node.name] = segment.decode("utf-8")
    return functions


def function_source_for(paths: tuple[Path, ...], function_name: str) -> str:
    functions = function_sources_for(paths)
    if function_name not in functions:
        raise AssertionError(f"Function {function_name} not found.")
    return functions[function_name]


@cache
def python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.py"), key=lambda path: path.as_posix()))
