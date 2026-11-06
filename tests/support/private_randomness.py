"""Public deterministic seed material for canonical tests, never real game creation."""

from __future__ import annotations

import hashlib


def fixture_private_rng_seed(label: str | int) -> str:
    return hashlib.sha256(f"core-v2-test-fixture:{label}".encode()).hexdigest()
