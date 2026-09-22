from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_ROOTS = (
    _ROOT / "src" / "warhammer40k_core" / "core",
    _ROOT / "src" / "warhammer40k_core" / "engine",
    _ROOT / "src" / "warhammer40k_core" / "geometry",
)
_FORBIDDEN_PDF_IMPORTS = frozenset(("pypdf", "PyPDF2", "pdfminer", "fitz"))
_FORBIDDEN_EVENT_RAW_TOKENS = frozenset(
    (
        "event_rules",
        "terrain_footprints",
        "eng_12-06_warhammer40000_event_companion",
        "eng_12-06_warhammer40000_terrainareafootprints",
        ".pdf",
    )
)


def test_phase17j_runtime_does_not_parse_event_companion_pdf_text_or_images() -> None:
    violations: list[str] = []
    for source_path in _runtime_python_files():
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".", 1)[0]
                    if root_name in _FORBIDDEN_PDF_IMPORTS:
                        violations.append(f"{source_path}: imports {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                root_name = node.module.split(".", 1)[0]
                if root_name in _FORBIDDEN_PDF_IMPORTS:
                    violations.append(f"{source_path}: imports {node.module}")
        violations.extend(
            f"{source_path}: references raw Event Companion source"
            for _ in _raw_source_literals(tree)
        )

    assert not violations


def _raw_source_literals(tree: ast.Module) -> tuple[ast.Constant, ...]:
    documentation: set[ast.Constant] = set()
    for scope in ast.walk(tree):
        if not isinstance(
            scope, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        if not scope.body:
            continue
        first = scope.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            documentation.add(first.value)
    # A mathematics PDF citation in documentation is not runtime ingestion.
    # Explicit Event Companion source tokens remain forbidden even in docstrings;
    # all executable PDF strings and the parser-import checks remain protected.
    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(
            token in node.value and (token != ".pdf" or node not in documentation)
            for token in _FORBIDDEN_EVENT_RAW_TOKENS
        )
    )


@pytest.mark.parametrize(
    ("source", "forbidden"),
    [
        ('"https://example.org/mathematics.pdf"', False),
        ('def proof():\n    "https://example.org/mathematics.pdf"', False),
        ('async def proof():\n    "https://example.org/mathematics.pdf"', False),
        ('class Proof:\n    "https://example.org/mathematics.pdf"', False),
        ('SOURCE = "https://example.org/mathematics.pdf"', True),
        ('def proof():\n    return "https://example.org/mathematics.pdf"', True),
        ('def proof():\n    pass\n    "https://example.org/mathematics.pdf"', True),
        ('"eng_12-06_warhammer40000_event_companion.pdf"', True),
        ('def proof():\n    "terrain_footprints"', True),
    ],
)
def test_pdf_source_audit_distinguishes_citations_from_runtime_references(
    source: str, forbidden: bool
) -> None:
    assert bool(_raw_source_literals(ast.parse(source))) is forbidden


def _runtime_python_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for root in _RUNTIME_ROOTS
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )
