"""D06 preserves the existing ownership and mutation authority."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data/source_audits/d06"
OWNER = ROOT / "src/warhammer40k_core/engine/transport_embark_validation.py"


def _functions(path: Path) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
    }


def test_d06_preserves_original_ownership_setup_capacity_and_atomic_resolution() -> None:
    provenance = json.loads((ARCHIVE / "provenance.json").read_text(encoding="utf-8"))
    for name, digest in provenance["archives"].items():
        assert hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest
    old = _functions(ARCHIVE / "baseline-embark-validation.py.txt")
    new = _functions(OWNER)
    for name in ("resolve_embark", "embark_after_setup_forbidden"):
        assert ast.dump(old[name], include_attributes=False) == ast.dump(
            new[name], include_attributes=False
        )
    assert not provenance["original_tests_assertions_archives_or_budgets_changed"]
    assert provenance["FRAME_native_applicability"].startswith("UNPROVEN")


def test_d06_offer_selection_and_source_continuation_retain_one_resolver() -> None:
    consumers = {
        "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": 2,
        "src/warhammer40k_core/engine/transport_source_embark.py": 1,
    }
    for name, expected in consumers.items():
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "resolve_embark"
        ]
        assert len(calls) == expected
        assert all(
            {"scenario", "selection", "cargo_state", "unit_placement", "transport_placement"}
            <= {keyword.arg for keyword in call.keywords}
            for call in calls
        )
