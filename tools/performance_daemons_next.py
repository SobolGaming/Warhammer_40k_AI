"""Exact-base Daemons source semantics admission; no timing or family relaxation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

BASE = "baeb3e1f0d12d00ec41f55046fc754e19cee5dd2"
PRIOR_POLICY_SHA256 = "8cd7b97a934f6fb6c71270f0004850f7203a12ed3d19548f005b2156a3b8900c"
SCOPE = "docs/performance/policy-v3/daemons-next-three-smoke-scope.json"
OPERATIONS = {
    "tools/ability_support_sources.py": "qualification40-exact-b0712fa66a9cc38e",
}
IMPORT = b"    from tools.performance_daemons_next import daemons_next_policy_predecessor\n"
SMOKE_IMPORT = b"        from tools.performance_daemons_next import daemons_next_smoke_operations\n"
CALL = (
    b"            | daemons_next_smoke_operations(\n"
    b"                base=base, path=path, category=category, change=changes[path]\n"
    b"            )\n"
)
PREDECESSOR = b"    raw = daemons_next_policy_predecessor(raw)\n"


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _scope() -> dict[str, Any]:
    value = json.loads((Path(__file__).resolve().parents[1] / SCOPE).read_bytes())
    if type(value) is not dict or set(cast(dict[str, Any], value)) != {
        "base",
        "changes",
        "smoke_operations",
        "source_obligation",
        "unchanged_work",
        "policy_successor",
        "module_sha256",
    }:
        raise ValueError("Daemons next-three scope fields drifted.")
    if value["base"] != BASE or value["module_sha256"] != _hash(Path(__file__).read_bytes()):
        raise ValueError("Daemons next-three scope identity drifted.")
    return cast(dict[str, Any], value)


def daemons_next_policy_predecessor(raw: bytes) -> bytes:
    """Authenticate bounded insertions before the unchanged historical policy chain."""
    if _hash(raw) in {
        PRIOR_POLICY_SHA256,
        "879f0ca4328865a8f24c515abaa894dc8628a49865dcdb817902b94dc7e02a4a",
        "53855381390dae96880a448d0bf3729fa9099280441aad539e5db56124134526",
    }:
        return raw
    scope = _scope()
    proof = scope["policy_successor"]
    error = (
        "Core description policy: Whispering Web successor: "
        "Starfang/Deep Strike: Daemons next-three"
    )
    if proof != {
        "before_sha256": PRIOR_POLICY_SHA256,
        "after_sha256": _hash(raw),
        "import_sha256": _hash(IMPORT),
        "call_sha256": _hash(CALL),
        "predecessor_sha256": _hash(PREDECESSOR),
        "smoke_import_sha256": _hash(SMOKE_IMPORT),
    } or any(raw.count(part) != 1 for part in (IMPORT, SMOKE_IMPORT, CALL, PREDECESSOR)):
        raise ValueError(error + " policy successor drifted.")
    prior = (
        raw.replace(IMPORT, b"", 1)
        .replace(SMOKE_IMPORT, b"", 1)
        .replace(CALL, b"", 1)
        .replace(PREDECESSOR, b"", 1)
    )
    if _hash(prior) != PRIOR_POLICY_SHA256:
        raise ValueError(error + " predecessor bytes drifted.")
    return prior


def daemons_next_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    if base != BASE or category != "rule_semantics" or path not in OPERATIONS:
        return frozenset()
    scope = _scope()
    daemons_next_policy_predecessor(Path(__file__).with_name("performance_policy.py").read_bytes())
    if set(scope["changes"]) != set(OPERATIONS) or scope["smoke_operations"] != {
        name: [operation] for name, operation in OPERATIONS.items()
    }:
        raise ValueError("Daemons next-three scope operations drifted.")
    owners = {"tools/ability_support_sources.py": {"ability_support_index_inputs"}}
    for name, binding in scope["changes"].items():
        if (
            set(binding) != {"before_sha256", "after_sha256", "owners"}
            or set(binding["owners"]) != owners[name]
        ):
            raise ValueError("Daemons next-three scope owners drifted.")
        pairs = {
            "@file": {"before": binding["before_sha256"], "after": binding["after_sha256"]},
            **binding["owners"],
        }
        for owner, pair in pairs.items():
            if set(pair) != {"before", "after"}:
                raise ValueError("Daemons next-three scope owner hash fields drifted.")
            for side, value in pair.items():
                if (
                    owner == "load_before_daemons_next_three_sources"
                    and side == "before"
                    and value is None
                ):
                    continue
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or set(value) - set("0123456789abcdef")
                ):
                    raise ValueError("Daemons next-three scope requires exact owner hashes.")
    if scope["changes"][path] != change:
        return frozenset()
    return frozenset({OPERATIONS[path]})
