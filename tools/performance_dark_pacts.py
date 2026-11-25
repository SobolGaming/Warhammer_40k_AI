"""Classify exact Dark Pact orchestration edits without changing benchmark policy."""

from __future__ import annotations

import hashlib
from pathlib import Path

BASE = "ab3a4ac03854964649f74efe5b8cebd528d3e25a"
SCOPE = "docs/performance/policy-v3/dark-pact-timing-scope.json"
OPERATIONS = {
    "scripts/build_test_shards.py": frozenset(
        {"ci78-cutover-owners-83cd0803bcde80cbfc805d2a110f3274d501da3bc2230de8cc7f95cc0cbd608f"}
    ),
    "src/warhammer40k_core/engine/lifecycle.py": frozenset(
        {"order135-gathered-attack-steps", "d04-combat-lifecycle-continuation"}
    ),
    "src/warhammer40k_core/engine/phases/fight.py": frozenset(
        {"order103-src-warhammer40k_core-engine-phases-fight"}
    ),
    "src/warhammer40k_core/engine/phases/shooting_handler.py": frozenset(
        {"order103-src-warhammer40k_core-engine-phases-shooting_handler"}
    ),
}


def dark_pacts_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    if base != BASE or category != "rule_semantics" or path not in OPERATIONS:
        return frozenset()
    from tools.performance_policy import object_value, read_object

    scope = read_object(Path(__file__).resolve().parents[1] / SCOPE)
    changes = object_value(scope["changes"])
    if scope["base"] != base or changes.keys() != OPERATIONS.keys() or changes[path] != change:
        return frozenset()
    return OPERATIONS[path]


RETIRED_COMPLETION_OPERATION = "dark-pact-timing-retired-completion"
RETIRED_COMPLETION_SOURCE = (
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
    "chaos_space_marines/completion_sequencing.py"
)
RETIRED_COMPLETION_SHA256 = "0ecada76e882ec1f4f15861f2cbd304d7a5474249ffe2b21c39d86b2aa572cc1"
_POLICY_BEFORE = "6da5eb9e49bb2e521afe322cae620dde2e40162fbdc7605326cde2d28f0dbf6c"
_POLICY_AFTER = "7f522cd8485dc761ba56dd271728222fbace7dcc1c93134a51bff7b7b67728b5"
_INSERTIONS = (
    b"        from tools.performance_dark_pacts import dark_pacts_smoke_operations\n",
    b"            | dark_pacts_smoke_operations(\n"
    b"                base=base, path=path, category=category, change=changes[path]\n"
    b"            )\n",
)


def dark_pacts_policy_predecessor(raw: bytes) -> bytes:
    """Recover the exact policy used by earlier hash-bound receipts."""
    if not any(part in raw for part in _INSERTIONS):
        return raw
    if hashlib.sha256(raw).hexdigest() != _POLICY_AFTER:
        raise ValueError("Dark Pact policy successor drifted.")
    for part in _INSERTIONS:
        if raw.count(part) != 1:
            raise ValueError("Dark Pact policy insertion identity drifted.")
        raw = raw.replace(part, b"", 1)
    if hashlib.sha256(raw).hexdigest() != _POLICY_BEFORE:
        raise ValueError("Dark Pact historical performance policy preimage drifted.")
    return raw
