"""Hash-checked D02 inputs; original tests continue to exercise the live policy validator."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ASSESSMENT = "docs/performance/policy-v3/d02-final-history/assessment.json"
MAP = "docs/performance/policy-v3/d02-final-history/operation-map.json"
ORIGINAL_TEST = (
    "docs/performance/policy-v3/d02-final-history/test_d02_performance_assessment.py.txt"
)
LIVE_TEST = "tests/code_quality/test_d02_performance_assessment.py"
PINNED = {
    ASSESSMENT: "5fede0aca5404959780115897c9b8e0b70cb07719411d18a3fe912fe577c5502",
    MAP: "0b80d34a84ae30555830d97f8bf0ba7d062655725d8188495a4046ec6f92fc54",
    ORIGINAL_TEST: "150f89747eebb82281bb7ad2986de395a9a572c7a1c270a7a0e172f9a2263437",
}


def verify_d02_history(root: Path) -> None:
    for path, expected in PINNED.items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"D02 historical input bytes changed: {path}")

    def test_bodies(path: str) -> dict[str, str]:
        tree = ast.parse((root / path).read_bytes())
        return {
            node.name: ast.dump(node, include_attributes=False)
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        }

    if test_bodies(ORIGINAL_TEST) != test_bodies(LIVE_TEST):
        raise ValueError("D02 original test functions, branches or assertions changed")
