"""Explicitly approved legacy dice metadata for unchanged scalar LOS domains.

This is never visibility proof. Current witnesses retain complete physical input
and battlefield fingerprints; fresh context equality authenticates this separate
projection. Only the copied RNG view uses these legacy metadata values.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.continuous_visibility import prism_fingerprint_payload
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism

LOS_RNG_PROJECTION_VERSION = "unchanged-scalar-los-rng:1"
LEGACY_VISIBILITY_ALGORITHM_ID = "continuous-analytic-prism-visibility:1"


def legacy_scalar_input_fingerprint(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    visibility_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
) -> str:
    """Exact authentic v1 encoding; caller must prove unchanged scalar domain."""
    payload = [
        LEGACY_VISIBILITY_ALGORITHM_ID,
        prism_fingerprint_payload(observer),
        prism_fingerprint_payload(target),
        [prism_fingerprint_payload(blocker) for blocker in visibility_blockers],
        [prism_fingerprint_payload(blocker) for blocker in full_blockers],
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


class VisibilityRngPairPayload(TypedDict):
    target_model_id: str
    input_fingerprint: str


class VisibilityRngProjectionPayload(TypedDict):
    version: str
    context_fingerprint: str
    pairs: list[VisibilityRngPairPayload]


def _fingerprint(value: object) -> str:
    if type(value) is not str:
        raise GeometryError("LOS RNG projection requires canonical SHA256 fingerprints.")
    result = value
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise GeometryError("LOS RNG projection requires canonical SHA256 fingerprints.")
    return result


@dataclass(frozen=True, slots=True)
class VisibilityRngProjection:
    context_fingerprint: str
    pairs: tuple[tuple[str, str], ...]
    version: str = LOS_RNG_PROJECTION_VERSION

    def __post_init__(self) -> None:
        if self.version != LOS_RNG_PROJECTION_VERSION or type(self.version) is not str:
            raise GeometryError("Unsupported LOS RNG projection version.")
        _fingerprint(self.context_fingerprint)
        if type(self.pairs) is not tuple:
            raise GeometryError("LOS RNG projection pairs must be an immutable tuple.")
        seen: set[str] = set()
        for pair in self.pairs:
            if type(pair) is not tuple or len(pair) != 2:
                raise GeometryError("LOS RNG projection pairs require target ID and fingerprint.")
            target, fingerprint = pair
            if type(target) is not str or not target or target.strip() != target or target in seen:
                raise GeometryError("LOS RNG projection requires unique canonical target IDs.")
            seen.add(target)
            _fingerprint(fingerprint)

    def to_payload(self) -> VisibilityRngProjectionPayload:
        return {
            "version": self.version,
            "context_fingerprint": self.context_fingerprint,
            "pairs": [
                {"target_model_id": target, "input_fingerprint": fingerprint}
                for target, fingerprint in self.pairs
            ],
        }

    @classmethod
    def from_payload(cls, payload: VisibilityRngProjectionPayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) != set(
            VisibilityRngProjectionPayload.__required_keys__
        ):
            raise GeometryError("Invalid LOS RNG projection fields.")
        if type(payload["pairs"]) is not list:
            raise GeometryError("LOS RNG projection pairs must be a list.")
        pairs: list[tuple[str, str]] = []
        for row in payload["pairs"]:
            if type(cast(object, row)) is not dict or set(row) != set(
                VisibilityRngPairPayload.__required_keys__
            ):
                raise GeometryError("Invalid LOS RNG projection pair fields.")
            pairs.append((row["target_model_id"], row["input_fingerprint"]))
        return cls(payload["context_fingerprint"], tuple(pairs), payload["version"])
