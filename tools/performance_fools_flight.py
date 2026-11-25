"""Bind one source-only Fool's Flight eligibility edit to the existing serial smoke."""

from __future__ import annotations

import hashlib
from pathlib import Path

BASE = "740b558ab5542e4120fdc49d05bb6819d1b53698"
PATH = "src/warhammer40k_core/engine/stratagems_eligibility.py"
SCOPE = "docs/performance/policy-v3/fools-flight-smoke-scope.json"
SCOPE_SHA256 = "3f44ce8e95c64c0a4c3a9f9d96b816b814fa96cbd575ff283f2f688972fa00e5"
_POLICY_BEFORE = "7f522cd8485dc761ba56dd271728222fbace7dcc1c93134a51bff7b7b67728b5"
_POLICY_AFTER = "b50d348363bd0926f6b8bbc09f15a4269ec2e723ef05f28841bf7d6ed1b66358"
_INSERTIONS = (
    b"        from tools.performance_fools_flight import fools_flight_smoke_operations\n",
    b"            | fools_flight_smoke_operations(\n"
    b"                base=base, path=path, category=category, change=changes[path]\n"
    b"            )\n",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fools_flight_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    if base != BASE or path != PATH or category != "rule_semantics":
        return frozenset()
    from tools.performance_policy import read_object

    file = Path(__file__).resolve().parents[1] / SCOPE
    if _sha(file.read_bytes()) != SCOPE_SHA256:
        raise ValueError("Fool's Flight performance scope bytes drifted.")
    scope = read_object(file)
    if scope["base"] != base or scope["path"] != path or scope["change"] != change:
        return frozenset()
    return frozenset({"order135-visibility-hot-consumers"})


def fools_flight_policy_predecessor(raw: bytes) -> bytes:
    """Recover the exact unchanged Dark Pact policy before replaying its proof."""
    if not any(part in raw for part in _INSERTIONS):
        return raw
    if _sha(raw) != _POLICY_AFTER or any(raw.count(part) != 1 for part in _INSERTIONS):
        raise ValueError("Fool's Flight performance policy successor drifted.")
    for part in _INSERTIONS:
        raw = raw.replace(part, b"", 1)
    if _sha(raw) != _POLICY_BEFORE:
        raise ValueError("Fool's Flight performance policy predecessor drifted.")
    return raw
