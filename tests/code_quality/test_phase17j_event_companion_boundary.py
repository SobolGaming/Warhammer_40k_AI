from __future__ import annotations

import ast
from pathlib import Path

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
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and any(token in node.value for token in _FORBIDDEN_EVENT_RAW_TOKENS)
            ):
                violations.append(f"{source_path}: references raw Event Companion source")

    assert not violations


def _runtime_python_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for root in _RUNTIME_ROOTS
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )
