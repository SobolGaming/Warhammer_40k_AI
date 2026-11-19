from __future__ import annotations

import hashlib
import json

import pytest

from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError
from warhammer40k_core.geometry.milli_inch_oval_oval import oval_oval_relation
from warhammer40k_core.geometry.milli_inch_oval_oval_distance import oval_oval_distance_ticks


@pytest.mark.parametrize(("facing", "normalized"), [(180, 0), (225, 45), (-90, 90), (-45, 135)])
def test_canonical_oval_payload_round_trips_exactly(facing: int, normalized: int) -> None:
    low, high = -(2**63), 2**63 - 1
    oval = CanonicalOval((low, high), high, 7, facing)
    payload = oval.to_payload()
    assert payload == {
        "schema_version": "milli-inch-oval-v1",
        "numerical_policy_id": "milli-inch-half-away-v1",
        "center": [low, high],
        "length_ticks": high,
        "width_ticks": 7,
        "facing_degrees": normalized,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    restored = CanonicalOval.from_payload(json.loads(encoded))
    assert restored == oval
    assert (
        json.dumps(restored.to_payload(), sort_keys=True, separators=(",", ":")).encode() == encoded
    )
    assert restored.content_hash == oval.content_hash == hashlib.sha256(encoded).hexdigest()


def test_canonical_oval_payload_detaches_center_and_retains_equal_axis_facing() -> None:
    oval = CanonicalOval((-9, 13), 7, 7, 45)
    payload = oval.to_payload()
    restored = CanonicalOval.from_payload(payload)
    payload["center"][0] = 0
    assert restored == oval
    assert oval.to_payload()["center"] == [-9, 13]
    assert restored.facing_degrees == 45
    assert restored.content_hash != CanonicalOval(oval.center, 7, 7, 135).content_hash


def test_canonical_oval_payload_requires_an_exact_object_shape() -> None:
    class FieldName(str):
        pass

    payload = CanonicalOval((0, 0), 11, 7).to_payload()
    mistyped_keys = {FieldName(key): value for key, value in payload.items()}
    for invalid in (
        None,
        [],
        "oval",
        list(payload.items()),
        mistyped_keys,
        {**payload, "radius_ticks": 5},
    ):
        with pytest.raises(CanonicalOvalError):
            CanonicalOval.from_payload(invalid)
    for missing in payload:
        with pytest.raises(CanonicalOvalError):
            CanonicalOval.from_payload(
                {key: value for key, value in payload.items() if key != missing}
            )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("schema_version", "milli-inch-oval-v2"),
        ("schema_version", False),
        ("numerical_policy_id", "legacy-binary-inch-v1"),
        ("numerical_policy_id", 1),
        ("center", (0, 0)),
        ("center", [0]),
        ("center", [0, 0, 0]),
        ("center", [True, 0]),
        ("center", [0, 0.0]),
        ("center", [-(2**63) - 1, 0]),
        ("center", [0, 2**63]),
        ("length_ticks", 11.0),
        ("length_ticks", 2**63),
        ("length_ticks", 6),
        ("width_ticks", True),
        ("width_ticks", "7"),
        ("width_ticks", 0),
        ("facing_degrees", False),
        ("facing_degrees", 45.0),
        ("facing_degrees", 30),
        ("facing_degrees", -45),
        ("facing_degrees", 180),
        ("facing_degrees", 225),
    ],
)
def test_canonical_oval_payload_rejects_noncanonical_values(field: str, invalid: object) -> None:
    payload = CanonicalOval((0, 0), 11, 7, 45).to_payload()
    with pytest.raises(CanonicalOvalError):
        CanonicalOval.from_payload({**payload, field: invalid})


@pytest.mark.parametrize(
    ("first", "second", "relation", "gap"),
    [
        (
            CanonicalOval((0, 0), 70, 10, 0),
            CanonicalOval((85, -48), 140, 20, 135),
            CircleRelation.EXTERNAL_CONTACT,
            0,
        ),
        (
            CanonicalOval((0, 0), 70, 10, 0),
            CanonicalOval((84, -48), 140, 20, 135),
            CircleRelation.INTERIOR_OVERLAP,
            0,
        ),
        (
            CanonicalOval((0, 0), 85, 34, 0),
            CanonicalOval((64, 118), 234, 130, 90),
            CircleRelation.SEPARATED,
            3,  # Exact 2.5-tick gap.
        ),
    ],
)
def test_restored_ovals_preserve_relation_and_rounded_gap(
    first: CanonicalOval, second: CanonicalOval, relation: CircleRelation, gap: int
) -> None:
    for left, right in (
        (first, second),
        (
            CanonicalOval.from_payload(first.to_payload()),
            CanonicalOval.from_payload(second.to_payload()),
        ),
    ):
        assert oval_oval_relation(left, right) is relation
        assert oval_oval_distance_ticks(left, right) == gap
