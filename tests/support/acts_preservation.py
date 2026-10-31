"""Exact additive Acts regression projection for immutable migrated history."""

import ast
import hashlib
from pathlib import Path

TEST_PATH = "tests/infrastructure/runtime_hooks/unit/test_runtime_hook_bindings.py"
ARCHIVE = "docs/performance/policy-v3/acts-provenance-20261031/runtime-hook-predecessor.py.txt"
BEFORE_SHA256 = "2097b78ccf59d264f9dfdba560697c84984afa0b7ad61c4ae18d208f1435a0a2"
ADDITIONS = {
    "test_acts_of_faith_uses_turn_start_and_preserves_triumph_round_hook": (
        "b28524bd68b3fd2555e50c7d38e463ff1d442c6f59231012e47d77d3cb805bf8"
    ),
    "test_acts_of_faith_turn_transition_duplicate_restore_and_replay": (
        "07c17133418c5d37e50f49b183af7516777700a7a994f2cc12f04de65d8cbc77"
    ),
    "test_acts_turn_candidates_preserve_spend_destruction_and_source_deduplication": (
        "77f91475030af4ebd8eebb4dccd46d9e349ed91167017b554601676b7a8a2d46"
    ),
    "test_acts_actual_casualty_and_native_combat_replay": (
        "46cd0bb285159916ad05a26536e01245fe1920317809d19e461865d9e4375272"
    ),
    "test_destruction_keyword_predicate_uses_canonical_retained_physical_models": (
        "634d3c6aa10b6c2e6056c7aea78260fde958240ba76155fd1a892014f8c94116"
    ),
}


def acts_predecessor(root: Path, path: str, current: bytes) -> bytes:
    if path != TEST_PATH:
        return current
    target = root / ARCHIVE
    if target.is_symlink() or not target.is_file():
        raise ValueError("Acts predecessor must be a regular retained file.")
    before = target.read_bytes()
    if hashlib.sha256(before).hexdigest() != BEFORE_SHA256:
        raise ValueError("Acts original predecessor bytes drifted.")
    tree = ast.parse(current)
    retained: list[ast.stmt] = []
    observed: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ADDITIONS:
            if node.name in observed:
                raise ValueError("Acts additive regression duplicated.")
            observed[node.name] = hashlib.sha256(ast.dump(node).encode()).hexdigest()
        else:
            retained.append(node)
    if observed != ADDITIONS:
        raise ValueError("Acts exact additive regression assertions changed.")
    tree.body = retained
    if ast.dump(tree) != ast.dump(ast.parse(before)):
        raise ValueError("Acts original assertions or module initialization changed.")
    return before


PROVENANCE_ARCHIVE = (
    "docs/performance/policy-v3/acts-provenance-20261031/source-scope-predecessor.py.txt"
)
PROVENANCE_BEFORE_SHA256 = "ae603f64b1b154f785ac33735c63bc62c8167d9e5e150268c3c08debf7aa14fd"
PROVENANCE_AFTER_SHA256 = "40ef539dc75aa669df54a099d7788b74ca68453c7ae18a1e009194c48a42f64a"
PROVENANCE_ADDITIONS = (
    (
        b"# No overlay is added by the Acts timing repair. Only its exact comparison\n"
        b"# documents contain the independently authenticated historical input paths.\n"
        b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE,)\n"
        b"\n"
        b"\n"
    ),
    (
        b"    for base in COMPARISON_ONLY_SCOPE_BASES:\n"
        b"        scope = scopes.registered_scope(base)\n"
        b'        record = ProvenanceRecord(base, "", "", "", "", ())\n'
        b"        for context in (scope.spec_path, scope.report_path):\n"
        b"            if context in contexts:\n"
        b'                raise ValueError("Registered provenance contexts must be unique.")\n'
        b"            contexts[context] = (record, scope)\n"
    ),
)


def acts_provenance_predecessor(root: Path, current: bytes) -> bytes:
    """Retain the exact historical helper under its finite comparison-only addition."""
    target = root / PROVENANCE_ARCHIVE
    error = "Exact registered edition provenance inputs changed."
    if target.is_symlink() or not target.is_file():
        raise ValueError(error)
    before = target.read_bytes()
    if (
        hashlib.sha256(before).hexdigest() != PROVENANCE_BEFORE_SHA256
        or hashlib.sha256(current).hexdigest() != PROVENANCE_AFTER_SHA256
    ):
        raise ValueError(error)
    projected = current
    for addition in PROVENANCE_ADDITIONS:
        if projected.count(addition) != 1:
            raise ValueError(error)
        projected = projected.replace(addition, b"", 1)
    if projected != before:
        raise ValueError(error)
    return before
