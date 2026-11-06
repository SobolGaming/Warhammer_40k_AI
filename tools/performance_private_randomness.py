"""Exact PR2 private-RNG semantic applicability; serializer comparisons stay mandatory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

BASE = "2b640ffca912f72d74e3b08cec0c0c4b12ce776a"
SCOPE = "docs/performance/policy-v3/private-rng-smoke-scope.json"
OPERATIONS: dict[str, list[str]] = {
    "tests/disembark_eligibility_helpers.py": ["fixture-reconstruction"],
    "tests/order63_reserve_transport_helpers.py": ["fixture-reconstruction", "fixture-setup"],
    "contracts/schemas/game-view.schema.json": ["qualification40-exact-9a69b77fc8902bb0"],
    "src/warhammer40k_core/engine/attack_completion_triggers.py": ["cumulative-exact-008"],
    "src/warhammer40k_core/engine/attack_sequence_dice_rerolls.py": [
        "order135-gathered-attack-steps"
    ],
    "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py": [
        "ci78-current-owner-closure-f83517431236fc6310408e45339dac64861443343978ac8ee40fe7ae28b8593b"
    ],
    "src/warhammer40k_core/engine/desperate_escape_mortal_wounds.py": ["cumulative-exact-020"],
    (
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
        "thousand_sons/army_rule.py"
    ): ["order135-visibility-hot-consumers"],
    "src/warhammer40k_core/engine/lifecycle.py": [
        "d04-combat-lifecycle-continuation",
        "order135-gathered-attack-steps",
    ],
    "src/warhammer40k_core/engine/phases/movement_rules_unit_disembark.py": [
        "d04-combat-direct-status",
        "order135-tactical-exclusion",
    ],
    "src/warhammer40k_core/engine/phases/shooting_surge_candidates.py": ["cumulative-exact-034"],
    "src/warhammer40k_core/engine/rule_model_destruction.py": ["cumulative-exact-039"],
    "src/warhammer40k_core/engine/transports.py": ["order135-grouped-combat-decoding"],
    "tests/dice_result_semantics_helpers.py": ["fixture-dice"],
    "tests/phase11c_command_phase_helpers.py": ["fixture-objective_control"],
    "tests/phase13b_shooting_declaration_helpers.py": ["fixture-visibility"],
    "tests/phase15c_fight_order_helpers.py": ["fixture-fight"],
    "tests/support/fight_phase_reconstruction.py": [
        "ci78-cutover-owners-2da5cb2ac2e33579aae933134e54539766dd5c6c28c88a269ec8233e8efe78ce"
    ],
}
PRIOR_POLICY_SHA256 = "cc2c9c9925ed6bb6487990c026a459181894e81d30989861bad498b3694fdb9a"
INSERTIONS = (
    b"    from tools.performance_private_randomness import private_randomness_policy_predecessor\n",
    b"    raw = private_randomness_policy_predecessor(raw)\n",
    (
        b"        from tools.performance_private_randomness import "
        b"private_randomness_smoke_operations\n"
    ),
    (
        b"            | private_randomness_smoke_operations(\n"
        b"                base=base, path=path, category=category, change=changes[path]\n"
        b"            )\n"
    ),
)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _scope() -> dict[str, Any]:
    value = json.loads((Path(__file__).resolve().parents[1] / SCOPE).read_bytes())
    if type(value) is not dict or set(value) != {
        "base",
        "changes",
        "smoke_operations",
        "source_obligation",
        "unchanged_work",
        "module_sha256",
        "policy_before_sha256",
        "policy_after_sha256",
    }:
        raise ValueError("Private RNG applicability fields drifted.")
    scope = cast("dict[str, Any]", value)
    if (
        scope["base"] != BASE
        or scope["smoke_operations"] != OPERATIONS
        or set(scope["changes"]) != set(OPERATIONS)
        or scope["module_sha256"] != _hash(Path(__file__).read_bytes())
        or scope["policy_before_sha256"] != PRIOR_POLICY_SHA256
        or any(
            "cache" in key or "serialization" in key for keys in OPERATIONS.values() for key in keys
        )
    ):
        raise ValueError("Private RNG applicability identity or operations drifted.")
    return scope


def private_randomness_policy_predecessor(raw: bytes) -> bytes:
    """Strip only this authenticated insertion before existing historical proofs."""
    if not any(part in raw for part in INSERTIONS):
        return raw
    scope = _scope()
    if _hash(raw) != scope["policy_after_sha256"] or any(raw.count(p) != 1 for p in INSERTIONS):
        raise ValueError("Private RNG policy successor drifted.")
    for part in INSERTIONS:
        raw = raw.replace(part, b"", 1)
    if _hash(raw) != PRIOR_POLICY_SHA256:
        raise ValueError("Private RNG policy predecessor drifted.")
    return raw


def private_randomness_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    if base != BASE or category != "rule_semantics" or path not in OPERATIONS:
        return frozenset()
    scope = _scope()
    private_randomness_policy_predecessor(
        Path(__file__).with_name("performance_policy.py").read_bytes()
    )
    if scope["changes"][path] != change:
        return frozenset()
    return frozenset(OPERATIONS[path])
