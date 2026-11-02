"""Exact additive Acts regression projection for immutable migrated history."""

import ast
import hashlib
import json
from pathlib import Path

TEST_PATH = "tests/infrastructure/runtime_hooks/unit/test_runtime_hook_bindings.py"
ARCHIVE = "docs/performance/policy-v3/acts-provenance-20261031/runtime-hook-predecessor.py.txt"
BEFORE_SHA256 = "2097b78ccf59d264f9dfdba560697c84984afa0b7ad61c4ae18d208f1435a0a2"
ADDITIONS = {
    "test_acts_of_faith_uses_turn_start_and_preserves_triumph_round_hook": (
        "544ab81bdefc8c7ab950885cef33d51ccfa6db512146532c2f58af0e4582949e"
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
    if path == CONSUMER_PATH:
        return acts_consumer_predecessor(root, current)
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


CONSUMER_PATH = "tests/shared/category_migration/reporting__test_runtime_consumer_evidence.py"
CONSUMER_ARCHIVE = (
    "docs/performance/policy-v3/acts-provenance-20261031/runtime-consumer-predecessor.py.txt"
)
CONSUMER_BEFORE_SHA256 = "2606d89d43fffdecffafbb301fe19e561119a57629dbd29d2d7a8ba2bef261c9"
CONSUMER_OLD_TOKEN = b"adepta_sororitas_army_rule.BATTLE_ROUND_START_HOOK_ID"
CONSUMER_NEW_TOKEN = b"adepta_sororitas_army_rule.TURN_START_HOOK_ID"


def acts_consumer_predecessor(root: Path, current: bytes) -> bytes:
    """Authenticate exactly one live expected-consumer rename before historical checks."""
    target = root / CONSUMER_ARCHIVE
    error = "Acts runtime-consumer predecessor or exact token substitution changed."
    if target.is_symlink() or not target.is_file():
        raise ValueError(error)
    before = target.read_bytes()
    if (
        hashlib.sha256(before).hexdigest() != CONSUMER_BEFORE_SHA256
        or before.count(CONSUMER_OLD_TOKEN) != 1
        or before.replace(CONSUMER_OLD_TOKEN, CONSUMER_NEW_TOKEN, 1) != current
    ):
        raise ValueError(error)
    return before


INACTIVE_PATH = "tests/unit/test_phase17g_adepta_sororitas_army_rule.py"
INACTIVE_ARCHIVE = (
    "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-predecessor.py.txt"
)
INACTIVE_RECIPE = (
    "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-api-recipe.json"
)
INACTIVE_BEFORE_SHA256 = "c4fe28349415081f36acaf612cd6715d8a383c6892e70830ad1bcc1d6a4e968e"
INACTIVE_RECIPE_SHA256 = "7206bee260fe831e3c9626042dd4e7954dea5e074590a32f9cb40cd6161e82fa"


def acts_inactive_predecessor(root: Path, current: bytes) -> bytes:
    """Retain the unadmitted module's original assertions under exact typed API edits."""
    targets = (root / INACTIVE_ARCHIVE, root / INACTIVE_RECIPE)
    error = "Acts inactive API predecessor or finite recipe changed."
    if any(target.is_symlink() or not target.is_file() for target in targets):
        raise ValueError(error)
    before, recipe = (target.read_bytes() for target in targets)
    if (
        hashlib.sha256(before).hexdigest() != INACTIVE_BEFORE_SHA256
        or hashlib.sha256(recipe).hexdigest() != INACTIVE_RECIPE_SHA256
    ):
        raise ValueError(error)
    projected = before
    for edit in json.loads(recipe):
        old, new = edit["before"].encode(), edit["after"].encode()
        if projected.count(old) != edit["count"]:
            raise ValueError(error)
        projected = projected.replace(old, new)
    if projected != current:
        raise ValueError(error)
    return before


def defiler_provenance_predecessor(current: bytes) -> bytes:
    """Reverse exact current admissions, then retain the original Defiler/Acts proof."""
    if hashlib.sha256(current).hexdigest() == (
        "e755f0325fd4b8d2877f6389962177483d0731a97d880929b8541da9d1da71be"
    ):
        # Reverse only the exact Sorcerer table addition before the retained EC proof.
        addition = (
            b"\n"
            b"SORCERER_OVERLAY = (\n"
            b'    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"\n'
            b'    "emperors_children_sorcerer_2026_11.overlay-pack.json"\n'
            b")\n"
            b'SORCERER_OVERLAY_SHA256 = "'
            b'735e021d0df16ee20f54f742a562152bed109c77ea600e35c90420abc8c7ab7a"\n'
        )
        successor = (
            b"    reviewed_hash = {\n"
            b"        root / CURRENT_EC_OVERLAY: CURRENT_EC_OVERLAY_SHA256,\n"
            b"        root / SORCERER_OVERLAY: SORCERER_OVERLAY_SHA256,\n"
            b"    }.get(path)\n"
            b"    if reviewed_hash is None:\n"
            b"        return None\n"
            b"    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != reviewed_hash:\n"
        )
        predecessor = (
            b"    if path != root / CURRENT_EC_OVERLAY:\n"
            b"        return None\n"
            b"    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != "
            b"CURRENT_EC_OVERLAY_SHA256:\n"
        )
        if current.count(addition) != 1 or current.count(successor) != 1:
            raise ValueError("Exact registered edition provenance inputs changed.")
        current = current.replace(addition, b"", 1).replace(successor, predecessor, 1)
        if hashlib.sha256(current).hexdigest() != (
            "7d5dbcca852a9ae237fe79b8d518e8b1a08f776a8af448ee19439746735ad732"
        ):
            raise ValueError("Exact registered edition provenance inputs changed.")
    if hashlib.sha256(current).hexdigest() == (
        "7d5dbcca852a9ae237fe79b8d518e8b1a08f776a8af448ee19439746735ad732"
    ):
        # Authenticate the complete EC successor before removing its two finite additions.
        begin = (
            b"# Current source-only admission: historical base metadata "
            b"remains exact and immutable.\n"
        )
        end = b"\ndef registered_provenance_context("
        route = (
            b"    current = current_ec_overlay_provenance(root, path, raw)\n"
            b"    if current is not None:\n"
            b"        return current\n"
        )
        if current.count(begin) != 1 or current.count(end) != 1 or current.count(route) != 1:
            raise ValueError("Exact registered edition provenance inputs changed.")
        start = current.index(begin)
        predecessor = current[:start] + current[current.index(end, start) :]
        predecessor = predecessor.replace(route, b"", 1)
        if hashlib.sha256(predecessor).hexdigest() != (
            "26b77718d94a586afebf33f90d1ca1eb0c7df17a5e922f054b28d5901abe938b"
        ):
            raise ValueError("Exact registered edition provenance inputs changed.")
        current = predecessor
    old = b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE,)"
    new = b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE, scopes.DEFILER_BASE)"
    if current.count(new) != 1:
        raise ValueError("Exact registered edition provenance inputs changed.")
    predecessor = current.replace(new, old, 1)
    if hashlib.sha256(predecessor).hexdigest() != PROVENANCE_AFTER_SHA256:
        raise ValueError("Exact registered edition provenance inputs changed.")
    return predecessor
