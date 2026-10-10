"""The prerequisite preserves original guards, assertions and archived source."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data/source_audits/physical-history-restore"


def _functions(path: Path) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
    }


def test_scoring_anchor_extraction_preserves_authentication_body_and_archive_hashes() -> None:
    provenance = json.loads((ARCHIVE / "provenance.json").read_text(encoding="utf-8"))
    for name, digest in provenance["archives"].items():
        assert hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest
    original = _functions(ARCHIVE / "baseline-physical-authority.py.txt")
    extracted = _functions(ROOT / "src/warhammer40k_core/engine/primary_scoring_physical_anchor.py")
    old = original["_authenticated_scoring_commit_checkpoint"]
    new = extracted["authenticated_scoring_commit_checkpoint"]
    assert ast.dump(old.args, include_attributes=False) == ast.dump(
        new.args, include_attributes=False
    )
    assert [ast.dump(node, include_attributes=False) for node in old.body] == [
        ast.dump(node, include_attributes=False) for node in new.body
    ]
    assert provenance["original_assertion_changes"] == []
    assert not provenance["original_budgets_changed"]


def test_prior_command_history_regression_bodies_are_preserved() -> None:
    original = _functions(ARCHIVE / "baseline-off-battlefield-command-tests.py.txt")
    current = _functions(ROOT / "tests/integration/test_off_battlefield_command_battle_shock.py")
    for name, body in original.items():
        assert ast.dump(body, include_attributes=False) == ast.dump(
            current[name], include_attributes=False
        )
